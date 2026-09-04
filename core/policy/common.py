"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary of policy.
"""
from __future__ import annotations

from typing import Dict, Tuple

# The decisions a gate can reach. There is no "warn": a gate that warns is a
# gate that is not a gate, and everybody learns to click past it.
ALLOW, REFUSE = "allow", "refuse"
DECISIONS: Tuple[str, ...] = (ALLOW, REFUSE)

DRAFT, PUBLISHED, SUPERSEDED = "draft", "published", "superseded"
STATES: Tuple[str, ...] = (DRAFT, PUBLISHED, SUPERSEDED)

# The acts a policy may govern. Closed, because a policy that could attach to
# anything would need a fact vocabulary for everything.
GATES: Tuple[str, ...] = ("version:approve", "alias:move", "model:mutate",
                          "warrant:resolve")

GATE_MEANING: Dict[str, str] = {
    "version:approve": "whether a version may be approved",
    "alias:move": "whether an alias may be pointed at a version",
    "model:mutate": "whether a model record accepts a change",
    "warrant:resolve": "whether a warrant may be resolved into a descriptor",
}

# Rules a policy's own test corpus must satisfy before it can be published.
MIN_CASES = 2


class PolicyError(RuntimeError):
    """A policy operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
