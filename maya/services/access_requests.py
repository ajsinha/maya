"""
Access requests (§11.5) and the reason a control is disabled (§16.4).

"Access requests are a workflow: a user clicks *request access*, the owner
receives an approval item, and the resulting grant is time-boxed by default
(90 days)." Two halves, and the second is the one that usually goes missing:
the ask, the decision, and an audit entry for both, so the question "who let
them in, when, and why" is answerable a year later from the record rather than
from somebody's memory of an inbox message.

The same machinery answers §16.4's other half. A control the user cannot use
is shown disabled *with the reason*, not hidden, and the reason has to come
from the same decision that will refuse the action — ``can()`` — or the screen
and the server will drift apart. ``check`` returns exactly that decision, plus
whether a request for access is worth offering.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.core.clock import utcnow
from maya.core.errors import NotFound, PermissionDenied, ValidationFailed
from maya.security.authz import LEVELS, Principal, can
from maya.services import refs
from maya.services.access import KINDS

OPEN = "pending"
STATES = (OPEN, "approved", "denied", "withdrawn")
DEFAULT_DAYS = 90


class AccessRequestService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- asking (§11.5) ---------------------------------------------------------
    def request(
        self,
        p: Principal,
        *,
        kind: str,
        ref: str,
        level: str = "read",
        reason: str = "",
        days: int = DEFAULT_DAYS,
    ) -> dict[str, Any]:
        """Ask the object's owner for access. One open request per person per object."""
        if kind not in KINDS:
            raise ValidationFailed(f"Access is requested on {', '.join(KINDS)}", kind=kind)
        if level not in LEVELS:
            raise ValidationFailed(f"Level must be one of {', '.join(LEVELS)}", level=level)
        obj = self.p.access.resolve_object(kind, ref)
        with self.p.uow(p.username) as uow:
            if self.p.access.allowed(uow, p, "read", kind, obj):
                raise ValidationFailed(
                    "You can already read this; there is nothing to request", ref=ref
                )
            open_already = uow.repo("access_requests").find_one(
                kind=kind, object_id=obj["id"], requester_id=p.user_id, state=OPEN
            )
            if open_already is not None:
                return {**open_already, "duplicate": True}
            object_ref = self._object_ref(uow, kind, obj)
            row = uow.repo("access_requests").add(
                {
                    "kind": kind,
                    "object_id": obj["id"],
                    "object_ref": object_ref,
                    "requester_id": p.user_id,
                    "level": level,
                    "reason": reason,
                    "state": OPEN,
                    "days": int(days),
                }
            )
            for user_id in self._deciders(uow, kind, obj):
                uow.repo("notifications").add(
                    {
                        "user_id": user_id,
                        "kind": "access_request",
                        "object_ref": object_ref,
                        "message": f"{p.username} requests {level} on {object_ref}"
                        + (f": {reason}" if reason else ""),
                    }
                )
            uow.audit(
                "access.requested",
                object_type=kind,
                object_ref=object_ref,
                detail={"level": level, "reason": reason, "days": int(days)},
            )
            return row

    def withdraw(self, p: Principal, request_id: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            row = uow.repo("access_requests").require(request_id)
            if row["requester_id"] != p.user_id:
                raise PermissionDenied("Only the person who asked can withdraw the request")
            if row["state"] != OPEN:
                raise ValidationFailed(f"The request is already {row['state']}")
            out = uow.repo("access_requests").update(request_id, {"state": "withdrawn"})
            uow.audit(
                "access.request_withdrawn", object_type=row["kind"], object_ref=row["object_ref"]
            )
            return out

    # -- deciding (§11.5) -------------------------------------------------------
    def decide(
        self,
        p: Principal,
        request_id: str,
        *,
        approve: bool,
        note: str = "",
        days: int | None = None,
    ) -> dict[str, Any]:
        """The owner's decision. Approving issues the grant; refusing says so and why.

        The grant is made by ``access.grant`` under the decider's own principal, so a
        decision can never hand out more than the decider holds, and the grant's own
        audit entry is written alongside the decision's.
        """
        with self.p.uow(p.username) as uow:
            row = uow.repo("access_requests").require(request_id)
            if row["state"] != OPEN:
                raise ValidationFailed(f"The request is already {row['state']}", state=row["state"])
            obj = self._object(uow, row)
            self.p.access.require(uow, p, "grant", row["kind"], obj)
            requester = uow.repo("users").require(row["requester_id"])
        grant = None
        if approve:
            grant = self.p.access.grant(
                p,
                kind=row["kind"],
                obj=obj,
                principal_type="user",
                principal_id=requester["username"],
                level=row["level"],
                days=int(days or row["days"] or DEFAULT_DAYS),
            )
        with self.p.uow(p.username) as uow:
            out = uow.repo("access_requests").update(
                request_id,
                {
                    "state": "approved" if approve else "denied",
                    "decided_by": p.username,
                    "decided_at": utcnow(),
                    "decision_note": note,
                    "grant_id": (grant or {}).get("id"),
                },
            )
            verdict = "granted" if approve else "refused"
            uow.repo("notifications").add(
                {
                    "user_id": row["requester_id"],
                    "kind": "access_decision",
                    "object_ref": row["object_ref"],
                    "message": f"{p.username} {verdict} your request for {row['level']} on "
                    f"{row['object_ref']}" + (f": {note}" if note else ""),
                }
            )
            uow.audit(
                "access.request_decided",
                object_type=row["kind"],
                object_ref=row["object_ref"],
                detail={
                    "decision": out["state"],
                    "requester": requester["username"],
                    "level": row["level"],
                    "note": note,
                    "grant_id": (grant or {}).get("id"),
                },
            )
            return {**out, "grant": grant}

    # -- reading ------------------------------------------------------------------
    def list(self, p: Principal, *, state: str | None = None) -> list[dict[str, Any]]:
        """Requests you made, plus those waiting on you (all of them, for an admin)."""
        if state is not None and state not in STATES:
            raise ValidationFailed(f"state must be one of {', '.join(STATES)}", state=state)
        out = []
        with self.p.uow() as uow:
            users = {u["id"]: u["username"] for u in uow.repo("users").list()}
            filters = {"state": state} if state else {}
            for row in uow.repo("access_requests").list(order_by=["-created_at"], **filters):
                obj = self._object(uow, row, quiet=True)
                mine = row["requester_id"] == p.user_id
                yours = obj is not None and self.p.access.allowed(uow, p, "grant", row["kind"], obj)
                if not (mine or yours or p.is_admin):
                    continue
                out.append(
                    {
                        **row,
                        "requester": users.get(row["requester_id"]),
                        "mine": mine,
                        "you_decide": yours,
                    }
                )
        return out

    # -- "why is this disabled?" (§16.4) ------------------------------------------
    def check(self, p: Principal, *, kind: str, ref: str, action: str = "read") -> dict[str, Any]:
        """May ``p`` take ``action``, and if not, in the words of the rule that decided."""
        if kind not in KINDS:
            raise ValidationFailed(f"Unknown object kind '{kind}'", kind=kind)
        obj = self.p.access.resolve_object(kind, ref)
        with self.p.uow() as uow:
            described = self.p.access.describe(uow, kind, obj)
            decision = can(p, action, described["obj"], described["grants"], described["namespace"])
            readable = self.p.access.allowed(uow, p, "read", kind, obj)
            pending = uow.repo("access_requests").find_one(
                kind=kind, object_id=obj["id"], requester_id=p.user_id, state=OPEN
            )
        return {
            "kind": kind,
            "ref": ref,
            "action": action,
            "allowed": bool(decision),
            "reason": None if decision else f"you may not {action} this: {decision.rule}",
            "rule": decision.rule,
            "conditions": decision.conditions,
            "can_request": not decision.allowed and action in ("read", "download", "update"),
            "pending_request": (pending or {}).get("id"),
            "readable": readable,
        }

    # -- helpers --------------------------------------------------------------------
    def _object(self, uow: Any, row: dict[str, Any], *, quiet: bool = False) -> Any:
        obj = uow.repo(KINDS[row["kind"]][0]).get(row["object_id"])
        if obj is None and not quiet:
            raise NotFound(f"{row['object_ref']} no longer exists", ref=row["object_ref"])
        return obj

    @staticmethod
    def _object_ref(uow: Any, kind: str, obj: dict[str, Any]) -> str:
        if kind == "namespace":
            return f"maya://namespace/{obj['name']}"
        if kind in ("training_warrant", "execution_warrant"):
            ns = uow.repo("namespaces").require(obj["namespace_id"])
            leaf = "train" if kind == "training_warrant" else "exec"
            return f"maya://warrant/{leaf}/{ns['name']}/{obj['name']}"
        ns = uow.repo("namespaces").require(obj["namespace_id"])
        return refs.object_ref(kind, ns["name"], obj["name"])

    def _deciders(self, uow: Any, kind: str, obj: dict[str, Any]) -> set[str]:
        """Who receives the item: the object's owner and its namespace's owner, because
        §11.5 says the owner hears about it, and the administrators, because with the
        shipped role matrix they are the ones holding ``G`` who can actually answer."""
        out = {x for x in (obj.get("owner_id"),) if x}
        if kind != "namespace" and obj.get("namespace_id"):
            ns = uow.repo("namespaces").get(obj["namespace_id"])
            if ns and ns.get("owner_id"):
                out.add(ns["owner_id"])
        role = uow.repo("roles").find_one(name="admin")
        if role is not None:
            out |= {r["user_id"] for r in uow.repo("user_roles").list(role_id=role["id"])}
        return out
