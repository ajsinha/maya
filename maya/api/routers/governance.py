"""
Model governance: the findings register, materiality tiers, periodic review and ongoing
monitoring.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["governance"])


@router.get("/governance")
def overview(me: Principal = Me, plat: Any = Plat) -> Response:
    """Every model the caller may read, with its tier, next review and open findings."""
    return ok(plat.governance.overview(me))


@router.get("/governance/findings")
def findings(
    model: str | None = None, state: str | None = None, me: Principal = Me, plat: Any = Plat
) -> Response:
    """The register. ``state=active`` is everything not yet closed or accepted."""
    return ok(plat.governance.findings(me, model, state))


@router.post("/governance/findings", status_code=201)
def raise_finding(body: s.FindingIn, me: Principal = Me, plat: Any = Plat) -> Response:
    data = body.model_dump(exclude_none=True)
    return ok(
        plat.governance.raise_finding(
            me, data.pop("model"), data.pop("title"), data.pop("severity"), **data
        ),
        201,
    )


@router.get("/governance/findings/{finding_id}")
def finding(finding_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.governance.finding(me, finding_id))


@router.post("/governance/findings/{finding_id}/move")
def move_finding(
    finding_id: str, body: s.FindingMoveIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.governance.move_finding(me, finding_id, body.action, body.note))


@router.get("/governance/models/{namespace}/{name}")
def profile(namespace: str, name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """Tier and its drivers, review schedule, findings and review history for one model."""
    return ok(plat.governance.profile(me, f"{namespace}/{name}"))


@router.put("/governance/models/{namespace}/{name}")
def set_profile(
    namespace: str, name: str, body: s.GovernanceProfileIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.governance.set_profile(me, f"{namespace}/{name}", **body.model_dump()))


@router.post("/governance/models/{namespace}/{name}/reviews", status_code=201)
def record_review(
    namespace: str, name: str, body: s.ReviewIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        plat.governance.record_review(me, f"{namespace}/{name}", body.outcome, body.note), 201
    )


@router.post("/governance/sweep")
def sweep(me: Principal = Me, plat: Any = Plat) -> Response:
    """Suspend the live warrants of every model whose periodic review is overdue."""
    return ok(plat.governance.sweep(me))


@router.get("/monitoring", tags=["monitoring"])
def monitoring(days: int = 30, me: Principal = Me, plat: Any = Plat) -> Response:
    """Every sealed execution warrant the caller may read, graded ok, watch or breach."""
    return ok(plat.monitoring.overview(me, days))


@router.get("/monitoring/warrants/{ew_id}", tags=["monitoring"])
def monitoring_warrant(
    ew_id: str, days: int = 90, me: Principal = Me, plat: Any = Plat
) -> Response:
    """One warrant's reported executions read as series: volume, null rates, ranges, PSI."""
    return ok(plat.monitoring.warrant(me, ew_id, days))
