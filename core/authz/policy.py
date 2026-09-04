"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The authorisation decision point.

Three questions are asked in a fixed order, and the order is the design:

  1. **May this principal do this at all?** — permission, from roles.
  2. **May they do it to this model?** — scope, by legal entity and domain.
  3. **May they do it given what they already did?** — segregation, from the
     evidence chain.

Cheapest first, and each refusal is more specific than the last. A principal who
fails on permission never learns whether the model exists, which is the correct
disclosure boundary: an inventory of model names is itself sensitive.

One class answers all three so there is a single place to look for "why was this
refused", and a single place to change when the answer should be different.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from core.authz.common import AuthzError, require_known
from core.authz.roles import permissions_for
from core.authz.scope import Scope
from core.authz.segregation import SegregationPolicy
from core.log import get_logger

logger = get_logger(__name__)


class AuthorizationPolicy:
    """Permission, scope and segregation, decided in one place."""

    def __init__(self, segregation: Optional[SegregationPolicy] = None):
        self.segregation = segregation

    # ------------------------------------------------------------ permission
    @staticmethod
    def permissions(principal: Dict[str, Any]) -> frozenset:
        return permissions_for(principal.get("roles") or ())

    def permits(self, principal: Dict[str, Any], permission: str) -> bool:
        return require_known(permission) in self.permissions(principal)

    def require_permission(self, principal: Dict[str, Any], permission: str) -> None:
        if self.permits(principal, permission):
            return
        held = ", ".join(principal.get("roles") or ["none"])
        logger.warning("refused %s for %s (roles: %s)",
                       permission, principal.get("username"), held)
        raise AuthzError(
            "forbidden",
            f"'{permission}' is not granted by your roles ({held})",
            "ask an administrator for a role that carries this permission")

    # ----------------------------------------------------------------- scope
    @staticmethod
    def scope(principal: Dict[str, Any]) -> Scope:
        return Scope.of(principal)

    def require_scope(self, principal: Dict[str, Any], model: Dict[str, Any]) -> None:
        scope = self.scope(principal)
        if scope.permits(model):
            return
        logger.warning("scope refused %s for %s", model.get("urn"),
                       principal.get("username"))
        raise AuthzError("out_of_scope", scope.refusal(model),
                         "ask an administrator to widen your entity or domain scope")

    def visible(self, principal: Dict[str, Any],
                models: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.scope(principal).filter(models)

    # ----------------------------------------------------------- segregation
    def require_segregation(self, principal: Dict[str, Any], permission: str,
                            subject_id: Optional[str],
                            about: Optional[str] = None) -> None:
        if self.segregation is None or subject_id is None:
            return
        self.segregation.check(principal.get("username", ""), permission,
                               subject_id, about)

    # ------------------------------------------------------------------- all
    def authorise(self, principal: Dict[str, Any], permission: str,
                  model: Optional[Dict[str, Any]] = None,
                  subject_id: Optional[str] = None,
                  about: Optional[str] = None) -> None:
        """The whole decision. Raises AuthzError naming which gate refused."""
        self.require_permission(principal, permission)
        if model is not None:
            self.require_scope(principal, model)
        self.require_segregation(principal, permission, subject_id, about)

    def explain(self, principal: Dict[str, Any]) -> Dict[str, Any]:
        """What this principal may do — for the interface and for review."""
        return {"username": principal.get("username"),
                "roles": principal.get("roles") or [],
                "permissions": sorted(self.permissions(principal)),
                "scope": self.scope(principal).describe()}
