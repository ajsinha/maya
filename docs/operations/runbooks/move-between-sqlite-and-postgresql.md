# Moving between SQLite and PostgreSQL

For the administrator taking a MAYA instance from SQLite to PostgreSQL — because it has
outgrown one writing process, because it is going to `prod`, or because it needs several web
processes — or taking a copy of a PostgreSQL instance down to SQLite on a laptop. A MAYA
instance runs on exactly one database and the two are never mixed
([ADR-013](../../design/adr/ADR-013-sqlite-default-postgresql-by-config.md)); moving is the same
estate round trip as a [schema rebuild](schema-rebuild.md), with the dialect changed in the
middle.

## Symptoms that say it is time

- Startup refuses `prod` on SQLite:

  ```text
  maya.core.errors.ConfigurationError: app.environment is prod but db.dialect is sqlite.
  SQLite is a single-node, small-team backend (spec §14.1); set db.dialect=postgresql for
  production.
  ```

- Startup refuses several web processes on SQLite:

  ```text
  maya.core.errors.ConfigurationError: server.workers is <n>, but the database is SQLite,
  which admits one writing process. Use PostgreSQL (db.dialect: postgresql) for several web
  processes, or set server.workers: 1.
  ```

- The health page lists *"database: SQLite — single writer, suited to a laptop or small team;
  PostgreSQL is the production backend"* under `degraded`, and write latency grows with load.

## Diagnosis

```bash
# Which database is this instance on, and is its schema the code's?
curl -s "$MAYA_URL/api/v1/system/health" -H "Authorization: Bearer $MAYA_API_KEY" \
  | python -c "import json,sys; print(json.load(sys.stdin)['database'])"
# {'dialect': 'sqlite', 'ok': True, 'detail': 'schema identity verified', 'schema_hash': '…', 'schema_file': 'maya/persistence/schema/sqlite.sql'}
```

## SQLite to PostgreSQL

1. **Prepare PostgreSQL** (outside MAYA — MAYA creates tables, never databases or roles). A
   dedicated database the MAYA role owns, on PostgreSQL 14 or later. Use a database of its
   own: `init-db --force` on PostgreSQL runs `DROP SCHEMA public CASCADE`.
2. **Record the audit chain head**, then **stop MAYA**:

   ```bash
   curl -s "$MAYA_URL/api/v1/audit/verify" -H "Authorization: Bearer $MAYA_API_KEY"
   ```

3. **Export from SQLite**, with the environment MAYA runs with:

   ```bash
   python -m maya.cli admin export-estate --out estate-sqlite.mayabundle
   ```

4. **Create the PostgreSQL schema.** The dialect and connection come from the environment
   (or `--db.dialect=postgresql --db.postgresql.host=…` flags); keep the password in the
   environment or `config/application.local.yaml`, never in the tracked
   `config/application.yaml`, where a test fails the build on a secret:

   ```bash
   export MAYA_DB_DIALECT=postgresql MAYA_PG_HOST=db.internal MAYA_PG_PORT=5432 \
          MAYA_PG_DATABASE=maya MAYA_PG_USER=maya MAYA_PG_PASSWORD='…'
   python -m maya.cli admin init-db
   # Created the postgresql schema from maya/persistence/schema/postgresql.sql (schema-hash <16 hex>…)
   ```

   `init-db` without `--force` refuses a database that already has a MAYA schema: *"The
   database already has a MAYA schema; pass --force to drop and recreate it."* That refusal
   is your protection against pointing at the wrong database; do not reach for `--force`
   until you have checked which one you are pointing at.

5. **Import into PostgreSQL**, in the same environment:

   ```bash
   python -m maya.cli admin import-estate --in estate-sqlite.mayabundle
   ```

   On PostgreSQL the import also advances every auto-numbered key past the loaded rows, so
   the first new audit entry does not collide with an imported one.

6. **Make the dialect permanent**: `db.dialect: postgresql` and the connection settings in
   `config/application.local.yaml`, or the `MAYA_DB_DIALECT` and `MAYA_PG_*` variables in the
   service definition. **Keep `storage.root` exactly where it was**: the lake, blobs, keys and
   anchor file stay put; only the database moved.
7. **Start MAYA.** `server.workers` above 1 is now allowed.

## PostgreSQL to SQLite (a copy for a laptop)

The same three commands in the other direction: export with the PostgreSQL environment, then
`init-db` and `import-estate` with SQLite and a new, empty `MAYA_HOME`. Three things differ,
and each has bitten someone:

- **Copy `storage.root` too**, or every pin is unreadable and integrity verification reports
  every one of them. The database holds the record; the lake holds the bytes.
- **Disarm webhooks in the copy before anything starts**, or the copy delivers events —
  signed with production's secrets — to production's receivers. The
  [restore drill](restore-drill.md) has the statement.
- The copy cannot run as `prod` on SQLite, and must run with `server.workers: 1`.

## If something refuses

- **A connection error** (`psycopg.OperationalError … Is the server running on that host and
  accepting TCP/IP connections?`) arrives as a raw traceback, not a MAYA refusal. Check host,
  port, database, role and password.
- **Import refusals** — a failed hash check, a required column, a non-empty target, a broken
  chain — are the same as in the [schema rebuild runbook](schema-rebuild.md#if-the-import-refuses).

## Verification

- The import prints `"audit_chain": {"ok": true, …}` with the same `head` you recorded.
- The health page shows the new dialect, `"ok": true`, and the new schema file.
- `python -m maya.cli admin verify-integrity` exits 0 with the same pin count as before.
- `GET /api/v1/custody/verify` answers `"chain and anchors agree"`.

## What this does not reach

- **No test moves an estate across dialects.** The estate format is dialect-neutral by design,
  and the round trip is tested within SQLite and within PostgreSQL 16, 17 and 18, but never
  exported from one and imported into the other. The first cross-dialect move of real data is
  the first test of it. Verify as above, and keep the source until you have.
- **The PostgreSQL commands here were not run when this runbook was written**; the connection
  settings were checked against a closed port only. PostgreSQL 14 and 15 have never been run
  at all.
- MAYA has no failover of its own. High availability is whatever the PostgreSQL deployment
  provides.
