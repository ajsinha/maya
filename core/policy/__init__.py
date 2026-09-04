"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Versioned gates.

A gate that cannot be changed without a release is worked around; one that can be
weakened without a release is worse. A policy ships with its own cases and cannot
be published until they pass, and a change that loosens a gate is reported rather
than discovered.
"""
from core.policy.common import (ALLOW, DECISIONS, GATES, GATE_MEANING, REFUSE,
                                STATES, PolicyError)
from core.policy.engine import PolicyGate, PolicyRegister
from core.policy.facts import BUILT_IN, describe as describe_facts, vocabulary
from core.policy.language import Rule

__all__ = ["PolicyRegister", "PolicyGate", "PolicyError", "Rule", "GATES", "GATE_MEANING",
           "DECISIONS", "STATES", "ALLOW", "REFUSE", "BUILT_IN",
           "vocabulary", "describe_facts"]
