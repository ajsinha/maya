# Operations and administration guide

This guide is for whoever installs, runs and looks after a MAYA instance: starting it, choosing and changing the database, backing it up, keeping the lake healthy, proving its records are intact, and watching it run. Commands assume the repository root as the working directory.

## Install

MAYA needs Python 3.13 or later.

```bash
# Create an environment and install MAYA's dependencies
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` holds what a deployment needs. Several packages are *preferred backends* behind dependency seams: without them MAYA still runs, on a named fallback whose cost it reports. A few are capabilities that are refused, never substituted:

| Package | Without it |
|---|---|
| `cryptography` | Signing, sealing, certificates, bundles and TOTP enrollment are refused. |
| `python3-saml`, `xmlsec` | `auth.sso.protocol: saml2` refuses to start. |
| `webauthn` | Security keys are unavailable. |
| `openpyxl` | Spreadsheet import is refused. |
| `anthropic` | `assistant.provider: claude` is refused. |
| `deltalake` | The lake uses MAYA's pure-Python backend. |
| `opentelemetry-sdk` and exporter | Trace ids still propagate; spans are not exported. |

Two things live outside Python:

- **Tectonic**, for true LaTeX builds of model specifications. Put the `tectonic` binary on `PATH`. Without it, specification PDFs are rendered by MAYA's structural draft renderer, watermarked `DRAFT RENDER — NOT EVIDENCE`, and refused wherever a PDF is evidence. Tectonic downloads its TeX bundle on first use, so an air-gapped server must be given a cached bundle.
- **bubblewrap, seccomp and cgroup v2**, on Linux, for the `strong` sandbox tier. See the security guide.

## Run

```bash
# The one supported way to start MAYA
python run_maya_web.py
python run_maya_web.py --config=/etc/maya/application.yaml
python run_maya_web.py --db.dialect=postgresql --server.port=9000
```

`run_maya_web.py` is the only supported entry point. It sets the `spawn` multiprocessing start method, loads and validates the configuration, configures logging, builds the platform, prints a banner and serves the web UI and the API from one process on `server.host:server.port` (default `127.0.0.1:8600`). The API explorer is at `/api/v1/docs`.

At startup MAYA, in order:

1. resolves every dependency seam, honouring `seams.*` and `lake.backend`;
2. opens the database for `db.dialect` — creating the schema from its schema file when the database is empty — and verifies the schema's identity;
3. rebuilds the search index if it is empty but the catalog is not;
4. seeds the built-in roles, the default workflow policies and, on a new database, the bootstrap `admin` account;
5. runs the startup refusals: SSO settings, the sandbox tier, the default admin password;
6. requeues jobs left `running` by a previous process;
7. starts the job workers, the webhook dispatcher and the scheduler.

The banner reports the environment, the database and its schema file, the lake backend, the sandbox tier, the storage root, the number of job workers, and every seam running on a fallback. It warns while the bootstrap admin still has its default password.

`SIGINT` and `SIGTERM` shut MAYA down cleanly: job workers drain, the webhook dispatcher and scheduler stop, and the database pool closes.

!!! tip "Behind a reverse proxy"
    MAYA serves plain HTTP and honours forwarded headers from its proxy. Terminate TLS at the proxy, set `server.host: 0.0.0.0` (or the proxy-facing address), and set `auth.webauthn.origins` and the SSO redirect and ACS URLs to the public `https://` addresses.

## Choosing the database

MAYA runs on SQLite by default and on PostgreSQL by configuration. One key decides which, and a MAYA instance uses exactly one: they are never mixed.

| | SQLite | PostgreSQL |
|---|---|---|
| Select with | `db.dialect: sqlite` (default) | `db.dialect: postgresql` |
| Schema file | `maya/persistence/schema/sqlite.sql` | `maya/persistence/schema/postgresql.sql` |
| Suited to | a laptop, a single node, a small team | production |
| Writers | one at a time; MAYA queues its own writes | concurrent; jobs claimed with `SELECT … FOR UPDATE SKIP LOCKED` |
| In `prod` | refused at startup | required |

Both schema files are generated from the same model definitions. The schema's hash is stamped into the database when it is created, and MAYA refuses to start against a database whose stamped hash differs from the code's.

### Starting on PostgreSQL

```bash
# A new instance on PostgreSQL
export MAYA_DB_DIALECT=postgresql MAYA_PG_HOST=db.internal MAYA_PG_USER=maya MAYA_PG_PASSWORD='…'
python -m maya.cli admin init-db
python run_maya_web.py
```

`init-db` creates the schema for the configured dialect and refuses when one already exists; `--force` drops and recreates it. The database and role must already exist — MAYA creates tables, not databases.

## Upgrades and moving between databases

There are no migrations. Upgrading MAYA to a version whose schema changed, and moving from SQLite to PostgreSQL, are the same three steps: export the estate, create a fresh schema, import the estate.

The **estate** is every table of the database, dialect-neutral, as JSON lines per table in dependency order inside a zip (format `maya-estate-v1`), with a manifest recording each table's row count and SHA-256. The import verifies every table's hash, loads everything in one transaction, then verifies the audit chain; on PostgreSQL it also advances every auto-numbered key past the loaded rows.

!!! warning "Export with the code that matches the database"
    `export-estate` opens the database with the running code, and a schema mismatch refuses to open. Export **before** installing the new version (or with the old version's checkout), then upgrade, then create and import.

### Moving from SQLite to PostgreSQL

```bash
# 1. Stop MAYA, then export from the SQLite database
python -m maya.cli admin export-estate --out estate.mayabundle

# 2. Create the PostgreSQL schema
export MAYA_DB_DIALECT=postgresql MAYA_PG_HOST=db.internal MAYA_PG_PASSWORD='…'
python -m maya.cli admin init-db --force

# 3. Import, then start on PostgreSQL
python -m maya.cli admin import-estate --in estate.mayabundle
python run_maya_web.py
```

Make the dialect permanent in `config/application.local.yaml` (or keep the environment variables in the service definition). Keep `storage.root` the same: the lake, the blobs and the keys stay where they are; only the database moved.

### Upgrading MAYA

```bash
# With the current version still installed
python -m maya.cli admin export-estate --out estate-before-upgrade.mayabundle
# install the new version, then:
python -m maya.cli admin init-db --force
python -m maya.cli admin import-estate --in estate-before-upgrade.mayabundle
python run_maya_web.py
# then, from another shell:
python -m maya.cli admin verify-integrity
```

!!! warning "Import into an empty schema, and do not start MAYA in between"
    Starting MAYA on an empty database seeds the built-in roles, policies and the bootstrap admin, and the import would then collide with those rows. Run `init-db --force` and `import-estate` back to back.

When MAYA refuses to start with a schema mismatch, its message prints the same three commands.

## Backups

A MAYA instance is two things, and a backup needs both:

| Part | Holds |
|---|---|
| The database | the catalog, versions, workflow, warrants, grants, users, jobs, events and the audit log |
| `storage.root` | the Delta lake (ingested and pinned data), the blob store (artifacts, PDFs, bundles, estates), `keys/` (the signing key, the sealing key, the dev session secret), logs, the default anchor file, and with SQLite the database file |

!!! warning "The keys directory is part of the backup"
    Without `keys/secretbox.key`, sealed secrets — TOTP enrollments and webhook signing secrets — cannot be opened. Without `keys/signing.pem`, signatures made after a restore come from a new key. Back it up, and restrict who can read the backup.

Take the two together, with MAYA stopped or quiet, so the database never points at data the storage copy lacks. Standard tools do the work:

- **SQLite** — the database file lives under `storage.root`; copy the whole directory while MAYA is stopped, or use `sqlite3 maya.db ".backup …"` for the database while it runs, then copy the rest.
- **PostgreSQL** — `pg_dump` for the database, and a copy of `storage.root`.

The estate export (`GET /api/v1/system/estate`, administrators, or `admin export-estate`) is a dialect-neutral logical copy of the database, hash-checked on import. It does not include `storage.root`.

After a restore, run integrity verification: it proves every sealed pin still re-hashes to its recorded hash and the audit chain is intact.

## The lake and storage

Pinned and ingested data live in `maya_delta` tables under `storage.root`. `lake.backend` selects the native `deltalake` backend or MAYA's pure-Python one (`auto`: native when installed).

### Maintenance

The scheduler compacts and vacuums every lake table every `lake.maintenance.interval_seconds` (daily). Compaction rewrites small files toward `lake.maintenance.target_size_mb` (128 MB); vacuum deletes files no longer referenced once they are older than `lake.maintenance.vacuum_retention_hours` (168). Maintenance is safe for sealed pins: a pin is read by fragment value and row number, never by file.

```python
# Run lake maintenance now (administrators and techops)
import maya.sdk as maya
my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
out = my.admin.lake_maintain()
print(out["filesRemoved"], out["filesAdded"], out["vacuumed"])
```

The same is `POST /api/v1/system/lake/maintain`. Each run is audited as `lake.maintained`, with totals per run. A retention under 168 hours is allowed but shortens how far back a table can be time-travelled.

### The storage report

`GET /api/v1/system/storage` (`my.admin.storage()`) reports what content addressing saved: sealed pins, fragments, logical and stored bytes, the saved ratio, and **orphan fragments** — fragments no sealed pin references, left by failed pins. Orphans are reported, never deleted automatically.

## Integrity and custody

### Integrity verification

Integrity verification re-reads every sealed feature and feature set pin, recomputes its content hash from its fragments, and walks the audit chain.

```bash
# Verify every sealed pin and the audit chain
python -m maya.cli admin verify-integrity
# 412 pin(s) checked; drift: 0; audit chain ok: True
```

The command exits 1 on any drift or a broken chain, so it can gate a deployment script. It is also `POST /api/v1/system/integrity` (administrators and techops). Each run is audited as `integrity.verified` — which is also an event — and any drift notifies every administrator.

### Audit chain and anchors

The audit log is hash-chained and append-only (a database trigger refuses updates and deletes). `GET /api/v1/audit/verify` walks the chain and reports the first broken link.

Anchors pin the chain head outside the database so a consistent rewrite of history is still caught. Every `custody.anchor.interval_seconds` (hourly), with the methods in `custody.anchor.methods`:

| Method | What is written |
|---|---|
| `signature` | an Ed25519 signature over the head's sequence number, hash and time |
| `file` | a JSON line appended to `custody.anchor.file` (default `<storage.root>/anchors.jsonl`) |
| `event` | an `audit.anchored` event, delivered to webhook subscribers |
| `rfc3161` | a timestamp token from `custody.anchor.tsa_url` (off by default) |

MAYA refuses to anchor a chain that does not verify. Administrators and techops can anchor on demand (`POST /api/v1/custody/anchor`), list anchors (`GET /api/v1/custody/anchors`) and verify them (`GET /api/v1/custody/verify`): each anchor must still match the live chain at its sequence number, its signature must verify, it must still be in the anchor file, and a timestamp token must carry its imprint. A disagreement is reported as `TAMPERING`.

## Health and readiness

| Endpoint | Authentication | Answers |
|---|---|---|
| `GET /healthz` | none | `{"alive": true, "version": …}` while the process serves |
| `GET /readyz` | none | 200 when the schema identity verifies and the lake root exists; 503 otherwise |
| `GET /api/v1/system/health` | any signed-in user | the full picture below |

The health document reports: version, build and environment; the database dialect, whether its schema identity verifies, its schema hash and schema file; the lake backend and root; the sandbox tier and why; the typesetting backend; jobs queued, running and dead-lettered, and the worker count; every seam's selected and preferred backend, and a `degraded` list with each fallback's cost (SQLite is listed there too); process statistics; whether the default admin password is still active; whether spans are exported; the webhook backlog; and the audit chain's verification.

## Metrics, tracing and logs

### Metrics

`/metrics` serves Prometheus text format. To protect it, set `observability.metrics.token_env` to the **name** of an environment variable that holds a token; scrapes must then send `Authorization: Bearer <token>`. If the named variable is unset, every scrape gets 401.

| Metric | Type | Labels |
|---|---|---|
| `maya_http_requests_total` | counter | `method`, `route` (the route template), `status` |
| `maya_http_request_duration_seconds` | histogram | `method`, `route` |
| `maya_job_runs_total`, `maya_job_duration_seconds` | counter, histogram | job type and outcome |
| `maya_pins_sealed_total`, `maya_pin_new_bytes_total` | counters | pin kind |
| `maya_authz_denials_total` | counter | action |
| `maya_audit_events_total`, `maya_events_total` | counters | — / event type |
| `maya_webhook_deliveries_total` | counter | `outcome` |
| `maya_jobs` | gauge, read at scrape time | `state`: queued, running, failed, dead_letter |
| `maya_sessions_active` | gauge, read at scrape time | — |
| `maya_webhook_backlog` | gauge, read at scrape time | `state`: pending, dead |
| `maya_build_info`, `maya_sandbox_tier`, `maya_seam_backend` | info gauges | version, build and dialect; tier; seam and backend |

### Tracing

Every request carries a W3C trace context: taken from the caller's `traceparent`, or created. The trace id is returned in `traceparent` and `X-Request-Id`, written into log lines, audit entries, jobs and events, and forwarded by the SDK, so a page, the API call behind it and the jobs it queued share one trace. With `observability.otlp.endpoint` set and the OpenTelemetry SDK installed, spans are exported over OTLP/HTTP; otherwise the health page says they are not.

### Logs

Logs go to the console and to `logging.file` (rotating at 20 MB, five files kept), at `logging.level`, as text or — with `logging.format: json` — one JSON object per line.

## Jobs

Slow work runs in a queue held in the database, claimed by `jobs.workers` worker threads.

| Job type | Started by |
|---|---|
| `feature.pin`, `featureset.pin` | pinning |
| `model.validate_artifact` | uploading a model artifact |
| `workspace.shadow_replay` | a workspace's shadow replay |
| `assistant.challenge` | an object entering review |
| `integrity.verify` | an integrity run queued as a job |

A deliberate refusal inside a job (a failed quality check, a contract mismatch) ends it `failed` without retry. An unexpected error requeues it with exponential backoff until `jobs.max_attempts` is spent, then dead-letters it with the traceback kept. Administrators and techops requeue failed and dead-lettered jobs with `POST /api/v1/jobs/{id}/retry`. Anyone who can see a job can cancel it: at once when queued, between stages when running. Jobs left `running` by a crashed process are requeued at the next startup.

## The scheduler

A scheduler thread in each MAYA process checks once a minute for due tasks. Each task is idempotent, so a restart, or a second process running the same sweep, sends nothing twice.

| Task | Interval | What it does |
|---|---|---|
| `workflow.escalate_overdue` | hourly | Escalates items past their policy's `sla_days` to the namespace owner (or the administrators), once per item; audited as `workflow.escalated`. |
| `execution.expiry_notices` | hourly | Notifies an execution warrant's owner once, 30 days before it expires. |
| `lake.maintenance` | `lake.maintenance.interval_seconds` (daily) | Compacts and vacuums every lake table. |
| `custody.anchor` | `custody.anchor.interval_seconds` (hourly) | Anchors the audit chain head. |

A failing task is logged and does not stop the others.

## Events and webhooks

Some audit entries are also **events**, written in the same transaction, so an event never describes something that did not commit. Workflow transitions become `<object_type>.<state reached>` — `feature_version.approved`, `model_version.deprecated`. The other types:

| Area | Event types |
|---|---|
| Pins and data | `pin.sealed`, `pin.failed`, `pin.retired`, `featureset.cascade_rolled_back`, `feature.ingested`, `feature.pulled` |
| Warrants | `warrant.created`, `warrant.parameters_uploaded`, `warrant.sealed`, `warrant.revoked`, `warrant.exec_created`, `warrant.exec_sealed`, `warrant.suspended`, `warrant.reinstated`, `warrant.exec_revoked`, `warrant.limit_exceeded`, `bundle.exported` |
| Access and identity | `access.granted`, `access.revoked`, `auth.lockout`, `auth.mfa_reset` |
| Change and governance | `workspace.submitted`, `workspace.merged`, `policy.activated`, `workflow.break_glass` |
| Operations | `job.dead_letter`, `integrity.verified`, `audit.anchored` |

Events are numbered by an increasing sequence. Administrators and techops read them three ways: `GET /api/v1/events?after=<seq>`, the server-sent stream `GET /api/v1/events/stream?after=<seq>`, and webhooks.

### Webhooks

```python
# Subscribe a receiver to warrant events and approvals
hook = my.events.create_webhook("risk-bus", "https://hooks.example.com/maya",
                                event_types=["warrant.*", "model_version.approved"])
print(hook["secret"])          # whsec_…, shown once
my.events.ping(hook["id"])     # a maya.ping event, delivered now
```

An empty `event_types` subscribes to everything; a trailing `*` is a prefix. Each delivery is a JSON POST with `X-Maya-Event`, `X-Maya-Delivery` (use it as an idempotency key: delivery is at-least-once), `X-Maya-Timestamp` and `X-Maya-Signature: sha256=<HMAC-SHA256 of "<timestamp>.<body>">`.

A 2xx settles a delivery. Anything else is retried with exponential backoff and jitter, capped at an hour, up to `observability.webhooks.max_attempts` (8); then the delivery is dead, with its last status and error kept. Each attempt times out after `observability.webhooks.timeout_seconds` (5). Deleting a webhook deactivates it and drops its pending deliveries. URL rules — HTTPS, no private or local addresses, re-checked at every delivery — are in the security guide.

## Search index

Catalog search uses MAYA's own inverted index, on both databases, maintained as objects are written. If it is ever out of step, an administrator rebuilds it from the catalog:

```bash
# Rebuild the search index (administrators)
curl -s -X POST https://maya.example.com/api/v1/search/reindex -H "Authorization: Bearer $MAYA_API_KEY"
```

MAYA also rebuilds it at startup when it is empty but the catalog is not.

## Administration tasks

| Task | SDK | Who |
|---|---|---|
| Create a user | `my.admin.create_user("val.jones", password="…", roles=["feature_designer"])` | administrators |
| Change roles | `my.admin.set_roles("val.jones", ["feature_manager"])` | administrators |
| Suspend an account | `my.admin.update_user("val.jones", status="disabled")` | administrators |
| Reset a password or a second factor | `my.admin.reset_password(...)`, `my.admin.reset_mfa(...)` | administrators |
| See and end sessions | `my.auth.sessions()`, `my.auth.end_session(id)` | administrators |
| Create a namespace | `my.namespaces.create("credit", preset="regulated", production=True)` | holders of `C` on namespaces |
| Named SQL connections | `my.sources.create_connection("warehouse", url, password_env="WH_PASSWORD")` | administrators |
| Effective configuration | `my.admin.config()` | administrators |
| Audit explorer | `my.admin.audit(action="licence.refused")` | administrators and techops |

Any status other than `active` stops an account from signing in and from using its API keys.

!!! tip "A weekly routine"
    Check the health page's `degraded` list and dead-letter count, run integrity verification, verify custody anchors, review the break-glass report and the aging list, and confirm backups include `storage.root/keys`.
