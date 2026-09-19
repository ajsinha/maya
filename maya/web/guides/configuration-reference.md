# Configuration reference

Every setting MAYA reads lives in one file, `config/application.yaml`. This reference lists every key in that file: its shipped default, what it does, the environment variable its placeholder reads (where it has one), and how to override it. Keys are written in the dotted form MAYA uses internally: `db.postgresql.host` is `host` under `postgresql` under `db`.

!!! note "The file carries no secret"
    `config/application.yaml` is tracked in git, and a test fails the build if a secret is written into it. Secrets — the session key, the PostgreSQL password, the OIDC client secret — go in the environment or in the git-ignored overlay `config/application.local.yaml`.

## How settings are resolved

MAYA builds its configuration once at startup, in layers. A later layer wins over an earlier one, key by key.

| Layer | Where it comes from | Shown as source |
|---|---|---|
| 1. The file | `config/application.yaml`, or the file named by `MAYA_CONFIG_FILE` | `file` |
| 2. The local overlay | `<file>.local.yaml` beside it (`config/application.local.yaml`), when it exists | `file` |
| 3. The environment | an environment variable named by the **full dotted key**, for example `db.dialect` | `env` |
| 4. The command line | a `--key=value` argument, for example `--db.dialect=postgresql` | `commandline` |

The overlay is optional: a missing overlay changes nothing. It sets only the keys it names and leaves everything else alone, so it is the right place for a machine's secrets and local tweaks.

### Placeholders

Most values that differ between machines are written as placeholders:

- `${NAME}` — the value of `NAME`, looked up among the other keys, the environment and the `--key=value` flags;
- `${NAME:default}` — the same, with a default when `NAME` is not set anywhere;
- `${MAYA_PG_PASSWORD:}` — an empty default: the key is empty unless the variable is set.

A placeholder can refer to another key: `db.sqlite.path` is `${storage.root}/maya.db`, so moving `storage.root` moves the SQLite file with it.

Every value is a string until it is read. MAYA coerces it where it is used: `"false"` and `false` mean the same thing, and `port: "${MAYA_PORT:8600}"` becomes the integer 8600.

### Three ways to change one setting

```bash
# Change the port three ways
MAYA_PORT=9000 python run_maya_web.py          # the ${MAYA_PORT:8600} placeholder
python run_maya_web.py --server.port=9000      # a flag: highest precedence
# or put server.port: 9000 in config/application.local.yaml
```

The environment layer uses the dotted key itself as the variable name, which most shells cannot export directly. Use the `MAYA_*` variable a placeholder reads when there is one, or `env` for keys without a placeholder:

```bash
# Set a key that has no MAYA_* placeholder
env 'jobs.workers=4' python run_maya_web.py
```

### Another configuration file

```bash
# Start from a different file
python run_maya_web.py --config=/etc/maya/application.yaml
MAYA_CONFIG_FILE=/etc/maya/application.yaml python run_maya_web.py
```

`MAYA_CONFIG_FILE` wins over `--config`. The overlay rule follows the file: `/etc/maya/application.yaml` picks up `/etc/maya/application.local.yaml`.

!!! warning "The command line tool reads the file, not flags"
    `python -m maya.cli` takes `--config <path>` but does not accept `--key=value` overrides: its argument parser rejects them. For the CLI, use the `MAYA_*` environment variables or the overlay.

### Validated at startup

A setting that changes MAYA's behaviour materially is checked when MAYA starts, and a bad value stops it with the key named, rather than failing at first use:

| Check | Refusal |
|---|---|
| `app.environment` is `dev`, `uat` or `prod` | `ConfigurationError` naming the key and the allowed values |
| `db.dialect` is `sqlite` or `postgresql` | the same |
| `auth.mode` is `db`, `sso` or `hybrid` | the same |
| `app.environment: prod` with `db.dialect: sqlite` | refused: SQLite is a single-node, small-team backend |
| `app.secret_key` empty outside dev | refused: MAYA generates a key only in dev |
| sandbox tier below `sandbox.min_tier` outside dev | refused, naming the tier and why |
| bootstrap admin still on its default password outside dev | refused unless `app.allow_default_admin_password` is true |
| `auth.mode` is `sso`/`hybrid` with incomplete SSO settings | refused, naming the missing keys |
| `auth.mfa.enforce` not `auto`, `true` or `false` | refused |
| `assistant.provider` not `rules` or `claude` | refused |
| `custody.anchor.methods` names `rfc3161` without `custody.anchor.tsa_url` | refused |

### Seeing the effective configuration

An administrator can list every effective setting with its source (`file`, `env` or `commandline`). Any key whose name contains `password`, `secret` or `token` is shown as `••••••` when it has a value.

```python
# List the effective configuration (administrators only)
import maya.sdk as maya
my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
for row in my.admin.config():
    print(row["key"], row["value"], row["source"])
```

The same list is `GET /api/v1/system/config`.

!!! note "Read once, at startup"
    The configurator re-reads its files every five minutes, but the services read their settings when they are built at startup. Restart MAYA after changing a setting.

## app

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `app.name` | `MAYA` | — | The application name. Informational. |
| `app.environment` | `dev` | `MAYA_ENV` | `dev`, `uat` or `prod`. Outside `dev`: the default admin password refuses to start, an unset `app.secret_key` refuses to start, the sandbox minimum tier is enforced, MFA is enforced by role under `auth.mfa.enforce: auto`, session cookies are marked secure, self-approval is never honoured and a model cannot be approved on a draft PDF. In `prod`, SQLite refuses to start. API keys carry the environment in their text, so a `uat` key is refused in `prod`. |
| `app.secret_key` | empty | `MAYA_SECRET_KEY` | Signs the web session cookie and the paging cursors. In `dev`, when empty, MAYA generates one and keeps it in `<storage.root>/keys/session.secret`. Outside `dev` an empty key refuses to start. |
| `app.allow_default_admin_password` | `false` | — | Outside `dev`, MAYA refuses to start while the bootstrap `admin` account still has its default password. Setting this to `true` lifts that refusal. |

!!! warning "Keep app.secret_key secret and stable"
    Anyone who knows it can forge a web session. Changing it signs everyone out of the web UI and invalidates paging cursors that are in flight.

## server

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `server.host` | `127.0.0.1` | `MAYA_HOST` | The address the server listens on. The default accepts local connections only; use `0.0.0.0` behind a reverse proxy. |
| `server.port` | `8600` | `MAYA_PORT` | The listening port. |
| `server.workers` | `1` | — | Declared, but not read by this build: `run_maya_web.py` always starts one server process. |

## logging

| Key | Default | Meaning |
|---|---|---|
| `logging.level` | `INFO` | The root log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `logging.format` | `text` | `text` for human-readable lines, `json` for one JSON object per line. |
| `logging.file` | `${storage.root}/logs/maya.log` | A rotating log file (20 MB per file, five kept) in addition to the console. Empty means console only. |

## db

One key chooses the database; everything else under `db` belongs to one dialect or the other. SQLite and PostgreSQL are never mixed: a MAYA instance uses exactly one.

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `db.dialect` | `sqlite` | `MAYA_DB_DIALECT` | `sqlite` or `postgresql`. It decides the connection, the pool, the pragmas and which schema file creates the database: `maya/persistence/schema/sqlite.sql` or `maya/persistence/schema/postgresql.sql`. |
| `db.echo` | `false` | — | Log every SQL statement. For debugging only. |
| `db.sqlite.path` | `${storage.root}/maya.db` | — | The SQLite file. Its directory is created when missing. |
| `db.sqlite.busy_timeout_ms` | `30000` | — | How long a SQLite connection waits for a lock before failing. MAYA also opens SQLite with WAL journaling, foreign keys on and `synchronous=NORMAL`, and serializes its own writes. |
| `db.postgresql.host` | `localhost` | `MAYA_PG_HOST` | The PostgreSQL server. |
| `db.postgresql.port` | `5432` | `MAYA_PG_PORT` | Its port. |
| `db.postgresql.database` | `maya` | `MAYA_PG_DATABASE` | The database name. |
| `db.postgresql.user` | `maya` | `MAYA_PG_USER` | The role MAYA connects as. |
| `db.postgresql.password` | empty | `MAYA_PG_PASSWORD` | The password. Environment or overlay only. |
| `db.postgresql.pool_size` | `10` | — | Connections kept open in the pool. |
| `db.postgresql.max_overflow` | `10` | — | Extra connections allowed above the pool under load. |

MAYA connects to PostgreSQL through the `psycopg` driver (`postgresql+psycopg://`), with pre-ping on every checkout. Moving between dialects is covered in the operations guide: there are no migrations, only estate export and import.

## storage

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `storage.root` | `data` | `MAYA_HOME` | The directory that holds everything MAYA keeps outside the database: the blob store, the Delta lake, the `keys/` directory (signing key, secret-box key, generated session secret), logs, the default anchor file and, with SQLite, the database file. A relative path is relative to the working directory. |

!!! warning "Back up storage.root with the database"
    The `keys/` directory holds the Ed25519 signing key and the key that seals TOTP seeds and webhook secrets. A database restored without it cannot open those secrets, and signatures made afterwards come from a different key.

## lake

| Key | Default | Meaning |
|---|---|---|
| `lake.backend` | `auto` | The `maya_delta` backend: `native` (the `deltalake` package), `pure` (MAYA's pure-Python implementation of a declared subset of the Delta protocol) or `auto` (native when installed). |
| `lake.maintenance.interval_seconds` | `86400` | How often the scheduler compacts and vacuums every lake table. |
| `lake.maintenance.target_size_mb` | `128` | The file size compaction aims for. |
| `lake.maintenance.vacuum_retention_hours` | `168` | How long unreferenced files are kept before vacuum removes them, for time travel. |
| `lake.fragment.target_rows` | `512` | Content-defined chunking of pinned data: the target fragment size in rows. |
| `lake.fragment.min_rows` | `32` | The smallest fragment. |
| `lake.fragment.max_rows` | `8192` | The largest fragment. |

!!! tip "Fragment sizes and deduplication"
    Pins share fragments by content. The fragment parameters decide how finely data is cut, and therefore how much two nearby pins share. Change them only on a fresh estate: fragments already written keep their boundaries.

## auth

### Sign-in mode and sessions

| Key | Default | Meaning |
|---|---|---|
| `auth.mode` | `db` | `db`: MAYA passwords. `sso`: single sign-on for people; password login refused. `hybrid`: single sign-on for people, passwords kept for break-glass and service accounts. |
| `auth.session.idle_timeout_minutes` | `30` | A session unused this long ends. |
| `auth.session.absolute_timeout_hours` | `12` | A session ends this long after sign-in, however active. |
| `auth.session.token_ttl_minutes` | `15` | Declared, but not read by this build. Execution-warrant tokens have a fixed 15-minute life set in code. |
| `auth.password.min_length` | `12` | The minimum password length. A password must also use three of: lower case, upper case, digits, symbols. |
| `auth.lockout.attempts` | `5` | Failed attempts inside the window that lock an account. |
| `auth.lockout.window_minutes` | `15` | The window in which failures count. |
| `auth.lockout.duration_minutes` | `30` | How long a locked account stays locked. |
| `auth.api_keys.max_days` | `365` | The longest life an API key may be given. Keys default to 90 days. |

### Single sign-on (OIDC)

Used when `auth.mode` is `sso` or `hybrid` and `auth.sso.protocol` is `oidc`.

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `auth.sso.protocol` | `oidc` | `MAYA_SSO_PROTOCOL` | `oidc` or `saml2`. |
| `auth.sso.issuer` | empty | `MAYA_OIDC_ISSUER` | The issuer URL; discovery is read from it. Required. |
| `auth.sso.client_id` | `maya` | `MAYA_OIDC_CLIENT_ID` | MAYA's client id at the identity provider. Required. |
| `auth.sso.client_secret` | empty | `MAYA_OIDC_CLIENT_SECRET` | The client secret, when the provider issues one. Environment or overlay only. |
| `auth.sso.redirect_uri` | `http://127.0.0.1:8600/auth/sso/callback` | `MAYA_OIDC_REDIRECT_URI` | Where the provider returns the browser. Register exactly this URL. Required. |
| `auth.sso.scopes` | `openid profile email groups` | — | Scopes requested. |
| `auth.sso.username_claim` | `preferred_username` | — | The claim that becomes the MAYA username. |
| `auth.sso.email_claim` | `email` | — | The claim that becomes the email address. |
| `auth.sso.groups_claim` | `groups` | — | The claim holding the person's groups. |
| `auth.sso.jit_provision` | `true` | — | Create the MAYA account at first sign-in. When `false`, someone without an account is refused. |
| `auth.sso.on_missing_group` | `deny` | — | `deny`: a person none of whose groups maps to a role cannot sign in. |
| `auth.sso.group_role_map` | `maya-admins: [admin]` | — | Identity-provider group → list of MAYA roles, re-applied at every sign-in. |

```yaml
# config/application.local.yaml: OIDC with two mapped groups
auth:
  mode: hybrid
  sso:
    protocol: oidc
    issuer: "https://login.example.com/realms/bank"
    redirect_uri: "https://maya.example.com/auth/sso/callback"
    group_role_map:
      maya-admins: [admin]
      quant-desk: [model_designer, model_developer]
```

### Single sign-on (SAML 2.0)

Used when `auth.sso.protocol` is `saml2`. Needs the `python3-saml` and `xmlsec` packages; without them MAYA refuses to start. Every value marked required must be present, or MAYA refuses to start naming the missing keys.

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `auth.sso.saml.sp_entity_id` | empty | `MAYA_SAML_SP_ENTITY_ID` | MAYA's entity id. Required. |
| `auth.sso.saml.acs_url` | `http://127.0.0.1:8600/auth/sso/saml/acs` | `MAYA_SAML_ACS_URL` | MAYA's assertion consumer service. Required. |
| `auth.sso.saml.idp_entity_id` | empty | `MAYA_SAML_IDP_ENTITY_ID` | The identity provider's entity id. Required. |
| `auth.sso.saml.idp_sso_url` | empty | `MAYA_SAML_IDP_SSO_URL` | The provider's sign-on URL (HTTP-Redirect). Required. |
| `auth.sso.saml.idp_cert` | empty | `MAYA_SAML_IDP_CERT` | The provider's signing certificate, inline PEM. This or the file is required. |
| `auth.sso.saml.idp_cert_file` | empty | `MAYA_SAML_IDP_CERT_FILE` | The same certificate, read from a file; used when `idp_cert` is empty. |
| `auth.sso.saml.username_attribute` | empty | — | The attribute that becomes the username. Empty: the NameID. |
| `auth.sso.saml.groups_attribute` | `groups` | — | The attribute holding group names. |
| `auth.sso.saml.email_attribute` | `email` | — | The attribute holding the email address. |
| `auth.sso.saml.name_attribute` | `displayName` | — | The attribute holding the display name. |

The group mapping, JIT provisioning and `on_missing_group` keys above apply to SAML exactly as to OIDC.

### Security keys (WebAuthn)

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `auth.webauthn.rp_id` | `localhost` | `MAYA_WEBAUTHN_RP_ID` | The relying-party id: the site's domain, never an IP address. |
| `auth.webauthn.rp_name` | `MAYA` | — | The name the browser shows during registration. |
| `auth.webauthn.origins` | `http://localhost:8600` | `MAYA_WEBAUTHN_ORIGINS` | The exact `scheme://host:port` the browser shows, comma-separated when there are several. |

### Two-factor enforcement

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `auth.mfa.enforce` | `auto` | `MAYA_MFA_ENFORCE` | `auto`: users who enrolled are always challenged; outside dev, users holding a role in `required_for_roles` must enroll. `true`: the role requirement applies in every environment. `false`: no second factor is asked for. |
| `auth.mfa.required_for_roles` | `[admin, model_owner]` | — | The roles that require a second factor. |
| `auth.mfa.issuer_name` | `MAYA` | — | The issuer shown in authenticator apps. |

## sandbox

| Key | Default | Meaning |
|---|---|---|
| `sandbox.min_tier` | `strong` | `strong`, `moderate` or `minimal`. Outside dev, MAYA refuses to start when the host's verified sandbox tier is below it. In dev the tier is reported, not enforced. |

## workflow

| Key | Default | Meaning |
|---|---|---|
| `workflow.allow_self_approval` | `false` | Lets a person approve their own work and activate their own policy draft. Honoured only when `app.environment` is `dev`; ignored everywhere else. |

## typeset

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `typeset.require_true_build` | `false` | `MAYA_REQUIRE_TECTONIC` | When `true`, the `spec_true_build` check refuses to approve a model whose specification PDF is a watermarked draft render. Outside dev the check requires a true build regardless of this key. |

## jobs

| Key | Default | Meaning |
|---|---|---|
| `jobs.workers` | `2` | Worker threads claiming jobs from the database queue. |
| `jobs.max_attempts` | `3` | Attempts before a failing job is dead-lettered, with the failure kept. |

## observability

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `observability.otlp.endpoint` | empty | `MAYA_OTLP_ENDPOINT` | An OTLP/HTTP collector, for example `http://collector:4318/v1/traces`. Spans are exported only when this is set and the OpenTelemetry SDK is installed; trace ids propagate either way. |
| `observability.metrics.token_env` | empty | — | The **name** of an environment variable holding a bearer token for `/metrics`. Empty: `/metrics` is open. Named but unset: every scrape gets 401. |
| `observability.webhooks.max_attempts` | `8` | — | Delivery attempts before a webhook delivery is dead. |
| `observability.webhooks.timeout_seconds` | `5` | — | The timeout of one delivery attempt. |
| `observability.webhooks.allow_private` | `false` | — | Allows webhooks to plain-HTTP localhost and to private addresses. Honoured only in dev. |

## sources

Limits for `python` sources: a producer function run in the sandbox on each pull.

| Key | Default | Meaning |
|---|---|---|
| `sources.python.cpu_seconds` | `30` | CPU time allowed. |
| `sources.python.memory_mb` | `1024` | Memory allowed. |
| `sources.python.wall_seconds` | `60` | Wall-clock time before the child is killed. |
| `sources.python.max_output_mb` | `20` | The largest result accepted. |

## assistant

The recorded challenger writes a memo on every submission into review. It never approves, blocks or edits.

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `assistant.enabled` | `true` | — | Queue a challenge memo when an object enters review. |
| `assistant.provider` | `rules` | `MAYA_ASSISTANT_PROVIDER` | `rules`: deterministic findings, no network. `claude`: also asks Claude, sending definitions, the specification and the formula — never data rows — to Anthropic's API. |
| `assistant.claude.model` | `claude-opus-5` | — | The model asked when the provider is `claude`. |
| `assistant.claude.effort` | `high` | — | The effort level passed to the model. |
| `assistant.claude.api_key_env` | empty | — | The name of an environment variable holding the Anthropic key. Empty: the Anthropic SDK's own resolution (`ANTHROPIC_API_KEY`, or a saved login). |
| `assistant.claude.timeout_seconds` | `300` | — | The request timeout. |

## custody

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `custody.anchor.methods` | `signature,file,event` | — | How the audit chain head is anchored: any of `signature` (Ed25519), `file` (an append-only JSON-lines file), `event` (an `audit.anchored` event, visible to webhooks), `rfc3161` (a timestamp authority; sends the head hash to it). |
| `custody.anchor.file` | empty | `MAYA_ANCHOR_FILE` | The anchor file. Empty: `<storage.root>/anchors.jsonl`. Point it at write-once or off-host storage. |
| `custody.anchor.tsa_url` | empty | `MAYA_TSA_URL` | The RFC 3161 timestamp authority. Required when `methods` names `rfc3161`. |
| `custody.anchor.interval_seconds` | `3600` | — | How often the scheduler anchors the head. |

## workspaces

| Key | Default | Meaning |
|---|---|---|
| `workspaces.shadow.sample_rows` | `5000` | Rows replayed per dependent warrant in a shadow replay (the most recent, by index). Stated on the report. |
| `workspaces.shadow.materiality` | `0.0001` | An absolute output shift above this counts as material. |

## featureset

| Key | Default | Meaning |
|---|---|---|
| `featureset.pin.materialize` | `always` | Declared, but not read by this build. Materialization is recorded per namespace (`materialize_policy`, default `always`). |

## seams

MAYA resolves each optional dependency (a *seam*) once at startup: the preferred backend when it is installed, otherwise a named fallback whose cost the health page states. `auto` takes that choice; naming a backend pins it. Pinning a preferred backend that is not installed falls back and says so.

| Key | Default | Backends (preferred first) |
|---|---|---|
| `seams.json` | `auto` | `orjson`, `stdlib` |
| `seams.frames` | `auto` | `polars`, `pandas` |
| `seams.compress` | `auto` | `zstandard`, `zlib` |
| `seams.kdf` | `auto` | `argon2id`, `scrypt` |

Any seam can be pinned the same way with a `seams.<name>` key, although the shipped file lists only these four. The other seams are `pushdown` (`duckdb`, `maya`), `pg_driver` (`psycopg`, `pg8000`), `tzdb` (`system`, `tzdata`), `procstat` (`psutil`, `os`), `typeset` (`tectonic`, `draft`), `event_loop` (`uvloop`, `asyncio`) and `tracing` (`otel`, `ids`). `lake.backend` is the lake seam's pin. The `crypto` seam has no fallback: without the `cryptography` package, signing, sealing and certificates are refused rather than weakened.

```bash
# See which backend every seam resolved to
curl -s http://localhost:8600/api/v1/system/health -H "Authorization: Bearer $MAYA_API_KEY" \
  | jq '.seams[] | {seam, selected, preferred, reason}'
```

## Environment variables at a glance

| Variable | Sets |
|---|---|
| `MAYA_CONFIG_FILE` | the configuration file itself |
| `MAYA_ENV` | `app.environment` |
| `MAYA_SECRET_KEY` | `app.secret_key` |
| `MAYA_HOST`, `MAYA_PORT` | `server.host`, `server.port` |
| `MAYA_HOME` | `storage.root` |
| `MAYA_DB_DIALECT` | `db.dialect` |
| `MAYA_PG_HOST`, `MAYA_PG_PORT`, `MAYA_PG_DATABASE`, `MAYA_PG_USER`, `MAYA_PG_PASSWORD` | `db.postgresql.*` |
| `MAYA_SSO_PROTOCOL` | `auth.sso.protocol` |
| `MAYA_OIDC_ISSUER`, `MAYA_OIDC_CLIENT_ID`, `MAYA_OIDC_CLIENT_SECRET`, `MAYA_OIDC_REDIRECT_URI` | `auth.sso.*` |
| `MAYA_SAML_SP_ENTITY_ID`, `MAYA_SAML_ACS_URL`, `MAYA_SAML_IDP_ENTITY_ID`, `MAYA_SAML_IDP_SSO_URL`, `MAYA_SAML_IDP_CERT`, `MAYA_SAML_IDP_CERT_FILE` | `auth.sso.saml.*` |
| `MAYA_WEBAUTHN_RP_ID`, `MAYA_WEBAUTHN_ORIGINS` | `auth.webauthn.*` |
| `MAYA_MFA_ENFORCE` | `auth.mfa.enforce` |
| `MAYA_REQUIRE_TECTONIC` | `typeset.require_true_build` |
| `MAYA_OTLP_ENDPOINT` | `observability.otlp.endpoint` |
| `MAYA_ASSISTANT_PROVIDER` | `assistant.provider` |
| `MAYA_ANCHOR_FILE`, `MAYA_TSA_URL` | `custody.anchor.file`, `custody.anchor.tsa_url` |

The SDK and CLI read their own variables — `MAYA_URL`, `MAYA_API_KEY`, `MAYA_CONFIG`, `MAYA_DEBUG_AUTH`, and for `--local` `MAYA_USER` and `MAYA_PASSWORD` — described in the Python SDK and CLI reference.

## A production overlay

```yaml
# config/application.local.yaml on a production host (git-ignored)
app:
  environment: prod
  secret_key: "…48+ random characters…"
server:
  host: 0.0.0.0
db:
  dialect: postgresql
  postgresql:
    host: db.internal
    password: "…"
storage:
  root: /srv/maya
auth:
  mode: hybrid
custody:
  anchor:
    file: /mnt/worm/maya-anchors.jsonl
observability:
  metrics:
    token_env: MAYA_METRICS_TOKEN
```

!!! tip "Check before you start"
    Start once and read the banner: it prints the environment, the database and its schema file, the lake backend, the sandbox tier, the storage root, the job workers and every seam that is not on its preferred backend.
