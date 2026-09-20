"""
Retention, archives, restore drills and log levels (§7.3, §20, §29.3).

Separate from ``admin`` because that module reached the gate's limit on public names, and
because these are the operator's own surface: what the estate holds, what it has let go of,
and what it remembers about the last time somebody proved a backup worked.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter()


@router.get("/system/cold-pins", tags=["ops"])
def cold_pins(days: int | None = None, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.retention.cold_report(me, days))


@router.post("/system/pins/{pin_id}/archive", tags=["ops"])
def archive_pin(
    pin_id: str, table: str = "feature_pins", me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.retention.archive(me, pin_id, table=table))


@router.get("/system/pins/{pin_id}/archive", tags=["ops"])
def read_pin_archive(
    pin_id: str, table: str = "feature_pins", me: Principal = Me, plat: Any = Plat
) -> Response:
    """The archive's manifest, and whether its rows still hash to the sealed pin. The rows
    themselves are not returned here: an archive is read back to a file, by the CLI."""
    out = plat.retention.restore(me, pin_id, table=table)
    rows = out.pop("table", None)
    return ok({**out, "rows": rows.num_rows if rows is not None else 0})


@router.post("/system/fragments/collect", tags=["ops"])
def collect_fragments(dry_run: bool = True, me: Principal = Me, plat: Any = Plat) -> Response:
    """Remove fragments no pin references (§29.3). A dry run by default: an operator should
    see the list before it goes."""
    return ok(plat.retention.collect(me, dry_run=dry_run))


@router.get("/system/extensions", tags=["ops"])
def extensions(me: Principal = Me, plat: Any = Plat) -> Response:
    """§25's extension points, what is registered at each, and which notification channels
    are configured."""
    return ok(plat.ops.extensions(me))


@router.get("/system/restore-drills", tags=["ops"])
def restore_drills(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok({"status": plat.ops.restore_drill_status(me), "drills": plat.ops.restore_drills(me)})


@router.post("/system/restore-drills", tags=["ops"])
def record_restore_drill(body: s.RestoreDrillIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.record_restore_drill(me, **body.model_dump(exclude_none=True)), 201)


@router.put("/system/log-level", tags=["ops"])
def set_log_level(body: s.LogLevelIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.set_log_level(me, body.module, body.level))
