"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The lifecycle's shared refusal type and its vocabulary.
"""
from __future__ import annotations

from typing import Dict, Tuple

DAY = 86400.0

AMENDMENT_STATES: Tuple[str, ...] = ("open", "submitted", "attested", "withdrawn")
ATTESTATION_STATES: Tuple[str, ...] = ("open", "attested", "declined", "expired")
ATTESTATION_KINDS: Tuple[str, ...] = ("initial", "amendment", "periodic")
DECISIONS: Tuple[str, ...] = ("attest", "decline")

# Who must sign before a model is in force. Configuration, because the quorum a
# firm's model risk policy requires is a policy question and not ours.
DEFAULT_REQUIRED_ROLES: Tuple[str, ...] = ("model_owner", "model_risk_manager")
DEFAULT_VALIDITY_DAYS = 365


class LifecycleError(RuntimeError):
    """A lifecycle act was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        """The RFC 9457 body. Same shape as every other refusal in the platform."""
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
