"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — point-in-time assembly, in two layers that prove different things.

Layer 1 refuses an assembly lacking either temporal bound, and that is a proof
about the data. Layer 2 recomputes a sample by a second route — and the module
says plainly what that is worth: "this catches implementation drift between
two paths rather than a wrong rule. Both would be wrong together." A platform
that let the second stand for the first would be claiming the stronger thing.
"""
from __future__ import annotations

from core.features.pit import (AssemblyRequest, static_check,
                               verify_sampled)
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _flat(text: str) -> str:
    """Prose with its line breaks removed.

    A docstring wraps, so `"implementation drift" in doc` is False when the
    source reads `implementation\ndrift`. Searching a wrapped paragraph for
    an unwrapped phrase reports a statement as absent when it is there — the
    same token trap as matching a name instead of a call.
    """
    return " ".join((text or "").split())


def _request(**over) -> AssemblyRequest:
    body = {"spine": [], "views": [], "as_of": 1000.0,
            "valid_time_bound": True, "transaction_time_bound": True}
    body.update(over)
    return AssemblyRequest(**body)


@case("QA-FX-026", "An assembly with no valid-time bound")
def fx_026(ctx: Ctx) -> Result:
    """Without a bound on when a fact was TRUE, a feature can carry a value
    the world only reached after the label did."""
    report = static_check(_request(valid_time_bound=False))
    if report.passed:
        return FAIL, "an assembly with no valid-time bound was admitted"
    if "valid_time" not in report.detail:
        return FAIL, f"the refusal does not name the bound: {report.detail}"
    return PASS, report.detail


@case("QA-FX-027", "An assembly with no transaction-time bound")
def fx_027(ctx: Ctx) -> Result:
    """Without a bound on when a fact was KNOWN, a feature can carry a value
    the firm had not yet recorded — a correction applied in hindsight."""
    report = static_check(_request(transaction_time_bound=False))
    if report.passed:
        return FAIL, "an assembly with no transaction-time bound was admitted"
    if "transaction_time" not in report.detail:
        return FAIL, f"the refusal does not name the bound: {report.detail}"
    return PASS, report.detail


@case("QA-FX-028", "Both bounds missing")
def fx_028(ctx: Ctx) -> Result:
    """One message naming both. Reporting the first and stopping makes fixing
    an assembly a sequence of round trips."""
    report = static_check(_request(valid_time_bound=False,
                                   transaction_time_bound=False))
    if report.passed:
        return FAIL, "an assembly with neither bound was admitted"
    for bound in ("valid_time", "transaction_time"):
        if bound not in report.detail:
            return FAIL, (f"the refusal names only one bound, so fixing it "
                          f"takes two attempts: {report.detail}")
    return PASS, report.detail


@case("QA-FX-3900", "Both bounds present")
def fx_3900(ctx: Ctx) -> Result:
    """The refusal has to admit the legitimate case, or nothing assembles."""
    report = static_check(_request())
    if not report.passed:
        return FAIL, f"a bounded assembly was refused: {report.detail}"
    if not report.detail.strip():
        return FAIL, "the passing report says nothing"
    return PASS, report.detail


@case("QA-FX-3901", "Layer 2 over nothing is not a verification")
def fx_3901(ctx: Ctx) -> Result:
    """An empty frame gives a passing sampled report — correctly, since there
    is nothing to disagree with — and must say so rather than implying rows
    were checked."""
    report = verify_sampled([], lambda row: {})
    if not report.passed:
        return FAIL, "an empty frame failed verification"
    # `checked`, not `sampled` — the field counts what was compared.
    if report.checked:
        return FAIL, f"an empty frame reports {report.checked} checked"
    if "nothing" not in report.detail:
        return FAIL, f"the report does not say it checked nothing: {report.detail}"
    return PASS, report.detail


@case("QA-FX-3902", "Layer 2 catches a row that disagrees")
def fx_3902(ctx: Ctx) -> Result:
    """The thing it does prove: the two paths still agree."""
    rows = [{"entity_id": f"e{i}", "label": i % 2, "x": float(i)}
            for i in range(20)]
    rows[7]["x"] = -999.0
    report = verify_sampled(rows, lambda row: {"x": float(
        int(row["entity_id"][1:]))}, sample=20)
    if report.passed:
        return FAIL, ("a row whose value disagrees with the second route was "
                      "verified as correct")
    if not report.violations:
        return FAIL, "the failure names no violating row"
    if report.violations[0].get("entity_id") != "e7":
        return FAIL, f"the wrong row was named: {report.violations[0]}"
    for field in ("assembled", "expected"):
        if field not in report.violations[0]:
            return FAIL, f"the violation does not carry '{field}'"
    return PASS, f"{len(report.violations)} violation(s), naming e7"


@case("QA-FX-3903", "Layer 2 reports comparisons, not rows")
def fx_3903(ctx: Ctx) -> Result:
    """"`N of M rows independently recomputed` counted rows SAMPLED, not
    comparisons MADE, and those differ by exactly the amount that matters."
    A row with one feature and a row with forty are not the same evidence.
    """
    rows = [{"entity_id": f"e{i}", "label": i % 2, "a": float(i),
             "b": float(i), "c": float(i)} for i in range(10)]

    def recompute(row):
        n = float(int(row["entity_id"][1:]))
        return {"a": n, "b": n, "c": n}

    report = verify_sampled(rows, recompute, sample=10)
    if not report.passed:
        return FAIL, f"a consistent frame failed: {report.detail}"
    numbers = [int(t) for t in report.detail.replace("(", " ")
               .replace(")", " ").replace(",", " ").split() if t.isdigit()]
    if 30 not in numbers:
        return FAIL, (f"ten rows of three features each were reported as "
                      f"{report.detail!r}; the comparison count (30) is what "
                      f"says how much was actually checked")
    return PASS, report.detail


@case("QA-FX-3904", "What layer 2 proves is stated, not implied")
def fx_3904(ctx: Ctx) -> Result:
    """The second route applies the same bound as the assembler — which is
    right, the two must not diverge — and means this catches drift between
    two paths rather than a wrong rule. Claiming more would make the weaker
    check stand for the stronger one.
    """
    import inspect
    doc = _flat(inspect.getdoc(verify_sampled))
    for phrase in ("implementation drift", "wrong rule"):
        if phrase not in doc:
            return FAIL, (f"the sampled check does not record what it proves "
                          f"('{phrase}' absent), so a reader may take it for "
                          f"a proof about the data")
    if "Layer 1" not in doc:
        return FAIL, "it does not point at the check that does prove something"
    return PASS, "what it proves, and what it does not, are both written down"


@case("QA-FX-3905", "The sample size and the strata are stated")
def fx_3905(ctx: Ctx) -> Result:
    """"`_stratified` buckets on the label value and nothing else. This said
    strata span label period, entity and label value — a claim the deck
    repeated from here, and neither was true." A sampling claim that is wrong
    is worse than none."""
    import inspect
    doc = _flat(inspect.getdoc(verify_sampled))
    if "label value" not in doc:
        return FAIL, "the strata are not stated"
    if "no power computation" not in doc.lower():
        return FAIL, ("the sample size is presented without saying it rests "
                      "on no power computation")
    rows = [{"entity_id": f"e{i}", "label": i % 2, "x": float(i)}
            for i in range(500)]
    report = verify_sampled(rows, lambda row: {"x": row["x"]}, sample=200)
    if report.checked > 200:
        return FAIL, (f"{report.checked} comparisons against a 200-row "
                      f"sample limit")
    return PASS, f"{report.checked} comparison(s) over {len(rows)} rows"
