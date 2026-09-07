"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Validation episodes: plan, measure, conclude.

Three rules are enforced here rather than trusted to process.

**Independence.** A validator may not be the person who built the version. This
is SS1/23 Principle 4 and SR 26-2's effective challenge in the only form a system
can check: the attestation is recorded, and a violation is refused at the point
of opening rather than noticed in an audit.

**No approval over failures.** A validation with a failed test cannot conclude
``approved``. It can conclude ``approved_with_conditions`` — which forces the
conditions to be written down — or ``rejected``. The one thing it cannot do is
quietly pass.

**No approval over blocking findings.** If something blocking is open against the
model, approval is refused until it is closed.

Results are immutable once the episode completes, because a validation that can
be edited after the fact is not evidence of anything.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.ports import BlockingSource
from core.registry import ModelRegistry
from core.validation.catalogue import TestCatalogue
from core.authz.common import bare_name, same_person
from core.validation.common import KINDS, OUTCOMES, ValidationError
from db import TestResultRepository, ValidationRepository

TERMINAL = ("completed",)


class ValidationService:
    """Opens validations, records measurements, and concludes them."""

    def __init__(self, validations: ValidationRepository, results: TestResultRepository,
                 registry: ModelRegistry, catalogue: TestCatalogue,
                 evidence: EvidenceEngine, blocking: Optional[BlockingSource] = None):
        self.validations, self.results = validations, results
        self.registry, self.catalogue = registry, catalogue
        self.evidence, self.blocking = evidence, blocking
        # The principal register, for resolving named validators. Optional so
        # the service can be built before it exists; when absent, `_resolve`
        # cannot run and says so rather than passing silently.
        self.principals: Any = None

    # ------------------------------------------------------------------- open
    def open(self, urn: str, semver: str, kind: str = "initial",
             validators: Optional[Sequence[str]] = None,
             scope: Optional[List[str]] = None, plan: Optional[Dict[str, Any]] = None,
             due_at: Optional[float] = None, snapshot_id: Optional[str] = None,
             actor: str = "system") -> Dict[str, Any]:
        if kind not in KINDS:
            raise ValidationError(f"unknown validation kind '{kind}'; "
                                  f"expected one of {', '.join(KINDS)}")
        m = self.registry.require(urn)
        version = self.registry.version(urn, semver)
        if not version:
            raise ValidationError(f"no version {semver} for {urn}")
        validators = list(validators or [])
        if not validators:
            raise ValidationError("a validation needs at least one named validator")
        # Resolved against the register rather than accepted as prose. This was
        # free text: a validation naming `person/nobody.at.all` was accepted,
        # recorded and concluded, and the independence check compared that
        # string against the builder's username — so an independence test on a
        # name that resolves to nobody passes by construction.
        self._resolve(validators)

        independence = self.attest(validators, version)
        if not independence["independent"]:
            raise ValidationError(
                f"independence failed: {independence['reason']}; effective challenge "
                "requires a validator who did not build the version")

        row = {"model_id": m["id"], "model_version_id": version["id"], "kind": kind,
               "scope": scope or [], "plan": plan or {}, "validators": validators,
               "independence": independence, "status": "in_progress", "outcome": None,
               "conditions": [], "snapshot_id": snapshot_id, "started_at": time.time(),
               "completed_at": None, "due_at": due_at}
        with self.evidence.recording():
            self.validations.add(row)
            self.evidence.append("validation_opened", "version", version["id"],
                                 {"validation_id": row["id"], "kind": kind,
                                  "validators": validators}, actor=actor)
        return self.validations.one(id=row["id"])

    def _resolve(self, validators: Sequence[str]) -> None:
        """Every named validator must be a principal who exists and is active.

        Refused rather than warned: a validation is a record of who challenged
        the model, and a name nobody can look up is not that record.
        """
        if self.principals is None:            # not wired; nothing to check
            return
        unknown, inactive = [], []
        for name in validators:
            row = self.principals.get(bare_name(name))
            if row is None:
                unknown.append(name)
            elif row.get("status") != "active":
                inactive.append(name)
        if unknown:
            raise ValidationError(
                f"no principal is registered for {', '.join(sorted(unknown))}; "
                f"a validation names who challenged the model, and a name "
                f"nobody can look up is not a record of that")
        if inactive:
            raise ValidationError(
                f"{', '.join(sorted(inactive))} "
                f"{'is' if len(inactive) == 1 else 'are'} not active, so "
                f"cannot be recorded as having challenged this version")

    @staticmethod
    def attest(validators: Sequence[str], version: Dict[str, Any]) -> Dict[str, Any]:
        """Record who validated and whether they were independent of the build."""
        builder = version.get("created_by")
        # `same_person`, not `==`. Production writes created_by as the bare
        # authenticated username and validators are conventionally written
        # `person/...`, so the two spellings of one human never matched and
        # effective challenge -- the control this whole module exists for --
        # was inert over HTTP. The unit test passed because it constructed the
        # version with an actor the route layer never produces.
        conflicted = [v for v in validators if same_person(v, builder)]
        return {"independent": not conflicted, "validators": list(validators),
                "version_created_by": builder,
                "reason": (f"{', '.join(conflicted)} built this version"
                           if conflicted else "no validator built this version")}

    # ----------------------------------------------------------------- record
    def record(self, validation_id: str, test_key: str, left: Sequence, right: Sequence,
               threshold: Optional[Dict[str, Any]] = None,
               parameters: Optional[Dict[str, Any]] = None,
               slice_: Optional[Dict[str, Any]] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Run one catalogue test against supplied data and record the result."""
        v = self.require(validation_id)
        if v["status"] in TERMINAL:
            raise ValidationError(
                f"validation {validation_id} is complete; its results are immutable")
        outcome = self.catalogue.run(test_key, left, right, threshold, parameters, slice_)
        row = {"validation_id": validation_id, **outcome.as_row(),
               "computed_at": time.time()}
        with self.evidence.recording():
            self.results.add(row)
            self.evidence.append("test_result_recorded", "version", v["model_version_id"],
                                 {"validation_id": validation_id, "test_key": test_key,
                                  "value": outcome.value, "passed": outcome.passed,
                                  "digest": row["digest"]}, actor=actor)
        return self.results.one(id=row["id"])

    def results_for(self, validation_id: str) -> List[Dict[str, Any]]:
        return self.results.many(validation_id=validation_id)

    # ---------------------------------------------------------------- conclude
    def conclude(self, validation_id: str, outcome: str,
                 conditions: Optional[List[str]] = None,
                 actor: str = "system") -> Dict[str, Any]:
        if outcome not in OUTCOMES:
            raise ValidationError(f"unknown outcome '{outcome}'; "
                                  f"expected one of {', '.join(OUTCOMES)}")
        v = self.require(validation_id)
        if v["status"] in TERMINAL:
            raise ValidationError(f"validation {validation_id} is already concluded "
                                  f"as '{v['outcome']}'")
        failed = [r for r in self.results_for(validation_id) if not r["passed"]]
        conditions = list(conditions or [])

        if outcome == "approved":
            self._check_approvable(v, failed, conditions)

        with self.evidence.recording():
            self.validations.set({"status": "completed", "outcome": outcome,
                                  "conditions": conditions, "completed_at": time.time()},
                                 id=validation_id)
            self.evidence.append("validation_concluded", "version", v["model_version_id"],
                                 {"validation_id": validation_id, "outcome": outcome,
                                  "failed_tests": [r["test_key"] for r in failed],
                                  "conditions": conditions}, actor=actor)
        return self.validations.one(id=validation_id)

    def _check_approvable(self, v: Dict[str, Any], failed: List[Dict[str, Any]],
                          conditions: List[str]) -> None:
        # A validation with NO results is not a validation that found nothing;
        # it is a validation that did not happen. `failed` is empty in both
        # cases, so an episode opened and concluded `approved` in two calls,
        # with no test recorded, satisfied every check here — and effective
        # challenge is the control the whole second line exists to be.
        if not self.results_for(v["id"]):
            raise ValidationError(
                "cannot approve: no test result has been recorded, so there is "
                "nothing this validation examined. Record what was tested and "
                "what it showed, or conclude 'rejected'")
        if failed:
            keys = ", ".join(sorted({r["test_key"] for r in failed}))
            raise ValidationError(
                f"cannot approve: {len(failed)} test(s) failed ({keys}); conclude "
                "'approved_with_conditions' with the conditions written down, or 'rejected'")
        if self.blocking:
            open_blocking = self.blocking.blocking_for(v["model_id"])
            if open_blocking:
                titles = "; ".join(f["title"] for f in open_blocking)
                raise ValidationError(
                    f"cannot approve: {len(open_blocking)} blocking finding(s) open "
                    f"against this model ({titles})")

    # ------------------------------------------------------------------ query
    def get(self, validation_id: str) -> Optional[Dict[str, Any]]:
        return self.validations.one(id=validation_id)

    def require(self, validation_id: str) -> Dict[str, Any]:
        row = self.get(validation_id)
        if not row:
            raise ValidationError(f"no validation {validation_id}")
        return row

    def for_model(self, urn: str) -> List[Dict[str, Any]]:
        return self.validations.many(model_id=self.registry.require(urn)["id"])

    def summary(self, validation_id: str) -> Dict[str, Any]:
        v = self.require(validation_id)
        rows = self.results_for(validation_id)
        failed = [r for r in rows if not r["passed"]]
        return {"validation_id": validation_id, "status": v["status"],
                "outcome": v["outcome"], "kind": v["kind"],
                "tests_run": len(rows), "tests_failed": len(failed),
                "failed_keys": sorted({r["test_key"] for r in failed}),
                "independent": v["independence"].get("independent"),
                "conditions": v["conditions"]}
