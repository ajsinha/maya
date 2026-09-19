"""
The workflow engine (§10). One engine drives every object's lifecycle.

A service hands the engine a *subject* — the object's type, id, state,
owner, namespace and grants — and names a transition. The engine:

1. loads the active policy for the object type (namespace-scoped first);
2. refuses a transition that does not start from the current state;
3. checks the actor's role capability and object ACL through ``can()``;
4. runs every named check, refusing with the name of each that failed;
5. applies segregation of duties at the namespace's strictness (§28.9);
6. accumulates approvals until each ``{role, count}`` requirement is met;
7. records the event, the audit entry and the notifications — or, for
   break-glass, skips 4–6 loudly, permanently and never silently (§10.4).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from maya.security.authz import Principal, can
from maya.workflow.policy import transitions_from

CheckFn = Callable[[Any, dict[str, Any]], tuple[bool, str]]
SUBMITTERS = ("created_by", "submitted_by", "updated_by")


@dataclass
class Subject:
    """What the engine needs to know about the object moving through workflow."""

    object_type: str              # policy key, e.g. feature_version
    table: str                    # repository name
    id: str
    ref: str                      # maya:// reference, for audit and notifications
    cap_type: str                 # capability object type, e.g. feature
    row: dict[str, Any]
    namespace: dict[str, Any]
    owner_id: str | None
    owner_name: str | None
    grants: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def state(self) -> str:
        return str(self.row["state"])


@dataclass
class Outcome:
    moved: bool
    state: str
    message: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    approvals: dict[str, Any] = field(default_factory=dict)


class WorkflowEngine:
    """Stateless apart from the check registry and the settings it was given."""

    def __init__(self, *, allow_self_approval: bool = False, environment: str = "dev") -> None:
        self.checks: dict[str, CheckFn] = {}
        self.allow_self_approval = allow_self_approval and environment == "dev"
        self.environment = environment

    def register_check(self, name: str, fn: CheckFn) -> None:
        self.checks[name] = fn

    # -- policy lookup -------------------------------------------------------
    def active_policy(self, uow: Any, object_type: str, namespace: str) -> dict[str, Any]:
        repo = uow.repo("workflow_policies")
        for scope in (namespace, "*"):
            rows = repo.list(object_type=object_type, scope=scope, state="active",
                             order_by=["-version_no"], limit=1)
            if rows:
                return rows[0]
        raise ValidationFailed(f"No active workflow policy for {object_type}")

    def available(self, uow: Any, subject: Subject) -> list[str]:
        policy = self.active_policy(uow, subject.object_type, subject.namespace["name"])
        return transitions_from(policy["policy"], subject.state)

    # -- the transition --------------------------------------------------------
    def transition(self, uow: Any, p: Principal, subject: Subject, name: str, *,
                   rationale: str | None = None, force: bool = False) -> Outcome:
        record = self.active_policy(uow, subject.object_type, subject.namespace["name"])
        policy = record["policy"]
        t = (policy.get("transitions") or {}).get(name)
        if t is None:
            raise ValidationFailed(f"'{name}' is not a transition of {subject.object_type}")
        sources = t["from"] if isinstance(t["from"], list) else [t["from"]]
        if subject.state not in sources:
            raise NotApproved(f"Cannot {name} from state '{subject.state}'; "
                              f"allowed from {', '.join(sources)}", state=subject.state)
        if force:
            return self._break_glass(uow, p, subject, name, t, rationale, record)
        self._authorize(p, subject, t, name)
        results = self._run_checks(uow, subject, t)
        failed = [r for r in results if not r["passed"]]
        if failed:
            raise NotApproved("Blocked by check(s): " + "; ".join(
                f"{r['check']} — {r['detail']}" for r in failed), checks=results)
        if t.get("approvals"):
            return self._approve(uow, p, subject, name, t, rationale, record, results)
        return self._move(uow, p, subject, name, t, rationale, record, results)

    def _authorize(self, p: Principal, subject: Subject, t: dict[str, Any], name: str) -> None:
        roles = t.get("roles")
        if roles and not set(roles) & set(p.roles):
            raise PermissionDenied(f"'{name}' requires one of the roles {', '.join(roles)}")
        letter = t.get("capability")
        if letter:
            action = {"A": "approve", "U": "submit", "C": "create", "P": "seal"}.get(letter, "update")
            obj = {"type": subject.cap_type, "id": subject.id, "owner_id": subject.owner_id,
                   "state": subject.row.get("state"), "namespace_name": subject.namespace["name"]}
            decision = can(p, action, obj, subject.grants, subject.namespace)
            if not decision:
                raise PermissionDenied(f"You may not {name} this object: {decision.rule}",
                                       rule=decision.rule)

    def _run_checks(self, uow: Any, subject: Subject, t: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for check in t.get("checks") or []:
            fn = self.checks.get(check)
            if fn is None:
                out.append({"check": check, "passed": False, "detail": "check is not registered"})
                continue
            passed, detail = fn(uow, {"subject": subject, "row": subject.row,
                                      **subject.context})
            out.append({"check": check, "passed": bool(passed), "detail": detail})
        return out

    def _sod_violation(self, p: Principal, subject: Subject) -> str | None:
        if self.allow_self_approval:
            return None
        level = subject.namespace.get("sod", "strict")
        if level == "none":
            return None
        row = subject.row
        involved = {row.get(k) for k in SUBMITTERS if row.get(k)} if level == "strict" \
            else {row.get("submitted_by") or row.get("created_by")}
        if p.username in involved:
            return (f"segregation of duties ({level}): you created, submitted or last "
                    "modified this object, so you cannot approve it")
        return None

    def _approve(self, uow: Any, p: Principal, subject: Subject, name: str,
                 t: dict[str, Any], rationale: str | None, record: dict[str, Any],
                 results: list[dict[str, Any]]) -> Outcome:
        violation = self._sod_violation(p, subject)
        if violation:
            raise PermissionDenied(violation, sod=subject.namespace.get("sod"))
        reqs = self._requirements(t, subject)
        round_no = self._round(uow, subject)
        existing = uow.repo("approvals").list(object_type=subject.object_type,
                                              object_id=subject.id, round_no=round_no,
                                              decision="approve")
        if any(a["approver"] == p.username for a in existing):
            raise NotApproved("You have already approved this object in this round")
        role = next((r["role"] for r in reqs if r["role"] in p.roles
                     and self._count(existing, r["role"]) < r["count"]),
                    None) or ("admin" if p.is_admin else None)
        if role is None:
            raise PermissionDenied("Your roles do not satisfy any outstanding approval: "
                                   + self._outstanding_text(reqs, existing))
        uow.repo("approvals").add({"object_type": subject.object_type, "object_id": subject.id,
                                   "round_no": round_no, "approver": p.username, "role": role,
                                   "decision": "approve", "rationale": rationale})
        existing.append({"role": role, "approver": p.username})
        outstanding = [r for r in reqs if self._count(existing, r["role"]) < r["count"]
                       and not (role == "admin" and p.is_admin)]
        if outstanding:
            uow.audit("workflow.approval_recorded", object_type=subject.object_type,
                      object_ref=subject.ref, detail={"role": role, "rationale": rationale})
            return Outcome(False, subject.state, "Approval recorded; still outstanding: "
                           + self._outstanding_text(reqs, existing), results,
                           {"outstanding": outstanding})
        return self._move(uow, p, subject, name, t, rationale, record, results)

    def _requirements(self, t: dict[str, Any], subject: Subject) -> list[dict[str, Any]]:
        out = []
        for a in t.get("approvals") or []:
            when = a.get("when")
            if when == "prod" and not subject.namespace.get("production"):
                continue
            out.append({"role": a["role"], "count": int(a.get("count", 1))})
        return out

    @staticmethod
    def _count(approvals: list[dict[str, Any]], role: str) -> int:
        return sum(1 for a in approvals if a["role"] == role)

    def _outstanding_text(self, reqs: list[dict[str, Any]], existing: list[dict[str, Any]]) -> str:
        parts = [f"{r['role']} ×{r['count'] - self._count(existing, r['role'])}"
                 for r in reqs if self._count(existing, r["role"]) < r["count"]]
        return ", ".join(parts) or "none"

    def _round(self, uow: Any, subject: Subject) -> int:
        events = uow.repo("workflow_events").count(object_type=subject.object_type,
                                                   object_id=subject.id, transition="submit")
        return max(events, 1)

    def _move(self, uow: Any, p: Principal, subject: Subject, name: str, t: dict[str, Any],
              rationale: str | None, record: dict[str, Any], results: list[dict[str, Any]],
              forced: bool = False) -> Outcome:
        target = t["to"]
        uow.repo(subject.table).update(subject.id, self._state_changes(p, name, target, forced))
        uow.repo("workflow_events").add({
            "object_type": subject.object_type, "object_id": subject.id, "object_ref": subject.ref,
            "transition": name, "from_state": subject.state, "to_state": target,
            "actor": p.username, "rationale": rationale, "forced": forced,
            "policy_id": record["id"], "checks": results})
        uow.audit("workflow.break_glass" if forced else f"workflow.{name}",
                  object_type=subject.object_type, object_ref=subject.ref,
                  detail={"from": subject.state, "to": target, "rationale": rationale},
                  channel=p.channel)
        self._notify(uow, record["policy"], subject, target, name, p, forced)
        return Outcome(True, target, f"{name}: {subject.state} → {target}", results)

    @staticmethod
    def _state_changes(p: Principal, name: str, target: str, forced: bool) -> dict[str, Any]:
        from maya.persistence.types import utcnow
        changes: dict[str, Any] = {"state": target}
        if name == "submit":
            changes.update(submitted_by=p.username, submitted_at=utcnow())
        if target == "approved":
            changes.update(approved_by=p.username, approved_at=utcnow())
        if forced:
            changes["force_approved"] = True
        return changes

    def _break_glass(self, uow: Any, p: Principal, subject: Subject, name: str,
                     t: dict[str, Any], rationale: str | None,
                     record: dict[str, Any]) -> Outcome:
        if not p.is_admin:
            raise PermissionDenied("Break-glass is reserved to administrators")
        if not rationale or len(rationale.strip()) < 10:
            raise ValidationFailed("Break-glass requires a written reason (10+ characters)")
        return self._move(uow, p, subject, name, t, rationale, record,
                          [{"check": "break_glass", "passed": True,
                            "detail": "checks and approvals bypassed by an administrator"}],
                          forced=True)

    def _notify(self, uow: Any, policy: dict[str, Any], subject: Subject, target: str,
                name: str, p: Principal, forced: bool) -> None:
        audience = list((policy.get("notify") or {}).get(target, []))
        if forced and "owner" not in audience:
            audience.append("owner")
        users: set[str] = set()
        for who in audience:
            if who == "owner" and subject.owner_id:
                users.add(subject.owner_id)
            elif who != "owner":
                users |= _users_with_role(uow, who)
        prefix = "BREAK-GLASS: " if forced else ""
        for uid in users:
            uow.repo("notifications").add({
                "user_id": uid, "kind": "break_glass" if forced else "workflow",
                "message": f"{prefix}{p.username} took '{name}' on {subject.ref} → {target}",
                "object_ref": subject.ref})


def _users_with_role(uow: Any, role_name: str) -> set[str]:
    role = uow.repo("roles").find_one(name=role_name)
    if role is None:
        return set()
    return {ur["user_id"] for ur in uow.repo("user_roles").list(role_id=role["id"])}
