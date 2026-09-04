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

from fastapi import Request
from pydantic import BaseModel

from core.features.expressions import describe as describe_language
from core.parameters import PROVENANCE_MEANING
from routes.base import Routes


class DerivedIn(BaseModel):
    name: str
    expression: str
    dtype: str = "numeric"
    description: str = ""
    evaluator: str = "internal"
    on_error: str = "null"
    note: str = ""


class FeaturesetIn(BaseModel):
    name: str
    entity: str
    slots: Dict[str, Any]
    label_slot: Optional[str] = None
    outcome_window_days: int = 0
    grain: str = ""
    description: str = ""


class VersionIn(BaseModel):
    bindings: Dict[str, Any]
    label: Optional[Dict[str, Any]] = None
    note: str = ""


class AssembleIn(BaseModel):
    version: int
    spine: list
    as_of: float
    name: Optional[str] = None


class ParametersIn(BaseModel):
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


class ReviewIn(BaseModel):
    accept: bool
    note: str = ""


class FeaturesetRoutes(Routes):
    def register(self) -> None:
        features, api = self.ctx["features"], self.api
        parameters, registry = self.ctx["parameters"], self.ctx["registry"]

        # ------------------------------------------------------- derived features
        @self.app.get(f"{api}/expression-language", tags=["features"])
        def language(request: Request):
            """What a derived feature may be written in. Deliberately small."""
            self.principal(request)
            return describe_language()

        @self.app.get(f"{api}/derived-features", tags=["features"])
        def list_derived(request: Request):
            self.authorise(request, "feature:read")
            return {"derived": features.derived.list()}

        @self.app.post(f"{api}/derived-features", status_code=201, tags=["features"])
        def define_derived(request: Request, body: DerivedIn):
            """Declare Z = f(X, Y). Corrections are new definition versions."""
            who = self.authorise(request, "feature:define")
            return self.guard(lambda: features.define_derived(
                body.name, body.expression, body.dtype, body.description,
                self.actor(who), body.evaluator, body.on_error, body.note,
                self.actor(who)))

        @self.app.get(f"{api}/derived-features/{{name}}/lineage", tags=["features"])
        def lineage(request: Request, name: str):
            """Everything this feature rests on, and everything resting on it."""
            self.authorise(request, "feature:read")
            return self.guard(lambda: {
                "feature": name,
                "rests_on": features.lineage(name),
                "depended_on_by": features.dependants_of(name)})

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
                body.description, self.actor(who)))

        @self.app.get(f"{api}/featuresets/{{name}}", tags=["features"])
        def read_set(request: Request, name: str):
            self.authorise(request, "feature:read")
            return self.guard(lambda: {
                **features.sets.require(name),
                "versions": [{"version": v["version"], "digest": v["digest"],
                              "created_at": v["created_at"], "note": v["note"]}
                             for v in features.sets.versions_of(name)]})

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

        @self.app.get(f"{api}/parameter-sets/{{parameter_set_id}}", tags=["parameters"])
        def read(request: Request, parameter_set_id: str):
            self.authorise(request, "model:read")
            return self.guard(lambda: parameters.require(parameter_set_id))

        @self.app.post(f"{api}/parameter-sets/{{parameter_set_id}}/review",
                       tags=["parameters"])
        def review(request: Request, parameter_set_id: str, body: ReviewIn):
            """A parameter set changes behaviour, so it is approved like a version."""
            who = self.authorise(request, "parameter:approve")
            actor = self.actor(who)
            return self.guard(
                lambda: parameters.approve(parameter_set_id, actor, body.note)
                if body.accept
                else parameters.reject(parameter_set_id, actor, body.note))
