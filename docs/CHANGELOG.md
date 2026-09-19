# Changelog

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

See the README's *What's shipped* and *Not yet* sections for the precise boundary.
