"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The authorisation vocabulary.

Permissions are ``resource:act`` strings rather than an enum, so a new resource
does not require a schema change — but the full set is enumerated here, and a
permission not in it is refused rather than silently granted. A typo in a role
definition must fail loudly; the alternative is a role that quietly grants
nothing and a user who quietly cannot work.
"""
from __future__ import annotations

from typing import FrozenSet


class AuthzError(RuntimeError):
    """An act was refused on authorisation grounds. The message says which."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation


# Every permission the platform recognises, grouped by the resource it acts on.
PERMISSIONS: FrozenSet[str] = frozenset({
    # the register
    "model:read", "model:register", "model:retire", "model:delete",
    "model:submit", "model:approve", "model:attest", "model:amend",
    "version:create", "version:approve",
    "alias:move",
    "risk:assess",
    # the feature platform
    "feature:read", "feature:define", "feature:certify",
    "feature:materialise", "feature:contract", "feature:assemble",
    # execution
    "warrant:read", "warrant:issue", "warrant:revoke", "warrant:execute",
    # Obtaining a signed descriptor is not the same act as reading which grants
    # exist. It was authorised as `warrant:read` -- which sits in the read set
    # and is therefore held by every role, the auditor included -- so any
    # authenticated principal could mint a production execution credential.
    "warrant:resolve",
    # assurance
    "validation:read", "validation:open", "validation:record", "validation:conclude",
    "finding:read", "finding:raise", "finding:close",
    # The workflow between raising a finding and closing it. `finding:extend` is
    # deliberately apart from the other three: accepting a finding and planning
    # it are the first line's acts, and moving the date it is due is not — an
    # owner who could extend their own deadline has no deadline.
    "finding:assign", "finding:acknowledge", "finding:plan", "finding:extend",
    "monitor:read", "monitor:define", "monitor:evaluate",
    # Taking delivery of telemetry is not the same act as judging it. The
    # principal that scores has the rows and should be able to hand them over
    # without also being able to decide that a monitor has breached.
    "monitor:observe",
    "document:read", "document:compile",
    "document:attach", "document:review",
    # features, featuresets and the parameters a fit produces
    "featureset:define", "featureset:publish",
    # Sealing is a distinct act: it makes something final, and
    # whoever may define a thing is not automatically who may end it.
    "feature:seal", "featureset:seal",
    # Authoring a gate and putting it in force are separate duties.
    "policy:read", "policy:author", "policy:publish",
    # Signing a quorum is not the same act as approving alone: a
    # validator signs one and may never do the other.
    "version:sign",
    "parameter:record", "parameter:approve",
    "overlay:read", "overlay:propose", "overlay:approve", "overlay:measure",
    "assist:read", "assist:register", "assist:generate", "assist:attest",
    "baseline:read", "baseline:import", "baseline:plan",
    "regime:read", "regime:activate",
    "scheduler:read", "scheduler:run",
    "evidence:read",
    # Portfolio reporting. Reading a board pack is a `:read` and therefore in
    # every role's set, which is right — a pack is what the estate is told about
    # itself. Cutting one is not: a recorded pack is the document a committee is
    # minuted against, so producing it is an act rather than a view.
    "report:read", "report:cut",
    # the platform itself
    "principal:read", "principal:manage",
})

READ_PERMISSIONS: FrozenSet[str] = frozenset(
    p for p in PERMISSIONS if p.endswith(":read"))


def require_known(permission: str) -> str:
    """Reject an unrecognised permission at definition time, not at use."""
    if permission not in PERMISSIONS:
        raise AuthzError("unknown_permission",
                         f"'{permission}' is not a recognised permission",
                         "check the spelling against core.authz.common.PERMISSIONS")
    return permission


def same_person(a: str, b: str) -> bool:
    """Whether two identities name the same person.

    The platform writes an owner as ``person/j.okafor`` and authenticates the
    same human as ``j.okafor``. A duties check that compares the two with ``==``
    is one anybody can step around by dropping seven characters, which is the
    whole value of it gone.

    It lives here rather than beside any one register because the question is
    about identity, and every subsystem that enforces a duties rule has to ask
    it the same way. Two of them were asking it differently.
    """
    def bare(who: str) -> str:
        return (who or "").strip().rsplit("/", 1)[-1].casefold()

    return bool(a) and bool(b) and bare(a) == bare(b)
