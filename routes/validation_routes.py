"""
MAYA — validation episodes and the findings register.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The register is not a log. An open blocking finding refuses an alias move and
refuses warrant resolution, so these endpoints are a control surface rather than a
record-keeping one.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from pydantic import Field

from core.validation.common import TIER_VERDICT_MEANING, TIER_VERDICTS
from core.authz.common import same_person
from routes.base import Body, Routes


class OpenValidationIn(Body):
    urn: str
    semver: str
    validators: List[str]
    kind: str = "initial"
    scope: List[str] = Field(default_factory=list)
    plan: Dict[str, Any] = Field(default_factory=dict)
    snapshot_id: Optional[str] = None
    due_at: Optional[float] = None


class RecordTestIn(Body):
    test_key: str
    left: List[float]
    right: List[float]
    threshold: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    slice: Dict[str, Any] = Field(default_factory=dict)


class ConcludeIn(Body):
    outcome: str
    conditions: List[str] = Field(default_factory=list)
    #: What the episode found about the model's RISK TIER. Required, and with
    #: no default: SS1/23 1.3(e) asks that the tier be re-assessed during
    #: validation, and an episode concluded without a verdict reads exactly
    #: like one where the validator looked and agreed.
    tier_verdict: Optional[str] = None
    #: Mandatory when the verdict is not `remains_appropriate`. Saying the tier
    #: is wrong without saying why is not something anybody can act on.
    tier_note: str = ""


class FindingIn(Body):
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


class CloseFindingIn(Body):
    # Optional, and never trusted. The verifier is the authenticated caller; a
    # value here is accepted only to be checked against them, so a caller that
    # names somebody else is told plainly rather than silently ignored.
    verified_by: Optional[str] = None
    evidence: Dict[str, Any]


class ReplayIn(Body):
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
            who = self.authorise(
                request, "validation:record",
                model=self.model_behind(
                    self.guard(lambda: service.require(validation_id))))
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
                                 model=self.model_behind(episode),
                                 subject_id=episode["model_version_id"])
            return self.guard(lambda: service.conclude(
                validation_id, body.outcome, body.conditions,
                tier_verdict=body.tier_verdict, tier_note=body.tier_note,
                actor=self.actor(who)))

        @self.app.get(f"{api}/validation-plans", tags=["validation"])
        def validation_plan(request: Request, urn: str, semver: str,
                            scope: Optional[str] = None):
            """What a validation of this version must cover, and how deeply.

            Derived: the class says what the questions are — `L-15` already
            makes each one declare its conceptual soundness, outcomes and
            monitoring — and the tier says how much independence answering them
            takes. A catalogue of plans keyed by class would be a second copy
            of the fibres, and the two would disagree the first time either
            moved.

            With `scope`, a comma-separated list, this reports what that scope
            leaves out. A targeted revalidation is a real thing and this is not
            a refusal, but the omission has to be visible.
            """
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "validation:read", model=model)
            plans = self.ctx["validation_plans"]
            if scope is None:
                return self.guard(lambda: plans.propose(urn, semver))
            declared = [s.strip() for s in scope.split(",") if s.strip()]
            return self.guard(lambda: plans.check(urn, semver, declared))

        @self.app.get(f"{api}/validation-due", tags=["validation"])
        def validation_due(request: Request, urn: str):
            """Why this model is due for validation, if it is.

            Triggers rather than a calendar. A tier 4 model has no elapsed-time
            trigger at all — it is revalidated when something happens to it and
            not otherwise, which is the proportionality clause being used
            rather than quietly discarded.
            """
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "validation:read", model=model)
            return self.guard(lambda: self.ctx["validation_plans"].due(urn))

        @self.app.get(f"{api}/tier-verdicts", tags=["validation"])
        def tier_verdicts(request: Request):
            """The three a validator may reach about a model's tier, and what
            each one causes. Closed: not looking is not a verdict."""
            self.principal(request)
            return {"verdicts": [{"verdict": v, "means": TIER_VERDICT_MEANING[v]}
                                 for v in TIER_VERDICTS],
                    "detail": "concluding a validation requires one. SS1/23 "
                              "1.3(e) asks that the tier be re-assessed during "
                              "validation, and an episode with no verdict "
                              "reads exactly like one where the validator "
                              "looked and agreed"}

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

        @self.app.get(f"{api}/open-findings", tags=["findings"])
        def open_findings(request: Request):
            """Every open finding across the estate, scoped to the caller.

            A separate path rather than making `urn` optional on the one below,
            because the two answer different questions and a required parameter
            that becomes optional is how a caller ends up asking for one model
            and receiving all of them.

            This did not exist. `open_for` takes a single model and the endpoint
            below demands a `urn`, so an estate-wide list of what is outstanding
            could not be produced by any route in the product.
            """
            who = self.authorise(request, "finding:read")
            visible = self.ctx["authz"].visible(who, registry.list())
            by_id = {m["id"]: m for m in visible}
            rows = register.open_across(list(by_id))
            return {"open": len(rows),
                    "models": len({r["model_id"] for r in rows}),
                    "findings": [
                        {**r,
                         "urn": by_id[r["model_id"]]["urn"],
                         "model_name": by_id[r["model_id"]]["name"],
                         "tier": by_id[r["model_id"]]["tier"]}
                        for r in rows]}

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
                                 model=self.model_of(finding["model_id"]),
                                 subject_id=finding["model_id"], about=finding_id)
            # The verifier is WHO IS ASKING. It used to be a request field, so
            # the owner of a blocking finding could close their own by naming
            # somebody else -- and that forged attribution went into the
            # permanent evidence chain. The register's owner/verifier check was
            # correct all along; it was comparing against a value the caller
            # invented.
            verifier = self.actor(who)
            if body.verified_by and not same_person(body.verified_by, verifier):
                raise HTTPException(403, {
                    "error": "verifier_not_self",
                    "detail": f"a closure is attributed to whoever performs it, "
                              f"and this one names '{body.verified_by}' rather "
                              f"than {verifier}",
                    "remediation": "omit verified_by, or have that person close it"})
            return self.guard(lambda: register.close(
                finding_id, verifier, body.evidence, actor=verifier))
