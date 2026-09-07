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
import resource
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from core.execution.errors import WarrantError
from core.log import get_logger, swallowed

logger = get_logger(__name__)

_log = get_logger(__name__)

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

    @classmethod
    def of(cls, warrant: Dict[str, Any]) -> "Limits":
        resources = (warrant.get("constraints") or {}).get("resources") or {}
        return cls(float(resources.get("max_seconds") or DEFAULT_SECONDS),
                   int(resources.get("max_memory_mb") or DEFAULT_MEMORY_MB))

    def as_dict(self) -> Dict[str, Any]:
        return {"max_seconds": self.seconds, "max_memory_mb": self.memory_mb}


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


def _apply_limits(limits: Limits) -> None:
    """Bound what the ARTIFACT consumes, after the interpreter has loaded.

    Applied here rather than at process start on purpose: capping address space
    before Python has imported its own runtime means the child dies importing
    lxml, which is a limit on the platform rather than on the model.
    """
    soft_cpu = max(1, int(limits.seconds))
    resource.setrlimit(resource.RLIMIT_CPU, (soft_cpu, soft_cpu + 1))
    if limits.memory_mb:
        budget = limits.memory_mb * 1024 * 1024
        cap = _address_space() + budget
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))


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
        _apply_limits(limits)
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
    """What this sandbox does and does not protect against."""
    isolated = sandbox.name == "subprocess"
    return {
        "sandbox": sandbox.name,
        "isolates": isolated,
        "protects_against": (["runaway cpu", "unbounded memory", "artifact crash"]
                             if isolated else []),
        "does_not_protect_against": (
            ["a deliberately hostile artifact: the child shares the filesystem "
             "and the network namespace",
             "bound callables, which run unisolated by construction"]
            if isolated else
            ["anything; this sandbox provides no isolation and is for bound "
             "callables and development only"]),
    }
