"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The screens for the model algebra: versions, composition, refinement, lifecycle.

Split out of `ui_routes.py` rather than added to it. That file holds the pages
that *read* the register; these author into it, and the two have different
failure modes — a read page that breaks shows nothing, an authoring page that
breaks writes something wrong.

**These screens decide nothing.** Every refusal a user sees here is the API's,
rendered; nothing about whether an act is permitted is computed in the browser
or in this module. A page that made a governance decision locally would be a
second implementation of a rule, and a second implementation disagrees with the
first eventually, in the direction of permitting more — because that is the
direction in which nobody files a bug.

## The three endpoints this module adds, and why each has to exist

Every act on this screen goes to the endpoint that already performs it. Three
questions had no endpoint at all, and each of them is a question somebody has to
be able to ask *before* writing:

* `POST /api/v1/model-algebra/kernel` — what class would this kernel be, and
  would the version be accepted? The class is `T0`–`T8` and nobody types it, so
  a form that does not show it as it is filled in is a form whose most important
  output is invisible until after the write. It answers with
  `VersionService`'s own functions rather than a paraphrase of them.
* `POST /api/v1/model-algebra/substitution` — may version B stand in for
  version A? This is `L-7` and `L-12`, discharged by `AliasService.obligations`,
  which is the function the alias move itself discharges them with. The move is
  the act; this is the same proof without the act.
* `GET /api/v1/model-algebra/composite` — the derived schema of `to ∘ from`.
  `ModelComposition.composite_schema` computes it and nothing exposed it.

All three write nothing, carry `model:read`, and are honest about what they do
not answer: a check holds no lock, so a name free now can be taken between the
check and the write, and the write is always the authority.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse
from pydantic import Field

from core.attachments import KIND_MEANING as DOCUMENT_MEANING, KINDS as DOCUMENT_KINDS
from core.docs.subjects import describe as describe_subjects
from core.domain.algebra import FitProcedure, OutputKind, ParameterKind
from core.lifecycle import describe as describe_machine
from core.lifecycle.states import MEANING as STATE_MEANING, MUTABLE, STATES
from core.log import get_logger, swallowed
from core.registry import ModelComposition
from core.registry.aliases import AliasService
from core.registry.common import RegistryError
from core.registry.versions import VersionService
from core.risk import COMPLEXITY, CONTROLS, MATERIALITY
from core.registry.versions import latest_version
from core.execution.grammar import RUNTIME_ENTRY
from routes.base import Body, Routes, login_required

logger = get_logger(__name__)

#: What a check cannot answer, said out loud rather than left to be discovered.
#: A screen that implied a clean check meant a guaranteed write would be
#: claiming a control that is not there.
UNCHECKED = (
    "the create call is the authority; this check writes nothing and holds no "
    "lock, so the semver free now can be taken between the two",
    "whether the model's record is open to change — a new version IS a change, "
    "and an attested record refuses one until an amendment is opened",
    "the policy gate, which may tighten what is accepted and is consulted by "
    "the create call rather than here",
)


class KernelIn(Body):
    """A draft kernel. Nothing here is recorded."""
    parameter_kind: str = "none"
    fit_procedure: str = "none"
    output_kind: str = "point_estimate"
    adaptive: int = 0
    deterministic: int = 1
    input_schema: List[Dict[str, Any]] = Field(default_factory=list)
    output_schema: List[Dict[str, Any]] = Field(default_factory=list)


class SubstitutionIn(Body):
    """Two versions, and the question of whether the second may replace the first."""
    urn: str
    incumbent: str
    replacement: str
    #: Defaults to `urn`. Naming a different model answers the same proof over
    #: two registers entries, which is informative and is NOT an act the
    #: platform performs — an alias only ever moves within one model.
    replacement_urn: str = ""


def _vocabulary(word: str, kind, field: str) -> Any:
    """One enum member, or a refusal naming the whole vocabulary.

    `ParameterKind('nonsense')` is a `ValueError`, which reaches a caller as a
    500 — the platform failing rather than refusing. The vocabulary is closed
    and published, so an unknown word is the caller's to fix and is told so.
    """
    try:
        return kind(word)
    except ValueError as exc:
        swallowed(logger, exc, "read a kernel word off the check form",
                  detail=f"'{word}' is not a {field}; refusing rather than "
                         f"raising, because the vocabulary is closed and published",
                  level=logging.INFO)
        raise RegistryError(
            f"'{word}' is not a {field}; the vocabulary is "
            f"{', '.join(m.value for m in kind)}") from exc


def _derivation(kernel) -> List[Dict[str, str]]:
    """The route the class came out by, in the order the property takes it.

    The class itself is **never** recomputed here — it is read off
    `kernel.trainability_class`, which is the one place it is decided. What this
    adds is *which* of that property's branches applied, asked through the same
    public predicates the property asks: `is_accessible`, `is_terminal`, the fit
    procedure and whether the kernel adapts. A reader who cannot see which
    branch fired cannot tell a derived T0 from a T0 that came of a mistake.
    """
    steps: List[Dict[str, str]] = []
    if not kernel.parameters.is_accessible:
        steps.append({
            "reads": "parameter_kind = opaque",
            "says": "P is inhabited and the governing party cannot see it. This "
                    "short-circuits: nothing after it is read, because a fit "
                    "procedure declared over parameters nobody can inspect is "
                    "not a checkable claim."})
        return steps
    steps.append({
        "reads": f"parameter_kind = {kernel.parameters.kind.value}",
        "says": "P is accessible, so how it was inhabited is a fact about the "
                "artifact rather than an assertion about it."})
    if kernel.parameters.is_terminal:
        steps.append({
            "reads": "P is the terminal object",
            "says": "there is nothing to fit, so the fit procedure is not read. "
                    "Asking a model in this class for a training set is a "
                    "category error, not rigour."})
        return steps
    steps.append({
        "reads": f"fit_procedure = {kernel.fit.value}",
        "says": "how P was inhabited. Every legitimate way has one, which is why "
                "'none' beside real parameters is refused rather than resolved."})
    if kernel.fit is FitProcedure.TRAIN:
        steps.append({
            "reads": f"adaptive = {int(kernel.adaptive)}",
            "says": "a trained kernel that keeps learning after release is a "
                    "different class from one that does not: the artifact under "
                    "the warrant stops being the artifact that was validated."})
    return steps


def _fibre_of(fibres, trainability_class: str) -> Optional[Dict[str, Any]]:
    """The fibre over a class, or None when the class has none.

    `get` rather than `of`, because this reports rather than decides: a page
    that raised here would turn a missing fibre — which is the platform's
    problem and is gated at start-up — into a broken screen for whoever
    happened to open it.
    """
    fibre = fibres.get(trainability_class)
    if fibre is None:
        logger.info("no fibre for %s; the page says so rather than inventing one",
                    trainability_class)
        return None
    return {"trainability_class": fibre.trainability_class, "label": fibre.label,
            "evidence": list(fibre.evidence), "lifecycle": list(fibre.lifecycle),
            "metrics": list(fibre.metrics), "templates": list(fibre.templates),
            "soundness": fibre.soundness, "outcomes": fibre.outcomes,
            "answers": fibre.answers}


def _verdict(spec: Dict[str, Any], fibres) -> Dict[str, Any]:
    """What the register would make of this kernel, without recording it.

    Both halves come from `VersionService`: `kernel_of` builds the kernel the
    create call builds, and `_refuse_unexplained_parameters` is the refusal the
    create call raises. Reaching for the second one by its private name is
    deliberate and is the lesser evil — the alternative is a copy of the rule
    living on a screen, and the copy is the one that drifts.
    """
    kernel = VersionService.kernel_of(spec, None)
    refusal = None
    try:
        VersionService._refuse_unexplained_parameters(kernel)
    except RegistryError as exc:
        # Rendered rather than raised: the derivation above is what explains the
        # refusal, and a 409 here would carry the refusal and lose the account
        # of how the class was arrived at.
        swallowed(logger, exc, "showed the version refusal on the form",
                  detail="the create call raises this; the check shows it beside "
                         "the derivation that caused it",
                  level=logging.INFO)
        refusal = str(exc)
    trainability_class = kernel.trainability_class
    return {
        "ok": 0 if refusal else 1,
        "refusal": refusal,
        "trainability_class": trainability_class,
        "requires_fitting_evidence": int(kernel.requires_fitting_evidence),
        "derivation": _derivation(kernel),
        "fibre": _fibre_of(fibres, trainability_class),
        "not_checked": list(UNCHECKED),
        "detail": (f"this kernel is {trainability_class}, derived from how P is "
                   f"inhabited and never declared"),
    }


class ModelAlgebraRoutes(Routes):
    """Screens for the operations *on* models, and the three checks they need."""

    def register(self) -> None:
        registry = self.ctx["registry"]
        composition, fibres = self.ctx["composition"], self.ctx["fibres"]

        # ------------------------------------------------------------- index
        @self.app.get("/model-algebra", response_class=HTMLResponse, tags=["ui"])
        def algebra_index(request: Request):
            """The vocabulary: what may be derived, related or refused, in one place.

            A hub rather than a menu. Everything on it is read from the code
            that enforces it — the relations from `ModelComposition.describe`,
            the classes from the fibration, the states from the state machine,
            the quorum from the approval service — so a rule that changes
            changes here without anybody editing a template.
            """
            if (r := login_required(request)) is not None:
                return r
            who = self.page_principal(request)
            return self.page(
                request, "model_algebra_index.html",
                models=self.ctx["authz"].visible(who, registry.list()),
                relations=ModelComposition.describe(),
                classes=[c for c in (_fibre_of(fibres, name)
                                     for name in fibres.classes()) if c],
                machine=describe_machine(),
                states=[{"state": s, "means": STATE_MEANING.get(s, ""),
                         "mutable": int(s in MUTABLE)} for s in STATES],
                quorum=self.ctx["approvals"].describes(),
                subjects=describe_subjects(),
                parameter_kinds=[k.value for k in ParameterKind],
                fit_procedures=[p.value for p in FitProcedure],
                output_kinds=[k.value for k in OutputKind])

        # ----------------------------------------------------------- version
        @self.app.get("/model-algebra/version/{name:path}",
                      response_class=HTMLResponse, tags=["ui"])
        def version_page(request: Request, name: str):
            """Create a version, with the class derived in front of you.

            The two facts that decide the class are the first two fields, and
            the derivation is shown as they are chosen rather than after the
            write — because `trainability_class` is not something the author
            supplies and is the thing everything downstream reads.
            """
            model = registry.get(_urn(name))
            if (refusal := self._gate(request, model, name,
                                      f"Versions of {name}")) is not None:
                return refusal
            versions = registry.versions(model["urn"])
            return self.page(
                request, "model_algebra_version.html", model=model,
                name=name, versions=versions,
                classes={v["semver"]: _fibre_of(fibres, v["trainability_class"])
                         for v in versions},
                flow=self.ctx["lifecycle"].state(model["urn"]),
                parameter_kinds=[k.value for k in ParameterKind],
                fit_procedures=[p.value for p in FitProcedure],
                output_kinds=[k.value for k in OutputKind],
                # The realisation half. This form had the derived-class preview
                # and no way to say what runs, while `/models/new` could say
                # what runs and showed no class — so the screen tutorial 01
                # sends you to could not create a version that executes, and
                # the one that could gave no feedback on what it was producing.
                runtimes=sorted(RUNTIME_ENTRY),
                runtime_entry={k: list(v) for k, v in RUNTIME_ENTRY.items()},
                unchecked=list(UNCHECKED),
                # Whether this person may create is the API's answer. This only
                # decides whether to say so before the form is filled in rather
                # than after, and it does not include segregation — which is
                # checked against the evidence chain at the act itself.
                may_create=self.may_view(request, "version:create", model))

        # ------------------------------------------------------- composition
        @self.app.get("/model-algebra/composition", response_class=HTMLResponse,
                      tags=["ui"])
        def composition_page(request: Request, urn: str = ""):
            """Propose an edge, and see it accepted or refused.

            An `input_to` edge is a claim about types: what the source produces
            must arrive where the target reads. Drawn and never checked it is a
            picture; checked, it is composition, and the composite has a
            *derived* schema rather than a declared one.
            """
            if (r := login_required(request)) is not None:
                return r
            who = self.page_principal(request)
            models = self.ctx["authz"].visible(who, registry.list())
            subject = registry.get(urn) if urn else None
            if subject is not None and not self.may_view(request, "model:read",
                                                         subject):
                return self.refused_page(request, f"The model {urn}")
            return self.page(
                request, "model_algebra_composition.html", models=models,
                relations=ModelComposition.describe(), subject=subject,
                edges=composition.edges_of(subject["urn"]) if subject else None,
                radius=composition.blast_radius(subject["urn"]) if subject else None,
                may_relate=(self.may_view(request, "model:amend", subject)
                            if subject else self.may_view(request, "model:amend")))

        # -------------------------------------------------------- refinement
        @self.app.get("/model-algebra/refinement/{name:path}",
                      response_class=HTMLResponse, tags=["ui"])
        def refinement_page(request: Request, name: str):
            """May B replace A, and the alias that is the act of saying yes.

            Both halves on one screen on purpose: the obligations an alias move
            discharges are exactly the question 'may this replace that', and
            separating them is how somebody comes to believe the move is a
            judgement call.
            """
            model = registry.get(_urn(name))
            if (refusal := self._gate(request, model, name,
                                      f"Refinement for {name}")) is not None:
                return refusal
            urn = model["urn"]
            versions = registry.versions(urn)
            return self.page(
                request, "model_algebra_refinement.html", model=model, name=name,
                versions=versions, history=registry.alias_history(urn),
                # The history holds version *ids*, and an id is not something a
                # reviewer can read. Resolved here rather than in the template,
                # which would have to hold a loop to do it.
                version_names={v["id"]: v["semver"] for v in versions},
                may_move=self.may_view(request, "alias:move", model))

        # --------------------------------------------------------- lifecycle
        @self.app.get("/model-algebra/lifecycle/{name:path}",
                      response_class=HTMLResponse, tags=["ui"])
        def lifecycle_page(request: Request, name: str):
            """Seven states, the legal moves out of this one, and who may make them.

            An attested record refuses field changes *and* new versions, and the
            only route out of immutability is an amendment. Both refusals are
            reachable from this page rather than described on it.
            """
            model = registry.get(_urn(name))
            if (refusal := self._gate(request, model, name,
                                      f"The lifecycle of {name}")) is not None:
                return refusal
            who = self.page_principal(request)
            return self.page(
                request, "model_algebra_lifecycle.html", model=model, name=name,
                flow=self.ctx["lifecycle"].state(model["urn"]), now=time.time(),
                machine=describe_machine(),
                states=[{"state": s, "means": STATE_MEANING.get(s, ""),
                         "mutable": int(s in MUTABLE)} for s in STATES],
                versions=registry.versions(model["urn"]),
                # Which permissions the reader holds, so the table of moves can
                # say which of them this person carries. It is not a decision:
                # scope and segregation are checked at the act, and a permission
                # held is not an act allowed.
                permissions=sorted(self.ctx["authz"].explain(who)["permissions"])
                if who else [])

        # ------------------------------------------------------------ quorum
        @self.app.get("/model-algebra/quorum/{name:path}",
                      response_class=HTMLResponse, tags=["ui"])
        def quorum_page(request: Request, name: str):
            """Approval as a quorum, with its depth following the tier.

            The button that approves with one signature is offered, and where a
            quorum applies it is refused by the register with the endpoint that
            does the right thing named. Hiding it would teach nobody why.
            """
            model = registry.get(_urn(name))
            if (refusal := self._gate(request, model, name,
                                      f"Version approval for {name}")) is not None:
                return refusal
            urn, approvals = model["urn"], self.ctx["approvals"]
            versions = registry.versions(urn)
            return self.page(
                request, "model_algebra_quorum.html", model=model, name=name,
                versions=versions, quorum=approvals.describes(),
                needed={v["semver"]: approvals.needed(urn, v["semver"])
                        for v in versions},
                history={v["semver"]: approvals.history(urn, v["semver"])
                         for v in versions},
                may_open=self.may_view(request, "version:approve", model),
                may_sign=self.may_view(request, "version:sign", model))

        # -------------------------------------------------------------- risk
        @self.app.get("/model-algebra/risk/{name:path}",
                      response_class=HTMLResponse, tags=["ui"])
        def risk_page(request: Request, name: str):
            """Materiality × complexity → tier, with the derivation kept.

            The grid is the tiering engine's own `tau` evaluated at every point,
            not a table somebody typed: a picture of the map that disagreed with
            the map would be worse than no picture.
            """
            model = registry.get(_urn(name))
            if (refusal := self._gate(request, model, name,
                                      f"The risk assessment for {name}")) is not None:
                return refusal
            tiering, versions = self.ctx["tiering"], registry.versions(model["urn"])
            # The recorded assessment, and the facts it was reached on.
            #
            # The tier was shown as a number with no derivation anywhere, while
            # the form beneath it shipped a zero exposure and the lowest-ranked
            # purpose already selected — so submitting it as rendered assessed
            # the model at minimum risk, returned 200, and said nothing. Both
            # halves of that are fixed here: the derivation is rendered, and
            # the form starts from what was last recorded rather than from the
            # least conservative answer available.
            assessments = self.ctx["risk_repo"].many(model_id=model["id"])
            assessment = assessments[-1] if assessments else None
            facts = (assessment or {}).get("facts") or {}
            # Does the recorded assessment still describe this model? It was
            # reached before the versions existed for every model in a seeded
            # estate, so its complexity term spoke about a class the register
            # has since superseded.
            recorded_class = facts.get("trainability_class")
            declared = latest_version(versions).get("trainability_class") if versions else None
            return self.page(
                request, "model_algebra_risk.html", model=model, name=name,
                versions=versions, latest=versions[-1] if versions else None,
                materiality=list(MATERIALITY), complexity=list(COMPLEXITY),
                grid=[[tiering.tau(m, c) for c in COMPLEXITY] for m in MATERIALITY],
                controls={tier: list(names) for tier, names in CONTROLS.items()},
                purposes=self._purpose_classes(),
                assessment=assessment, facts=facts,
                assessed_before_any_version=bool(assessment and not recorded_class
                                                 and declared),
                declared_class=declared, recorded_class=recorded_class,
                may_assess=self.may_view(request, "risk:assess", model))

        # --------------------------------------------------------- documents
        @self.app.get("/model-algebra/documents/{name:path}",
                      response_class=HTMLResponse, tags=["ui"])
        def documents_page(request: Request, name: str):
            """What is filed against this model, and against what exactly.

            A document is filed against what it is ABOUT, and the subject is
            always pinned: `model_version`, never a moving name.
            """
            model = registry.get(_urn(name))
            if (refusal := self._gate(request, model, name,
                                      f"Documents for {name}",
                                      permission="document:read")) is not None:
                return refusal
            attachments = self.ctx["attachments"]
            return self.page(
                request, "model_algebra_documents.html", model=model, name=name,
                versions=registry.versions(model["urn"]),
                attachments=attachments.for_model(model["id"]),
                status=attachments.status(model["id"]),
                kinds=[{"kind": k, "means": DOCUMENT_MEANING[k]}
                       for k in DOCUMENT_KINDS],
                subjects=describe_subjects(),
                may_attach=self.may_view(request, "document:attach", model),
                may_review=self.may_view(request, "document:review", model))

        # ------------------------------------------------------------ checks
        @self.app.post(f"{self.api}/model-algebra/kernel", tags=["versions"])
        def kernel_check(request: Request, body: KernelIn):
            """What class would this kernel be, and would the version be accepted?

            Carries `model:read` and not `version:create`, for the reason the
            feature check does: requiring the writing permission in order to
            *look* at what a draft derives to teaches authors to skip the step,
            and the step is the one that keeps the register clean.
            """
            self.authorise(request, "model:read")
            return self.guard(lambda: _verdict(_spec(body), fibres))

        @self.app.post(f"{self.api}/model-algebra/substitution", tags=["versions"])
        def substitution(request: Request, body: SubstitutionIn):
            """May the replacement stand in for the incumbent? L-7 and L-12.

            Discharged by `AliasService.obligations`, which is the function the
            alias move discharges them with rather than a second reading of the
            same two laws.
            """
            incumbent_model = self.guard(lambda: registry.require(body.urn))
            self.authorise(request, "model:read", model=incumbent_model)
            other_urn = body.replacement_urn or body.urn
            replacement_model = self.guard(lambda: registry.require(other_urn))
            if other_urn != body.urn:
                self.authorise(request, "model:read", model=replacement_model)
            old = self.guard(lambda: registry.version_service.require(
                body.urn, body.incumbent))
            new = self.guard(lambda: registry.version_service.require(
                other_urn, body.replacement))
            proof = AliasService.obligations(new, old)
            return {
                "incumbent": f"{body.urn}@{body.incumbent}",
                "replacement": f"{other_urn}@{body.replacement}",
                "same_model": int(other_urn == body.urn),
                **proof,
                "ok": int(proof["refinement"]["holds"] and proof["variance"]["ok"]),
                "detail": _substitution_detail(proof, other_urn == body.urn),
            }

        @self.app.get(f"{self.api}/aggregate-risk", tags=["models"])
        def aggregate_risk(request: Request, from_urn: str, to_urn: str):
            """`L-14` for one composable pair: is the composite at least as
            risky as the join of its parts, and what makes it riskier?

            No single number comes back. The board pack refuses to produce one
            and this is not the side door — the interaction term is a set of
            named obstructions, each read from something the register holds.
            """
            source = self.guard(lambda: registry.require(from_urn))
            target = self.guard(lambda: registry.require(to_urn))
            self.authorise(request, "model:read", model=source)
            self.authorise(request, "model:read", model=target)
            return self.guard(
                lambda: self.ctx["aggregate"].holds(from_urn, to_urn))

        @self.app.get(f"{self.api}/model-algebra/composite", tags=["models"])
        def composite(request: Request, from_urn: str, to_urn: str):
            """The type of `to ∘ from`, and the contract of it.

            Derived rather than declared, which is the whole reason to type the
            edge — a composite whose schema somebody wrote down is a composite
            that can disagree with its parts.

            The schema says what the pair needs. The `contract` says under what
            conditions the pair still promises anything, and reports which of
            the target's operating boundaries the source's own guarantee
            settles — along with the ones it speaks to and does not settle,
            which look covered by the wiring and are not.
            """
            source = self.guard(lambda: registry.require(from_urn))
            target = self.guard(lambda: registry.require(to_urn))
            self.authorise(request, "model:read", model=source)
            self.authorise(request, "model:read", model=target)
            return self.guard(lambda: composition.composite_schema(from_urn, to_urn))

    # ------------------------------------------------------------------ util
    def _gate(self, request: Request, model: Optional[Dict[str, Any]], name: str,
              what: str, permission: str = "model:read"):
        """Sign-in, existence and scope, in that order. None when the page may render.

        Scope is checked on the page and not only on the API it calls, because a
        page that renders a model the API refuses has already disclosed it — the
        versions, the schemas and the whole shape of the model are on the screen
        before any call is made.
        """
        if (r := login_required(request)) is not None:
            return r
        if model is None:
            return self.page(request, "not_found.html", http_status=404, name=name)
        if not self.may_view(request, permission, model):
            return self.refused_page(request, what)
        return None

    def _purpose_classes(self) -> List[Dict[str, Any]]:
        """The purpose classes the tiering engine was configured with.

        Read from the same configuration the engine reads rather than listed on
        the page: a class the page offers and the engine does not know ranks as
        1, and the tier comes out low for a reason nobody can see.
        """
        prefix = "risk.purpose_ranks."
        cfg = self.ctx["config"]
        return sorted(({"purpose": key[len(prefix):], "rank": cfg.get_int(key, 1)}
                       for key in cfg.as_dict() if key.startswith(prefix)),
                      key=lambda row: (row["rank"], row["purpose"]))


def _urn(name: str) -> str:
    return f"maya://model/{name}"


def _spec(body: KernelIn) -> Dict[str, Any]:
    """A draft form as the kernel spec `create` takes, with the words checked.

    The vocabulary is closed, so an unrecognised word is refused here rather
    than raised out of an enum constructor three frames down as a 500.
    """
    _vocabulary(body.parameter_kind, ParameterKind, "parameter kind")
    _vocabulary(body.fit_procedure, FitProcedure, "fit procedure")
    _vocabulary(body.output_kind, OutputKind, "output kind")
    return {"parameter_kind": body.parameter_kind,
            "fit_procedure": body.fit_procedure,
            "output_kind": body.output_kind,
            "adaptive": bool(body.adaptive),
            "deterministic": bool(body.deterministic),
            "input_schema": body.input_schema,
            "output_schema": body.output_schema}


def _substitution_detail(proof: Dict[str, Any], same_model: bool) -> str:
    """Say what the answer means, including where it is not an act.

    The alias move is the only place the platform acts on this proof, and it
    only ever moves within one model. Answering across two models is useful and
    is not a promotion path, and saying so is cheaper than letting somebody
    discover it.
    """
    verdict = ("the replacement may stand in for the incumbent"
               if proof["refinement"]["holds"] and proof["variance"]["ok"]
               else f"refused — contract: {proof['refinement']['reason']}; "
                    f"schemas: {proof['variance']['reason']}")
    if same_model:
        return (f"{verdict}. This is the proof an alias move discharges, so a "
                f"move to this version would be judged on exactly this")
    return (f"{verdict}. These are two different models, so nothing here "
            f"promotes anything: an alias moves within one model, and this "
            f"answer is a comparison rather than a route")
