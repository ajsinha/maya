# ADR-012 — No migrations: two generated schema files, everything through SQLAlchemy

**Status:** Accepted, 2026-09-17. **Amended by ADR-023** (revision 2.3): the export reads
the database as it is, so the upgrade path works across the schema change that needs it.

## Context

A migration framework is a second description of the schema — a revision graph of
`upgrade()` and `downgrade()` pairs — that has to agree with the first. It fails in the
familiar ways: a half-applied upgrade, a `downgrade()` that was never run, two branches that
each added a column, and a production database whose shape is whatever the history of
applied revisions made it, which nobody can read in one place. MAYA has two dialects, which
doubles every one of those.

## Decision

**No migration framework and no migration history.** The single source of truth is the
SQLAlchemy metadata in `maya/persistence/models/`. `tools/ci/gen_schema.py` generates
`maya/persistence/schema/sqlite.sql` and `maya/persistence/schema/postgresql.sql` from it;
neither is ever edited by hand, and the build fails on any difference. A database is created
by executing the shipped file for its dialect, and the hash of the generated DDL is stamped
into `schema_meta`. At startup MAYA compares the stamp with the running code's hash and
**refuses to start** on a mismatch, naming the three commands that rebuild it:

```text
Schema mismatch: the database was created from a different schema (stored <12 hex>, code
expects <12 hex>). MAYA has no migrations. Rebuild with:
  python -m maya.cli admin export-estate --out estate.mayabundle
  python -m maya.cli admin init-db --force
  python -m maya.cli admin import-estate --in estate.mayabundle
```

## Consequences

- There is exactly one way a database can be shaped, and it is a file you can read.
- **The bill arrives with production data.** Every schema change is a maintenance window
  proportional to the estate: export, drop, recreate, import. There is no in-place `ALTER`
  path, and none will be built. The procedure is the
  [schema rebuild runbook](../runbooks/schema-rebuild.md).
- That path is the only upgrade path, so it is tested in the suite — a round trip, a
  database from another schema, a required column the estate cannot fill — rather than
  written when first needed.
- Feature data is unaffected: pins in the lake are immutable, content-addressed and
  independent of the metadata schema, so a rebuild never touches a byte of Delta.
- Specification §20 still describes "an expand-migrate-contract pattern" for upgrades.
  That sentence predates this decision and contradicts §14.3; §14.3 is the one the code
  follows.

## References

- Specification §14.3, §20; plan §4.2, §4.3.
- Code: `maya/persistence/schema.py` (`create_all`, `verify_identity`),
  `maya/persistence/schema/`, `tools/ci/gen_schema.py`, `maya/cli/__main__.py`
  (`admin init-db`).
- Tests: `tests/test_foundation.py::test_shipped_schema_files_match_the_metadata`,
  `::test_hand_edit_is_detected`;
  `tests/test_api_and_gates.py::test_schema_drift_gate_fails_after_a_hand_edit`;
  `tests/test_workflow_and_estate.py::test_schema_mismatch_refuses_to_start`,
  `::test_estate_round_trip_and_audit_tamper_detection`.
