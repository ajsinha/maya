# ADR-023 — The estate export reads the database as it is

**Status:** Accepted, revision 2.3 (2026-09-19). Amends ADR-012.

## Context

The estate round trip — export, `init-db --force`, import — is MAYA's only upgrade path
(ADR-012). As first built, the export ran through a platform that checked the schema identity
first. That check is exactly what refuses a database made by an older schema, so the export
refused precisely when an upgrade needed it: the one door out of a schema mismatch was
locked by the schema mismatch.

## Decision

`admin export-estate` reads straight from the database, with no platform and no schema check.
Each table the code knows is read through the code's column types, but only for the columns
the database really has. On import, a column the new code added and the estate lacks takes
its default. **Nothing is lost from view**: a column or table the database has and the new
code does not is named in the bundle manifest's `not_carried`. A required column with no
default that the estate cannot fill is refused by name, before the database is touched:

```text
Table <table>: the estate has no values for required column(s) <columns>, and the schema
gives them no default. Give them a default in the model, or fill them in the export,
before loading.
```

## Consequences

- The export works with the new version already installed, which is the only moment it is
  needed.
- `not_carried` is information, not recovery. Data in it is not in the new database; whoever
  runs the upgrade has to read the manifest before discarding the old one. The export command
  does not print it.
- A release that adds a required column without a default breaks every upgrade into it. The
  refusal says so rather than failing inside the database — and the refusal comes *after*
  `init-db --force` has emptied the target, so the old database must be kept until the import
  has succeeded. The [schema rebuild runbook](../runbooks/schema-rebuild.md) is written around
  that.

## References

- Specification §14.3 (revision 2.3 note).
- Code: `maya/persistence/estate.py` (`export`, `load`, `_require_carried`),
  `maya/cli/admin.py` (`admin_export_estate`).
- Tests: `tests/test_workflow_and_estate.py` —
  `test_a_database_from_another_schema_still_exports_and_loads`,
  `test_a_required_column_the_estate_cannot_fill_is_named`.
