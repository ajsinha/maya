"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The captive execution engine.

MAYA manages models and issues hooks; it does not execute them. This module is
deliberately a CONSUMER of the public hook contract, not part of the control
plane: it resolves a descriptor, verifies the signature, checks expiry, checks
the operating boundaries, and only then runs. An external engine that does the
same is indistinguishable to MAYA — which is the point. It exists so that a
deployment works out of the box, and it is disabled by a single config key.

It is also the reference implementation of what a well-behaved engine must do.
Note the ordering: every check happens BEFORE the artifact is touched.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.domain.contracts import Bound, Contract
from core.execution.hooks import HookError, HookService


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
    """A minimal, honest execution engine. Runs registered Python callables only."""

    def __init__(self, hooks: HookService, max_seconds: float = 30.0):
        self.hooks = hooks
        self.max_seconds = max_seconds
        self._runtimes: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._revoked_locally: set = set()

    def register_runtime(self, version_id: str, fn: Callable[[Dict[str, Any]], Any]) -> None:
        """Bind an executable to a version. A real engine would load an artifact."""
        self._runtimes[version_id] = fn

    def note_revocation(self, descriptor_id: str) -> None:
        """The revocation floor: honoured regardless of grace state."""
        self._revoked_locally.add(descriptor_id)

    def _constraints(self, descriptor: Dict[str, Any]) -> Contract:
        spec = descriptor.get("constraints") or {}
        return Contract(tuple(Bound(b["key"], b.get("minimum"), b.get("maximum"),
                                    tuple(b.get("allowed", ())))
                              for b in spec.get("assumptions", [])))

    def execute(self, urn: str, environment: str, principal: str, declared_use: str,
                inputs: Dict[str, Any]) -> ExecutionResult:
        started = time.perf_counter()
        descriptor = self.hooks.resolve(urn, environment, principal, declared_use)

        if not self.hooks.verify(descriptor):
            raise HookError("signature_invalid", "descriptor signature does not verify",
                            "discard it and raise a security incident")
        if descriptor["descriptor_id"] in self._revoked_locally:
            raise HookError("revoked", "descriptor is on the local revocation list",
                            "stop; grace never extends revocation ignorance")
        if self.hooks.is_expired(descriptor):
            raise HookError("expired", "descriptor has expired beyond its grace window",
                            "re-resolve the hook")

        violations = self._constraints(descriptor).check_inputs(inputs)
        policy = (descriptor.get("constraints") or {}).get("on_boundary_violation", "reject")
        if violations and policy == "reject":
            raise HookError("boundary_violation",
                            f"inputs outside the operating boundary: {', '.join(violations)}",
                            "the guarantee is void outside the assumption; refer or widen it")

        version_id = descriptor["resolved"]["version_id"]
        runtime = self._runtimes.get(version_id)
        if runtime is None:
            raise HookError("no_runtime", f"no runtime registered for version {version_id}",
                            "register a runtime, or use an external execution engine")

        prediction = runtime(inputs)
        return ExecutionResult(
            descriptor_id=descriptor["descriptor_id"],
            model_urn=descriptor["resolved"]["model_urn"],
            version=descriptor["resolved"]["version"],
            prediction=prediction, boundary_ok=not violations,
            boundary_violations=violations,
            latency_ms=round((time.perf_counter() - started) * 1000, 3))
