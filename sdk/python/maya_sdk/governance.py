"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The governed acts: the record's lifecycle, the rule-set editor, the fibration,
and the parts of the feature and featureset algebra the feature module leaves
out.

Three ideas run through everything here, and each is a thing this module
deliberately does **not** do.

**It does not hold the state machine.** There is one method per endpoint, and no
check anywhere about whether the move is legal from where the record stands. The
machine is published — `Lifecycle.machine()` returns it — precisely so that a
client can show the legal moves without owning a copy of them. A copy would
disagree with the platform eventually, and it would disagree by offering a
button that should not have been there.

**It keeps free and authoritative apart.** `Rules.check` and `Rules.trial` carry
no authority, record nothing and append no evidence; `Rules.publish` is the
ordinary `parameter:record` act with the ordinary consequences. The same split
runs through the feature side — `check`, `trial`, `preview`, `as_of` are free,
`define`, `seal` and `publish` are not. That is the design and not an
implementation detail: an author who has to spend authority to *look* at whether
their draft is sound learns to skip the looking, and the looking is what keeps
the register clean.

**It never re-derives a trainability class.** `Fibres` asks the platform which
classes exist and what each one carries. Nothing here enumerates a class, and
nothing here decides which verbs one admits — the fibration is a governance rule
and a second copy of a governance rule drifts, always in the direction of
permitting more, because that is the direction in which nobody files a bug.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from maya_sdk.models import short


class Lifecycle:
    """The model record's state machine, as acts rather than as a diagram.

    Seven states — draft, baselined, submitted, approved, attested, amending,
    retired — and the promise the whole platform rests on: an **attested record
    is immutable**, and the only way out of that is a declared amendment which
    must itself be attested. Everything below is either a step towards that
    state or the declared act of leaving it.

    A refusal from here is worth reading rather than logging. `illegal_transition`
    names what *is* legal from where the record stands, and the gate that refuses
    a change to an attested record names the amendment as the way through, so the
    remediation is an instruction and not an apology.

    `submit`, `approve` and `attest` also appear on `maya.models`, from an earlier
    pass. These are the fuller ones — `attest` here can carry a **decline**, which
    the other cannot express, and a quorum where the only expressible answer is
    yes is not a quorum. The thin pair should go on the next merge; until then,
    prefer these.
    """

    def __init__(self, maya):
        self._maya = maya
        self.approvals = VersionApprovals(maya)
        self.relations = Relations(maya)

    # ------------------------------------------------------------ the machine
    def machine(self) -> Dict[str, Any]:
        """The transitions themselves: name, sources, target, permission, note.

        Asked for rather than carried. A client that wants to offer only the
        legal moves reads this and filters on the record's state; a client that
        hard-codes the same table has written a second state machine, and the
        two will part company at the first policy change.
        """
        return self._maya.call("GET", "/lifecycle")

    def state(self, urn: str) -> Dict[str, Any]:
        """Where this record stands, with its attestation and any open amendment.

        Travels with the model rather than living at its own path, because the
        model segment is a greedy converter and would swallow the suffix.
        """
        return self._maya.call("GET", f"/models/{short(urn)}").get("lifecycle", {})

    # ------------------------------------------------------------- portfolio
    def portfolio(self, dimension: str = "tier") -> Dict[str, Any]:
        """The register grouped by one dimension, with what is owed in each.

        Ordered by outstanding work rather than alphabetically, because a cut
        sorted by name buries whatever needs doing.
        """
        return self._maya.call("GET", "/portfolio",
                               params={"dimension": dimension})

    def heatmap(self, rows: str = "domain",
                columns: str = "tier") -> Dict[str, Any]:
        """A cross-tabulation shaded by what is owed rather than by count.

        A grid coloured by count tells you where the models are, which nobody
        needed a grid to learn. A cell with forty healthy models and a cell with
        one that is missing its validation are not the same cell.
        """
        return self._maya.call("GET", "/portfolio/heatmap",
                               params={"rows": rows, "columns": columns})

    def portfolio_trend(self, *, points: int = 12,
                        span_days: float = 365.0) -> Dict[str, Any]:
        """The register as it stood, at intervals, folded from the chain.

        Not a snapshot table — a nightly snapshot starts on the day somebody
        remembered it and is wrong for every day before. Each point carries the
        chain hash that makes it verifiable rather than asserted.
        """
        return self._maya.call("GET", "/portfolio/trend",
                               params={"points": points,
                                       "span_days": span_days})

    def aggregate_risk(self) -> Dict[str, Any]:
        """How much rides on the models that are not right.

        Read `exposure_coverage` alongside the figure: a weighted answer over a
        third of an estate presented as *the* answer would be worse than the
        count it replaced.
        """
        return self._maya.call("GET", "/portfolio/aggregate")

    # ------------------------------------------------------ approved on terms
    def condition_kinds(self) -> Dict[str, Any]:
        """The conditions an approval may carry, and which are enforced.

        Read `enforcement` on every one. **Enforced** means something in the
        platform refuses when the condition is broken. **Attested** means MAYA
        cannot see the thing the condition is about, so the control is that a
        named person periodically confirms it — a real control, and not the same
        one. A firm that believes its exposure cap is machine-enforced is worse
        off than one that knows it is a diary entry, because the first has
        stopped checking.
        """
        return self._maya.call("GET", "/condition-kinds")

    def conditions(self, urn: str = "") -> Dict[str, Any]:
        """A model's approval conditions and whether they hold, or the estate's."""
        params = {"urn": urn} if urn else None
        return self._maya.call("GET", "/approval-conditions", params=params)

    def approve_on_terms(self, urn: str, *, kind: str, rationale: str,
                         days: float,
                         parameters: Optional[Dict[str, Any]] = None,
                         semver: str = "",
                         confirm_every_days: float = 30.0) -> Dict[str, Any]:
        """Impose a condition on this model's approval.

        SR 26-2 V permits use before validation with compensating controls, and
        this is what makes them enforced rather than promised. The window is
        mandatory and bounded: a conditional approval with no end date is an
        unconditional approval that has not noticed yet.
        """
        return self._maya.call("POST", "/approval-conditions", json={
            "urn": urn, "kind": kind, "rationale": rationale, "days": days,
            "parameters": parameters or {}, "semver": semver,
            "confirm_every_days": confirm_every_days})

    def confirm_condition(self, reference: str, *,
                          note: str = "") -> Dict[str, Any]:
        """State that an attested condition still holds.

        Only the attested ones take this. Confirming something the platform
        already checks would record an opinion about a fact.
        """
        return self._maya.call(
            "POST", f"/approval-conditions/{reference}/confirm",
            json={"note": note})

    def discharge_condition(self, reference: str, *,
                            reason: str) -> Dict[str, Any]:
        """Lift a condition, because what it stood in for has been done."""
        return self._maya.call(
            "POST", f"/approval-conditions/{reference}/discharge",
            json={"reason": reason})

    # -------------------------------------------------------- what a move costs
    def profiles(self) -> Dict[str, Any]:
        """The reference lifecycle for every trainability class.

        One state graph and several sets of obligations. Nine graphs would mean
        nine reachability proofs, nine answers to *can this be changed*, and a
        supervisor who has to ask which machine a model is on before reading its
        status. What varies is what each move **costs**: the class says which
        evidence kinds must be on file before a record can be attested, the tier
        says how many signatures the move takes.
        """
        return self._maya.call("GET", "/lifecycle-profiles")

    def profile(self, trainability_class: str, *,
                tier: Optional[int] = None) -> Dict[str, Any]:
        """What a model of this class owes on each move, at this tier.

        Both halves are derived rather than configured: the evidence comes from
        the fibre, which `L-15` already makes each class declare, and the quorum
        from the tier. Omit the tier and the lightest quorum is shown — an
        untiered model is not a tier 1 model, and this must not invent one.
        """
        params = {"tier": tier} if tier is not None else None
        return self._maya.call("GET", f"/lifecycle-profiles/{trainability_class}",
                               params=params)

    def readiness(self, urn: str, *,
                  transition: str = "attest") -> Dict[str, Any]:
        """Whether this model can make this move, and what is missing if not.

        Read `awaiting_review` apart from `missing_evidence`. A document on file
        that nobody has accepted is a different problem from a document nobody
        has written, and treating them alike sends somebody off to produce a
        report that is already sitting in a review queue.
        """
        return self._maya.call("GET", "/lifecycle-readiness",
                               params={"urn": urn, "transition": transition})

    def stalled(self) -> Dict[str, Any]:
        """Records that have been mid-move longer than their tier allows.

        Nothing else in the platform can see this. Submission succeeded, every
        gate passed, and no control watches the clock — which is how a
        governance queue becomes a place things go to wait. Not a refusal: a
        queue is allowed to have a queue, but one with no expected duration is
        one nobody can tell is stuck.
        """
        return self._maya.call("GET", "/lifecycle-stalled")

    # ------------------------------------------------------------------- acts
    def update(self, urn: str, *, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Revise an open record. Refused once it is attested, naming the amendment."""
        return self._maya.call("PATCH", f"/models/{short(urn)}",
                               json={"fields": fields})

    def submit(self, urn: str, *, note: str = "") -> Dict[str, Any]:
        """Put the record forward. The owner's act, not the developer's."""
        return self._maya.call("POST", f"/models/{short(urn)}/submit",
                               json={"note": note})

    def approve(self, urn: str, *, note: str = "") -> Dict[str, Any]:
        """The second line approves the record — and it is still not in force.

        Approval opens the attestation; the record is in force when the required
        roles have signed. Collapsing the two would let one approval by one
        person do the work the quorum exists to divide.
        """
        return self._maya.call("POST", f"/models/{short(urn)}/approve",
                               json={"note": note})

    def send_back(self, urn: str, *, reason: str) -> Dict[str, Any]:
        """Return a submission for more work. The reason is required, not polite."""
        return self._maya.call("POST", f"/models/{short(urn)}/return",
                               json={"reason": reason})

    def attest(self, urn: str, *, role: str, decision: str = "attest",
               statement: str = "") -> Dict[str, Any]:
        """Sign one role's half of the attestation.

        A quorum and not a button: which roles must sign is the platform's
        answer, read off `state()`, and one decline ends the attestation rather
        than being outvoted. You may only sign for a role you actually hold, and
        the SDK does not check that — the platform does, and it is the one that
        knows what you hold.
        """
        return self._maya.call("POST", f"/models/{short(urn)}/attest", json={
            "role": role, "decision": decision, "statement": statement})

    def amend(self, urn: str, *, reason: str,
              scope: Optional[List[str]] = None) -> Dict[str, Any]:
        """The only route out of immutability, and it leaves a record.

        `scope` names what the amendment touches. It is not enforcement — it is
        the sentence a reviewer reads next year when asking what changed and
        why, and an amendment whose scope is empty is one nobody can review.
        """
        return self._maya.call("POST", f"/models/{short(urn)}/amend", json={
            "reason": reason, "scope": scope or []})

    def retire(self, urn: str, *, reason: str) -> Dict[str, Any]:
        """Withdraw the model from use. Nothing is deleted.

        This is what everybody except an administrator does instead of deleting:
        the model stops being usable and the record — versions, findings,
        evidence — survives, because the questions asked about a retired model
        are the same questions asked about a live one.
        """
        return self._maya.call("POST", f"/models/{short(urn)}/retire",
                               json={"reason": reason})

    def decommission(self, urn: str, *, rationale: str, replacement: str,
                     retention_class: str,
                     notified: Optional[List[str]] = None,
                     acknowledged: bool = False) -> Dict[str, Any]:
        """Retire it, and record the four facts that otherwise go missing.

        Why, what does this job now, who was relying on it, and how long the
        record is kept. Every one of those is discovered to be needed months
        later, and they go missing because retiring a model is the moment
        everybody involved has stopped caring about it.

        `replacement` is a registered URN or the literal `"none"` — blank is
        indistinguishable from nobody having filled it in. An unnotified live
        consumer refuses the retirement; `acknowledged=True` records that
        somebody looked at the list and decided, which is a different fact from
        nobody having looked.

        MAYA notifies nobody and archives nothing. `notified` is a statement by
        whoever retired the model, and the retention class states an obligation
        rather than moving a byte.
        """
        return self._maya.call("POST", "/decommission", params={"urn": urn},
                               json={"rationale": rationale,
                                     "replacement": replacement,
                                     "retention_class": retention_class,
                                     "notified": list(notified or []),
                                     "acknowledged": bool(acknowledged)})

    def consumers(self, urn: str) -> Dict[str, Any]:
        """Who reads this model, before anybody retires it.

        From the register's own typed edges. An unwired graph answers *unknown*
        rather than *none* — retiring into a silence you have not checked is
        how a feeder model disappears and four downstream models start reading
        nulls that somebody turns into zeros.
        """
        return self._maya.call("GET", "/decommission/consumers",
                               params={"urn": urn})

    def decommissioned(self, urn: str) -> Dict[str, Any]:
        """One model's decommissioning record, or the honest absence of one.

        A model retired before this existed reads back as `decommissioned:
        false` with a reason and none of the other three facts, which is not
        the same as a model still in service — and the answer says which.
        """
        return self._maya.call("GET", "/decommission", params={"urn": urn})

    def decommissioning_estate(self) -> Dict[str, Any]:
        """*Retired* and *decommissioned*, counted separately.

        Two populations. The gap between them is every model retired before
        this existed, and it is a backlog somebody can work rather than a
        defect.
        """
        return self._maya.call("GET", "/decommission/estate")

    def delete(self, urn: str, *, reason: str = "") -> Dict[str, Any]:
        """Administrators only, and the evidence chain survives it.

        Kept here rather than hidden because a capability that exists and is
        undocumented is one somebody discovers at the worst moment. Retirement
        is the act you almost certainly want.
        """
        return self._maya.call("DELETE", f"/models/{short(urn)}",
                               params={"reason": reason})


class VersionApprovals:
    """The quorum on the thing that actually runs.

    The record was attested by several people; the version was, for a long time,
    approved by one. These close that asymmetry — and the number of signatures
    is decided by the **tier**, which is the platform's answer and not the
    requester's.

    Opening an approval and signing one live on `maya.versions`, where the rest
    of the version's acts are. They are not repeated here: two SDK spellings of
    one POST is two places for a caller to look and one of them to be stale.
    """

    def __init__(self, maya):
        self._maya = maya

    def quorum(self) -> Dict[str, Any]:
        """Who must sign, by tier, published so nobody has to read configuration.

        The table lives on the platform. A client that carried its own copy
        would be carrying a firm's model risk policy in a package that ships
        separately from it.
        """
        return self._maya.call("GET", "/version-approval-quorum")

    def needed(self, *, urn: str, semver: str) -> Dict[str, Any]:
        """What this version's approval requires, and where it stands.

        Also the honest answer when the model has no tier: approving before
        assessing would be choosing your own control depth, so this says the
        tier is undecided rather than reporting no quorum required.
        """
        return self._maya.call("GET", "/version-approvals",
                               params={"urn": urn, "semver": semver})

    def progress(self, approval_id: str) -> Dict[str, Any]:
        """Signatures so far, and which roles are still outstanding."""
        return self._maya.call("GET", f"/version-approvals/{approval_id}")

    def withdraw(self, approval_id: str) -> Dict[str, Any]:
        """Close an approval without a decision. It is not a rejection.

        A withdrawn approval and a declined one mean different things to whoever
        reads the chain later — one says nobody decided, the other says somebody
        did — and the platform keeps them apart.
        """
        return self._maya.call("POST",
                               f"/version-approvals/{approval_id}/withdraw")


class Authority:
    """Who may approve this, by tier, amount and legal entity — and in order.

    The quorum by tier is the spine and it is enforced. What a tier cannot say
    is that a $2bn book and a $4m book are different decisions, that authority
    is granted by an entity's board and does not travel, or that a second-line
    challenge signed before the first line filed anything is a signature about
    nothing.

    **The one thing worth knowing before you call any of this.** The amount
    comes from the sourced exposure fact and nowhere else, so most models do not
    have one — and where there is none the band is the *deepest* the tier
    admits, not the shallowest. An amount this register does not hold is not a
    small amount, but it compares as less than every floor, which is how an
    amount-banded matrix quietly approves everything while reporting itself as
    enforced.
    """

    def __init__(self, maya):
        self._maya = maya

    def posture(self) -> Dict[str, Any]:
        """What the matrix decides, the whole matrix, and what it cannot check."""
        return self._maya.call("GET", "/authority")

    def of(self, urn: str) -> Dict[str, Any]:
        """Which signatures this model's version approval needs, and why.

        Read `reached_by`. `"match"` means a band was chosen by measurement;
        anything else means it was chosen by absence.
        """
        return self._maya.call("GET", "/authority/model", params={"urn": urn})

    def sequence(self, urn: str) -> Dict[str, Any]:
        """What this model's NEXT approval would be sequenced as.

        A read, never the check. An approval already open carries its own
        stages and is held to those, so withdrawing or re-publishing a band
        cannot move the bar under people who are already signing.
        """
        return self._maya.call("GET", "/authority/sequence",
                               params={"urn": urn})

    def estate(self) -> Dict[str, Any]:
        """How much of the estate rests on authority nobody has re-attested."""
        return self._maya.call("GET", "/authority/estate")

    def publish(self, name: str, *, stages: List[List[str]],
                tier: Optional[int] = None, at_or_above: float = 0.0,
                legal_entity: Optional[str] = None,
                note: str = "") -> Dict[str, Any]:
        """Add a band. Until the first one, the tier quorum stands as it was.

        `stages` is a list of lists: roles that sign together, stages that sign
        in order. A flat role list cannot say *the second line signs after the
        first*, and that ordering is the half of this a quorum does not cover.
        """
        return self._maya.call("POST", "/authority/bands", json={
            "name": name, "stages": [list(s) for s in stages], "tier": tier,
            "at_or_above": at_or_above, "legal_entity": legal_entity,
            "note": note})

    def withdraw(self, name: str) -> Dict[str, Any]:
        """Withdraw a band. Open approvals keep the band they were opened under."""
        return self._maya.call("DELETE", f"/authority/bands/{name}")

    def delegate(self, principal: str, *, ceiling: float, instrument: str,
                 currency: str = "USD",
                 legal_entity: Optional[str] = None) -> Dict[str, Any]:
        """What one named person may approve, and until when.

        `instrument` is required and it is the field that gets left out: MAYA
        holds a reference to the board resolution rather than the resolution,
        so a delegation nobody can trace to a decision is exactly what an
        authority matrix exists to prevent. It expires for the same reason —
        the platform cannot tell whether the instrument still says what it said.
        """
        return self._maya.call("POST", "/authority/delegations", json={
            "principal": principal, "ceiling": ceiling,
            "instrument": instrument, "currency": currency,
            "legal_entity": legal_entity})

    def delegations(self, principal: str = "") -> Dict[str, Any]:
        """Delegations on file. Named a principal, only the live ones.

        The platform decides which of those two answers a blank principal
        means, because *live* is a governance fact — an expired delegation
        grants nothing — and a client deciding it locally would be a second
        implementation of the expiry rule.
        """
        return self._maya.call("GET", "/authority/delegations",
                               params={"principal": principal})


class Relations:
    """How one model stands to another, and what a change here reaches.

    The distinction that does the work: `input_to` **propagates** — change the
    source and this model's answer changes — and `derives_from` does not, because
    a model built from another has its own versions and its own approvals.
    Answering both with one edge makes a challenger look like a dependency and
    inflates every blast radius it appears in.

    Recording an edge, the blast radius and the shared-dependency read live on
    `maya.models`. This is the rest: the vocabulary, the removal, and one
    model's edges in both directions.
    """

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """The relations that exist and what each one means, including which
        propagate. Asked for, so a client never has to guess which is which."""
        return self._maya.call("GET", "/model-relations")

    def of(self, urn: str) -> Dict[str, Any]:
        """Everything attached to this model, upstream and downstream."""
        return self._maya.call("GET", f"/models/{short(urn)}/relations")

    def remove(self, *, from_urn: str, to_urn: str, kind: str,
               reason: str) -> Dict[str, Any]:
        """Remove an edge, with a reason.

        A POST and not a DELETE because it carries the reason, and the reason
        does not belong in a query string where it is truncated and logged. An
        edge that disappears without one is a dependency somebody stopped
        believing in and nobody can ask about.
        """
        return self._maya.call("POST", "/model-relations/remove", json={
            "from_urn": from_urn, "to_urn": to_urn, "kind": kind,
            "reason": reason})


class DistributedMonitoring:
    """Monitoring an estate that will not fit in one process.

    The scan moves off the platform; nothing else does. A job computes
    **sufficient statistics** where the data is — bin counts, a rank sum, class
    counts — and MAYA does the arithmetic from those to the metric and compares
    it to the threshold this firm's second line set.

    That is the difference between this and `maya.call` on the external
    observations endpoint. An external observation cannot be replayed, because
    MAYA does not hold the population and cannot re-derive the value. This one
    can: the statistics are what was recorded, and the metric is recomputed
    from them whenever anybody asks.

    What MAYA still cannot see is whether the job read the population it says
    it did. The predicate and the row count are recorded, and the answer says
    the population is *attested* rather than observed.
    """

    def __init__(self, maya):
        self._maya = maya

    def posture(self):
        """What this moves, what it does not, and the two things it cannot check."""
        return self._maya.call("GET", "/distributed-evaluation")

    def plan(self, monitor_id, *, since=None, until=None, partitions=64):
        """The contract one job must satisfy.

        For a drift monitor it carries the **reference bin edges and a digest
        of the sample they came from**. Compute against those edges: PSI
        against edges somebody else chose is a different measurement that
        prints the same, and a submission quoting a different digest is
        refused.

        Read `global_ranking_required`. For AUC and Gini a rank sum over one
        partition's rows is a rank sum in the wrong ordering, and summing those
        produces a number that looks like an AUC and is not.
        """
        return self._maya.call(
            "GET", f"/monitors/{monitor_id}/distributed-plan",
            params={"since": since, "until": until, "partitions": partitions})

    def submit(self, monitor_id, partitions, *, predicate, engine="",
               reference_digest="", ranked_globally=False, window=None,
               now=None):
        """Submit statistics. **Never a metric.**

        A submission carrying `psi: 0.31` would be an external observation
        wearing a better name; one carrying bin counts is something the
        register recomputes.

        `predicate` is required and is not paperwork: the one thing MAYA cannot
        check is whether the job read the population it claims, so an unstated
        predicate makes the attestation unfalsifiable.

        Every problem is reported at once and the whole submission is refused —
        a metric computed over the partitions that happened to be well-formed
        is a measurement of a population nobody chose.
        """
        return self._maya.call(
            "POST", f"/monitors/{monitor_id}/distributed-submit",
            json={"partitions": list(partitions), "predicate": predicate,
                  "engine": engine, "reference_digest": reference_digest,
                  "ranked_globally": ranked_globally,
                  "window": window or {}, "now": now})


class Rules:
    """The rule-set editor: four verbs and a vocabulary.

    A rule set is the parameter object of a model whose parameters are authored
    rather than fitted. It was always a governed object — versioned, digested,
    approved by somebody other than its author. What it lacked was any way to
    type into it except a raw JSON body, and any way for the platform to say a
    single thing about what the rules meant.

    **The split between the verbs is the design.** `vocabulary`, `check` and
    `trial` are free: they carry the read permission, record nothing, append no
    evidence, and can be called on every keystroke. `publish` is the ordinary
    `parameter:record` act — the set lands *proposed*, and somebody other than
    its author approves it, exactly as a fitted coefficient set does. That line
    is what lets an author iterate without filling the register with attempts,
    and it is why the moment a draft becomes a governed object is one act they
    had to choose.

    Approving a published set is `maya.parameters.review`. It is not repeated
    here, because publishing added no authority and neither should this module.
    """

    def __init__(self, maya):
        self._maya = maya

    def vocabulary(self) -> Dict[str, Any]:
        """Every operator an editor may offer, from the code rather than a copy.

        Including which operators need an ordered field, which is the check an
        interface most wants to make locally and most should not: a screen
        holding its own operator list is a second vocabulary, and it drifts.
        """
        return self._maya.call("GET", "/rulesets/vocabulary")

    def check(self, *, urn: str, semver: str,
              document: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a draft against the version's schemas. Free, and records nothing.

        Returns the whole report — the fields it reads, the English rendering,
        the canonical bytes, and any shadowing — rather than the first problem,
        because somebody fixing a forty-rule set wants the list.

        What makes the set *unusable* still raises. A rule that can never fire,
        two rules that contradict each other, a rule reading a field the version
        does not declare: those are refusals with a remediation, not advisories,
        because a rule that never fires still appears in the model card and in
        every committee paper and nobody reading either can tell.
        """
        return self._maya.call("POST", "/rulesets/check", json={
            "urn": urn, "semver": semver, "document": document})

    def trial(self, *, urn: str, semver: str, document: Dict[str, Any],
              rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Run a draft over sample rows. No warrant, no entitlement, no record.

        Deliberately not `/execute`: nothing is being scored — an author is
        reading their own draft back — and giving this an authority would have
        meant inventing one, which is the kind that turns up later attached to
        something else.

        Read `never_fired` before approving anything. A rule that fires on none
        of the sample is not necessarily wrong, but a set where most rules never
        fire on any realistic input is one somebody should look at first.
        """
        return self._maya.call("POST", "/rulesets/trial", json={
            "urn": urn, "semver": semver, "document": document,
            "rows": rows or []})

    def publish(self, *, urn: str, semver: str, name: str,
                document: Dict[str, Any], note: str = "") -> Dict[str, Any]:
        """Record the rule set as a parameter set, checked first.

        The one authoritative verb here, and it adds no authority of its own:
        this is `POST /parameters` reached through a door that validates the
        document. The set lands `proposed`; self-approval is refused there as it
        is everywhere else.
        """
        return self._maya.call("POST", "/rulesets", json={
            "urn": urn, "semver": semver, "name": name, "document": document,
            "note": note})

    def explain(self, parameter_set_id: str) -> Dict[str, Any]:
        """A published rule set in English. Carries no authority, records nothing.

        One rendering, so the model card, the committee paper and the export pack
        quote the same sentences — the differences between three renderings are
        exactly where a misreading survives.
        """
        return self._maya.call("GET", f"/rulesets/{parameter_set_id}")


class Fibres:
    """The fibration: what varies with the trainability class, asked rather than assumed.

    `L-15` says every class carries a **total** evidence schema, lifecycle,
    metric set and template set, and that no fibre is empty. A class with an
    empty facet is one the platform can say nothing about, which in practice
    means one it silently skips.

    This module holds no list of classes and no list of what any of them admits.
    Both come back from the platform, and that is not tidiness: asking a pricer
    with no fitted parameters for out-of-sample discrimination is not rigour, it
    is a category error that wastes a review cycle and teaches everybody that
    the checklist is noise. Which questions a class can answer is a governance
    rule, and this package is the wrong place for a second copy of one.
    """

    def __init__(self, maya):
        self._maya = maya

    def list(self) -> Dict[str, Any]:
        """Every fibre, with the base it is over and whether the fibration is total.

        Read `total` before trusting a facet. A partial fibration is the platform
        reporting a gap in itself, and a client that skipped past it would be
        showing a class's evidence requirements as complete when they are not.
        """
        return self._maya.call("GET", "/fibres")

    def of(self, trainability_class: str) -> Dict[str, Any]:
        """One fibre, with all four facets and the three sentences that say what
        each facet is *for*.

        The class is a value the caller passes in — read off a version the
        platform derived it for, never spelled out here. Refuses `no_fibre`
        rather than answering with an empty shape, because an empty fibre is
        what the law forbids and returning one would be the platform reporting
        its own violation as data.
        """
        return self._maya.call("GET", f"/fibres/{trainability_class}")


class FeatureCatalogue:
    """The rest of a feature's life: reading, checking, certifying, sealing, ending.

    `maya.features` defines them and loads values into them. This is everything
    that happens afterwards, and the ordering of the ideas matters: a feature is
    an **object with an owner and a history**, so it is amended rather than
    overwritten, transferred rather than reassigned, and sealed rather than
    locked — a sealed feature can still be composed from, which is what sealing
    is for.

    `check` and `trial` are free, in the same sense the rule-set editor's are.
    """

    def __init__(self, maya):
        self._maya = maya

    def list(self, *, entity: Optional[str] = None) -> Dict[str, Any]:
        """The catalogue, optionally for one entity. Filtered on the platform."""
        return self._maya.call("GET", "/features", params={"entity": entity})

    def resolved(self, name: str) -> Dict[str, Any]:
        """The feature as it actually stands — not what its row says.

        Its row plus its parents plus its own operations, with its shape, its
        retrieval policy and how long it has left. Working that out is the
        platform's job: a client that walked the composition itself would be
        computing an answer the platform already computes, differently.
        """
        return self._maya.call("GET", f"/features/{name}/resolved")

    def check(self, *, name: str = "", entity: str = "", dtype: str = "numeric",
              description: str = "", kind: str = "primitive",
              expression: str = "", evaluator: str = "internal",
              on_error: str = "null", shape: Any = None,
              components: Optional[List[str]] = None,
              defaults: Optional[Dict[str, Any]] = None,
              inputs: Optional[List[str]] = None) -> Dict[str, Any]:
        """Would this definition be accepted? Records nothing either way.

        Carries the read permission and not the define permission, for the
        reason the rule-set editor's check does: requiring the writing
        permission in order to look at whether a draft is sound teaches authors
        to skip the step.
        """
        return self._maya.call("POST", "/features/check", json={
            "kind": kind, "name": name, "entity": entity, "dtype": dtype,
            "description": description, "shape": shape,
            "components": components, "defaults": defaults,
            "expression": expression, "evaluator": evaluator,
            "on_error": on_error, "inputs": inputs or []})

    def trial(self, *, expression: str, rows: List[Dict[str, Any]],
              on_error: str = "null") -> Dict[str, Any]:
        """Read a draft expression over sample rows. Records nothing.

        Two answers worth having before declaring anything: where the arithmetic
        has no answer, and where the inherited ingest clock moves. Both are
        decided by the functions a real materialisation uses, so a trial that
        passes is not a different check from the one that matters.
        """
        return self._maya.call("POST", "/features/trial", json={
            "expression": expression, "on_error": on_error, "rows": rows})

    def certify(self, name: str, *, level: str = "certified") -> Dict[str, Any]:
        """Raise a feature's certification level.

        Certification is a statement about how far the definition has been
        checked, not about the values. The levels come from the platform.
        """
        return self._maya.call("POST", f"/features/{name}/certify",
                               params={"level": level})

    def amend(self, name: str, *, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Revise a definition. Refused once it is sealed."""
        return self._maya.call("POST", f"/features/{name}/amend",
                               json={"fields": fields})

    def seal(self, name: str, *, note: str = "") -> Dict[str, Any]:
        """Declare it final — and it can still be composed from. That is the point.

        A parent that cannot move is worth building on; a parent that can is a
        dependency whose meaning changes underneath everything derived from it.
        """
        return self._maya.call("POST", f"/features/{name}/seal",
                               json={"note": note})

    def break_seal(self, name: str, *, reason: str) -> Dict[str, Any]:
        """Administrators only, and never quietly. The reason goes on the record."""
        return self._maya.call("POST", f"/features/{name}/break-seal",
                               json={"reason": reason})

    def transfer(self, name: str, *, to: str, reason: str = "") -> Dict[str, Any]:
        """Hand on the ownership. The creator does not move — they are a fact."""
        return self._maya.call("POST", f"/features/{name}/transfer",
                               json={"to": to, "reason": reason})

    def destroy(self, name: str) -> Dict[str, Any]:
        """Remove an ephemeral feature. The rows go; the record does not."""
        return self._maya.call("DELETE", f"/features/{name}")

    # ------------------------------------------------------------ vocabulary
    def expression_language(self) -> Dict[str, Any]:
        """What a derived feature may be written in. Deliberately small.

        Small because the analysis is the point: a free expression is opaque,
        and an opaque definition cannot be checked for leakage, lineage or
        anything else worth checking.
        """
        return self._maya.call("GET", "/expression-language")

    def retrieval(self) -> Dict[str, Any]:
        """What the platform will do to values on the way out, and the rules it obeys.

        Preparation, alignment, policy and composition in one answer, so a client
        offering these options offers the ones that exist.
        """
        return self._maya.call("GET", "/retrieval")

    def transfer_formats(self) -> Dict[str, Any]:
        """What the bulk surface reads and writes, so a client need not guess."""
        return self._maya.call("GET", "/transfer")

    def derived(self) -> Dict[str, Any]:
        """Every derived feature. Its lineage is on `maya.features.lineage`."""
        return self._maya.call("GET", "/derived-features")


class FeatureViews:
    """Where values live, and the pin that makes a read reproducible.

    One upload is one view version, because a version is what a featureset pins
    and half a version is not something anybody can pin. Everything below reads
    at a **pinned** version rather than at the head, so what comes out is what
    that version is and not what the path has since become.
    """

    def __init__(self, maya):
        self._maya = maya

    def list(self) -> Dict[str, Any]:
        return self._maya.call("GET", "/feature-views")

    def versions(self, name: str) -> Dict[str, Any]:
        return self._maya.call("GET", f"/feature-views/{name}/versions")

    def materialise(self, name: str, *,
                    rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Write rows as one new view version.

        For anything of a real size use `maya.features.load`, which streams a
        file: this takes the rows in the request body and is therefore bounded
        by what a request body can carry.
        """
        return self._maya.call("POST", f"/feature-views/{name}/materialise",
                               json={"rows": rows})

    def retirable(self, name: str, *, version: int) -> Dict[str, Any]:
        """Whether this version can be retired, and who is pinning it if not.

        The list of pinners is the useful half. "No" without them is a wall;
        with them it is a short conversation with three named owners.
        """
        return self._maya.call(
            "GET", f"/feature-views/{name}/versions/{version}/retirable")

    def as_of(self, name: str, *, version: int, label_ts: float, as_of: float,
              entity_id: Optional[str] = None,
              limit: Optional[int] = None) -> Dict[str, Any]:
        """The point-in-time read, explained row by row. Free, and writes nothing.

        Which row the rule admits, and which of the two clocks refused the rest.
        It is a read and not an assembly: no snapshot, no evidence, no warrant.
        Conflating the two acts is why nobody looks at the answer before
        building a training set out of it.
        """
        body = {"label_ts": label_ts, "as_of": as_of,
                "entity_id": entity_id, "limit": limit}
        return self._maya.call(
            "POST", f"/feature-views/{name}/versions/{version}/as-of",
            json={k: v for k, v in body.items() if v is not None})

    def alignment_trial(self, *, rows: List[Dict[str, Any]],
                        columns: Optional[List[str]] = None,
                        axis: Optional[str] = None, rule: Optional[str] = None,
                        grid: Optional[str] = None,
                        start: Optional[float] = None,
                        stop: Optional[float] = None,
                        step: Optional[float] = None,
                        points: Optional[List[float]] = None,
                        carry_limit: Optional[float] = None) -> Dict[str, Any]:
        """Align sample rows onto an axis. Aligns nothing that is stored.

        The axis, the fill rule and the grid all default to the platform's own
        defaults when omitted, which is why they are optional here rather than
        given values this package would have to keep in step.
        """
        body = {"rows": rows, "columns": columns or [], "axis": axis,
                "rule": rule, "grid": grid, "start": start, "stop": stop,
                "step": step, "points": points, "carry_limit": carry_limit}
        return self._maya.call("POST", "/features/alignment-trial",
                               json={k: v for k, v in body.items()
                                     if v is not None})

    def data(self, name: str, *, version: int, into: Union[str, Path],
             format: str = "parquet", columns: Optional[List[str]] = None,
             limit: Optional[int] = None) -> Path:
        """Stream one view version to a file. Returns the path.

        A path and not a list of dictionaries, for the reason the featureset
        read gives: these are not small, and an SDK that materialised them to be
        convenient would be convenient until the first real dataset.
        """
        body = self._maya.call(
            "GET", f"/feature-views/{name}/versions/{version}/data",
            params={"format": format, "limit": limit,
                    "columns": ",".join(columns) if columns else None},
            raw=True)
        destination = Path(into)
        destination.write_bytes(body)
        return destination


class FeatureContracts:
    """What a version must read at serving time, declared rather than inferred.

    A contract binds a model version to exact features. It is what makes `L-17`
    checkable: the platform can compare what serving *did* read against what it
    was supposed to, and a mismatch is a finding rather than a rumour. Without
    the declaration there is nothing to compare against, and "the model read
    what it read" is not an assurance.
    """

    def __init__(self, maya):
        self._maya = maya

    def bind(self, *, model_version_id: str,
             items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Declare the features this version reads, and at what pins."""
        return self._maya.call("POST", "/feature-contracts", json={
            "model_version_id": model_version_id, "items": items})

    def namespaces(self, model_version_id: str) -> Dict[str, Any]:
        """The namespaces serving MUST read. `L-17` compares this to what it did."""
        return self._maya.call(
            "GET", f"/feature-contracts/{model_version_id}/namespaces")


class TrainingSets:
    """Point-in-time-correct assembly from feature views.

    Assembly from a **featureset version** is `maya.featuresets.training_set`,
    and it is the one to prefer: it pins the columns as well as the rows. This
    one takes the views explicitly, for the case where there is no featureset —
    a one-off analysis, or a set being put together before it is declared.

    Both bounds default to on, and leaving them on is the whole point. Valid time
    asks what was *true* at the moment; transaction time asks what was *known*.
    Dropping the second is how a restatement quietly rewrites history and a model
    is trained on figures nobody had.
    """

    def __init__(self, maya):
        self._maya = maya

    def build(self, *, name: str, spine: List[Dict[str, Any]],
              views: List[Dict[str, Any]], as_of: float,
              valid_time_bound: bool = True,
              transaction_time_bound: bool = True) -> Dict[str, Any]:
        return self._maya.call("POST", "/training-sets", json={
            "name": name, "spine": spine, "views": views, "as_of": as_of,
            "valid_time_bound": valid_time_bound,
            "transaction_time_bound": transaction_time_bound})


class FeaturesetAlgebra:
    """Composition, the plan an engine executes, and whether the ground has moved.

    `maya.featuresets` declares a set, previews a fold, fills a version and
    reads the rows. This is the rest of the algebra.

    Two of these answer questions people otherwise answer by guessing.
    `plan` is everything needed to assemble one version, in one document, so an
    engine reads a plan rather than reconstructing one from five endpoints.
    `restatements` answers the neighbouring question a reviewer actually asks
    before comparing two runs: the version still reads the bytes it pinned —
    that is what a pin is for — but *has anything underneath it been written to
    since*. Those are different questions and only one of them is about
    reproducibility.
    """

    def __init__(self, maya):
        self._maya = maya

    def list(self) -> Dict[str, Any]:
        return self._maya.call("GET", "/featuresets")

    def plan(self, name: str, *, version: int) -> Dict[str, Any]:
        """Everything an engine needs to assemble this version, in one document."""
        return self._maya.call("GET", f"/featuresets/{name}/versions/{version}")

    def restatements(self, name: str, *, version: int) -> Dict[str, Any]:
        """Has anything underneath this version been written to since it was pinned?

        Not a reproducibility failure — the pinned read is unchanged — but the
        fact a reviewer needs before treating two runs as comparable.
        """
        return self._maya.call(
            "GET", f"/featuresets/{name}/versions/{version}/restatements")

    def roll_forward(self, name: str) -> Dict[str, Any]:
        """Take up newer view versions on purpose, and see what moved.

        Deliberate rather than automatic. A set that followed its inputs forward
        by itself would make every fit against it unreproducible, and the moment
        it happened would be nobody's decision.
        """
        return self._maya.call("POST", f"/featuresets/{name}/roll-forward")

    def prepared(self, name: str, *, version: int, as_of: Any = None,
                 fill: Optional[Dict[str, Any]] = None,
                 normalise: Optional[Dict[str, str]] = None,
                 align: Optional[Dict[str, Any]] = None,
                 limit: Optional[int] = None) -> Dict[str, Any]:
        """The rows with the platform's preparation applied, and the statistics.

        Aligned onto an axis if asked, gaps filled, normalised — with the
        statistics fitted from what was **knowable at the stated moment** and
        returned alongside the rows, so the same transform can be applied to one
        row tomorrow. A normalisation whose parameters are not written down is
        one that cannot be reapplied at serving time, which is the most common
        way a training/serving skew is introduced by accident.

        The policy is the featureset's own default, overridden column by column
        by anything passed here.
        """
        return self._maya.call(
            "POST", f"/featuresets/{name}/versions/{version}/prepared", json={
                "as_of": as_of, "fill": fill or {},
                "normalise": normalise or {}, "align": align or {},
                "limit": limit})

    def set_policy(self, name: str, *,
                   defaults: Dict[str, Any]) -> Dict[str, Any]:
        """Attach default retrieval behaviour. A request may still override it."""
        return self._maya.call("PUT", f"/featuresets/{name}/policy",
                               json={"defaults": defaults})

    def transfer(self, name: str, *, to: str, reason: str = "") -> Dict[str, Any]:
        """Hand on ownership of the set."""
        return self._maya.call("POST", f"/featuresets/{name}/transfer",
                               json={"to": to, "reason": reason})

    def destroy(self, name: str) -> Dict[str, Any]:
        """Remove an ephemeral featureset. Refused where a version is pinned to it."""
        return self._maya.call("DELETE", f"/featuresets/{name}")


class Validations:
    """The second line's episode: opened, evidenced, concluded, replayed.

    A validation is not a document. It is an episode with named validators, a
    scope, recorded test results and one conclusion — and the conclusion is
    refused to whoever created the version, however their roles are arranged,
    because the evidence chain recorded who created it.

    The replay is the part worth understanding. `replay` recomputes from data
    the caller supplies; `replay_from_storage` re-reads the snapshot the episode
    was **pinned** to and supplies nothing, so a mismatch is about the test
    rather than about who handed over which file. Prefer the second.
    """

    def __init__(self, maya):
        self._maya = maya

    def tests(self) -> Dict[str, Any]:
        """The registered catalogue. A validation may only run these.

        A closed catalogue rather than arbitrary code, because a test nobody
        registered is one nobody can replay and one whose threshold nobody
        agreed.
        """
        return self._maya.call("GET", "/tests")

    def open(self, *, urn: str, semver: str, validators: List[str],
             kind: str = "initial", scope: Optional[List[str]] = None,
             plan: Optional[Dict[str, Any]] = None,
             snapshot_id: Optional[str] = None,
             due_at: Optional[float] = None) -> Dict[str, Any]:
        """Open an episode. Pin a snapshot if there is one.

        `snapshot_id` is optional and worth supplying: an episode that pins no
        dataset cannot be replayed without somebody producing the data again,
        and the person who can produce it is usually the person under challenge.
        """
        return self._maya.call("POST", "/validations", json={
            "urn": urn, "semver": semver, "validators": validators,
            "kind": kind, "scope": scope or [], "plan": plan or {},
            "snapshot_id": snapshot_id, "due_at": due_at})

    def get(self, validation_id: str) -> Dict[str, Any]:
        """The episode with its results and its summary."""
        return self._maya.call("GET", f"/validations/{validation_id}")

    def record(self, validation_id: str, *, test_key: str, left: List[float],
               right: List[float], threshold: Optional[Dict[str, Any]] = None,
               parameters: Optional[Dict[str, Any]] = None,
               slice: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record one test result, with the threshold it was judged against.

        The threshold travels with the result rather than being looked up later,
        because a result read against a threshold that has since moved is a
        different claim from the one that was made.
        """
        return self._maya.call(
            "POST", f"/validations/{validation_id}/results", json={
                "test_key": test_key, "left": left, "right": right,
                "threshold": threshold or {}, "parameters": parameters or {},
                "slice": slice or {}})

    def recode(self, validation_id: str, *, model: Dict[str, float],
               recode: Dict[str, float], tolerance: float = 1e-9,
               model_source: str = "unstated",
               recode_source: str = "unstated") -> Dict[str, Any]:
        """Compare an independent implementation against the model's.

        Both sides are **outputs keyed by the input each was given**, not code:
        MAYA does not execute the validator's implementation, because running
        arbitrary code in the control plane is not a thing a register should do
        — and where each side came from is recorded rather than assumed.

        **The distribution is the point.** A recode agreeing to twelve decimal
        places on 9,997 rows and disagreeing wildly on three is a completely
        different finding from one off by 1e-9 everywhere, and a pass rate
        reports them identically. The first is a branch nobody tested, and it is
        exactly what independent recode exists to find.
        """
        return self._maya.call("POST", f"/validations/{validation_id}/recode",
                               json={"model": model, "recode": recode,
                                     "tolerance": tolerance,
                                     "model_source": model_source,
                                     "recode_source": recode_source})

    def conclude(self, validation_id: str, *, outcome: str,
                 tier_verdict: str,
                 conditions: Optional[List[str]] = None,
                 tier_note: str = "") -> Dict[str, Any]:
        """Reach the verdict. Never as whoever created the version.

        `tier_verdict` is required and has no default. SS1/23 1.3(e) asks that
        the model's risk tier be re-assessed *during* validation, and an
        episode concluded without a verdict is indistinguishable from one where
        the validator looked and agreed — which are the two answers a
        supervisor most needs told apart. The three are `remains_appropriate`,
        `should_be_higher` and `should_be_lower`; the last two need a
        `tier_note`, and `should_be_higher` raises a finding.
        """
        return self._maya.call(
            "POST", f"/validations/{validation_id}/conclude",
            json={"outcome": outcome, "conditions": conditions or [],
                  "tier_verdict": tier_verdict, "tier_note": tier_note})

    def tier_verdicts(self) -> Dict[str, Any]:
        """The three a validator may reach about a tier, and what each causes."""
        return self._maya.call("GET", "/tier-verdicts")

    def replay(self, validation_id: str, *,
               data: Optional[Dict[str, List[List[float]]]] = None) -> Dict[str, Any]:
        """Recompute the recorded tests from supplied data and compare digests.

        A key left out is reported as skipped rather than as passing, which is
        the distinction the whole exercise turns on.
        """
        return self._maya.call("POST", f"/validations/{validation_id}/replay",
                               json={"data": data or {}})

    def replay_from_storage(self, validation_id: str) -> Dict[str, Any]:
        """Replay by re-reading the pinned snapshot. Nothing is supplied.

        The stronger of the two replays, and the reason snapshots are pinned in
        the first place.
        """
        return self._maya.call(
            "POST", f"/validations/{validation_id}/replay-from-storage")

    def replayable(self, validation_id: str) -> Dict[str, Any]:
        """What a replay would read, and whether the ground under it moved."""
        return self._maya.call("GET", f"/validations/{validation_id}/replayable")


class Findings:
    """The register, which is a control surface and not a log.

    An open blocking finding refuses an alias move and refuses warrant
    resolution. That is what makes the register worth keeping honest, and it is
    why two of these acts exist to be refused: **acknowledgement is refused to
    anybody but the owner**, and **extension is refused to the owner**, so the
    person with the deadline cannot set it and the person setting it has to be
    somebody else.

    Closing is attributed to whoever performs it. Naming somebody else is
    refused rather than ignored — that forged attribution used to reach the
    permanent evidence chain.
    """

    def __init__(self, maya):
        self._maya = maya

    def acts(self) -> Dict[str, Any]:
        """The acts a finding can go through, and what each one means."""
        return self._maya.call("GET", "/finding-acts")

    def raise_finding(self, *, urn: str, severity: str, title: str, owner: str,
                      description: str = "", category: str = "general",
                      source: str = "validation",
                      validation_id: Optional[str] = None,
                      affected_component: Optional[str] = None,
                      blocking: Optional[bool] = None) -> Dict[str, Any]:
        """Raise one against a model.

        `blocking` is left unset by default on purpose: whether a finding of this
        severity blocks is the platform's rule, and passing a value here is
        overriding it rather than describing it.
        """
        return self._maya.call("POST", "/findings", json={
            "urn": urn, "severity": severity, "title": title, "owner": owner,
            "description": description, "category": category, "source": source,
            "validation_id": validation_id,
            "affected_component": affected_component, "blocking": blocking})

    def for_model(self, urn: str) -> Dict[str, Any]:
        """Open and blocking findings for one model, with the summary."""
        return self._maya.call("GET", "/findings", params={"urn": urn})

    def get(self, finding_id: str) -> Dict[str, Any]:
        """One finding and everything derived from what has happened to it."""
        return self._maya.call("GET", f"/findings/{finding_id}")

    def ageing(self, *, urn: Optional[str] = None) -> Dict[str, Any]:
        """Severity, age, overdue and extension counts.

        Without a URN this is the estate, filtered to the models the caller can
        see — a committee pack for a population somebody cannot look at is a
        number they cannot check. The filtering happens on the platform.
        """
        return self._maya.call("GET", "/findings/ageing", params={"urn": urn})

    def escalated(self, *, urn: Optional[str] = None) -> Dict[str, Any]:
        """What is no longer only its owner's problem — by role, not hierarchy.

        The platform does not know who reports to whom, so an escalation names a
        role. That is a limit worth stating plainly rather than papering over.
        """
        return self._maya.call("GET", "/findings/escalated", params={"urn": urn})

    def escalation(self, finding_id: str) -> Dict[str, Any]:
        """Whether this one has stopped being only its owner's problem, and why."""
        return self._maya.call("GET", f"/findings/{finding_id}/escalation")

    def assign(self, finding_id: str, *, to: str, reason: str) -> Dict[str, Any]:
        """Hand it over, with the handover on the record."""
        return self._maya.call("POST", f"/findings/{finding_id}/assign",
                               json={"to": to, "reason": reason})

    def acknowledge(self, finding_id: str, *,
                    committed_at: Optional[float] = None,
                    days: Optional[float] = None,
                    plan: str = "") -> Dict[str, Any]:
        """The owner accepts it and names the date. Nobody may do this for them.

        Give the date either way round — `committed_at` as a moment or `days`
        from now — because both are how people actually say it.
        """
        return self._maya.call("POST", f"/findings/{finding_id}/acknowledge",
                               json={"committed_at": committed_at,
                                     "days": days, "plan": plan})

    def plan(self, finding_id: str, *, plan: str) -> Dict[str, Any]:
        """What will be done to close it."""
        return self._maya.call("POST", f"/findings/{finding_id}/plan",
                               json={"plan": plan})

    def extend(self, finding_id: str, *, reason: str,
               days: Optional[float] = None,
               due_at: Optional[float] = None) -> Dict[str, Any]:
        """Move the remediation date. Not by its owner, and never silently."""
        return self._maya.call("POST", f"/findings/{finding_id}/extend",
                               json={"reason": reason, "days": days,
                                     "due_at": due_at})

    def close(self, finding_id: str, *, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Close it against evidence. The verifier is whoever is asking.

        There is deliberately no `verified_by` argument. It was a request field
        once, which let the owner of a blocking finding close their own by naming
        somebody else — and the forged attribution went into the evidence chain.
        """
        return self._maya.call("POST", f"/findings/{finding_id}/close",
                               json={"evidence": evidence})


class Monitors:
    """Measurement wired to consequence, which is what makes it not a dashboard.

    A breach raises a finding, a finding can block, and a blocking finding
    refuses warrant resolution. The chain from measurement to refusal is
    mechanical rather than dependent on somebody watching a screen.

    Which kinds of question a model can be asked depends on its trainability
    class, and this package does not know that mapping — `monitor_kinds()` and
    `maya.fibres` are where it comes from. A monitor the class does not admit is
    refused by the platform, which is the correct place for that refusal.
    """

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """Which questions can be asked, which tests answer them, and which need
        labels — the last being why a performance monitor cannot report today."""
        return self._maya.call("GET", "/monitor-kinds")

    def list(self, urn: str) -> Dict[str, Any]:
        """Every monitor on a model, with where each one stands."""
        return self._maya.call("GET", "/monitors", params={"urn": urn})

    def define(self, *, urn: str, name: str, kind: str, test_key: str,
               threshold: Dict[str, Any], owner: str,
               reference: Optional[Dict[str, Any]] = None,
               slice: Optional[Dict[str, Any]] = None,
               cadence_days: float = 1.0, label_delay_days: float = 0.0,
               breach_severity: str = "Medium",
               escalate_after: int = 3) -> Dict[str, Any]:
        """Define one.

        `label_delay_days` is the field people leave at zero and should not: a
        performance monitor evaluated over a cohort whose outcomes have not
        matured measures the maturity of the cohort, not the model. The platform
        refuses an immature evaluation, and this is what tells it when maturity
        arrives.
        """
        return self._maya.call("POST", "/monitors", json={
            "urn": urn, "name": name, "kind": kind, "test_key": test_key,
            "threshold": threshold, "owner": owner,
            "reference": reference or {}, "slice": slice or {},
            "cadence_days": cadence_days, "label_delay_days": label_delay_days,
            "breach_severity": breach_severity,
            "escalate_after": escalate_after})

    def defaults(self, urn: str) -> Dict[str, Any]:
        """What this model's class and tier say it should be watched for.

        And what it should NOT be. A model with no performance monitor because
        its class cannot answer that question, and one with no performance
        monitor because nobody got round to it, look identical on every
        coverage screen ever built — so the answer separates them.
        """
        return self._maya.call("GET", "/monitor-defaults", params={"urn": urn})

    def seed_defaults(self, urn: str, *,
                      owner: Optional[str] = None) -> Dict[str, Any]:
        """Create the proposed monitors that are not already there.

        An explicit act rather than something registration does for you: an
        estate that acquires monitors nobody asked for is one whose coverage
        nobody understands. Idempotent by kind and test.
        """
        # `owner` is sent as it arrives, empty or not. Branching on it here
        # would be this package deciding what an absent owner means, and the
        # server already has a better answer than the SDK could invent: the
        # model's own owner, then the actor.
        return self._maya.call("POST", "/monitor-defaults",
                               params={"urn": urn, "owner": owner or ""})

    def evaluate(self, monitor_id: str, *,
                 rows: Optional[List[Dict[str, Any]]] = None,
                 reference: Optional[List[float]] = None,
                 now: Optional[float] = None) -> Dict[str, Any]:
        """Compute one observation from rows you supply. Refused over an
        immature cohort, which is a refusal to want rather than to work around."""
        return self._maya.call("POST", f"/monitors/{monitor_id}/evaluate",
                               json={"rows": rows or [], "reference": reference,
                                     "now": now})

    def evaluate_from_telemetry(self, monitor_id: str, *,
                                since: Optional[float] = None,
                                until: Optional[float] = None,
                                reference_from: Optional[float] = None,
                                reference_to: Optional[float] = None) -> Dict[str, Any]:
        """Evaluate against telemetry the platform already holds.

        The stronger of the two: whoever supplies the rows does not also get to
        rule on them. The window is read at the moment it names rather than at
        the moment the read happens, so a review of last quarter sees the
        population last quarter saw.
        """
        return self._maya.call(
            "POST", f"/monitors/{monitor_id}/evaluate-from-telemetry",
            json={"since": since, "until": until,
                  "reference_from": reference_from,
                  "reference_to": reference_to})

    def observations(self, monitor_id: str) -> Dict[str, Any]:
        """The history and any breaches raised from it."""
        return self._maya.call("GET", f"/monitors/{monitor_id}/observations")

    def ingest(self, monitor_id: str, *, value: Optional[float],
               computed_by: str, window_start: float, window_end: float,
               method: str = "", sample_size: int = 0,
               now: Optional[float] = None) -> Dict[str, Any]:
        """Hand MAYA a number computed somewhere else.

        There is deliberately no `passed` parameter and there will not be one.
        MAYA takes the value and refuses the verdict: the threshold is the one
        this firm's second line set on the monitor, and the comparison happens
        in the platform. A system that could push its own metric *and* its own
        pass mark would be marking its own homework, which is the failure mode
        every "send us your metrics" API has.

        `computed_by` is required, because a number of unknown origin sitting in
        the system of record is worse than no number — it looks like one MAYA
        stands behind. And the window is required, because an observation that
        does not say what it covers cannot be paired, trended or read as-at a
        date.
        """
        return self._maya.call("POST", f"/monitors/{monitor_id}/ingest", json={
            "value": value, "computed_by": computed_by, "method": method,
            "sample_size": sample_size, "window_start": window_start,
            "window_end": window_end, "now": now})

    def provenance(self, monitor_id: Optional[str] = None) -> Dict[str, Any]:
        """How much of this monitoring MAYA could reproduce, and how much it could not.

        An external observation cannot be replayed: the platform does not hold
        the population it was computed over. That is a real loss of assurance
        and the price of not mandating the compute — an estate where most of
        the numbers cannot be re-derived is a finding about the programme, and
        an invisible one if both kinds print the same.
        """
        params = {"monitor_id": monitor_id} if monitor_id else {}
        return self._maya.call("GET", "/monitoring-provenance", params=params)

    def health(self, urn: Optional[str] = None,
               now: Optional[float] = None) -> Dict[str, Any]:
        """One model's health, or the estate's, with the derivation attached.

        Read `coverage` before `score`. Absent components are excluded from the
        denominator rather than scored well, so a high score over a small share
        of the weight is a model nobody has looked at rather than a healthy one,
        and the two would otherwise print the same.

        And read `band` rather than `score`. The band is the mean capped by
        conditions no amount of good news elsewhere may outweigh — a lapsed
        validation, an overdue Critical finding, an overlay nobody has measured.
        Where `band` is worse than `arithmetic_band`, the gap is the finding.
        """
        # Sent as they arrive. The transport drops what is None, so an absent
        # urn asks the estate question and a present one asks about a model —
        # and this package never decides which of those the caller meant.
        return self._maya.call("GET", "/model-health",
                               params={"urn": urn, "now": now})

    def health_components(self) -> Dict[str, Any]:
        """The weights, published before anything is scored."""
        return self._maya.call("GET", "/model-health/components")

    def compare(self, urn: str, *, champion: str, challenger: str,
                material: Optional[float] = None,
                now: Optional[float] = None) -> Dict[str, Any]:
        """Champion against challenger, paired window by window.

        `significant` and `material` are separate answers and both are returned.
        With enough windows any difference becomes significant, including one
        nobody would act on — so materiality is asked separately, in the units
        of the test itself, and defaults to something small enough to argue
        with rather than large enough to hide behind.

        The recommendation is never to promote. MAYA does not decide which model
        the bank uses, and promotion is a second-line approval this must not
        pre-empt; the strongest thing here is that the evidence for opening a
        validation is strong.
        """
        return self._maya.call("GET", "/champion-challenger",
                               params={"urn": urn, "champion": champion,
                                       "challenger": challenger,
                                       "material": material, "now": now})

    def challengers(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every version being run beside the one production serves."""
        params = {"now": now} if now is not None else {}
        return self._maya.call("GET", "/champion-challenger", params=params)

    def set_status(self, monitor_id: str, *, status: str) -> Dict[str, Any]:
        """Suspend or resume a monitor. A suspended monitor is still on the record.

        Which is the point: a monitor that was quietly turned off before a
        breach is exactly what a reviewer is looking for, so turning it off is
        an act rather than a deletion.
        """
        return self._maya.call("POST", f"/monitors/{monitor_id}/status",
                               params={"status": status})


class Reports:
    """Structured queries over the register, saved views, and extracts.

    There is no method here that takes query text, and there will not be one. A
    read layer that accepted SQL could promise nothing about what a query can
    reach — and the first thing a BI tool does with table access is invent its
    own definition of *in force*, which then lives in a dashboard nobody
    governs and is the one that reaches the committee.

    Read `catalogue()` first. A field marked `derived` is computed by the same
    code the screens use, so `in_force` here is the platform's `in_force`.
    """

    def __init__(self, maya):
        self._maya = maya

    def catalogue(self) -> Dict[str, Any]:
        """Every entity, field and operator, with the derived fields marked."""
        return self._maya.call("GET", "/semantic-layer")

    def query(self, entity: str, *,
              select: Optional[List[str]] = None,
              where: Optional[List[Dict[str, Any]]] = None,
              order_by: str = "", descending: bool = False,
              limit: int = 1000) -> Dict[str, Any]:
        """Run one structured query under your own scope.

        Scope filters ROWS rather than refusing the call, and `outside_scope`
        says how many it removed. Read it: a total that is silently short gets
        reconciled against somebody else's total, and the difference is
        attributed to a bug rather than to a permission.
        """
        return self._maya.call("POST", "/query", json={
            "entity": entity, "select": select, "where": where or [],
            "order_by": order_by, "descending": descending, "limit": limit})

    def views(self) -> Dict[str, Any]:
        """Your saved views, and everything shared with you."""
        return self._maya.call("GET", "/saved-views")

    def save_view(self, name: str, *, entity: str, query: Dict[str, Any],
                  description: str = "", shared: bool = False) -> Dict[str, Any]:
        """Keep a query.

        A view stores the **query** and never the rows. Sharing one therefore
        discloses nothing: it re-runs under whoever opens it, and two readers
        legitimately see different numbers. Had the rows been stored, sharing
        would carry the author's scope to the reader — a disclosure nobody
        realised they were making.
        """
        return self._maya.call("POST", "/saved-views", json={
            "name": name, "entity": entity, "query": query,
            "description": description, "shared": shared})

    def run_view(self, view_id: str, *,
                 limit: Optional[int] = None) -> Dict[str, Any]:
        """Run a saved view under your scope, not its author's."""
        return self._maya.call("GET", f"/saved-views/{view_id}",
                               params={"limit": limit})

    def delete_view(self, view_id: str) -> Dict[str, Any]:
        """Remove one of your own views."""
        return self._maya.call("DELETE", f"/saved-views/{view_id}")

    def export_formats(self) -> Dict[str, Any]:
        """The three offered, and the ones refused with the reason.

        `xlsx` is refused rather than absent: a binary workbook cannot be
        diffed, carries formatting and formulas that are not in the register,
        and invites the edit-then-circulate cycle that turns an extract into a
        second source of truth nobody versions. CSV opens in Excel.
        """
        return self._maya.call("GET", "/export-formats")

    def vocabulary(self) -> Dict[str, Any]:
        """What a question in English may be built from, and who translates it.

        Read `translated_by`. Where no provider is wired MAYA matches the
        published vocabulary — deterministic and weaker — and how much a reader
        should trust a translation depends entirely on which of the two produced
        it.
        """
        return self._maya.call("GET", "/ask/vocabulary")

    def ask(self, question: str, *, limit: int = 100) -> Dict[str, Any]:
        """Ask in English. The answer always carries the query it became.

        **The translation produces a query and never a number.** The rows come
        from the register, computed by the same code the screens use, under your
        own scope — nothing a model emitted is in them.

        Read `proposed` before `result`, every time. An interface that shows
        only the answer is one where nobody can tell a misread question from a
        wrong number, and the misread question is far commoner: somebody asking
        how many models are unmonitored and being handed 4 has no way to know
        the query counted retired ones.

        When the proposal names something the register does not have,
        `understood` is false and `result` is None. It is not retried into
        something that parses — a query answering a different question would be
        indistinguishable from one answering yours.
        """
        return self._maya.call("POST", "/ask", json={"question": question,
                                                     "limit": limit})

    def translate(self, question: str) -> Dict[str, Any]:
        """The query a question becomes, without running it."""
        return self._maya.call("POST", "/ask/translate",
                               json={"question": question, "limit": 1})

    def returns(self) -> Dict[str, Any]:
        """Every supervisory return, and the fields the register cannot answer.

        Published before anybody runs one. The gaps are a property of the
        platform and are worth knowing in advance rather than finding in the
        output.
        """
        return self._maya.call("GET", "/regulatory-returns")

    def extract(self, name: str, *,
                now: Optional[float] = None) -> Dict[str, Any]:
        """Produce one return.

        **MAYA extracts and does not file.** A field the register cannot answer
        comes back empty and named in `not_held`, and the header says the
        extract is incomplete. That is deliberate: unlike every other output in
        this platform, this one gets sent to a supervisor, and a plausible value
        in a box nobody knew the answer to is a misstatement rather than a
        convenience.

        `excluded` lists the models the population left out and why. A
        regulator's first question about a population of eleven is what happened
        to the twelfth.
        """
        return self._maya.call("GET", f"/regulatory-returns/{name}",
                               params={"now": now})


class ValidationAssistance:
    """Three pieces of a validator's work. None of them is a conclusion.

    There is no method here that concludes a validation and no parameter that
    takes an outcome, because effective challenge is a judgement made by a
    person who can be held to it. The absence is the control.

    Each answer carries a `basis`, and it is worth reading: `exact` is
    arithmetic over the register, `derived` is inference from what the register
    holds, `retrieved` points at a document somebody must still read. A screen
    that mixed the three without saying so would get one level of trust applied
    to all of them, which is either too much or too little for two.
    """

    def __init__(self, maya):
        self._maya = maya

    def describe(self) -> Dict[str, Any]:
        """The three offerings, and the one thing none of them does."""
        return self._maya.call("GET", "/validation-assistance")

    def vendor_coverage(self, urn: str) -> Dict[str, Any]:
        """Which filed document speaks to which vendor checklist item.

        Retrieval, never summary. A paraphrase of a vendor document is a second
        document that says something the vendor did not, and the validator who
        relies on it cannot cite it when the vendor disagrees. What comes back
        is where to look.
        """
        return self._maya.call("GET", "/validation-assistance/vendor-coverage",
                               params={"urn": urn})

    def challenge_questions(self, urn: str, *, limit: int = 20) -> Dict[str, Any]:
        """Questions from findings raised against comparable models.

        Every one carries the finding it came from and the model it was raised
        against. A challenge question with no provenance is one a validator
        cannot defend when the owner pushes back, and "the tool suggested it" is
        not an answer.

        An empty result is not a clean bill: a model with no comparable peers is
        one whose failure modes nobody else has met yet.
        """
        return self._maya.call(
            "GET", "/validation-assistance/challenge-questions",
            params={"urn": urn, "limit": limit})

    def untested_assumptions(self, urn: str = "") -> Dict[str, Any]:
        """Assumptions with nothing watching them. Exact, and labelled exact.

        No model is involved: the assumption register already records whether a
        monitor watches each one, so this is a filter. Routing it through a
        language model would add a source of error to an answer that had none.
        """
        return self._maya.call(
            "GET", "/validation-assistance/untested-assumptions",
            params={"urn": urn})


class RegimeEncoding:
    """Proposes an encoding from regulatory prose, and stops short of one.

    **Nothing here activates a regime.** What comes back is a candidate: a
    signature, some sentences and a translation, already run through the same
    satisfaction condition (`L-8`) and deontic-conflict check (`L-16`) that
    activation uses. A person reads it, argues with it and writes it into the
    library themselves — a regime that entered force because a machine proposed
    it and a check passed would mean the institution's obligations were set by
    something with no standing to set them.

    And note what the check means when it passes: the draft is *self-consistent*.
    That is a far weaker claim than that it reads the regulation correctly, and
    nothing in this package can make the stronger one.
    """

    def __init__(self, maya):
        self._maya = maya

    def forms(self) -> Dict[str, Any]:
        """The forms, the modal cues and the core vocabulary.

        A proposal names a form — `requires`, `forbids`, `implies` — and the
        terms it applies to. MAYA builds the sentence from its own constructors,
        so no predicate ever crosses the boundary: a language model emitting
        code that decides what a regulation obliges is the point at which a
        governance platform starts making up the law.
        """
        return self._maya.call("GET", "/regime-encoding")

    def propose(self, name: str, *, text: str,
                citation: str = "") -> Dict[str, Any]:
        """Read obligations out of regulatory text.

        Read three things in the result before the sentences. `uncertain` on a
        sentence says the reading may be backwards — "must not X without Y" is a
        conditional obligation, and read as a prohibition it forbids the thing
        the regulation requires. `terms_dropped` says an obligation named more
        than the form carries. And `unread_sentences` is the most important line
        in a gap analysis: a passage carrying a duty about something the
        platform holds no term for.
        """
        return self._maya.call("POST", "/regime-encoding", json={
            "name": name, "text": text, "citation": citation})


class Probes:
    """Probe sets derived from a declared domain, and graded against it.

    A probe set written from rows that were lying around samples the **interior**
    of the input domain, and the interior is where two implementations agree.
    They come apart at the boundary: the value one clamps and the other rejects,
    the missing field one reads as zero, the category neither was fitted on.

    **MAYA proposes probes and does not run them.** Running a probe means running
    the model, and the register does not run models — a platform producing both
    the test and the result would be the only witness to its own model's
    behaviour.
    """

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """What each kind of probe is for."""
        return self._maya.call("GET", "/probe-sets")

    def propose(self, urn: str, *, semver: str) -> Dict[str, Any]:
        """The probe set this version's own declaration implies."""
        return self._maya.call("GET", "/probe-sets/propose",
                               params={"urn": urn, "semver": semver})

    def grade(self, urn: str, *, semver: str,
              probes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Which declared constraints your probe set exercises.

        Coverage is over the **declaration**, never over the probes. "We have
        four thousand probes" is not an answer to "does anything test the lower
        bound of this input", and the two get confused because only the first is
        easy to count.

        A thin set comes back as a `deficiency` in the probe set rather than as
        a result about the model — the two are indistinguishable in every
        equivalence report ever written.
        """
        return self._maya.call("POST", "/probe-sets/grade", json={
            "urn": urn, "semver": semver, "probes": probes})


class Remediation:
    """What is still owed, computed rather than proposed.

    *What do I still have to do* is answered everywhere else with a checklist,
    and a checklist is a conjunction. The real structure is a **disjunction of
    conjunctions** — there is usually more than one route to a model being in
    force, and the routes cost different amounts. That makes it a shortest-path
    problem, solved in the tropical semiring over a published derivation.

    Nothing asks a language model what to do next, and nothing could: the answer
    is arithmetic, and an arithmetic answer produced by a model is a worse
    version of the same number.

    **Nothing is executed.** Each step names the route a person calls — no
    capability in this platform holds a credential permitting a governance
    transition, and an assistant that could conclude a validation to close out
    its own plan would defeat the whole control structure in one method.
    """

    def __init__(self, maya):
        self._maya = maya

    def acts(self) -> Dict[str, Any]:
        """The acts, their costs and the derivation, before any plan."""
        return self._maya.call("GET", "/remediation")

    def plan(self, urn: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        """The cheapest route to this model being in force.

        Read `cheaper_but_hollow`. A validation is expensive and a waiver of the
        validation requirement is cheap; both make the compliance predicate
        true, and a shortest-path solver with no opinion about kind recommends
        the waiver every time — correctly, and disastrously. Those acts are
        excluded from the plan by *kind* and listed separately, so a firm can
        take one deliberately rather than find it by accident.

        Read `defaulted_share` too. A shortest path over guessed weights is a
        confident answer to a question nobody asked, and the confidence is the
        dangerous part.
        """
        return self._maya.call("GET", f"/models/{urn}/remediation",
                               params={"now": now})


class Migrations:
    """An artifact converted to another format, and the claim it is the same model.

    **MAYA does not convert it.** Converting means loading and running a model,
    and this platform does neither. What it does is hold the equivalence claim
    to a standard: you run both artifacts over a probe set and send the results,
    and the register judges them.

    Three things it refuses on, each a way a real equivalence report passes when
    it should not. A probe with **no result** fails rather than being skipped —
    a report over 40 of 50 probes looks exactly like a report over 50 at the
    bottom of the page. A **thin probe set** makes the claim `unsubstantiated`
    rather than `passed`, because two implementations agree in the interior by
    construction and this one never reached the boundary. And **tolerance has no
    default**: one chosen after the divergences are known is not a tolerance, it
    is a description of them, and it will be exactly wide enough.
    """

    def __init__(self, maya):
        self._maya = maya

    def outcomes(self) -> Dict[str, Any]:
        """The three outcomes, and what MAYA does not do."""
        return self._maya.call("GET", "/migrations")

    def verify(self, urn: str, *, semver: str, from_digest: str,
               to_digest: str, to_format: str, tolerance: float,
               probes: List[Dict[str, Any]], results: List[Dict[str, Any]],
               ran_by: str) -> Dict[str, Any]:
        """Judge an equivalence claim you measured.

        `results` pairs each probe by index with what each artifact answered:
        `{"probe": 0, "from": ..., "to": ...}`. Both refusing is *agreement*,
        and about the most informative kind — the boundary behaves the same way
        in both.
        """
        return self._maya.call("POST", "/migrations/verify", json={
            "urn": urn, "semver": semver, "from_digest": from_digest,
            "to_digest": to_digest, "to_format": to_format,
            "tolerance": tolerance, "probes": probes, "results": results,
            "ran_by": ran_by})


class SupervisoryMatters:
    """Matters a supervisor raised, and the two dates that are not one date.

    An MRA, an MRIA, a s166 finding: these look like findings and differ from
    them structurally, twice.

    **A matter is not about one model.** A thematic MRA about documentation
    reaches forty at once. Filing it against one makes thirty-nine invisible;
    filing it forty times makes it forty matters, and the firm then reports
    forty remediation programmes to a supervisor who raised one. So a matter
    carries a `scope` and the findings under it are derived from it.

    **And it carries `committed_at`** — the date the *firm gave the supervisor*,
    which is not the internal remediation date each finding derives from its
    severity. Both are held so `at_risk` can be computed: a matter whose last
    remediation lands inside two weeks of its committed date has no room for the
    firm's own closure verification, and that is arithmetic available months
    before the letter is due.
    """

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """What a supervisor may raise, and how hard each binds."""
        return self._maya.call("GET", "/supervisory-matters/kinds")

    def list(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Every matter, at-risk first.

        `no_committed_date` is worth reading: an absent commitment reads on
        every screen exactly like a distant one.
        """
        return self._maya.call("GET", "/supervisory-matters",
                               params={"now": now})

    def get(self, reference: str, *,
            now: Optional[float] = None) -> Dict[str, Any]:
        """One matter, with the findings under it."""
        return self._maya.call("GET", "/supervisory-matters",
                               params={"reference": reference, "now": now})

    def raise_matter(self, reference: str, *, kind: str, supervisor: str,
                     title: str, scope: List[str], owner: str,
                     description: str = "", examination: str = "",
                     severity: str = "High",
                     committed_at: Optional[float] = None) -> Dict[str, Any]:
        """Record a matter and raise one finding per model in scope.

        `reference` is the supervisor's own — it is how the firm and the
        supervisor talk about the same thing, and a matter tracked under an
        internal id only is one nobody can reconcile against the letter.
        """
        return self._maya.call("POST", "/supervisory-matters", json={
            "reference": reference, "kind": kind, "supervisor": supervisor,
            "title": title, "scope": scope, "owner": owner,
            "description": description, "examination": examination,
            "severity": severity, "committed_at": committed_at})

    def close(self, reference: str, *, note: str) -> Dict[str, Any]:
        """Close a matter. Refused while any finding under it is open.

        Telling a supervisor something is done when it is not is a failure of
        bookkeeping rather than of intent — somebody closes the programme in one
        system while two remediations run in another. This is the one system.
        """
        return self._maya.call("POST",
                               f"/supervisory-matters/{reference}/close",
                               json={"note": note})


class ValidationBacklog:
    """The validation queue, and what a backlog is a symptom of.

    **Workload is derived; capacity is declared.** MAYA counts what is open and
    computes what falls due. It does not guess how many validations a person can
    run in a quarter — a platform that did would produce a forecast nobody could
    dispute, which is worse than none because it survives the meeting.

    Read `assumes` before `shortfall`. Dividing work by capacity assumes every
    validation costs the same, which is false and everybody knows it, and a
    forecast that hides its assumption is one people act on.
    """

    def __init__(self, maya):
        self._maya = maya

    def workload(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """What each validator is carrying, against what they declared.

        `overloaded` is not a scheduling report. The commonest response to a
        validation backlog is to let a model's own team review it, and the
        second commonest is to conclude an episode without doing the work —
        both are independence failures that begin as capacity problems.
        """
        return self._maya.call("GET", "/validation-capacity",
                               params={"now": now})

    def declare(self, validator: str, *, episodes_per_quarter: float,
                note: str = "") -> Dict[str, Any]:
        """Record what one validator can take on."""
        return self._maya.call("POST", "/validation-capacity", json={
            "validator": validator,
            "episodes_per_quarter": episodes_per_quarter, "note": note})

    def forecast(self, *, horizon_days: float = 365.0,
                 now: Optional[float] = None) -> Dict[str, Any]:
        """What falls due against what the function said it could do."""
        return self._maya.call("GET", "/validation-backlog",
                               params={"horizon_days": horizon_days,
                                       "now": now})

    def queue(self, *, horizon_days: float = 365.0,
              now: Optional[float] = None) -> Dict[str, Any]:
        """Which models come due, highest risk first.

        `inverted` says whether a date-sorted list would put lower-risk work in
        front of higher-risk work. That is a statement about how the function is
        being run, and it is invisible in the list everybody actually keeps —
        which is sorted by date.
        """
        return self._maya.call("GET", "/validation-queue",
                               params={"horizon_days": horizon_days,
                                       "now": now})


class Campaigns:
    """Rounds of asking, over a population fixed at the moment of asking.

    **The population is derived at launch and then frozen**, and the derivation
    is kept beside it. That is the whole design, and the reason is a number
    nobody watches: a campaign whose population is a live query silently changes
    size, so a model retired in week three turns 47 of 50 into 47 of 49 and the
    completion figure **goes up without anybody having done anything**.

    So there are two numbers. `completion` is against the frozen population —
    the one that goes to a committee, and it can only move when somebody
    responds. `drift` is what re-deriving now would add, reported rather than
    folded in, because adding a model mid-round moves the denominator.

    Assignment is derived from the register, never typed: a campaign with typed
    assignees ends up assigned to people who left.
    """

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """What a round may be for, and how completion is measured."""
        return self._maya.call("GET", "/campaigns/kinds")

    def list(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Every round, least complete first."""
        return self._maya.call("GET", "/campaigns", params={"now": now})

    def get(self, reference: str, *,
            now: Optional[float] = None) -> Dict[str, Any]:
        """One round, with its items and its drift."""
        return self._maya.call("GET", "/campaigns",
                               params={"reference": reference, "now": now})

    def open(self, reference: str, *, kind: str, title: str,
             where: Optional[List[Dict[str, Any]]] = None,
             instruction: str = "",
             due_at: Optional[float] = None) -> Dict[str, Any]:
        """Fix a population from a semantic-layer filter and assign it.

        There is no parameter for a list of models. A typed population is one
        somebody assembled by hand, and nothing can re-derive it later to say
        what has changed since.
        """
        return self._maya.call("POST", "/campaigns", json={
            "reference": reference, "kind": kind, "title": title,
            "where": where or [], "instruction": instruction,
            "due_at": due_at})

    def respond(self, reference: str, *, urn: str, state: str,
                response: str = "") -> Dict[str, Any]:
        """Answer one item. `declined` and `not_applicable` need a reason."""
        return self._maya.call("POST", f"/campaigns/{reference}/respond",
                               json={"urn": urn, "state": state,
                                     "response": response})

    def reassign(self, reference: str, *, urn: str, to: str,
                 reason: str) -> Dict[str, Any]:
        """Move an item, on the record rather than by editing it.

        *Who was this originally for* is the question asked about the items that
        were not done, and an edit erases the answer.
        """
        return self._maya.call("POST", f"/campaigns/{reference}/reassign",
                               json={"urn": urn, "to": to, "reason": reason})

    def close(self, reference: str) -> Dict[str, Any]:
        """End a round, recording what was never answered.

        Closing over outstanding items is allowed — a round has to end — and the
        count goes on the chain, because a campaign that ends quietly and
        reports 100% is worse than one that reports 84% and stops.
        """
        return self._maya.call("POST", f"/campaigns/{reference}/close")


class Intake:
    """What arrives before a model, and the answer that matters most.

    A proposal is **not a model** and is not stored as one: no version, no
    artifact, nothing that could resolve. Keeping it in the register would be
    the fastest way to turn one into an inventory of ideas.

    Triage answers three prior questions — is it a model at all, build or buy,
    is it generative — and **the most valuable answer is "this is not a model"**.
    The pressure runs entirely the other way, because nobody is ever criticised
    for registering something. An out-of-scope determination is kept rather than
    deleted: a proposal declined and forgotten comes back next year as a fresh
    idea, and the second triage starts over without knowing the first happened.
    """

    def __init__(self, maya):
        self._maya = maya

    def questions(self) -> Dict[str, Any]:
        """The three questions, the cues each turns on, and the sourcing terms."""
        return self._maya.call("GET", "/intake/questions")

    def list(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Every proposal, untriaged first."""
        return self._maya.call("GET", "/intake", params={"now": now})

    def get(self, reference: str) -> Dict[str, Any]:
        return self._maya.call("GET", "/intake",
                               params={"reference": reference})

    def propose(self, reference: str, *, title: str, description: str,
                proposed_by: str, business_area: str = "") -> Dict[str, Any]:
        """Record a proposal."""
        return self._maya.call("POST", "/intake", json={
            "reference": reference, "title": title, "description": description,
            "proposed_by": proposed_by, "business_area": business_area})

    def assessment(self, reference: str) -> Dict[str, Any]:
        """What the description suggests, with the words it turned on.

        A reading, never a determination — and the words are shown so somebody
        can disagree with something specific. A determination whose reasoning is
        invisible is one nobody can disagree with, and the whole value of triage
        is in the disagreements.
        """
        return self._maya.call("GET", f"/intake/{reference}/assessment")

    def triage(self, reference: str, *, in_scope: bool, sourcing: str,
               generative: bool, rationale: str) -> Dict[str, Any]:
        """Record the determination a person made, beside the reading.

        `rationale` is required. An out-of-scope decision with no reason is one
        that gets re-litigated every year by somebody who was not there.
        """
        return self._maya.call("POST", f"/intake/{reference}/triage", json={
            "in_scope": in_scope, "sourcing": sourcing,
            "generative": generative, "rationale": rationale})

    def register(self, reference: str, *, urn: str, name: str,
                 model_class: str, domain: str, owner: str,
                 legal_entity: str, purpose: str) -> Dict[str, Any]:
        """Cross from proposal to model. Refused before triage.

        The triage travels with the model as its first evidence: the
        build-versus-buy decision is the one that decides what the firm owes,
        and it is otherwise made in a meeting nobody minuted.
        """
        return self._maya.call("POST", f"/intake/{reference}/register", json={
            "urn": urn, "name": name, "model_class": model_class,
            "domain": domain, "owner": owner, "legal_entity": legal_entity,
            "purpose": purpose})


class OverlayDisclosure:
    """The part of the number that is not the model, for the accounts.

    IFRS 9 requires disclosure of the significant judgements applied in
    measuring expected credit losses, and the figure is almost always assembled
    in a spreadsheet at period end from a list somebody keeps.

    Three things about this extract are decisions rather than arithmetic.

    **An unmeasured overlay cannot be disclosed and is named.** It is active, it
    is changing the number, and nobody recorded by how much. Leaving it out
    understates the judgement component; putting it in at zero is worse, because
    zero is a measurement. It appears as a hole, and `complete` is False.

    **New and grown are reported separately.** One is a judgement somebody newly
    formed, the other is a judgement that got bigger, and the second is the one
    an auditor asks about — a single "change in overlays" figure collapses them.

    **An overlay renewed past its limit is reported as structural.** An
    adjustment continued five times is not a temporary judgement about an
    unusual period; it is a permanent correction to a model nobody has fixed.

    MAYA produces an extract, not a disclosure note: the figures are the
    register's, and the words, the materiality judgement and the decision to
    file are the firm's.
    """

    def __init__(self, maya):
        self._maya = maya

    def extract(self, period: str, *, prior: str = "",
                now: Optional[float] = None) -> Dict[str, Any]:
        """The judgement component for one reporting period."""
        return self._maya.call("GET", "/overlay-disclosure",
                               params={"period": period, "prior": prior,
                                       "now": now})

    def trend(self, periods: List[str]) -> Dict[str, Any]:
        """The judgement component across periods, oldest first.

        `monotonically_rising` is the shape a model that needs fixing makes:
        each quarter's adjustment is defensible on its own, and the series is
        the finding.
        """
        return self._maya.call("GET", "/overlay-disclosure/trend",
                               params={"periods": ",".join(periods)})


class Configuration:
    """The platform configuring itself, and the line that does not move.

    "Configuration as code" done naively to a governance platform is the single
    most effective way to defeat one: the gates and the git repository end up
    with **the same approval process**, and that process is a pull request
    reviewed by whoever is on shift.

    So `boundary()` publishes what a firm may configure and what it may not, and
    why. Policies, warrant profiles, monitoring defaults, appetite limits and
    remediation costs are a bank's own judgement. The lifecycle state graph, the
    tier lattice, the trainability fibration and the refusal taxonomy are not
    settings that happen to be hardcoded — they are the argument, and the
    argument is what the platform is.

    Applying is a **governance act**, not a deployment step. `plan()` renders
    exactly what would change and which way each change points, and a plan that
    **loosens** needs a named approver: a configuration that tightens can be a
    deployment, one that loosens is a decision, and the whole risk of
    configuration-as-code is that the two travel in the same pull request.
    """

    def __init__(self, maya):
        self._maya = maya

    def boundary(self) -> Dict[str, Any]:
        """What is configuration, what is code, and why."""
        return self._maya.call("GET", "/configuration/boundary")

    def export(self, *, sections: Optional[List[str]] = None) -> Dict[str, Any]:
        """What is in force, read from the registers rather than from a file.

        That difference matters: a file describes somebody's intentions, and the
        registers describe the platform.
        """
        params = {"sections": ",".join(sections)} if sections else {}
        return self._maya.call("GET", "/configuration", params=params)

    def plan(self, configuration: Dict[str, Any], *,
             format: str = "maya.configuration/v1") -> Dict[str, Any]:
        """Exactly what would change. Read `loosens` first.

        *Three rules changed* is not a reviewable sentence; *two of these three
        let something through that is refused today* is — and the direction is
        computed from the shape of each change rather than asserted by whoever
        wrote it. Where the shape gives no reading it is `neutral` and is not
        guessed, because a wrong direction on a review screen is worse than
        none: somebody stops reading the diff.
        """
        return self._maya.call("POST", "/configuration/plan", json={
            "format": format, "configuration": configuration})

    def apply(self, configuration: Dict[str, Any], *, rationale: str,
              approved_by: str = "",
              format: str = "maya.configuration/v1") -> Dict[str, Any]:
        """Record that a configuration was applied, with its diff.

        Each section is applied through its own register, which keeps its own
        approval — a path here that wrote policies directly would be a second
        way to publish a gate, and the second way is always the one without the
        signature.
        """
        return self._maya.call("POST", "/configuration/apply", json={
            "format": format, "configuration": configuration,
            "rationale": rationale, "approved_by": approved_by})


class DocumentReview:
    """Comments on a compiled document, and the one thing a reviewer cannot do.

    **A compiled document cannot be edited.** Every sentence is assembled from
    the evidence chain and cites a node; editing the prose would break the
    citation without changing the record it cites, producing a document that
    reads correctly and is no longer traceable to anything. That is worse than a
    wrong sentence, because a wrong sentence can be found.

    So the fix for a wrong sentence is **a fix to the record it was compiled
    from**, and a recompilation. What a reviewer does here is say which section
    is wrong and what about it, with `asks_for` from a closed list — *please
    look at this* and *this is factually wrong* are different obligations, and a
    free-text field makes them the same one.

    Comments attach to a **digest**, not a document id: a comment carried onto a
    recompilation is a remark about text that may no longer be there, and worse,
    one that looks answered.
    """

    def __init__(self, maya):
        self._maya = maya

    def asks(self) -> Dict[str, Any]:
        """What a comment may ask for, and why a document is not editable."""
        return self._maya.call("GET", "/document-review/asks")

    def list(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Every document under review, most contested first.

        An empty answer is worth reading as a fact about how documents are
        reviewed here rather than about their quality: a review that happens in
        email leaves the register exactly this empty.
        """
        return self._maya.call("GET", "/document-review", params={"now": now})

    def read(self, document_id: str, *,
             now: Optional[float] = None) -> Dict[str, Any]:
        """One document's review state, against the version it was raised on."""
        return self._maya.call("GET", "/document-review",
                               params={"document_id": document_id,
                                       "now": now})

    def comment(self, document_id: str, *, section: str, body: str,
                asks_for: str = "comment", quote: str = "") -> Dict[str, Any]:
        """Say which section is wrong and what about it."""
        return self._maya.call("POST", "/document-review",
                               params={"document_id": document_id},
                               json={"section": section, "body": body,
                                     "asks_for": asks_for, "quote": quote})

    def resolve(self, comment_id: str, *, resolution: str,
                evidence_id: str = "") -> Dict[str, Any]:
        """Close a comment, saying what was done — and which node if any.

        A comment closed with "fixed" and nothing else is indistinguishable a
        year later from one closed because the reviewer gave up, and the
        difference is the entire value of a review history. A `factual` comment
        or an `objection` may not be closed by the person who raised it.
        """
        return self._maya.call("POST",
                               f"/document-review/{comment_id}/resolve",
                               json={"resolution": resolution,
                                     "evidence_id": evidence_id})

    def withdraw(self, comment_id: str, *, reason: str = "") -> Dict[str, Any]:
        """Take your own comment back. Recorded as what it is, never deleted."""
        return self._maya.call("POST",
                               f"/document-review/{comment_id}/withdraw",
                               params={"reason": reason})


class RequestTimeInputs:
    """The inputs the caller brings, and the guarantees that do not reach them.

    Most of a model's inputs come from the feature platform: materialised,
    versioned, bitemporal, replayable. Some arrive **in the request** — a loan
    amount typed into a form, a transaction being scored as it happens. That is
    fine, and it is also a hole in every assurance this platform otherwise
    gives.

    Point-in-time does not apply: the value was never stored as at anything.
    There is no ingest time, so the two clocks that separate a future value from
    a late arrival do not exist. A replay cannot reproduce it. And **the skew
    check is blind to it** — there is no offline value to compare against, so the
    check finds nothing, which reads on a screen exactly like finding no skew.
    That is why the gap is counted rather than left to be inferred.

    The collision is the real bug: a name that is both a request-time input and
    a catalogued feature means the model was fitted on the stored value and is
    served the caller's. It is refused at declaration, because by the time it
    shows up in production it looks like model degradation.
    """

    def __init__(self, maya):
        self._maya = maya

    def guarantees(self) -> Dict[str, Any]:
        """What the platform promises about a stored value, and not a sent one."""
        return self._maya.call("GET", "/request-time/guarantees")

    def posture(self, urn: str, *, semver: str) -> Dict[str, Any]:
        """What arrives in the request, and what cannot be promised about it.

        Read `unbounded`. An input with no declared bound gives the operating
        contract's boundary check nothing to refuse against, so a caller may
        send anything.
        """
        return self._maya.call("GET", "/request-time",
                               params={"urn": urn, "semver": semver})

    def across_the_estate(self, *,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """Every version that reads a value the caller brings."""
        return self._maya.call("GET", "/request-time", params={"now": now})

    def check(self, urn: str, *, semver: str,
              payload: Dict[str, Any]) -> Dict[str, Any]:
        """Judge one request's caller-supplied values against the contract.

        Every violation is reported rather than the first: a caller told about
        one bad field fixes it, retries, and is told about the next.
        """
        return self._maya.call("POST", "/request-time/check", json={
            "urn": urn, "semver": semver, "payload": payload})


class Concentration:
    """What several models depend on at once, and why there is no score.

    Supervisors ask about "reliance on common assumptions, data, or
    methodologies". The register already found shared *upstream models*; the
    rest of that sentence — the data, the vendor, the methodology — was not
    computed, and those are the ones a firm is least likely to know.

    **`aggregate_score` is always None, and that is a result rather than a
    gap.** A network that *copies* a dependency and one that *duplicates* it
    produce identical component ratings, so any figure computed from those
    ratings is blind to exactly the thing this exists to find. What composes is
    the **order** — the worst tier at stake — and not a magnitude.

    **A concentration is not a count.** Twelve models on one feature view is a
    number; twelve *tier 1* models on it is a finding. Every shared thing
    carries the worst tier riding on it, and the sort is by what is at stake.

    The two kinds nobody usually has are `vendor` — because the vendor's name is
    on an *assessment* and not on the model, so nothing joins four models from
    one bureau — and `dataset`, because a pinned snapshot is invisible in
    ordinary operation and two parameter sets fitted from one share whatever was
    wrong with it, silently.
    """

    def __init__(self, maya):
        self._maya = maya

    def across_the_estate(self, *,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """Every shared dependency, worst tier at stake first."""
        return self._maya.call("GET", "/concentration", params={"now": now})

    def of_model(self, urn: str, *,
                 now: Optional[float] = None) -> Dict[str, Any]:
        """What this model shares with anything else, and with what.

        The reverse of a blast radius: that reads outward from a change, this
        reads inward to what a change elsewhere would reach.
        """
        return self._maya.call("GET", "/concentration",
                               params={"urn": urn, "now": now})

    def single_points(self, *,
                      now: Optional[float] = None) -> Dict[str, Any]:
        """What the estate would lose if one thing stopped working.

        Read `resilience_is_known`, which is False. These are named as
        **dependencies** and not asserted as failure points: whether a thing can
        fail is a fact about a pipeline, a cluster and an on-call rota, and MAYA
        holds none of the three. Half of the judgement is here, and the answer
        says which half.
        """
        return self._maya.call("GET", "/concentration/single-points",
                               params={"now": now})


class FeatureImpact:
    """Who is downstream of a feature, walked forward to the declared use.

    **A count of models is not an impact assessment.** *Eleven models* tells a
    feature owner nothing they can take to anybody. The chain that matters runs
    further:

        feature → view → featureset version → parameter set → model version
                → grant → **declared use**

    *This feature feeds the origination decision for retail mortgages, under
    three live grants held by two services, one of which is tier 1* names who has
    to be told, what will stop working, and how urgent it is.

    Live and historical grants are reported apart, because a version referring
    to a feature is a migration and a live grant is an outage.

    Read `reaches_decisions`, which is False. The walk reaches the **authority**
    to decide and stops there — whether the model was called is invocation
    telemetry, and whether an answer reached a customer is outside the register.
    A count of affected decisions would be a number MAYA does not have.
    """

    def __init__(self, maya):
        self._maya = maya

    def of_feature(self, name: str, *,
                   now: Optional[float] = None) -> Dict[str, Any]:
        """Everything downstream of one feature."""
        return self._maya.call("GET", "/feature-impact",
                               params={"feature": name, "now": now})

    def of_view(self, view: str, *,
                now: Optional[float] = None) -> Dict[str, Any]:
        """Everything downstream of one materialised view."""
        return self._maya.call("GET", "/feature-impact",
                               params={"view": view, "now": now})

    def across_the_estate(self, *,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """Every feature with a model bound to it, most exposed first."""
        return self._maya.call("GET", "/feature-impact", params={"now": now})

    def of_restatement(self, view: str, *, version: int,
                       now: Optional[float] = None) -> Dict[str, Any]:
        """What a restatement of this view version reaches.

        The detection half already existed — `restated()` compares the pin
        against current. This is the walk forward that did not: a correction to
        a stale row is a legitimate act, and a correction nobody traced is one
        that quietly invalidates every parameter set fitted from it and every
        authority resting on those.

        Worth calling **before** the correction rather than after, which is why
        it answers for a view that has not moved yet.
        """
        return self._maya.call("GET", "/feature-impact/restatement",
                               params={"view": view, "version": version,
                                       "now": now})
