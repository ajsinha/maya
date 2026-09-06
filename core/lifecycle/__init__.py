"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The model record lifecycle.

draft -> submitted -> approved -> attested, with amendment as the only route out
of immutability. Split by responsibility: the state machine, amendments,
attestation quorum, and the service that wires them and implements the mutation
gate the registry consults.
"""
from core.lifecycle.amendments import AmendmentService
from core.lifecycle.approval import VersionApproval
from core.lifecycle.attestation import AttestationService
from core.lifecycle.common import (ATTESTATION_KINDS, DECISIONS, DEFAULT_REQUIRED_ROLES,
                                   LifecycleError)
from core.lifecycle.service import LifecycleService
from core.lifecycle.states import (AMENDING, APPROVED, ATTESTED, BASELINED,
                                   DRAFT, MEANING,
                                   MUTABLE, RETIRED, STATES, SUBMITTED, TRANSITIONS,
                                   allowed_from, describe, is_mutable, transition)

__all__ = [
                                   "AMENDING",
                                   "APPROVED",
                                   "ATTESTATION_KINDS",
                                   "ATTESTED",
                                   "BASELINED",
                                   "DECISIONS",
                                   "DEFAULT_REQUIRED_ROLES",
                                   "DRAFT",
                                   "MEANING",
                                   "MUTABLE",
                                   "RETIRED",
                                   "STATES",
                                   "SUBMITTED",
                                   "TRANSITIONS",
                                   "AmendmentService",
                                   "AttestationService",
                                   "LifecycleError",
                                   "LifecycleService",
                                   "VersionApproval",
                                   "allowed_from",
                                   "describe",
                                   "is_mutable",
                                   "transition",
]
