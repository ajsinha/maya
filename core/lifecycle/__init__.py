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
from core.lifecycle.attestation import AttestationService
from core.lifecycle.common import (ATTESTATION_KINDS, DECISIONS, DEFAULT_REQUIRED_ROLES,
                                   LifecycleError)
from core.lifecycle.service import LifecycleService
from core.lifecycle.states import (AMENDING, APPROVED, ATTESTED, DRAFT, MEANING,
                                   MUTABLE, RETIRED, STATES, SUBMITTED, TRANSITIONS,
                                   allowed_from, describe, is_mutable, transition)

__all__ = ["LifecycleService", "AmendmentService", "AttestationService",
           "LifecycleError", "STATES", "TRANSITIONS", "MUTABLE", "MEANING",
           "DRAFT", "SUBMITTED", "APPROVED", "ATTESTED", "AMENDING", "RETIRED",
           "DECISIONS", "ATTESTATION_KINDS", "DEFAULT_REQUIRED_ROLES",
           "is_mutable", "allowed_from", "transition", "describe"]
