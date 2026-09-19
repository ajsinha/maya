# Schema rebuild: export → `init-db` → import

For the administrator upgrading MAYA to a version whose database schema changed, or facing a
server that refuses to start with *Schema mismatch*. MAYA has no migrations
([ADR-012](../adr/ADR-012-no-migrations-two-generated-schema-files.md)): a database whose
schema is not the code's is not altered in place, it is rebuilt from an export. This is the
only upgrade path there is, so it is worth doing carefully — the one irreversible step,
`init-db --force`, destroys the old database, and an import can be refused after it has run.

## Symptoms

- `run_maya_web.py` refuses to start:

  ```text
  maya.core.errors.ConfigurationError: Schema mismatch: the database was created from a
  different schema (stored <12 hex>, code expects <12 hex>). MAYA has no migrations. Rebuild with:
    python -m maya.cli admin export-estate --out estate.mayabundle
    python -m maya.cli admin init-db --force
    python -m maya.cli admin import-estate --in estate.mayabundle
  ```

  Those three commands are right, but run bare they rebuild in place and give you no way back.
  Use the steps below instead.
- A release's changelog says the schema changed.
- Startup refuses with *"The database has no MAYA schema. Run 'python -m maya.cli admin
  init-db'."* — that is an empty database, not a mismatch: run `admin init-db` and stop here.

## Diagnosis

```bash
# The hash the database was created with (read-only)
python -c "import sqlite3,sys; print(dict(sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True).execute('SELECT key, value FROM schema_meta')))" "$MAYA_HOME/maya.db"
# PostgreSQL:  psql -d maya -c "SELECT key, value FROM schema_meta"

# The hash the installed code expects
grep -m1 "schema-hash" maya/persistence/schema/sqlite.sql        # or postgresql.sql
```

Different hashes: a rebuild is needed. The same hash but still refused: you are pointing at a
different database than you think — check `MAYA_HOME`, `db.dialect` and `db.sqlite.path` or
`db.postgresql.*`.

## Before you start

1. **Record the audit chain head while the old version still runs**, so you can prove the
   rebuild carried the chain intact:

   ```bash
   curl -s "$MAYA_URL/api/v1/audit/verify" -H "Authorization: Bearer $MAYA_API_KEY"
   # {"ok":true,"checked":<n>,"head":"<64 hex>"}
   ```

2. **Stop every MAYA process.** Anything written between the export and the import is lost.
3. **Back up the database** (the [restore drill](restore-drill.md) has the commands). Keep it
   until the new database has been verified and has run for a while.

## Steps

1. **Install the new version, then export.** The export reads the database as it is, without
   the schema check ([ADR-023](../adr/ADR-023-estate-export-reads-the-database-as-it-is.md)),
   so it works with the new code already installed — and it must be run by the new code:
   `not_carried` is computed against the code that exports, and an import silently drops any
   column or table the loading code does not know. An estate exported by the old version and
   loaded by the new one loses removed columns with no record of it.

   ```bash
   python -m maya.cli admin export-estate --out estate-$(date +%F).mayabundle
   # Estate written to estate-<date>.mayabundle
   ```

2. **Read the manifest before going further.** The export does not print what it could not
   carry:

   ```bash
   python -c "import json,sys,zipfile; m=json.loads(zipfile.ZipFile(sys.argv[1]).read('manifest.json')); print(m['maya_version'], m['source_dialect'], sum(t['rows'] for t in m['tables'].values()), 'rows'); print('not_carried:', json.dumps(m['not_carried'], indent=2))" estate-<date>.mayabundle
   ```

   `not_carried` names every column (`{"namespaces": ["legacy_cost_centre"]}`) and whole table
   (`["(the whole table)"]`) the database has and the new code does not. Their data will not
   be in the new database. If any of it matters, stop and keep the old version running.

3. **Create the new schema beside the old one**, so the old database is never touched:

   ```bash
   # SQLite: a new file under the storage root
   python -m maya.cli admin init-db --db.sqlite.path="$MAYA_HOME/maya-new.db"
   # PostgreSQL: a new, empty database the MAYA role owns (not exercised here)
   #   createdb -O maya maya_new
   #   python -m maya.cli admin init-db --db.postgresql.database=maya_new
   ```

   Rebuilding in place (`admin init-db --force`) also works, but on PostgreSQL it runs
   `DROP SCHEMA public CASCADE` — everything in that schema, MAYA's or not — and on either
   dialect it leaves no way back but your backup.

4. **Import**, with the same flag:

   ```bash
   python -m maya.cli admin import-estate --in estate-<date>.mayabundle --db.sqlite.path="$MAYA_HOME/maya-new.db"
   ```

   It verifies every table's SHA-256, loads everything in one transaction, advances the
   PostgreSQL sequences, verifies the audit chain, and prints the row count per table and
   `"audit_chain": {"ok": true, "checked": <n>, "head": "<64 hex>"}`.

5. **Put the new database in place.** SQLite: move the old `maya.db` (with any `maya.db-wal`
   and `maya.db-shm`) aside and rename `maya-new.db` to `maya.db`, or set `db.sqlite.path` in
   `config/application.local.yaml`. PostgreSQL: set `db.postgresql.database` (or
   `MAYA_PG_DATABASE`) to the new database.

6. **Start MAYA** with `python run_maya_web.py`.

## If the import refuses

- **A required column the estate cannot fill:**

  ```text
  maya: ValidationFailed: Table <table>: the estate has no values for required column(s)
  <columns>, and the schema gives them no default. Give them a default in the model, or fill
  them in the export, before loading.
  ```

  The new release added a required column with no default, which breaks every upgrade into
  it. That is a release defect: report it. Nothing was written — the target is still an empty
  schema and can take another import without a fresh `init-db`. Either stay on the old
  version, or fill the column in the estate. Filling it means writing values into the record
  that nobody entered, so choose values you can defend and write down why. A table's hash is
  checked on import, so the manifest must be re-hashed; this script does both:

  ```python
  # fill_column.py — python fill_column.py IN.mayabundle OUT.mayabundle TABLE COLUMN VALUE
  import hashlib, json, sys, zipfile
  src, dst, table, column, value = sys.argv[1:6]
  with zipfile.ZipFile(src) as z:
      files = {n: z.read(n) for n in z.namelist()}
  manifest = json.loads(files["manifest.json"])
  name = f"tables/{table}.jsonl"
  rows = [json.loads(line) for line in files[name].decode().splitlines() if line]
  for r in rows:
      r.setdefault(column, value)
  body = "\n".join(json.dumps(r, sort_keys=True) for r in rows)
  files[name] = body.encode()
  manifest["tables"][table]["sha256"] = hashlib.sha256(body.encode()).hexdigest()
  files["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode()
  with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
      for n, b in files.items():
          z.writestr(n, b)
  print(f"{len(rows)} row(s) of {table} given {column}={value!r}; wrote {dst}")
  ```

  It sets a text value; a column of another type needs the value in the estate's encoding.
- **`Table <table> failed its hash check`** — the bundle was altered or damaged. Export again.
- **`Not a MAYA estate bundle`** — the file is not an estate.
- **A raw `sqlalchemy.exc.IntegrityError` traceback** (`UNIQUE constraint failed`) — the
  target was not empty: MAYA was started on it (which seeds roles, policies and the admin) or
  an import already ran. The load is one transaction, so nothing was written. Run
  `admin init-db --force` on the *target* and import again.
- **`maya: ValidationFailed: The imported audit chain does not verify`** — careful: despite
  exit code 1, **every row has been committed**. The chain was already broken in the source.
  Do not start MAYA on the new database until you have been through the
  [audit chain runbook](audit-chain-and-custody.md) on the old one.

## Verification

- The import's `audit_chain.head` equals the head you recorded before the upgrade, and
  `checked` equals the old `checked`.
- Each table's count in the import output equals its `rows` in the manifest, except
  `schema_meta`, which is not loaded — the new schema stamps its own.
- MAYA starts; `curl -s http://<host>:<port>/readyz` answers
  `{"ready":true,"database":"schema identity verified",…}`.
- `python -m maya.cli admin verify-integrity` exits 0: `<n> pin(s) checked; drift: 0; audit
  chain ok: True`. The lake was not touched, so any drift here predates the rebuild.
- Custody anchors still agree: `GET /api/v1/custody/verify` returns `"verdict": "chain and
  anchors agree"` ([custody runbook](audit-chain-and-custody.md)).

## What this does not reach

- **Only the database moves.** `storage.root` — the lake, the blobs, the keys, the anchor
  file — is untouched and must stay where the configuration says it is.
- **`not_carried` data is gone from the new database.** It survives only in the estate bundle
  and the old database. Keep both.
- **How long it takes has not been measured.** The maintenance window is proportional to the
  estate; no benchmark of export or import time exists.
- **The procedure cannot be rehearsed against a release that does not exist yet.** The suite
  tests a round trip, a database from another schema, and the required-column refusal; the
  first real upgrade with production data will be the first real test.
