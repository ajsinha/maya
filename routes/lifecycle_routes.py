"""
MAYA — the model record lifecycle: submission, approval, attestation, amendment.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

An attested record is immutable. Everything here is either a step towards that
state or the declared act of leaving it.

Deletion is the one endpoint with no workflow, and it is administrators only.
Everyone else retires a model, which withdraws it from use and keeps the record.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Request
from pydantic import Field

from core.execution.urn import urn_of
from core.lifecycle import describe
from core.lifecycle.conditions import ApprovalConditions
from core.lifecycle.authority import AuthorityMatrix
from routes.base import Body, Routes



class AuthorityBandIn(Body):
    """One row of the delegated authority matrix.

    `stages` is a list of lists: roles that sign together, stages that sign in
    order. A flat role list cannot say *the second line signs after the first*,
    and that ordering is the half of `FR-LC-005` a quorum does not cover.
    """
    name: str
    stages: List[List[str]]
    tier: Optional[int] = None
    at_or_above: float = 0.0
    legal_entity: Optional[str] = None
    note: str = ""


class DelegationIn(Body):
    """What one named person may approve, and under which instrument.

    `instrument` is required. MAYA holds the reference rather than the
    resolution, and a delegation nobody can trace to a decision is the precise
    thing an authority matrix exists to prevent.
    """
    principal: str
    ceiling: float
    instrument: str
    currency: str = "USD"
    legal_entity: Optional[str] = None

class DecommissionIn(Body):
    """Taking a model out of service, with the four facts a firm needs later.

    `replacement` is a registered URN or the literal `none`. Blank is refused
    because blank is indistinguishable from nobody having filled it in.
    """
    rationale: str
    replacement: str
    retention_class: str
    notified: List[str] = Field(default_factory=list)
    acknowledged: bool = False


class CampaignIn(Body):
    """A round of asking.

    `where` is a semantic-layer filter, and the population it selects is frozen
    at launch. There is no field for a list of models: a typed population is one
    somebody assembled by hand, and nothing can re-derive it later to say what
    has changed.
    """
    reference: str
    kind: str
    title: str
    where: List[Dict[str, Any]] = Field(default_factory=list)
    instruction: str = ""
    due_at: Optional[float] = None


class CampaignResponseIn(Body):
    urn: str
    state: str
    response: str = ""


class ReassignIn(Body):
    urn: str
    to: str
    reason: str


class ProposalIn(Body):
    reference: str
    title: str
    description: str
    proposed_by: str
    business_area: str = ""


class TriageIn2(Body):
    """A determination a person made. `rationale` is not optional.

    An out-of-scope decision with no reason is one that gets re-litigated every
    year by somebody who was not there.
    """
    in_scope: bool
    sourcing: str
    generative: bool
    rationale: str


class RegisterProposalIn(Body):
    urn: str
    name: str
    model_class: str
    domain: str
    owner: str
    legal_entity: str
    purpose: str


class ParallelIn(Body):
    urn: str
    champion: str
    challenger: str
    purpose: str
    tolerance: float = 1e-9


class ObservationIn(Body):
    input_key: str
    champion: Optional[float] = None
    challenger: Optional[float] = None


class OutcomeIn(Body):
    input_key: str
    outcome: float


class ConcludeRunIn(Body):
    conclusion: str
    note: str


class ConditionIn(Body):
    urn: str
    kind: str
    rationale: str
    days: float
    parameters: Dict[str, Any] = Field(default_factory=dict)
    semver: str = ""
    confirm_every_days: float = 30.0


class ConfirmIn(Body):
    note: str = ""


class NoteIn(Body):
    note: str = ""


class ReasonIn(Body):
    reason: str


class AmendIn(Body):
    reason: str
    scope: List[str] = Field(default_factory=list)


class SignIn(Body):
    role: str
    decision: str = "attest"
    statement: str = ""


class UpdateIn(Body):
    fields: Dict[str, Any] = Field(default_factory=dict)


class LifecycleRoutes(Routes):
    def register(self) -> None:
        registry, lifecycle = self.ctx["registry"], self.ctx["lifecycle"]
        api = self.api

        def model_of(name: str) -> Dict[str, Any]:
            return self.guard(lambda: registry.require(urn_of(name)))

        @self.app.get(f"{api}/lifecycle", tags=["lifecycle"])
        def machine(request: Request):
            """The state machine itself: who may move what, from where, to where."""
            self.principal(request)
            return {"transitions": describe()}

        @self.app.get(f"{api}/parallel-runs", tags=["lifecycle"])
        def parallel_runs(request: Request, reference: str = ""):
            """Open parallel runs, or one run's two readings.

            **Divergence and outcomes are never mixed.** How often the two
            models disagree is knowable the moment both have answered and says
            nothing about which is right; which was right needs the outcome, and
            the outcome arrives months later or never. Nearly every shadow-mode
            dashboard reports the first and lets a reader conclude the second.
            """
            self.authorise(request, "model:read")
            runs = self.ctx["parallel_runs"]
            if not reference:
                return self.guard(lambda: runs.across_the_estate())
            return self.guard(lambda: runs.report(reference))

        @self.app.post(f"{api}/parallel-runs", status_code=201,
                       tags=["lifecycle"])
        def open_parallel_run(request: Request, body: ParallelIn):
            """Declare that a challenger is running beside the champion.

            MAYA runs neither. It records that the run is happening and takes
            delivery of what both produced.
            """
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "model:approve", model=model)
            return self.guard(lambda: self.ctx["parallel_runs"].open(
                body.urn, champion=body.champion, challenger=body.challenger,
                purpose=body.purpose, tolerance=body.tolerance,
                actor=self.actor(who)))

        @self.app.post(f"{api}/parallel-runs/{{reference}}/observations",
                       status_code=201, tags=["lifecycle"])
        def observe(request: Request, reference: str, body: ObservationIn):
            """What one or both models answered for one input.

            Either side may arrive first and separately, because in a real
            shadow deployment they do. An observation with only one side is
            kept and reported as unpaired rather than dropped — a challenger
            that silently failed on the hard cases would otherwise look like the
            better model.
            """
            runs = self.ctx["parallel_runs"]
            run = self.guard(lambda: runs.require(reference))
            model = self.ctx["registry"].by_id(run["model_id"])
            # `monitor:observe`, the same permission the telemetry ingestion
            # path takes: an observation is what a running model produced, and
            # a shadow deployment posts them from a service rather than a
            # person.
            self.authorise(request, "monitor:observe", model=model)
            return self.guard(lambda: runs.observe(
                reference, input_key=body.input_key, champion=body.champion,
                challenger=body.challenger))

        @self.app.post(f"{api}/parallel-runs/{{reference}}/outcomes",
                       tags=["lifecycle"])
        def record_outcome(request: Request, reference: str,
                           body: OutcomeIn):
            """The label, when it arrives — which is the part that takes months."""
            runs = self.ctx["parallel_runs"]
            run = self.guard(lambda: runs.require(reference))
            model = self.ctx["registry"].by_id(run["model_id"])
            self.authorise(request, "monitor:observe", model=model)
            return self.guard(
                lambda: runs.record_outcome(reference, body.input_key,
                                            body.outcome))

        @self.app.post(f"{api}/parallel-runs/{{reference}}/conclude",
                       tags=["lifecycle"])
        def conclude_parallel_run(request: Request, reference: str,
                                  body: ConcludeRunIn):
            """End the run with a verdict.

            Promoting on divergence alone is refused. Divergence says the two
            models differ; it does not say the challenger is better, and the
            pressure at the end of an expensive run is to conclude something
            rather than nothing. `inconclusive` is an honest end and a common
            one.
            """
            runs = self.ctx["parallel_runs"]
            run = self.guard(lambda: runs.require(reference))
            model = self.ctx["registry"].by_id(run["model_id"])
            who = self.authorise(request, "model:approve", model=model)
            return self.guard(lambda: runs.conclude(
                reference, body.conclusion, body.note, actor=self.actor(who)))

        @self.app.get(f"{api}/condition-kinds", tags=["lifecycle"])
        def condition_kinds(request: Request):
            """The conditions an approval may carry, and which are enforced.

            The column that matters is `enforcement`. **Enforced** means
            something here refuses when it is broken. **Attested** means MAYA
            cannot see the thing the condition is about, so the control is that
            a named person periodically confirms it — a real control, and not
            the same one. A firm that believes its exposure cap is
            machine-enforced is worse off than one that knows it is a diary
            entry, because the first has stopped checking.
            """
            self.principal(request)
            return ApprovalConditions.vocabulary()

        @self.app.get(f"{api}/approval-conditions", tags=["lifecycle"])
        def approval_conditions(request: Request, urn: str = ""):
            """A model's conditions and whether they hold, or the estate's."""
            conditions = self.ctx["approval_conditions"]
            if not urn:
                self.authorise(request, "model:read")
                return self.guard(lambda: conditions.across_the_estate())
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: conditions.for_model(urn))

        @self.app.post(f"{api}/approval-conditions", status_code=201,
                       tags=["lifecycle"])
        def impose_condition(request: Request, body: ConditionIn):
            """Approve on terms. SR 26-2 V permits use before validation with
            compensating controls; this is what makes them enforced rather than
            promised.

            The window is mandatory and bounded. A conditional approval with no
            end date is an unconditional approval that has not noticed yet.
            """
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "model:approve", model=model)
            return self.guard(lambda: self.ctx["approval_conditions"].impose(
                body.urn, body.kind, rationale=body.rationale, days=body.days,
                parameters=body.parameters, semver=body.semver or None,
                confirm_every_days=body.confirm_every_days,
                actor=self.actor(who)))

        @self.app.post(f"{api}/approval-conditions/{{reference}}/confirm",
                       tags=["lifecycle"])
        def confirm_condition(request: Request, reference: str,
                              body: ConfirmIn):
            """State that an attested condition still holds.

            Only the attested ones need this. Confirming something the platform
            already checks would record an opinion about a fact.
            """
            conditions = self.ctx["approval_conditions"]
            row = self.guard(lambda: conditions.require(reference))
            model = self.ctx["registry"].by_id(row["model_id"])
            who = self.authorise(request, "model:approve", model=model)
            return self.guard(lambda: conditions.confirm(
                reference, self.actor(who), body.note))

        @self.app.post(f"{api}/approval-conditions/{{reference}}/discharge",
                       tags=["lifecycle"])
        def discharge_condition(request: Request, reference: str,
                                body: ReasonIn):
            """Lift a condition, because what it stood in for has been done."""
            conditions = self.ctx["approval_conditions"]
            row = self.guard(lambda: conditions.require(reference))
            model = self.ctx["registry"].by_id(row["model_id"])
            who = self.authorise(request, "model:approve", model=model)
            return self.guard(lambda: conditions.discharge(
                reference, body.reason, actor=self.actor(who)))

        @self.app.get(f"{api}/lifecycle-profiles", tags=["lifecycle"])
        def profiles(request: Request):
            """The reference lifecycle for every trainability class.

            One state graph and several sets of obligations. Nine graphs would
            mean nine reachability proofs, nine answers to *can this be
            changed*, and a supervisor who has to ask which machine a model is
            on before reading its status. What varies is what each move costs.
            """
            self.principal(request)
            return self.guard(lambda: self.ctx["lifecycle_profiles"].reference())

        @self.app.get(f"{api}/lifecycle-profiles/{{trainability}}",
                      tags=["lifecycle"])
        def profile(request: Request, trainability: str,
                    tier: Optional[int] = None):
            """What a model of this class owes on each move, at this tier.

            The class says which evidence kinds must be on file — `L-15`
            already makes each one declare that — and the tier says how many
            signatures a move takes and how long it may sit.
            """
            self.principal(request)
            return self.guard(
                lambda: self.ctx["lifecycle_profiles"].for_class(
                    trainability, tier))

        # A top-level path with a `urn` query rather than a suffix under
        # `/models/{name}`: the model route's path converter is greedy and
        # swallows any suffix hung off it, which is why every derived read in
        # this platform — validation plans, monitoring plans, uses — takes the
        # urn as a parameter instead.
        @self.app.get(f"{api}/lifecycle-readiness", tags=["lifecycle"])
        def readiness(request: Request, urn: str, transition: str = "attest"):
            """Whether this model can make this move, and what is missing.

            *On file but unreviewed* is reported apart from *missing*: the
            document exists and the obligation is not yet discharged, and
            collapsing the two sends somebody off to write a report that is
            already written and sitting in a queue.
            """
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(
                lambda: self.ctx["lifecycle_profiles"].check(urn, transition))

        @self.app.get(f"{api}/lifecycle-stalled", tags=["lifecycle"])
        def stalled(request: Request):
            """Records that have been mid-move longer than their tier allows.

            Nothing else here can see this. Submission succeeded, every gate
            passed, and no control is watching the clock — which is how a
            governance queue becomes a place things go to wait. Not a refusal:
            a queue is allowed to have a queue, but one with no expected
            duration is one nobody can tell is stuck.
            """
            self.principal(request)
            return self.guard(lambda: self.ctx["lifecycle_profiles"].stalled())

        @self.app.patch(f"{api}/models/{{name:path}}", tags=["lifecycle"])
        def update(request: Request, name: str, body: UpdateIn):
            """Revise an open record. Refused once it is attested."""
            model = model_of(name)
            who = self.authorise(request, "model:register", model=model)
            return self.guard(lambda: registry.update(model["urn"], body.fields,
                                                      self.actor(who)))

        @self.app.post(f"{api}/models/{{name:path}}/submit", tags=["lifecycle"])
        def submit(request: Request, name: str, body: NoteIn):
            model = model_of(name)
            who = self.authorise(request, "model:submit", model=model)
            return self.guard(lambda: lifecycle.submit(model, self.actor(who), body.note))

        @self.app.post(f"{api}/models/{{name:path}}/approve", tags=["lifecycle"])
        def approve(request: Request, name: str, body: NoteIn):
            """Approve the record and open the attestation it now needs."""
            model = model_of(name)
            who = self.authorise(request, "model:approve", model=model,
                                 subject_id=model["id"])
            return self.guard(lambda: lifecycle.approve(model, self.actor(who), body.note))

        @self.app.post(f"{api}/models/{{name:path}}/return", tags=["lifecycle"])
        def send_back(request: Request, name: str, body: ReasonIn):
            model = model_of(name)
            who = self.authorise(request, "model:approve", model=model)
            return self.guard(lambda: lifecycle.send_back(model, self.actor(who),
                                                          body.reason))

        @self.app.post(f"{api}/models/{{name:path}}/attest", tags=["lifecycle"])
        def attest(request: Request, name: str, body: SignIn):
            """Sign one role's half of the attestation. A quorum, not a button."""
            model = model_of(name)
            who = self.authorise(request, "model:attest", model=model)
            return self.guard(lambda: lifecycle.sign(model, who, body.role,
                                                     body.decision, body.statement))

        @self.app.post(f"{api}/models/{{name:path}}/amend", tags=["lifecycle"])
        def amend(request: Request, name: str, body: AmendIn):
            """The only route out of immutability."""
            model = model_of(name)
            who = self.authorise(request, "model:amend", model=model)
            return self.guard(lambda: lifecycle.amend(model, body.reason, body.scope,
                                                      self.actor(who)))

        @self.app.post(f"{api}/models/{{name:path}}/retire", tags=["lifecycle"])
        def retire(request: Request, name: str, body: ReasonIn):
            """Withdraw a model from use, keeping the record.

            This is the transition and nothing else. `POST /decommission`
            records what a retirement *is* — what replaced it, who was told,
            how long it is kept — and refuses the silent versions. Both exist
            because a model retired before that endpoint did has a reason and
            none of the other three facts, and pretending otherwise would make
            a backlog invisible.
            """
            model = model_of(name)
            who = self.authorise(request, "model:retire", model=model)
            return self.guard(lambda: lifecycle.retire(model, self.actor(who), body.reason))

        @self.app.get(f"{api}/decommission", tags=["lifecycle"])
        def decommission_posture(request: Request, urn: Optional[str] = None):
            """What a decommissioning captures — or one model's record.

            Two things it does **not** do. It **notifies nobody**: `notified`
            records who was *told*, as an attestation, because the people who
            depend on a model are reachable through channels MAYA does not own
            and claiming to have notified them would be claiming a delivery it
            never made. And it **archives nothing and deletes nothing**: a
            retention class states the obligation, and retiring a model does
            not move a byte.
            """
            self.principal(request)
            engine = self.ctx["decommissioning"]
            if urn is None:
                from core.lifecycle.decommission import Decommissioning
                return Decommissioning.posture()
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: engine.of(model["urn"]))

        @self.app.get(f"{api}/decommission/consumers", tags=["lifecycle"])
        def decommission_consumers(request: Request, urn: str):
            """Who reads this model, before anybody retires it.

            Computed from the typed `input_to` edges the register already
            holds, so it is the register's answer rather than somebody's
            recollection.
            """
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(
                lambda: self.ctx["decommissioning"].consumers(model["urn"]))

        @self.app.get(f"{api}/decommission/estate", tags=["lifecycle"])
        def decommission_estate(request: Request):
            """Retired models, and how many were decommissioned properly.

            *Retired* and *decommissioned* are two different populations, and
            the gap between them is a backlog somebody can work.
            """
            self.authorise(request, "model:read",
                           estate_wide="reading decommissioning records")
            return self.guard(
                lambda: self.ctx["decommissioning"].across_the_estate())

        @self.app.post(f"{api}/decommission", status_code=201,
                       tags=["lifecycle"])
        def decommission(request: Request, urn: str, body: DecommissionIn):
            """Record the decommissioning, then retire.

            Everything is validated **before** the transition, so a refusal
            leaves the model in service rather than half-retired with no
            record of why.

            Three refusals. A replacement that is not registered is a sentence
            rather than a link. A retention class MAYA does not have would be
            a schedule nobody can act on. And a retirement with **unnotified
            live consumers** is refused — escapably, because `acknowledged`
            records that somebody looked at the list and decided, which is a
            different fact from nobody having looked.
            """
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            who = self.authorise(request, "model:retire", model=model)
            return self.guard(lambda: self.ctx["decommissioning"].decommission(
                model["urn"], rationale=body.rationale,
                replacement=body.replacement,
                retention_class=body.retention_class,
                notified=body.notified, acknowledged=body.acknowledged,
                actor=self.actor(who)))

        # ------------------------------------------ the authority matrix
        @self.app.get(f"{api}/authority", tags=["lifecycle"])
        def authority_posture(request: Request):
            """What the matrix decides, and the one thing it cannot check.

            The dimension worth reading is **amount**. It comes from the
            sourced exposure fact (`H-8`) and nowhere else, because the figure
            the tiering assessment was made from is a number typed into a form
            — using it would let the amount that decides the approval depth be
            chosen by whoever wants the approval.

            And where no amount is sourced the band is the **deepest the tier
            admits**, not the shallowest. An amount MAYA does not have is not
            a small amount, but it compares as less than every floor, so the
            natural implementation of this quietly approves everything.
            """
            self.principal(request)
            return {**AuthorityMatrix.posture(),
                    "matrix": self.ctx["authority"].matrix()}

        @self.app.get(f"{api}/authority/model", tags=["lifecycle"])
        def authority_for_model(request: Request, urn: str):
            """Which signatures this model's version approval needs, and why."""
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(
                lambda: self.ctx["authority"].required_for(model["urn"]))

        @self.app.get(f"{api}/authority/sequence", tags=["lifecycle"])
        def authority_sequence(request: Request, urn: str):
            """What this model's NEXT approval would be sequenced as.

            A read, never the check. An approval already open carries its own
            stages and is held to those — withdrawing or re-publishing a band
            cannot move the bar under people who are already signing.
            """
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(
                lambda: self.ctx["authority"].sequence_for(model["urn"]))

        @self.app.get(f"{api}/authority/estate", tags=["lifecycle"])
        def authority_estate(request: Request):
            """How much of the estate rests on authority nobody re-attested."""
            self.authorise(request, "model:read",
                           estate_wide="reading the authority matrix")
            return self.guard(
                lambda: self.ctx["authority"].across_the_estate())

        @self.app.post(f"{api}/authority/bands", status_code=201,
                       tags=["lifecycle"])
        def publish_band(request: Request, body: AuthorityBandIn):
            """Add a band to the matrix.

            Until the first one is published the tier quorum stands exactly as
            it always has — a feature that deepens every approval in the estate
            the moment it is deployed is one switched off before anybody reads
            what it does.
            """
            who = self.authorise(request, "policy:publish",
                                 estate_wide="publishing an authority band")
            return self.guard(lambda: self.ctx["authority"].publish(
                body.model_dump(), actor=self.actor(who)))

        @self.app.delete(f"{api}/authority/bands/{{name}}", tags=["lifecycle"])
        def withdraw_band(request: Request, name: str):
            """Withdraw a band. Approvals already open keep the band they were
            opened under."""
            who = self.authorise(request, "policy:publish",
                                 estate_wide="withdrawing an authority band")
            return self.guard(lambda: self.ctx["authority"].withdraw(
                name, actor=self.actor(who)))

        @self.app.get(f"{api}/authority/delegations", tags=["lifecycle"])
        def delegations(request: Request, principal: Optional[str] = None):
            """Live delegations. An expired one is not one."""
            self.authorise(request, "model:read",
                           estate_wide="reading delegated authority")
            engine = self.ctx["authority"]
            if principal:
                return {"principal": principal,
                        "delegations": engine.held_by(principal)}
            return {"delegations": list(engine.delegations.many())}

        @self.app.post(f"{api}/authority/delegations", status_code=201,
                       tags=["lifecycle"])
        def delegate(request: Request, body: DelegationIn):
            """Record what one named person may approve, and until when.

            It expires, deliberately. MAYA holds a reference to the instrument
            rather than the instrument, so it cannot tell whether the board
            resolution behind a delegation still says what it said — and a
            ceiling with no expiry is a ceiling nobody will ever revisit.
            """
            who = self.authorise(request, "policy:publish",
                                 estate_wide="delegating approval authority")
            return self.guard(lambda: self.ctx["authority"].delegate(
                body.principal, ceiling=body.ceiling,
                instrument=body.instrument, currency=body.currency,
                legal_entity=body.legal_entity, actor=self.actor(who)))

        @self.app.delete(f"{api}/models/{{name:path}}", tags=["lifecycle"])
        def delete(request: Request, name: str, reason: str = ""):
            """Administrators only, and only if nothing refers to it.

            Nineteen tables carry a `model_id`. Deleting a model with a live
            warrant, an open finding, a monitor and three parameter sets left
            every one of those rows pointing at an identifier that no longer
            resolves — and the evidence chain, which survives the deletion by
            design, then described acts against a model nobody could look up.

            The refusal names what refers to it rather than saying no: somebody
            told *why* can go and deal with it, and somebody told *no* finds
            another way.
            """
            model = model_of(name)
            who = self.authorise(request, "model:delete", model=model)
            self.guard(lambda: self.ctx["references"].refuse_if_referenced(
                "model", model["urn"], label=model["urn"]))
            return self.guard(lambda: lifecycle.delete(model, who, reason))

        # --------------------------------------------------------- campaigns
        @self.app.get(f"{api}/campaigns/kinds", tags=["lifecycle"])
        def campaign_kinds(request: Request):
            """What a round may be for, and how completion is measured."""
            self.authorise(request, "model:read")
            from core.lifecycle.campaigns import Campaigns
            return Campaigns.kinds()

        @self.app.get(f"{api}/campaigns", tags=["lifecycle"])
        def campaigns(request: Request, reference: Optional[str] = None,
                      now: Optional[float] = None):
            """Every round, least complete first — or one of them."""
            self.authorise(request, "model:read",
                           estate_wide="reading campaigns over the estate")
            engine = self.ctx["campaigns"]
            if reference is None:
                return self.guard(lambda: engine.across_the_estate(now=now))
            return self.guard(lambda: engine.status(reference, now=now))

        @self.app.post(f"{api}/campaigns", status_code=201, tags=["lifecycle"])
        def open_campaign(request: Request, body: CampaignIn):
            """Fix a population and assign it to the models' own owners."""
            who = self.authorise(
                request, "model:attest",
                estate_wide="opening a campaign across a derived population")
            return self.guard(lambda: self.ctx["campaigns"].open(
                body.reference, kind=body.kind, title=body.title,
                where=body.where, instruction=body.instruction,
                due_at=body.due_at, actor=self.actor(who)))

        @self.app.post(f"{api}/campaigns/{{reference}}/respond",
                       tags=["lifecycle"])
        def respond(request: Request, reference: str,
                    body: CampaignResponseIn):
            """Answer one item."""
            model = self.guard(lambda: self.ctx["registry"].require(body.urn))
            who = self.authorise(request, "model:attest", model=model)
            return self.guard(lambda: self.ctx["campaigns"].respond(
                reference, body.urn, state=body.state, response=body.response,
                actor=self.actor(who)))

        @self.app.post(f"{api}/campaigns/{{reference}}/reassign",
                       tags=["lifecycle"])
        def reassign(request: Request, reference: str, body: ReassignIn):
            """Move an item, on the record rather than by editing it."""
            model = self.guard(lambda: self.ctx["registry"].require(body.urn))
            who = self.authorise(request, "model:attest", model=model)
            return self.guard(lambda: self.ctx["campaigns"].reassign(
                reference, body.urn, body.to, body.reason,
                actor=self.actor(who)))

        @self.app.post(f"{api}/campaigns/{{reference}}/close",
                       tags=["lifecycle"])
        def close_campaign(request: Request, reference: str):
            """End a round, recording what was never answered."""
            who = self.authorise(
                request, "model:attest",
                estate_wide="closing a campaign over its whole population")
            return self.guard(lambda: self.ctx["campaigns"].close(
                reference, actor=self.actor(who)))

        # ------------------------------------------------------------ intake
        @self.app.get(f"{api}/intake/questions", tags=["lifecycle"])
        def intake_questions(request: Request):
            """The three questions, the cues and the sourcing vocabulary."""
            self.authorise(request, "model:read")
            from core.lifecycle.intake import Intake
            return Intake.questions()

        @self.app.get(f"{api}/intake", tags=["lifecycle"])
        def proposals(request: Request, reference: Optional[str] = None,
                      now: Optional[float] = None):
            """Every proposal, untriaged first — or one of them."""
            self.authorise(request, "model:read",
                           estate_wide="reading the intake queue")
            engine = self.ctx["intake"]
            if reference is None:
                return self.guard(lambda: engine.across_the_estate(now=now))
            return self.guard(lambda: engine.read(reference))

        @self.app.post(f"{api}/intake", status_code=201, tags=["lifecycle"])
        def propose(request: Request, body: ProposalIn):
            """Record a proposal. It is not a model and is not stored as one."""
            who = self.authorise(request, "model:read",
                                 estate_wide="recording an intake proposal")
            return self.guard(lambda: self.ctx["intake"].propose(
                body.reference, title=body.title, description=body.description,
                proposed_by=body.proposed_by,
                business_area=body.business_area, actor=self.actor(who)))

        @self.app.get(f"{api}/intake/{{reference}}/assessment",
                      tags=["lifecycle"])
        def assess(request: Request, reference: str):
            """What the description suggests, with the words it turned on.

            A reading, never a determination. A determination whose reasoning is
            invisible is one nobody can disagree with, and the whole value of
            triage is in the disagreements.
            """
            self.authorise(request, "model:read",
                           estate_wide="reading an intake assessment")
            return self.guard(lambda: self.ctx["intake"].assess(reference))

        @self.app.post(f"{api}/intake/{{reference}}/triage", tags=["lifecycle"])
        def triage_proposal(request: Request, reference: str, body: TriageIn2):
            """Record the determination a person made, beside the reading."""
            who = self.authorise(
                request, "risk:assess",
                estate_wide="triaging a proposal into or out of scope")
            return self.guard(lambda: self.ctx["intake"].triage(
                reference, in_scope=body.in_scope, sourcing=body.sourcing,
                generative=body.generative, rationale=body.rationale,
                actor=self.actor(who)))

        @self.app.post(f"{api}/intake/{{reference}}/register",
                       status_code=201, tags=["lifecycle"])
        def register_proposal(request: Request, reference: str,
                              body: RegisterProposalIn):
            """Cross from proposal to model. Refused before triage."""
            who = self.authorise(
                request, "model:register",
                estate_wide="registering a model from a proposal")
            return self.guard(lambda: self.ctx["intake"].register(
                reference, urn=body.urn, name=body.name,
                model_class=body.model_class, domain=body.domain,
                owner=body.owner, legal_entity=body.legal_entity,
                purpose=body.purpose, actor=self.actor(who)))
