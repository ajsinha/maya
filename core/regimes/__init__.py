"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Regulatory regimes as institutions.

Each regime carries its own signature (the vocabulary it reasons in), its own
sentences (obligations in that vocabulary), and a translation into MAYA's core
terms. A regime is activated only when its translation passes the satisfaction
condition — truth invariant under change of notation — because an encoding that
fails it produces determinations nobody can defend.
"""
from core.regimes.common import RegimeError
from core.regimes.engine import PROBE_STATES, RegimeEngine
from core.regimes.library import REGIMES
from core.regimes.sentences import Sentence, forbids, implies, requires
from core.regimes.signature import CORE, CORE_TERMS, Interpretation, Signature
from core.regimes.translation import Translation, satisfaction_condition

__all__ = ["RegimeEngine", "RegimeError", "REGIMES", "Signature", "Interpretation",
           "Sentence", "Translation", "satisfaction_condition", "CORE",
           "CORE_TERMS", "PROBE_STATES", "requires", "forbids", "implies"]
