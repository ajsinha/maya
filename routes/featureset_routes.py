"""
MAYA — featuresets, derived features and fitted parameters.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A featureset names a presentation of X; a parameter set names a point in P.
Between them they are what a warrant needs in order to mean "train this model on
that data" rather than "train it on whatever is around".
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request, Query
from pydantic import Field

from core.features.expressions import describe as describe_language
from core.parameters import PROVENANCE_MEANING
import logging

from core.log import get_logger, swallowed
from routes.base import Body, Routes

logger = get_logger(__name__)
from routes.warrant_routes import strip_qualifier


class FeatureIn(Body):
    name: str
    entity: str
    dtype: str = "numeric"
    description: str = ""
    shape: Any = None
    components: Optional[List[str]] = None
    composes: Optional[List[Any]] = None
    operations: Optional[List[Dict[str, Any]]] = None
    defaults: Optional[Dict[str, Any]] = None
    ephemeral: bool = False
    ttl_days: Optional[float] = None


class AmendIn(Body):
    fields: Dict[str, Any]


class SealIn(Body):
    note: str = ""


class BreakSealIn(Body):
    reason: str


class RetireIn(Body):
    # Required, with no default. A feature leaving the catalogue without a
    # stated reason is a decision nobody can review afterwards, which is the
    # thing this register exists to prevent.
    reason: str


class TransferIn(Body):
    to: str
    reason: str = ""


class PolicyIn(Body):
    defaults: Dict[str, Any]


class DerivedIn(Body):
    name: str
    expression: str
    dtype: str = "numeric"
    description: str = ""
    evaluator: str = "internal"
    on_error: str = "null"
    note: str = ""
    # Only for `external`, and only when the expression is one MAYA cannot
    # parse: the features it reads, declared, so lineage and the leakage check
    # still have something to work with. Refused on an internal definition,
    # where the expression is the single source of truth.
    inputs: List[str] = Field(default_factory=list)


class FeaturesetPreviewIn(Body):
    """The composition half of a definition, with nothing that identifies it.

    A preview needs no name, entity or owner, and asking for them would make
    somebody invent three fields to answer a question about a fourth.
    """
    slots: Dict[str, Any] = {}
    composes: Optional[List[Any]] = None
    operations: Optional[List[Dict[str, Any]]] = None
    defaults: Optional[Dict[str, Any]] = None


class FeaturesetIn(Body):
    name: str
    entity: str
    slots: Dict[str, Any] = {}
    composes: Optional[List[Any]] = None
    operations: Optional[List[Dict[str, Any]]] = None
    defaults: Optional[Dict[str, Any]] = None
    ephemeral: bool = False
    ttl_days: Optional[float] = None
    label_slot: Optional[str] = None
    outcome_window_days: int = 0
    grain: str = ""
    description: str = ""


class VersionIn(Body):
    bindings: Dict[str, Any]
    label: Optional[Dict[str, Any]] = None
    note: str = ""


class FitIn(Body):
    urn: str
    snapshot_id: str
    environment: str = "lab"
    principal: str
    declared_use: str = "model_development"
    window: dict
    name: str = "fitted"
    kind: str = "coefficients"
    note: str = ""


class AssembleIn(Body):
    version: int
    spine: list
    as_of: float
    name: Optional[str] = None


class RunIn(Body):
    """A run somebody else will execute, declared before it does.

    There is no field for a job specification and no endpoint that submits one.
    MAYA is the callee: it records the authority and takes delivery of what came
    back. `log_uri` is recorded and never read — fetching it would put this
    platform's readiness on somebody else's object store.
    """
    reference: str
    verb: str
    urn: str = ""
    semver: str = ""
    warrant_id: str = ""
    parent: str = ""
    purpose: str = ""
    resource_profile: Dict[str, Any] = Field(default_factory=dict)
    environment: Dict[str, Any] = Field(default_factory=dict)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    hyperparameters: Dict[str, Any] = Field(default_factory=dict)
    seeds: Dict[str, Any] = Field(default_factory=dict)
    log_uri: str = ""
    expected_seconds: Optional[float] = None


class CloseRunIn(Body):
    """What a run produced. `lost` is not accepted here.

    It is derived from the clock, because a caller who could report a run lost
    could close one it would rather nobody read.
    """
    state: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    parameter_set_id: str = ""
    cost: Optional[float] = None
    note: str = ""


class RetrainPolicyIn(Body):
    triggers: List[str] = Field(default_factory=list)
    tolerance: Dict[str, Any] = Field(default_factory=dict)
    auto_accept: bool = False
    rationale: str
    expires_at: Optional[float] = None


class ParametersIn(Body):
    urn: str
    semver: str
    name: str
    kind: str
    values: Dict[str, Any] = {}
    provenance: str = "fitted"
    diagnostics: Dict[str, Any] = {}
    featureset: Optional[str] = None
    featureset_version: Optional[int] = None
    window: Optional[Dict[str, float]] = None
    as_of: Optional[float] = None
    snapshot_id: Optional[str] = None
    warrant_id: Optional[str] = None
    values_uri: Optional[str] = None
    note: str = ""


class ReviewIn(Body):
    accept: bool
    note: str = ""


class FeaturesetRoutes(Routes):
    def register(self) -> None:
        features, api = self.ctx["features"], self.api
        parameters, registry = self.ctx["parameters"], self.ctx["registry"]

        # ------------------------------------------------------- derived features
        # ------------------------------------------------------ dependencies
        @self.app.get(f"{api}/references", tags=["features"])
        def references(request: Request, kind: str = Query(...),
                       id_: str = Query(..., alias="id")):
            """What refers to this — and whether it could be deleted.

            The same index a delete consults. *Where is this feature used?* and
            *may I remove it?* are the same question with different
            consequences, and answering them separately is how a screen comes to
            list three usages while the delete check knows about four.
            """
            self.authorise(request, "feature:read")
            try:
                return self.ctx["references"].to(kind, id_)
            except ValueError as exc:
                # Translated rather than swallowed: the caller asked about a
                # kind the index does not answer for, which is a 422 naming the
                # ones it does — not a 500 and not an empty list, which would
                # read as "nothing refers to it".
                swallowed(logger, exc, "looked up what refers to something",
                          detail=f"'{kind}' is not a kind this index answers "
                                 f"for; refused rather than answered empty",
                          level=logging.INFO)
                raise HTTPException(422, {
                    "error": "unknown_reference_kind", "detail": str(exc),
                    "remediation": "ask about one of the kinds it names"}) from exc

        @self.app.get(f"{api}/expression-language", tags=["features"])
        def language(request: Request):
            """What a derived feature may be written in. Deliberately small."""
            self.principal(request)
            return describe_language()

        @self.app.get(f"{api}/derived-features", tags=["features"])
        def list_derived(request: Request):
            self.authorise(request, "feature:read")
            return {"derived": features.derived.list()}

        @self.app.get(f"{api}/retrieval", tags=["features"])
        def retrieval(request: Request):
            """What MAYA can do to values on the way out, and the rules it obeys."""
            self.principal(request)
            from core.features import alignment, policy, preparation
            return {"preparation": preparation.describe(),
                    "alignment": alignment.describe(),
                    "policy": policy.describe(),
                    "composition": __import__(
                        "core.features.composition",
                        fromlist=["describe"]).describe()}

        @self.app.post(f"{api}/derived-features", status_code=201, tags=["features"])
        def define_derived(request: Request, body: DerivedIn):
            """Declare Z = f(X, Y). Corrections are new definition versions."""
            who = self.authorise(request, "feature:define")
            return self.guard(lambda: features.define_derived(
                body.name, body.expression, body.dtype, body.description,
                owner=self.actor(who), evaluator=body.evaluator,
                on_error=body.on_error, note=body.note, inputs=body.inputs,
                actor=self.actor(who)))

        @self.app.get(f"{api}/derived-features/{{name}}/lineage", tags=["features"])
        def lineage(request: Request, name: str):
            """Everything this feature rests on, and everything resting on it."""
            self.authorise(request, "feature:read")
            return self.guard(lambda: {
                "feature": name,
                "rests_on": features.lineage(name),
                "depended_on_by": features.dependants_of(name)})

        @self.app.get(f"{api}/features/{{name}}/resolved", tags=["features"])
        def resolved_feature(request: Request, name: str):
            """The feature as it actually stands.

            Not what the row says — what the row plus its parents plus its own
            operations say, with its shape, its retrieval policy and how long it
            has left. Working that out is MAYA's job, not the caller's.
            """
            self.authorise(request, "feature:read")
            return self.guard(lambda: features.resolved_feature(name))

        @self.app.post(f"{api}/features/{{name}}/amend", tags=["features"])
        def amend_feature(request: Request, name: str, body: AmendIn):
            who = self.authorise(request, "feature:define")
            return self.guard(lambda: features.catalogue.amend(
                name, body.fields, self.actor(who)))

        @self.app.post(f"{api}/features/{{name}}/seal", tags=["features"])
        def seal_feature(request: Request, name: str, body: SealIn):
            """Declare it final. It can still be composed from — that is why."""
            who = self.authorise(request, "feature:seal")
            return self.guard(lambda: features.seal_feature(
                name, self.actor(who), body.note))

        @self.app.post(f"{api}/features/{{name}}/break-seal", tags=["features"])
        def break_feature_seal(request: Request, name: str, body: BreakSealIn):
            """Administrators only, and never quietly."""
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: features.catalogue.break_seal(
                name, self.actor(who), body.reason))

        @self.app.post(f"{api}/features/{{name}}/transfer", tags=["features"])
        def transfer_feature(request: Request, name: str, body: TransferIn):
            """Hand on the responsibility. The creator does not move."""
            who = self.authorise(request, "feature:define")
            return self.guard(lambda: features.catalogue.transfer(
                name, body.to, self.actor(who), body.reason))

        @self.app.post(f"{api}/features/{{name}}/retire", tags=["features"])
        def retire_feature(request: Request, name: str, body: RetireIn):
            """Take a durable feature out of use, keeping the record.

            The act every refusal on `destroy` has named since they were
            written, and which nothing implemented — so a feature created by
            mistake was permanent, and the two refusals pointed at each other:
            delete the featureset and you are told to remove what refers to it;
            delete the feature and you are told to correct the view version.
            """
            who = self.authorise(request, "feature:define")
            # The same index a delete consults, so retiring cannot strand
            # anything a delete would have refused to strand.
            self.guard(lambda: self.ctx["references"].refuse_if_referenced(
                "feature", name, label=f"feature '{name}'"))
            return self.guard(lambda: features.catalogue.retire(
                name, body.reason, actor=self.actor(who)))

        @self.app.post(f"{api}/featuresets/{{name}}/retire", tags=["features"])
        def retire_featureset(request: Request, name: str, body: RetireIn):
            """Take a durable featureset out of use, keeping the record."""
            who = self.authorise(request, "featureset:define")
            self.guard(lambda: self.ctx["references"].refuse_if_referenced(
                "featureset", name, label=f"featureset '{name}'"))
            return self.guard(lambda: features.sets.retire(
                name, body.reason, actor=self.actor(who)))

        @self.app.delete(f"{api}/features/{{name}}", tags=["features"])
        def destroy_feature(request: Request, name: str):
            """Remove an ephemeral feature. The rows go; the record does not.

            "Ephemeral" is the right rule and not the whole rule: an ephemeral
            feature sitting in a materialised view or a published featureset
            version is exactly as load-bearing while it is there.
            """
            who = self.authorise(request, "feature:define")
            # Ordering matters, and it is about which refusal helps.
            #
            # "A durable feature is retired, not destroyed" is a property of the
            # THING and the answer is the same tomorrow. "Two views carry it" is
            # a property of the ESTATE and changes when somebody deals with
            # them. Telling a person about the estate when the thing is not
            # deletable at all sends them to remove three references and meet
            # the real refusal afterwards, so the register's own rule goes
            # first and this applies to what survives it.
            row = self.guard(lambda: features.catalogue.require(name))
            if row.get("ephemeral"):
                self.guard(lambda: self.ctx["references"].refuse_if_referenced(
                    "feature", name, label=f"feature '{name}'"))
            return self.guard(lambda: features.catalogue.destroy(
                name, "asked for", self.actor(who)))

        # -------------------------------------------------------------- featuresets
        @self.app.get(f"{api}/featuresets", tags=["features"])
        def list_sets(request: Request):
            self.authorise(request, "feature:read")
            return {"featuresets": features.sets.list()}

        @self.app.post(f"{api}/featuresets", status_code=201, tags=["features"])
        def define_set(request: Request, body: FeaturesetIn):
            """Declare the schema. Constituents come later, with a version."""
            who = self.authorise(request, "featureset:define")
            return self.guard(lambda: features.define_featureset(
                body.name, body.entity, self.actor(who), body.slots,
                body.label_slot, body.outcome_window_days, body.grain,
                body.description, body.composes, body.operations,
                body.ephemeral, body.ttl_days, body.defaults, self.actor(who)))

        @self.app.post(f"{api}/featuresets/preview", tags=["features"])
        def preview_featureset(request: Request, body: FeaturesetPreviewIn):
            """What this featureset WOULD resolve to. Declares nothing.

            Composition, inheritance and overrides are the part of the design
            people get wrong, and for a good reason: the answer is not what you
            typed, it is what your parents plus your operations say. Without
            this, finding out means declaring one — and the register fills with
            attempts.

            It refuses exactly what `define` refuses, because a preview that
            accepted more than the real thing would be worse than none.
            """
            self.authorise(request, "featureset:define")
            return self.guard(lambda: features.preview_featureset(
                body.slots, body.composes, body.operations, body.defaults))

        @self.app.get(f"{api}/featuresets/{{name}}", tags=["features"])
        def read_set(request: Request, name: str):
            self.authorise(request, "feature:read")
            return self.guard(lambda: {
                **features.sets.require(name),
                "versions": [{"version": v["version"], "digest": v["digest"],
                              "created_at": v["created_at"], "note": v["note"]}
                             for v in features.sets.versions_of(name)]})

        @self.app.get(f"{api}/featuresets/{{name}}/resolved", tags=["features"])
        def resolved_set(request: Request, name: str):
            """The slots this featureset actually has, and who decided each."""
            self.authorise(request, "feature:read")
            return self.guard(lambda: features.resolved_featureset(name))

        @self.app.post(f"{api}/featuresets/{{name}}/seal", tags=["features"])
        def seal_set(request: Request, name: str, body: SealIn):
            who = self.authorise(request, "featureset:seal")
            return self.guard(lambda: features.seal_featureset(
                name, self.actor(who), body.note))

        @self.app.post(f"{api}/featuresets/{{name}}/transfer", tags=["features"])
        def transfer_set(request: Request, name: str, body: TransferIn):
            who = self.authorise(request, "featureset:define")
            return self.guard(lambda: features.sets.transfer(
                name, body.to, self.actor(who), body.reason))

        @self.app.put(f"{api}/featuresets/{{name}}/policy", tags=["features"])
        def set_policy(request: Request, name: str, body: PolicyIn):
            """Attach default retrieval behaviour. A request may still override."""
            who = self.authorise(request, "featureset:define")
            return self.guard(lambda: features.sets.set_policy(
                name, body.defaults, self.actor(who)))

        @self.app.delete(f"{api}/featuresets/{{name}}", tags=["features"])
        def destroy_set(request: Request, name: str):
            """Remove an ephemeral featureset — unless something pinned it."""
            who = self.authorise(request, "featureset:define")
            # The same ordering as a feature: the register's own rule about
            # what kind of thing this is, then what refers to it.
            row = self.guard(lambda: features.sets.require(name))
            if row.get("ephemeral"):
                self.guard(lambda: self.ctx["references"].refuse_if_referenced(
                    "featureset", name, label=f"featureset '{name}'"))
            return self.guard(lambda: features.sets.destroy(
                name, "asked for", self.actor(who)))

        @self.app.post(f"{api}/featuresets/{{name}}/versions", status_code=201,
                       tags=["features"])
        def publish(request: Request, name: str, body: VersionIn):
            """Fill the schema with exact, pinned constituents."""
            who = self.authorise(request, "featureset:publish")
            return self.guard(lambda: features.publish_featureset(
                name, body.bindings, body.label, body.note, self.actor(who)))

        @self.app.get(f"{api}/featuresets/{{name}}/versions/{{version}}",
                      tags=["features"])
        def plan(request: Request, name: str, version: int):
            """Everything an engine needs to assemble this set, in one document."""
            self.authorise(request, "feature:read")
            return self.guard(lambda: features.featureset_plan(name, version))

        @self.app.get(f"{api}/featuresets/{{name}}/versions/{{version}}/restatements",
                      tags=["features"])
        def restatements(request: Request, name: str, version: int):
            """Whether anything underneath this version has been written to since.

            The version still reads the bytes it pinned — that is what the pin is
            for. This answers the neighbouring question a reviewer actually asks
            before comparing two runs: has the ground moved.
            """
            self.authorise(request, "feature:read")
            return self.guard(lambda: features.restatements(name, version))

        @self.app.post(f"{api}/featuresets/{{name}}/roll-forward",
                       status_code=201, tags=["features"])
        def roll_forward(request: Request, name: str):
            """Take up newer view versions on purpose, and see what moved."""
            who = self.authorise(request, "featureset:publish")
            return self.guard(lambda: features.roll_forward(name, self.actor(who)))

        @self.app.post(f"{api}/featuresets/{{name}}/training-sets",
                       status_code=201, tags=["features"])
        def assemble(request: Request, name: str, body: AssembleIn):
            """Assemble a PIT-correct training set from a pinned version.

            The set supplies the columns; the caller supplies the spine and the
            as_of. A snapshot built this way names the featureset version, so a
            fit warrant may pin the snapshot and recompute nothing.
            """
            who = self.authorise(request, "feature:assemble")
            return self.guard(lambda: features.build_from_featureset(
                name, body.version, body.spine, body.as_of, body.name,
                self.actor(who)))

        # --------------------------------------------------------------- parameters
        @self.app.get(f"{api}/parameter-provenance", tags=["parameters"])
        def provenance(request: Request):
            self.principal(request)
            return {"provenance": [{"kind": k, "means": v}
                                   for k, v in PROVENANCE_MEANING.items()]}

        # Deliberately not nested under /models/{name:path}: that converter is
        # greedy and would swallow the trailing segment. A urn query parameter
        # is unambiguous and does not depend on registration order.
        @self.app.get(f"{api}/parameters", tags=["parameters"])
        def list_parameters(request: Request, urn: str, semver: str):
            """What this version may run on, and whether anything is approved."""
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: {
                **parameters.status(urn, semver),
                "parameter_sets": parameters.for_version(urn, semver)})

        @self.app.post(f"{api}/parameters", status_code=201, tags=["parameters"])
        def record(request: Request, body: ParametersIn):
            """Take delivery of an inhabitant of P, under the warrant that made it."""
            urn = body.urn
            model = self.guard(lambda: registry.require(urn))
            who = self.authorise(request, "parameter:record", model=model)
            return self.guard(lambda: parameters.record(
                urn, body.semver, body.name, body.kind, body.values,
                body.provenance, body.diagnostics, body.featureset,
                body.featureset_version, body.window, body.as_of,
                body.snapshot_id, body.warrant_id, body.values_uri, body.note,
                self.actor(who)))

        @self.app.post(f"{api}/parameter-fits", status_code=201,
                       tags=["parameters"])
        def fit(request: Request, body: FitIn):
            """Fit this version from a snapshot, and record what came out.

            The one route that produces a parameter set rather than taking
            delivery of one. It resolves a fit warrant first and reads the
            training set second, so a read never happens under an authority that
            turns out not to exist; and the result lands PROPOSED, so the person
            who ran the fit still cannot be the person who approves it.
            """
            fitting = self.ctx.get("fitting")
            if fitting is None:
                raise HTTPException(501, {
                    "error": "no_captive_engine",
                    "detail": "this instance runs no captive engine, so it can "
                              "record a fit performed elsewhere but cannot "
                              "perform one",
                    "remediation": "enable execution.captive, or POST the "
                                   "parameters to /parameters under the warrant "
                                   "that produced them"})
            # Stripped, like every other warrant-facing route. Without it a
            # caller pinning `…@1.0.0` — which is the ordinary way to name the
            # version being fitted — is refused `registry_refused` for a model
            # that exists.
            model = self.guard(
                lambda: registry.require(strip_qualifier(body.urn)))
            who = self.authorise(request, "parameter:record", model=model)
            return self.guard(lambda: fitting.fit(
                body.urn, body.snapshot_id, body.environment, body.principal,
                body.declared_use, body.window, body.name, body.kind,
                body.note, self.actor(who)))

        @self.app.get(f"{api}/parameter-sets/{{parameter_set_id}}", tags=["parameters"])
        def read(request: Request, parameter_set_id: str):
            self.authorise(request, "model:read")
            return self.guard(lambda: parameters.require(parameter_set_id))

        @self.app.post(f"{api}/parameter-sets/{{parameter_set_id}}/review",
                       tags=["parameters"])
        def review(request: Request, parameter_set_id: str, body: ReviewIn):
            """A parameter set changes behaviour, so it is approved like a version."""
            who = self.authorise(
                request, "parameter:approve",
                model=self.model_behind(parameters.get(parameter_set_id)))
            actor = self.actor(who)
            return self.guard(
                lambda: parameters.approve(parameter_set_id, actor, body.note)
                if body.accept
                else parameters.reject(parameter_set_id, actor, body.note))

        # ------------------------------------------------------------- runs
        @self.app.get(f"{api}/runs/vocabulary", tags=["parameters"])
        def run_vocabulary(request: Request):
            """The verbs, the states and what MAYA does not do."""
            self.authorise(request, "model:read")
            from core.parameters.runs import Runs
            return Runs.describe()

        @self.app.get(f"{api}/runs", tags=["parameters"])
        def runs(request: Request, reference: Optional[str] = None,
                 now: Optional[float] = None):
            """Every top-level run, lost first — or one of them."""
            self.authorise(request, "model:read",
                           estate_wide="reading the run register")
            engine = self.ctx["runs"]
            if reference is None:
                return self.guard(lambda: engine.across_the_estate(now=now))
            return self.guard(lambda: engine.read(reference, now=now))

        @self.app.post(f"{api}/runs", status_code=201, tags=["parameters"])
        def open_run(request: Request, body: RunIn):
            """Declare a run before it happens.

            A run recorded only on success is a register of successes, and the
            run a supervisor asks about is the one that consumed a warrant,
            read a snapshot of somebody's data and vanished.
            """
            model = (self.guard(lambda: self.ctx["registry"].require(body.urn))
                     if body.urn else None)
            who = self.authorise(request, "parameter:record", model=model) \
                if model else self.authorise(
                    request, "parameter:record",
                    estate_wide="declaring a run against no model")
            return self.guard(lambda: self.ctx["runs"].open(
                body.reference, verb=body.verb, urn=body.urn,
                semver=body.semver, warrant_id=body.warrant_id,
                parent=body.parent, purpose=body.purpose,
                resource_profile=body.resource_profile,
                environment=body.environment, inputs=body.inputs,
                hyperparameters=body.hyperparameters, seeds=body.seeds,
                log_uri=body.log_uri, expected_seconds=body.expected_seconds,
                actor=self.actor(who)))

        @self.app.post(f"{api}/runs/{{reference}}/close", tags=["parameters"])
        def close_run(request: Request, reference: str, body: CloseRunIn):
            """Take delivery of what a run produced."""
            run = self.guard(lambda: self.ctx["runs"].require(reference))
            model = self.model_behind(run)
            who = self.authorise(request, "parameter:record", model=model) \
                if model else self.authorise(
                    request, "parameter:record",
                    estate_wide="closing a run against no model")
            return self.guard(lambda: self.ctx["runs"].close(
                reference, state=body.state, metrics=body.metrics,
                parameter_set_id=body.parameter_set_id, cost=body.cost,
                note=body.note, actor=self.actor(who)))

        @self.app.get(f"{api}/runs/{{reference}}/search", tags=["parameters"])
        def run_search(request: Request, reference: str,
                       now: Optional[float] = None):
            """A parent and its children — and what the ranking hides.

            The best of four hundred draws from a null distribution looks
            excellent. The count of children is what makes that visible, and
            MAYA does not select a winner: choosing one is approving a
            parameter set, which is an act with a person's name on it.
            """
            self.authorise(request, "model:read",
                           estate_wide="reading a search and its children")
            return self.guard(
                lambda: self.ctx["runs"].search(reference, now=now))

        # ---------------------------------------------------------- retraining
        @self.app.get(f"{api}/retraining/triggers", tags=["parameters"])
        def retrain_triggers(request: Request):
            """The triggers, the tier ceiling and the policy lifetime."""
            self.authorise(request, "model:read")
            from core.parameters.retraining import Retraining
            return Retraining.triggers()

        @self.app.get(f"{api}/retraining", tags=["parameters"])
        def retraining(request: Request, urn: Optional[str] = None,
                       now: Optional[float] = None):
            """Whether a re-fit is due, and the standing approval if any."""
            engine = self.ctx["retraining"]
            if urn is None:
                self.authorise(request, "model:read",
                               estate_wide="reading every retraining policy")
                return self.guard(lambda: engine.across_the_estate(now=now))
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: engine.due(urn, now=now))

        @self.app.post(f"{api}/retraining", status_code=201,
                       tags=["parameters"])
        def declare_policy(request: Request, urn: str,
                           body: RetrainPolicyIn):
            """Write the standing policy. Approval is a separate act."""
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            who = self.authorise(request, "parameter:approve", model=model)
            return self.guard(lambda: self.ctx["retraining"].declare(
                urn, triggers=body.triggers, tolerance=body.tolerance,
                auto_accept=body.auto_accept, rationale=body.rationale,
                expires_at=body.expires_at, actor=self.actor(who)))

        @self.app.post(f"{api}/retraining/approve", tags=["parameters"])
        def approve_policy(request: Request, urn: str):
            """Approve a standing policy. Never by the person who wrote it."""
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            who = self.authorise(request, "parameter:approve", model=model)
            return self.guard(lambda: self.ctx["retraining"].approve(
                urn, actor=self.actor(who)))

        @self.app.post(f"{api}/retraining/revoke", tags=["parameters"])
        def revoke_policy(request: Request, urn: str, reason: str = ""):
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            who = self.authorise(request, "parameter:approve", model=model)
            return self.guard(lambda: self.ctx["retraining"].revoke(
                urn, reason, actor=self.actor(who)))
