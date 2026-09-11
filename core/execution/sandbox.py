"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Isolating artifact execution.

The engine loads ONNX graphs and PMML documents, which means it loads files
whose contents it did not write. A governance platform that runs an arbitrary
artifact in its own process has made the artifact's bugs into its own, and a
malformed graph that exhausts memory takes the register down with it.

So artifact-backed runtimes run in a **child process with resource limits taken
from the warrant** — the grammar already carries `constraints.resources`, and
this is where that section stops being documentation.

**What this protects against, honestly:**

  * a runaway artifact — CPU and address space are bounded, and the parent
    reclaims the child on timeout
  * a crash — a segfault in a native runtime kills the child, not the platform
  * unbounded memory — an allocation past the limit fails in the child

**What it does not protect against:**

  * a deliberately hostile artifact. The child shares the filesystem and the
    network namespace. Blocking those needs a container, a VM or seccomp, and
    pretending otherwise would be worse than saying so.
  * a callable bound in process. You cannot sandbox a function somebody handed
    you in your own address space, and the engine does not claim to — bound
    callables are a development convenience and run unisolated, which is one
    more reason not to use them for anything else.

Being precise about that boundary is the point. An engine that claims isolation
it does not have is more dangerous than one that claims none.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from core.execution.errors import WarrantError
from core.log import get_logger, swallowed

logger = get_logger(__name__)

_log = get_logger(__name__)

# `resource` is POSIX-only. On Windows it does not exist, and importing it at
# module scope took the whole platform down at start-up — MAYA could not boot
# on Windows at all, which is a portability bug rather than a sandbox one and
# is why it is an import guard and not a feature flag.
#
# What survives without it, and what does not, is the whole of the honesty this
# module is about:
#
#   survives   process isolation — a crash kills the child, not the register
#   survives   the WALL-CLOCK deadline — the parent reclaims a child that does
#              not return, which catches a hang and a slow model
#   lost       RLIMIT_CPU — a child spinning inside its wall-clock window is
#              not stopped early
#   lost       RLIMIT_AS — an artifact may allocate past the warrant's budget
#
# Windows can bound both through Job Objects, which needs pywin32 or a slab of
# ctypes; that is a real option and it is not this. What matters is that the
# platform stops CLAIMING the two it cannot deliver.
try:
    import resource
except ImportError as _exc:                           # Windows
    resource = None                                   # type: ignore[assignment]
    # Said once, at import, and at WARNING. An operator on a platform without
    # resource limits should learn it from the log at start-up rather than from
    # a refusal the first time somebody executes a warrant that states one.
    logger.warning(
        "POSIX resource limits are unavailable here (%s), so the sandbox "
        "cannot bound an artifact's cpu or memory. It still isolates — a "
        "crash does not reach the register and the parent reclaims a child "
        "that does not return — and a warrant STATING max_memory_mb is "
        "refused rather than run unbounded.", _exc)

#: Whether this platform can bound what a child consumes.
RLIMITS = resource is not None

DEFAULT_SECONDS = 30.0
DEFAULT_MEMORY_MB = 2048
# A child gets a little more wall-clock than CPU, so a process that is waiting
# rather than spinning is still reclaimed, and the CPU limit is what bites first
# on a runaway.
WALL_CLOCK_MARGIN = 2.0


@dataclass(frozen=True)
class Limits:
    """What a child may consume, read from the warrant that authorised it."""
    seconds: float = DEFAULT_SECONDS
    memory_mb: int = DEFAULT_MEMORY_MB
    #: Which of these the WARRANT stated, as against which MAYA defaulted.
    #:
    #: The distinction decides what happens on a platform that cannot enforce
    #: them. A default is MAYA's own conservative choice and running past it is
    #: a degradation; a figure written into a warrant is a constraint somebody
    #: signed for, and running an artifact while silently not applying it would
    #: be the platform asserting compliance with a control it did not exercise.
    declared: tuple = ()

    @classmethod
    def of(cls, warrant: Dict[str, Any]) -> "Limits":
        resources = (warrant.get("constraints") or {}).get("resources") or {}
        stated = tuple(sorted(
            key for key in ("max_seconds", "max_memory_mb")
            if resources.get(key)))
        return cls(float(resources.get("max_seconds") or DEFAULT_SECONDS),
                   int(resources.get("max_memory_mb") or DEFAULT_MEMORY_MB),
                   stated)

    def as_dict(self) -> Dict[str, Any]:
        return {"max_seconds": self.seconds, "max_memory_mb": self.memory_mb,
                "declared_by_the_warrant": list(self.declared)}

    def unenforceable(self) -> tuple:
        """Limits this platform cannot apply, of those the warrant STATED.

        Empty where rlimits exist, and empty on Windows for a warrant that
        stated none — because there is then nothing anybody was promised.
        """
        if RLIMITS:
            return ()
        # `max_seconds` is still bounded, by the parent's wall clock. It is
        # bounded LESS precisely — a child may burn CPU inside its window — but
        # a warrant asking for thirty seconds does get thirty seconds, so
        # calling it unenforced would be the opposite error.
        return tuple(key for key in self.declared if key == "max_memory_mb")


@runtime_checkable
class Sandbox(Protocol):
    """Somewhere to run an artifact."""

    name: str

    def run(self, warrant: Dict[str, Any], inputs: Dict[str, Any],
            artifact_dir: Optional[Path], limits: Limits) -> Any:
        ...


# ---------------------------------------------------------------------------
# The child. A module-level function so it survives the spawn start method.
# ---------------------------------------------------------------------------
def _address_space() -> int:
    """What this process has already reserved, in bytes.

    The memory budget in a warrant means "what this model may use", not "what a
    Python interpreter plus numpy plus onnxruntime may total" — and the second
    number is both larger and not the warrant author's business. So the limit is
    applied on top of what the interpreter has already taken.
    """
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmSize:"):
                return int(line.split()[1]) * 1024
    except OSError as exc:
        swallowed(logger, exc, "could not read this process's address space",
                  detail="applying the memory budget as an absolute limit",
                  level=logging.DEBUG)
    return 0


def _apply_limits(limits: Limits) -> tuple:
    """Bound what the ARTIFACT consumes, after the interpreter has loaded.

    Applied here rather than at process start on purpose: capping address space
    before Python has imported its own runtime means the child dies importing
    lxml, which is a limit on the platform rather than on the model.

    **Both caps are the process's CURRENT usage plus the budget**, and the CPU
    one was not. `RLIMIT_AS` was always written that way — `_address_space() +
    budget` — because address space is a level and capping it at the budget
    alone would cap the interpreter. `RLIMIT_CPU` is a *cumulative* count from
    process start, and it was being set to `limits.seconds` flat, so the
    interpreter's own start-up was spent out of the model's budget.

    That is not a rounding error. `tools/spikes/sandbox_escape` measured a
    spawned child at **3.3 CPU-seconds just to import this package**, so a
    warrant stating `max_seconds: 2` killed the artifact with SIGXCPU before it
    ran a single instruction — and the failure was indistinguishable, in the
    log and on the evidence chain, from a runaway model. A tighter budget made
    it *more* likely, which is the opposite of what the author of the warrant
    was doing.

    Returns what was ACTUALLY applied. The caller reports it back to the
    parent, so that "the artifact ran under a 512 MB cap" is something the
    platform observed rather than something it intended — on a system without
    rlimits those are different statements, and only one of them is evidence.
    """
    if not RLIMITS:
        return ()
    applied = []
    # Cumulative, so the budget starts from what this process has already
    # spent getting here rather than from zero.
    spent = resource.getrusage(resource.RUSAGE_SELF)
    already = int(spent.ru_utime + spent.ru_stime) + 1
    soft_cpu = already + max(1, int(limits.seconds))
    resource.setrlimit(resource.RLIMIT_CPU, (soft_cpu, soft_cpu + 1))
    applied.append("cpu_seconds")
    if limits.memory_mb:
        budget = limits.memory_mb * 1024 * 1024
        cap = _address_space() + budget
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        applied.append("address_space")
    return tuple(applied)


def _invoke_in_child(conn, warrant: Dict[str, Any], inputs: Dict[str, Any],
                     artifact_dir: Optional[str], limits: Limits) -> None:
    """Load the artifact and invoke it, under limits, reporting back one way."""
    try:
        # Import first, then limit. The budget is what the model may use; the
        # interpreter's own footprint is not the warrant author's concern.
        from core.execution.runtimes import (Invocation, OnnxRuntime, PmmlRuntime,
                                             RuntimeRegistry)
        directory = Path(artifact_dir) if artifact_dir else None
        registry = RuntimeRegistry([OnnxRuntime(directory), PmmlRuntime(directory)])
        for runtime in (OnnxRuntime(directory), PmmlRuntime(directory)):
            runtime.available()          # force the dependency import under no cap
        applied = _apply_limits(limits)
        if not applied:
            _log.warning(
                "this artifact ran with NO resource limits applied: POSIX "
                "rlimits are unavailable on this platform. The child is still "
                "isolated — a crash does not reach the register and the parent "
                "reclaims a child that does not return — but CPU and memory "
                "are unbounded within that window.")
        conn.send(("ok", registry.invoke(Invocation(warrant, inputs))))
    except WarrantError as exc:
        # The child has its own logger; the parent learns through the pipe.
        _log.info("sandboxed invocation refused: %s (%s)", exc.code, exc.detail)
        conn.send(("refused", (exc.code, exc.detail, exc.remediation)))
    except MemoryError as exc:
        # Report before logging: under an exhausted address space the logger
        # may not have the memory to format a record, and the parent must
        # still hear why the child stopped.
        conn.send(("limit", "the artifact exhausted the memory it was allowed"))
        swallowed(_log, exc, "ran the artifact",
                  "it exhausted the memory the warrant allowed", logging.WARNING)
    except BaseException as exc:
        conn.send(("failed", f"{type(exc).__name__}: {exc}"))
        swallowed(_log, exc, "ran the artifact",
                  "the failure is reported to the parent process", logging.ERROR)
    finally:
        conn.close()


class SubprocessSandbox:
    """Runs artifact-backed runtimes in a limited child process."""

    name = "subprocess"

    def __init__(self, start_method: str = "spawn"):
        # `spawn` rather than `fork`: a forked child inherits the parent's open
        # database handles and signal state, and an artifact that crashes while
        # holding them is a much messier failure than one that never had them.
        self._ctx = mp.get_context(start_method)

    def run(self, warrant: Dict[str, Any], inputs: Dict[str, Any],
            artifact_dir: Optional[Path], limits: Limits) -> Any:
        # A limit the WARRANT stated and this platform cannot apply is a
        # refusal, not a warning. Running anyway would put an execution on the
        # evidence chain under a warrant declaring a memory cap that was never
        # imposed — the platform asserting compliance with a control it did not
        # exercise, which is the one thing a governance system must not do.
        #
        # A limit MAYA merely DEFAULTED to is different: nobody was promised
        # it, so the run proceeds and `describe()` says what is enforced.
        if (missing := limits.unenforceable()):
            raise WarrantError(
                "limit_not_enforceable",
                f"this warrant states {', '.join(missing)} and this platform "
                f"cannot enforce it: POSIX resource limits are unavailable "
                f"here, which is the case on Windows. The artifact has not "
                f"been run.",
                "run the engine on a platform with resource limits, run this "
                "model on a remote engine, or remove the limit from the "
                "warrant — which is a governance decision and should be a "
                "deliberate one")
        parent, child = self._ctx.Pipe(duplex=False)
        # `mp.get_context()` is typed as returning `BaseContext`, which
        # declares no `Process`; the concrete SpawnContext does. Annotated
        # rather than left for the backlog, because the backlog is how the
        # string-for-int defect two handlers up survived: the gate found it and
        # was told not to look at this file.
        process = self._ctx.Process(   # type: ignore[attr-defined]
            target=_invoke_in_child,
            args=(child, warrant, inputs,
                  str(artifact_dir) if artifact_dir else None, limits))
        started = time.perf_counter()
        process.start()
        child.close()

        deadline = limits.seconds + WALL_CLOCK_MARGIN
        payload = parent.recv() if parent.poll(deadline) else None
        process.join(timeout=1.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1.0)

        if payload is None:
            logger.warning("sandboxed artifact exceeded %.1fs and was reclaimed",
                           deadline)
            raise WarrantError(
                "execution_timeout",
                f"the artifact did not return within {deadline:.0f} seconds and "
                "the sandbox reclaimed it",
                "raise max_seconds on the warrant if this model is genuinely slow, "
                "or investigate why it is not returning")
        return self._unpack(payload, time.perf_counter() - started)

    @staticmethod
    def _unpack(payload, elapsed: float) -> Any:
        kind, value = payload
        if kind == "ok":
            return value
        if kind == "refused":
            code, detail, remediation = value
            raise WarrantError(code, detail, remediation)
        if kind == "limit":
            logger.warning("sandboxed artifact hit its memory limit after %.2fs",
                           elapsed)
            raise WarrantError(
                "execution_limit", value,
                "raise max_memory_mb on the warrant, or investigate why the "
                "artifact needs that much")
        logger.error("sandboxed artifact failed: %s", value)
        raise WarrantError(
            "execution_failed", f"the artifact failed in the sandbox: {value}",
            "the failure is the artifact's, not the platform's; the engine "
            "survived it")


class InProcessSandbox:
    """No isolation at all. For bound callables, and for tests that need speed.

    Named rather than implicit, because "we run it in process" is a decision
    somebody should have to read.
    """

    name = "in_process"

    def run(self, warrant: Dict[str, Any], inputs: Dict[str, Any],
            artifact_dir: Optional[Path], limits: Limits) -> Any:
        from core.execution.runtimes import (Invocation, OnnxRuntime, PmmlRuntime,
                                             RuntimeRegistry)
        registry = RuntimeRegistry([OnnxRuntime(artifact_dir),
                                    PmmlRuntime(artifact_dir)])
        return registry.invoke(Invocation(warrant, inputs))


def describe(sandbox: Sandbox) -> Dict[str, Any]:
    """What this sandbox does and does not protect against, ON THIS PLATFORM.

    Platform-dependent because the answer is. Reporting "protects against
    unbounded memory" on a system with no `resource` module would be this
    module's own stated failure — an engine claiming isolation it does not
    have — printed by the function whose job is to prevent it.
    """
    isolated = sandbox.name == "subprocess"
    if not isolated:
        return {
            "sandbox": sandbox.name, "isolates": False,
            "resource_limits": "not applicable",
            "protects_against": [],
            "does_not_protect_against": [
                "anything; this sandbox provides no isolation and is for bound "
                "callables and development only"],
        }

    protects = ["artifact crash",
                "a hung or slow artifact: the parent reclaims it on the wall "
                "clock"]
    misses = ["a deliberately hostile artifact: the child shares the "
              "filesystem and the network namespace",
              "bound callables, which run unisolated by construction"]
    if RLIMITS:
        protects[:0] = ["runaway cpu", "unbounded memory"]
    else:
        misses[:0] = [
            "unbounded memory: POSIX resource limits are unavailable on this "
            "platform, so an artifact may allocate past the warrant's budget",
            "cpu burned inside the wall-clock window, for the same reason"]
    return {
        "sandbox": sandbox.name, "isolates": True,
        "resource_limits": "enforced" if RLIMITS else
                           "UNAVAILABLE on this platform; a warrant that states "
                           "max_memory_mb is refused rather than run unbounded",
        "platform": sys.platform,
        "protects_against": protects,
        "does_not_protect_against": misses,
    }
