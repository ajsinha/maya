"""
The declared configuration schema (§24.2): every setting, its type, what it is
for, its default and its validator.

Before this existed a setting was whatever ``settings.get(key, default)``
happened to say at the call site, so the tracked ``config/application.yaml``,
the documentation and the code could drift apart without anything noticing, and
a typo in the file was simply a key nobody read. Declaring every setting in one
place fixes three things at once:

* a key in a configuration file that is not declared here is refused at startup,
  with the nearest declared key named, so ``db.dialct`` stops MAYA instead of
  silently leaving SQLite in place;
* a setting's default lives here and nowhere else, so a call site cannot
  introduce a second, different default (``tests/test_config_schema.py``
  compares every code default against this table and fails on a difference);
* a setting the specification says must exist is marked ``required``, and MAYA
  refuses to start without it rather than guessing.

``family`` covers the two shapes whose leaf names are not known in advance —
seam pins and the IdP group-to-role map — and ``kind`` ``list`` accepts the
``key.0``, ``key.1`` indices the YAML parser writes beside a joined list.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from maya.core.errors import ConfigurationError

KINDS = ("string", "int", "float", "bool", "path", "choice", "list", "duration")
_TRUE = ("1", "true", "yes", "on", "y", "t")
_FALSE = ("0", "false", "no", "off", "n", "f")


@dataclass(frozen=True)
class Setting:
    """One declared setting: what it is, what it defaults to, what it accepts."""

    key: str
    kind: str
    description: str
    default: str | None = None
    required: bool = False
    choices: tuple[str, ...] = ()
    secret: bool = False
    family: bool = False
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, value: str) -> None:
        """Refuse a value this setting cannot hold, naming the key and what it accepts."""
        if self.kind == "choice" and value.strip().lower() not in self.choices:
            self._refuse(value, f"one of {', '.join(self.choices)}")
        if self.kind == "bool" and value.strip().lower() not in _TRUE + _FALSE:
            self._refuse(value, "a boolean (true/false)")
        if self.kind in ("int", "duration"):
            try:
                number: float = int(value)
            except ValueError:
                self._refuse(value, "a whole number")
        elif self.kind == "float":
            try:
                number = float(value)
            except ValueError:
                self._refuse(value, "a number")
        else:
            return
        if self.minimum is not None and number < self.minimum:
            self._refuse(value, f"at least {self.minimum:g}")
        if self.maximum is not None and number > self.maximum:
            self._refuse(value, f"at most {self.maximum:g}")

    def _refuse(self, value: str, expected: str) -> None:
        raise ConfigurationError(
            f"Setting '{self.key}' is '{value}'; expected {expected}. {self.description}",
            key=self.key,
            expected=expected,
        )


def _s(*args: Any, **kw: Any) -> Setting:
    return Setting(*args, **kw)


SETTINGS: tuple[Setting, ...] = (
    # -- the application ------------------------------------------------------
    _s("app.name", "string", "The name in the banner and the page titles.", "MAYA"),
    _s(
        "app.environment",
        "choice",
        "dev, uat or prod. Outside dev the default admin password, SQLite and a weak "
        "sandbox each refuse to start.",
        required=True,
        choices=("dev", "uat", "prod"),
    ),
    _s(
        "app.secret_key",
        "string",
        "The session-signing secret. Empty in dev generates one under storage.root/keys; "
        "outside dev an empty value refuses to start.",
        "",
        secret=True,
    ),
    _s(
        "app.allow_default_admin_password",
        "bool",
        "Let a non-dev environment start with the bootstrap admin password unchanged. "
        "Only ever true while a deployment is being set up.",
        "false",
    ),
    # -- the server -----------------------------------------------------------
    _s("server.host", "string", "The address the web server binds.", "127.0.0.1"),
    _s("server.port", "int", "The port the web server binds.", "8600", minimum=1, maximum=65535),
    _s(
        "server.workers",
        "int",
        "Web processes. Above 1 needs PostgreSQL (ADR-022) and the launching process keeps "
        "the job workers, webhooks and scheduler.",
        "1",
        minimum=1,
    ),
    # -- logging --------------------------------------------------------------
    _s("logging.level", "string", "The root log level at startup.", "INFO"),
    _s("logging.format", "choice", "Line format.", "text", choices=("text", "json")),
    _s("logging.file", "path", "Where the log is written. Empty: stderr only.", ""),
    # -- the database ---------------------------------------------------------
    _s(
        "db.dialect",
        "choice",
        "sqlite or postgresql, never mixed (ADR-013). The schema file follows from it.",
        required=True,
        choices=("sqlite", "postgresql"),
    ),
    _s("db.echo", "bool", "Log every SQL statement. Debugging only.", "false"),
    _s(
        "db.sqlite.path",
        "path",
        "The SQLite database file. No default: it is required when db.dialect is sqlite, and required() names it.",
        None,
    ),
    _s(
        "db.sqlite.busy_timeout_ms",
        "int",
        "How long a writer waits for SQLite's single write lock before failing.",
        "30000",
        minimum=0,
    ),
    _s("db.postgresql.host", "string", "The PostgreSQL host.", "localhost"),
    _s("db.postgresql.port", "int", "The PostgreSQL port.", "5432", minimum=1, maximum=65535),
    _s("db.postgresql.database", "string", "The PostgreSQL database name.", "maya"),
    _s("db.postgresql.user", "string", "The PostgreSQL user.", "maya"),
    _s(
        "db.postgresql.password",
        "string",
        "The PostgreSQL password. From the environment or the local overlay, never the "
        "tracked file.",
        "",
        secret=True,
    ),
    _s("db.postgresql.pool_size", "int", "Connections kept open.", "10", minimum=1),
    _s(
        "db.postgresql.max_overflow",
        "int",
        "Connections opened above the pool under load.",
        "10",
        minimum=0,
    ),
    # -- storage and the lake -------------------------------------------------
    _s(
        "storage.root",
        "path",
        "Root of the local stores: the lake, blobs, keys, logs and the SQLite file.",
        required=True,
    ),
    _s(
        "lake.root",
        "path",
        "Where the Delta lake lives. Empty means <storage.root>/lake, which is what a "
        "throwaway instance wants. A relative path is resolved against the project root "
        "-- the checkout this package was imported from -- rather than the working "
        "directory, so that the same configuration means the same lake whatever directory "
        "a script is launched from.",
        "",
    ),
    _s(
        "lake.backend",
        "choice",
        "The maya_delta backend (§7.4).",
        "auto",
        choices=("auto", "native", "pure"),
    ),
    # -- what one caller may ask of one process (§13.2, §21.1, §24.4) -----------
    _s(
        "api.limits.max_body_bytes",
        "int",
        "Largest request body accepted, by its header or as it streams in. 0 turns the limit off.",
        "268435456",
        minimum=0,
    ),
    _s(
        "api.limits.requests_per_minute",
        "int",
        "Requests a caller may make in a minute before MAYA answers 429. Counted per web "
        "process, so several processes multiply it. 0 turns it off.",
        "6000",
        minimum=0,
    ),
    _s(
        "api.limits.burst",
        "int",
        "Requests a caller may make back to back before the per-minute rate applies.",
        "1200",
        minimum=1,
    ),
    _s(
        "api.limits.max_concurrent",
        "int",
        "Requests in flight in one web process before it sheds load with 503 rather than "
        "queueing. 0 turns it off.",
        "128",
        minimum=0,
    ),
    _s(
        "api.limits.timeout_seconds",
        "duration",
        "How long a request may run before it is answered 504. Work already committed is "
        "not undone. 0 turns it off.",
        "120",
        minimum=0,
    ),
    _s(
        "api.limits.archive.max_entries",
        "int",
        "Entries an uploaded zip - a bundle, an estate, an .xlsx - may declare.",
        "5000",
        minimum=1,
    ),
    _s(
        "api.limits.archive.max_expanded_bytes",
        "int",
        "How far an uploaded archive may expand in total.",
        "2147483648",
        minimum=1,
    ),
    _s(
        "api.limits.archive.max_expansion_ratio",
        "int",
        "Expanded bytes per compressed byte, over the archive as a whole: past this it is "
        "a decompression bomb.",
        "200",
        minimum=1,
    ),
    _s(
        "sources.delta.roots",
        "string",
        "Directories a `delta` feature source may read, separated by the path separator. "
        "Empty means the lake root alone.",
        "",
    ),
    # -- extension points and notification channels (§25) -----------------------
    _s(
        "plugins.allow",
        "string",
        "Names of installed entry-point plugins MAYA may load, comma separated. A plugin "
        "runs in this process with MAYA's privileges, so it is opt-in by name; anything "
        "installed and not named here is listed as refused with that reason.",
        "",
    ),
    _s(
        "notify.email.host",
        "string",
        "SMTP host for the email channel. Empty means MAYA sends no email.",
        "",
    ),
    _s("notify.email.port", "int", "SMTP port.", "587", minimum=1),
    _s("notify.email.from", "string", "Envelope sender for MAYA's email.", ""),
    _s("notify.email.username", "string", "SMTP username, where the server wants one.", ""),
    _s(
        "notify.email.password",
        "string",
        "SMTP password. A secret: set it in the environment or the local overlay, never in "
        "the tracked configuration file.",
        "",
        secret=True,
    ),
    _s("notify.email.starttls", "bool", "Upgrade the SMTP connection with STARTTLS.", "true"),
    _s(
        "notify.slack.webhook_url",
        "string",
        "Slack incoming-webhook URL. A secret, and one channel per URL: MAYA posts the "
        "notice and does not name recipients.",
        "",
        secret=True,
    ),
    _s(
        "notify.teams.webhook_url",
        "string",
        "Microsoft Teams incoming-webhook URL. A secret; see the Slack note.",
        "",
        secret=True,
    ),
    _s(
        "lake.maintenance.interval_seconds",
        "duration",
        "How often the scheduler compacts and vacuums every lake table.",
        "86400",
        minimum=0,
    ),
    _s(
        "lake.maintenance.target_size_mb",
        "int",
        "Compaction's target file size.",
        "128",
        minimum=1,
    ),
    _s(
        "lake.maintenance.vacuum_retention_hours",
        "float",
        "How long an unreferenced file is kept for time travel. Under 168 is allowed but "
        "must be written out.",
        "168",
        minimum=0,
    ),
    _s("lake.fragment.target_rows", "int", "Rows per pin fragment, aimed at.", "512", minimum=1),
    _s("lake.fragment.min_rows", "int", "Smallest pin fragment.", "32", minimum=1),
    _s("lake.fragment.max_rows", "int", "Largest pin fragment.", "8192", minimum=1),
    # -- authentication -------------------------------------------------------
    _s(
        "auth.mode",
        "choice",
        "db (passwords), sso (the IdP only) or hybrid.",
        required=True,
        choices=("db", "sso", "hybrid"),
    ),
    _s(
        "auth.session.idle_timeout_minutes",
        "int",
        "A session idle this long ends.",
        "30",
        minimum=1,
    ),
    _s(
        "auth.session.absolute_timeout_hours",
        "int",
        "A session ends this long after sign-in whatever it is doing.",
        "12",
        minimum=1,
    ),
    _s(
        "auth.session.principal_cache_seconds",
        "int",
        "A signed-in session's principal is reused this long (0: never). ADR-026.",
        "2",
        minimum=0,
    ),
    _s(
        "auth.session.concurrent_sessions",
        "int",
        "Live sessions one person may hold; a further sign-in ends their oldest. 0: no cap.",
        "3",
        minimum=0,
    ),
    _s("auth.password.min_length", "int", "Shortest password accepted.", "8", minimum=4),
    _s(
        "auth.password.force_change",
        "bool",
        "Make a person change a password an administrator set (the bootstrap admin's, a new "
        "account's, a reset) at their next sign-in. Off by default: with SSO it is rarely wanted.",
        "false",
    ),
    _s(
        "auth.password.require_classes",
        "int",
        "How many of lower, upper, digit and symbol a password must use.",
        "2",
        minimum=1,
        maximum=4,
    ),
    _s(
        "auth.password.history",
        "int",
        "How many previous passwords may not be chosen again. 0: no history.",
        "5",
        minimum=0,
    ),
    _s(
        "auth.password.max_age_days",
        "int",
        "A password older than this must be changed before its owner can sign in. 0: never.",
        "90",
        minimum=0,
    ),
    _s(
        "auth.password.reset_token_minutes",
        "int",
        "How long a password-reset token is valid; it is single use whatever its age.",
        "60",
        minimum=1,
    ),
    _s("auth.lockout.attempts", "int", "Failed sign-ins before a lockout.", "5", minimum=1),
    _s(
        "auth.lockout.window_minutes", "int", "The window those attempts count in.", "15", minimum=1
    ),
    _s("auth.lockout.duration_minutes", "int", "How long a lockout lasts.", "30", minimum=1),
    _s("auth.api_keys.max_days", "int", "Longest life of an API key.", "365", minimum=1),
    _s(
        "auth.api_keys.rate_per_minute",
        "int",
        "A key's own request budget a minute when it declares none. 0: the process limit only.",
        "0",
        minimum=0,
    ),
    _s(
        "auth.api_keys.rotation_overlap_days",
        "int",
        "How long a rotated key keeps working beside its successor.",
        "7",
        minimum=0,
    ),
    _s(
        "auth.api_keys.unused_days",
        "int",
        "A key unused this long is reported for revocation.",
        "90",
        minimum=1,
    ),
    _s(
        "auth.api_keys.remind_days_before_expiry",
        "int",
        "How long before expiry a key is reported for rotation.",
        "14",
        minimum=1,
    ),
    _s(
        "auth.client_credentials.token_minutes",
        "int",
        "How long an access token from the client-credentials grant lives.",
        "60",
        minimum=1,
    ),
    _s(
        "auth.break_glass.users",
        "list",
        "Accounts that may sign in with a password even under auth.mode: sso, for an IdP "
        "outage (§13.3). Every use is audited loudly and notified to every administrator.",
        "",
    ),
    _s(
        "auth.break_glass.session_minutes",
        "int",
        "How long a break-glass session lasts, whatever the ordinary session timeouts say.",
        "60",
        minimum=1,
    ),
    _s(
        "auth.sso.protocol",
        "choice",
        "The single sign-on protocol.",
        "oidc",
        choices=("oidc", "saml2"),
    ),
    _s("auth.sso.issuer", "string", "The OIDC issuer URL.", ""),
    _s("auth.sso.client_id", "string", "MAYA's client id at the IdP.", "maya"),
    _s("auth.sso.client_secret", "string", "MAYA's client secret at the IdP.", "", secret=True),
    _s(
        "auth.sso.redirect_uri",
        "string",
        "Where the IdP sends the authorization code.",
        "http://127.0.0.1:8600/auth/sso/callback",
    ),
    _s(
        "auth.sso.post_logout_redirect_uri",
        "string",
        "Set it to sign out at the IdP too (ADR-027). Empty: the MAYA session only.",
        "",
    ),
    _s(
        "auth.sso.scopes",
        "string",
        "Scopes requested, space separated.",
        "openid profile email groups",
    ),
    _s(
        "auth.sso.username_claim", "string", "The claim holding the username.", "preferred_username"
    ),
    _s("auth.sso.email_claim", "string", "The claim holding the email address.", "email"),
    _s("auth.sso.groups_claim", "string", "The claim holding the group list.", "groups"),
    _s("auth.sso.jit_provision", "bool", "Create a user on first successful sign-in.", "true"),
    _s(
        "auth.sso.on_missing_group",
        "choice",
        "What happens to someone none of whose IdP groups maps to a role.",
        "deny",
        choices=("deny", "allow"),
    ),
    _s(
        "auth.sso.group_role_map",
        "list",
        "IdP group to MAYA roles, re-applied at every login. A family: one key per group.",
        "",
        family=True,
    ),
    _s("auth.sso.saml.sp_entity_id", "string", "MAYA's SAML entity id.", ""),
    _s(
        "auth.sso.saml.acs_url",
        "string",
        "MAYA's assertion consumer service URL.",
        "http://127.0.0.1:8600/auth/sso/saml/acs",
    ),
    _s("auth.sso.saml.idp_entity_id", "string", "The IdP's SAML entity id.", ""),
    _s("auth.sso.saml.idp_sso_url", "string", "The IdP's single sign-on endpoint.", ""),
    _s("auth.sso.saml.idp_cert", "string", "The IdP's signing certificate, inline (public).", ""),
    _s("auth.sso.saml.idp_cert_file", "path", "The IdP's signing certificate, as a file.", ""),
    _s("auth.sso.saml.idp_slo_url", "string", "The IdP's single logout endpoint (ADR-024).", ""),
    _s(
        "auth.sso.saml.sls_url",
        "string",
        "MAYA's single logout service URL.",
        "http://127.0.0.1:8600/auth/sso/saml/sls",
    ),
    _s("auth.sso.saml.sign_requests", "bool", "Sign AuthnRequests and logout messages.", "false"),
    _s("auth.sso.saml.sp_cert", "string", "MAYA's SAML certificate, inline.", ""),
    _s("auth.sso.saml.sp_cert_file", "path", "MAYA's SAML certificate, as a file.", ""),
    _s("auth.sso.saml.sp_key", "string", "MAYA's SAML private key, inline.", "", secret=True),
    _s("auth.sso.saml.sp_key_file", "path", "MAYA's SAML private key, as a file.", ""),
    _s(
        "auth.sso.saml.username_attribute",
        "string",
        "The assertion attribute holding the username. Empty: the NameID.",
        "",
    ),
    _s("auth.sso.saml.groups_attribute", "string", "The attribute holding the groups.", "groups"),
    _s("auth.sso.saml.email_attribute", "string", "The attribute holding the email.", "email"),
    _s(
        "auth.sso.saml.name_attribute",
        "string",
        "The attribute holding the display name.",
        "displayName",
    ),
    _s(
        "auth.webauthn.rp_id",
        "string",
        "The WebAuthn relying-party id: the site's domain, never an IP address.",
        "localhost",
    ),
    _s("auth.webauthn.rp_name", "string", "The relying-party name shown by the browser.", "MAYA"),
    _s(
        "auth.webauthn.origins",
        "string",
        "Exact origins accepted, comma separated.",
        "http://localhost:8600",
    ),
    _s(
        "auth.mfa.enforce",
        "choice",
        "auto enforces the role requirement outside dev; true always; false never.",
        "auto",
        choices=("auto", "true", "false"),
    ),
    _s(
        "auth.mfa.required_for_roles",
        "list",
        "Roles a second factor is required for.",
        "admin,model_owner",
    ),
    _s("auth.mfa.issuer_name", "string", "The issuer shown in an authenticator app.", "MAYA"),
    # -- the sandbox, workflow and typesetting --------------------------------
    _s(
        "sandbox.min_tier",
        "choice",
        "Outside dev MAYA refuses to start below this tier (§17.2).",
        "strong",
        choices=("strong", "moderate", "minimal"),
    ),
    _s(
        "workflow.allow_self_approval",
        "bool",
        "Honoured in dev only: lets one person submit and approve.",
        "false",
    ),
    _s(
        "typeset.require_true_build",
        "bool",
        "A model cannot be approved on a draft (non-Tectonic) render.",
        "false",
    ),
    _s(
        "typeset.timeout_seconds",
        "int",
        "Wall clock and CPU a LaTeX build may spend before it is stopped (§17.1).",
        "120",
        minimum=1,
    ),
    _s(
        "typeset.memory_mb",
        "int",
        "Address space a LaTeX build may map (§17.1). TeX takes its arenas up front, so "
        "this is generous by nature; its job is to stop a runaway macro, not to be tight.",
        "2048",
        minimum=64,
    ),
    _s(
        "typeset.output_mb",
        "int",
        "Largest file a LaTeX build may write (§17.1), which caps the PDF and the log together.",
        "64",
        minimum=1,
    ),
    # -- jobs (§15) -----------------------------------------------------------
    _s("jobs.workers", "int", "Job worker threads in this process.", "2", minimum=0),
    _s("jobs.max_attempts", "int", "Attempts before a job dead-letters.", "3", minimum=1),
    _s(
        "jobs.fair",
        "bool",
        "Claim jobs by weighted fair queueing across owners rather than strict arrival "
        "order, so one person's campaign cannot starve everyone else (§15.2).",
        "true",
    ),
    _s(
        "jobs.per_user.max_concurrent",
        "int",
        "Jobs one owner may have running at once across the fleet. 0: no cap.",
        "4",
        minimum=0,
    ),
    _s(
        "jobs.per_user.max_queued",
        "int",
        "Jobs one owner may have waiting. A further submission is refused with an "
        "estimated wait. 0: no cap.",
        "200",
        minimum=0,
    ),
    _s(
        "jobs.queue.max_depth",
        "int",
        "Queued jobs across everyone before MAYA sheds load and refuses new "
        "submissions (§15.4). 0: no cap.",
        "2000",
        minimum=0,
    ),
    _s(
        "jobs.queue.seconds_per_job",
        "float",
        "Assumed service time per job, used only for the honest wait estimate in a "
        "backpressure refusal.",
        "10",
        minimum=0,
    ),
    _s(
        "jobs.claim_candidates",
        "int",
        "Queued rows a worker ranks when claiming fairly. Larger is fairer and slower.",
        "200",
        minimum=1,
    ),
    _s(
        "featuresets.cascade_wait_seconds",
        "duration",
        "How long a cascade pin waits for its member pins before giving up.",
        "120",
        minimum=1,
    ),
    # -- observability (§20) --------------------------------------------------
    _s("observability.otlp.endpoint", "string", "OTLP/HTTP span endpoint. Empty: no export.", ""),
    _s(
        "observability.metrics.token_env",
        "string",
        "Name of an environment variable holding a bearer token for /metrics.",
        "",
    ),
    _s(
        "observability.metrics.namespace_gauges",
        "bool",
        "Collect pins and bytes stored per namespace at scrape time. It counts pin rows "
        "on every scrape, so a very large estate may want it off.",
        "true",
    ),
    _s(
        "observability.metrics.cache_seconds",
        "duration",
        "How long the costly scrape-time gauges — lake file counts, pins per namespace — "
        "are held before being recomputed.",
        "60",
        minimum=0,
    ),
    _s(
        "observability.slow_query_ms",
        "duration",
        "A database statement slower than this counts as a slow query in /metrics.",
        "500",
        minimum=1,
    ),
    _s("observability.webhooks.max_attempts", "int", "Delivery attempts.", "8", minimum=1),
    _s(
        "observability.webhooks.timeout_seconds",
        "float",
        "Per-delivery timeout.",
        "5",
        minimum=0.1,
    ),
    _s(
        "governance.tiering_questionnaire",
        "path",
        "The materiality questionnaire a model's owner answers; blank for measured drivers only.",
        "config/tiering.yaml",
    ),
    # -- connectors -----------------------------------------------------------------
    _s(
        "integrations.mlflow.tracking_uri",
        "string",
        "The MLflow tracking server models may be fetched from; blank means upload only.",
        "",
    ),
    _s(
        "integrations.mlflow.token_env",
        "string",
        "Environment variable holding a bearer token for the MLflow server, if it needs one.",
        "",
    ),
    _s(
        "integrations.mlflow.live_alias",
        "string",
        "The MLflow alias MAYA points at each model version with a live execution warrant.",
        "maya-live",
    ),
    _s(
        "integrations.openlineage.url",
        "string",
        "An OpenLineage endpoint (e.g. Marquez) lineage is posted to; blank means download only.",
        "",
    ),
    _s(
        "integrations.openlineage.api_key_env",
        "string",
        "Environment variable holding the OpenLineage endpoint's bearer token, if any.",
        "",
    ),
    _s(
        "integrations.openlineage.namespace",
        "string",
        "The OpenLineage namespace MAYA's jobs and datasets are reported under.",
        "maya",
    ),
    _s(
        "observability.webhooks.allow_private",
        "bool",
        "dev only: allow localhost and private addresses as webhook targets.",
        "false",
    ),
    _s(
        "health.audit_verify_seconds",
        "duration",
        "The health page re-walks the whole audit chain at most this often.",
        "60",
        minimum=0,
    ),
    _s(
        "integrity.verify.interval_seconds",
        "duration",
        "How often the scheduler submits an integrity verification job (§20, §21.3). "
        "0: only on demand.",
        "86400",
        minimum=0,
    ),
    # -- sources, the assistant, custody, workspaces --------------------------
    _s("sources.python.cpu_seconds", "int", "CPU cap for a python source.", "30", minimum=1),
    _s("sources.python.memory_mb", "int", "Memory cap for a python source.", "1024", minimum=64),
    _s(
        "sources.python.wall_seconds", "int", "Wall-clock cap for a python source.", "60", minimum=1
    ),
    _s("sources.python.max_output_mb", "int", "Largest output a python source may return.", "20"),
    _s(
        "llm.provider",
        "string",
        "The language model MAYA drafts documents with: none, stub, anthropic, openai, "
        "azure_openai, ollama, bedrock, or an allowed llm_provider plugin (none drafts nothing).",
        "none",
    ),
    _s("llm.model", "string", "The model to ask. Empty: the provider's own default setting.", ""),
    _s(
        "llm.profiles_file",
        "path",
        "Named model profiles (provider, model, parameters, options); callers name a profile. "
        "Missing: one profile, default, from the llm.* settings.",
        "config/llm_profiles.yaml",
    ),
    _s("llm.profile", "string", "The default profile. Empty: the file's own default.", ""),
    _s(
        "llm.max_tokens",
        "int",
        "Longest answer asked for, per drafted section.",
        "2048",
        minimum=64,
    ),
    _s("llm.temperature", "float", "Sampling temperature where the provider takes one.", "0.2"),
    _s("llm.timeout_seconds", "int", "Per-call timeout for a provider.", "120", minimum=1),
    _s("llm.anthropic.model", "string", "Anthropic's default model.", "claude-opus-5"),
    _s(
        "llm.anthropic.api_key_env",
        "string",
        "Environment variable holding the Anthropic key.",
        "ANTHROPIC_API_KEY",
    ),
    _s(
        "llm.anthropic.base_url",
        "string",
        "A different Anthropic API endpoint. Empty: the SDK's own.",
        "",
    ),
    _s(
        "llm.anthropic.thinking",
        "choice",
        "adaptive lets the model think before answering; off does not.",
        "adaptive",
        choices=("adaptive", "off"),
    ),
    _s(
        "llm.openai.base_url",
        "string",
        "Chat Completions endpoint: OpenAI, or any compatible server.",
        "https://api.openai.com/v1",
    ),
    _s(
        "llm.openai.api_key_env",
        "string",
        "Environment variable holding the key (empty for a local server).",
        "OPENAI_API_KEY",
    ),
    _s("llm.openai.model", "string", "The model to ask at that endpoint.", ""),
    _s("llm.azure_openai.endpoint", "string", "The Azure OpenAI resource endpoint.", ""),
    _s("llm.azure_openai.deployment", "string", "The deployment to call.", ""),
    _s("llm.azure_openai.api_version", "string", "The Azure OpenAI API version.", "2024-10-21"),
    _s(
        "llm.azure_openai.api_key_env",
        "string",
        "Environment variable holding the Azure key.",
        "AZURE_OPENAI_API_KEY",
    ),
    _s("llm.ollama.base_url", "string", "Where Ollama serves.", "http://localhost:11434"),
    _s("llm.ollama.model", "string", "The Ollama model to ask.", "llama3.1"),
    _s("llm.bedrock.region", "string", "The AWS region Bedrock is called in.", "us-east-1"),
    _s("llm.bedrock.profile", "string", "An AWS profile name. Empty: boto3's own resolution.", ""),
    _s("llm.bedrock.model", "string", "The Bedrock model id to ask.", ""),
    _s(
        "documents.template_dir",
        "path",
        "Where a firm's own document templates live; a file named like a built-in replaces it.",
        "config/templates/documents",
    ),
    _s("assistant.enabled", "bool", "The recorded challenger writes a memo on submission.", "true"),
    _s(
        "assistant.provider",
        "choice",
        "rules is deterministic and offline; claude also asks Anthropic's API.",
        "rules",
        choices=("rules", "claude"),
    ),
    _s("assistant.claude.model", "string", "The Claude model asked.", "claude-opus-5"),
    _s("assistant.claude.effort", "string", "The reasoning effort asked for.", "high"),
    _s(
        "assistant.claude.api_key_env",
        "string",
        "Environment variable holding the API key. Empty: the SDK's own resolution.",
        "",
    ),
    _s("assistant.claude.timeout_seconds", "int", "Per-call timeout.", "300", minimum=1),
    _s(
        "custody.anchor.methods",
        "string",
        "Anchoring methods, comma separated: signature, file, event, rfc3161 (§29.6).",
        "signature,file,event",
    ),
    _s(
        "custody.anchor.file",
        "path",
        "The append-only anchor file. Empty: storage.root/anchors.jsonl.",
        "",
    ),
    _s("custody.anchor.tsa_url", "string", "An RFC 3161 timestamp authority.", ""),
    _s("custody.anchor.tsa_ca_file", "path", "The timestamp authority's CA certificate.", ""),
    _s("custody.anchor.interval_seconds", "duration", "How often to anchor.", "3600", minimum=0),
    _s(
        "workspaces.shadow.sample_rows",
        "int",
        "Rows replayed per dependent warrant in a shadow replay.",
        "5000",
        minimum=1,
    ),
    _s(
        "workspaces.shadow.materiality",
        "float",
        "An absolute output shift above this counts as material.",
        "0.0001",
        minimum=0,
    ),
    _s(
        "workspaces.shadow.budget_rows",
        "int",
        "Row comparisons a namespace's replays may spend in a rolling day. 0: no ceiling.",
        "2000000",
        minimum=0,
    ),
    # -- dependency seams (§13.4) --------------------------------------------
    _s(
        "seams",
        "string",
        "Seam pins: auto, or a backend name to force it. One key per seam (§13.4).",
        "auto",
        family=True,
    ),
)

BY_KEY: dict[str, Setting] = {s.key: s for s in SETTINGS}
FAMILIES: tuple[Setting, ...] = tuple(s for s in SETTINGS if s.family)
_INDEX = re.compile(r"\.\d+$")


def find(key: str) -> Setting | None:
    """The declaration for a configured key, following list indices and families."""
    if key in BY_KEY:
        return BY_KEY[key]
    bare = _INDEX.sub("", key)
    if bare in BY_KEY and BY_KEY[bare].kind == "list":
        return BY_KEY[bare]
    for fam in FAMILIES:
        if key.startswith(fam.key + "."):
            return fam
    return None


def default_for(key: str) -> str | None:
    """The one declared default for a key, or None when the key has no default."""
    setting = find(key)
    return setting.default if setting is not None else None


def unknown_keys(keys: Any) -> list[str]:
    """Configured keys this schema does not declare, sorted."""
    return sorted(k for k in keys if find(k) is None)


def nearest(key: str) -> str | None:
    """The declared key a mistyped one most likely meant."""
    matches = difflib.get_close_matches(key, list(BY_KEY), n=1, cutoff=0.7)
    return matches[0] if matches else None


def refuse_unknown(keys: list[str], *, where: str) -> None:
    """Stop startup on an undeclared key, naming it and what it was probably meant to be."""
    if not keys:
        return
    named = []
    for key in keys:
        guess = nearest(key)
        named.append(f"{key}" + (f" (did you mean '{guess}'?)" if guess else ""))
    raise ConfigurationError(
        f"{len(keys)} setting(s) in {where} are not declared in MAYA's configuration "
        f"schema (maya/config/schema.py): " + "; ".join(named),
        keys=keys,
    )


def required_keys() -> tuple[str, ...]:
    return tuple(s.key for s in SETTINGS if s.required)


__all__ = [
    "SETTINGS",
    "BY_KEY",
    "Setting",
    "find",
    "default_for",
    "unknown_keys",
    "nearest",
    "refuse_unknown",
    "required_keys",
]
