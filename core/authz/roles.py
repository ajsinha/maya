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
    # The first line states what the model cannot do — they are the ones who
    # know. Withdrawing a limitation makes the register say less than it did,
    # so it is not theirs.
    "limitation:read", "limitation:record",
    "assumption:read", "assumption:record",
    # A developer or owner may ASK for a control to be relaxed. Only
    # the second line may grant it.
    "waiver:read", "waiver:propose",
    "feature:read", "feature:define", "feature:materialise", "feature:assemble",
    "feature:contract", "validation:read", "finding:read", "evidence:read",
    # A finding can be owned by whoever has to fix it, and the first line does
    # most of the fixing: accept what is yours and write down what you will do.
    # Never extend — that is the one act the person with the deadline may not do.
    "finding:acknowledge", "finding:plan",
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
    "warrant:issue", "warrant:resolve", "warrant:execute", "finding:raise",
    # The owner hands remediation to whoever will do it, on the record. They
    # still cannot move the date it is due.
    "finding:assign",
    # The owner puts the record forward, opens amendments to it, and signs the
    # owner half of the attestation. They never approve it.
    "model:submit", "model:amend", "model:attest", "baseline:plan",
    # Defines the monitors on its own models and evaluates them. It does NOT
    # deliver the telemetry they are evaluated against: the owner is the party
    # the monitor judges, and a principal that both supplies the population and
    # scores it has been left to mark its own work.
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
    # Extension sits in the second line and nowhere else. Moving a remediation
    # date is the moment somebody independent asks whether the date was ever
    # realistic, and the first line asking itself is not that moment.
    "finding:extend", "finding:assign", "finding:acknowledge", "finding:plan",
    # The second line accepts or rejects what the first line filed -- and
    # approves the parameters it fitted, which change what the model does.
    "document:review", "parameter:approve", "version:sign",
    # Withdrawing a limitation makes the register say less than it did about an
    # immutable version, so it is the second line's, not the first's.
    "limitation:withdraw",
    "assumption:withdraw",
    "waiver:approve", "waiver:revoke",
    "feature:seal", "featureset:seal",
    # Writing a gate and putting it in force are different acts, so a validator
    # drafts and the model risk manager publishes. A rule authored and enacted
    # by one person is a rule nobody reviewed.
    "policy:read", "policy:author",
    # The second line asks the machine for a draft and attests what it produced.
    "assist:generate", "assist:attest",
}
MODEL_RISK_MANAGER = VALIDATOR | {
    # The second line owns the interface to legal and compliance,
    # so it places holds. Reading them needs only `evidence:read`.
    "hold:place",
    "risk:assess", "version:approve", "alias:move",
    "feature:certify", "warrant:revoke", "model:retire",
    # Approves the record, and signs the second-line half of the attestation.
    # Cannot submit or amend: that is the first line's act.
    "model:approve", "model:attest", "monitor:define", "document:compile",
    "overlay:approve", "assist:register", "assist:attest",
    "document:review", "parameter:approve", "version:sign",
    # Withdrawing a limitation makes the register say less than it did about an
    # immutable version, so it is the second line's, not the first's.
    "limitation:withdraw",
    "assumption:withdraw",
    "waiver:approve", "waiver:revoke",
    "baseline:import", "baseline:plan", "regime:activate",
    "policy:publish",
    # Cutting the pack a committee is minuted against sits with the second line,
    # beside publishing a gate: both are acts that fix what the estate is
    # measured by. Reading one is a `:read` and every role already holds it.
    "report:cut",
}

# ---------------------------------------------------------------------------
# Third line and beyond: read, raise, never remediate.
# ---------------------------------------------------------------------------
AUDITOR = READ_PERMISSIONS | {"finding:raise"}
# The batch runner: it evaluates monitors on a schedule and can do nothing else.
OPERATOR = {"model:read", "warrant:read", "evidence:read",
            # Reads what a model cannot do, because that is what decides
            # whether an operational question belongs to this model at all.
            "limitation:read",
            # Evaluates on the schedule. Never delivers telemetry -- it does
            # not run the models and has no rows of its own to hand over.
            "monitor:read", "monitor:evaluate",
            # The operator runs the schedule. Every job is idempotent and derives
            # its own work, so this is an operational act and not a governance one.
            "scheduler:read", "scheduler:run",
            # Diagnosing the platform is the operator's job, and it is the one
            # role whose members are woken up to do it.
            "log:read"}
SERVICE = {"model:read", "warrant:read", "warrant:resolve", "warrant:execute",
           # The principal that runs the model is the one holding the scores, so
           # it hands them over -- and stops there. Deciding that a monitor has
           # breached is a governance act, and an execution engine that could
           # both produce the population and rule on it would be the only
           # witness to its own model's behaviour.
           "monitor:observe",
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
    # The pair the list was missing, and the plainest one in SR 11-7: effective
    # challenge means somebody other than the builder runs it. `validator` is
    # described in this very file as "Second line ... Never builds", and nothing
    # enforced it — a developer could hold it, open the validation of the version
    # they wrote, record its results and conclude it.
    ("model_developer", "validator",
     "effective challenge is not effective when the builder runs it: a developer "
     "holding validator concludes the challenge of their own version"),
    ("model_owner", "validator",
     "an owner who can also conclude their model's validation is signing off "
     "their own challenge"),
    ("model_owner", "model_risk_manager",
     "an owner who can also approve and tier their own models defeats second-line challenge"),
    ("model_developer", "auditor",
     "the third line must not build what it audits"),
    ("model_owner", "auditor",
     "the third line must not own what it audits"),
)


def validate_definitions() -> None:
    """Every permission named in every role must be a real one."""
    for _role, permissions in ROLES.items():
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
