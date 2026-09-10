"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Authorisation.

Three independent questions, answered in one place: permission (what a role
grants), scope (which models it reaches), and segregation of duties (what the
same person already did, read from the evidence chain rather than a second
record that could disagree with it).
"""
from core.authz.breakglass import BreakGlass
from core.authz.common import PERMISSIONS, READ_PERMISSIONS, AuthzError
from core.authz.policy import AuthorizationPolicy
from core.authz.principals import PrincipalService
from core.authz.roles import (DESCRIPTIONS, INCOMPATIBLE_ROLES, ROLES, conflicts,
                              permissions_for)
from core.authz.scope import Scope
from core.authz.segregation import RULES, Incompatibility, SegregationPolicy

__all__ = [
                              "DESCRIPTIONS",
                              "INCOMPATIBLE_ROLES",
                              "PERMISSIONS",
                              "READ_PERMISSIONS",
                              "ROLES",
                              "RULES",
                              "AuthorizationPolicy",
                              "AuthzError",
                              "BreakGlass",
                              "Incompatibility",
                              "PrincipalService",
                              "Scope",
                              "SegregationPolicy",
                              "conflicts",
                              "permissions_for",
]
