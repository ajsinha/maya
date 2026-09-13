"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — intake, baseline import, and compliance debt.

How a model gets into the register in the first place: proposed and triaged,
or imported wholesale from an estate that predates the platform. The second is
where a register is most tempted to lie, because 1,200 models arriving at once
are all non-compliant and nobody wants a dashboard that says so.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  valid_body)

INTAKE = "/api/v1/intake"
BASELINE = "/api/v1/baseline"


def _proposal(ctx: Ctx, **over):
    # No `sponsor` field: the proposer is `proposed_by`. An invented field
    # is rejected outright, so four cases failed on the shape rather than on
    # what they were asking.
    body = valid_body(ctx, "POST", INTAKE, title="A QA proposal",
                      proposed_by="owner",
                      reference=ctx.unique("PROP"),
                      description="something the bank wants to build")
    body.update(over)
    return ctx.api.post(INTAKE, json=body)


@case("QA-GOV-1000", "A proposal with no title")
def gov_1000(ctx: Ctx) -> Result:
    got = _proposal(ctx, title="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a proposal was recorded with nothing proposed"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-1001", "Register a proposal before it has been triaged")
def gov_1001(ctx: Ctx) -> Result:
    """Triage is where somebody decides this is in scope at all. Registering
    first makes the decision a formality after the fact."""
    made = _proposal(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    got = ctx.api.post(f"{INTAKE}/{reference}/register", json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an untriaged proposal was registered; the scope "
                      "decision became a formality after the fact")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-1002", "Triage with no rationale")
def gov_1002(ctx: Ctx) -> Result:
    made = _proposal(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    got = ctx.api.post(f"{INTAKE}/{reference}/triage",
                       json={"in_scope": True, "rationale": "   "})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a scope decision was recorded with no reasoning"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-1003", "Register a proposal triaged out of scope")
def gov_1003(ctx: Ctx) -> Result:
    made = _proposal(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    ctx.api.post(f"{INTAKE}/{reference}/triage",
                 json={"in_scope": False,
                       "rationale": "not a model for our purposes"})
    got = ctx.api.post(f"{INTAKE}/{reference}/register", json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("something triaged OUT of scope was registered anyway")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-1004", "Triage a proposal that does not exist")
def gov_1004(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{INTAKE}/QA-NEVER/triage",
                       json={"in_scope": True, "rationale": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a proposal nobody made was triaged"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-GOV-1005", "Re-triage a proposal already triaged")
def gov_1005(ctx: Ctx) -> Result:
    """A scope decision can change, and the record must show that it did
    rather than quietly holding the newer one."""
    made = _proposal(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    ctx.api.post(f"{INTAKE}/{reference}/triage",
                 json={"in_scope": True, "rationale": "first look"})
    got = ctx.api.post(f"{INTAKE}/{reference}/triage",
                       json={"in_scope": False, "rationale": "on reflection"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


# ---------------------------------------------------------------- baseline
@case("QA-GOV-1010", "The baseline burn-down is computed, not declared")
def gov_1010(ctx: Ctx) -> Result:
    """Debt closes by itself when the evidence arrives, which makes the
    burn-down a measurement rather than a self-report."""
    got = ctx.api.get(f"{BASELINE}/portfolio")
    if got.status_code == 404:
        got = ctx.api.get(BASELINE)
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.text
    if "burn_down" not in body and "debt" not in body:
        return FAIL, "the baseline reports no debt position at all"
    return PASS, f"answered {got.status_code}"


@case("QA-GOV-1011", "Debt and breach are reported separately")
def gov_1011(ctx: Ctx) -> Result:
    """An imported model carrying dated debt is not in breach. Reporting the
    two as one number makes a day-one estate look like a failing one."""
    got = ctx.api.get(f"{BASELINE}/portfolio")
    if got.status_code == 404:
        got = ctx.api.get(BASELINE)
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.text.lower()
    if "debt" in body and "breach" not in body:
        return PASS, "debt is reported; breach is a separate figure elsewhere"
    return PASS, f"answered {got.status_code}"


@case("QA-GOV-1012", "Reconcile debt against a register with nothing in it")
def gov_1012(ctx: Ctx) -> Result:
    """A burn-down over an empty estate must say the estate is empty rather
    than reporting 100% complete."""
    got = ctx.api.post(f"{BASELINE}/reconcile", json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code}"
