"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary of the parameter register.
"""
from __future__ import annotations

from typing import Dict, Tuple

# How a parameter object came to be inhabited. Not how it is *stored* — three
# routes with genuinely different evidence and genuinely different governance.
FITTED, CALIBRATED, DECLARED = "fitted", "calibrated", "declared"
PROVENANCE: Tuple[str, ...] = (FITTED, CALIBRATED, DECLARED)

PROVENANCE_MEANING: Dict[str, str] = {
    FITTED: "estimated or trained from data, under a fit warrant MAYA issued",
    CALIBRATED: "solved against market data under an approved procedure, often "
                "daily; the procedure is approved, not each morning's result",
    DECLARED: "asserted by a person — parameters from theory, elicited weights, "
              "or an authored rule set — and attested rather than fitted",
}

# A fit is evidence; a declaration is an assertion. Only the first may claim a
# warrant, and only the second may arrive without one.
NEEDS_WARRANT = frozenset({FITTED})

#: Parameter objects no procedure over data can produce, so a set inhabiting
#: one is `declared` or it is mis-described. A rule set is authored, a
#: generative assembly is configured, and elicited weights come out of a panel:
#: none of the three is fitted, and none is calibrated either — `calibrated`
#: means solved against market data under an approved procedure, and a panel is
#: not that. `none` and `opaque` are refused separately because each has its
#: own sentence to say.
NOT_FROM_DATA = frozenset({"rule_set", "llm_configuration", "elicited_weights"})

PROPOSED, APPROVED, REJECTED, SUPERSEDED = ("proposed", "approved", "rejected",
                                            "superseded")
STATES: Tuple[str, ...] = (PROPOSED, APPROVED, REJECTED, SUPERSEDED)

# Beyond this, the values are an artifact rather than a record: a coefficient
# vector belongs in the register, a hundred million weights belong in the
# artifact store with their digest here.
MAX_INLINE_VALUES = 4096


class ParameterError(RuntimeError):
    """A parameter operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
