"""
MAYA — model, version, alias and risk endpoints.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Query, Request
from pydantic import Field

from core.execution.urn import urn_of
from core.domain import paging
from routes.base import Body, Routes
from core.features.rendering import to_latex, to_python
from core.assumptions import KIND_MEANING as ASSUMPTION_KIND_MEANING
from core.assumptions import KINDS as ASSUMPTION_KINDS
from core.assumptions import MATERIALITIES
from core.limitations import KIND_MEANING, KINDS
from core.risk.designations import DESIGNATIONS, extra_controls
from core.risk.designations import explain as explain_designations
from core.waivers import QUORUM_BY_TIER, WAIVABLE
from core.waivers import STATUS_MEANING as WAIVER_STATUS_MEANING
from core.waivers import STATUSES as WAIVER_STATUSES
from core.registry.versions import latest_version


class RelateIn(Body):
    """One model's standing to another. `from` is a Python keyword, so the
    field is `from_urn` and the shape says so rather than being clever."""
    from_urn: str
    to_urn: str
    kind: str
    note: str = ""


class UnrelateIn(Body):
    from_urn: str
    to_urn: str
    kind: str
    reason: str


class ModelIn(Body):
    urn: str
    name: str
    model_class: str
    domain: str
    owner: str
    legal_entity: str
    purpose: str
    description: str = ""
    origin: str = "internal"


class VersionIn(Body):
    semver: str
    kernel: Dict[str, Any] = Field(default_factory=dict)
    contract: Dict[str, Any] = Field(default_factory=dict)
    artifact_digest: Optional[str] = None
    artifact_uri: Optional[str] = None


class AliasIn(Body):
    semver: str
    environment: str = "prod"
    alias: str = "champion"
    justification: str = ""


class LimitationIn(Body):
    urn: str
    semver: str
    kind: str
    statement: str
    basis: str = ""
    #: The contract clause that enforces this, if one does. Checked against the
    #: version's own contract rather than accepted — a limitation claiming an
    #: enforcement that does not exist reads as the safe case and is not.
    bound_key: Optional[str] = None


class AssumptionIn(Body):
    urn: str
    semver: str
    kind: str
    statement: str
    basis: str = ""
    #: The monitor that TESTS this assumption, if one does. Checked against the
    #: monitors that exist AND against the model they are on, rather than
    #: accepted — an assumption watched by somebody else's monitor is unwatched
    #: and reads as watched.
    monitor_id: Optional[str] = None
    #: Who is accountable for it, which is routinely not who raised it.
    owner: str = ""
    materiality: str = "moderate"
    #: What compensates when the assumption fails. Its emptiness on a material
    #: assumption is the number the estate view surfaces.
    mitigation: str = ""
    review_due: Optional[float] = None
    finding_id: Optional[str] = None
    overlay_id: Optional[str] = None


class ModelUseIn(Body):
    urn: str
    #: The string a warrant grant carries, so a grant and a use can be matched.
    declared_use: str
    name: str
    owner: str
    purpose: str = ""
    #: The institution's own vocabulary. Not closed here: a closed list would
    #: be this platform having an opinion about how a bank divides itself up.
    product: str = ""
    legal_entity: str = ""
    geography: str = ""
    channel: str = ""
    segment: str = ""
    #: Who decides on the back of the output, which is routinely not the
    #: model's owner and is the person a supervisor asks for.
    decision_authority: str = ""
    effective_from: Optional[float] = None
    #: The field that catches the commonest form of misuse. A use somebody
    #: approved, for a period that ended, which nobody switched off, is
    #: invisible to every other control here.
    effective_to: Optional[float] = None


class DesignateIn(Body):
    #: The complete set, not an addition. A designation being removed is a
    #: decision worth as much as one being applied.
    designations: List[str] = Field(default_factory=list)


class ChangeOverrideIn(Body):
    urn: str
    from_semver: str
    to_semver: str
    verdict: str
    #: Mandatory. The rules cannot see what a change is FOR, which is exactly
    #: why an override with no reasoning is indistinguishable from somebody who
    #: did not want to revalidate.
    reason: str


class WaiverIn(Body):
    urn: str
    #: Which control. Closed, and drawn from what the tiering engine requires.
    control: str
    rationale: str
    #: Mandatory. A waiver with nothing compensating records the gap and not
    #: the containment.
    compensating_control: str
    #: Mandatory, and bounded. No indefinite exceptions.
    days: float
    model_version_id: Optional[str] = None


class ApproveWaiverIn(Body):
    role: str


class RenewWaiverIn(Body):
    days: float


class WithdrawLimitationIn(Body):
    reason: str


class HoldIn(Body):
    matter: str
    owner: str
    scope_kind: str = "estate"
    scope_id: Optional[str] = None
    classes: List[str] = Field(default_factory=list)


class LiftIn(Body):
    reason: str


class ClassifyIn(Body):
    classification: str


class AssessIn(Body):
    # No defaults on these two. Exposure and purpose are the whole materiality
    # axis, and a default of "nothing, commercial" tiers an unassessed model at
    # the bottom of the lattice on nobody's word.
    exposure: float
    purpose_class: str
    # These three keep their defaults, but the route refuses the request when a
    # default is load-bearing — see `TieringEngine.load_bearing`.
    feature_count: int = 0
    uses_alternative_data: bool = False
    interpretable: bool = True
    # What was actually examined, when the facts have not moved.
    #
    # A periodic review was dischargeable by re-POSTing last year's numbers:
    # identical facts produced an identical tier and pushed `next_review_due`
    # eighteen months out, and the job that raises "review overdue" measures
    # whether the formula was RE-RUN, not whether anybody reviewed anything. A
    # reassessment that changes nothing is the commonest honest outcome of a
    # review, so it is not refused — it is required to say what was looked at.
    review_note: Optional[str] = None


class ModelRoutes(Routes):
    """The inventory API.

    Every endpoint authorises before it acts, and every act is attributed to the
    principal who made it rather than to "system". That attribution is what the
    segregation policy reads back: a version approved by the person who created
    it is refused because the evidence chain says who created it.
    """

    def register(self) -> None:
        reg, ev = self.ctx["registry"], self.ctx["evidence"]
        composition = self.ctx["composition"]
        tiering, risk_repo = self.ctx["tiering"], self.ctx["risk_repo"]
        findings, approvals = self.ctx["findings"], self.ctx["approvals"]
        # Accepts a bare name or the full urn MAYA prints everywhere; see
        # `core.execution.urn.urn_of` for why the second was a 404.
        urn = urn_of

        @self.app.get(f"{self.api}/models", tags=["models"])
        def list_models(request: Request, domain: Optional[str] = None,
                        tier: Optional[int] = None, q: Optional[str] = None,
                        limit: Optional[int] = None,
                        offset: Optional[int] = None):
            who = self.authorise(request, "model:read")
            # Filtered at the listing, not only at the detail page: a model out
            # of scope must not be discoverable by a count that does not add up.
            #
            # And filtered BEFORE the page is cut, for the same reason: page two
            # of a filtered list must not be page two of the unfiltered one with
            # holes in it.
            visible = self.ctx["authz"].visible(who, reg.list(domain, tier))
            if q:
                needle = q.strip().lower()
                visible = [m for m in visible
                           if needle in f"{m.get('name','')} {m.get('urn','')} "
                                        f"{m.get('owner','')} "
                                        f"{m.get('model_class','')}".lower()]
            return paging.page(visible, limit, offset).as_dict("models")

        # ------------------------------------------------------ composition
        @self.app.get(f"{self.api}/model-relations", tags=["models"])
        def relations(request: Request):
            """The relations one model may have to another, and what each means."""
            self.principal(request)
            from core.registry import ModelComposition
            return ModelComposition.describe()

        @self.app.post(f"{self.api}/model-relations", status_code=201,
                       tags=["models"])
        def relate(request: Request, body: RelateIn):
            """Record that one model stands to another in this way.

            Two relations do different work. `input_to` propagates -- change the
            source and this model's answer changes -- and `derives_from` does
            not: a model built from another has its own versions and its own
            approvals. Conflating them makes a challenger look like a
            dependency and inflates every blast radius it appears in.
            """
            target = self.guard(lambda: reg.require(body.to_urn))
            who = self.authorise(request, "model:amend", model=target)
            return self.guard(lambda: composition.relate(
                body.from_urn, body.to_urn, body.kind, body.note,
                actor=self.actor(who)))

        # A POST rather than a DELETE because it carries a body: removing a
        # relation requires a reason, and a reason does not belong in a query
        # string where it will be truncated and logged.
        @self.app.post(f"{self.api}/model-relations/remove", tags=["models"])
        def unrelate(request: Request, body: UnrelateIn):
            """Remove a relation, with a reason. An edge that disappears without
            one is a dependency somebody stopped believing in and nobody can ask
            about."""
            target = self.guard(lambda: reg.require(body.to_urn))
            who = self.authorise(request, "model:amend", model=target)
            return self.guard(lambda: composition.unrelate(
                body.from_urn, body.to_urn, body.kind, body.reason,
                actor=self.actor(who)))

        @self.app.get(f"{self.api}/models/{{name:path}}/relations", tags=["models"])
        def model_relations(request: Request, name: str):
            """Everything attached to this model, in both directions."""
            model = self.guard(lambda: reg.require(urn(name)))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: composition.edges_of(model["urn"]))

        @self.app.post(f"{self.api}/blast-radius", tags=["models"])
        def blast_radius(request: Request, body: Dict[str, Any]):
            """What a change here reaches, and how far away each one is.

            Only propagating relations are followed, so a challenger is not
            downstream of the model it argues with.
            """
            model = self.guard(lambda: reg.require(body["urn"]))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: composition.blast_radius(model["urn"]))

        @self.app.post(f"{self.api}/shared-dependencies", tags=["models"])
        def shared(request: Request, body: Dict[str, Any]):
            """What two or more of these models both depend on.

            The obstruction, made computable: a network that COPIES a dependency
            is not the same as one that duplicates it, and that difference is
            why an aggregate risk assignment cannot simply add up. Supervisors
            ask about common dependencies in prose; this answers it.
            """
            self.authorise(request, "model:read")
            return self.guard(lambda: composition.shared_dependencies(
                body.get("urns") or []))

        @self.app.post(f"{self.api}/models", status_code=201, tags=["models"])
        def create_model(request: Request, body: ModelIn):
            who = self.authorise(request, "model:register",
                                 model={"legal_entity": body.legal_entity,
                                        "domain": body.domain})
            return self.guard(lambda: reg.register(
                body.urn, body.name, body.model_class, body.domain, body.owner,
                body.legal_entity, body.purpose, body.description, body.origin,
                actor=self.actor(who)))

        @self.app.get(f"{self.api}/models/{{name:path}}", tags=["models"])
        def get_model(request: Request, name: str):
            m = reg.get(urn(name))
            if not m:
                raise self.not_found(f"no model {name}")
            self.authorise(request, "model:read", model=m)
            # The lifecycle state travels with the model rather than living at
            # /models/{name}/state: the name segment is a greedy `:path`
            # converter and would swallow any suffix registered after it.
            return {"model": m, "versions": reg.versions(m["urn"]),
                    "alias_history": reg.alias_history(m["urn"]),
                    "lifecycle": self.ctx["lifecycle"].state(m["urn"]),
                    "evidence": ev.for_subject(m["id"])}

        @self.app.post(f"{self.api}/models/{{name:path}}/versions", status_code=201,
                       tags=["versions"])
        def create_version(request: Request, name: str, body: VersionIn):
            who = self.authorise(request, "version:create",
                                 model=self.guard(lambda: reg.require(urn(name))))
            return self.guard(lambda: reg.create_version(
                urn(name), body.semver, body.kernel, body.contract,
                body.artifact_digest, body.artifact_uri, actor=self.actor(who)))

        # ------------------------------------------------------- limitations
        @self.app.get(f"{self.api}/limitation-kinds", tags=["models"])
        def limitation_kinds(request: Request):
            """The four kinds, and what each is for. Closed on purpose."""
            self.principal(request)
            return {"kinds": [{"kind": k, "means": KIND_MEANING[k]}
                              for k in KINDS],
                    "detail": "a limitation names the contract clause that "
                              "enforces it, or names none — and none is the "
                              "value worth counting"}

        # A model name is a QUERY parameter here rather than a path segment,
        # which is this API's rule wherever a name is not the last thing in the
        # path: `{name:path}` is greedy, so `/models/x/versions/1.0.0/limitations`
        # resolves `name` to `x/versions/1.0.0/limitations` and answers 404
        # naming a model nobody asked for. Written down in `14 §Addressing`;
        # discovered again here, which is what the rule is for.
        @self.app.get(f"{self.api}/limitations", tags=["models"])
        def limitations(request: Request,
                        urn_: Optional[str] = Query(None, alias="urn"),
                        semver: Optional[str] = Query(None)):
            """What a version cannot do — or, with no urn, the whole estate.

            The urn and semver were both REQUIRED, so the register could not
            answer its own question: "what are we relying on people to
            remember, across the book?" is the reason a limitation register
            exists, and there was no route that could be asked it and no screen
            that asked. A limitation nobody can enumerate is a limitation
            nobody is managing.
            """
            if urn_ is None:
                self.authorise(
                    request, "limitation:read",
                    estate_wide="reading every limitation on every model")
                return self.guard(
                    lambda: self.ctx["limitations"].across_the_estate())
            if semver is None:
                raise HTTPException(422, {
                    "error": "semver_required",
                    "detail": "a urn was given without a semver; a limitation "
                              "is recorded against a version, not a model",
                    "remediation": "add semver=..., or omit urn for the whole "
                                   "estate"})
            m = self.guard(lambda: reg.require(urn_of(urn_)))
            self.authorise(request, "limitation:read", model=m)
            return self.guard(
                lambda: self.ctx["limitations"].for_version(urn_of(urn_), semver))

        @self.app.post(f"{self.api}/limitations", status_code=201,
                       tags=["models"])
        def record_limitation(request: Request, body: LimitationIn):
            """State a limitation against one version."""
            m = self.guard(lambda: reg.require(urn_of(body.urn)))
            who = self.authorise(request, "limitation:record", model=m)
            return self.guard(lambda: self.ctx["limitations"].record(
                urn_of(body.urn), body.semver, body.kind, body.statement,
                basis=body.basis, bound_key=body.bound_key,
                actor=self.actor(who)))

        @self.app.post(f"{self.api}/limitations/{{limitation_id}}/withdraw",
                       tags=["models"])
        def withdraw_limitation(request: Request, limitation_id: str,
                                body: WithdrawLimitationIn):
            """Withdraw one. Never deleted: the version is immutable, so what it
            was understood to be is part of the record."""
            row = self.guard(
                lambda: self.ctx["limitations"].require(limitation_id))
            who = self.authorise(request, "limitation:withdraw",
                                 model=self.model_of(row["model_id"]))
            return self.guard(lambda: self.ctx["limitations"].withdraw(
                limitation_id, body.reason, actor=self.actor(who)))

        # -------------------------------------------------------- assumptions
        @self.app.get(f"{self.api}/assumption-kinds", tags=["models"])
        def assumption_kinds(request: Request):
            """The five kinds and the four materialities. Closed on purpose."""
            self.principal(request)
            return {"kinds": [{"kind": k, "means": ASSUMPTION_KIND_MEANING[k]}
                              for k in ASSUMPTION_KINDS],
                    "materialities": list(MATERIALITIES),
                    "detail": "an assumption names the monitor that tests it, "
                              "or names none — and none is the value worth "
                              "counting, because it is what the platform "
                              "believes and would not notice becoming false"}

        # A model name is a QUERY parameter here for the same reason it is on
        # `/limitations`: `{name:path}` is greedy and would swallow the rest of
        # the path. See `14 §Addressing`.
        @self.app.get(f"{self.api}/assumptions", tags=["models"])
        def assumptions(request: Request,
                        urn_: Optional[str] = Query(None, alias="urn"),
                        semver: Optional[str] = Query(None)):
            """What a version relies on being true — or the whole estate."""
            if urn_ is None:
                self.authorise(
                    request, "assumption:read",
                    estate_wide="reading every assumption on every model")
                return self.guard(
                    lambda: self.ctx["assumptions"].across_the_estate())
            if semver is None:
                raise HTTPException(422, {
                    "error": "semver_required",
                    "detail": "a urn was given without a semver; an assumption "
                              "is recorded against a version, not a model",
                    "remediation": "add semver=..., or omit urn for the whole "
                                   "estate"})
            m = self.guard(lambda: reg.require(urn_of(urn_)))
            self.authorise(request, "assumption:read", model=m)
            return self.guard(
                lambda: self.ctx["assumptions"].for_version(urn_of(urn_), semver))

        @self.app.post(f"{self.api}/assumptions", status_code=201,
                       tags=["models"])
        def record_assumption(request: Request, body: AssumptionIn):
            """State an assumption against one version."""
            m = self.guard(lambda: reg.require(urn_of(body.urn)))
            who = self.authorise(request, "assumption:record", model=m)
            return self.guard(lambda: self.ctx["assumptions"].record(
                urn_of(body.urn), body.semver, body.kind, body.statement,
                basis=body.basis, monitor_id=body.monitor_id,
                owner=body.owner, materiality=body.materiality,
                mitigation=body.mitigation, review_due=body.review_due,
                finding_id=body.finding_id, overlay_id=body.overlay_id,
                actor=self.actor(who)))

        @self.app.post(f"{self.api}/assumptions/{{assumption_id}}/withdraw",
                       tags=["models"])
        def withdraw_assumption(request: Request, assumption_id: str,
                                body: WithdrawLimitationIn):
            """Withdraw one. Never deleted, for the same reason a limitation is
            not: the version is immutable, so what it was understood to rely on
            is part of the record."""
            row = self.guard(
                lambda: self.ctx["assumptions"].require(assumption_id))
            who = self.authorise(request, "assumption:withdraw",
                                 model=self.model_of(row["model_id"]))
            return self.guard(lambda: self.ctx["assumptions"].withdraw(
                assumption_id, body.reason, actor=self.actor(who)))

        # -------------------------------------------------------- model uses
        @self.app.get(f"{self.api}/model-uses", tags=["models"])
        def model_uses(request: Request,
                       urn_: Optional[str] = Query(None, alias="urn"),
                       product: Optional[str] = Query(None),
                       legal_entity: Optional[str] = Query(None),
                       at: Optional[float] = Query(None)):
            """One model's uses, or every model in use for something.

            With no urn this is the *which models fed the Q2 provision* query,
            and `at` is the half that makes it worth asking: a use in force
            today and one in force in June are different sets, and the second
            is the one an examiner wants.
            """
            if urn_ is None:
                self.authorise(request, "model:read",
                               estate_wide="reading every declared use across "
                                           "the estate")
                return self.guard(
                    lambda: self.ctx["uses"].across_the_estate(
                        product=product, legal_entity=legal_entity, at=at))
            m = self.guard(lambda: reg.require(urn_of(urn_)))
            self.authorise(request, "model:read", model=m)
            return self.guard(lambda: self.ctx["uses"].for_model(urn_of(urn_)))

        @self.app.get(f"{self.api}/model-uses/lapsed", tags=["models"])
        def lapsed_uses(request: Request):
            """Uses whose window ended and which nobody retired.

            A use nobody approved gets refused. A use somebody approved, for a
            period that has ended, is invisible to every other control here —
            the grant still exists, the warrant still resolves, and every call
            under it is still authorised.
            """
            self.authorise(request, "model:read",
                           estate_wide="reading every lapsed use")
            return self.guard(lambda: self.ctx["uses"].lapsed())

        @self.app.post(f"{self.api}/model-uses", status_code=201,
                       tags=["models"])
        def declare_use(request: Request, body: ModelUseIn):
            """Record what this model is used for."""
            m = self.guard(lambda: reg.require(urn_of(body.urn)))
            who = self.authorise(request, "model:register", model=m)
            payload = body.model_dump()
            payload.pop("urn")
            return self.guard(lambda: self.ctx["uses"].declare(
                urn_of(body.urn), actor=self.actor(who), **payload))

        @self.app.post(f"{self.api}/model-uses/{{use_id}}/retire",
                       tags=["models"])
        def retire_use(request: Request, use_id: str,
                       body: WithdrawLimitationIn):
            """End a use. Never deleted: what a model was used for, and when,
            is the history a supervisor asks about."""
            row = self.guard(lambda: self.ctx["uses"].require(use_id))
            who = self.authorise(request, "model:register",
                                 model=self.model_of(row["model_id"]))
            return self.guard(lambda: self.ctx["uses"].retire(
                use_id, body.reason, actor=self.actor(who)))

        # ------------------------------------------------------ as at a date
        @self.app.get(f"{self.api}/as-at", tags=["models"])
        def as_at(request: Request, at: float,
                  urn_: Optional[str] = Query(None, alias="urn")):
            """The register as it stood at a moment, or one model in it.

            Folded from the evidence chain rather than read from a history
            table, so the answer carries the chain sequence and hash it is true
            at. A projection somebody could have rewritten is not evidence, and
            the chain cannot be rewritten without every hash after the edit
            disagreeing.

            What the chain does not carry is named in `not_projected` rather
            than guessed: *we do not know what the purpose field said in March*
            is an answer, and a confidently wrong purpose is not.
            """
            if urn_ is None:
                self.authorise(request, "model:read",
                               estate_wide="reconstructing the whole register "
                                           "as at a past date")
                return self.guard(lambda: self.ctx["as_at"].register(at))
            m = self.guard(lambda: reg.require(urn_of(urn_)))
            self.authorise(request, "model:read", model=m)
            return self.guard(
                lambda: self.ctx["as_at"].model(urn_of(urn_), at))

        # ----------------------------------------------------- designations
        @self.app.get(f"{self.api}/designations", tags=["models"])
        def designations(request: Request):
            """The four, what each means, and what each one ADDS."""
            self.principal(request)
            return {"designations": explain_designations(DESIGNATIONS),
                    "detail": "orthogonal to the tier and additive to it. A "
                              "designation does not move a model up or down "
                              "the lattice — two models at the same tier can "
                              "owe different things because one of them feeds "
                              "a regulatory submission, and no amount of "
                              "re-tiering produces a reconciliation "
                              "requirement. A tag that changes nothing is a "
                              "label"}

        @self.app.put(f"{self.api}/models/{{name:path}}/designations",
                      tags=["models"])
        def designate(request: Request, name: str, body: DesignateIn):
            """Say what this model is also subject to. Replaces the set."""
            m = self.guard(lambda: reg.require(urn_of(name)))
            who = self.authorise(request, "risk:assess", model=m)
            updated = self.guard(lambda: reg.designate(
                urn_of(name), body.designations, actor=self.actor(who)))
            return {**updated,
                    "adds_controls": extra_controls(
                        updated.get("designations") or []),
                    "why": explain_designations(
                        updated.get("designations") or [])}

        # ------------------------------------------------ change management
        @self.app.get(f"{self.api}/change-classification", tags=["models"])
        def change_classification(request: Request,
                                  urn_: str = Query(..., alias="urn"),
                                  from_semver: str = Query(...),
                                  to_semver: str = Query(...)):
            """Material or not, computed from what actually changed.

            Every reason is returned rather than reduced to the verdict,
            because the argument a person is about to have is never about the
            verdict — it is about which of the differences counts.
            """
            m = self.guard(lambda: reg.require(urn_of(urn_)))
            self.authorise(request, "model:read", model=m)
            return self.guard(lambda: self.ctx["changes"].classify(
                urn_of(urn_), from_semver, to_semver))

        @self.app.post(f"{self.api}/change-classification", tags=["models"])
        def record_change_classification(request: Request,
                                         body: ChangeOverrideIn):
            """A person's answer, recorded beside the computed one.

            Both are kept, and an override goes on the evidence chain — *this
            was computed non-material and a person called it material* is a
            much better sentence for a supervisor than a bare classification.
            """
            m = self.guard(lambda: reg.require(urn_of(body.urn)))
            who = self.authorise(request, "validation:conclude", model=m)
            return self.guard(lambda: self.ctx["changes"].override(
                urn_of(body.urn), body.from_semver, body.to_semver,
                body.verdict, body.reason, actor=self.actor(who)))

        # ---------------------------------------------------------- waivers
        @self.app.get(f"{self.api}/waivable-controls", tags=["models"])
        def waivable_controls(request: Request):
            """What may be waived, and how many signatures each tier takes."""
            self.principal(request)
            return {"controls": list(WAIVABLE),
                    "quorum_by_tier": QUORUM_BY_TIER,
                    "statuses": [{"status": s, "means": WAIVER_STATUS_MEANING[s]}
                                 for s in WAIVER_STATUSES],
                    "detail": "a waiver names a control some tier actually "
                              "requires; waiving anything else would relax "
                              "nothing while reading on a report as though it "
                              "had. Approval scales with the tier, because "
                              "relaxing a control on the estate's most "
                              "material model on one person's say-so is what "
                              "'scaled to risk' is about"}

        @self.app.get(f"{self.api}/waivers", tags=["models"])
        def waivers(request: Request,
                    urn_: Optional[str] = Query(None, alias="urn")):
            """What a model is not doing — or, with no urn, the whole estate."""
            if urn_ is None:
                self.authorise(request, "waiver:read",
                               estate_wide="reading every control the estate "
                                           "is currently not meeting")
                return self.guard(
                    lambda: self.ctx["waivers"].across_the_estate())
            m = self.guard(lambda: reg.require(urn_of(urn_)))
            self.authorise(request, "waiver:read", model=m)
            return self.guard(
                lambda: self.ctx["waivers"].for_model(urn_of(urn_)))

        @self.app.post(f"{self.api}/waivers", status_code=201, tags=["models"])
        def propose_waiver(request: Request, body: WaiverIn):
            """Ask for a control to be relaxed, for a bounded time."""
            m = self.guard(lambda: reg.require(urn_of(body.urn)))
            who = self.authorise(request, "waiver:propose", model=m)
            return self.guard(lambda: self.ctx["waivers"].propose(
                urn_of(body.urn), body.control, body.rationale,
                body.compensating_control, body.days,
                model_version_id=body.model_version_id,
                actor=self.actor(who)))

        @self.app.post(f"{self.api}/waivers/{{waiver_id}}/approve",
                       tags=["models"])
        def approve_waiver(request: Request, waiver_id: str,
                           body: ApproveWaiverIn):
            """Sign one. The proposer may not, and a tier 1 waiver takes two."""
            row = self.guard(lambda: self.ctx["waivers"].require(waiver_id))
            who = self.authorise(request, "waiver:approve",
                                 model=self.model_of(row["model_id"]))
            return self.guard(lambda: self.ctx["waivers"].approve(
                waiver_id, body.role, actor=self.actor(who)))

        @self.app.post(f"{self.api}/waivers/{{waiver_id}}/renew",
                       tags=["models"])
        def renew_waiver(request: Request, waiver_id: str, body: RenewWaiverIn):
            """Extend one, and count that it happened. Past the limit, a
            finding: a control relaxed four times running is not a temporary
            exception, it is the framework the model is governed under."""
            row = self.guard(lambda: self.ctx["waivers"].require(waiver_id))
            who = self.authorise(request, "waiver:approve",
                                 model=self.model_of(row["model_id"]))
            return self.guard(lambda: self.ctx["waivers"].renew(
                waiver_id, body.days, actor=self.actor(who)))

        @self.app.post(f"{self.api}/waivers/{{waiver_id}}/revoke",
                       tags=["models"])
        def revoke_waiver(request: Request, waiver_id: str,
                          body: WithdrawLimitationIn):
            """End one early. Never deleted: what was relaxed, and when, is
            part of what this model's governance actually was."""
            row = self.guard(lambda: self.ctx["waivers"].require(waiver_id))
            who = self.authorise(request, "waiver:revoke",
                                 model=self.model_of(row["model_id"]))
            return self.guard(lambda: self.ctx["waivers"].revoke(
                waiver_id, body.reason, actor=self.actor(who)))

        @self.app.get(f"{self.api}/mathematics", tags=["models"])
        def mathematics(request: Request, name: str = Query(..., alias="urn"),
                        semver: str = Query(...)):
            """The version's kernel as mathematics and as code, both derived.

            Neither is stored. A `latex` field beside the expression, filled in
            by whoever wrote it, is a second description of one model — and two
            descriptions drift, with the one nobody executes drifting first. So
            this renders the syntax tree the platform evaluates, which means a
            disagreement between the equation, the code and the answer is not
            possible rather than merely unlikely.

            Only a `formula` kernel has an expression to render. Every other
            runtime names an artifact MAYA does not read, and inventing an
            equation for one would be exactly the invented description this
            exists to avoid — so it says so instead.
            """
            m = self.guard(lambda: reg.require(urn_of(name)))
            self.authorise(request, "model:read", model=m)
            version = self.guard(
                lambda: reg.version_service.require(urn_of(name), semver))
            kernel = (version.get("manifest") or {}).get("kernel") or {}
            entry = kernel.get("entry") or {}
            expression = entry.get("expression")
            if kernel.get("runtime") != "formula" or not expression:
                raise HTTPException(409, {
                    "error": "not_derivable",
                    "detail": f"version {semver} runs on "
                              f"'{kernel.get('runtime') or 'no runtime'}', which "
                              f"names an artifact rather than carrying its own "
                              f"expression — so there is nothing here to derive "
                              f"an equation from",
                    "remediation": "only a 'formula' kernel is renderable; for "
                                   "everything else the mathematics belongs in "
                                   "an attached document, where a person signs "
                                   "for it"})
            # X and P together. The expression reads both — a calibrated
            # pricer's `sigma` is as much a free name as its `spot` — so a
            # rendering built from `input_schema` alone typeset the parameters
            # as \mathrm{plain names} and, worse, generated a `predict()`
            # whose signature omitted them. That function could not be called
            # for any model with parameters, which is most of them.
            fields = [f for f in ((version.get("input_schema") or [])
                                  + (version.get("parameter_schema") or []))
                      if isinstance(f, dict) and f.get("name")]
            symbols = {f["name"]: f["symbol"] for f in fields if f.get("symbol")}
            reads = sorted({f["name"] for f in fields})
            return {
                "urn": urn_of(name), "semver": semver,
                "expression": expression,
                "target": entry.get("target") or "value",
                "latex": to_latex(expression, symbols),
                "python": to_python(expression, name="predict", inputs=reads),
                "symbols": symbols,
                "inputs": sorted({f["name"] for f in
                                  (version.get("input_schema") or [])
                                  if isinstance(f, dict) and f.get("name")}),
                "parameters": sorted({f["name"] for f in
                                      (version.get("parameter_schema") or [])
                                      if isinstance(f, dict) and f.get("name")}),
                "detail": "both are derived from the expression at request "
                          "time and neither is stored, so they cannot disagree "
                          "with what runs",
            }

        @self.app.post(f"{self.api}/models/{{name:path}}/versions/{{semver}}/approve",
                       tags=["versions"])
        def approve(request: Request, name: str, semver: str):
            model = self.guard(lambda: reg.require(urn(name)))
            version = reg.version(urn(name), semver)
            if not version:
                raise self.not_found(f"no version {semver} for {name}")
            # The subject is the VERSION, because that is what the evidence chain
            # recorded `version_created` against.
            who = self.authorise(request, "version:approve", model=model,
                                 subject_id=version["id"])
            return self.guard(lambda: reg.approve_version(urn(name), semver,
                                                          actor=self.actor(who)))

        @self.app.put(f"{self.api}/models/{{name:path}}/aliases", tags=["aliases"])
        def move_alias(request: Request, name: str, body: AliasIn):
            model = self.guard(lambda: reg.require(urn(name)))
            version = reg.version(urn(name), body.semver)
            who = self.authorise(request, "alias:move", model=model,
                                 subject_id=version["id"] if version else None)
            return self.guard(lambda: reg.move_alias(
                urn(name), body.environment, body.alias, body.semver,
                actor=self.actor(who), justification=body.justification))

        @self.app.get(f"{self.api}/version-comparison", tags=["registry"])
        def version_comparison(request: Request, urn: str, left: str,
                               right: str):
            """What changed between two versions, as a diff a person reads.

            `L-7` and `L-12` already decide whether an alias *may* move — a yes
            with a reason, and the right thing to gate a promotion on. *Is this
            legal* and *what changed* are different questions, and a boolean
            cannot be turned back into the second one.

            Read `shape` first. A rebuild, a re-fit and a re-specification
            arrive at a reviewer looking identical — a new semver, a new digest,
            an approval request — and they ask completely different questions.
            """
            model = self.guard(lambda: reg.require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(
                lambda: self.ctx["version_comparison"].compare(
                    urn, left, right))

        @self.app.get(f"{self.api}/version-history", tags=["registry"])
        def version_history(request: Request, urn: str):
            """Every consecutive pair, so a reader can see the shape of the
            series.

            A model whose last six versions were all rebuilds is telling a
            different story from one with six re-specifications, and neither is
            visible from a list of semvers.
            """
            model = self.guard(lambda: reg.require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(
                lambda: self.ctx["version_comparison"].history(urn))

        @self.app.get(f"{self.api}/classification", tags=["risk"])
        def classification_of(request: Request, urn: str):
            """What this model's inputs force, and what it declares.

            A top-level path with a `urn` query rather than a suffix under
            `/models/{name}`, whose path converter is greedy.
            """
            model = self.guard(lambda: reg.require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(
                lambda: self.ctx["classification"].of_model(urn))

        @self.app.put(f"{self.api}/classification", tags=["risk"])
        def declare_classification(request: Request, urn: str,
                                   body: ClassifyIn):
            """State a model's class. Refused if it is below the derived floor.

            Higher is allowed: an output can be more disclosive than any single
            input, which is most of what re-identification is. Lower is refused,
            and the refusal names the feature that forces the floor — somebody
            told *why* can go and deal with it.
            """
            model = self.guard(lambda: reg.require(urn))
            who = self.authorise(request, "model:register", model=model)
            return self.guard(lambda: self.ctx["classification"].declare(
                urn, body.classification, actor=self.actor(who)))

        @self.app.get(f"{self.api}/classifications", tags=["risk"])
        def classifications(request: Request):
            """Every model's data classification, derived from what it reads.

            Read `untraceable` first. A model whose inputs match no catalogued
            feature has a classification derived from nothing, and reporting the
            default for it would be reporting an assumption as a finding.
            """
            self.authorise(request, "model:read")
            return self.guard(
                lambda: self.ctx["classification"].across_the_estate())

        @self.app.get(f"{self.api}/retention", tags=["registry"])
        def retention(request: Request):
            """How long each class is kept, and whether the backing meets it.

            Read `requirements_not_met` first. A WORM option is a claim about
            **where something is stored**, not a flag on a row: a directory with
            the permission bit cleared is an honest limit and not immutable
            storage, because whoever can clear the bit can set it again.
            Reporting compliance because somebody chose WORM from a dropdown is
            worse than having no such field, since the tick is what stops
            anybody asking.
            """
            self.authorise(request, "evidence:read")
            return self.guard(lambda: self.ctx["retention"].describe())

        @self.app.get(f"{self.api}/legal-holds", tags=["registry"])
        def legal_holds(request: Request):
            """Every hold, and how long each has been in force."""
            self.authorise(request, "evidence:read")
            return self.guard(
                lambda: self.ctx["legal_holds"].across_the_estate())

        @self.app.post(f"{self.api}/legal-holds", status_code=201,
                       tags=["registry"])
        def place_hold(request: Request, body: HoldIn):
            """Stop things being deleted, for a stated matter.

            A hold has **no end date, and that is correct** — it inverts the
            rule every other bounded thing here follows. A hold ends when the
            matter ends, and when that is cannot be known when it is placed;
            putting a date on it would be guessing at a litigation timetable and
            calling the guess a control. What replaces the deadline is a named
            owner and a stated matter.
            """
            who = self.authorise(request, "hold:place")
            return self.guard(lambda: self.ctx["legal_holds"].place(
                matter=body.matter, owner=body.owner,
                scope_kind=body.scope_kind, scope_id=body.scope_id,
                classes=body.classes, actor=self.actor(who)))

        @self.app.post(f"{self.api}/legal-holds/{{reference}}/lift",
                       tags=["registry"])
        def lift_hold(request: Request, reference: str, body: LiftIn):
            """Let deletion resume. The act that needs the ceremony.

            Placing a hold keeps more than necessary, which is recoverable.
            Lifting one lets deletion resume on material somebody may be about
            to ask for, which is not.
            """
            who = self.authorise(request, "hold:place")
            return self.guard(lambda: self.ctx["legal_holds"].lift(
                reference, body.reason, actor=self.actor(who)))

        @self.app.get(f"{self.api}/classification-levels", tags=["risk"])
        def classification_levels(request: Request):
            """The lattice, and what each class means.

            Closed on purpose. A join over free text means nothing:
            'Confidential', 'confidential' and 'CONF' are three classes to a
            computer and one to a person.
            """
            self.principal(request)
            from core.classification import LEVELS, MEANING
            return {"levels": [{"level": level, "means": MEANING[level]}
                               for level in LEVELS],
                    "detail": "totally ordered, so propagation is a maximum — "
                              "a thing built out of parts is not less "
                              "sensitive than its most sensitive part"}

        @self.app.post(f"{self.api}/models/{{name:path}}/assess", tags=["risk"])
        def assess(request: Request, name: str, body: AssessIn):
            m = self.guard(lambda: reg.require(urn(name)))
            who = self.authorise(request, "risk:assess", model=m)
            versions = reg.versions(urn(name))
            # The class is read off the latest version rather than sent. When
            # there is no version there is no class, and injecting "T0" here
            # silently assessed an unbuilt model as an analytic formula — the
            # simplest reading available. It is now left absent so that
            # `load_bearing` can ask the only question that matters: would
            # knowing it change the tier?
            latest_class = (latest_version(versions) or {}).get("trainability_class")
            # The designations are read off the model rather than sent, for the
            # same reason the class is: they are a property of the model, and a
            # caller who could set them in an assessment could choose which
            # controls it owes.
            facts = {**body.model_dump(),
                     "designations": list(m.get("designations") or [])}
            declared = set(body.model_dump(exclude_unset=True))
            if latest_class:
                facts["trainability_class"] = latest_class
                declared.add("trainability_class")
            # Guarded, because `load_bearing` assesses the facts twice to
            # see whether the omissions move the tier, and an assessment can
            # refuse — an unknown purpose class does. Unguarded, that refusal
            # left as a 500: a control working exactly as intended, reported
            # as a crash, which is the failure DR-6 forbids.
            missing = self.guard(lambda: tiering.load_bearing(facts, declared))
            if missing:
                # `trainability_class` is not a field the caller can send — it
                # comes from a version — so telling them to send it would be
                # a refusal naming a remedy that does not exist. It gets its
                # own sentence, and the sendable facts keep theirs.
                sendable = sorted(f for f in missing
                                  if f != "trainability_class")
                fixes = []
                if "trainability_class" in missing:
                    fixes.append(
                        "register a version first — the class is derived from "
                        "the kernel, and with no version this model's "
                        "complexity is being read at its most favourable")
                if sendable:
                    fixes.append(
                        "send " + ", ".join(sendable) + "; the schema's "
                        "defaults are the low-risk reading, and defaulting to "
                        "it silently is choosing your own tier")
                raise HTTPException(422, {
                    "error": "fact_not_supplied",
                    "detail": "this assessment lands on a different tier "
                              "depending on " + ", ".join(sorted(missing))
                              + ", and the request did not say",
                    "remediation": "; ".join(fixes)})
            self.guard(lambda: tiering.refuse_a_review_that_says_nothing(
                risk_repo, m["id"], facts, body.review_note))
            a = self.guard(lambda: tiering.assess(facts))
            was = m.get("tier")
            tiering.persist(risk_repo, m["id"], a)
            reg.set_tier(m["id"], a.tier)
            ev.append("tier_assigned", "model", m["id"],
                      {"tier": a.tier, "rationale": a.rationale,
                       "previous_tier": was,
                       "review_note": (body.review_note or "").strip() or None},
                      actor=self.actor(who))
            # A tier that RISES invalidates the approvals granted beneath it.
            # The first line set the tier and nothing looked back: a model
            # assessed Tier 4, approved on one signature, and honestly
            # reassessed to Tier 2 went on serving from prod/champion while the
            # platform simultaneously reported `quorum_required: true,
            # required_roles: [mrm, validator]`. No finding, no reopening —
            # the record said the control applied and the model had never been
            # through it.
            #
            # Recorded as a BLOCKING finding rather than by tearing up the
            # approval: unwinding it silently would strand a live model with no
            # trace, and the people who granted it are the people who have to
            # be told. Blocking is what makes it stop an alias move.
            stale = self._approvals_below_quorum(m, a.tier)
            if stale:
                self.guard(lambda: findings.raise_finding(
                    m["id"], "High",
                    f"tier raised to {a.tier}; "
                    f"{len(stale)} approved version"
                    f"{'' if len(stale) == 1 else 's'} were approved under "
                    f"tier {was}",
                    owner=m["owner"], category="governance",
                    source="self_identified",
                    blocking=True, actor=self.actor(who),
                    description=(
                        f"{', '.join(stale)} "
                        f"{'was' if len(stale) == 1 else 'were'} approved when "
                        f"this model was tier {was}, which required "
                        f"{len(approvals.required_for(was)) or 1} signature"
                        f"{'' if len(approvals.required_for(was)) == 1 else 's'}. "
                        f"Tier {a.tier} requires "
                        f"{', '.join(approvals.required_for(a.tier)) or 'one authorised person'}. "
                        f"Re-approve each version under the quorum this tier "
                        f"requires, or reassess the tier if the rise was an "
                        f"error.")))
            return {"tier": a.tier, "materiality": a.materiality, "complexity": a.complexity,
                    "required_controls": list(a.required_controls), "rationale": a.rationale,
                    "ruleset_version": a.ruleset_version,
                    "previous_tier": was,
                    "approvals_below_quorum": stale}

        @self.app.get(f"{self.api}/evidence/chain", tags=["evidence"])
        def chain(request: Request):
            self.authorise(request, "evidence:read")
            return ev.verify_chain()


    def _approvals_below_quorum(self, model: Dict[str, Any],
                                tier: int) -> List[str]:
        """Approved versions whose approval would not satisfy this tier.

        A tier is not a label on a model; it is the size of the quorum every
        version of it has to pass. Raising the tier therefore says something
        about versions that were approved before — and nothing looked.
        """
        approvals = self.ctx["approvals"]
        wanted = set(approvals.required_for(tier))
        if not wanted:
            return []                      # this tier needs no quorum at all
        registry = self.ctx["registry"]
        stale = []
        for version in registry.versions(model["urn"]):
            if version.get("status") != "approved":
                continue
            signed = {s["role"] for s in
                      approvals.signatures_for(version["id"])
                      if s.get("decision") == "approve"}
            if not wanted <= signed:
                stale.append(version["semver"])
        return stale
