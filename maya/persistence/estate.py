"""
The estate (§14.3): every table, dialect-neutral, as MAYA's only upgrade path.

There are no migrations. Upgrading, or moving between SQLite and PostgreSQL, is
``export`` from the old database, ``init-db --force`` from the new schema file,
and ``load`` into it. Rows travel as JSON lines per table, in dependency order,
each table hashed in the manifest; a load verifies every hash before writing
and advances every auto-numbered key on PostgreSQL, so the next insert after a
load cannot collide with a loaded row.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import io
import json
import zipfile
from typing import Any

from sqlalchemy import Integer

from maya.core.errors import ValidationFailed
from maya.persistence.models import Base
from maya.persistence.types import utcnow

FORMAT = "maya-estate-v1"


def _enc(v: Any) -> Any:
    if isinstance(v, (dt.datetime, dt.date)):
        return {"$dt": v.isoformat()}
    if isinstance(v, decimal.Decimal):
        return {"$dec": str(v)}
    raise TypeError(type(v).__name__)


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if isinstance(v, dict) and set(v) == {"$dt"}:
            text = v["$dt"]
            out[k] = dt.datetime.fromisoformat(text) if "T" in text else dt.date.fromisoformat(text)
        elif isinstance(v, dict) and set(v) == {"$dec"}:
            out[k] = decimal.Decimal(v["$dec"])
        else:
            out[k] = v
    return out


def export(db: Any, maya_version: str) -> bytes:
    """Dump every table, hashed per table, in dependency order.

    Reads the database as it is, not as this code's schema says it should be: an
    estate is how a database made by an older schema reaches a newer one, so export
    must work exactly when the schema check at startup refuses. Each table is read
    through this code's column types, but only the columns the database really has;
    columns this code has and the database lacks are left out (the load fills them
    with their defaults), and whatever the database has that this code does not is
    named in the manifest's ``not_carried``, never silently lost from view.
    """
    from sqlalchemy import inspect, select

    out = io.BytesIO()
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "maya_version": maya_version,
        "exported_at": utcnow().isoformat(),
        "source_dialect": db.dialect,
        "tables": {},
        "not_carried": {},
    }
    found = inspect(db.engine)
    present = set(found.get_table_names())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z, db.engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in present:
                continue
            have = {c["name"] for c in found.get_columns(table.name)}
            cols = [c for c in table.columns if c.name in have]
            extra = sorted(have - {c.name for c in table.columns})
            if extra:
                manifest["not_carried"][table.name] = extra
            stmt = select(*cols)
            if table.name == "audit_events":
                stmt = stmt.order_by(table.c.seq)
            rows = [dict(r._mapping) for r in conn.execute(stmt)]
            body = "\n".join(json.dumps(r, default=_enc, sort_keys=True) for r in rows)
            z.writestr(f"tables/{table.name}.jsonl", body)
            manifest["tables"][table.name] = {
                "rows": len(rows),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
            }
        for name in sorted(present - set(Base.metadata.tables)):
            manifest["not_carried"][name] = ["(the whole table)"]
        z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return out.getvalue()


def load(db: Any, data: bytes, *, allow_drop: bool = False) -> dict[str, Any]:
    """Load an estate into an empty, freshly created schema; row counts per table.

    Everything that could make the load wrong is checked before a row is written: the
    bundle's hashes, that the target is empty, that the estate's own audit chain links,
    and — unless ``allow_drop`` — that it carries no table or column this code does not
    know (which would otherwise be lost without a word)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format") != FORMAT:
            raise ValidationFailed("Not a MAYA estate bundle")
        tables = {t.name: t for t in Base.metadata.sorted_tables}
        bodies: dict[str, list[dict[str, Any]]] = {}
        for name, meta in manifest["tables"].items():
            body = z.read(f"tables/{name}.jsonl").decode()
            if hashlib.sha256(body.encode()).hexdigest() != meta["sha256"]:
                raise ValidationFailed(f"Table {name} failed its hash check")
            bodies[name] = [_decode(json.loads(line)) for line in body.splitlines() if line]
    dropped = _not_known(bodies, tables)
    if dropped and not allow_drop:
        raise ValidationFailed(
            "The estate carries data this version does not know, which the load would "
            "drop: "
            + "; ".join(f"{t}: {', '.join(c)}" for t, c in sorted(dropped.items()))
            + ". Load with the version that made it, or accept the loss explicitly "
            "(--allow-drop).",
            not_carried=dropped,
        )
    _require_empty(db, tables)
    _require_chain(bodies.get("audit_events", []))
    counts: dict[str, int] = {}
    with db.engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in bodies or table.name == "schema_meta":
                continue
            known = {c.name for c in table.columns}
            rows = [{k: v for k, v in r.items() if k in known} for r in bodies[table.name]]
            if rows:
                _require_carried(table, rows[0])
                conn.execute(table.insert(), rows)
            counts[table.name] = len(rows)
        if db.dialect == "postgresql":
            _advance_sequences(conn)
    return {"tables": counts, "dropped": dropped}


def _not_known(
    bodies: dict[str, list[dict[str, Any]]], tables: dict[str, Any]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, rows in bodies.items():
        if name not in tables:
            out[name] = ["(the whole table)"]
        elif rows:
            extra = sorted(set(rows[0]) - {c.name for c in tables[name].columns})
            if extra:
                out[name] = extra
    return out


def _require_empty(db: Any, tables: dict[str, Any]) -> None:
    from sqlalchemy import func, select

    with db.engine.connect() as conn:
        for name, table in tables.items():
            if name == "schema_meta":
                continue
            n = conn.execute(select(func.count()).select_from(table)).scalar_one()
            if n:
                raise ValidationFailed(
                    f"The database already holds data ({name} has {n} rows); an estate "
                    "loads only into a freshly created schema: run init-db --force first",
                    table=name,
                    rows=n,
                )


def _require_chain(rows: list[dict[str, Any]]) -> None:
    """The estate's audit chain must link before any of it is written."""
    from maya.persistence.repositories.special import GENESIS, audit_digest

    prev = GENESIS
    for row in sorted(rows, key=lambda r: r["seq"]):
        if row.get("prev_hash") != prev or audit_digest(prev, row) != row.get("hash"):
            raise ValidationFailed(
                "The estate's audit chain does not verify; nothing was loaded", broken_at=row["seq"]
            )
        prev = row["hash"]


def _require_carried(table: Any, row: dict[str, Any]) -> None:
    """A column the new code added takes its default on load; a required column with no
    default cannot, and is named here rather than failing inside the database."""
    missing = [
        c.name
        for c in table.columns
        if c.name not in row
        and not c.nullable
        and c.default is None
        and c.server_default is None
        and c.autoincrement is not True
    ]
    if missing:
        raise ValidationFailed(
            f"Table {table.name}: the estate has no values for required column(s) "
            f"{', '.join(missing)}, and the schema gives them no default. Give them a "
            "default in the model, or fill them in the export, before loading.",
            table=table.name,
            columns=missing,
        )


def _advance_sequences(conn: Any) -> None:
    """Explicit key values leave a SERIAL/IDENTITY sequence behind; move each past its max."""
    for table in Base.metadata.sorted_tables:
        for col in table.primary_key.columns:
            if isinstance(col.type, Integer) and col.autoincrement in (True, "auto"):
                # names from the ORM metadata, never input
                conn.exec_driver_sql(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', '{col.name}'), "  # nosec B608
                    f"COALESCE((SELECT MAX({col.name}) FROM {table.name}), 1))"
                )
