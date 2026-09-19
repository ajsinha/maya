# Restore drill

For `techops`, quarterly, and after any change to how backups are taken. A backup nobody has
restored is a hope, not a backup (§20). The drill restores the latest backup into a scratch
environment that cannot touch production, proves that every sealed pin still re-hashes to its
seal and that the audit chain and its anchors still agree, and records the result — including
how long it took, because that is the only way MAYA's recovery-time target will ever be
measured.

## What a backup is

A MAYA instance is two things, and a backup is both, taken together:

| Part | Holds |
|---|---|
| The database | Catalog, versions, workflow, warrants, grants, users, sessions, jobs, events, the audit log, the anchors table |
| `storage.root` (`MAYA_HOME`) | The lake (every pin's bytes), the blob store (artifacts, PDFs, bundles), `keys/` (the signing key, the sealing key, the dev session secret), logs, the default anchor file — and, on SQLite, the database file |

Plus the anchor file, if `custody.anchor.file` puts it outside `storage.root` (it should: see
the [custody runbook](audit-chain-and-custody.md)).

**Take the database first, then `storage.root`.** The storage copy is then a superset of what
the database copy references — a pin sealed in between leaves unreferenced fragments, which
are harmless — never the other way round, which would give you pins whose bytes are missing.
`keys/` is part of the backup: without `keys/secretbox.key`, sealed secrets (TOTP enrolments,
webhook signing secrets) cannot be opened. Restrict who can read the backup accordingly.

## 1. Take the backup

SQLite, online (the backup API copies a consistent snapshot while MAYA runs):

```bash
python -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); print('backed up', sys.argv[1])" "$MAYA_HOME/maya.db" /backup/maya.db
tar -C "$MAYA_HOME" --exclude=./maya.db --exclude=./maya.db-wal --exclude=./maya.db-shm \
    -czf /backup/storage-root.tgz .
```

PostgreSQL (standard tooling; exercised in the drill recorded in §5):

```bash
pg_dump -Fc -d maya -f /backup/maya.dump
tar -C "$MAYA_HOME" -czf /backup/storage-root.tgz .
```

Specification §20 asks for continuous WAL archiving and nightly full backups, RPO 5 minutes and
RTO 1 hour. Those are **targets**. MAYA does not configure PostgreSQL's WAL archiving, and neither
figure has been measured.

## 2. Restore into a scratch environment

A different directory at the very least, a different host if you have one, a different port
always, and never the production database.

```bash
export MAYA_HOME=/srv/maya-drill
mkdir -p "$MAYA_HOME"
tar -C "$MAYA_HOME" -xzf /backup/storage-root.tgz
cp /backup/maya.db "$MAYA_HOME/maya.db"                       # SQLite
# PostgreSQL: createdb maya_drill && pg_restore -d maya_drill /backup/maya.dump
#             export MAYA_DB_DIALECT=postgresql MAYA_PG_DATABASE=maya_drill …
export MAYA_ANCHOR_FILE="$MAYA_HOME/anchors.jsonl"            # a copy, never production's file
export MAYA_PORT=8698
```

## 3. Disarm the copy before anything starts

The restored database holds production's webhooks and their signing secrets. The server started
in step 4 starts the webhook dispatcher at once, and would deliver pending and new events,
correctly signed, to production's receivers (the CLI's `--local` mode runs job workers only and
delivers nothing). Even the verification in step 4 emits one: `integrity.verified` is an event.
Disarm them first — a disarmed webhook's deliveries settle as "webhook is inactive; nothing was
sent":

```bash
python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); n=c.execute('UPDATE webhooks SET active = 0').rowcount; c.commit(); print(n, 'webhook(s) disarmed')" "$MAYA_HOME/maya.db"
# PostgreSQL: psql -d maya_drill -c "UPDATE webhooks SET active = false"
```

Also: if production anchors with `rfc3161`, pass `--custody.anchor.methods=signature,file,event`
to the scratch instance so it does not ask the timestamp authority to witness a drill. The
scheduler's first run, a minute after start, compacts and vacuums the copy's lake; that is
harmless to verification.

## 4. Verify

```bash
# Every sealed pin re-hashed, and the audit chain walked
MAYA_USER=<admin> MAYA_PASSWORD=<password> python -m maya.cli --local admin verify-integrity
# <n> pin(s) checked; drift: 0; audit chain ok: True        (exit 0)

# The anchors: start the copy and ask it
python run_maya_web.py --server.port=8698 &
curl -s http://127.0.0.1:8698/readyz
# {"ready":true,"database":"schema identity verified","lake":"<backend>",…}
curl -s http://127.0.0.1:8698/api/v1/custody/verify -H "Authorization: Bearer <token>"
# {"ok":true,…,"verdict":"chain and anchors agree"}
```

`--local` signs in with a password: it needs a database account whose second factor is not
pending — the break-glass account ([SSO outage](sso-outage.md)) is the natural one, and the
drill is its test. Where that is impossible, sign in to the scratch server's web UI with the
second factor and create a short-lived API key there, then use `MAYA_URL` and `MAYA_API_KEY`.

Check, and write down:

- `verify-integrity` exits 0, and `<n>` equals the number of sealed pins production had when the
  backup was taken.
- `custody/verify` answers `chain and anchors agree`, with the anchor count you expect.
- `/readyz` is ready and names the lake backend.
- The break-glass account signed in.
- How long it took, from "start restore" to "verification green".

## 5. Record the result

MAYA has nowhere to record a drill: the scratch copy's own `integrity.verified` audit entry is
thrown away with the copy, and nothing in production learns the drill happened. Keep the
record outside MAYA, where the model risk function can see it, one row per drill:

| Date | Backup taken at | Dialect | Pins checked | Drift | Chain | Anchors | Duration | Performed by | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-19 | 20:37 UTC | SQLite | 5 of 5 | 0 | ok (50 events) | 1, agree | 7.7 s | development | Drill estate, not a deployment: 5 sealed pins (3 feature, 2 cascade), a training warrant, 1 webhook, 1 anchor. Steps 1–4 and 6 exactly as written; the webhook disarmed, its pending delivery settled "webhook is inactive; nothing was sent", no request made |
| 2026-09-19 | 20:37 UTC | PostgreSQL 17 | 5 of 5 | 0 | ok (50 events) | 1, agree | 3.1 s | development | The same estate on PostgreSQL: `pg_dump -Fc` / `pg_restore` into a new database (the first run of this runbook's PostgreSQL steps). Same outcome |

Duration is from "start restore" to "verification green", on a laptop, for a tiny estate: it
says the procedure works, not what the recovery time of a real one would be.

A failed drill is recorded as failed, with the cause, and repeated once the cause is fixed.

## 6. Tear down

Delete the scratch environment and, on PostgreSQL, drop `maya_drill`. It holds production data
and production's signing key.

## If the drill fails

- **Drift** — the backup's lake does not match its database: see [integrity drift](integrity-drift.md).
  A restore that pairs a database with an older `storage.root` looks exactly like this.
- **The chain or anchors disagree** — see [audit chain and custody](audit-chain-and-custody.md).
  An anchor file copied from a different moment than the database reports anchors *missing
  from the append-only file*.
- **Schema mismatch at start** — the backup was taken under another MAYA version: restore with
  that version, or rebuild per the [schema rebuild runbook](schema-rebuild.md).

## What this does not reach

- **No drill of a real deployment has been recorded.** The drills above ran on a small drill
  estate on SQLite and on PostgreSQL 17 (§5): the procedure is proven on both dialects, and the
  plan's M8 criterion *"the restore drill has been performed and its result recorded and
  visible"* is met for the procedure. A deployment's first drill, on its own backups, is still
  its operator's to perform and record.
- **Recovery time and recovery point have never been measured** at production size.
- **`verify-integrity` re-hashes sealed pins only** — not blobs, raw ingested data or keys. A
  backup that lost a model's specification PDF passes it.
- **Why step 3 is still not optional.** The CLI's `--local` mode no longer starts the webhook
  dispatcher or the scheduler (it runs job workers only), but the scratch server started in
  step 4 does both, and it is started on production's webhooks.
