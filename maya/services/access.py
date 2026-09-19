"""
Access administration and enforcement: users, roles, groups, namespaces,
grants, and the ``require`` helper every service calls before acting (§11).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from maya.core import kdf
from maya.core.errors import ConflictError, NotFound, PermissionDenied, ValidationFailed
from maya.core.clock import utcnow
from maya.security.authz import LEVELS, Principal, can, inert_grant_reason
from maya.security.roles import PRESETS

# object kind -> (table, capability type, grant object_type)
KINDS = {
    "feature": ("features", "feature"),
    "featureset": ("feature_sets", "featureset"),
    "model": ("models", "model"),
    "training_warrant": ("training_warrants", "training_warrant"),
    "execution_warrant": ("execution_warrants", "execution_warrant"),
    "namespace": ("namespaces", "namespace"),
}


CREDENTIAL_FIELDS = ("password_hash", "mfa_secret", "mfa_last_step")

# How a namespace's feature-set pins keep their resolved output (§6, revision 2.3):
# written at sealing; written at first read; or never written, replayed from member pins.
MATERIALIZE_POLICIES = ("always", "on_demand", "never")


DIRECTORY_FIELDS = ("id", "username", "display_name", "status")


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    """A user row with every credential field removed — the only form that leaves."""
    return {k: v for k, v in row.items() if k not in CREDENTIAL_FIELDS}


class AccessService:
    """Everything that decides or changes who may do what."""

    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- enforcement -----------------------------------------------------------
    def describe(
        self,
        uow: Any,
        kind: str,
        obj: dict[str, Any],
        state: str | None = None,
        cap_type: str | None = None,
    ) -> dict[str, Any]:
        """The ``can()`` view of a catalog object plus its namespace and grants."""
        ns = (
            uow.repo("namespaces").require(obj["namespace_id"]) if obj.get("namespace_id") else None
        )
        grants = uow.repo("grants").list(object_type=kind, object_id=obj["id"])
        if ns:
            grants += uow.repo("grants").list(object_type="namespace", object_id=ns["id"])
        return {
            "obj": {
                "type": cap_type or KINDS[kind][1],
                "id": obj["id"],
                "owner_id": obj.get("owner_id"),
                "state": state,
                "namespace_name": ns["name"] if ns else None,
            },
            "grants": grants,
            "namespace": ns,
        }

    def require(
        self,
        uow: Any,
        p: Principal,
        action: str,
        kind: str,
        obj: dict[str, Any],
        *,
        state: str | None = None,
        cap_type: str | None = None,
        audit: bool = True,
    ) -> None:
        d = self.describe(uow, kind, obj, state, cap_type)
        decision = can(p, action, d["obj"], d["grants"], d["namespace"])
        if not decision:
            label = obj.get("name", obj["id"])
            if audit:
                from maya.observability.metrics import METRICS

                METRICS.inc("maya_authz_denials_total", {"action": action})
            if audit and (
                action in ("approve", "pin", "seal", "grant", "revoke") or kind == "namespace"
            ):
                uow.audit(
                    "authz.denied",
                    object_type=kind,
                    object_ref=str(label),
                    detail={"action": action, "rule": decision.rule},
                    durable=True,
                )
            raise PermissionDenied(
                f"You may not {action} {kind} '{label}': {decision.rule}",
                action=action,
                rule=decision.rule,
            )

    def read_conditions(
        self, uow: Any, p: Principal, kind: str, obj: dict[str, Any]
    ) -> dict[str, Any]:
        """The §11.4 conditions under which ``p`` reads ``obj`` (empty: unconditioned)."""
        d = self.describe(uow, kind, obj)
        decision = can(p, "read", d["obj"], d["grants"], d["namespace"])
        return decision.conditions if decision.allowed else {}

    @staticmethod
    def user_context(p: Principal) -> dict[str, Any]:
        return {"username": p.username, "desk": p.desk}

    def allowed(
        self, uow: Any, p: Principal, action: str, kind: str, obj: dict[str, Any], **kw: Any
    ) -> bool:
        try:
            self.require(uow, p, action, kind, obj, audit=False, **kw)
            return True
        except PermissionDenied:
            return False

    def reader(self, uow: Any, p: Principal, kind: str) -> Any:
        """``keep(uow, obj)``: may ``p`` read ``obj``? — ``allowed(..., "read", kind, obj)``
        for a whole list, with the namespaces and grants loaded once rather than per row."""
        namespaces = {n["id"]: n for n in uow.repo("namespaces").list()}
        grants: dict[tuple[str, Any], list[dict[str, Any]]] = {}
        for g in uow.repo("grants").list(object_type__in=[kind, "namespace"]):
            grants.setdefault((g["object_type"], g["object_id"]), []).append(g)

        # Without grants of its own, an object's read decision depends only on its
        # namespace (grants, visibility, owner) and whether p owns it: decided once per
        # such pair, not once per row — a 20k-object total is then a scan, not 20k rules.
        decided: dict[tuple[Any, bool], bool] = {}

        def keep(_uow: Any, obj: dict[str, Any]) -> bool:
            own = grants.get((kind, obj["id"]))
            key = (obj.get("namespace_id"), obj.get("owner_id") == p.user_id)
            if own is None and key in decided:
                return decided[key]
            ns = namespaces.get(obj.get("namespace_id"))
            found = list(own or ())
            if ns:
                found += grants.get(("namespace", ns["id"]), [])
            view = {
                "type": KINDS[kind][1],
                "id": obj["id"],
                "owner_id": obj.get("owner_id"),
                "state": None,
                "namespace_name": ns["name"] if ns else None,
            }
            allowed = bool(can(p, "read", view, found, ns))
            if own is None:
                decided[key] = allowed
            return allowed

        def count(uow: Any, table: str, search: Any, filters: dict[str, Any]) -> int:
            """How many rows ``keep`` admits, counted by the database: rows without grants
            of their own by (namespace, owned) group, decided once per group; the few
            with their own grants one by one."""
            granted = [oid for (k, oid) in grants if k == kind]
            repo = uow.repo(table)
            total = sum(
                n
                for ns_id, owned, n in repo.owner_namespace_counts(
                    p.user_id, granted, search=search, **filters
                )
                if keep(
                    uow,
                    {"id": None, "namespace_id": ns_id, "owner_id": p.user_id if owned else None},
                )
            )
            if granted:
                rows = repo.slim(
                    ["id", "namespace_id", "owner_id"], search=search, id__in=granted, **filters
                )
                total += sum(1 for r in rows if keep(uow, r))
            return total

        keep.count = count  # type: ignore[attr-defined]
        return keep

    def require_capability(self, p: Principal, object_type: str, letter: str) -> None:
        if not p.has_capability(object_type, letter):
            raise PermissionDenied(f"Your roles carry no '{letter}' on {object_type}")

    # -- namespaces --------------------------------------------------------------
    def namespace(self, uow: Any, name: str) -> dict[str, Any]:
        ns = uow.repo("namespaces").find_one(name=name)
        if ns is None:
            raise NotFound(f"Namespace '{name}' does not exist", namespace=name)
        return ns

    def create_namespace(
        self,
        p: Principal,
        *,
        name: str,
        description: str = "",
        parent: str | None = None,
        preset: str = "standard",
        default_visibility: str = "namespace_read",
        production: bool = False,
        classification: str = "internal",
        quota_bytes: int | None = None,
    ) -> dict[str, Any]:
        self.require_capability(p, "namespace", "C")
        if preset not in PRESETS:
            raise ValidationFailed(f"Preset must be one of {', '.join(PRESETS)}")
        if not name.replace("_", "").replace(".", "").replace("-", "").isalnum():
            raise ValidationFailed("Namespace names use letters, digits, '_', '-' and '.'")
        with self.p.uow(p.username) as uow:
            if uow.repo("namespaces").find_one(name=name):
                raise ConflictError(f"Namespace '{name}' already exists")
            parent_id = None
            if parent:
                par = self.namespace(uow, parent)
                if par["parent_id"]:
                    raise ValidationFailed("Namespaces nest one level only (D-5)")
                parent_id = par["id"]
            ns = uow.repo("namespaces").add(
                {
                    "name": name,
                    "description": description,
                    "parent_id": parent_id,
                    "preset": preset,
                    "sod": PRESETS[preset]["sod"],
                    "default_visibility": default_visibility,
                    "production": production,
                    "classification": classification,
                    "quota_bytes": quota_bytes,
                    "owner_id": p.user_id,
                }
            )
            uow.audit(
                "namespace.created",
                object_type="namespace",
                object_ref=name,
                detail={"preset": preset, "production": production},
            )
            return ns

    def update_namespace(self, p: Principal, name: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.require_capability(p, "namespace", "U")
        allowed = {
            "description",
            "sod",
            "default_visibility",
            "quota_bytes",
            "classification",
            "production",
            "preset",
            "materialize_policy",
            "shadow_materiality",
        }
        bad = set(changes) - allowed
        if bad:
            raise ValidationFailed("Cannot change: " + ", ".join(sorted(bad)))
        if "sod" in changes and changes["sod"] not in ("strict", "two_person", "none"):
            raise ValidationFailed("sod must be strict, two_person or none")
        if (
            "materialize_policy" in changes
            and changes["materialize_policy"] not in MATERIALIZE_POLICIES
        ):
            raise ValidationFailed(
                "materialize_policy must be one of " + ", ".join(MATERIALIZE_POLICIES)
            )
        if (
            changes.get("shadow_materiality") is not None
            and float(changes["shadow_materiality"]) <= 0
        ):
            raise ValidationFailed(
                "shadow_materiality is the shift this namespace calls material; it is "
                "above zero, or unset to use the global default"
            )
        with self.p.uow(p.username) as uow:
            ns = self.namespace(uow, name)
            row = uow.repo("namespaces").update(ns["id"], changes)
            uow.audit("namespace.updated", object_type="namespace", object_ref=name, detail=changes)
            return row

    def ensure_scratch(self, uow: Any, p: Principal) -> dict[str, Any]:
        """Every user's zero-ceremony namespace (§28.1)."""
        name = f"scratch.{p.username}"
        ns = uow.repo("namespaces").find_one(name=name)
        if ns is None:
            ns = uow.repo("namespaces").add(
                {
                    "name": name,
                    "description": f"Personal scratch space of {p.username} — "
                    "ungoverned: no review, no approval, no SoD",
                    "preset": "small_team",
                    "sod": "none",
                    "default_visibility": "private",
                    "is_scratch": True,
                    "owner_id": p.user_id,
                    "classification": "internal",
                }
            )
            uow.audit("namespace.scratch_created", object_type="namespace", object_ref=name)
        return ns

    def list_namespaces(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            rows = uow.repo("namespaces").list(order_by=["name"])
            counts: dict[Any, dict[str, int]] = {}
            for tbl in ("features", "feature_sets", "models"):
                for r in uow.repo(tbl).list():
                    counts.setdefault(r["namespace_id"], {}).setdefault(tbl, 0)
                    counts[r["namespace_id"]][tbl] += 1
        for r in rows:
            r["counts"] = counts.get(r["id"], {})
        return rows

    # -- grants ------------------------------------------------------------------
    def resolve_object(self, kind: str, ref: str) -> dict[str, Any]:
        """The grantable object behind ``ref`` (a maya:// reference, a name or an id)."""
        from maya.services import catalog, refs as refmod

        if kind not in KINDS:
            raise ValidationFailed(f"Grants apply to {', '.join(KINDS)}")
        table = KINDS[kind][0]
        with self.p.uow() as uow:
            if kind == "namespace":
                return self.namespace(uow, ref)
            if kind in ("training_warrant", "execution_warrant"):
                return uow.repo(table).require(ref)
            obj, _ = catalog.find_object(uow, table, kind, refmod.parse(ref, kind))
            return obj

    def grant(
        self,
        p: Principal,
        *,
        kind: str,
        obj: dict[str, Any],
        principal_type: str,
        principal_id: str,
        level: str,
        days: int | None = 90,
        deny: bool = False,
        conditions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if level not in LEVELS:
            raise ValidationFailed(f"Level must be one of {', '.join(LEVELS)}")
        if principal_type not in ("user", "group", "role", "everyone"):
            raise ValidationFailed("principal_type must be user, group, role or everyone")
        if conditions:
            from maya.security.conditions import validate as validate_conditions

            validate_conditions(conditions)
        with self.p.uow(p.username) as uow:
            self.require(uow, p, "grant", kind, obj)
            if not p.is_admin and LEVELS.index(level) > LEVELS.index("own"):
                raise PermissionDenied("Only administrators grant 'admin'")
            if principal_type == "user":
                # grants are matched on the user id; a name typed in the UI would never match
                principal_id = self._user_id(uow, principal_id)
            if kind in ("feature", "featureset"):
                self._licence_allows(uow, kind, obj, principal_type, principal_id)
            inert = self._inert(uow, principal_type, principal_id, level, KINDS[kind][1])
            row = uow.repo("grants").add(
                {
                    "object_type": kind,
                    "object_id": obj["id"],
                    "principal_type": principal_type,
                    "principal_id": principal_id,
                    "level": level,
                    "deny": deny,
                    "expires_at": utcnow() + dt.timedelta(days=days) if days else None,
                    "conditions": conditions or {},
                    "inert_reason": inert,
                }
            )
            uow.audit(
                "access.granted",
                object_type=kind,
                object_ref=obj.get("name"),
                detail={
                    "to": f"{principal_type}:{principal_id}",
                    "level": level,
                    "deny": deny,
                    "inert": inert,
                },
            )
            return row

    def _licence_allows(
        self, uow: Any, kind: str, obj: dict[str, Any], ptype: str, pid: str
    ) -> None:
        from maya.services import refs as refmod

        ns = uow.repo("namespaces").require(obj["namespace_id"])
        ref = refmod.object_ref(kind, ns["name"], obj["name"])
        groups: list[str] = []
        desk = None
        if ptype == "user":
            holder = self.p.auth.build_principal(uow, pid)
            groups, desk = holder.groups, holder.desk
        try:
            self.p.licences.grantee(kind, ref, ptype, pid, groups, desk)
        except Exception as exc:
            if getattr(exc, "code", "") != "not_approved":
                raise

    @staticmethod
    def _user_id(uow: Any, who: str) -> str:
        user = uow.repo("users").find_one(id=who) if len(who) == 36 else None
        user = user or uow.repo("users").find_one(username=who)
        if user is None:
            raise NotFound(f"User '{who}' does not exist")
        return user["id"]

    def _inert(self, uow: Any, ptype: str, pid: str, level: str, cap_type: str) -> str | None:
        if ptype != "user":
            return None
        user = uow.repo("users").find_one(id=pid) or uow.repo("users").find_one(username=pid)
        if user is None:
            raise NotFound(f"User '{pid}' does not exist")
        principal = self.p.auth.build_principal(uow, user["id"])
        return inert_grant_reason(level, principal.capabilities, cap_type)

    def revoke_grant(self, p: Principal, grant_id: str) -> None:
        with self.p.uow(p.username) as uow:
            g = uow.repo("grants").require(grant_id)
            kind = g["object_type"]
            table = KINDS[kind][0]
            obj = uow.repo(table).require(g["object_id"])
            self.require(uow, p, "revoke", kind, obj)
            uow.repo("grants").delete(grant_id)
            uow.audit(
                "access.revoked",
                object_type=kind,
                object_ref=obj.get("name"),
                detail={"grant": g["principal_type"] + ":" + g["principal_id"]},
            )

    def grants_for(self, kind: str, obj_id: str) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("grants").list(object_type=kind, object_id=obj_id)

    def recertification(self, p: Principal) -> list[dict[str, Any]]:
        """Every grant on objects this user owns (§11.5 quarterly recertification)."""
        with self.p.uow() as uow:
            out = []
            for kind, (table, _) in KINDS.items():
                owned = (
                    uow.repo(table).list(owner_id=p.user_id)
                    if kind != "namespace"
                    else uow.repo(table).list(owner_id=p.user_id)
                )
                for obj in owned:
                    for g in uow.repo("grants").list(object_type=kind, object_id=obj["id"]):
                        out.append({**g, "object_name": obj["name"]})
            return out

    # -- users and roles -------------------------------------------------------------
    def create_user(
        self,
        p: Principal,
        *,
        username: str,
        password: str | None,
        email: str = "",
        display_name: str = "",
        roles: list[str] | None = None,
        is_service: bool = False,
        desk: str | None = None,
    ) -> dict[str, Any]:
        self.require_capability(p, "users", "C")
        if password:
            self.p.auth.check_policy(password)
        with self.p.uow(p.username) as uow:
            if uow.repo("users").find_one(username=username):
                raise ConflictError(f"User '{username}' already exists")
            user = uow.repo("users").add(
                {
                    "username": username,
                    "email": email,
                    "display_name": display_name or username,
                    "auth_source": "db",
                    "is_service": is_service,
                    "desk": desk,
                    "password_hash": kdf.hash_password(password) if password else None,
                    "must_change_password": bool(password),
                }
            )
            self._set_roles(uow, user["id"], roles or [])
            uow.audit("user.created", object_ref=f"user:{username}", detail={"roles": roles})
            return public_user(user)

    def set_roles(self, p: Principal, username: str, roles: list[str]) -> None:
        self.require_capability(p, "users", "U")
        with self.p.uow(p.username) as uow:
            user = uow.repo("users").find_one(username=username)
            if user is None:
                raise NotFound(f"User '{username}' does not exist")
            self._set_roles(uow, user["id"], roles)
            uow.audit("user.roles_changed", object_ref=f"user:{username}", detail={"roles": roles})

    def _set_roles(self, uow: Any, user_id: str, roles: list[str]) -> None:
        found = uow.repo("roles").list(name__in=roles) if roles else []
        missing = set(roles) - {r["name"] for r in found}
        if missing:
            raise ValidationFailed("Unknown role(s): " + ", ".join(sorted(missing)))
        uow.repo("user_roles").delete_where(user_id=user_id)
        for r in found:
            uow.repo("user_roles").add({"user_id": user_id, "role_id": r["id"]})

    def update_user(self, p: Principal, username: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.require_capability(p, "users", "U")
        allowed = {"email", "display_name", "status", "desk"}
        if set(changes) - allowed:
            raise ValidationFailed("Cannot change: " + ", ".join(set(changes) - allowed))
        with self.p.uow(p.username) as uow:
            user = uow.repo("users").find_one(username=username)
            if user is None:
                raise NotFound(f"User '{username}' does not exist")
            row = uow.repo("users").update(user["id"], changes)
            uow.audit("user.updated", object_ref=f"user:{username}", detail=changes)
            return public_user(row)

    def reset_password(self, p: Principal, username: str, new_password: str) -> None:
        self.require_capability(p, "users", "U")
        self.p.auth.check_policy(new_password)
        with self.p.uow(p.username) as uow:
            user = uow.repo("users").find_one(username=username)
            if user is None:
                raise NotFound(f"User '{username}' does not exist")
            uow.repo("users").update(
                user["id"],
                {
                    "password_hash": kdf.hash_password(new_password),
                    "must_change_password": True,
                    "failed_attempts": 0,
                    "locked_until": None,
                },
            )
            uow.audit("user.password_reset", object_ref=f"user:{username}")

    def list_users(self, p: Principal | None = None) -> list[dict[str, Any]]:
        """Administrators and techops see whole accounts; everyone else sees a directory
        (who exists, for delegation and grants) without lockout or password state."""
        with self.p.uow() as uow:
            users = uow.repo("users").list(order_by=["username"])
            roles = {r["id"]: r["name"] for r in uow.repo("roles").list()}
            links = uow.repo("user_roles").list()
        if p is not None and not (p.is_admin or "techops" in p.roles):
            return [{k: u.get(k) for k in DIRECTORY_FIELDS} for u in users]
        users = [public_user(u) for u in users]
        for u in users:
            u["roles"] = sorted(roles[lnk["role_id"]] for lnk in links if lnk["user_id"] == u["id"])
        return users

    def list_roles(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("roles").list(order_by=["name"])

    def create_role(
        self, p: Principal, name: str, description: str, capabilities: dict[str, str]
    ) -> dict[str, Any]:
        self.require_capability(p, "users", "C")
        for letters in capabilities.values():
            if set(letters) - set("CRUAPGQ"):
                raise ValidationFailed("Capabilities use the letters C R U A P G Q")
        with self.p.uow(p.username) as uow:
            if uow.repo("roles").find_one(name=name):
                raise ConflictError(f"Role '{name}' already exists")
            row = uow.repo("roles").add(
                {
                    "name": name,
                    "description": description,
                    "capabilities": capabilities,
                    "builtin": False,
                }
            )
            uow.audit("role.created", object_ref=f"role:{name}", detail=capabilities)
            return row

    def create_group(
        self,
        p: Principal,
        name: str,
        description: str = "",
        roles: list[str] | None = None,
        members: list[str] | None = None,
    ) -> dict[str, Any]:
        self.require_capability(p, "users", "C")
        with self.p.uow(p.username) as uow:
            group = uow.repo("groups").add({"name": name, "description": description})
            for r in uow.repo("roles").list(name__in=roles or []):
                uow.repo("group_roles").add({"group_id": group["id"], "role_id": r["id"]})
            for u in uow.repo("users").list(username__in=members or []):
                uow.repo("group_members").add({"group_id": group["id"], "user_id": u["id"]})
            uow.audit(
                "group.created",
                object_ref=f"group:{name}",
                detail={"roles": roles, "members": members},
            )
            return group

    def list_groups(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            groups = uow.repo("groups").list(order_by=["name"])
            users = {u["id"]: u["username"] for u in uow.repo("users").list()}
            roles = {r["id"]: r["name"] for r in uow.repo("roles").list()}
            for g in groups:
                g["members"] = sorted(
                    users[m["user_id"]] for m in uow.repo("group_members").list(group_id=g["id"])
                )
                g["roles"] = sorted(
                    roles[r["role_id"]] for r in uow.repo("group_roles").list(group_id=g["id"])
                )
            return groups

    # -- audit and inbox -------------------------------------------------------------
    def audit_log(
        self, p: Principal, *, limit: int = 1000, q: str | None = None, action: str | None = None
    ) -> list[dict[str, Any]]:
        if not (p.is_admin or "techops" in p.roles):
            raise PermissionDenied("The audit explorer is for administrators and techops")
        with self.p.uow() as uow:
            filters: dict[str, Any] = {}
            if action:
                filters["action__ilike"] = action
            return uow.repo("audit_events").list(
                order_by=["-seq"],
                limit=limit,
                search=(["actor", "action", "object_ref"], q or ""),
                **filters,
            )

    def audit_page(
        self,
        p: Principal,
        *,
        q: str | None = None,
        action: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        """The audit explorer, one keyset page at a time (newest first by default)."""
        from maya.services.paging import Listing, run_page

        if not (p.is_admin or "techops" in p.roles):
            raise PermissionDenied("The audit explorer is for administrators and techops")
        filters = {"action__ilike": action} if action else {}
        return run_page(
            self.p,
            lambda uow: Listing(
                "audit_events",
                {"-seq": "-seq", "seq": "seq"},
                "-seq",
                filters,
                (["actor", "action", "object_ref"], q or ""),
            ),
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            total=total,
        )

    def inbox_page(
        self,
        p: Principal,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        from maya.services.paging import Listing, run_page

        return run_page(
            self.p,
            lambda uow: Listing(
                "notifications",
                {"-created": "-created_at", "created": "created_at"},
                "-created",
                {"user_id": p.user_id},
            ),
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            total=total,
        )

    def grants_page(
        self,
        kind: str,
        obj_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        from maya.services.paging import Listing, run_page

        return run_page(
            self.p,
            lambda uow: Listing(
                "grants",
                {"created": "created_at", "-created": "-created_at"},
                "created",
                {"object_type": kind, "object_id": obj_id},
            ),
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            total=total,
        )

    def verify_audit(self) -> dict[str, Any]:
        with self.p.uow() as uow:
            return uow.repo("audit_events").verify_chain()

    def inbox(self, p: Principal) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("notifications").list(
                user_id=p.user_id, order_by=["-created_at"], limit=500
            )

    def mark_read(self, p: Principal, ids: list[str] | None = None) -> int:
        with self.p.uow(p.username) as uow:
            rows = uow.repo("notifications").list(user_id=p.user_id, read_at__isnull=True)
            n = 0
            for r in rows:
                if ids is None or r["id"] in ids:
                    uow.repo("notifications").update(r["id"], {"read_at": utcnow()})
                    n += 1
            return n
