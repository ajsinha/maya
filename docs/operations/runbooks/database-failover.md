# Database failover

For the administrator or `techops` engineer whose PostgreSQL has gone away, or is about to.

**Read this first: MAYA has no failover of its own.** It holds one engine against one URL
(ADR-013: SQLite by default, PostgreSQL by configuration, never mixed). There is no replica
awareness, no read/write split, no retry-on-another-host, and no leader election. Failover is
whatever your PostgreSQL deployment provides — a virtual IP, a connection proxy, a managed
service's promotion — and MAYA's part is to survive the gap, reconnect, and tell you honestly
whether anything was lost. What MAYA *does* give you is a short, verifiable list of things to
check on the other side, which is what this runbook is.

## Symptoms

- Every page and API call fails. `/healthz` still answers — it only proves the process is
  alive — while `/readyz` does not:

  ```bash
  curl -s http://127.0.0.1:8600/healthz
  # {"alive":true,"version":"0.3.0"}
  curl -s http://127.0.0.1:8600/readyz
  # database: connection refused …          (HTTP 503, "ready": false)
  ```

- `/admin/health` shows the database not ok, with the driver's own message in `detail`.
- The `MayaMetadataAvailabilityBurn` and `MayaDatabasePoolSaturated` alerts fire
  ([the rules file](../../../config/prometheus/maya-slo.rules.yml)).
- Jobs stop finishing. They are not lost: the queue *is* the database, so a job mid-flight
  fails and is retried, and a queued job simply waits.
- Log lines from `sqlalchemy` / `psycopg`: `connection refused`, `server closed the connection
  unexpectedly`, `terminating connection due to administrator command`, or — after a promotion
  — `cannot execute INSERT in a read-only transaction`.

A healthy answer, for comparison, is:

```json
{"ready":true,"database":"schema identity verified","lake":"native","seams":{ … }}
```

## Diagnosis

**Is it the database, or MAYA?**

```bash
curl -s "$MAYA_URL/readyz"                       # 503 with a database message: the database
curl -s "$MAYA_URL/metrics" | grep "^maya_db_pool"
# maya_db_pool_connections{state="in_use"} 0
# maya_db_pool_connections{state="available"} 1
# maya_db_pool_limit{kind="size"} 1
# maya_db_pool_limit{kind="max_overflow"} 0
```

`in_use` pinned at `size + max_overflow` is saturation, not an outage: something is holding
connections. `in_use` at zero with `/readyz` failing is an outage. (On SQLite the gauge reports
`size 1` and nothing else, because there is no pool: MAYA serialises writers behind its own
mutex.)

**Is the replica the one you think?** MAYA does not know. Ask PostgreSQL:

```bash
psql -d maya -c "SELECT pg_is_in_recovery(), inet_server_addr(), inet_server_port();"
# f = primary, t = still a standby (every write will fail read-only)
```

**Slow, not down?**

```bash
curl -s "$MAYA_URL/metrics" | grep -E "^maya_db_(statements|slow_queries)_total"
psql -d maya -c "SELECT state, count(*), max(now()-query_start) FROM pg_stat_activity
                 WHERE datname = 'maya' GROUP BY state;"
```

## Steps

1. **Let your PostgreSQL deployment fail over.** Promote the standby, move the virtual IP,
   reconfigure the proxy — whatever that deployment's procedure is. MAYA does not participate.
2. **Restart MAYA if the endpoint changed.** The URL is built at startup from `db.postgresql.*`,
   and nothing re-reads it. If failover is transparent (a VIP or a proxy keeps the same
   host:port), MAYA reconnects on its own and you can skip this — `pool_pre_ping` is on, so the
   first request after the gap discards the dead connection rather than failing on it. If the
   endpoint moved:

   ```bash
   python run_maya_web.py --db.postgresql.host=<new-host> --db.postgresql.port=5432
   # or set MAYA_PG_HOST / MAYA_PG_PORT and restart under your service manager
   ```

3. **Verify the schema identity before letting anyone in.** This is the step that catches a
   failover to the *wrong* database — an old standby, a test instance, a restore from the wrong
   night:

   ```bash
   curl -s "$MAYA_URL/readyz"
   # {"ready":true,"database":"schema identity verified", …}
   ```

   A mismatch refuses startup and names the export → `init-db` → import path; see the
   [schema rebuild runbook](schema-rebuild.md). MAYA has no migrations (ADR-012), so a schema
   hash that differs means a different MAYA version, not a version to catch up.

4. **Check what the gap cost you.** Three things, in this order:

   ```bash
   # The audit chain: the one record whose breakage is an incident
   python -m maya.cli admin verify-integrity
   # <n> pin(s) checked; drift: 0; audit chain ok: True

   # Jobs the outage interrupted: requeued by the reaper at startup, or left running
   curl -s "$MAYA_URL/api/v1/jobs?all=true" -H "Authorization: Bearer $MAYA_API_KEY" \
     | python -c "import json,sys; [print(j['state'], j['job_type'], j['error']) for j in json.load(sys.stdin)['data'] if j['state'] in ('running','dead_letter','failed')]"

   # Pins whose saga did not close
   curl -s "$MAYA_URL/metrics" | grep 'maya_pins{.*materializing'
   ```

   A pin interrupted between the Delta write and the metadata commit leaves an orphaned
   partition and never becomes visible — that is the saga working as designed (§15.3). Clean up
   with [orphaned pin partitions](orphaned-pin-partitions.md).

5. **If the failover lost transactions**, the audit chain is where you will see it, because it
   is hash-linked: a gap shows as a broken link, not as a missing row you have to notice. Treat
   a break as an incident — [audit chain and custody](audit-chain-and-custody.md) — and compare
   against the custody anchors, which live outside the database precisely for this.

6. **Restart the worker processes too**, if you run any (`python run_maya_web.py --worker`).
   They hold their own engine against the same URL and are subject to all of the above.

## If there is no standby to fail over to

Then this is a restore, not a failover:

1. Follow the [restore drill](restore-drill.md) — the same procedure, against production.
2. **Restore the database and `storage.root` from the same moment**, database first. A database
   newer than the lake means pins whose bytes are missing; that is the one direction that
   loses data. The opposite — a lake newer than the database — only leaves orphans.
3. `admin verify-integrity` afterwards, and record the result with
   `python -m maya.cli admin record-drill --failed --notes="…"` if it found anything, so the
   estate remembers that recovery was exercised for real.

## A note on SQLite

There is nothing to fail over to. SQLite is one file under `storage.root`, and MAYA says so on
every page. Several web processes over SQLite are refused outright:

```text
maya.core.errors.ConfigurationError: server.workers is 2, but the database is SQLite, which
admits one writing process. Use PostgreSQL (db.dialect: postgresql) for several web processes,
or set server.workers: 1.
```

If a SQLite deployment needs availability, the answer is the
[move to PostgreSQL](move-between-sqlite-and-postgresql.md), not a trick here.

## Verification

- `/readyz` is `{"ready":true,"database":"schema identity verified", …}`.
- `python -m maya.cli admin verify-integrity` exits 0.
- `maya_db_pool_connections{state="in_use"}` moves under load and is not pinned at the limit.
- A write works end to end: sign in, edit a draft, save it. A read-only standby that was
  promoted incompletely passes every read check and fails exactly here.
- No pin is left `materializing`, and no job is stuck `running` with no worker.

**Commands run while this runbook was written.** `/healthz`, `/readyz`, the `maya_db_pool`
gauges, `maya_pins` by state, `admin verify-integrity`, and the several-web-processes refusal
(whose text above is quoted from the actual failure) — all against a throwaway `MAYA_HOME` on
SQLite. **Every `psql` command here is not exercised**: there was no PostgreSQL server
available, so `pg_is_in_recovery`, `pg_stat_activity`, the promotion itself and the
reconnect-after-VIP-move behaviour are written from the code and PostgreSQL's documentation, not
from a run. The same is true of the read-only-transaction symptom.

## What this does not reach

- **MAYA has no failover, retry-to-another-host, or replica awareness.** §20's 99.9% availability
  objective is an objective, not a mechanism. Everything that makes it achievable is outside
  MAYA.
- **No read replicas.** §24.3 lists "add read replicas for catalog queries" as a scaling lever;
  MAYA sends every query to one engine. Pointing it at a replica makes the whole instance
  read-only, which it will not tolerate.
- **RPO and RTO have never been measured.** §20 states 5 minutes and 1 hour. MAYA does not
  configure WAL archiving and nothing measures either figure; the
  [restore drill](restore-drill.md) records a duration for a tiny estate only.
- **No connection retry policy is configurable.** `pool_pre_ping` and the pool size are all
  there is; there is no configurable retry count, backoff or statement timeout.
- **A partial failover is not detected.** MAYA verifies the schema *hash*, not which host
  answered. Failing over to a stale standby with the same schema passes every check here; only
  the audit chain and the custody anchors will show it.
