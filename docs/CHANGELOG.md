# Changelog

## 0.2.0 — 2026-09-19

Built from specification revision 2.3. The SDK's own version (`CLIENT_VERSION`) is
0.2.0 too; 0.1 clients remain accepted.

**Using MAYA**

- A new shell: top navigation with mega-menu panels, and a card-based help centre with
  four tutorials and thirteen full-reference guides whose examples were run.
- Spreadsheet import lifts an Excel formula graph into the IR. The lift is checked cell
  by cell against the workbook's cached results, and against LibreOffice Calc.
- A Python source driver: a reviewed producer function, run in the sandbox on each pull.
- The assistant as a recorded challenger on every review. Rules are the default;
  Claude is opt-in.
- The workbench shows the 50 most recently changed drafts. Feature and feature-set
  lists take a `state` filter on the latest version.
- The owner of a scratch namespace pins directly. Before, every scratch pin was refused.

**Security**

- SAML 2.0 sign-in, with signed requests and single logout in both directions. An IdP's
  logout request is accepted only when signed. WebAuthn security keys as a second factor.
- Execution warrants: a copy issued for offline use is labelled `unattested`, on the
  copy and on the warrant.
- Defects found by test hardening were fixed, including code execution in
  server-side bundle verification, and review comments and history open to any
  signed-in user rather than to those who may read the object.

**Evidence**

- Bundles re-execute composite models of closed-form members. `maya.sdk.offline`
  evaluates them from the signed member IRs.
- SDK record/replay for both clients; `maya.sdk.offline(bundle)`; real LaTeX builds with
  Tectonic.

**Operations and performance**

- `server.workers`: several web processes on one node over PostgreSQL. On Linux each
  has its own `SO_REUSEPORT` socket. The setting is refused over SQLite.
- Catalog lists check access and load versions in bulk; page latency fell 10–60×.
  Search loads its hits in bulk.
- The health check caches its expensive parts: the audit-chain walk, the default
  password check and the schema digest.
- maya_delta compaction and vacuum on both backends, run daily over every lake table.
- The estate export reads the database as it is, so it works across a schema change.
- Measured: SC-5, SC-4 and 100k-object search pass. SC-3 is close but not met.
  See `docs/BENCHMARKS.md`.
- The suite runs on SQLite and on PostgreSQL 16, 17 and 18.

**Fixed**

- A feature pin whose resolution or lake write failed unexpectedly stayed
  "materializing" for ever. It now ends `failed`.
- Shadow replay could not find execution warrants.
- The event `type` filter matched anywhere; it is now a prefix.
- Review aging ignored namespace policies.
- The CLI refused `--key=value` setting overrides.
- Removed unused configuration keys: `auth.session.token_ttl_minutes` and
  `featureset.pin.materialize`. `server.workers`, also unused before, now does
  something (above). `health.audit_verify_seconds` is new.
- A stray pasted sentence was removed from a configuration comment.

## 0.1.0 — 2026-09-19

First end-to-end build from specification revision 2.1. The version authority is
`maya/core/version.py`; this file is the narrative.

- The spine, working end to end through the UI, API, SDK and CLI: features → feature
  sets → models → training warrants → parameter sets → execution warrants → evidence
  bundles.
- Bitemporal features and content-addressed pins shared as fragments (§29.1, §29.3).
- `maya_delta`, with a native (delta-rs) backend and a pure-Python backend; each reads the other's tables.
- SQLite and PostgreSQL from two generated schema files, switched by `db.dialect`; no
  migration framework; estate export → recreate → import.
- Workflow policy as data, edited in the UI, governed, projected to YAML.
- Gate ladder in `tools/ci/`.

See the README's *Status* and *Not yet* sections for the precise boundary.
