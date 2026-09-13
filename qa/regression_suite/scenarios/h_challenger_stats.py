"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — comparing a challenger against the model in production.

**The recommendation is never to promote.** MAYA is a register: it does not
run models and it does not decide which one a bank uses. Promotion is a
second-line approval, and the strongest thing this comparison can say is that
the evidence for LOOKING is strong.

Everything else follows from the paired test being honest. Observations are
matched on the WINDOW they name rather than on the order they were written,
because two monitors on different schedules produce interleaved histories and
zipping them would pair last quarter against this one. Below five pairs
nothing is tested at all — four windows agreeing is a coin landing the same
way four times, and a p-value for it would lend arithmetic authority to a
coincidence.
"""
from __future__ import annotations

from core.monitoring.challengers import (
    ALPHA,
    APPROXIMATE,
    CHALLENGER_AHEAD,
    CHAMPION_AHEAD,
    EXACT,
    EXACT_UP_TO,
    INSUFFICIENT,
    MINIMUM_PAIRS,
    NO_DIFFERENCE,
    _sign_flip_p,
    _verdict,
)
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


@case("QA-AM-277", "Five paired windows, exactly")
def am_277(ctx: Ctx) -> Result:
    """The floor is inclusive, and at five the test is EXACT: the sign-flip
    distribution is enumerable, so the p-value is counted rather than
    approximated."""
    if MINIMUM_PAIRS != 5:
        return FAIL, f"the documented floor is five and the constant is {MINIMUM_PAIRS}"
    diffs = [0.1, 0.2, 0.15, 0.05, 0.12]
    p, method = _sign_flip_p(diffs)
    if method != EXACT:
        return FAIL, f"five pairs used '{method}' rather than the exact test"
    if not 0.0 <= p <= 1.0:
        return FAIL, f"the p-value is {p}"
    if p != 1.0 / (2 ** 5) * 2 and p > 0.1:
        return FAIL, (f"five differences all the same sign gave p={p}, which "
                      f"is not what enumerating 32 sign flips produces")
    return PASS, f"five pairs, exact enumeration, p={p}"


@case("QA-AM-278", "Fifteen paired windows")
def am_278(ctx: Ctx) -> Result:
    """Past the enumerable bound the normal approximation takes over, and
    the method is REPORTED — two p-values computed differently should not
    print the same without saying so."""
    if EXACT_UP_TO >= 15:
        return FAIL, (f"fifteen pairs are still enumerated: EXACT_UP_TO is "
                      f"{EXACT_UP_TO}")
    diffs = [0.1 + i * 0.01 for i in range(15)]
    _p, method = _sign_flip_p(diffs)
    if method != APPROXIMATE:
        return FAIL, f"fifteen pairs used '{method}'"
    at_bound = _sign_flip_p([0.1] * EXACT_UP_TO)[1]
    if at_bound != EXACT:
        return FAIL, (f"exactly {EXACT_UP_TO} pairs used '{at_bound}' rather "
                      f"than the exact test, so the bound is not inclusive")
    over = _sign_flip_p([0.1] * (EXACT_UP_TO + 1))[1]
    if over != APPROXIMATE:
        return FAIL, f"{EXACT_UP_TO + 1} pairs used '{over}'"
    return PASS, (f"exact up to {EXACT_UP_TO} inclusive, approximate above, "
                  f"and the method is named")


@case("QA-AM-281",
      "Every paired difference identical and non-zero, over twenty windows")
def am_281(ctx: Ctx) -> Result:
    """Zero variance and a non-zero mean. The normal approximation divides by
    the standard deviation, so this is the case that would raise — it must
    answer a p-value of 0.0 rather than crash, because twenty identical
    differences is the strongest evidence the test can see."""
    p, method = _sign_flip_p([0.25] * 20)
    if method != APPROXIMATE:
        return FAIL, f"twenty pairs used '{method}'"
    if p != 0.0:
        return FAIL, (f"twenty identical non-zero differences gave p={p}; "
                      f"zero variance with a non-zero mean is the strongest "
                      f"evidence available")
    flat, _ = _sign_flip_p([0.0] * 20)
    if flat != 1.0:
        return FAIL, (f"twenty differences of exactly zero gave p={flat}; no "
                      f"difference at all is the weakest evidence, not the "
                      f"strongest")
    return PASS, "identical non-zero gives 0.0, identical zero gives 1.0"


@case("QA-AM-284", "Any comparison at all")
def am_284(ctx: Ctx) -> Result:
    """The recommendation is never 'promote'. MAYA does not decide which
    model the bank uses, and a promotion needs a second-line approval this
    must not pre-empt — so the strongest verdict available is *the challenger
    is ahead*, whose action is to open a validation."""
    verdicts = set()
    for significant in (True, False):
        for material in (True, False):
            for mean in (0.5, -0.5, 0.0):
                verdicts.add(_verdict(significant, material, mean))
    forbidden = [v for v in verdicts
                 if "promote" in f"{v}".lower() or "switch" in f"{v}".lower()]
    if forbidden:
        return FAIL, (f"a comparison can recommend {forbidden}: MAYA does not "
                      f"decide which model the bank uses")
    if CHALLENGER_AHEAD not in verdicts:
        return FAIL, f"the challenger can never be reported ahead: {verdicts}"
    if NO_DIFFERENCE not in verdicts:
        return FAIL, "no combination reports no material difference"
    return PASS, f"the reachable verdicts are {sorted(verdicts)}, none a promotion"


@case("QA-AM-283",
      "A challenger ahead on one test and behind on another")
def am_283(ctx: Ctx) -> Result:
    """A model better at one thing and worse at another is a trade-off, and
    a trade-off is a judgement somebody has to make rather than a number. So
    the verdict is *no material difference* and the ACTION is still to open a
    validation — the two are separate, and collapsing them would either hide
    the trade-off or overstate it."""
    from core.monitoring.challengers import ChampionChallenger
    tests = [{"tested": True, "recommendation": CHALLENGER_AHEAD},
             {"tested": True, "recommendation": CHAMPION_AHEAD}]
    got = ChampionChallenger._recommend(tests)
    if got["verdict"] != NO_DIFFERENCE:
        return FAIL, f"the verdict is {got['verdict']!r}"
    if "no action" in (got.get("action") or ""):
        return FAIL, ("a trade-off is reported with no action, so the "
                      "disagreement between the tests goes unexamined")
    if "trade-off" not in (got.get("detail") or ""):
        return FAIL, f"the detail does not name the trade-off: {got.get('detail')}"
    ahead_only = ChampionChallenger._recommend(
        [{"tested": True, "recommendation": CHALLENGER_AHEAD}])
    if ahead_only["verdict"] != CHALLENGER_AHEAD:
        return FAIL, "a challenger ahead on every test is not reported ahead"
    if "second-line" not in (ahead_only.get("detail") or ""):
        return FAIL, ("the strongest verdict does not say promotion is a "
                      "second-line approval")
    return PASS, (f"trade-off -> {got['verdict']} with '{got['action']}'; "
                  f"clean win -> {ahead_only['verdict']}")


@case("QA-AM-4890", "A comparison where no test could run")
def am_4890(ctx: Ctx) -> Result:
    """*Not enough evidence* and *no difference* are different answers, and
    only one of them means the challenger was measured. Reporting the first
    as the second is how a challenger nobody could compare reads as a
    challenger that made no difference."""
    from core.monitoring.challengers import ChampionChallenger
    got = ChampionChallenger._recommend(
        [{"tested": False, "recommendation": INSUFFICIENT}])
    if got["verdict"] != INSUFFICIENT:
        return FAIL, (f"a comparison where nothing could be tested reports "
                      f"{got['verdict']!r}")
    if got["verdict"] == NO_DIFFERENCE:
        return FAIL, "not enough evidence is being reported as no difference"
    detail = got.get("detail") or ""
    if "has not compared anything" not in detail:
        return FAIL, f"the detail does not say nothing was compared: {detail}"
    empty = ChampionChallenger._recommend([])
    if empty["verdict"] != INSUFFICIENT:
        return FAIL, f"a comparison with no tests at all reports {empty['verdict']!r}"
    return PASS, "insufficient is reported apart from no difference"


@case("QA-AM-4891", "The material threshold and the significance test are separate")
def am_4891(ctx: Ctx) -> Result:
    """A difference can be statistically significant and too small to act on,
    or large and not significant. Collapsing the two would let a huge sample
    make a trivial difference look like a reason to change a model."""
    significant_trivial = _verdict(True, False, 0.5)
    if significant_trivial in (CHALLENGER_AHEAD, CHAMPION_AHEAD):
        return FAIL, ("a significant but immaterial difference is reported as "
                      "a challenger ahead: a large enough sample makes any "
                      "difference significant")
    material_noise = _verdict(False, True, 0.5)
    if material_noise in (CHALLENGER_AHEAD, CHAMPION_AHEAD):
        return FAIL, ("a material but insignificant difference is reported as "
                      "a challenger ahead, so noise of the right size wins")
    both = _verdict(True, True, 0.5)
    if both != CHALLENGER_AHEAD:
        return FAIL, f"significant AND material reports {both!r}"
    against = _verdict(True, True, -0.5)
    if against != CHAMPION_AHEAD:
        return FAIL, f"a significant material difference the other way reports {against!r}"
    return PASS, "both conditions required, and the sign decides which way"


@case("QA-AM-4892", "The significance level is stated on every test")
def am_4892(ctx: Ctx) -> Result:
    """`alpha` travels with the result. A p-value with no threshold beside it
    is a number a reader has to bring their own convention to, and two
    readers bring different ones."""
    if not 0.0 < ALPHA < 1.0:
        return FAIL, f"alpha is {ALPHA}"
    if ALPHA != 0.05:
        return FAIL, (f"alpha is {ALPHA} rather than the conventional 0.05; "
                      f"a non-standard level is defensible and has to be "
                      f"argued for rather than drifted into")
    import inspect

    from core.monitoring.challengers import ChampionChallenger
    source = inspect.getsource(ChampionChallenger._one)
    for field in ('"alpha"', '"p_value"', '"method"', '"material_threshold"'):
        if field not in source:
            return FAIL, (f"a test result does not carry {field}, so a reader "
                          f"cannot tell what it was judged against")
    return PASS, f"alpha {ALPHA}, the p-value, the method and the threshold all reported"
