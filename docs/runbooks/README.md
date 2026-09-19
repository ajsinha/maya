# Runbooks

These are for whoever is on the hook when MAYA misbehaves — an administrator, a `techops`
engineer, the person restoring it at two in the morning. Each runbook starts from what you
see (the symptoms), gives the commands that tell you what is actually wrong, the steps that
fix it, how to prove it is fixed, and what the procedure does **not** reach. Specification §20
requires that runbooks ship with the product, not after it; these are those runbooks.

They are procedures, not explanations. The why of each subsystem is in the
[operations guide](../../maya/web/guides/operations-guide.md) (also in the product, under
*Help → Guides*), the [security guide](../../maya/web/guides/security-guide.md) and the
[architecture decision records](../adr/README.md).

## Index

| Runbook | Use it when |
|---|---|
| [Schema rebuild](schema-rebuild.md) | MAYA refuses to start with *Schema mismatch*, or you are upgrading to a version whose schema changed |
| [Moving between SQLite and PostgreSQL](move-between-sqlite-and-postgresql.md) | Outgrowing SQLite, or taking a copy of production to a laptop |
| [`maya_delta` backend fallback](maya-delta-backend-fallback.md) | The banner or health page shows `maya_delta pure`, the lake refuses a table by feature name, or you need to pin a backend |
| [Integrity drift](integrity-drift.md) | `verify-integrity` exits 1, or an `integrity_drift` notification arrives |
| [Audit chain break and custody anchors](audit-chain-and-custody.md) | The chain does not verify, custody verification says `TAMPERING`, or anchoring is refused |
| [Stuck or failed jobs and pins](stuck-or-failed-jobs-and-pins.md) | A job sits `running` or `queued`, dead-letters, or a pin is stuck `materializing` or `failed` |
| [A suspended execution warrant](suspended-execution-warrant.md) | A consumer is refused with `warrant_suspended` (HTTP 423) |
| [SSO outage](sso-outage.md) | The identity provider is down or misbehaving, or sign-out does not behave as expected |
| [Restore drill](restore-drill.md) | Quarterly, and after any change to how backups are taken |

## Conventions every runbook uses

**Which Python.** `python` means the interpreter of MAYA's own environment — activate the
virtualenv, or write `.venv/bin/python` (`.venv\Scripts\python.exe` on Windows).

**Where commands run.** From the repository root of the MAYA installation, with the same
environment the server runs with — the same `MAYA_HOME`, `MAYA_DB_DIALECT`, `MAYA_PG_*` and
configuration file. The CLI reads `config/application.yaml` relative to the working
directory; elsewhere, pass `--config /path/to/application.yaml`. Any setting can be given on
the command line as `--section.key=value`, exactly as for `run_maya_web.py`.

**Which CLI mode.** `python -m maya.cli` has three ways to reach MAYA, and they are not
interchangeable:

| Mode | How | Use for |
|---|---|---|
| Beside the database | `admin init-db`, `admin export-estate`, `admin import-estate` — no flags | Rebuilding a database. These open the database directly and never start a platform, because they must work exactly when the platform refuses to start. **Stop MAYA first.** |
| Remote | `MAYA_URL` and `MAYA_API_KEY` in the environment (or `--profile`) | Everything else, against a running server. Needs an administrator's or `techops` key. |
| In process | `--local`, with `MAYA_USER` and `MAYA_PASSWORD` | A server that is not running. Signs in with a password, so it needs a database account — it is refused when `auth.mode` is `sso`, and by an account whose second factor is pending. **It starts the job workers, the webhook dispatcher and the scheduler**, so never use it on a copy of production without disarming webhooks first (see the [restore drill](restore-drill.md)). |

**Exit codes.** 0 success, 1 MAYA refused (the reason is on stderr, as
`maya: <ErrorType>: <message>`), 2 usage error, 3 network error. `admin verify-integrity`
exits 1 on any drift or a broken chain, so it can gate a script.

**Refusals are quoted whole.** Where a runbook quotes a message, it is the exact text the code
produces, with placeholders in angle brackets. If what you see differs, the runbook is out of
date — say so.

**Commands that were run.** Every command in these runbooks was run against a throwaway
`MAYA_HOME` on SQLite when they were written, except where a runbook marks one as not
exercised — PostgreSQL commands and anything needing a real identity provider or timestamp
authority.

## What these runbooks do not cover

Specification §20 lists runbooks these do not yet include, and they are named here so nobody
assumes otherwise:

- **Orphaned pin partitions** — only in part: the [jobs and pins](stuck-or-failed-jobs-and-pins.md)
  runbook covers the orphan fragments a failed pin leaves; MAYA reports them and never deletes
  them, and there is no supported command to collect them.
- **Delta small-file explosion** — lake maintenance (compaction and vacuum) is described in the
  operations guide; there is no runbook for diagnosing it.
- **Database failover** — not written. MAYA has no failover of its own; it is whatever the
  PostgreSQL deployment provides.
- **Sandbox escape suspicion** — not written.
- **Storage quota exhaustion** — not written.
- **Default-password remediation** — not written. Outside `dev`, MAYA refuses to start while
  the bootstrap admin has the default password; the banner and health page say so.

There are no alerts wired to these runbooks: §20's "each SLO has an alert with a runbook link"
is not built. MAYA exposes the metrics (`/metrics`); the alerting is yours.
