"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Spike 3: what the sandbox actually stops.

`core/execution/sandbox.py` is careful about its own boundary — it names what
survives without POSIX resource limits and what does not, and it refuses a
warrant stating a limit it cannot enforce. What the roadmap has listed since the
first release, and what has never been done, is **trying**.

The distinction matters more here than in the other two spikes. A latency figure
is a number somebody either measured or did not. A security boundary is a claim
about what an adversary cannot do, and the only evidence for it is an attempt
that failed.

## What this reports, and the order it reports it in

**What was tried, first.** A control that stopped everything somebody thought to
attempt has been tested against that person's imagination, and printing HELD
above the list of attempts is how a reader comes away with more confidence than
the evidence supports. The attempt list is the result; the verdicts are a
property of it.

**What it is not.** This is not a penetration test, and running it is not
`NFR-SEC-001`'s annual engagement by another name. It is a regression suite for
a boundary that is *documented*: each attempt corresponds to a sentence the
sandbox module already makes about itself, and the value is that the sentence
stops being unexamined.

## The attempts, and why each one is here

`cpu_spin` and `memory_balloon` are the two `RLIMITS` buys and the two lost
without it — so on a POSIX host they should be stopped, and on Windows they
should be *refused at issuance* rather than run. Either is a pass; running
unbounded is not.

`wall_clock_hang` is the limit that survives everywhere, and the one that
catches a model which is waiting rather than spinning.

`crash` is the isolation claim: a child that dies must not reach the register.

`escape_import` and `filesystem_write` are the two an honest reading says will
NOT be stopped — the child is a Python process with the parent's filesystem
access, and `docs/14` says a `spawn`ed child with rlimits is *honestly scoped*
rather than a jail. They are here so the report says so out loud, with a number
beside it, rather than leaving a reader to infer a containment boundary from the
word "sandbox".
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List

from tools.spikes.common import conditions

HELD, NOT_HELD, REFUSED, NOT_CLAIMED = "held", "NOT HELD", "refused", \
    "not claimed"

#: A failure in this harness, kept apart from a stop by the sandbox.
#:
#: The first version of this file did not have it, and reported **six holds
#: having tried nothing**: `SubprocessSandbox.run()` was called with the wrong
#: signature, every attempt raised `TypeError` before the child started, and a
#: bare `except Exception` counted each one as the sandbox stopping an attack.
#: A security spike that cannot tell *the boundary held* from *my test was
#: broken* is worse than no spike, because it produces a green result and a
#: false belief. So a harness error is its own verdict and it fails the run.
HARNESS_ERROR = "HARNESS ERROR"


def _warrant(seconds: float = 2.0, memory_mb: int = 256) -> Dict[str, Any]:
    return {"operating_boundary": {"resources": {
        "max_seconds": seconds, "max_memory_mb": memory_mb}}}


# --------------------------------------------------------------- the attempts
def _cpu_spin(_: Dict[str, Any]) -> None:
    end = time.time() + 3600
    total = 0
    while time.time() < end:
        total += 1


def _memory_balloon(_: Dict[str, Any]) -> None:
    held = []
    while True:
        held.append(bytearray(16 * 1024 * 1024))


def _wall_clock_hang(_: Dict[str, Any]) -> None:
    time.sleep(3600)


def _crash(_: Dict[str, Any]) -> None:
    import ctypes
    ctypes.string_at(0)                      # segfault the child, deliberately


def _escape_import(_: Dict[str, Any]) -> Any:
    import os
    import socket                            # noqa: F401
    return {"pid": os.getpid(), "cwd": os.getcwd(),
            "env_keys": len(os.environ)}


def _filesystem_write(_: Dict[str, Any]) -> Any:
    import tempfile
    from pathlib import Path
    target = Path(tempfile.gettempdir()) / "maya-sandbox-escape-probe"
    target.write_text("the child wrote this")
    written = target.read_text()
    target.unlink(missing_ok=True)
    return {"wrote": written}


ATTEMPTS: List[Dict[str, Any]] = [
    {"name": "cpu_spin",
     "fn": _cpu_spin,
     "expect": "stopped by RLIMIT_CPU, or the wall-clock deadline",
     "why": "the limit POSIX buys and Windows loses. A child spinning inside "
            "its wall-clock window is not stopped early without it"},
    {"name": "memory_balloon",
     "fn": _memory_balloon,
     "expect": "stopped by RLIMIT_AS",
     "why": "the other thing RLIMITS buys. Without it an artifact allocates "
            "past the warrant's budget and the host, not the child, is what "
            "runs out"},
    {"name": "wall_clock_hang",
     "fn": _wall_clock_hang,
     "expect": "reclaimed by the parent at the deadline",
     "why": "the limit that survives everywhere, and the one that catches a "
            "model waiting on something rather than spinning"},
    {"name": "crash",
     "fn": _crash,
     "expect": "the child dies and the register does not",
     "why": "the isolation claim itself. A segfault in somebody's artifact "
            "must not reach the process holding the evidence chain"},
    {"name": "escape_import",
     "fn": _escape_import,
     "expect": "NOT stopped — the child is a Python process",
     "why": "here to make the boundary explicit. A `spawn`ed child with "
            "rlimits is honestly scoped and is not a jail: it imports what it "
            "likes, including `socket`. Reported so nobody infers containment "
            "from the word sandbox"},
    {"name": "filesystem_write",
     "fn": _filesystem_write,
     "expect": "NOT stopped — the child has the parent's filesystem access",
     "why": "the same point with a sharper edge. Containment here is a "
            "deployment's job — a read-only root and a dropped capability "
            "set, which `deploy/` does provide — and not this module's"},
]


def run(timeout: float = 25.0) -> Dict[str, Any]:
    """Try each attempt against the real mechanism and report what happened.

    **Against the mechanism, not through `run()`.** `SubprocessSandbox.run`
    loads a registered artifact through a runtime registry; it does not take an
    arbitrary callable, and pretending otherwise is what produced this file's
    first false result. So each attempt is spawned the way `_invoke_in_child`
    spawns one — the same `spawn` context, the same `_apply_limits`, the same
    wall-clock reclaim — and the refusal path is exercised separately against
    the real `run()`. Saying which is which is the point.
    """
    from core.execution.sandbox import RLIMITS

    results = [_try(attempt, timeout) for attempt in ATTEMPTS]
    results.append(_refusal_path())
    held = sum(1 for r in results if r["verdict"] == HELD)
    not_held = [r["attempt"] for r in results
                if r["verdict"] in (NOT_HELD, HARNESS_ERROR)]
    return {
        "spike": "sandbox-escape",
        "requirement": "docs/10 §2.3; NFR-SEC-001",
        "conditions": conditions(rlimits_available=RLIMITS,
                                 start_method="spawn"),
        # What was TRIED, before what held. A control that stopped everything
        # somebody thought to attempt has been tested against that person's
        # imagination, and printing the verdict first is how a reader comes
        # away with more confidence than the evidence supports.
        "attempted": [{"attempt": a["name"], "expect": a["expect"],
                       "why": a["why"]} for a in ATTEMPTS],
        "results": results,
        "held": held,
        "did_not_hold": not_held,
        "is_a_penetration_test": False,
        "detail": _detail(results, RLIMITS, not_held),
    }


def _try(attempt: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """Spawn one attempt under the sandbox's own limits and see what happens."""
    import multiprocessing as mp

    from core.execution.sandbox import Limits

    seconds = min(timeout, 2.0)
    limits = Limits(seconds=seconds, memory_mb=256)
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    started = time.perf_counter()
    deadline = seconds + 2.0
    try:
        process = ctx.Process(target=_child,
                              args=(child, attempt["name"], limits))
        process.start()
        child.close()
        # The same reclaim the sandbox performs: a child that does not answer
        # inside the deadline is terminated by the parent.
        # An EOF here is the child DYING, not the harness failing — a
        # segfault, or a SIGKILL from the kernel's OOM handling, closes the
        # pipe without sending. Telling the two apart is the whole reason
        # this catch is narrow: `except Exception` around the recv would have
        # filed four dead children as broken tests.
        try:
            payload = parent.recv() if parent.poll(deadline) else None
        except EOFError:
            payload = ("died", None)
        process.join(timeout=1.0)
        reclaimed = process.is_alive()
        if reclaimed:
            process.terminate()
            process.join(timeout=1.0)
        exitcode = process.exitcode
    except Exception as broken:
        # The harness, not the boundary. Kept apart because conflating them is
        # how this file first reported six holds having tried nothing.
        return {"attempt": attempt["name"], "verdict": HARNESS_ERROR,
                "seconds": round(time.perf_counter() - started, 3),
                "error": f"{type(broken).__name__}: {broken}",
                "detail": "the harness failed before the attempt ran. This is "
                          "not evidence about the sandbox in either direction"}
    elapsed = time.perf_counter() - started
    expected_open = attempt["expect"].startswith("NOT stopped")

    if reclaimed or payload is None:
        return {"attempt": attempt["name"], "verdict": HELD,
                "seconds": round(elapsed, 3), "exitcode": exitcode,
                "detail": f"the child did not return within {deadline:.0f}s "
                          f"and was reclaimed by the parent"}
    kind, value = payload
    if kind == "died":
        return {"attempt": attempt["name"], "verdict": HELD,
                "seconds": round(elapsed, 3), "exitcode": exitcode,
                "detail": (f"the child died (exit {exitcode}) and the parent "
                           f"did not. A negative exit code is a signal: -11 "
                           f"is a segfault, -9 is the kernel killing it")}
    if kind == "raised":
        return {"attempt": attempt["name"], "verdict": HELD,
                "seconds": round(elapsed, 3), "stopped_by": str(value)[:120],
                "detail": f"the child was stopped: {str(value)[:200]}"}
    return {
        "attempt": attempt["name"],
        "verdict": NOT_CLAIMED if expected_open else NOT_HELD,
        "seconds": round(elapsed, 3), "returned": _short(value),
        "detail": (attempt["why"] if expected_open else
                   f"the child completed in {elapsed:.2f}s and should not "
                   f"have"),
    }


def _child(conn: Any, name: str, limits: Any) -> None:
    """The child, applying the sandbox's own limits before the attempt.

    `_apply_limits` is imported from the module rather than reproduced, so what
    is exercised is the platform's rule and not this file's idea of it.
    """
    try:
        from core.execution.sandbox import _apply_limits
        _apply_limits(limits)
        fn = {a["name"]: a["fn"] for a in ATTEMPTS}[name]
        conn.send(("returned", fn({})))
    except BaseException as stopped:
        # BaseException: a MemoryError is one, and so is the SIGXCPU that
        # RLIMIT_CPU raises. Catching only Exception would let the two the
        # limits exist for go unreported.
        try:
            conn.send(("raised", f"{type(stopped).__name__}: {stopped}"))
        except Exception:                       # noqa: S110
            # Nothing to log to: the child's own logging may be what the
            # limit killed, and a child that cannot report is reported by
            # the PARENT as reclaimed, which is the correct verdict anyway.
            pass
    finally:
        conn.close()


def _refusal_path() -> Dict[str, Any]:
    """A warrant stating a limit this platform cannot apply must be REFUSED.

    Separate from the attempts because it is the opposite claim: not *the
    boundary held* but *the platform declined to pretend*. Running anyway would
    put an execution on the evidence chain under a warrant declaring a memory
    cap that was never imposed.
    """
    from core.execution.errors import WarrantError
    from core.execution.sandbox import RLIMITS, Limits, SubprocessSandbox

    name = "stated_limit_refused_when_unenforceable"
    if RLIMITS:
        return {"attempt": name, "verdict": NOT_CLAIMED,
                "detail": "this host HAS POSIX resource limits, so there is "
                          "no unenforceable limit to refuse. The refusal path "
                          "matters on a host without them, and is exercised "
                          "there"}
    limits = Limits(seconds=1.0, memory_mb=64,
                    declared=("max_memory_mb",))
    try:
        SubprocessSandbox().run({}, {}, None, limits)
    except WarrantError as refused:
        return {"attempt": name, "verdict": REFUSED, "code": refused.code,
                "detail": "a limit the warrant stated and this platform "
                          "cannot apply is refused rather than run. For an "
                          "unenforceable limit, refusing IS the control"}
    except Exception as broken:
        return {"attempt": name, "verdict": HARNESS_ERROR,
                "error": f"{type(broken).__name__}: {broken}",
                "detail": "the harness failed before the claim was tested"}
    return {"attempt": name, "verdict": NOT_HELD,
            "detail": "a stated memory cap was accepted on a host that cannot "
                      "impose one. That is the platform asserting compliance "
                      "with a control it did not exercise"}

def _short(value: Any) -> Any:
    text = json.dumps(value, default=str)
    return json.loads(text) if len(text) < 400 else text[:400]


def _detail(results: List[Dict[str, Any]], rlimits: bool,
            not_held: List[str]) -> str:
    out = (f"{len(results)} attempt(s) tried. "
           + ", ".join(f"{r['attempt']}: {r['verdict']}" for r in results))
    broken = [r["attempt"] for r in results
              if r["verdict"] == HARNESS_ERROR]
    if broken:
        out += (f". **{len(broken)} attempt(s) never ran — the harness "
                f"failed**: " + ", ".join(broken) + ". This is not evidence "
                "about the sandbox in either direction, and it is reported as "
                "loudly as a failure because a spike that cannot tell a held "
                "boundary from a broken test produces a green result and a "
                "false belief")
    if not_held:
        out += (f". **{len(not_held)} did not hold and were expected to**: "
                + ", ".join(not_held) + ". That is a finding rather than a "
                "measurement, and it belongs in front of whoever owns the "
                "execution path")
    if not rlimits:
        out += (". POSIX resource limits are unavailable on this host, so cpu "
                "and memory bounds cannot be enforced — a warrant STATING one "
                "should be refused rather than run, and `refused` above is a "
                "pass rather than a failure")
    out += (". This is NOT a penetration test and running it is not "
            "NFR-SEC-001's annual engagement by another name. It is a "
            "regression suite for a boundary the module already documents, "
            "and its value is that those sentences stop being unexamined. "
            "`escape_import` and `filesystem_write` are expected to succeed: "
            "a spawned child is honestly scoped and is not a jail, and "
            "containment is the deployment's job — a read-only root and a "
            "dropped capability set, which `deploy/` provides")
    return out


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.spikes.sandbox_escape")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args(argv)
    result = run(args.timeout)
    print(json.dumps(result, indent=2))
    print("\n" + result["detail"], file=sys.stderr)
    return 0 if not result["did_not_hold"] else 1


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(main())
