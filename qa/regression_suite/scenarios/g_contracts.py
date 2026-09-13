"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the contract algebra: refinement, composition, quotient.

The source records what went wrong here, and it is the sharpest arithmetic
defect in the platform: "`⊗`, `∧` and `/` were three names for one line of
code — concatenate both tuples. Three operations that answer three different
questions returned the same answer to all of them", and `/` discharged a
requirement whenever the partner MENTIONED the key, so a challenger promising
`gini >= 0.2` satisfied a target of `gini >= 0.4`.
"""
from __future__ import annotations

from core.domain.contracts import Bound, Contract, ContractError
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _c(assumptions=(), guarantees=()) -> Contract:
    return Contract(assumptions=tuple(assumptions),
                    guarantees=tuple(guarantees))


@case("QA-FX-5100", "A weaker bound admits everything the stronger one does")
def fx_5100(ctx: Ctx) -> Result:
    """The relation everything else is written in terms of. If it is wrong
    once, refinement and composition are both wrong everywhere."""
    wide = Bound("x", minimum=0.0, maximum=100.0)
    narrow = Bound("x", minimum=10.0, maximum=50.0)
    if not wide.weaker_than(narrow):
        return FAIL, "a wider band is not weaker than a narrower one"
    if narrow.weaker_than(wide):
        return FAIL, "a narrower band reports as weaker than a wider one"
    if not wide.weaker_than(wide):
        return FAIL, "a band is not weaker-or-equal to itself"
    unbounded = Bound("x")
    if not unbounded.weaker_than(wide):
        return FAIL, ("an unbounded assumption is not weaker than a bounded "
                      "one, and an absent constraint is the weakest there is")
    return PASS, "wider is weaker, and unbounded is weakest"


@case("QA-FX-5101", "A refinement that weakens an assumption holds")
def fx_5101(ctx: Ctx) -> Result:
    """`C' <= C iff A subset A'`. Promising to work on MORE inputs is a
    stronger promise, so a wider assumption refines a narrower one."""
    original = _c([Bound("x", minimum=10.0, maximum=50.0)],
                  [Bound("gini", minimum=0.4)])
    better = _c([Bound("x", minimum=0.0, maximum=100.0)],
                [Bound("gini", minimum=0.5)])
    result = better.refines(original)
    if not result.holds:
        return FAIL, (f"a contract with wider assumptions and stronger "
                      f"guarantees does not refine: assumptions "
                      f"{result.assumption_failures}, guarantees "
                      f"{result.guarantee_failures}")
    return PASS, "wider assumptions and stronger guarantees refine"


@case("QA-FX-5102", "A refinement that narrows an assumption does not")
def fx_5102(ctx: Ctx) -> Result:
    """Working on FEWER inputs is a weaker promise, however good the
    guarantee."""
    original = _c([Bound("x", minimum=0.0, maximum=100.0)],
                  [Bound("gini", minimum=0.4)])
    narrower = _c([Bound("x", minimum=10.0, maximum=50.0)],
                  [Bound("gini", minimum=0.9)])
    result = narrower.refines(original)
    if result.holds:
        return FAIL, ("a contract that works on a narrower range of inputs "
                      "was accepted as a refinement because its guarantee is "
                      "better")
    if "x" not in result.assumption_failures:
        return FAIL, f"the failure does not name x: {result}"
    return PASS, f"refused, naming {result.assumption_failures}"


@case("QA-FX-5103", "A guarantee withdrawn is not a refinement")
def fx_5103(ctx: Ctx) -> Result:
    """"An absent guarantee is a promise withdrawn" — the asymmetry with
    assumptions, where absent is weakest."""
    original = _c(guarantees=[Bound("gini", minimum=0.4)])
    silent = _c()
    result = silent.refines(original)
    if result.holds:
        return FAIL, ("a contract promising nothing refines one promising "
                      "gini >= 0.4")
    if "gini" not in result.guarantee_failures:
        return FAIL, f"the failure does not name the withdrawn promise: {result}"
    return PASS, "an absent guarantee fails refinement"


@case("QA-FX-5104", "An absent assumption is the weakest, not a failure")
def fx_5104(ctx: Ctx) -> Result:
    """The other half of the asymmetry. "Promising to work without
    constraining x is stronger than promising it only on a band." """
    original = _c([Bound("x", minimum=10.0, maximum=50.0)],
                  [Bound("gini", minimum=0.4)])
    unconstrained = _c(guarantees=[Bound("gini", minimum=0.4)])
    result = unconstrained.refines(original)
    if not result.holds:
        return FAIL, (f"a contract that constrains nothing does not refine "
                      f"one that constrains x: {result.assumption_failures}")
    return PASS, "an absent assumption refines a bounded one"


@case("QA-FX-5105", "Composition discharges what the upstream guarantees")
def fx_5105(ctx: Ctx) -> Result:
    """"That discharge is the entire difference between composition and
    concatenation." A downstream assumption the upstream's guarantee already
    implies is not asked of the caller."""
    upstream = _c([Bound("raw", minimum=0.0)],
                  [Bound("score", minimum=0.0, maximum=1.0)])
    downstream = _c([Bound("score", minimum=0.0, maximum=1.0)],
                    [Bound("decision", allowed=("approve", "refer"))])
    composed = upstream.compose(downstream)
    keys = {b.key for b in composed.assumptions}
    if "score" in keys:
        return FAIL, ("`score` is still asked of the caller although the "
                      "upstream guarantees it; composition concatenated "
                      "rather than discharged")
    if "raw" not in keys:
        return FAIL, "the upstream's own assumption was dropped"
    guarantees = {b.key for b in composed.guarantees}
    if guarantees != {"score", "decision"}:
        return FAIL, f"the composite guarantees {guarantees}"
    return PASS, f"assumptions {keys}, guarantees {guarantees}"


@case("QA-FX-5106", "Composition does not discharge a weaker guarantee")
def fx_5106(ctx: Ctx) -> Result:
    """The `/` defect in its composition form. An upstream that merely
    MENTIONS the key must not satisfy a stricter downstream assumption."""
    upstream = _c(guarantees=[Bound("score", minimum=0.0, maximum=100.0)])
    downstream = _c([Bound("score", minimum=0.0, maximum=1.0)])
    try:
        composed = upstream.compose(downstream)
    except ContractError:
        return PASS, "refused: the guarantee does not meet the assumption"
    keys = {b.key for b in composed.assumptions}
    if "score" not in keys:
        return FAIL, ("a guarantee of 0..100 discharged an assumption of "
                      "0..1 because it mentioned the same key; the caller is "
                      "now asked for nothing and the pair is unsound")
    return PASS, "the stricter assumption survives as the caller's"


@case("QA-FX-5107", "The working is shown")
def fx_5107(ctx: Ctx) -> Result:
    """`composed_with` reports what was discharged and what could not be. A
    composite whose derivation is invisible is one nobody can argue with."""
    upstream = _c(guarantees=[Bound("score", minimum=0.0, maximum=1.0)])
    downstream = _c([Bound("score", minimum=0.0, maximum=1.0),
                     Bound("tenure", minimum=1.0)])
    # `Composition` carries `contract`, `discharged` and `unmet` — what the
    # caller still supplies is read off the composite's own assumptions.
    working = upstream.composed_with(downstream)
    discharged = {getattr(b, "key", b) for b in (working.discharged or ())}
    still = {b.key for b in working.contract.assumptions}
    if "score" not in discharged:
        return FAIL, f"the discharge is not reported: {working}"
    if "tenure" not in still:
        return FAIL, ("an assumption nothing upstream speaks to is not "
                      "reported as still the caller's")
    return PASS, f"discharged {discharged}, still the caller's {still}"


@case("QA-FX-5108", "The three operations are not one operation")
def fx_5108(ctx: Ctx) -> Result:
    """The recorded defect: "`⊗`, `∧` and `/` were three names for one line of
    code — concatenate both tuples. Three operations that answer three
    different questions returned the same answer to all of them."

    Tested by ASKING them, rather than by reading their source: `compose`
    delegates to `composed_with`, so a source scan for a lattice call finds
    nothing and reports a correct implementation as broken.
    """
    upstream = _c([Bound("raw", minimum=0.0)],
                  [Bound("score", minimum=0.0, maximum=1.0)])
    downstream = _c([Bound("score", minimum=0.0, maximum=1.0)],
                    [Bound("decision", allowed=("approve", "refer"))])

    def shape(contract) -> tuple:
        return (tuple(sorted(b.key for b in contract.assumptions)),
                tuple(sorted(b.key for b in contract.guarantees)))

    answers = {"compose": shape(upstream.compose(downstream))}
    try:
        answers["conjoin"] = shape(upstream.conjoin(downstream))
    except ContractError as exc:
        answers["conjoin"] = ("refused", str(exc)[:20])
    try:
        answers["quotient"] = shape(upstream.quotient(downstream))
    except ContractError as exc:
        answers["quotient"] = ("refused", str(exc)[:20])
    if len(set(answers.values())) == 1:
        return FAIL, (f"compose, conjoin and quotient all answer "
                      f"{answers['compose']}; three questions, one answer")
    if answers["compose"] == answers["conjoin"]:
        return FAIL, ("compose and conjoin agree: the discharge that is the "
                      "entire difference between them did not happen")
    return PASS, f"three distinct answers: {answers}"


@case("QA-FX-5109", "A lattice operation that does not exist is refused")
def fx_5109(ctx: Ctx) -> Result:
    """"Both are PARTIAL, and both say so by returning `None` rather than
    something adjacent." Two disjoint bands have no meet, and inventing one
    would be a contract nobody wrote."""
    low = Bound("x", minimum=0.0, maximum=10.0)
    high = Bound("x", minimum=90.0, maximum=100.0)
    met = low.meet(high) if hasattr(low, "meet") else "missing"
    if met == "missing":
        return FAIL, "there is no meet to test"
    if met is not None:
        return FAIL, (f"two disjoint bands produced a meet of {met}; the "
                      f"operation does not exist and something adjacent was "
                      f"returned")
    overlapping = Bound("x", minimum=5.0, maximum=95.0)
    if low.meet(overlapping) is None:
        return FAIL, "two overlapping bands have no meet"
    return PASS, "disjoint bands have no meet; overlapping ones do"
