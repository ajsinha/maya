"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The captive execution engine.

MAYA manages models and issues warrants; it does not execute them. This module is
deliberately a CONSUMER of the public warrant contract, not part of the control
plane: it resolves a warrant, verifies the signature, checks expiry, checks
the operating boundaries, and only then runs. An external engine that does the
same is indistinguishable to MAYA — which is the point. It exists so that a
deployment works out of the box, and it is disabled by a single config key.

It is also the reference implementation of what a well-behaved engine must do.
Note the ordering: every check happens BEFORE the artifact is touched.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.domain.contracts import Bound, Contract
from core.execution.runtimes import (CallableRuntime, EstimatorRuntime, Invocation,
                                     OnnxRuntime, PmmlRuntime, QuantLibRuntime,
                                     RulesRuntime, RuntimeRegistry)
from core.execution.sandbox import (Limits, Sandbox, SubprocessSandbox,
                                    describe as describe_sandbox)
from core.execution.warrants import WarrantError, WarrantService
from core.log import get_logger

# Runtimes that load an artifact from disk, and therefore run isolated.
# QuantLib is not here on purpose. It loads no artifact — the instrument and the
# curve arrive in the warrant — so there is no untrusted file to isolate from,
# and paying a process spawn per valuation would buy nothing.
SANDBOXED_RUNTIMES = frozenset({"onnx", "pmml"})

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    descriptor_id: str
    model_urn: str
    version: str
    prediction: Any
    boundary_ok: bool
    boundary_violations: List[str]
    latency_ms: float


class CaptiveEngine:
    """A reference consumer of the warrant contract, with six real runtimes.

    It implements registered Python callables, ONNX graphs, the regression and
    scorecard subset of PMML, QuantLib valuation, the captive estimator, and
    authored rule sets. (This said "three" while five were registered, which is
    the count-written-once-and-never-recounted pattern in the code's own account
    of itself; `tests/test_registry_execution.py` now counts them.)

    The grammar names eighteen runtimes, and an engine's usefulness lies in
    being precise about which it has rather than in having them all: a warrant
    naming one it does not implement is refused by name, listing what it does.
    """

    def __init__(self, warrants: WarrantService, max_seconds: float = 30.0,
                 artifact_dir: Optional[Path] = None,
                 runtimes: Optional[RuntimeRegistry] = None,
                 sandbox: Optional[Sandbox] = None,
                 parameters=None):
        self.warrants = warrants
        self.max_seconds = max_seconds
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self._callables = CallableRuntime()
        self.runtimes = runtimes or RuntimeRegistry([
            self._callables,
            OnnxRuntime(self.artifact_dir),
            PmmlRuntime(self.artifact_dir),
            QuantLibRuntime(),
            EstimatorRuntime(),
            RulesRuntime(),
        ])
        # Artifacts run in a child with limits from the warrant. Bound callables
        # cannot: you cannot isolate a function handed to you in your own address
        # space, which is one more reason not to use them for anything real.
        self.sandbox = sandbox or SubprocessSandbox()
        # Optional: an engine with no parameter register can still run every
        # artifact-backed runtime, and refuses by name the one binding it cannot
        # honour. That is better than a hard dependency for a capability most
        # deployments of the captive engine do not use.
        self.parameters = parameters
        self._revoked_locally: set = set()

    def register_runtime(self, version_id: str, fn: Callable[[Dict[str, Any]], Any]) -> None:
        """Bind a callable to a version, for development and for tests."""
        self._callables.bind(version_id, fn)

    def implements(self) -> list:
        """What this engine can run, and why it cannot run the rest."""
        return self.runtimes.describe()

    def isolation(self) -> Dict[str, Any]:
        """What the sandbox protects against, and what it does not."""
        return describe_sandbox(self.sandbox)

    def _sandboxed(self, warrant: Dict[str, Any]) -> bool:
        """Artifact-backed runtimes are isolated; bound callables cannot be."""
        runtime = (warrant.get("realisation") or {}).get("runtime")
        bound = self._callables.is_bound(warrant.get("subject", {}).get("version_id"))
        return runtime in SANDBOXED_RUNTIMES and not bound

    def _with_parameters(self, warrant: Dict[str, Any],
                         inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve the parameter set the warrant names, digest-checked.

        The same act as verifying an artifact's digest, one object over: the
        warrant says which point of P this run is at, and an engine that took
        the register's word for it without checking would have a chain of
        custody whose last link is the one that touches what actually runs.
        """
        source = (warrant.get("parameters") or {}).get("source") or {}
        if source.get("binding") != "parameter_set":
            return inputs
        if self.parameters is None:
            raise WarrantError(
                "no_parameter_register",
                "this warrant runs at a registered parameter set and the engine "
                "was built without a register to read it from",
                "wire the parameter register into the engine, or resolve a "
                "warrant whose parameters come from the artifact")
        row = self.parameters.get(source.get("parameter_set"))
        if row is None:
            raise WarrantError(
                "no_parameter_set",
                f"the warrant names parameter set {source.get('parameter_set')} "
                f"and the register does not have it",
                "the set was removed after the warrant was minted; re-resolve")
        # RE-DERIVED from the values, not read off the row. Comparing the stored
        # digest against the warrant's compares two copies of the same claim and
        # would pass over values edited underneath it.
        actual = self.parameters.digest_of(row)
        if actual != source.get("digest") or actual != row.get("digest"):
            logger.error("parameter digest mismatch for %s: warrant %s, "
                         "stored %s, recomputed %s", source.get("parameter_set"),
                         source.get("digest"), row.get("digest"), actual)
            raise WarrantError(
                "parameter_mismatch",
                "the parameter set does not match the digest in the warrant, so "
                "the numbers about to run are not the numbers that were approved",
                "do not run it; re-resolve the warrant and raise a security "
                "incident if the values moved without an approval")
        return {**(inputs or {}), "parameters": row.get("values_inline") or {}}

    def note_revocation(self, subject: str) -> None:
        """The revocation floor: honoured regardless of grace state.

        `subject` is either a **model URN** or a single `warrant_id`. Both are
        accepted because both are things an engine gets told, but the model URN
        is the one that works, and for a while it was not accepted at all.

        This took a `descriptor_id`, and `execute` re-resolves before checking —
        and every `builder.build` mints a **fresh** `warrant_id`. So the noted id
        never matched the id being checked, and the floor could not fire. It is
        the same defect as finding C-2 seen from the other side: there, an
        identifier stayed stable while its contents moved; here, an identifier
        moves while the thing it names stays exactly the same.

        The floor exists for the case where an engine has been told to stop and
        cannot reach MAYA to have that confirmed, so it must key on something
        that survives a re-resolve. `subject.model_urn` does; a per-descriptor id
        is minted fresh each time, by design.
        """
        self._revoked_locally.add(subject)

    def _constraints(self, warrant: Dict[str, Any]) -> Contract:
        """The operating boundary, read from where the grammar puts it."""
        boundary = (warrant.get("constraints") or {}).get("operating_boundary") or {}
        return Contract(tuple(Bound(b["key"], b.get("minimum"), b.get("maximum"),
                                    tuple(b.get("allowed", ())))
                              for b in boundary.get("assumptions", [])))

    def execute(self, urn: str, environment: str, principal: str, declared_use: str,
                inputs: Dict[str, Any]) -> ExecutionResult:
        started = time.perf_counter()
        warrant = self.warrants.resolve(urn, environment, principal, declared_use)

        if not self.warrants.verify(warrant):
            raise WarrantError("signature_invalid", "warrant signature does not verify",
                            "discard it and raise a security incident")
        revoked = self._revoked_locally & {
            warrant["warrant_id"],
            (warrant.get("subject") or {}).get("model_urn"),
            (warrant.get("subject") or {}).get("urn"),
        }
        if revoked:
            raise WarrantError(
                "revoked",
                f"{sorted(revoked)[0]} is on the local revocation list",
                "stop; grace never extends revocation ignorance")
        if self.warrants.is_expired(warrant):
            raise WarrantError("expired", "warrant has expired beyond its grace window",
                            "re-resolve the warrant")

        violations = self._constraints(warrant).check_inputs(inputs)
        policy = (warrant.get("constraints") or {}).get("on_boundary_violation", "reject")
        if violations and policy == "reject":
            raise WarrantError("boundary_violation",
                            f"inputs outside the operating boundary: {', '.join(violations)}",
                            "the guarantee is void outside the assumption; refer or widen it")

        # Dispatch on the warrant's declared runtime. Everything above this line
        # is checked without touching an artifact, which is the order that makes
        # a refusal cheap and stops an artifact loading on an authorisation that
        # was never valid.
        # A warrant that names a point of P is a warrant whose values have to be
        # read and checked before anything runs at them. Done here rather than in
        # the runtime because a runtime that resolved its own parameters would be
        # choosing which numbers it ran on, and that is the decision the approval
        # exists to make.
        inputs = self._with_parameters(warrant, inputs)

        if self._sandboxed(warrant):
            prediction = self.sandbox.run(warrant, inputs, self.artifact_dir,
                                          Limits.of(warrant))
        else:
            prediction = self.runtimes.invoke(Invocation(warrant, inputs))
        return ExecutionResult(
            descriptor_id=warrant["warrant_id"],
            model_urn=warrant["subject"]["model_urn"],
            version=warrant["subject"]["version"],
            prediction=prediction, boundary_ok=not violations,
            boundary_violations=violations,
            latency_ms=round((time.perf_counter() - started) * 1000, 3))
