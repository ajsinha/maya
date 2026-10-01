# ADR-013 — SQLite by default, PostgreSQL by configuration, never mixed

**Status:** Accepted, 2026-09-17. **Extended by ADR-022** (revision 2.3): several web
processes need PostgreSQL.

## Context

A quant evaluating MAYA on a laptop should not have to stand up a database server first; a
platform that is hard to try is a platform people route around (§28.1). Production needs
concurrent writers, row locks and a queue that `SKIP LOCKED`s. Supporting both is cheap if
the difference is handled once; it is expensive if some tables live in one and some in the
other, or if a deployment can be half-migrated between them.

## Decision

- **One key decides:** `db.dialect: sqlite | postgresql` (`MAYA_DB_DIALECT`). SQLite is the
  default. A MAYA instance uses exactly one database; nothing is ever split across the two.
- Dialect differences are resolved once, in `maya/persistence/types.py` and the engine
  factory — portable JSON and UUID types, UTC normalisation, `NUMERIC(38,12)` as text on
  SQLite and never as float, WAL and a write mutex on SQLite, row and advisory locks on
  PostgreSQL.
- **`app.environment: prod` on SQLite refuses to start**, naming the key.
- Moving between them is the estate path of ADR-012: export, create the other schema,
  import.

## Consequences

- The suite runs on both: SQLite always, PostgreSQL when `MAYA_TEST_PG_URL` is set, with a
  freshly created schema per test platform. It has passed on PostgreSQL 16, 17 and 18.
  PostgreSQL 14 and 15 — the documented floor — have not been run.
- SQLite is honest about itself: the health page lists it under `degraded` with its
  ceiling, and the prod refusal reads *"app.environment is prod but db.dialect is sqlite.
  SQLite is a single-node, small-team backend (spec §14.1); set db.dialect=postgresql for
  production."*
- A move between dialects copies the database only. `storage.root` — the lake, blobs and
  keys — stays where it is. The procedure is the
  [dialect move runbook](../../operations/runbooks/move-between-sqlite-and-postgresql.md).

## References

- Specification §14, §14.1, §26.2; plan §4.2.
- Code: `maya/config/__init__.py` (`Settings`, `database_url`),
  `maya/persistence/engine.py`, `maya/persistence/types.py`, `config/application.yaml`
  (`db`).
- Tests: `tests/test_foundation.py::test_dialect_switches_by_configuration`,
  `::test_postgres_ddl_uses_native_types`; the whole suite under `MAYA_TEST_PG_URL`
  (`tests/conftest.py`, `build_platform`).
