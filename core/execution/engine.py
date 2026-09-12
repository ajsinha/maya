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

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.domain.contracts import Bound, Contract
from core.execution.runtimes import (CallableRuntime, EstimatorRuntime, Invocation,
                                     OnnxRuntime, PmmlRuntime, QuantLibRuntime,
                                     FormulaRuntime, RulesRuntime,
                                     RuntimeRegistry)
from core.execution.sandbox import (Limits, Sandbox, SubprocessSandbox,
                                    describe as describe_sandbox)
from core.execution.warrants import WarrantError, WarrantService
from core.log import get_logger, swallowed

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
    """A reference consumer of the warrant contract, with seven real runtimes.

    It implements registered Python callables, ONNX graphs, the regression and
    scorecard subset of PMML, QuantLib valuation, the captive estimator, and
    authored rule sets. (This said "three" while five were registered, which is
    the count-written-once-and-never-recounted pattern in the code's own account
    of itself; `tests/test_registry_execution.py` now counts them.)

    The grammar names nineteen runtimes, and an engine's usefulness lies in
    being precise about which it has rather than in having them all: a warrant
    naming one it does not implement is refused by name, listing what it does.
    """

    def __init__(self, warrants: WarrantService, max_seconds: float = 30.0,
                 artifact_dir: Optional[Path] = None,
                 runtimes: Optional[RuntimeRegistry] = None,
                 sandbox: Optional[Sandbox] = None,
                 parameters=None, invocations=None):
        self.warrants = warrants
        # The invocation log, and NOT the register. The engine is a consumer of
        # the public warrant contract and nothing more, so it hands the log a
        # urn and lets the log resolve it — an engine holding a registry is an
        # engine that could read the register directly, which is the thing
        # `test_engine_never_reaches_the_store_directly` exists to prevent.
        self.invocations = invocations
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
            FormulaRuntime(),
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
        # The furthest revocation epoch this engine has ever been shown.
        #
        # Every descriptor carries the epoch it was minted at, and the epoch is
        # bumped by every revocation and persisted. Nothing compared it — a
        # field stamped on every warrant and read by nobody, which is the
        # defect this platform names as its own worst kind. See
        # `_refuse_stale_epoch` for what comparing it does and does not buy.
        self._seen_epoch: int = 0

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

    def _refuse_stale_epoch(self, warrant: Dict[str, Any]) -> None:
        """Refuse a descriptor minted before a revocation this engine has seen.

        **What this buys, exactly.** The epoch advances on every revocation and
        is stamped on every descriptor. An engine that has been handed epoch 7
        knows somebody withdrew authority seven times; a descriptor arriving
        stamped 5 was minted before the sixth, so presenting it now is either a
        replay or a descriptor that has been sitting in a queue across a
        revocation. Either way it is refused, and refused **offline** — the
        comparison needs nothing but what the engine has already been shown.

        **What it does not buy, which is the larger half.** It cannot see a
        revocation the engine has not been told about, and *MAYA does not tell
        it*: the platform does not run engines and has no channel to push a
        withdrawal down one. So an engine that never sees a newer descriptor
        will honour a revoked warrant until it expires.

        The bound on that residual is the **severity-scaled TTL**, and it is
        the honest whole answer rather than a footnote to this check: a Tier 1
        descriptor lives sixty seconds with no grace
        (`grants.DEFAULT_TTL`/`DEFAULT_GRACE`), so for the models the original
        finding was about there is almost nothing for a floor to do. What
        finding C-1 described — a locally persisted list that refuses
        regardless of grace — is not built and is not claimed; see
        `docs/11 §4.2`.
        """
        stamped = (((warrant.get("authority") or {}).get("revocation") or {})
                   .get("epoch"))
        if stamped is None:
            return
        stamped = int(stamped)
        if stamped < self._seen_epoch:
            raise WarrantError(
                "revoked_epoch",
                f"this descriptor was minted at revocation epoch {stamped} and "
                f"this engine has already seen epoch {self._seen_epoch}, so it "
                f"predates at least one withdrawal of authority",
                "re-resolve the warrant. A descriptor older than a revocation "
                "you have already been shown is either a replay or one that "
                "waited in a queue across it")
        self._seen_epoch = max(self._seen_epoch, stamped)

    def _constraints(self, warrant: Dict[str, Any]) -> Contract:
        """The operating boundary, read from where the grammar puts it."""
        boundary = (warrant.get("constraints") or {}).get("operating_boundary") or {}
        return Contract(tuple(Bound(b["key"], b.get("minimum"), b.get("maximum"),
                                    tuple(b.get("allowed", ())))
                              for b in boundary.get("assumptions", [])))

    def execute(self, urn: str, environment: str, principal: str, declared_use: str,
                inputs: Dict[str, Any]) -> ExecutionResult:
        started = time.perf_counter()
        # The log wraps everything from the resolution onward, because the
        # calls worth reading in an access review are the ones that were
        # REFUSED — and a log that only saw successful executions would miss
        # every one of them.
        try:
            warrant = self.warrants.resolve(urn, environment, principal,
                                            declared_use)
        except WarrantError as refusal:
            logger.info("refused to resolve %s for %s: %s", urn, principal,
                        getattr(refusal, "code", "refused"))
            self._log_refusal(urn, environment, principal, declared_use,
                              refusal)
            raise

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
        self._refuse_stale_epoch(warrant)
        if self.warrants.is_expired(warrant):
            raise WarrantError("expired", "warrant has expired beyond its grace window",
                            "re-resolve the warrant")

        contract = self._constraints(warrant)
        violations = contract.check_inputs(inputs)
        unchecked = contract.unchecked_inputs(inputs)
        if unchecked:
            # Not a refusal — an assumption constrains a value that was
            # supplied. But "the boundary held" and "the boundary never applied"
            # look identical from `boundary_ok` alone, and the second is what a
            # silently-unenforced contract looks like from outside.
            logger.info("operating boundary: %d assumption(s) found no value "
                        "and were not checked: %s",
                        len(unchecked), ", ".join(unchecked))
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
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        self._log(warrant, "ok", latency_ms=latency_ms,
                  boundary_ok=not violations)
        return ExecutionResult(
            descriptor_id=warrant["warrant_id"],
            model_urn=warrant["subject"]["model_urn"],
            version=warrant["subject"]["version"],
            prediction=prediction, boundary_ok=not violations,
            boundary_violations=violations,
            latency_ms=latency_ms)

    # ------------------------------------------------------------------- log
    def _log(self, warrant: Dict[str, Any], outcome: str, **fields) -> None:
        """Record one invocation. Never raises.

        This is called on the way out of an execution, including a failing one,
        and a logger that could fail the call it is logging would be a worse
        defect than the missing log.
        """
        if self.invocations is None:
            return
        try:
            self.invocations.record(warrant=warrant, outcome=outcome, **fields)
        except Exception as exc:
            swallowed(logger, exc, "did not record an invocation",
                      detail="the call itself is unaffected",
                      level=logging.WARNING)

    def _log_refusal(self, urn: str, environment: str, principal: str,
                     declared_use: str, refusal) -> None:
        """A call that never got a warrant, which is the kind an access review
        wants most and the kind a warrant-keyed log would miss entirely."""
        if self.invocations is None:
            return
        try:
            self.invocations.record_refusal(
                urn=urn, principal=principal, declared_use=declared_use,
                environment=environment,
                code=getattr(refusal, "code", "refused"))
        except Exception as exc:
            swallowed(logger, exc, "did not record a refused invocation",
                      detail="the refusal itself is unaffected",
                      level=logging.WARNING)
