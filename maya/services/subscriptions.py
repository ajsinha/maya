"""
Who gets told what (§5.7, §5.5, §9.4, §29.5).

Two things live here because they are the same thing seen from two sides.

**Subscriptions** are what a user asks for: *subscribe to a feature and be
notified when a new version is approved or a dependent pin is created* (§5.7).
A subscription is a row against a bare object reference, so it follows the
object rather than a version, and it is only ever honoured for someone who may
still read the object — access can be revoked after the subscription was made,
and a notification must not become a side channel around ``can()``.

**Notices** are what the platform owes people whether or not they asked: a
covenant breach and a warrant thirty days from expiry reach the model manager
as well as the owner (§29.5, §9.4), and a quality check that failed and blocked
a pin reaches the owner (§5.5). Each is idempotent on (user, kind, object), so
a sweep that runs hourly does not become an hourly reminder.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import datetime as dt
from typing import Any

from maya.core.clock import utcnow
from maya.core.errors import MayaError, ValidationFailed
from maya.security.authz import Principal
from maya.services import refs

# object kind -> the access kind and table a subscription resolves against
SUBSCRIBABLE = {
    "feature": ("feature", "features"),
    "featureset": ("featureset", "feature_sets"),
    "model": ("model", "models"),
}
EXPIRY_DAYS = 30
MANAGER_ROLE = "model_manager"


def _bare(ref: str) -> str:
    return ref.split("@")[0].split("#")[0]


class SubscriptionService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- subscriptions (§5.7) --------------------------------------------------
    def subscribe(self, p: Principal, object_ref: str) -> dict[str, Any]:
        """Follow an object. You may only follow what you may read."""
        with self.p.uow(p.username) as uow:
            ref, obj, kind = self._resolve(uow, p, object_ref)
            existing = uow.repo("subscriptions").find_one(user_id=p.user_id, object_ref=ref)
            if existing is not None:
                return existing
            row = uow.repo("subscriptions").add({"user_id": p.user_id, "object_ref": ref})
            uow.audit("subscription.created", object_type=kind, object_ref=ref)
            _ = obj
            return row

    def unsubscribe(self, p: Principal, object_ref: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            ref = _bare(object_ref)
            row = uow.repo("subscriptions").find_one(user_id=p.user_id, object_ref=ref)
            if row is None:
                raise ValidationFailed(f"You are not subscribed to {ref}", ref=ref)
            uow.repo("subscriptions").delete(row["id"])
            uow.audit("subscription.removed", object_ref=ref)
            return {"ok": True, "object_ref": ref}

    def list(self, p: Principal) -> list[dict[str, Any]]:
        """Your subscriptions, each with where it points and whether you can still read it."""
        out = []
        with self.p.uow() as uow:
            for row in uow.repo("subscriptions").list(user_id=p.user_id, order_by=["-created_at"]):
                out.append({**row, "readable": self._readable(uow, p, row["object_ref"])})
        return out

    def subscribers(self, uow: Any, object_ref: str) -> builtins.list[str]:
        """The user ids following ``object_ref`` who may still read it.

        Access granted yesterday can be gone today, and a notification naming an object
        somebody may no longer read would be a side channel around ``can()``. The
        subscription survives — it is honoured again if access returns — but it is
        silent while it would leak, and the check is made without auditing a denial:
        nobody asked for anything, so nobody was refused.
        """
        ref = _bare(object_ref)
        kept = []
        for row in uow.repo("subscriptions").list(object_ref=ref):
            user = uow.repo("users").get(row["user_id"])
            if user is None or user["status"] != "active":
                continue
            principal = self.p.auth.build_principal(uow, user["id"])
            if self._readable(uow, principal, ref):
                kept.append(row["user_id"])
        return kept

    def _readable(self, uow: Any, p: Principal, object_ref: str) -> bool:
        try:
            parsed = refs.parse(_bare(object_ref))
            kind, table = SUBSCRIBABLE[parsed.kind]
            obj, _ = self._find(uow, table, kind, parsed)
        except (MayaError, KeyError):
            return False
        return bool(self.p.access.allowed(uow, p, "read", kind, obj))

    @staticmethod
    def _find(
        uow: Any, table: str, kind: str, parsed: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from maya.services import catalog

        found: tuple[dict[str, Any], dict[str, Any]] = catalog.find_object(uow, table, kind, parsed)
        return found

    def _resolve(self, uow: Any, p: Principal, object_ref: str) -> tuple[str, dict[str, Any], str]:
        parsed = refs.parse(_bare(object_ref))
        if parsed.kind not in SUBSCRIBABLE:
            raise ValidationFailed(
                f"You can subscribe to {', '.join(SUBSCRIBABLE)}", kind=parsed.kind
            )
        kind, table = SUBSCRIBABLE[parsed.kind]
        obj, ns = self._find(uow, table, kind, parsed)
        self.p.access.require(uow, p, "read", kind, obj)
        return refs.object_ref(parsed.kind, ns["name"], obj["name"]), obj, kind

    # -- fan-out ----------------------------------------------------------------
    def on_move(self, uow: Any, subject: Any, transition: str, to_state: str) -> None:
        """A new version was approved: tell whoever follows the object (§5.7)."""
        _ = transition
        if to_state != "approved":
            return
        ref = _bare(subject.ref)
        message = f"{ref} approved v{subject.row.get('version_no')}" + (
            f" ({subject.row['change_class']})" if subject.row.get("change_class") else ""
        )
        # The unit of work's actor, not the row's ``approved_by``: the listener runs inside
        # the transition's own transaction, where the row dict is still the one read before
        # the move and carries no approver yet.
        self._tell(uow, ref, "subscription", message, exclude=uow.actor)

    def announce_pin(self, kind: str, pin_id: str) -> int:
        """A pin was sealed (or failed): tell the object's followers, and — where the
        quality contract blocked it — its owner, which §5.5 requires and nothing did."""
        table = "feature_pins" if kind == "feature" else "feature_set_pins"
        sent = 0
        with self.p.uow("system") as uow:
            pin = uow.repo(table).get(pin_id)
            if pin is None:
                return 0
            ref, obj = self._pin_object(uow, kind, pin)
            if pin["state"] == "sealed":
                sent += self._tell(
                    uow,
                    ref,
                    "subscription",
                    f"{ref} has a new sealed pin: {pin['pin_name']} as of {pin['as_of_date']}",
                )
                for member in self._member_refs(uow, kind, pin):
                    sent += self._tell(
                        uow,
                        member,
                        "subscription",
                        f"a pin of {ref} ({pin['pin_name']}/{pin['as_of_date']}) "
                        f"depends on {member}",
                    )
            elif pin["state"] == "failed":
                sent += self._notify(
                    uow,
                    obj.get("owner_id"),
                    "quality_failed",
                    pin["id"],
                    f"{ref}: pin '{pin['pin_name']}' as of {pin['as_of_date']} was blocked — "
                    f"{pin.get('failure') or 'a check failed'}",
                )
        return sent

    @staticmethod
    def _pin_object(uow: Any, kind: str, pin: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        table, fk = (
            ("features", "feature_id") if kind == "feature" else ("feature_sets", "feature_set_id")
        )
        obj = uow.repo(table).require(pin[fk])
        ns = uow.repo("namespaces").require(obj["namespace_id"])
        return refs.object_ref(kind, ns["name"], obj["name"]), obj

    @staticmethod
    def _member_refs(uow: Any, kind: str, pin: dict[str, Any]) -> builtins.list[str]:
        """For a feature-set pin, the member features whose own pins it created."""
        if kind != "featureset":
            return []
        version = uow.repo("feature_set_versions").get(pin["feature_set_version_id"])
        members = ((version or {}).get("definition") or {}).get("members") or []
        return sorted({_bare(m["ref"]) for m in members if m.get("ref")})

    def _tell(self, uow: Any, ref: str, kind: str, message: str, exclude: str | None = None) -> int:
        sent = 0
        for user_id in self.subscribers(uow, ref):
            user = uow.repo("users").get(user_id)
            if exclude and user and user["username"] == exclude:
                continue
            sent += self._notify(uow, user_id, kind, ref, message)
        return sent

    @staticmethod
    def _notify(uow: Any, user_id: str | None, kind: str, object_ref: str, message: str) -> int:
        """One notification, once: the same (user, kind, object, words) is never repeated."""
        if not user_id:
            return 0
        if uow.repo("notifications").find_one(
            user_id=user_id, kind=kind, object_ref=object_ref, message=message
        ):
            return 0
        uow.repo("notifications").add(
            {"user_id": user_id, "kind": kind, "message": message, "object_ref": object_ref}
        )
        return 1

    # -- the notices the platform owes (§5.5, §9.4, §29.5) ----------------------
    def notices(self) -> dict[str, int]:
        """The sweep: expiry, covenant breaches and blocked pins. Run by the scheduler."""
        counts = {
            "expiry": self.expiry_notices(),
            "covenant_breach": self.breach_notices(),
            "quality_failed": self.failed_pin_notices(),
        }
        if any(counts.values()):
            with self.p.uow("system") as uow:
                uow.audit(
                    "notices.swept",
                    principal_type="system",
                    channel="scheduler",
                    detail=counts,
                )
        return counts

    def expiry_notices(self) -> int:
        """Thirty days before a warrant expires, the model manager hears too (§9.4).

        ``execution.expire_sweep`` already tells the owner about execution warrants;
        this adds the manager, and the training warrants nobody was telling anyone about.
        """
        soon = utcnow() + dt.timedelta(days=EXPIRY_DAYS)
        sent = 0
        with self.p.uow("system") as uow:
            managers = self._role_holders(uow, MANAGER_ROLE)
            for table, column in (
                ("execution_warrants", "valid_to"),
                ("training_warrants", "expires_at"),
            ):
                for warrant in uow.repo(table).list(
                    **{f"{column}__le": soon, f"{column}__gt": utcnow()},
                    revoked_at__isnull=True,
                ):
                    when = warrant[column]
                    message = (
                        f"{warrant['name']} ({table[:-1].replace('_', ' ')}) expires "
                        f"{when:%Y-%m-%d}"
                    )
                    for user_id in managers | {warrant["owner_id"]}:
                        sent += self._notify(uow, user_id, "expiry", warrant["id"], message)
        return sent

    def breach_notices(self) -> int:
        """A covenant breach suspends the warrant and reaches the model manager (§29.5)."""
        sent = 0
        with self.p.uow("system") as uow:
            managers = self._role_holders(uow, MANAGER_ROLE)
            for ew in uow.repo("execution_warrants").list(
                suspended_at__isnull=False, revoked_at__isnull=True
            ):
                reason = ew["suspend_reason"] or "a covenant was breached"
                ns = uow.repo("namespaces").get(ew["namespace_id"])
                uri = self.p.execution.uri(ew, ns) if ns else ew["id"]
                message = f"{uri} SUSPENDED: {reason}"
                for user_id in managers:
                    sent += self._notify(uow, user_id, "covenant_breach", uri, message)
        return sent

    def failed_pin_notices(self) -> int:
        """A failing quality check blocks a pin and raises an alert to the owner (§5.5)."""
        sent = 0
        with self.p.uow("system") as uow:
            for kind, table in (("feature", "feature_pins"), ("featureset", "feature_set_pins")):
                for pin in uow.repo(table).list(state="failed"):
                    ref, obj = self._pin_object(uow, kind, pin)
                    sent += self._notify(
                        uow,
                        obj.get("owner_id"),
                        "quality_failed",
                        pin["id"],
                        f"{ref}: pin '{pin['pin_name']}' as of {pin['as_of_date']} was "
                        f"blocked — {pin.get('failure') or 'a check failed'}",
                    )
        return sent

    @staticmethod
    def _role_holders(uow: Any, role_name: str) -> set[str]:
        role = uow.repo("roles").find_one(name=role_name)
        if role is None:
            return set()
        return {ur["user_id"] for ur in uow.repo("user_roles").list(role_id=role["id"])}
