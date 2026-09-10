"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Parameter sets: the point of `P` a run happens at.

The distinction this module exists to keep visible: **recording new parameters
does not create a new model version.** The kernel did not change. That is what
lets a daily recalibration procedure be approved once rather than pretending a
committee meets every morning, and it is the thing people coming from an
experiment tracker most often get wrong.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Parameters:
    """Fitting, delivering, and the four eyes that accept the numbers."""

    def __init__(self, maya):
        self._maya = maya

    def fit(self, *, urn: str, snapshot_id: str, principal: str,
            window: Dict[str, float], name: str = "fitted",
            environment: str = "lab", kind: str = "coefficients",
            declared_use: str = "model_development",
            note: str = "") -> Dict[str, Any]:
        """Let MAYA fit it, where the kernel names the `estimator` runtime.

        Four things happen in this order, and the order is the point: the warrant
        is resolved **first** (authority before data — a read performed under an
        authority that turns out not to exist has already happened), the snapshot
        is read at its pinned Delta version rather than at the head, the estimator
        runs through the ordinary runtime dispatch, and the result lands
        `proposed` rather than approved.
        """
        return self._maya.call("POST", "/parameter-fits", json={
            "urn": urn, "snapshot_id": snapshot_id, "principal": principal,
            "environment": environment, "window": window, "name": name,
            "kind": kind, "declared_use": declared_use, "note": note})

    def record(self, *, urn: str, semver: str, name: str, kind: str,
               values: Dict[str, Any], warrant_id: str,
               provenance: str = "fitted",
               featureset: Optional[str] = None,
               featureset_version: Optional[int] = None,
               window: Optional[Dict[str, float]] = None,
               as_of: Optional[float] = None,
               snapshot_id: Optional[str] = None,
               diagnostics: Optional[Dict[str, Any]] = None,
               note: str = "") -> Dict[str, Any]:
        """Deliver parameters fitted in your own engine.

        `warrant_id` is not optional in practice: a fitted set is accepted only
        against a warrant MAYA issued, because without one *"which data produced
        these numbers"* has no answer. The keyword is here rather than buried in
        a dictionary so that omitting it is a visible mistake.

        Send the diagnostics. They are what a reviewer reads — the condition
        number before the R², the convergence flag, the residual — and a set
        delivered without them asks somebody to approve a number on trust.
        """
        return self._maya.call("POST", "/parameters", json={
            "urn": urn, "semver": semver, "name": name, "kind": kind,
            "values": values, "provenance": provenance,
            "featureset": featureset, "featureset_version": featureset_version,
            "window": window, "as_of": as_of, "snapshot_id": snapshot_id,
            "warrant_id": warrant_id, "diagnostics": diagnostics or {},
            "note": note})

    def get(self, parameter_set_id: str) -> Dict[str, Any]:
        return self._maya.call("GET", f"/parameter-sets/{parameter_set_id}")

    def review(self, parameter_set_id: str, *, accept: bool,
               note: str = "") -> Dict[str, Any]:
        """Accept or reject, and never as whoever recorded them.

        A number one person can both produce and bless is a preference, not an
        estimate. The platform refuses it; this method cannot make that easier
        and does not try.
        """
        return self._maya.call("POST", f"/parameter-sets/{parameter_set_id}/review",
                               json={"accept": accept, "note": note})

    def provenance(self) -> Dict[str, Any]:
        """What each provenance means: fitted, calibrated, declared."""
        return self._maya.call("GET", "/parameter-provenance")


class Runs:
    """The record of an activity somebody else executed.

    Every experiment tracker records a run **when it finishes**, and that
    produces a register of successes. A fit that started, consumed a warrant,
    read a snapshot of somebody's data and vanished — preempted node, killed
    job, nobody watching — appears in none of them, and it is the run a
    supervisor asks about.

    So `open()` is called **before** the activity, `close()` after, and a run
    still open well past its own `expected_seconds` reads as `lost`. Lost is a
    state, not an absence, and it is derived from the clock rather than
    asserted: a caller who could report a run lost could close one it would
    rather nobody read.

    **MAYA submits no jobs and never reads `log_uri`.** Submitting would put the
    register on the failure path of the thing it exists to observe; fetching
    logs would put its readiness on somebody else's object store.
    """

    def __init__(self, maya):
        self._maya = maya

    def vocabulary(self) -> Dict[str, Any]:
        """The verbs, the states, and what MAYA does not do."""
        return self._maya.call("GET", "/runs/vocabulary")

    def list(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Every top-level run, lost first."""
        return self._maya.call("GET", "/runs", params={"now": now})

    def get(self, reference: str, *,
            now: Optional[float] = None) -> Dict[str, Any]:
        return self._maya.call("GET", "/runs",
                               params={"reference": reference, "now": now})

    def open(self, reference: str, *, verb: str, urn: str = "",
             semver: str = "", warrant_id: str = "", parent: str = "",
             purpose: str = "",
             resource_profile: Optional[Dict[str, Any]] = None,
             environment: Optional[Dict[str, Any]] = None,
             inputs: Optional[Dict[str, Any]] = None,
             hyperparameters: Optional[Dict[str, Any]] = None,
             seeds: Optional[Dict[str, Any]] = None, log_uri: str = "",
             expected_seconds: Optional[float] = None) -> Dict[str, Any]:
        """Declare a run before it happens.

        Supply `expected_seconds`. Without it nothing can ever call this run
        lost, and a run that can never be lost is one that quietly stays open
        forever — which reads on every screen exactly like one still working.
        """
        return self._maya.call("POST", "/runs", json={
            "reference": reference, "verb": verb, "urn": urn, "semver": semver,
            "warrant_id": warrant_id, "parent": parent, "purpose": purpose,
            "resource_profile": resource_profile or {},
            "environment": environment or {}, "inputs": inputs or {},
            "hyperparameters": hyperparameters or {}, "seeds": seeds or {},
            "log_uri": log_uri, "expected_seconds": expected_seconds})

    def close(self, reference: str, *, state: str,
              metrics: Optional[Dict[str, Any]] = None,
              parameter_set_id: str = "", cost: Optional[float] = None,
              note: str = "") -> Dict[str, Any]:
        """Take delivery of what a run produced.

        A failure needs a note. The failures are the part of a training record
        anybody reads twice, and a bare `failed` six months on is
        indistinguishable from a run nobody looked at.
        """
        return self._maya.call("POST", f"/runs/{reference}/close", json={
            "state": state, "metrics": metrics or {},
            "parameter_set_id": parameter_set_id, "cost": cost, "note": note})

    def search(self, reference: str, *,
               now: Optional[float] = None) -> Dict[str, Any]:
        """A parent search and its children, and what a ranking hides.

        Read `tried` before any metric. A search that tried four hundred
        configurations and published the best is a multiple-comparisons problem
        — the best of four hundred draws from a null distribution looks
        excellent — and the count is what makes that visible.

        MAYA does not select a winner. Choosing a child means approving its
        parameter set, and a search cannot approve its own output.
        """
        return self._maya.call("GET", f"/runs/{reference}/search",
                               params={"now": now})


class Retraining:
    """When a re-fit is due, and the standing approval that may accept one.

    **MAYA retrains nothing.** It says a re-fit is due from triggers it already
    computes; the fit happens under a warrant elsewhere and comes back as a run
    and a parameter set.

    The auto-acceptance policy approves a **procedure**, never a result. The
    objection is obvious and mostly right — nobody looked at this number — but
    the alternative in practice is not a committee reading every recalibration.
    It is a recalibration that happens anyway, at the frequency the business
    needs, with nobody's name on it.

    Four things make that defensible, and each is enforced rather than
    documented: tier 1 is never eligible and it is not configurable; every
    policy expires; the tolerance is checked here rather than by whatever
    produced the parameters; and the person who writes a policy may not approve
    it. An acceptance is attributed to the policy's human approver, because
    *who approved this parameter set* must always have a human answer.
    """

    def __init__(self, maya):
        self._maya = maya

    def triggers(self) -> Dict[str, Any]:
        """The triggers, the tier ceiling and the maximum policy lifetime."""
        return self._maya.call("GET", "/retraining/triggers")

    def due(self, urn: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Whether a re-fit is due for one model, and on what."""
        return self._maya.call("GET", "/retraining",
                               params={"urn": urn, "now": now})

    def across_the_estate(self, *,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """Every model's policy and whether anything has fired."""
        return self._maya.call("GET", "/retraining", params={"now": now})

    def declare(self, urn: str, *, triggers: List[str], rationale: str,
                tolerance: Optional[Dict[str, Any]] = None,
                auto_accept: bool = False,
                expires_at: Optional[float] = None) -> Dict[str, Any]:
        """Write the standing policy. Approval is a separate act.

        Declaring it without `auto_accept` still fires the triggers and still
        puts the model on the due list, which is most of the value and none of
        the delegation.
        """
        return self._maya.call("POST", "/retraining",
                               params={"urn": urn},
                               json={"triggers": triggers,
                                     "tolerance": tolerance or {},
                                     "auto_accept": auto_accept,
                                     "rationale": rationale,
                                     "expires_at": expires_at})

    def approve(self, urn: str) -> Dict[str, Any]:
        """Approve a standing policy — never as the person who wrote it."""
        return self._maya.call("POST", "/retraining/approve",
                               params={"urn": urn})

    def revoke(self, urn: str, *, reason: str = "") -> Dict[str, Any]:
        return self._maya.call("POST", "/retraining/revoke",
                               params={"urn": urn, "reason": reason})


class Elicitations:
    """A panel asked a question, and the disagreement that is the answer.

    T7 parameters come out of expert judgement, and **the value of an
    elicitation is the spread, not the number**. *How much did they disagree* is
    the first question a validator asks about a judgemental parameter, and a
    process that stores only the final weight has destroyed the evidence that
    they disagreed at all.

    So responses are recorded per round, per panellist, and **never
    overwritten**: a response revised in place erases the movement between
    rounds, and the movement is the only thing convergence can be measured from.

    Read `convergence` knowing what it cannot say. The spread narrowing is
    arithmetic; *why* it narrowed is not. A panel that converged because the
    most senior person answered first is indistinguishable, in the numbers, from
    one that converged on the evidence — which is why the `method` is recorded,
    so a workshop's spread is not read like a Delphi's.

    **Dissent travels with the number.** A final weight whose dissent nobody can
    find is a weight that looks unanimous, and the firm relying on it does not
    know it is relying on a majority.
    """

    def __init__(self, maya):
        self._maya = maya

    def methods(self) -> Dict[str, Any]:
        """The methods, the panel floor, and what convergence cannot say."""
        return self._maya.call("GET", "/elicitations/methods")

    def list(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Every elicitation, widest disagreement first.

        An empty answer is worth reading: a T7 parameter with no elicitation
        behind it is a number somebody chose, and the register cannot tell that
        from one a panel agreed.
        """
        return self._maya.call("GET", "/elicitations", params={"now": now})

    def get(self, reference: str) -> Dict[str, Any]:
        return self._maya.call("GET", "/elicitations",
                               params={"reference": reference})

    def open(self, reference: str, *, urn: str, question: str,
             panel: List[str], facilitator: str, units: str = "",
             method: str = "delphi", semver: str = "") -> Dict[str, Any]:
        """Convene a panel around one question.

        Fewer than three panellists is refused: one expert's judgement is not an
        elicitation, it is an assumption, and the assumption register is where
        an assumption belongs — with a materiality, an owner, and something
        watching it. The facilitator may not also answer.
        """
        return self._maya.call("POST", "/elicitations", json={
            "reference": reference, "urn": urn, "question": question,
            "panel": panel, "facilitator": facilitator, "units": units,
            "method": method, "semver": semver})

    def respond(self, reference: str, *, panellist: str, value: float,
                confidence: str = "", reasoning: str = "",
                independent: bool = True,
                dissented: bool = False) -> Dict[str, Any]:
        """Record one answer in the current round.

        Set `independent=False` where the panellist is not independent of the
        model. It is recorded rather than refused, because in a small firm the
        only person who genuinely understands the model is often the person who
        built it, and refusing would push the elicitation off the platform
        entirely — the share of the answer that came from conflicted panellists
        is then visible instead of invisible.
        """
        return self._maya.call("POST", f"/elicitations/{reference}/respond",
                               json={"panellist": panellist, "value": value,
                                     "confidence": confidence,
                                     "reasoning": reasoning,
                                     "independent": independent,
                                     "dissented": dissented})

    def next_round(self, reference: str) -> Dict[str, Any]:
        """Open another round. The previous one stays exactly as it was."""
        return self._maya.call("POST", f"/elicitations/{reference}/next-round")

    def convergence(self, reference: str) -> Dict[str, Any]:
        """Whether the spread narrowed, and why that is all it can say."""
        return self._maya.call("GET", f"/elicitations/{reference}/convergence")

    def conclude(self, reference: str, *, value: float,
                 note: str) -> Dict[str, Any]:
        """Record the number the panel arrived at, with its dissent attached.

        `note` is required. The number is the least interesting thing an
        elicitation produces, and a year later the note is the only part
        anybody can act on.
        """
        return self._maya.call("POST", f"/elicitations/{reference}/conclude",
                               json={"value": value, "note": note})
