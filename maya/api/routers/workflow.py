"""
Workflow endpoints (§10): queue, policies, comments, history, campaigns.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok, parse_date
from maya.security.authz import Principal

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/queue")
def queue(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.queue(me))


@router.get("/aging")
def aging(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.aging())


@router.get("/break-glass")
def break_glass(days: int = 31, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.break_glass_report(days))


@router.get("/policies")
def policies(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.policies())


@router.get("/policies/{policy_id}")
def policy(policy_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.policy(policy_id))


@router.get("/policies/{policy_id}/yaml", response_class=PlainTextResponse)
def policy_yaml(policy_id: str, me: Principal = Me, plat: Any = Plat) -> str:
    return plat.workflow_svc.export_yaml(policy_id)


@router.post("/policies", status_code=201)
def draft_policy(body: s.PolicyIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.draft_policy(me, body.object_type, body.policy, scope=body.scope,
                                             note=body.note), 201)


@router.post("/policies/import", status_code=201)
def import_policy(body: s.PolicyYamlIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.import_yaml(me, body.object_type, body.yaml, scope=body.scope), 201)


@router.post("/policies/validate")
def validate_policy(body: s.PolicyIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok({"errors": plat.workflow_svc.validate(body.policy),
               "impact": plat.workflow_svc.preview(body.object_type, body.policy)})


@router.post("/policies/{policy_id}/activate")
def activate_policy(policy_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.activate(me, policy_id))


@router.get("/population/{object_type}")
def population(object_type: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.population(object_type))


@router.get("/history")
def history(object_type: str, object_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.history(object_type, object_id, me))


@router.get("/comments")
def comments(object_type: str, object_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.comments(object_type, object_id, me))


@router.post("/comments", status_code=201)
def add_comment(body: s.CommentIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.comment(me, body.object_type, body.object_id, body.body,
                                        blocking=body.blocking, anchor=body.anchor), 201)


@router.post("/comments/{comment_id}/resolve")
def resolve_comment(comment_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.resolve_comment(me, comment_id))


@router.post("/transitions")
def transition(body: s.GenericTransitionIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.dispatch_transition(me, body.object_type, body.object_id, body.transition,
                                       rationale=body.rationale, force=body.force))


@router.get("/campaigns")
def campaigns(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.campaigns())


@router.post("/campaigns", status_code=201)
def run_campaign(body: s.CampaignIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.run_campaign(me, body.name, body.transition, body.items,
                                             body.rationale), 201)


@router.get("/delegations")
def delegations(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.delegations(me))


@router.post("/delegations", status_code=201)
def delegate(body: s.DelegationIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.delegate(
        me, to=body.to, starts_on=parse_date(body.starts_on, "starts_on"),
        ends_on=parse_date(body.ends_on, "ends_on"), object_types=body.object_types,
        reason=body.reason), 201)


@router.delete("/delegations/{delegation_id}")
def revoke_delegation(delegation_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.workflow_svc.revoke_delegation(me, delegation_id)
    return ok({"ok": True})
