"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the captive engine and its sandbox.

MAYA is a register and does not run models; the captive engine is the
deliberate exception, off by default, for the case where a firm wants the
reference implementation. So the cases here are about what it refuses to run
and what it refuses to CLAIM — "the artifact ran under a 512 MB cap" has to be
something the platform observed rather than something it intended.
"""
from __future__ import annotations

from core.execution.sandbox import (DEFAULT_MEMORY_MB, DEFAULT_SECONDS,
                                    RLIMITS, Limits)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

E = "/api/v1/engine"


def _warrant(**resources) -> dict:
    return {"constraints": {"resources": dict(resources)}}


@case("QA-FX-425", "`GET /api/v1/engine` with the captive engine disabled")
def fx_425(ctx: Ctx) -> Result:
    """Off by default is the design, and a caller has to be able to tell
    "not enabled" from "broken"."""
    got = ctx.api.get(E, auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return FAIL, (f"the engine endpoint refuses '{code_of(got)}' rather "
                      f"than reporting its own state, so disabled and broken "
                      f"look the same")
    body = got.json() or {}
    if "enabled" not in str(body).lower():
        return FAIL, f"the answer does not say whether it is on: {str(body)[:120]}"
    return PASS, f"reports its state: {str(body.get('detail') or body)[:90]}"


@case("QA-FX-426", "Executing with the captive engine disabled")
def fx_426(ctx: Ctx) -> Result:
    """The refusal has to say this INSTANCE does not run models, not that the
    request was wrong."""
    got = ctx.api.post("/api/v1/execute",
                       json={"urn": "maya://model/qa.never",
                             "principal": "svc-pricing",
                             "declared_use": "credit_decision",
                             "environment": "prod", "inputs": {}},
                       auth=ctx.people["owner"])
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got) or got.status_code}'"
    return PASS, "the captive engine is enabled on this instance"


@case("QA-FX-421", "A memory limit stated in the warrant")
def fx_421(ctx: Ctx) -> Result:
    """A default is MAYA's own conservative choice; a figure written into a
    warrant is a constraint somebody signed for. The two must be
    distinguishable, or "ran under a cap" means nothing."""
    limits = Limits.of(_warrant())
    if limits.declared:
        return FAIL, (f"a warrant stating no resources reports "
                      f"{limits.declared} as declared by the warrant")
    if limits.seconds != DEFAULT_SECONDS or limits.memory_mb != DEFAULT_MEMORY_MB:
        return FAIL, (f"the defaults are not the platform's: "
                      f"{limits.seconds}s / {limits.memory_mb}MB")
    stated = Limits.of(_warrant(max_seconds=5, max_memory_mb=64))
    if set(stated.declared) != {"max_seconds", "max_memory_mb"}:
        return FAIL, (f"a warrant stating both limits reports "
                      f"{stated.declared} as declared")
    return PASS, ("a default and a signed-for figure are held apart in "
                  "`declared_by_the_warrant`")


@case("QA-FX-422", "A limit the platform cannot enforce is named")
def fx_422(ctx: Ctx) -> Result:
    """Running an artifact while silently not applying a stated limit would
    be the platform asserting compliance with a control it did not exercise.
    """
    stated = Limits.of(_warrant(max_seconds=5, max_memory_mb=64))
    cannot = stated.unenforceable()
    if RLIMITS:
        if cannot:
            return FAIL, (f"rlimits are available here and yet {cannot} is "
                          f"reported unenforceable")
        return PASS, "rlimits available; both stated limits are enforceable"
    if "max_memory_mb" not in cannot:
        return FAIL, ("no rlimits here, and a stated memory cap is not "
                      "reported unenforceable — the platform would claim a "
                      "cap it cannot apply")
    if "max_seconds" in cannot:
        return FAIL, ("a stated wall-clock limit is reported unenforceable "
                      "although the parent still bounds it; calling it "
                      "unenforced is the opposite error")
    return PASS, f"unenforceable here: {cannot}"


@case("QA-FX-3100", "A warrant stating nothing has nothing unenforceable")
def fx_3100(ctx: Ctx) -> Result:
    """"Cannot enforce" is about what somebody was PROMISED. With no stated
    limit there is no promise, so reporting one would manufacture a gap."""
    bare = Limits.of(_warrant())
    if bare.unenforceable():
        return FAIL, (f"a warrant stating no limits reports "
                      f"{bare.unenforceable()} as unenforceable, so every "
                      f"execution carries a gap nobody was promised")
    return PASS, "no statement, no gap"


@case("QA-FX-3101", "A resource limit of zero is not a limit")
def fx_3101(ctx: Ctx) -> Result:
    """`resources.get(key)` is falsy at zero, so a zero limit falls to the
    default rather than being recorded as a constraint. That is the right
    reading — a zero-second budget is not a budget — and the case pins it so
    it cannot become a silent zero cap."""
    zeroed = Limits.of(_warrant(max_seconds=0, max_memory_mb=0))
    if zeroed.declared:
        return FAIL, (f"a zero limit was recorded as declared: "
                      f"{zeroed.declared}")
    if zeroed.seconds <= 0 or zeroed.memory_mb <= 0:
        return FAIL, (f"a zero limit became the applied budget: "
                      f"{zeroed.seconds}s / {zeroed.memory_mb}MB")
    return PASS, f"zero falls to {zeroed.seconds}s / {zeroed.memory_mb}MB"


@case("QA-FX-424", "A callable runtime is not sandboxed, and says so")
def fx_424(ctx: Ctx) -> Result:
    """You cannot sandbox a function somebody handed you in-process. The
    engine reporting that honestly is the control; claiming otherwise would
    be worse than not having one."""
    import inspect

    from core.execution import sandbox
    source = inspect.getsource(sandbox)
    if "cannot sandbox" not in source.lower():
        return FAIL, ("the sandbox does not record that an in-process "
                      "callable is unsandboxable")
    got = ctx.api.get(E, auth=ctx.people["risk"])
    if got.status_code < 400 and "sandbox" not in got.text.lower():
        return FAIL, ("the engine's posture says nothing about sandboxing, so "
                      "a caller cannot tell what was isolated")
    return PASS, "an in-process callable is stated to be unsandboxed"


@case("QA-FX-6119", "The CPU cap is the process's usage plus the budget")
def fx_423(ctx: Ctx) -> Result:
    """A measured defect worth a permanent case. `RLIMIT_CPU` is CUMULATIVE
    from process start, and setting it to the budget flat spent the
    interpreter's own start-up — 3.3 CPU-seconds just to import the package —
    out of the model's allowance. A warrant asking for two seconds killed the
    artifact before it ran an instruction, and a TIGHTER budget made it more
    likely, which is the opposite of what the warrant's author was doing.
    """
    import inspect

    from core.execution import sandbox
    source = inspect.getsource(sandbox._apply_limits)
    # The CODE, not the docstring. The paragraph above this function narrates
    # the defect at length and mentions `RLIMIT_CPU` several times, so a scan
    # of the whole source finds the explanation rather than the fix — and
    # reports a repaired control as broken.
    doc = inspect.getdoc(sandbox._apply_limits) or ""
    body = "\n".join(ln for ln in source.splitlines()
                     if ln.strip() and ln.strip() not in doc)
    setting = [ln for ln in body.splitlines() if "RLIMIT_CPU" in ln]
    if not setting:
        return BLOCKED, "no CPU limit is applied on this platform"
    budget = [ln for ln in body.splitlines()
              if "soft_cpu" in ln and "=" in ln and "setrlimit" not in ln]
    if not budget:
        return FAIL, f"the CPU budget is computed nowhere: {setting}"
    if "+" not in budget[0]:
        return FAIL, ("the CPU cap is set to the budget flat rather than to "
                      "current usage plus the budget, so the interpreter's "
                      "start-up is spent out of the model's allowance: "
                      + budget[0].strip())
    return PASS, f"cumulative: {budget[0].strip()}"


@case("QA-FX-3102", "What was applied is reported, not what was intended")
def fx_3102(ctx: Ctx) -> Result:
    """On a system without rlimits, "the artifact ran under a 512 MB cap" and
    "we asked for a 512 MB cap" are different statements and only one is
    evidence."""
    import inspect

    from core.execution import sandbox
    source = inspect.getsource(sandbox._apply_limits)
    if "Returns what was ACTUALLY applied" not in inspect.getdoc(
            sandbox._apply_limits):
        return FAIL, ("the limit application does not state that it returns "
                      "what was applied rather than what was asked")
    if "return" not in source:
        return FAIL, "nothing is returned, so nothing can be reported back"
    return PASS, "the applied limits are returned for the parent to record"
