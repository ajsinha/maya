"""
Workflow as seen by people (§10.3–§10.6): the review queue, comments,
instance history, the live population per state, campaigns, the break-glass
report, and the policy editor — where a policy is itself governed: drafted,
validated as it is edited, previewed against the live population, activated
by a second administrator, and retained so the policy behind any past
decision is recoverable.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from maya.persistence.types import utcnow
from maya.security.authz import Principal
from maya.workflow import policy as pol

# policy object type -> (table, how to transition an object of it)
TABLES = {
    "feature_version": "feature_versions", "featureset_version": "feature_set_versions",
    "model_version": "model_versions", "parameter_set": "parameter_sets",
    "training_warrant": "training_warrants", "execution_warrant": "execution_warrants",
}


class WorkflowService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- policies ------------------------------------------------------------------
    def policies(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("workflow_policies").list(order_by=["object_type", "-version_no"])

    def policy(self, policy_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            row = uow.repo("workflow_policies").require(policy_id)
        row["yaml"] = pol.to_yaml(row["policy"])
        row["errors"] = self.validate(row["policy"])
        row["population"] = self.population(row["object_type"])
        return row

    def validate(self, policy: dict[str, Any]) -> list[str]:
        with self.p.uow() as uow:
            roles = [r["name"] for r in uow.repo("roles").list()]
        return pol.validate(policy, checks=self.p.workflow.checks.keys(), roles=roles)

    def draft_policy(self, p: Principal, object_type: str, policy: dict[str, Any], *,
                     scope: str = "*", note: str = "") -> dict[str, Any]:
        """Save a policy draft — refused at edit time if it is invalid (§10.6)."""
        self._admin(p)
        if object_type not in TABLES:
            raise ValidationFailed(f"Unknown object type '{object_type}'")
        errors = self.validate(policy)
        if errors:
            raise ValidationFailed("The policy cannot be saved: " + "; ".join(errors),
                                   errors=errors)
        impact = self.preview(object_type, policy)
        with self.p.uow(p.username) as uow:
            last = uow.repo("workflow_policies").list(object_type=object_type, scope=scope,
                                                      order_by=["-version_no"], limit=1)
            row = uow.repo("workflow_policies").add({
                "object_type": object_type, "scope": scope,
                "version_no": last[0]["version_no"] + 1 if last else 1, "state": "draft",
                "policy": policy, "note": note})
            uow.audit("policy.drafted", object_type="workflow_policy",
                      object_ref=f"{object_type}@{scope}#v{row['version_no']}",
                      detail={"impact": impact})
            return {**row, "impact": impact}

    def import_yaml(self, p: Principal, object_type: str, text: str, *, scope: str = "*",
                    note: str = "imported from YAML") -> dict[str, Any]:
        return self.draft_policy(p, object_type, pol.from_yaml(text), scope=scope, note=note)

    def activate(self, p: Principal, policy_id: str) -> dict[str, Any]:
        """Activation is approval by a second administrator; the old version is retained."""
        self._admin(p)
        with self.p.uow(p.username) as uow:
            row = uow.repo("workflow_policies").require(policy_id)
            if row["state"] != "draft":
                raise NotApproved(f"Policy v{row['version_no']} is {row['state']}")
            if row["created_by"] == p.username and not self.p.workflow.allow_self_approval:
                raise PermissionDenied("A policy you drafted must be activated by another "
                                       "administrator: the rules of governance are governed too")
            for old in uow.repo("workflow_policies").list(object_type=row["object_type"],
                                                          scope=row["scope"], state="active"):
                uow.repo("workflow_policies").update(old["id"], {"state": "superseded"})
            out = uow.repo("workflow_policies").update(policy_id, {
                "state": "active", "approved_by": p.username, "activated_at": utcnow()})
            uow.audit("policy.activated", object_type="workflow_policy",
                      object_ref=f"{row['object_type']}@{row['scope']}#v{row['version_no']}")
            return out

    def preview(self, object_type: str, policy: dict[str, Any]) -> dict[str, Any]:
        """What this policy would do to the live population, before it is saved."""
        population = self.population(object_type)
        states = set(policy.get("states") or [])
        stranded = {s: n for s, n in population.items() if s not in states and n}
        exits = {s: pol.transitions_from(policy, s) for s in states}
        blocked = {s: n for s, n in population.items()
                   if s in states and n and not exits.get(s) and s not in ("retired", "withdrawn")}
        messages = []
        if stranded:
            messages.append("would strand " + ", ".join(f"{n} object(s) in '{s}'"
                                                        for s, n in stranded.items()))
        if blocked:
            messages.append("would block " + ", ".join(f"{n} object(s) in '{s}' (no way out)"
                                                       for s, n in blocked.items()))
        return {"population": population, "stranded": stranded, "blocked": blocked,
                "messages": messages or ["no object currently in flight is affected"]}

    def population(self, object_type: str) -> dict[str, int]:
        with self.p.uow() as uow:
            counts: dict[str, int] = {}
            for row in uow.repo(TABLES[object_type]).list():
                counts[row["state"]] = counts.get(row["state"], 0) + 1
            return counts

    def export_yaml(self, policy_id: str) -> str:
        with self.p.uow() as uow:
            return pol.to_yaml(uow.repo("workflow_policies").require(policy_id)["policy"])

    @staticmethod
    def _admin(p: Principal) -> None:
        if not p.has_capability("workflow_policy", "U"):
            raise PermissionDenied("Workflow policy is administered by 'admin'")

    # -- people-facing ------------------------------------------------------------------
    def queue(self, p: Principal) -> list[dict[str, Any]]:
        """Everything in review that this user could act on (My queue, §16.2)."""
        out = []
        with self.p.uow() as uow:
            for object_type, table in TABLES.items():
                for row in uow.repo(table).list(state="in_review"):
                    ev = uow.repo("workflow_events").list(object_type=object_type,
                                                          object_id=row["id"],
                                                          order_by=["-created_at"], limit=1)
                    ref = ev[0]["object_ref"] if ev else row["id"]
                    since = ev[0]["created_at"] if ev else row["updated_at"]
                    out.append({"object_type": object_type, "id": row["id"], "ref": ref,
                                "submitted_by": row.get("submitted_by") or row.get("created_by"),
                                "since": since, "age_days": (utcnow() - since).days,
                                "mine": (row.get("submitted_by") or row.get("created_by"))
                                == p.username})
        return sorted(out, key=lambda r: r["since"])

    def history(self, object_type: str, object_id: str) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            events = uow.repo("workflow_events").list(object_type=object_type, object_id=object_id,
                                                      order_by=["created_at"])
            approvals = uow.repo("approvals").list(object_type=object_type, object_id=object_id,
                                                   order_by=["created_at"])
        return events + [{**a, "transition": "approval", "from_state": "", "to_state": "",
                          "actor": a["approver"]} for a in approvals]

    def comment(self, p: Principal, object_type: str, object_id: str, body: str, *,
                blocking: bool = False, anchor: str | None = None) -> dict[str, Any]:
        if not body.strip():
            raise ValidationFailed("A comment needs a body")
        with self.p.uow(p.username) as uow:
            row = uow.repo("comments").add({"object_type": object_type, "object_id": object_id,
                                            "author": p.username, "body": body,
                                            "blocking": blocking, "anchor": anchor})
            uow.audit("review.commented", object_type=object_type, object_ref=object_id,
                      detail={"blocking": blocking})
            return row

    def resolve_comment(self, p: Principal, comment_id: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            row = uow.repo("comments").require(comment_id)
            if row["author"] != p.username and not p.is_admin:
                raise PermissionDenied("Only the comment's author resolves it")
            return uow.repo("comments").update(comment_id, {"resolved": True})

    def comments(self, object_type: str, object_id: str) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("comments").list(object_type=object_type, object_id=object_id,
                                             order_by=["created_at"])

    def check_no_blocking_comments(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        subject = ctx["subject"]
        open_blocking = uow.repo("comments").count(object_type=subject.object_type,
                                                   object_id=subject.id, blocking=True,
                                                   resolved=False)
        return (open_blocking == 0, f"{open_blocking} open blocking comment(s)"
                if open_blocking else "no open blocking comments")

    def break_glass_report(self, days: int = 31) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("workflow_events").list(
                forced=True, created_at__ge=utcnow() - dt.timedelta(days=days),
                order_by=["-created_at"])

    def aging(self) -> list[dict[str, Any]]:
        """Items past their SLA (§10.4)."""
        out = []
        with self.p.uow() as uow:
            active = {r["object_type"]: r["policy"] for r in
                      uow.repo("workflow_policies").list(state="active", scope="*")}
        for item in self.queue_all():
            sla = (active.get(item["object_type"], {}).get("sla_days") or {}).get("in_review")
            if sla and item["age_days"] > int(sla):
                out.append({**item, "sla_days": sla})
        return out

    def queue_all(self) -> list[dict[str, Any]]:
        from maya.security.authz import Principal as P
        return self.queue(P("", "", [], {}))

    # -- campaigns ------------------------------------------------------------------------
    def run_campaign(self, p: Principal, name: str, transition: str,
                     items: list[dict[str, Any]], rationale: str = "") -> dict[str, Any]:
        """One transition over many objects, per-item status, one audit record (§10.5)."""
        results = []
        for item in items:
            try:
                out = self.p.dispatch_transition(p, item["object_type"], item["id"], transition,
                                                 rationale=rationale)
                results.append({**item, "ok": True, "state": out["state"],
                                "message": out["message"]})
            except Exception as exc:  # noqa: BLE001 - partial failure is reported per item
                results.append({**item, "ok": False, "message": str(getattr(exc, "message", exc))})
        with self.p.uow(p.username) as uow:
            row = uow.repo("campaigns").add({"name": name, "transition": transition,
                                             "items": items, "state": "done", "results": results,
                                             "rationale": rationale})
            uow.audit("campaign.run", object_type="campaign", object_ref=name,
                      detail={"transition": transition, "items": len(items),
                              "succeeded": sum(1 for r in results if r["ok"])})
            return row

    def campaigns(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("campaigns").list(order_by=["-created_at"])
