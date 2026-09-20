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
| [Orphaned pin partitions](orphaned-pin-partitions.md) | The lake is bigger than the pins in it: fragments no sealed pin references |
| [Delta small-file explosion](delta-small-files.md) | Reads slow down while row counts do not, or a lake table is thousands of tiny files |
| [Database failover](database-failover.md) | PostgreSQL has gone away, or a standby has been promoted |
| [A suspended execution warrant](suspended-execution-warrant.md) | A consumer is refused with `warrant_suspended` (HTTP 423) |
| [SSO outage](sso-outage.md) | The identity provider is down or misbehaving, or sign-out does not behave as expected |
| [Suspected sandbox escape](sandbox-escape.md) | User-supplied Python may have got out of its jail, or the sandbox tier has fallen |
| [Storage quota exhaustion](quota-exhaustion.md) | The lake is filling up, one namespace is consuming it, or the job queue is shedding |
| [Default-password remediation](default-password.md) | MAYA refuses to start on the shipped admin password, or a running instance still has it |
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
| Beside the database | `admin init-db`, `admin export-estate`, `admin import-estate`, `admin record-drill`, `admin drills` — no flags | Rebuilding a database, and recording a restore drill on the instance that was backed up. These open the database directly and never go through a server, because they must work exactly when the platform refuses to start. **Stop MAYA first** for the three that rebuild; the two drill commands only read and append, and `MAYA_USER` names who is acting. |
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
authority. Each runbook says at the end of its verification section which of its own
commands were run and which were not, so a command you are about to trust at two in the
morning is not one nobody has ever typed.

## Alerts

§20 asks that "each SLO has an alert with a runbook link", and
[`config/prometheus/maya-slo.rules.yml`](../../config/prometheus/maya-slo.rules.yml) is that
file: recording rules for the four objectives and alerts that each carry a `runbook_url`
pointing into this directory. Load it beside your Prometheus configuration:

```yaml
rule_files:
  - /etc/prometheus/maya-slo.rules.yml
```

`tests/test_slo_rules.py` fails if an alert names a runbook that does not exist, or an
expression names a metric MAYA does not export — so a renamed metric or a moved runbook breaks
the build rather than the alert. Every threshold in the file is a starting point from a
laptop-sized estate and is meant to be edited. Prometheus itself, and where the alerts go, are
still yours.

## What these runbooks do not cover

The nine runbooks §20 asks for are all here, and six more beside them. What is not covered is
narrower, and named here so nobody assumes otherwise:

- **Nothing collects orphaned fragments on a schedule.** §29.3's collector is built and is
  the supported path (`maya admin collect-fragments`), but it runs only when an administrator
  asks, its removal is a Delta remove rather than a delete, and the disk frees at the next
  vacuum — see [orphaned partitions](orphaned-pin-partitions.md), which also keeps the
  unsupported manual rewrite for the case the collector cannot reach.
- **Pin tables cannot be compacted.** They are partitioned one file per fragment, so the
  [small-files](delta-small-files.md) runbook's lever there is the fragment size, for new pins
  only.
- **A storage quota is not an export quota.** `quota_bytes` is enforced on the way to a pin,
  twice ([quota exhaustion](quota-exhaustion.md)), but §21.2's per-namespace export quotas and
  manifest watermarking are not built, and there is no cold storage tier to move quiet pins
  into.
- **MAYA has no database failover of its own**, and every PostgreSQL command in
  [that runbook](database-failover.md) is marked as not exercised: no server was available when
  it was written.
- **The sandbox is tested against a fixed list of attacks.** §26 puts an external security
  review out of scope, so [suspected escape](sandbox-escape.md) is measurement against that
  list, not a proof.
- **RPO and RTO have never been measured** at production size (§20 states 5 minutes and 1 hour).
  The [restore drill](restore-drill.md) records a duration for a tiny estate only.
