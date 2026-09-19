"""
Authorization: ``can(principal, action, obj) -> Decision`` (§11).

This is the single function every surface calls. It is pure — the caller
supplies the principal, the object and the grants that apply to it — so it
can be tested exhaustively (the authorization matrix suite, SC-7) without a
database.

Order of evaluation:

1. **Role ceiling.** The action's capability letter must be held by one of
   the principal's roles for this object type. An ACL can never exceed it.
2. **API-key scope.** A key's namespace and action allowlists narrow further.
3. **Object state.** Sealed, pinned and retired objects are read-only to
   everyone, including their owner and administrators.
4. **Administrators** pass once the ceiling and state checks have.
5. **ACL resolution**, deny wins then the most specific grant (§11.2):
   explicit deny → user grant → highest group/role grant → ``everyone`` →
   ownership → namespace default → deny.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

# action -> capability letter required by the role ceiling
ACTION_LETTER = {
    "read": "R",
    "download": "R",
    "create": "C",
    "update": "U",
    "submit": "U",
    "approve": "A",
    "pin": "P",
    "seal": "P",
    "request_pin": "Q",
    "grant": "G",
    "revoke": "G",
    "admin": "C",
}
# action -> minimum ACL level (Appendix B)
LEVELS = ("read", "read_write", "approve", "own", "admin")
LEVEL_ALLOWS = {
    "read": {"read", "download"},
    "read_write": {"read", "download", "update", "submit", "request_pin"},
    "approve": {"read", "download", "approve", "pin", "seal"},
    "own": {
        "read",
        "download",
        "update",
        "submit",
        "request_pin",
        "approve",
        "pin",
        "seal",
        "grant",
        "revoke",
    },
    "admin": set(ACTION_LETTER),
}
WRITE_ACTIONS = {"update", "submit", "create"}
FROZEN_STATES = {"sealed", "retired"}
REVIEW_ACTIONS = {"approve", "pin", "seal", "request_pin"}


@dataclass
class Principal:
    """Who is asking. Built once per request by the authentication layer."""

    user_id: str
    username: str
    roles: list[str]
    capabilities: dict[str, str]
    groups: list[str] = field(default_factory=list)
    principal_type: str = "user"
    channel: str = "api"
    key_namespaces: list[str] = field(default_factory=list)
    key_actions: list[str] = field(default_factory=list)
    desk: str | None = None

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    def has_capability(self, object_type: str, letter: str) -> bool:
        return letter in self.capabilities.get(object_type, "")


@dataclass
class Decision:
    allowed: bool
    rule: str
    # the §11.4 conditions of the grant that decided a read; empty means unconditioned
    conditions: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.allowed


def merge_capabilities(role_caps: list[dict[str, str]]) -> dict[str, str]:
    """Union of the capability letters of several roles."""
    merged: dict[str, set[str]] = {}
    for caps in role_caps:
        for obj_type, letters in caps.items():
            merged.setdefault(obj_type, set()).update(letters)
    return {k: "".join(sorted(v)) for k, v in merged.items()}


def can(
    p: Principal,
    action: str,
    obj: dict[str, Any],
    grants: list[dict[str, Any]] | None = None,
    namespace: dict[str, Any] | None = None,
) -> Decision:
    """Decide whether ``p`` may take ``action`` on ``obj``.

    ``obj`` carries ``type`` (capability object type), ``id``, and optionally
    ``owner_id``, ``state``, ``namespace_id``.
    """
    letter = ACTION_LETTER.get(action)
    if letter is None:
        return Decision(False, f"unknown action '{action}'")
    obj_type = obj["type"]
    if not p.has_capability(obj_type, letter) and not (
        letter == "Q" and p.has_capability(obj_type, "P")
    ):
        return Decision(
            False,
            f"role ceiling: no '{letter}' on {obj_type} in roles {', '.join(p.roles) or '(none)'}",
        )
    scope = _key_scope(p, action, obj)
    if scope is not None:  # a Decision(False) is falsy: test identity, not truth
        return scope
    if obj.get("state") in FROZEN_STATES and action in WRITE_ACTIONS:
        return Decision(False, f"object is {obj['state']}: read-only to everyone")
    if (
        namespace
        and namespace.get("is_scratch")
        and namespace.get("owner_id") != p.user_id
        and not p.is_admin
    ):
        return Decision(False, "scratch namespaces belong to their owner alone")
    if p.is_admin:
        return Decision(True, "admin role")
    if action == "create":
        return Decision(True, "role capability to create")
    return _acl(p, action, obj, grants or [], namespace)


def _key_scope(p: Principal, action: str, obj: dict[str, Any]) -> Decision | None:
    if p.principal_type != "api_key":
        return None
    if p.key_actions and action not in p.key_actions:
        return Decision(False, f"API key does not allow '{action}'")
    ns = obj.get("namespace_name")
    if p.key_namespaces and ns and ns not in p.key_namespaces:
        return Decision(False, f"API key is not scoped to namespace '{ns}'")
    return None


def _live(grants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    return [g for g in grants if g.get("expires_at") is None or g["expires_at"] > now]


def _acl(
    p: Principal,
    action: str,
    obj: dict[str, Any],
    grants: list[dict[str, Any]],
    namespace: dict[str, Any] | None,
) -> Decision:
    grants = _live(grants)
    mine = [g for g in grants if g["principal_type"] == "user" and g["principal_id"] == p.user_id]
    if any(g.get("deny") for g in mine):
        return Decision(False, "explicit deny for this user")
    if mine:
        return _granted(action, mine, "user grant")
    shared = [
        g
        for g in grants
        if not g.get("deny")
        and (
            (g["principal_type"] == "group" and g["principal_id"] in p.groups)
            or (g["principal_type"] == "role" and g["principal_id"] in p.roles)
        )
    ]
    if shared:
        return _granted(action, shared, "group/role grant")
    everyone = [g for g in grants if g["principal_type"] == "everyone" and not g.get("deny")]
    if everyone:
        return _granted(action, everyone, "everyone grant")
    if obj.get("owner_id") and obj["owner_id"] == p.user_id:
        return _level_decision(action, "own", "owner")
    default = (namespace or {}).get("default_visibility", "private")
    if default == "public_read" or (default == "namespace_read" and belongs(p, namespace)):
        # Review actions follow the role, not a per-object grant: in a namespace
        # whose default is not private, a holder of the role capability (checked
        # above as the ceiling) may approve, pin and seal. Editing still needs
        # ownership or an explicit grant, and an explicit deny still wins.
        if action in REVIEW_ACTIONS:
            return Decision(True, f"namespace default ({default}) + role capability")
        return _level_decision(action, "read", f"namespace default ({default})")
    if default == "namespace_read":
        return Decision(False, "namespace is readable by its own people, and you are not one")
    return Decision(False, "no grant and namespace is private")


def belongs(p: Principal, namespace: dict[str, Any] | None) -> bool:
    """Whether ``p`` is one of this namespace's people — what `namespace_read` means, and
    what makes it different from `public_read` (§11.1).

    MAYA has no membership list; a namespace declares the roles it is set up for (its
    preset), and it has an owner. So belonging is: an administrator, the namespace's
    owner, or a holder of a role that namespace expects. Someone signed in with roles the
    namespace does not use — another desk's developer, a service account scoped
    elsewhere — is not one of its people, and `namespace_read` no longer reads to them as
    `public_read` did. An explicit grant is decided before this and still lets anyone in.
    """
    if namespace is None:
        return False
    if p.is_admin or (namespace.get("owner_id") and namespace["owner_id"] == p.user_id):
        return True
    from maya.security.roles import PRESETS

    # a namespace always carries a preset; a view built without one reads as the default
    expected = set(PRESETS.get(namespace.get("preset") or "standard", {}).get("roles") or [])
    return bool(expected & set(p.roles))


def _granted(action: str, grants: list[dict[str, Any]], via: str) -> Decision:
    """Decide by the strongest grant; its conditions (combined if tied) ride along."""
    from maya.security.conditions import combine

    best = _best(grants)
    decision = _level_decision(action, best, via)
    if decision.allowed:
        decision.conditions = combine(
            [g.get("conditions") or {} for g in grants if g["level"] == best]
        )
    return decision


def _best(grants: list[dict[str, Any]]) -> str:
    return max((g["level"] for g in grants), key=LEVELS.index)


def _level_decision(action: str, level: str, via: str) -> Decision:
    if action in LEVEL_ALLOWS.get(level, set()):
        return Decision(True, f"{via}: {level}")
    return Decision(False, f"{via}: level '{level}' does not permit '{action}'")


def inert_grant_reason(level: str, holder_caps: dict[str, str], object_type: str) -> str | None:
    """A grant beyond the holder's role ceiling is inert; say so at creation (§11.2)."""
    needed = {"read_write": "U", "approve": "A", "own": "G", "admin": "C"}.get(level)
    if needed and needed not in holder_caps.get(object_type, ""):
        return (
            f"inert: the holder's roles carry no '{needed}' on {object_type}, so a "
            f"'{level}' grant cannot give them that capability"
        )
    return None
