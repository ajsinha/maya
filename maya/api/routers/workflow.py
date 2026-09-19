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
    return ok(plat.workflow_svc.aging(me))


@router.get("/break-glass")
def break_glass(days: int = 31, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.break_glass_report(me, days))


@router.get("/review")
def review(object_type: str, object_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """Everything the review screen shows (§10.3, §10.6): the semantic diff against the
    last approved version, the impact list with owners, the policy that governs this
    item, the separation of duties in force, and the approvals still outstanding."""
    return ok(plat.workflow_svc.review(me, object_type, object_id))


# -- access requests (§11.5): a request, a decision, and the audit trail of both --------
@router.get("/access-requests")
def access_requests(state: str | None = None, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access_requests.list(me, state=state))


@router.post("/access-requests", status_code=201)
def request_access(body: s.AccessRequestIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(
        plat.access_requests.request(
            me,
            kind=body.kind,
            ref=body.ref,
            level=body.level,
            reason=body.reason,
            days=body.days,
        ),
        201,
    )


@router.post("/access-requests/{request_id}/decide")
def decide_access_request(
    request_id: str, body: s.AccessDecisionIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        plat.access_requests.decide(
            me, request_id, approve=body.approve, note=body.note, days=body.days
        )
    )


@router.post("/access-requests/{request_id}/withdraw")
def withdraw_access_request(request_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access_requests.withdraw(me, request_id))


@router.get("/access-check")
def access_check(
    kind: str, ref: str, action: str = "read", me: Principal = Me, plat: Any = Plat
) -> Response:
    """Whether you may take ``action``, and in the words of the rule that decided — what
    a control disabled rather than hidden puts next to itself (§16.4)."""
    return ok(plat.access_requests.check(me, kind=kind, ref=ref, action=action))


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
    return ok(
        plat.workflow_svc.draft_policy(
            me, body.object_type, body.policy, scope=body.scope, note=body.note
        ),
        201,
    )


@router.post("/policies/import", status_code=201)
def import_policy(body: s.PolicyYamlIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.import_yaml(me, body.object_type, body.yaml, scope=body.scope), 201)


@router.post("/policies/validate")
def validate_policy(body: s.PolicyIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(
        {
            "errors": plat.workflow_svc.validate(body.policy),
            "impact": plat.workflow_svc.preview(body.object_type, body.policy),
        }
    )


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
    return ok(
        plat.workflow_svc.comment(
            me,
            body.object_type,
            body.object_id,
            body.body,
            blocking=body.blocking,
            anchor=body.anchor,
        ),
        201,
    )


@router.post("/comments/{comment_id}/resolve")
def resolve_comment(comment_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.resolve_comment(me, comment_id))


@router.post("/transitions")
def transition(body: s.GenericTransitionIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(
        plat.dispatch_transition(
            me,
            body.object_type,
            body.object_id,
            body.transition,
            rationale=body.rationale,
            force=body.force,
        )
    )


@router.get("/campaigns")
def campaigns(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.campaigns())


@router.post("/campaigns", status_code=201)
def run_campaign(body: s.CampaignIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(
        plat.workflow_svc.run_campaign(me, body.name, body.transition, body.items, body.rationale),
        201,
    )


@router.get("/delegations")
def delegations(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workflow_svc.delegations(me))


@router.post("/delegations", status_code=201)
def delegate(body: s.DelegationIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(
        plat.workflow_svc.delegate(
            me,
            to=body.to,
            starts_on=parse_date(body.starts_on, "starts_on"),
            ends_on=parse_date(body.ends_on, "ends_on"),
            object_types=body.object_types,
            reason=body.reason,
        ),
        201,
    )


@router.delete("/delegations/{delegation_id}")
def revoke_delegation(delegation_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.workflow_svc.revoke_delegation(me, delegation_id)
    return ok({"ok": True})
