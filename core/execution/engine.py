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
from core.execution.runtimes import (CallableRuntime, Invocation, OnnxRuntime,
                                     PmmlRuntime, QuantLibRuntime,
                                     RuntimeRegistry)
from core.execution.sandbox import (Limits, Sandbox, SubprocessSandbox,
                                    describe as describe_sandbox)
from core.execution.warrants import WarrantError, WarrantService

# Runtimes that load an artifact from disk, and therefore run isolated.
# QuantLib is not here on purpose. It loads no artifact — the instrument and the
# curve arrive in the warrant — so there is no untrusted file to isolate from,
# and paying a process spawn per valuation would buy nothing.
SANDBOXED_RUNTIMES = frozenset({"onnx", "pmml"})


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
    """A reference consumer of the warrant contract, with three real runtimes.

    It implements registered Python callables, ONNX graphs and the regression
    and scorecard subset of PMML. The grammar names seventeen runtimes, and an
    engine's usefulness lies in being precise about which it has rather than in
    having them all: a warrant naming one it does not implement is refused by
    name, listing what it does.
    """

    def __init__(self, warrants: WarrantService, max_seconds: float = 30.0,
                 artifact_dir: Optional[Path] = None,
                 runtimes: Optional[RuntimeRegistry] = None,
                 sandbox: Optional[Sandbox] = None):
        self.warrants = warrants
        self.max_seconds = max_seconds
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self._callables = CallableRuntime()
        self.runtimes = runtimes or RuntimeRegistry([
            self._callables,
            OnnxRuntime(self.artifact_dir),
            PmmlRuntime(self.artifact_dir),
            QuantLibRuntime(),
        ])
        # Artifacts run in a child with limits from the warrant. Bound callables
        # cannot: you cannot isolate a function handed to you in your own address
        # space, which is one more reason not to use them for anything real.
        self.sandbox = sandbox or SubprocessSandbox()
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

    def note_revocation(self, descriptor_id: str) -> None:
        """The revocation floor: honoured regardless of grace state."""
        self._revoked_locally.add(descriptor_id)

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
        if warrant["warrant_id"] in self._revoked_locally:
            raise WarrantError("revoked", "warrant is on the local revocation list",
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
