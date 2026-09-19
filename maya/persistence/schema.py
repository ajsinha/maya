"""
Schema generation, identity and creation (§14.3). No migration framework.

The DDL for each dialect is *generated* from ``Base.metadata`` and shipped as
``schema/sqlite.sql`` and ``schema/postgresql.sql``. ``tools/ci/gen_schema.py``
regenerates both and fails the build on any difference (SC-15).

Creating a database executes the shipped file for the configured dialect.
The hash of the generated DDL is stamped into ``schema_meta``; on startup the
stamp is compared with what the running code generates and a mismatch refuses
to start, naming the export → init-db → import commands.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import functools
import hashlib
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from maya.core.errors import ConfigurationError
from maya.persistence.models import Base

SCHEMA_DIR = Path(__file__).parent / "schema"
DIALECTS = {"sqlite": sqlite.dialect(), "postgresql": postgresql.dialect()}

# Append-only enforcement for the audit table, per backend (§14.2, §19).
_APPEND_ONLY = {
    "sqlite": [
        "CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
        "CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
    ],
    "postgresql": [
        "CREATE OR REPLACE FUNCTION maya_audit_append_only() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql",
        "CREATE TRIGGER audit_events_no_update BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION maya_audit_append_only()",
    ],
}

HEADER = (
    "-- ==========================================================================\n"
    "-- MAYA schema for {dialect} — GENERATED from the SQLAlchemy metadata in\n"
    "-- maya/persistence/models/. DO NOT EDIT BY HAND: regenerate with\n"
    "--     python tools/ci/gen_schema.py\n"
    "-- and CI fails the build on any drift (spec §14.3, SC-15).\n"
    "-- schema-hash: {digest}\n"
    "-- ==========================================================================\n\n"
)


def statements(dialect_name: str) -> list[str]:
    """Every DDL statement for a dialect, in dependency order."""
    dialect = DIALECTS[dialect_name]
    out: list[str] = []
    for table in Base.metadata.sorted_tables:
        out.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            out.append(str(CreateIndex(index).compile(dialect=dialect)).strip())
    out.extend(_APPEND_ONLY[dialect_name])
    return out


def ddl_body(dialect_name: str) -> str:
    return "".join(stmt + ";\n\n" for stmt in statements(dialect_name))


@functools.lru_cache(maxsize=None)
def schema_hash(dialect_name: str) -> str:
    """The digest of the schema this code defines — fixed for the life of the process."""
    return hashlib.sha256(ddl_body(dialect_name).encode("utf-8")).hexdigest()


def render(dialect_name: str) -> str:
    """The full file content that ships as schema/<dialect>.sql."""
    return HEADER.format(dialect=dialect_name, digest=schema_hash(dialect_name)) + \
        ddl_body(dialect_name)


def schema_file(dialect_name: str) -> Path:
    return SCHEMA_DIR / f"{dialect_name}.sql"


def write_files() -> list[Path]:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in DIALECTS:
        path = schema_file(name)
        path.write_text(render(name), encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def drift() -> dict[str, bool]:
    """True per dialect when the shipped file differs from the generated one."""
    out = {}
    for name in DIALECTS:
        path = schema_file(name)
        shipped = path.read_text(encoding="utf-8") if path.exists() else ""
        out[name] = shipped != render(name)
    return out


def _file_statements(dialect_name: str) -> list[str]:
    body = schema_file(dialect_name).read_text(encoding="utf-8")
    lines = [ln for ln in body.splitlines() if not ln.startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";\n\n") if s.strip()]


def create_all(engine: Engine, *, force: bool = False) -> str:
    """Create the schema from the shipped .sql file for the engine's dialect."""
    name = engine.dialect.name
    if drift()[name]:
        raise ConfigurationError(
            f"schema/{name}.sql does not match the ORM metadata. Regenerate it with "
            f"'python tools/ci/gen_schema.py' before creating a database.")
    with engine.begin() as conn:
        if force:
            _drop_everything(conn, name)
        for stmt in _file_statements(name):
            conn.exec_driver_sql(stmt)
        digest = schema_hash(name)
        conn.execute(text("INSERT INTO schema_meta (key, value) VALUES ('schema_hash', :v)"),
                     {"v": digest})
        conn.execute(text("INSERT INTO schema_meta (key, value) VALUES ('dialect', :v)"),
                     {"v": name})
    return digest


def _drop_everything(conn, name: str) -> None:  # type: ignore[no-untyped-def]
    if name == "postgresql":
        conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")
        return
    # Children before parents, so foreign keys hold at every step, then anything
    # left over from an older schema.
    for table in reversed(Base.metadata.sorted_tables):
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table.name}"')
    for (tbl,) in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'").fetchall():
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{tbl}"')


def stored_hash(engine: Engine) -> str | None:
    """The schema hash stamped at creation, or None for an empty database."""
    with engine.connect() as conn:
        try:
            row = conn.execute(text(
                "SELECT value FROM schema_meta WHERE key='schema_hash'")).fetchone()
        except Exception:  # noqa: BLE001 - absent table means an empty database
            conn.rollback()
            return None
    return row[0] if row else None


def verify_identity(engine: Engine) -> str:
    """Refuse to run against a database whose schema is not the code's schema."""
    expected = schema_hash(engine.dialect.name)
    found = stored_hash(engine)
    if found is None:
        raise ConfigurationError("The database has no MAYA schema. Run "
                                 "'python -m maya.cli admin init-db'.")
    if found != expected:
        raise ConfigurationError(
            "Schema mismatch: the database was created from a different schema "
            f"(stored {found[:12]}, code expects {expected[:12]}). MAYA has no "
            "migrations. Rebuild with:\n"
            "  python -m maya.cli admin export-estate --out estate.mayabundle\n"
            "  python -m maya.cli admin init-db --force\n"
            "  python -m maya.cli admin import-estate --in estate.mayabundle",
            stored=found, expected=expected)
    return found
