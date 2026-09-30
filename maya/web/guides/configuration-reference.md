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


The structured configuration files beside `application.yaml` — the model profiles (`llm.profiles_file`), the tiering questionnaire (`governance.tiering_questionnaire`) and the shipped workflow policies — are YAML read through the same configurator, so the same placeholders work in them: `base_url: "${LOCAL_LLM_URL:http://localhost:11434}"` in a profile resolves from the environment, with the same precedence as any setting. Quote a placeholder whose value could contain YAML syntax (a colon, a leading `[`).

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

!!! note "The command line tool takes the same overrides"
    `python -m maya.cli` takes `--config <path>` and lets `--section.key=value` settings through to the configuration, as the launcher does: `python -m maya.cli admin init-db --force --db.dialect=postgresql`. Only the commands that read the configuration themselves use them — the `admin` database commands and anything run with `--local`. A command that talks to a server is governed by that server's settings, not by flags on your command line. Any other unknown flag is still a usage error.

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
| `custody.anchor.tsa_ca_file` set, but the file does not exist or `openssl` is not installed | refused |

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
| `server.workers` | `1` | `MAYA_WEB_WORKERS` | Web processes. Above 1 — PostgreSQL only; with SQLite, which admits one writing process, MAYA refuses to start — this many web processes serve the one port (on Linux each on its own `SO_REUSEPORT` socket, so connections spread evenly); the launching process alone keeps the job workers, webhooks and scheduler (jobs submitted from any process are rows its workers poll every second). One Python process serves roughly 40 page requests a second; size this to cores and load. Prometheus metrics are per process. |

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
| `lake.root` | empty | Where the lake lives. Empty: `<storage.root>/lake`. A relative path is resolved against the project root, not the working directory, so the same configuration means the same lake whichever directory a script starts in. |
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
| `auth.session.principal_cache_seconds` | `2` | How long a signed-in session's principal is reused, since one page makes several internal calls. `0` turns it off. A sign-out, revocation or access change made in another web process reaches the session at most this many seconds late; in the same process it applies at once. Sessions still owing a second factor are never reused. |
| `auth.session.concurrent_sessions` | `3` | Live sessions one person may hold; a further sign-in ends their oldest. `0`: no cap. |
| `auth.password.min_length` | `8` | The minimum password length (at least 4). |
| `auth.password.force_change` | `false` | Make a person change a password an administrator set — the bootstrap admin's, a new account's, a reset — at their next sign-in. Off by default: with single sign-on it is rarely wanted. |
| `auth.password.require_classes` | `2` | How many of lower case, upper case, digits and symbols a password must use (1–4). |
| `auth.password.history` | `5` | How many previous passwords may not be chosen again. `0`: no history. |
| `auth.password.max_age_days` | `90` | A password older than this must be changed before its owner can sign in. `0`: never. |
| `auth.password.reset_token_minutes` | `60` | How long a reset token is valid. It is single use whatever its age. |
| `auth.lockout.attempts` | `5` | Failed attempts inside the window that lock an account. |
| `auth.lockout.window_minutes` | `15` | The window in which failures count. |
| `auth.lockout.duration_minutes` | `30` | How long a locked account stays locked. |
| `auth.api_keys.max_days` | `365` | The longest life an API key may be given. Keys default to 90 days. |
| `auth.api_keys.rate_per_minute` | `0` | A key's own request budget a minute when it declares none. `0`: the process limit of `api.limits` only. |
| `auth.api_keys.rotation_overlap_days` | `7` | How long a rotated key keeps working beside its successor. |
| `auth.api_keys.unused_days` | `90` | A key unused this long is reported for revocation. |
| `auth.api_keys.remind_days_before_expiry` | `14` | How long before expiry a key is reported for rotation. |
| `auth.client_credentials.token_minutes` | `60` | How long an access token from the client-credentials grant lives. |

**Break-glass.** §13.3 requires a way in when the identity provider is down. It is a named
account, not a configuration change made at the worst possible moment: these accounts may
sign in with a password even under `auth.mode: sso`, they are ordinary database accounts
holding the administrator role, a second factor applies to them as to anyone, and every such
sign-in is audited at warning level and notified to every administrator. The SSO outage
runbook (`docs/runbooks/sso-outage.md`) is the procedure.

| Key | Default | Meaning |
|---|---|---|
| `auth.break_glass.users` | empty | The accounts allowed that door, comma separated. Empty: nobody, and an IdP outage locks everyone out. |
| `auth.break_glass.session_minutes` | `60` | How long a break-glass session lasts, whatever the ordinary session timeouts say. |

### Single sign-on (OIDC)

Used when `auth.mode` is `sso` or `hybrid` and `auth.sso.protocol` is `oidc`.

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `auth.sso.protocol` | `oidc` | `MAYA_SSO_PROTOCOL` | `oidc` or `saml2`. |
| `auth.sso.issuer` | empty | `MAYA_OIDC_ISSUER` | The issuer URL; discovery is read from it. Required. |
| `auth.sso.client_id` | `maya` | `MAYA_OIDC_CLIENT_ID` | MAYA's client id at the identity provider. Required. |
| `auth.sso.client_secret` | empty | `MAYA_OIDC_CLIENT_SECRET` | The client secret, when the provider issues one. Environment or overlay only. |
| `auth.sso.redirect_uri` | `http://127.0.0.1:8600/auth/sso/callback` | `MAYA_OIDC_REDIRECT_URI` | Where the provider returns the browser. Register exactly this URL. Required. |
| `auth.sso.post_logout_redirect_uri` | empty | `MAYA_OIDC_POST_LOGOUT_URI` | Set, and registered with the provider, signing out of MAYA also sends the browser to the provider's end-session endpoint, which ends its session and returns here. Empty: signing out ends the MAYA session only. The provider's back-channel logout URL for MAYA is `POST /api/v1/auth/sso/oidc/backchannel-logout`, which needs no setting (see the security guide). |
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
| `auth.sso.saml.idp_slo_url` | empty | `MAYA_SAML_IDP_SLO_URL` | The IdP's single logout endpoint. Set, it turns on single logout both ways (see the security guide). |
| `auth.sso.saml.sls_url` | `http://127.0.0.1:8600/auth/sso/saml/sls` | `MAYA_SAML_SLS_URL` | MAYA's single logout service, as the IdP must call it. Required when `idp_slo_url` is set. |
| `auth.sso.saml.sign_requests` | `false` | `MAYA_SAML_SIGN_REQUESTS` | Sign AuthnRequests and logout messages (RSA-SHA256) with MAYA's key pair; needs `sp_cert` and `sp_key`, or startup is refused. |
| `auth.sso.saml.sp_cert` / `sp_cert_file` | empty | `MAYA_SAML_SP_CERT`, `MAYA_SAML_SP_CERT_FILE` | MAYA's certificate (PEM), inline or as a file. Published in the SP metadata. |
| `auth.sso.saml.sp_key` / `sp_key_file` | empty | `MAYA_SAML_SP_KEY`, `MAYA_SAML_SP_KEY_FILE` | MAYA's private key (PEM), from the environment or a file — never written into the configuration file. |
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

## api.limits

What one caller may ask for. Every one of these is counted **per web process**, so
`server.workers: 8` multiplies each of them by eight — a limit meant to protect one process's
memory and event loop, not the estate's.

| Key | Default | Meaning |
|---|---|---|
| `api.limits.max_body_bytes` | `268435456` (256 MB) | Largest request body accepted, refused by its `Content-Length` or as it streams in. `0` turns it off. |
| `api.limits.requests_per_minute` | `6000` | Requests a caller may make in a minute before MAYA answers `429` with `Retry-After`. The caller is the API key id, else the session, else the peer. `0` turns it off. |
| `api.limits.burst` | `1200` | Requests a caller may make back to back before the per-minute rate applies. |
| `api.limits.max_concurrent` | `128` | Requests in flight in one web process before it answers `503` rather than queueing. Shedding is honest; a queue that never drains is not. `0` turns it off. |
| `api.limits.timeout_seconds` | `120` | How long a request may run before it is answered `504`. Work already committed is not undone. `0` turns it off. |

**Archives from outside.** A reproducibility bundle, an estate and an `.xlsx` are all zip
files, and a zip file is a promise about its own size that an attacker writes. Each is checked
before it is read, and a member is read no further than its entry table declares. The verifier
a bundle carries checks the same before extracting.

| Key | Default | Meaning |
|---|---|---|
| `api.limits.archive.max_entries` | `5000` | Entries an uploaded zip may declare. |
| `api.limits.archive.max_expanded_bytes` | `2147483648` (2 GB) | How far it may expand in total. |
| `api.limits.archive.max_expansion_ratio` | `200` | Expanded bytes per compressed byte over the archive as a whole: past this it is a decompression bomb. |

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

A LaTeX build runs user-supplied source, so it is capped like any other user code (§17.1), and
the caps are recorded on the model version so a reviewer knows what the build was allowed to do.

| Key | Default | Meaning |
|---|---|---|
| `typeset.timeout_seconds` | `120` | Wall clock and CPU a build may spend before it is stopped. |
| `typeset.memory_mb` | `2048` | Address space a build may map. TeX takes its arenas up front, so this is generous by nature: its job is to stop a runaway macro, not to be tight. |
| `typeset.output_mb` | `64` | Largest file a build may write, which caps the PDF and the log together. |

## jobs

| Key | Default | Meaning |
|---|---|---|
| `jobs.workers` | `2` | Worker threads claiming jobs from the database queue. |
| `jobs.max_attempts` | `3` | Attempts before a failing job is dead-lettered, with the failure kept. |
| `jobs.fair` | `true` | Claim jobs by weighted fair queueing across owners rather than in strict arrival order, so one person's campaign cannot starve everybody else (§15.2). |
| `jobs.claim_candidates` | `200` | Queued rows a worker ranks when claiming fairly. Larger is fairer and slower. |
| `jobs.per_user.max_concurrent` | `4` | Jobs one owner may have running at once across the fleet. `0`: no cap. |
| `jobs.per_user.max_queued` | `200` | Jobs one owner may have waiting. A further submission is refused with an estimated wait. `0`: no cap. |
| `jobs.queue.max_depth` | `2000` | Queued jobs across everyone before MAYA sheds load and refuses new submissions (§15.4). `0`: no cap. |
| `jobs.queue.seconds_per_job` | `10` | Assumed service time per job, used only for the wait estimate in a backpressure refusal — which is there so the refusal is honest rather than merely a refusal. |
| `featuresets.cascade_wait_seconds` | `120` | How long a cascade pin waits for its member pins before giving up and rolling the whole cascade back. |

## observability

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `observability.otlp.endpoint` | empty | `MAYA_OTLP_ENDPOINT` | An OTLP/HTTP collector, for example `http://collector:4318/v1/traces`. Spans are exported only when this is set and the OpenTelemetry SDK is installed; trace ids propagate either way. |
| `observability.metrics.token_env` | empty | — | The **name** of an environment variable holding a bearer token for `/metrics`. Empty: `/metrics` is open. Named but unset: every scrape gets 401. |
| `observability.webhooks.max_attempts` | `8` | — | Delivery attempts before a webhook delivery is dead. |
| `observability.webhooks.timeout_seconds` | `5` | — | The timeout of one delivery attempt. |
| `observability.webhooks.allow_private` | `false` | — | Allows webhooks to plain-HTTP localhost and to private addresses. Honoured only in dev. |
| `observability.metrics.namespace_gauges` | `true` | — | Collect pins and bytes stored per namespace at scrape time. It counts pin rows on every scrape, so a very large estate may want it off. |
| `observability.metrics.cache_seconds` | `60` | — | How long the costly scrape-time gauges — lake file counts, pins per namespace — are held before being recomputed. |
| `observability.slow_query_ms` | `500` | — | A database statement slower than this counts as a slow query in `/metrics`. |

## integrity

| Key | Default | Meaning |
|---|---|---|
| `integrity.verify.interval_seconds` | `86400` | How often the maintenance scheduler submits an integrity verification job, which re-reads every sealed pin and recomputes its hash (§20, §21.3). Runs are deduplicated per window, so several web processes do not each start one. `0`: on demand only, from `maya admin verify-integrity` or the API. |

## notify

The channels beside the in-app inbox and the signed webhooks. **Each is off until configured**,
because a platform that mails people by default mails the wrong people the first time it starts,
and a channel that cannot send says so rather than dropping the notice — the inbox copy is
always written first. Every URL and password here is a secret, so it belongs in the environment
or `application.local.yaml`, which the no-secrets gate enforces.

| Key | Default | Meaning |
|---|---|---|
| `notify.email.host` | empty | SMTP host. Empty: MAYA sends no email. |
| `notify.email.port` | `587` | SMTP port. |
| `notify.email.from` | empty | Envelope sender. |
| `notify.email.username` | empty | SMTP username, where the server wants one. |
| `notify.email.password` | empty | SMTP password. **A secret.** |
| `notify.email.starttls` | `true` | Upgrade the connection with STARTTLS. |
| `notify.slack.webhook_url` | empty | Slack incoming-webhook URL. **A secret**, and one channel per URL: MAYA posts the notice and does not name recipients. |
| `notify.teams.webhook_url` | empty | Microsoft Teams incoming-webhook URL. **A secret**; see the Slack note. |

## plugins

| Key | Default | Meaning |
|---|---|---|
| `plugins.allow` | empty | Names of installed `maya.<point>` entry-point plugins MAYA may load, comma separated. An entry-point plugin runs in MAYA's own process with MAYA's privileges — it can read the database and the signing key — so §25's "untrusted plugins run under the sandbox rules" cannot be true of it, and the safety rule is this allowlist instead. Anything installed and not named here is listed on the admin **Extensions** page as refused, with that reason, rather than being absent for no visible cause. A plugin that fails to import is reported too, and does not stop MAYA. |

## sources

Limits for `python` sources: a producer function run in the sandbox on each pull.

| Key | Default | Meaning |
|---|---|---|
| `sources.python.cpu_seconds` | `30` | CPU time allowed. |
| `sources.python.memory_mb` | `1024` | Memory allowed. |
| `sources.python.wall_seconds` | `60` | Wall-clock time before the child is killed. |
| `sources.python.max_output_mb` | `20` | The largest result accepted. |

A `delta` source reads a Delta table already on the server, which is a file path a definition
supplies — so it is confined, or it is a peephole into the filesystem.

| Key | Default | Meaning |
|---|---|---|
| `sources.delta.roots` | empty | Directories a `delta` source may read, separated by the platform's path separator. Empty means the lake root alone. A path outside them is refused. |

## assistant

The recorded challenger writes a memo on every submission into review. It never approves, blocks or edits.

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `assistant.enabled` | `true` | — | Queue a challenge memo when an object enters review. |
| `assistant.provider` | `rules` | `MAYA_ASSISTANT_PROVIDER` | `rules`: deterministic findings, no network. `llm`: also asks a language model through the AI gateway (see `assistant.profile`), so any provider an administrator set up serves. `claude`: asks Anthropic's API directly. Either sends definitions, the specification and the formula — never data rows — to the provider. |
| `assistant.profile` | empty | — | With `llm`: the model profile asked. Empty: the gateway's default profile, so switching the default in **Admin → AI models** moves the challenger too. |
| `assistant.claude.model` | `claude-opus-5` | — | The model asked when the provider is `claude`. |
| `assistant.claude.effort` | `high` | — | The effort level passed to the model. |
| `assistant.claude.api_key_env` | empty | — | The name of an environment variable holding the Anthropic key. Empty: the Anthropic SDK's own resolution (`ANTHROPIC_API_KEY`, or a saved login). |
| `assistant.claude.timeout_seconds` | `300` | — | The request timeout. |

## llm

The AI gateway: the one place MAYA asks a language model anything — drafted sections of generated documents, the assistant's challenger under `assistant.provider: llm`, live evaluations of LLM applications. Callers name a **model profile**; without a profiles file there is one, `default`, made from these keys. Profiles can also be added in **Admin → AI models**, where the default can be switched at runtime. See *Model documents and the AI gateway* in Help.

| Key | Default | Meaning |
|---|---|---|
| `llm.provider` | `none` | `none` (drafts nothing), `stub`, `anthropic`, `openai`, `azure_openai`, `ollama`, `bedrock`, or an allowed `llm_provider` plugin. |
| `llm.model` | empty | The model to ask. Empty: the provider's own default below. |
| `llm.profiles_file` | `config/llm_profiles.yaml` | Named profiles (provider, model, parameters, options); `config/llm_profiles.example.yaml` shows the format. Missing: one profile from these keys. |
| `llm.profile` | empty | The default profile. Empty: the file's own `default:`. An administrator's choice in Admin → AI models overrides both. |
| `llm.max_tokens` | `2048` | The longest answer asked for, per call. |
| `llm.temperature` | `0.2` | Sampling temperature where the provider takes one. |
| `llm.timeout_seconds` | `120` | Per-call timeout. |
| `llm.anthropic.model` | `claude-opus-5` | Anthropic's default model. |
| `llm.anthropic.api_key_env` | `ANTHROPIC_API_KEY` | The environment variable holding the key. |
| `llm.anthropic.base_url` | empty | A different Anthropic endpoint. Empty: the SDK's own. |
| `llm.anthropic.thinking` | `adaptive` | `adaptive` lets the model think before answering; `off` does not. |
| `llm.openai.base_url` | `https://api.openai.com/v1` | A Chat Completions endpoint: OpenAI, or any compatible server (vLLM, LM Studio, a gateway). |
| `llm.openai.api_key_env` | `OPENAI_API_KEY` | The environment variable holding the key; empty for a local server. |
| `llm.openai.model` | empty | The model to ask at that endpoint. |
| `llm.azure_openai.endpoint` | empty | The Azure OpenAI resource endpoint. |
| `llm.azure_openai.deployment` | empty | The deployment to call. |
| `llm.azure_openai.api_version` | `2024-10-21` | The Azure OpenAI API version. |
| `llm.azure_openai.api_key_env` | `AZURE_OPENAI_API_KEY` | The environment variable holding the key. |
| `llm.ollama.base_url` | `http://localhost:11434` | Where Ollama serves. |
| `llm.ollama.model` | `llama3.1` | The Ollama model to ask. |
| `llm.bedrock.region` | `us-east-1` | The AWS region Bedrock is called in. |
| `llm.bedrock.profile` | empty | An AWS profile name. Empty: boto3's own resolution. |
| `llm.bedrock.model` | empty | The Bedrock model id. |

!!! warning "Keys never go in a profile"
    A profile, in the file or saved from the admin page, names the environment variable that holds a key (`api_key_env`); MAYA refuses one that holds a key itself.

## documents

| Key | Default | Meaning |
|---|---|---|
| `documents.template_dir` | `config/templates/documents` | Where a firm's own document templates live. A file named like a built-in (`model_card.md.j2`) replaces it; any other template there is offered for the kind its first line declares. |

## governance

| Key | Default | Meaning |
|---|---|---|
| `governance.tiering_questionnaire` | `config/tiering.yaml` | The materiality questionnaire a model's owner answers, from which its tier is derived. Blank: the tier comes from measured drivers only. |
| `governance.review_days_tier1` | `365` | Days between periodic reviews of a tier 1 model, unless its governance profile sets `review_days`. |
| `governance.review_days_tier2` | `730` | The same for tier 2. |
| `governance.review_days_tier3` | `1095` | The same for tier 3. |

## restatements

| Key | Default | Meaning |
|---|---|---|
| `restatements.alerts` | `true` | After an ingest restates rows, check every live execution warrant's training pin against what is known now, and record and notify how far the result moves. **Check now** on a warrant works either way. |

## integrations

| Key | Default | Meaning |
|---|---|---|
| `integrations.mlflow.tracking_uri` | empty | The MLflow tracking server models may be fetched from. Empty: models are uploaded only. |
| `integrations.mlflow.token_env` | empty | The environment variable holding a bearer token for that server, if it needs one. |
| `integrations.mlflow.live_alias` | `maya-live` | The MLflow alias MAYA sets on each registered version while it has a live execution warrant, and removes when it has none. |
| `integrations.openlineage.url` | empty | An OpenLineage endpoint (Marquez, for example) lineage is posted to. Empty: lineage can be downloaded, not posted. |
| `integrations.openlineage.api_key_env` | empty | The environment variable holding that endpoint's bearer token, if any. |
| `integrations.openlineage.namespace` | `maya` | The OpenLineage namespace MAYA's jobs and datasets are reported under. |

## custody

| Key | Default | Placeholder | Meaning |
|---|---|---|---|
| `custody.anchor.methods` | `signature,file,event` | — | How the audit chain head is anchored: any of `signature` (Ed25519), `file` (an append-only JSON-lines file), `event` (an `audit.anchored` event, visible to webhooks), `rfc3161` (a timestamp authority; sends the head hash to it). |
| `custody.anchor.file` | empty | `MAYA_ANCHOR_FILE` | The anchor file. Empty: `<storage.root>/anchors.jsonl`. Point it at write-once or off-host storage. |
| `custody.anchor.tsa_url` | empty | `MAYA_TSA_URL` | The RFC 3161 timestamp authority. Required when `methods` names `rfc3161`. |
| `custody.anchor.tsa_ca_file` | empty | `MAYA_TSA_CA_FILE` | The TSA's CA certificate, PEM. Set, MAYA checks the TSA's signature on each token with `openssl ts -verify`, when it anchors and at every custody verification. Empty, it checks the token's status and imprint only, and names the `openssl` command to run by hand — a token whose signature nobody checked is a claim, not a timestamp. |
| `custody.anchor.interval_seconds` | `3600` | — | How often the scheduler anchors the head. |

## workspaces

| Key | Default | Meaning |
|---|---|---|
| `workspaces.shadow.sample_rows` | `5000` | Rows replayed per dependent warrant in a shadow replay (the most recent, by index). Stated on the report. |
| `workspaces.shadow.materiality` | `0.0001` | An absolute output shift above this counts as material, unless the model version declares its own figure or its namespace sets one. |
| `workspaces.shadow.budget_rows` | `2000000` | Row comparisons a namespace's replays may spend in a rolling day, charged from the audit log. A namespace may set its own `shadow_budget_rows`; `0` anywhere means no ceiling. |

## health

| Key | Default | Meaning |
|---|---|---|
| `health.audit_verify_seconds` | `60` | The health report (read on every home page) re-walks the whole audit chain at most this often and states when it last did (`audit_chain.verified_at`). The audit page and the integrity check always walk it afresh. |

Materialization of feature-set pins is a per-namespace setting (`materialize_policy`: `always`, the default; `on_demand`; or `never`), not a configuration key. See the feature sets reference.

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
| `MAYA_OIDC_ISSUER`, `MAYA_OIDC_CLIENT_ID`, `MAYA_OIDC_CLIENT_SECRET`, `MAYA_OIDC_REDIRECT_URI`, `MAYA_OIDC_POST_LOGOUT_URI` | `auth.sso.*` |
| `MAYA_SAML_SP_ENTITY_ID`, `MAYA_SAML_ACS_URL`, `MAYA_SAML_IDP_ENTITY_ID`, `MAYA_SAML_IDP_SSO_URL`, `MAYA_SAML_IDP_CERT`, `MAYA_SAML_IDP_CERT_FILE`, `MAYA_SAML_IDP_SLO_URL`, `MAYA_SAML_SLS_URL`, `MAYA_SAML_SIGN_REQUESTS`, `MAYA_SAML_SP_CERT`, `MAYA_SAML_SP_CERT_FILE`, `MAYA_SAML_SP_KEY`, `MAYA_SAML_SP_KEY_FILE` | `auth.sso.saml.*` |
| `MAYA_WEBAUTHN_RP_ID`, `MAYA_WEBAUTHN_ORIGINS` | `auth.webauthn.*` |
| `MAYA_MFA_ENFORCE` | `auth.mfa.enforce` |
| `MAYA_REQUIRE_TECTONIC` | `typeset.require_true_build` |
| `MAYA_OTLP_ENDPOINT` | `observability.otlp.endpoint` |
| `MAYA_ASSISTANT_PROVIDER` | `assistant.provider` |
| `MAYA_ANCHOR_FILE`, `MAYA_TSA_URL`, `MAYA_TSA_CA_FILE` | `custody.anchor.file`, `custody.anchor.tsa_url`, `custody.anchor.tsa_ca_file` |

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
