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
