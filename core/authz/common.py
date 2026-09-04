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
    # assurance
    "validation:read", "validation:open", "validation:record", "validation:conclude",
    "finding:read", "finding:raise", "finding:close",
    "evidence:read",
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
