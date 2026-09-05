"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary of portfolio reporting.

A board pack is not a dashboard. A dashboard shows numbers; a board pack asks
whether the estate is inside the limits somebody set, names what is outside them,
and says what moved since the last meeting. Everything here follows from that.

**A metric this cannot compute is refused when the appetite is written**, not
when the report is run. A limit that fails at the moment a committee is reading
it would fail at the worst possible time, and the author is long gone by then.
This is the same discipline the policy gate applies to its fact vocabulary, for
the same reason.

**Direction belongs to the metric, not to its author.** Whether more is worse is
a property of *open blocking findings*, not an opinion somebody expresses while
setting a limit — and letting an author declare it would let one declare it
wrongly, producing a limit that reports green while the estate deteriorates.

**There is no composite score, and there will not be one.** Aggregating model
risk into a single number requires that the parts compose, and they do not: two
models fed by the same curve are not two independent risks, and any single figure
either double-counts the dependency or ignores it. A number a committee cannot
decompose is a number they cannot act on, so this reports the indicators and
refuses the average.
"""
from __future__ import annotations

from typing import Dict, NamedTuple, Tuple

LOWER_IS_BETTER = "lower_is_better"
HIGHER_IS_BETTER = "higher_is_better"

COUNT, RATIO, AMOUNT = "count", "ratio", "amount"


class Metric(NamedTuple):
    """One thing a committee can hold a limit against."""

    key: str
    means: str
    direction: str
    unit: str
    #: Why a committee cares. Carried into the pack so a reader who has not been
    #: in the room can tell what the number is *for*, which is the difference
    #: between an indicator and a statistic.
    matters: str


#: Closed on purpose. Each is computed from the register by `indicators.py`, and
#: each is something the estate can actually be outside.
METRICS: Tuple[Metric, ...] = (
    Metric("models_untiered", "models with no risk tier assessed",
           LOWER_IS_BETTER, COUNT,
           "a model with no tier has no required control set, so nothing is "
           "overdue for it and no gate applies — it is invisible to every "
           "control that keys on depth"),
    Metric("models_not_in_force", "models registered but not attested",
           LOWER_IS_BETTER, COUNT,
           "a record nobody has signed is a record nobody has taken "
           "responsibility for, however complete it looks"),
    Metric("blocking_findings", "open findings that block promotion and warrants",
           LOWER_IS_BETTER, COUNT,
           "each one is a model the platform is actively refusing to let move; "
           "a rising count means remediation is losing to discovery"),
    Metric("findings_overdue", "findings past the date their owner accepted",
           LOWER_IS_BETTER, COUNT,
           "the single most reliable indicator of whether the second line is "
           "resourced, because it measures promises rather than intentions"),
    Metric("models_unmonitored", "models in force with no monitor defined",
           LOWER_IS_BETTER, COUNT,
           "not a measure of degradation — a measure of whether degradation "
           "would be noticed at all"),
    Metric("open_breaches", "monitor breaches currently open",
           LOWER_IS_BETTER, COUNT,
           "models observed to be outside the envelope they were validated in"),
    Metric("overlay_magnitude", "aggregate absolute magnitude of live overlays",
           LOWER_IS_BETTER, AMOUNT,
           "how much of the estate's output is the models and how much is us; "
           "a committee that does not ask this is approving the models and "
           "getting the adjustments"),
    Metric("overlays_persistent", "overlays renewed past their limit",
           LOWER_IS_BETTER, COUNT,
           "an overlay that has outlived its renewal limit is an unversioned "
           "model change wearing a temporary label"),
    Metric("attestations_lapsed", "models whose attestation has expired",
           LOWER_IS_BETTER, COUNT,
           "the record was in force and has quietly stopped being"),
    Metric("baseline_debt", "models carrying cold-start compliance debt",
           LOWER_IS_BETTER, COUNT,
           "kept apart from breach on purpose: debt is what was inherited, "
           "breach is what happened since"),
    Metric("monitored_share", "share of models in force that are monitored",
           HIGHER_IS_BETTER, RATIO,
           "the same fact as models_unmonitored, held as a ratio so a limit "
           "survives the estate growing"),
    Metric("in_force_share", "share of registered models that are attested",
           HIGHER_IS_BETTER, RATIO,
           "how much of what is registered is actually governed"),
)

BY_KEY: Dict[str, Metric] = {m.key: m for m in METRICS}

#: Where an indicator stands against its limit.
WITHIN, AMBER, BREACH, NO_APPETITE = "within", "amber", "breach", "no_appetite"

STATUS_MEANING: Dict[str, str] = {
    WITHIN: "inside the limit the committee set",
    AMBER: "inside the limit and past the warning threshold",
    BREACH: "outside the limit",
    NO_APPETITE: "measured, with no limit declared — a number, not an indicator",
}

#: An appetite whose utilisation stays this far below its limit, pack after
#: pack, is reported as **slack**. Not a breach and not an error: a limit that
#: has never been approached is a limit that is not constraining anything, and a
#: committee reviewing appetite should be told which of its limits are doing no
#: work. A control that has never fired is indistinguishable from one that
#: cannot.
SLACK_UTILISATION = 0.25

#: How many consecutive packs must show slack before it is reported. One quiet
#: quarter is a quiet quarter.
SLACK_PACKS = 2

#: Scope dimensions an appetite may be declared over. Closed, because a scope
#: the platform cannot filter on is a limit that silently applies to everything.
SCOPES: Tuple[str, ...] = ("tier", "domain", "legal_entity")

MAX_RATIONALE = 2000


class ReportingError(RuntimeError):
    """A reporting operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
