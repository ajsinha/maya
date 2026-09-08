"""
MAYA — feature platform endpoints.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


from fastapi import Request
from pydantic import Field

from core.features.common import FeatureError
from routes.base import Body, Routes


class ServingAttestationIn(Body):
    """What an engine says it read. `served` is view name to namespace."""
    urn: str
    semver: str
    served: Dict[str, str]
    warrant_id: Optional[str] = None
    descriptor_id: Optional[str] = None


class FeatureIn(Body):
    name: str
    entity: str
    dtype: str
    description: str
    owner: str
    business_definition: str = ""
    source_system: str = ""
    sensitivity: str = "internal"
    pii: bool = False
    protected_basis: bool = False
    proxy_risk: str = "none"
    # A feature is not always a number: a shape of [10] is a vector, [10, 10] a
    # matrix, and the components name the first axis so composition can speak
    # about a tenor rather than about an index.
    shape: Any = None
    components: Optional[List[str]] = None
    composes: Optional[List[Any]] = None
    operations: Optional[List[Dict[str, Any]]] = None
    defaults: Optional[Dict[str, Any]] = None
    ephemeral: bool = False
    ttl_days: Optional[float] = None


class ViewIn(Body):
    name: str
    entity: str
    owner: str
    features: List[str]
    description: str = ""


class MaterialiseIn(Body):
    rows: List[Dict[str, Any]]


class ContractIn(Body):
    model_version_id: str
    items: List[Dict[str, Any]]


class TrainingSetIn(Body):
    name: str
    spine: List[Dict[str, Any]]
    views: List[Dict[str, Any]]
    as_of: float
    valid_time_bound: bool = True
    transaction_time_bound: bool = True


class SourceIn(Body):
    """Where a feature view's values come from."""

    kind: str = Field(description="sql, file, s3 or gcs")
    locator: str = Field(description="a connection URL, a path, or an s3:// URI")
    statement: str = Field(
        default="", description="for a SQL source: the SELECT that produces "
                                "the rows. Anything that is not a read is "
                                "refused before it is stored")
    format: str = Field(
        default="", description="csv, jsonl, parquet or arrow. Inferred from "
                                "the locator's suffix when it has one")
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="column mapping under `columns`, plus whatever the "
                    "connector needs — a CSV `delimiter`, an S3 `region`")
    credential_ref: Optional[str] = Field(
        default=None, description="the NAME of a credential this deployment "
                                  "has configured. Never the credential")


class SourceAmendIn(Body):
    fields: Dict[str, Any] = Field(
        description="locator, statement, format, options, credential_ref "
                    "or enabled")


class RetireSourceIn(Body):
    reason: str


class FeatureRoutes(Routes):
    def register(self) -> None:
        f = self.ctx["features"]

        @self.app.get(f"{self.api}/features", tags=["features"])
        def list_features(request: Request, entity: Optional[str] = None):
            self.authorise(request, "feature:read")
            # `f.features` does not exist — this raised AttributeError and
            # returned 500 on every call. `list_features` is the accessor, and
            # it filters, so the entity argument keeps working.
            return {"features": f.list_features(**({"entity": entity}
                                                   if entity else {}))}

        @self.app.post(f"{self.api}/features", status_code=201, tags=["features"])
        def define(request: Request, body: FeatureIn):
            who = self.authorise(request, "feature:define")
            near = [x["name"] for x in f.similar(body.name, body.description)]
            # The actor is who is CREATING it, which is a different fact from
            # the owner they nominate and is recorded separately.
            return {"feature": self.guard(
                        lambda: f.define(**body.model_dump(),
                                         actor=self.actor(who))),
                    "possible_duplicates": near}

        @self.app.post(f"{self.api}/features/{{name}}/certify", tags=["features"])
        def certify(request: Request, name: str, level: str = "certified"):
            self.authorise(request, "feature:certify")
            return self.guard(lambda: f.certify(name, level))

        def _sources():
            """The source registry, or a refusal naming why there is not one.

            Sources are optional: a deployment that forbids outbound
            connections leaves them off rather than configuring them into
            uselessness. Refusing HERE, once, means every route says the same
            thing instead of five of them raising AttributeError.
            """
            if f.sources is None:
                raise FeatureError(
                    "this instance does not read feature values from external "
                    "sources",
                    remediation="upload the values, or enable sources in the "
                                "deployment's configuration")
            return f.sources

        @self.app.get(f"{self.api}/feature-views", tags=["features"])
        def list_views(request: Request):
            self.authorise(request, "feature:read")
            # `ViewManager` has no `many`; the catalogue lists, the manager
            # resolves. 500 on every call before this.
            return {"views": f.views.views.many()}

        @self.app.post(f"{self.api}/feature-views", status_code=201, tags=["features"])
        def create_view(request: Request, body: ViewIn):
            self.authorise(request, "feature:define")
            return self.guard(lambda: f.create_view(
                body.name, body.entity, body.owner, body.features, body.description))

        @self.app.post(f"{self.api}/feature-views/{{name}}/materialise", status_code=201,
                       tags=["features"])
        def materialise(request: Request, name: str, body: MaterialiseIn):
            self.authorise(request, "feature:materialise")
            return self.guard(lambda: f.materialise(name, body.rows))

        # ------------------------------------------------ where values come from
        #
        # A source is PULLED, never read through. MAYA fetches and writes what
        # it got into its own Delta as a new version, so integrity, versioning
        # and the two clocks stay MAYA's. Serving a model off somebody's
        # warehouse table would give away point-in-time correctness, because a
        # table overwritten since March cannot say what was knowable in March —
        # it will answer something, which is worse than refusing.

        @self.app.get(f"{self.api}/feature-views/{{name}}/source", tags=["features"])
        def read_source(request: Request, name: str):
            """Where this view reads from, and what its last pull did."""
            self.authorise(request, "feature:read")
            return self.guard(lambda: {"source": _sources().get(name)})

        @self.app.put(f"{self.api}/feature-views/{{name}}/source",
                      status_code=201, tags=["features"])
        def declare_source(request: Request, name: str, body: SourceIn):
            """Declare where a view's values come from. Does not pull.

            Declaring and pulling are separate acts: one says where the data
            lives and is a decision somebody signs for, the other moves bytes
            and happens on a schedule.
            """
            who = self.authorise(request, "feature:define")
            return self.guard(lambda: _sources().declare(
                name, body.kind, body.locator, statement=body.statement,
                fmt=body.format, options=body.options,
                credential_ref=body.credential_ref, actor=self.actor(who)))

        @self.app.post(f"{self.api}/feature-views/{{name}}/source/amend",
                       tags=["features"])
        def amend_source(request: Request, name: str, body: SourceAmendIn):
            who = self.authorise(request, "feature:define")
            return self.guard(lambda: _sources().amend(
                name, body.fields, actor=self.actor(who)))

        @self.app.post(f"{self.api}/feature-views/{{name}}/source/retire",
                       tags=["features"])
        def retire_source(request: Request, name: str, body: RetireSourceIn):
            """Stop reading from it. The versions it produced stand."""
            who = self.authorise(request, "feature:define")
            return self.guard(lambda: _sources().retire(
                name, body.reason, actor=self.actor(who)))

        @self.app.get(f"{self.api}/feature-views/{{name}}/source/preview",
                      tags=["features"])
        def preview_source(request: Request, name: str, limit: int = 20):
            """Read a few rows and say what came back. Writes NOTHING.

            The only way to find out that the source calls the clock `asof`
            without first producing a version that says so.
            """
            self.authorise(request, "feature:read")
            return self.guard(lambda: _sources().preview(name, limit=limit))

        @self.app.post(f"{self.api}/feature-views/{{name}}/source/pull",
                       status_code=201, tags=["features"])
        def pull_source(request: Request, name: str):
            """Fetch everything the source has, as a NEW version.

            A version, not an update: the previous one keeps serving exactly
            what it served, so a warrant pinned to it does not change meaning
            because somebody refreshed.
            """
            who = self.authorise(request, "feature:materialise")
            return self.guard(lambda: _sources().pull(name, actor=self.actor(who)))

        @self.app.get(f"{self.api}/feature-views/{{name}}/versions", tags=["features"])
        def versions(request: Request, name: str):
            self.authorise(request, "feature:read")
            # `f.views.one` and `f.view_versions` are both absent — 500 on
            # every call. `versions_of` is the accessor and it raises its own
            # refusal for an unknown view, which is a better 404 than this was.
            return {"versions": self.guard(lambda: f.views.versions_of(name))}

        @self.app.get(f"{self.api}/feature-views/{{name}}/versions/{{version}}/retirable",
                      tags=["features"])
        def retirable(request: Request, name: str, version: int):
            self.authorise(request, "feature:read")
            ok, pinned_by = self.guard(lambda: f.can_retire(name, version))
            return {"retirable": ok, "pinned_by": pinned_by}

        @self.app.post(f"{self.api}/feature-contracts", status_code=201, tags=["features"])
        def bind(request: Request, body: ContractIn):
            self.authorise(request, "feature:contract")
            return self.guard(lambda: f.bind_contract(body.model_version_id, body.items))

        @self.app.get(f"{self.api}/feature-contracts/{{model_version_id}}/namespaces",
                      tags=["features"])
        def namespaces(request: Request, model_version_id: str):
            self.authorise(request, "feature:read")
            """What serving MUST read. Law L-17 compares this to what it did read."""
            return {"namespaces": self.guard(
                lambda: f.serving_namespaces(model_version_id))}

        # ------------------------------------------------- L-17, the other half
        @self.app.post(f"{self.api}/serving-attestations", status_code=201,
                       tags=["features"])
        def attest_serving(request: Request, body: ServingAttestationIn):
            """Declare which feature namespaces a run actually read.

            `L-17` is contract–serving agreement, and MAYA cannot check it by
            looking: it does not own the online store and deliberately does not
            sit on the serving path. The engine knows what it read, so it says
            so and the platform compares against what the version's contract
            pins.

            This is an attestation, not an observation, and the difference is
            not rhetorical: it is evidence that somebody asserted something. It
            proves disagreement rather than agreement — and disagreement is the
            thing worth catching, because it is training–serving skew.

            Recorded whether it agrees or not. A refusal that left no row would
            lose exactly the event this exists for.
            """
            model = self.guard(lambda: self.ctx["registry"].require(body.urn))
            who = self.authorise(request, "monitor:observe", model=model)
            return self.guard(lambda: self.ctx["serving"].attest(
                body.urn, body.semver, body.served, body.warrant_id,
                body.descriptor_id, actor=self.actor(who)))

        @self.app.get(f"{self.api}/serving-attestations", tags=["features"])
        def serving_agreement(request: Request, urn: str, semver: str):
            """Whether `L-17` holds for this version, and on what evidence.

            Three answers, not two: `agrees`, `disagrees`, and `unattested` —
            which is the absence of an answer. Reporting silence as agreement
            would be the failure this platform is written against.
            """
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "monitor:read", model=model)
            return self.guard(
                lambda: self.ctx["serving"].agreement(urn, semver))

        @self.app.post(f"{self.api}/training-sets", status_code=201, tags=["features"])
        def training_set(request: Request, body: TrainingSetIn):
            self.authorise(request, "feature:assemble")
            return self.guard(lambda: f.build_training_set(
                body.name, body.spine, body.views, body.as_of,
                body.valid_time_bound, body.transaction_time_bound))
