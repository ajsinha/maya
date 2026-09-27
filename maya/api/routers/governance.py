"""
Model governance: the findings register, materiality tiers, periodic review and ongoing
monitoring.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas_governance as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["governance"])


@router.get("/governance")
def overview(me: Principal = Me, plat: Any = Plat) -> Response:
    """Every model the caller may read, with its tier, next review and open findings."""
    return ok(plat.governance.overview(me))


@router.get("/governance/inventory")
def inventory(
    format: str = "csv", framework: str = "sr11-7", me: Principal = Me, plat: Any = Plat
) -> Response:
    """The model inventory as a file, in an SR 11-7 or SS1/23 aligned layout (or MAYA's own
    keys with ``framework=maya``). Only models the caller may read; the file says how many
    were left out."""
    out = plat.inventory.export(me, format, framework)
    return Response(
        out["data"],
        media_type=out["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"'},
    )


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


@router.get("/challenges", tags=["governance"])
def challenges(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.challenges.list(me))


@router.post("/challenges", status_code=201, tags=["governance"])
def create_challenge(body: s.ChallengeIn, me: Principal = Me, plat: Any = Plat) -> Response:
    """Score a champion and a challenger on their shared escrowed holdout and compare them."""
    data = body.model_dump()
    return ok(plat.challenges.create(me, data.pop("champion"), data.pop("challenger"), **data), 201)


@router.get("/challenges/{challenge_id}", tags=["governance"])
def challenge(challenge_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.challenges.get(me, challenge_id))


@router.post("/challenges/{challenge_id}/decision", tags=["governance"])
def decide_challenge(
    challenge_id: str, body: s.DecisionIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.challenges.decide(me, challenge_id, body.decision, body.rationale))


@router.get("/warrants/training/{warrant_id}/evidence", tags=["warrants"])
def evidence(warrant_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """Fairness and explainability evidence computed on this warrant's holdout."""
    return ok(plat.evidence.list(me, warrant_id))


@router.post("/warrants/training/{warrant_id}/evidence", status_code=201, tags=["warrants"])
def compute_evidence(
    warrant_id: str, body: s.EvidenceIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    """Segment metrics and permutation importance on the holdout; counts as one attempt."""
    return ok(plat.evidence.compute(me, warrant_id, **body.model_dump()), 201)


@router.post("/warrants/training/{warrant_id}/dispatch", status_code=201, tags=["warrants"])
def dispatch_training(
    warrant_id: str, body: s.DispatchIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    """A job definition for your own compute (Kubernetes, SageMaker), a signed manifest and a
    one-day key. MAYA runs nothing."""
    return ok(plat.training_ops.dispatch(me, warrant_id, **body.model_dump()), 201)


@router.post("/warrants/training/{warrant_id}/refit", status_code=201, tags=["warrants"])
def reference_refit(
    warrant_id: str, body: s.RefitIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    """MAYA's own least-squares fit on the training split, compared with a parameter set."""
    return ok(plat.training_ops.refit(me, warrant_id, parameter_set_id=body.parameter_set_id), 201)
