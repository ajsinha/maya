"""
The authorization matrix suite (SC-7, §11, §23): every built-in role × every
object type × every action × every object state × every access context, with
zero unexpected allows and zero unexpected denies.

``can()`` is pure, so the matrix runs without a database. The expected decision
never comes from ``maya.security.authz``: it comes from an independent,
hand-typed restatement of the policy in this file — the capability letter
each action needs, what each ACL level permits, and a small oracle that
applies the evaluation order (role ceiling → API-key scope → frozen state →
scratch ownership → administrator → create → ACL: deny, user, group/role,
everyone, owner, namespace default). The role matrix itself is input data
imported from ``maya.security.roles``; a literal spot-check table pins the
policy down against drift in that matrix too.

Contexts cover a private namespace with no grant, ownership, both non-private
namespace defaults, an explicit user grant at every ACL level, an explicit
deny (which beats an ``everyone`` admin grant), role and group grants, a grant
to a role the principal does not hold, a user grant that out-ranks a stronger
role grant, an ``everyone`` grant, expired grants (ignored), and scratch
namespaces owned by someone else and by the principal. A smaller sub-matrix
does the same for API-key principals narrowed by action and namespace scope.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import itertools

from maya.security.authz import Principal, can, merge_capabilities
from maya.security.roles import MATRIX, OBJECT_TYPES

ME, OTHER = "u-me", "u-other"
PAST = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
FUTURE = dt.datetime(2999, 1, 1, tzinfo=dt.timezone.utc)

# ---- the policy, restated by hand (never imported from authz.py) -------------------------
NEEDS = {"read": "R", "download": "R", "create": "C", "update": "U", "submit": "U",
         "approve": "A", "pin": "P", "seal": "P", "request_pin": "Q", "grant": "G",
         "revoke": "G", "admin": "C"}
PERMITS = {
    "read": {"read", "download"},
    "read_write": {"read", "download", "update", "submit", "request_pin"},
    "approve": {"read", "download", "approve", "pin", "seal"},
    "own": {"read", "download", "update", "submit", "request_pin", "approve", "pin", "seal",
            "grant", "revoke"},
    "admin": {"read", "download", "create", "update", "submit", "approve", "pin", "seal",
              "request_pin", "grant", "revoke", "admin"},
}
RANK = ["read", "read_write", "approve", "own", "admin"]
FROZEN = {"sealed", "retired"}                    # read-only to everyone, admins included
WRITES = {"create", "update", "submit"}
REVIEWS = {"approve", "pin", "seal", "request_pin"}   # follow the role in non-private namespaces
STATES = [None, "draft", "in_review", "changes_requested", "approved", "published", "sealed",
          "retired"]


def g(ptype, pid, level="read", deny=False, expires=None):
    return {"principal_type": ptype, "principal_id": pid, "level": level, "deny": deny,
            "expires_at": expires, "conditions": {}}


def ctx(owner=OTHER, default="private", grants=(), scratch=None):
    ns = {"default_visibility": default}
    if scratch:
        ns.update(is_scratch=True, owner_id=scratch)
    return {"owner": owner, "ns": ns, "grants": list(grants)}


def contexts(role: str) -> dict[str, dict]:
    """Access contexts for a principal holding ``role`` (and group ``g-desk``)."""
    other_role = "techops" if role != "techops" else "admin"
    out = {
        "private_no_grant": ctx(),
        "owner": ctx(owner=ME),
        "ns_namespace_read": ctx(default="namespace_read"),
        "ns_public_read": ctx(default="public_read"),
        "user_deny_beats_everyone_admin": ctx(default="public_read", owner=ME, grants=[
            g("user", ME, deny=True), g("everyone", None, "admin")]),
        "role_grant_own": ctx(grants=[g("role", role, "own")]),
        "role_grant_other_role": ctx(grants=[g("role", other_role, "admin")]),
        "group_grant_approve": ctx(grants=[g("group", "g-desk", "approve")]),
        "other_group_grant": ctx(grants=[g("group", "g-else", "admin")]),
        "user_read_beats_role_admin": ctx(grants=[g("user", ME, "read"),
                                                  g("role", role, "admin")]),
        "everyone_read_write": ctx(grants=[g("everyone", None, "read_write")]),
        "other_user_admin": ctx(grants=[g("user", OTHER, "admin")]),
        "expired_user_admin": ctx(grants=[g("user", ME, "admin", expires=PAST)]),
        "expired_deny_live_read": ctx(grants=[g("user", ME, deny=True, expires=PAST),
                                              g("user", ME, "read", expires=FUTURE)]),
        "scratch_other_with_admin_grant": ctx(owner=ME, scratch=OTHER,
                                              grants=[g("user", ME, "admin")]),
        "scratch_mine_owned": ctx(owner=ME, scratch=ME),
        "scratch_mine_not_owned": ctx(scratch=ME),
    }
    for level in RANK:
        out[f"user_{level}"] = ctx(grants=[g("user", ME, level)])
    return out


N_CONTEXTS = 22


def oracle(roles, caps, action, otype, state, c, key=None, obj_ns="eq") -> bool:  # noqa: C901 - one branch per evaluation step, in order
    """The rule, restated: True when ``action`` should be allowed."""
    need = NEEDS.get(action)
    if need is None:
        return False
    held = caps.get(otype, "")
    if need not in held and not (need == "Q" and "P" in held):
        return False
    if key is not None:
        actions, namespaces = key
        if actions and action not in actions:
            return False
        if namespaces and obj_ns and obj_ns not in namespaces:
            return False
    if state in FROZEN and action in WRITES:
        return False
    ns = c["ns"]
    if ns.get("is_scratch") and ns["owner_id"] != ME and "admin" not in roles:
        return False
    if "admin" in roles or action == "create":
        return True
    live = [x for x in c["grants"] if x["expires_at"] is None or x["expires_at"] > NOW()]
    mine = [x for x in live if x["principal_type"] == "user" and x["principal_id"] == ME]
    if any(x["deny"] for x in mine):
        return False
    shared = [x for x in live if not x["deny"] and (
        (x["principal_type"] == "role" and x["principal_id"] in roles)
        or (x["principal_type"] == "group" and x["principal_id"] == "g-desk"))]
    everyone = [x for x in live if x["principal_type"] == "everyone" and not x["deny"]]
    for tier in (mine, shared, everyone):
        if tier:
            return action in PERMITS[max((x["level"] for x in tier), key=RANK.index)]
    if c["owner"] == ME:
        return action in PERMITS["own"]
    if ns["default_visibility"] in ("namespace_read", "public_read"):
        return action in REVIEWS or action in PERMITS["read"]
    return False


def NOW():
    return dt.datetime.now(dt.timezone.utc)


def principal(role, key=None) -> Principal:
    p = Principal(user_id=ME, username="me", roles=[role],
                  capabilities=merge_capabilities([MATRIX[role]]), groups=["g-desk"])
    if key is not None:
        p.principal_type = "api_key"
        p.key_actions, p.key_namespaces = list(key[0]), list(key[1])
    return p


def decide(role, action, otype, state, c, key=None, obj_ns="eq") -> bool:
    obj = {"type": otype, "id": "o-1", "owner_id": c["owner"], "state": state}
    if obj_ns:
        obj["namespace_name"] = obj_ns
    return bool(can(principal(role, key), action, obj, grants=[dict(x) for x in c["grants"]],
                    namespace=dict(c["ns"])))


def _report(mismatches: list[str], total: int) -> str:
    head = f"{len(mismatches)} of {total} decisions disagree with the policy:\n  "
    return head + "\n  ".join(mismatches[:60]) + ("\n  …" if len(mismatches) > 60 else "")


# ---- the inputs themselves must not silently shrink ----------------------------------------
def test_matrix_inputs_are_complete():
    assert sorted(MATRIX) == sorted(["admin", "feature_designer", "feature_manager",
                                     "model_designer", "model_developer", "model_manager",
                                     "model_owner", "techops"])
    assert len(OBJECT_TYPES) == 13
    from maya.security.authz import ACTION_LETTER
    assert ACTION_LETTER == NEEDS, "an action was added or re-lettered; restate it here"
    assert len(contexts("admin")) == N_CONTEXTS


# ---- the full matrix -------------------------------------------------------------------------
def test_full_matrix_zero_unexpected_allows_or_denies():
    total, mismatches = 0, []
    tally = {r: [0, 0] for r in MATRIX}
    for role in MATRIX:
        caps, cs = merge_capabilities([MATRIX[role]]), contexts(role)
        for otype, action, state, (cname, c) in itertools.product(
                OBJECT_TYPES, NEEDS, STATES, cs.items()):
            want = oracle([role], caps, action, otype, state, c)
            got = decide(role, action, otype, state, c)
            total += 1
            tally[role][got] += 1
            if got != want:
                kind = "UNEXPECTED ALLOW" if got else "unexpected deny"
                mismatches.append(f"{kind}: {role} {action} {otype} state={state} ctx={cname}")
    assert total == 8 * 13 * 12 * 8 * N_CONTEXTS == 219648
    assert not mismatches, _report(mismatches, total)
    for role, (denies, allows) in tally.items():
        assert allows and denies, f"{role}: {allows} allows, {denies} denies"


# ---- API keys: the same rule, narrowed by action and namespace scope --------------------------
KEYS = {
    "unscoped": ((), ()),
    "read_only": (("read", "download"), ()),
    "namespace_eq": ((), ("eq",)),
    "namespace_fx": ((), ("fx",)),
    "update_in_fx": (("update", "read"), ("fx",)),
}


def test_api_key_sub_matrix():
    total, mismatches = 0, []
    tally = {k: [0, 0] for k in KEYS}
    picked = ("private_no_grant", "owner", "user_admin", "ns_public_read",
              "scratch_other_with_admin_grant")
    for role in MATRIX:
        caps, cs = merge_capabilities([MATRIX[role]]), contexts(role)
        for otype, action, state, cname, (kname, key), obj_ns in itertools.product(
                OBJECT_TYPES, NEEDS, (None, "draft", "sealed"), picked, KEYS.items(),
                ("eq", None)):
            want = oracle([role], caps, action, otype, state, cs[cname], key, obj_ns)
            got = decide(role, action, otype, state, cs[cname], key, obj_ns)
            total += 1
            tally[kname][got] += 1
            if got != want:
                kind = "UNEXPECTED ALLOW" if got else "unexpected deny"
                mismatches.append(f"{kind}: key={kname} {role} {action} {otype} "
                                  f"state={state} ctx={cname} ns={obj_ns}")
    assert total == 8 * 13 * 12 * 3 * 5 * 5 * 2 == 187200
    assert not mismatches, _report(mismatches, total)
    for kname, (denies, allows) in tally.items():
        assert allows and denies, f"key {kname}: {allows} allows, {denies} denies"


def test_api_key_scope_never_widens():
    """A key can only narrow its user: nothing a key allows is denied to the bare user."""
    for role in MATRIX:
        for cname, c in contexts(role).items():
            for otype, action, (_, key) in itertools.product(OBJECT_TYPES, NEEDS,
                                                            KEYS.items()):
                if decide(role, action, otype, "draft", c, key):
                    assert decide(role, action, otype, "draft", c), (role, action, otype,
                                                                      cname, key)


# ---- literal spot checks: pin the policy against drift in MATRIX itself ----------------------
SPOT = [  # role, object type, action, state, context, allowed
    ("feature_designer", "feature", "approve", "in_review", "ns_namespace_read", False),
    ("feature_designer", "feature", "create", None, "private_no_grant", True),
    ("feature_manager", "feature", "approve", "in_review", "ns_namespace_read", True),
    ("feature_manager", "feature", "create", None, "user_admin", False),
    ("feature_manager", "feature_pin", "request_pin", "approved", "user_read_write", True),
    ("feature_designer", "feature_pin", "pin", "approved", "user_admin", False),
    ("admin", "feature", "update", "sealed", "owner", False),
    ("admin", "feature", "update", "draft", "user_deny_beats_everyone_admin", True),
    ("admin", "model", "update", "retired", "user_admin", False),
    ("model_designer", "model", "update", "retired", "owner", False),
    ("model_designer", "model", "update", "draft", "owner", True),
    ("model_designer", "model", "update", "draft", "ns_public_read", False),
    ("model_designer", "model", "read", "draft", "user_deny_beats_everyone_admin", False),
    ("techops", "jobs", "create", None, "private_no_grant", True),
    ("techops", "users", "update", None, "user_admin", False),
    ("model_owner", "model", "grant", "approved", "owner", True),
    ("model_owner", "model", "grant", "approved", "ns_namespace_read", False),
    ("model_owner", "model", "update", "draft", "owner", False),
    ("admin", "users", "admin", None, "private_no_grant", True),
    ("feature_manager", "feature", "admin", None, "user_admin", False),
    ("model_designer", "model", "admin", None, "user_admin", True),
    ("feature_designer", "artifact", "read", None, "owner", False),
    ("model_developer", "featureset", "update", "draft", "user_read", False),
    ("model_developer", "featureset", "update", "draft", "user_read_write", True),
    ("model_developer", "featureset", "update", "draft", "user_read_beats_role_admin", False),
    ("model_manager", "execution_warrant", "create", "sealed", "private_no_grant", False),
    ("feature_designer", "feature", "update", "draft", "scratch_other_with_admin_grant", False),
    ("feature_designer", "feature", "update", "draft", "expired_user_admin", False),
    ("feature_designer", "feature", "read", "draft", "expired_deny_live_read", True),
    ("feature_designer", "feature", "read", "draft", "private_no_grant", False),
]


def test_spot_checks():
    bad = []
    for role, otype, action, state, cname, allowed in SPOT:
        c = contexts(role)[cname]
        got = decide(role, action, otype, state, c)
        want = oracle([role], merge_capabilities([MATRIX[role]]), action, otype, state, c)
        if got is not allowed or want is not allowed:
            bad.append(f"{role} {action} {otype} {state} {cname}: expected {allowed}, "
                       f"can()={got}, oracle={want}")
    assert not bad, "\n".join(bad)


def test_unknown_actions_are_denied():
    everything = merge_capabilities(list(MATRIX.values()))
    p = Principal(user_id=ME, username="me", roles=list(MATRIX), capabilities=everything)
    for action in ("delete", "", "READ", "execute", "approve ", "*", "own"):
        for otype in OBJECT_TYPES:
            d = can(p, action, {"type": otype, "id": "o", "owner_id": ME},
                    grants=[g("user", ME, "admin")], namespace={"default_visibility":
                                                                "public_read"})
            assert not d, (action, otype, d.rule)
