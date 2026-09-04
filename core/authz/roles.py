"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Roles, and the three lines of defence they encode.

A bank's model risk framework is organised around who may do what to a model,
and the organising principle is the three lines: the first line builds and owns,
the second line challenges and approves, the third line audits and cannot touch
anything.

These roles are that structure made executable. They are deliberately few. A
permission system with forty roles is one nobody can reason about, and the
question that matters at an audit — "who could have approved this?" — becomes
unanswerable.

Roles compose: a principal holds a set, and their permissions are the union.
That is how a small firm gives one person two hats, visibly, rather than
inventing a hybrid role that hides the fact.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, List, Set

from core.authz.common import PERMISSIONS, READ_PERMISSIONS, AuthzError, require_known

# ---------------------------------------------------------------------------
# First line: build, own, operate.
# ---------------------------------------------------------------------------
MODEL_DEVELOPER = {
    "model:read", "version:create",
    "feature:read", "feature:define", "feature:materialise", "feature:assemble",
    "feature:contract", "validation:read", "finding:read", "evidence:read",
    # The first line reads everything about its own models. Being able to act
    # on something you cannot read is a permission set nobody can reason about.
    "warrant:read", "monitor:read", "document:read", "overlay:read",
    "document:attach", "featureset:define", "featureset:publish",
    "parameter:record",
    "assist:read", "assist:generate", "baseline:read", "regime:read",
    "scheduler:read",
}
MODEL_OWNER = MODEL_DEVELOPER | {
    "model:register", "model:retire", "risk:assess",
    "warrant:issue", "warrant:execute", "finding:raise",
    # The owner puts the record forward, opens amendments to it, and signs the
    # owner half of the attestation. They never approve it.
    "model:submit", "model:amend", "model:attest", "baseline:plan",
    "monitor:define", "monitor:evaluate", "document:compile",
    # The first line proposes an adjustment and measures it. It never approves
    # its own, and never renews it.
    "overlay:propose", "overlay:measure",
}

# ---------------------------------------------------------------------------
# Second line: challenge, approve, tier. Never builds.
# ---------------------------------------------------------------------------
VALIDATOR = READ_PERMISSIONS | {
    "validation:open", "validation:record", "validation:conclude",
    "finding:raise", "finding:close", "document:compile",
    # The second line accepts or rejects what the first line filed -- and
    # approves the parameters it fitted, which change what the model does.
    "document:review", "parameter:approve", "version:sign",
    # The second line asks the machine for a draft and attests what it produced.
    "assist:generate", "assist:attest",
}
MODEL_RISK_MANAGER = VALIDATOR | {
    "risk:assess", "version:approve", "alias:move",
    "feature:certify", "warrant:revoke", "model:retire",
    # Approves the record, and signs the second-line half of the attestation.
    # Cannot submit or amend: that is the first line's act.
    "model:approve", "model:attest", "monitor:define", "document:compile",
    "overlay:approve", "assist:register", "assist:attest",
    "document:review", "parameter:approve", "version:sign",
    "baseline:import", "baseline:plan", "regime:activate",
}

# ---------------------------------------------------------------------------
# Third line and beyond: read, raise, never remediate.
# ---------------------------------------------------------------------------
AUDITOR = READ_PERMISSIONS | {"finding:raise"}
# The batch runner: it evaluates monitors on a schedule and can do nothing else.
OPERATOR = {"model:read", "warrant:read", "evidence:read",
            "monitor:read", "monitor:evaluate",
            # The operator runs the schedule. Every job is idempotent and derives
            # its own work, so this is an operational act and not a governance one.
            "scheduler:read", "scheduler:run"}
SERVICE = {"model:read", "warrant:read", "warrant:execute", "monitor:evaluate",
           # Read alongside run: acting on something you cannot read back is a
           # permission set nobody can reason about.
           "scheduler:run", "scheduler:read"}

ROLES: Dict[str, Set[str]] = {
    "model_developer": MODEL_DEVELOPER,
    "model_owner": MODEL_OWNER,
    "validator": VALIDATOR,
    "model_risk_manager": MODEL_RISK_MANAGER,
    "auditor": AUDITOR,
    "operator": OPERATOR,
    "service": SERVICE,
    # Bootstrap and break-glass. Deliberately last, deliberately obvious.
    "admin": set(PERMISSIONS),
}

DESCRIPTIONS: Dict[str, str] = {
    "model_developer": "Builds models and features. Cannot approve, tier or validate.",
    "model_owner": "Owns a model end to end: registers it, requests its tier, issues warrants.",
    "validator": "Second line. Runs effective challenge and closes findings. Never builds.",
    "model_risk_manager": "Second line with authority: approves versions, moves aliases, sets tiers.",
    "auditor": "Third line. Reads everything, raises findings, remediates nothing.",
    "operator": "Runs the platform and the monitoring batch. No governance authority.",
    "service": "A non-human principal. Resolves and executes warrants; signs in to nothing.",
    "admin": "Everything, including principal management. For bootstrap and break-glass.",
}

# Roles nobody should hold together, and why. Held as data so the constraint is
# inspectable rather than buried in a conditional.
INCOMPATIBLE_ROLES = (
    ("model_developer", "model_risk_manager",
     "a developer who can also approve versions is a first line approving its own work"),
    ("model_owner", "model_risk_manager",
     "an owner who can also approve and tier their own models defeats second-line challenge"),
    ("model_developer", "auditor",
     "the third line must not build what it audits"),
    ("model_owner", "auditor",
     "the third line must not own what it audits"),
)


def validate_definitions() -> None:
    """Every permission named in every role must be a real one."""
    for role, permissions in ROLES.items():
        for p in permissions:
            require_known(p)


def permissions_for(roles: Iterable[str]) -> FrozenSet[str]:
    """The union of a principal's roles. Unknown roles are refused, not ignored."""
    granted: Set[str] = set()
    for role in roles:
        if role not in ROLES:
            raise AuthzError("unknown_role", f"'{role}' is not a recognised role",
                             f"known roles are {', '.join(sorted(ROLES))}")
        granted |= ROLES[role]
    return frozenset(granted)


def conflicts(roles: Iterable[str]) -> List[str]:
    """Which incompatible pairs this set of roles holds together."""
    held = set(roles)
    if "admin" in held:
        return []          # break-glass is a conscious exception, not an accident
    return [reason for a, b, reason in INCOMPATIBLE_ROLES if a in held and b in held]


validate_definitions()
