"""
MAYA — validation episodes and the findings register.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The register is not a log. An open blocking finding refuses an alias move and
refuses warrant resolution, so these endpoints are a control surface rather than a
record-keeping one.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from fastapi import Request
from pydantic import BaseModel, Field

from routes.base import Routes


class OpenValidationIn(BaseModel):
    urn: str
    semver: str
    validators: List[str]
    kind: str = "initial"
    scope: List[str] = Field(default_factory=list)
    plan: Dict[str, Any] = Field(default_factory=dict)
    snapshot_id: Optional[str] = None
    due_at: Optional[float] = None


class RecordTestIn(BaseModel):
    test_key: str
    left: List[float]
    right: List[float]
    threshold: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    slice: Dict[str, Any] = Field(default_factory=dict)


class ConcludeIn(BaseModel):
    outcome: str
    conditions: List[str] = Field(default_factory=list)


class FindingIn(BaseModel):
    urn: str
    severity: str
    title: str
    owner: str
    description: str = ""
    category: str = "general"
    source: str = "validation"
    validation_id: Optional[str] = None
    affected_component: Optional[str] = None
    blocking: Optional[bool] = None


class CloseFindingIn(BaseModel):
    verified_by: str
    evidence: Dict[str, Any]


class ReplayIn(BaseModel):
    data: Dict[str, List[List[float]]] = Field(
        default_factory=dict,
        description="test_key -> [left, right]; omit a key to report it as skipped")


class ValidationRoutes(Routes):
    def register(self) -> None:
        service = self.ctx["validation"]
        register = self.ctx["findings"]
        catalogue = self.ctx["test_catalogue"]
        replayer = self.ctx["replayer"]
        registry = self.ctx["registry"]
        api = self.api

        # ------------------------------------------------------------ catalogue
        @self.app.get(f"{api}/tests", tags=["validation"])
        def list_tests(request: Request):
            self.authorise(request, "validation:read")
            """The registered test catalogue. A validation may only run these."""
            return {"tests": catalogue.describe()}

        # ----------------------------------------------------------- validations
        @self.app.post(f"{api}/validations", status_code=201, tags=["validation"])
        def open_validation(request: Request, body: OpenValidationIn):
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "validation:open", model=model)
            return self.guard(lambda: service.open(
                body.urn, body.semver, body.kind, body.validators, body.scope,
                body.plan, body.due_at, body.snapshot_id, actor=self.actor(who)))

        @self.app.get(f"{api}/validations/{{validation_id}}", tags=["validation"])
        def get_validation(request: Request, validation_id: str):
            self.authorise(request, "validation:read")
            v = service.get(validation_id)
            if not v:
                raise self.not_found(f"no validation {validation_id}")
            return {**v, "summary": service.summary(validation_id),
                    "results": service.results_for(validation_id)}

        @self.app.post(f"{api}/validations/{{validation_id}}/results",
                       status_code=201, tags=["validation"])
        def record_result(request: Request, validation_id: str, body: RecordTestIn):
            who = self.authorise(request, "validation:record")
            return self.guard(lambda: service.record(
                validation_id, body.test_key, body.left, body.right,
                body.threshold, body.parameters, body.slice, actor=self.actor(who)))

        @self.app.post(f"{api}/validations/{{validation_id}}/conclude", tags=["validation"])
        def conclude(request: Request, validation_id: str, body: ConcludeIn):
            episode = self.guard(lambda: service.require(validation_id))
            # Segregation is checked against the VERSION: the evidence chain
            # recorded who created it, and that person may not conclude its
            # challenge however their roles are arranged.
            who = self.authorise(request, "validation:conclude",
                                 subject_id=episode["model_version_id"])
            return self.guard(lambda: service.conclude(
                validation_id, body.outcome, body.conditions, actor=self.actor(who)))

        @self.app.post(f"{api}/validations/{{validation_id}}/replay", tags=["validation"])
        def replay(request: Request, validation_id: str, body: ReplayIn):
            self.authorise(request, "validation:read")
            """Recompute the recorded tests and compare digests."""
            def provider(test_key: str, _slice: Dict[str, Any]):
                pair = body.data.get(test_key)
                return (pair[0], pair[1]) if pair and len(pair) == 2 else None
            return self.guard(lambda: replayer.replay(validation_id, provider))

        @self.app.post(f"{api}/validations/{{validation_id}}/replay-from-storage",
                       tags=["validation"])
        def replay_stored(request: Request, validation_id: str):
            """Replay by re-reading the snapshot the episode was pinned to.

            Nothing is supplied by the caller, so a mismatch is about the test
            rather than about who handed over which file. An episode that pins no
            snapshot reports every test as skipped, with the reason.
            """
            self.authorise(request, "validation:read")
            return self.guard(lambda: replayer.from_storage(validation_id))

        @self.app.get(f"{api}/validations/{{validation_id}}/replayable",
                      tags=["validation"])
        def replayable(request: Request, validation_id: str):
            """What a replay would read, and whether the ground under it moved."""
            self.authorise(request, "validation:read")
            episode = self.guard(lambda: service.require(validation_id))
            if not episode.get("snapshot_id"):
                return {"validation_id": validation_id, "readable": False,
                        "detail": "this episode pins no dataset snapshot, so it "
                                  "cannot be replayed without the data being "
                                  "supplied"}
            return self.guard(
                lambda: {"validation_id": validation_id,
                         **replayer.storage.describe(episode["snapshot_id"])})

        # -------------------------------------------------------------- findings
        @self.app.post(f"{api}/findings", status_code=201, tags=["findings"])
        def raise_finding(request: Request, body: FindingIn):
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "finding:raise", model=model)
            return self.guard(lambda: register.raise_finding(
                model["id"], body.severity, body.title, body.owner, body.description,
                body.category, body.source, None, body.validation_id,
                body.affected_component, body.blocking, actor=self.actor(who)))

        @self.app.get(f"{api}/findings", tags=["findings"])
        def model_findings(request: Request, urn: str):
            """Findings for one model.

            A query parameter rather than a path nested under /models, because
            the model path segment is a greedy `:path` (URNs contain dots and
            slashes) and would otherwise swallow the suffix.
            """
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "finding:read", model=model)
            return {"model": model["urn"], "summary": register.summary(model["id"]),
                    "open": register.open_for(model["id"]),
                    "blocking": register.blocking_for(model["id"])}

        @self.app.post(f"{api}/findings/{{finding_id}}/close", tags=["findings"])
        def close_finding(request: Request, finding_id: str, body: CloseFindingIn):
            finding = self.guard(lambda: register.require(finding_id))
            # The evidence lives on the model, which is where a reader looks
            # for it; `about` narrows it to this finding.
            who = self.authorise(request, "finding:close",
                                 subject_id=finding["model_id"], about=finding_id)
            return self.guard(lambda: register.close(
                finding_id, body.verified_by, body.evidence, actor=self.actor(who)))
