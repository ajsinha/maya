"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model is *also* subject to, beside its tier.

A tier answers one question — how much rides on this model — and answers it
well. It does not answer the others a bank is asked. Two models can sit at the
same tier while one of them feeds a regulatory submission and the other does
not, and the second question has consequences the first cannot express: the
submission model needs a reconciliation nobody would ask of the other, and no
amount of moving it up or down the tier lattice produces that requirement.

So designations are **orthogonal to the tier and additive to it**. They do not
enter `tau`, they do not move a model up or down, and `supports_tier` — the
Galois adjoint the tier lattice rests on (`L-5`) — is untouched. It reads tier
controls and only tier controls, because an adjoint that also read designation
controls would answer *which tier do these controls defend* with a number that
depended on facts the tier lattice does not contain. That is the kind of change
that breaks a law quietly, and the separation here is the thing preventing it.

**A tag that changes nothing is a label.** The requirement's own phrase is
"driving additional control sets", and that is the whole of the design: each
designation names controls that are required *in addition*, and those controls
are then waivable through the ordinary register like any other — so a bank that
cannot yet meet one has to say so, bound it, and compensate for it, rather than
letting the tag be decoration.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

#: The four the requirement names. Closed, because the whole value is that each
#: one carries consequences, and a designation nothing keys off is a label.
DESIGNATIONS: Tuple[str, ...] = ("sox_relevant", "regulatory_reporting",
                                 "consumer_impacting", "safety_critical")

DESIGNATION_MEANING: Dict[str, str] = {
    "sox_relevant": "its output reaches the financial statements, so the "
                    "controls over how it CHANGES and who can change it are "
                    "themselves in scope",
    "regulatory_reporting": "it feeds a supervisory submission, so what it "
                            "produced has to be reconcilable to what was "
                            "filed, after the fact",
    "consumer_impacting": "it acts on an individual person, so the decision "
                          "has to be explainable to them and testable for "
                          "disparate outcomes",
    "safety_critical": "being wrong hurts somebody, so the question is not "
                       "only whether it is accurate but what happens when it "
                       "is not",
}

#: What each designation ADDS. Chosen to be the control the designation
#: actually implies rather than a general tightening — "be more careful" is not
#: a control set, and a designation that only raised the review cadence would
#: be a tier in disguise.
EXTRA_CONTROLS: Dict[str, Tuple[str, ...]] = {
    # SOX is about controls over financial reporting, which means controls over
    # the thing that produces the numbers rather than over the numbers.
    "sox_relevant": ("change_control_evidence", "access_review"),
    # The question a supervisor asks about a submission is not "is the model
    # good" but "can you show me that this figure came from that model on that
    # date", and that is a reconciliation, not a validation.
    "regulatory_reporting": ("reconciliation_to_submission",
                             "full_documentation"),
    # ECOA and Regulation B require the specific principal reasons for an
    # adverse action; the Consumer Duty asks whether outcomes differ across
    # groups. Neither is implied by any tier.
    "consumer_impacting": ("adverse_action_reasons", "fairness_assessment"),
    # For a safety-critical model the interesting analysis is of the failure
    # rather than of the fit.
    "safety_critical": ("failure_mode_analysis", "independent_validation"),
}

#: Every control any designation adds, flattened — the waiver register needs
#: this so a designation-driven control can be waived like any other. A
#: requirement that could not be waived would be one people meet on paper.
DESIGNATION_CONTROLS: Tuple[str, ...] = tuple(sorted(
    {c for controls in EXTRA_CONTROLS.values() for c in controls}))


class DesignationError(RuntimeError):
    """A designation was not one of the four. The message says which they are."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


def validate(designations: Iterable[str]) -> List[str]:
    """Check and normalise. Order is not meaningful, so the answer is sorted.

    Sorted rather than as given, because two models designated the same way
    should compare equal, and `["sox_relevant", "safety_critical"]` and its
    reverse are the same fact written twice.
    """
    out = sorted(set(designations or ()))
    unknown = [d for d in out if d not in DESIGNATIONS]
    if unknown:
        raise DesignationError(
            "unknown_designation",
            f"{', '.join(unknown)} is not a designation this platform keys "
            f"anything off, so applying it would change nothing while reading "
            f"on a report as though it had",
            f"the four are {', '.join(DESIGNATIONS)}")
    return out


def extra_controls(designations: Iterable[str]) -> List[str]:
    """The controls these designations add, over and above the tier's."""
    out: set = set()
    for designation in validate(designations):
        out.update(EXTRA_CONTROLS[designation])
    return sorted(out)


def explain(designations: Iterable[str]) -> List[Dict[str, object]]:
    """Which control came from which designation.

    A flat list of extra controls tells somebody what to do and not why, and
    *why* is the half that survives an argument about whether the designation
    was right in the first place.
    """
    return [{"designation": d, "means": DESIGNATION_MEANING[d],
             "adds": list(EXTRA_CONTROLS[d])}
            for d in validate(designations)]
