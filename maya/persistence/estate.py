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


def export(db: Any, uow_factory: Any, maya_version: str) -> bytes:
    """Dump every table, hashed per table, in dependency order."""
    out = io.BytesIO()
    manifest: dict[str, Any] = {"format": FORMAT, "maya_version": maya_version,
                                "exported_at": utcnow().isoformat(),
                                "source_dialect": db.dialect, "tables": {}}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z, uow_factory() as uow:
        for table in Base.metadata.sorted_tables:
            repo = uow.repo(table.name)
            rows = repo.list(order_by=["seq"]) if table.name == "audit_events" else repo.list()
            body = "\n".join(json.dumps(r, default=_enc, sort_keys=True) for r in rows)
            z.writestr(f"tables/{table.name}.jsonl", body)
            manifest["tables"][table.name] = {"rows": len(rows),
                                              "sha256": hashlib.sha256(body.encode()).hexdigest()}
        z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return out.getvalue()


def load(db: Any, data: bytes) -> dict[str, int]:
    """Load an estate into an empty, freshly created schema; row counts per table."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format") != FORMAT:
            raise ValidationFailed("Not a MAYA estate bundle")
        counts: dict[str, int] = {}
        with db.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if table.name not in manifest["tables"]:
                    continue
                body = z.read(f"tables/{table.name}.jsonl").decode()
                if hashlib.sha256(body.encode()).hexdigest() != \
                        manifest["tables"][table.name]["sha256"]:
                    raise ValidationFailed(f"Table {table.name} failed its hash check")
                if table.name == "schema_meta":
                    continue
                rows = [_decode(json.loads(line)) for line in body.splitlines() if line]
                if rows:
                    conn.execute(table.insert(), rows)
                counts[table.name] = len(rows)
            if db.dialect == "postgresql":
                _advance_sequences(conn)
    return counts


def _advance_sequences(conn: Any) -> None:
    """Explicit key values leave a SERIAL/IDENTITY sequence behind; move each past its max."""
    for table in Base.metadata.sorted_tables:
        for col in table.primary_key.columns:
            if isinstance(col.type, Integer) and col.autoincrement in (True, "auto"):
                conn.exec_driver_sql(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', '{col.name}'), "
                    f"COALESCE((SELECT MAX({col.name}) FROM {table.name}), 1))")
