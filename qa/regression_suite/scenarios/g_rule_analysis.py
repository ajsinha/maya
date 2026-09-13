"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — what the rule-set checker can decide, and what it declines to.

A rule that never fires still appears in the model card and in every committee
paper, and nobody reading either can tell. So the checker looks for three
things and reports them apart, because the messages send an author somewhere
different.

**Contradictions before shadowing**, and the order is not cosmetic: two rules
with the same condition are also a shadowing, so reporting shadowing first
made `rules_contradict` unreachable — in the checker written to find
unreachable rules. *This rule can never fire, reorder it* sends an author to
the ordering, and the ordering is not the mistake.

**Undecided is not "no problem found".** Where coverage cannot be decided the
rule set is still publishable and what is reported is that this rule was NOT
CHECKED. A checker that recorded an undecided as clean would be the exact
failure it exists to prevent.
"""
from __future__ import annotations

from core.rules.common import MAX_DEPTH, MAX_RULES, RuleError
from core.rules.conditions import Condition
from core.rules.domains import (MAX_DISJUNCTS, Unanalysable, covers, disjuncts, satisfiable, union_covers)
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _cond(raw) -> Condition:
    return Condition.parse(raw)


def _atom(field: str, op: str, value) -> dict:
    return {"field": field, "op": op, "value": value}


@case("QA-FX-293", "A rule shadowed by two earlier rules together")
def fx_293(ctx: Ctx) -> Result:
    """`ltv > 0.8` and `ltv <= 0.8` between them cover everything after, and
    no single-rule comparison sees it. This was a stated limit on the grounds
    that full coverage is satisfiability and a solver is a dependency nobody
    in the bank can debug — the premise was right and the conclusion did not
    follow, because a conjunction here is a box and coverage is geometry."""
    high = _cond(_atom("ltv", "gt", 0.8))
    low = _cond(_atom("ltv", "le", 0.8))
    later = _cond(_atom("ltv", "ge", 0.0))
    if covers(high, later) or covers(low, later):
        return FAIL, "one of the two earlier rules already covers it alone"
    if not union_covers([high, low], later):
        return FAIL, ("two rules partitioning the line do not cover a third, "
                      "so a rule that can never fire is published")
    narrower = _cond(_atom("ltv", "gt", 0.9))
    if not union_covers([high, low], narrower):
        return FAIL, "a narrower later rule is not covered either"
    return PASS, "the union of a partition covers what neither half does"


@case("QA-FX-4830", "Contradictions are reported before shadowing")
def fx_4830(ctx: Ctx) -> Result:
    """The recorded defect. Two rules with the same condition and different
    outcomes are ALSO a shadowing, so reporting shadowing first made
    `rules_contradict` unreachable. The two messages point somewhere
    different: one sends an author to the ordering, the other says somebody
    has to decide which outcome the policy means."""
    import inspect

    from core.rules import ruleset as module
    source = inspect.getsource(module.RuleSet.validate)
    at_contradiction = source.find("rules_contradict")
    at_shadow = source.find("rule_unreachable")
    if at_contradiction < 0:
        return FAIL, "the checker never raises 'rules_contradict'"
    if at_shadow < 0:
        return FAIL, "the checker never raises 'rule_unreachable'"
    if at_contradiction > at_shadow:
        return FAIL, ("shadowing is raised before contradiction, so two rules "
                      "saying opposite things about identical inputs are "
                      "reported as an ordering mistake — and 'rules_contradict' "
                      "is unreachable")
    return PASS, "contradictions raised before shadowing"


@case("QA-FX-294", "A condition expanding past 256 disjunctions")
def fx_294(ctx: Ctx) -> Result:
    """The blow-up is refused at the expansion and every caller turns it into
    a SOUND NEGATIVE — *not shown to cover* — rather than into a positive.
    That is the only safe direction: a coverage check that answered *yes,
    covered* on a condition it could not expand would call a live rule
    unreachable and somebody would delete it."""
    wide = _cond({"all": [{"any": [_atom(f"f{g}", "eq", n) for n in range(10)]}
                          for g in range(3)]})
    small = _cond(_atom("f0", "eq", 1))
    try:
        disjuncts(wide)
    except Unanalysable as exc:
        if str(MAX_DISJUNCTS) not in f"{exc}":
            return FAIL, f"the refusal does not name the bound: {f'{exc}'[:100]}"
    else:
        return FAIL, (f"a condition expanding to 1,000 conjunctions past a "
                      f"bound of {MAX_DISJUNCTS} was expanded anyway")
    if covers(wide, small) or covers(small, wide):
        return FAIL, ("an unanalysable condition is reported as COVERING, so "
                      "a live rule would be called unreachable on arithmetic "
                      "that was never done")
    if union_covers([wide], small):
        return FAIL, "the union check reports coverage it could not compute"
    if not satisfiable(wide):
        return FAIL, ("an unanalysable condition is reported UNSATISFIABLE, "
                      "so a publishable rule set is refused on a check that "
                      "gave up")
    return PASS, (f"past {MAX_DISJUNCTS} the expansion refuses, coverage "
                  f"answers a sound negative and satisfiability a sound "
                  f"positive")


@case("QA-FX-4831", "An undecided rule is reported, never counted as clean")
def fx_4831(ctx: Ctx) -> Result:
    """The property behind QA-FX-294, checked where it matters: the checker
    catches `Undecided` and records the rule as NOT CHECKED rather than
    swallowing it into the shadowed list or letting it pass silently."""
    import inspect

    from core.rules import ruleset as module
    source = inspect.getsource(module.RuleSet._shadowed)
    if "Undecided" not in source:
        return FAIL, ("the shadow pass does not catch Undecided, so a "
                      "combinatorial blow-up either crashes a publish or is "
                      "silently treated as no problem")
    if "undecided" not in source.lower().replace("Undecided", ""):
        return FAIL, "an undecided result is caught and then not recorded"
    if "self.undecided" not in source:
        return FAIL, ("the undecided rules are not kept anywhere a caller can "
                      "read them")
    return PASS, "Undecided is caught, recorded, and kept apart from shadowed"


@case("QA-FX-296", "The negation of `between`")
def fx_296(ctx: Ctx) -> Result:
    """Treated as opaque and never as coverage. A checker that guessed at the
    complement of an interval would report a rule unreachable on the strength
    of arithmetic it did not actually do — worse than declining, because an
    author deletes the rule."""
    inside = _cond({"not": _atom("ltv", "between", [0.2, 0.8])})
    later = _cond(_atom("ltv", "gt", 0.9))
    try:
        answer = covers(inside, later)
    except Unanalysable:
        return PASS, "the negation of an interval is declined rather than guessed"
    if answer:
        return FAIL, ("the complement of an interval was computed and used to "
                      "call a later rule unreachable")
    return PASS, "treated as opaque: covers nothing rather than guessing"


@case("QA-FX-4832", "A condition no input can satisfy")
def fx_4832(ctx: Ctx) -> Result:
    """Almost always a typo in a bound. A rule with an unsatisfiable
    condition is refused at publish rather than reported, because unlike a
    shadowing there is no reading of it that was intended."""
    impossible = _cond({"all": [_atom("ltv", "gt", 0.9),
                                _atom("ltv", "lt", 0.1)]})
    if satisfiable(impossible):
        return FAIL, "a condition demanding ltv > 0.9 and ltv < 0.1 is satisfiable"
    fine = _cond({"all": [_atom("ltv", "gt", 0.1),
                          _atom("ltv", "lt", 0.9)]})
    if not satisfiable(fine):
        return FAIL, "an ordinary bounded interval is reported unsatisfiable"
    return PASS, "the impossible interval is caught, the ordinary one is not"


@case("QA-FX-4833", "A condition nested past the depth bound")
def fx_4833(ctx: Ctx) -> Result:
    """A bound with a number in the refusal, so an author at the edge can
    tell a limit from a bug — and every refusal names the PATH, so somebody
    fixing a rule set with forty rules is told which one and where."""
    raw = _atom("f", "eq", 1)
    for _ in range(MAX_DEPTH + 2):
        raw = {"all": [raw]}
    try:
        Condition.parse(raw, path="when")
    except RuleError as exc:
        said = f"{exc}"
        if str(MAX_DEPTH) not in said:
            return FAIL, f"the refusal does not say what the bound is: {said[:100]}"
        if "when" not in said:
            return FAIL, "the refusal does not name the path"
        return PASS, f"refused past {MAX_DEPTH} levels, naming the path"
    return FAIL, f"a condition nested {MAX_DEPTH + 2} deep parsed"


@case("QA-FX-4834", "A condition naming no field, and an unknown operator")
def fx_4834(ctx: Ctx) -> Result:
    """Both are malformed rather than merely unsatisfiable, and both name the
    path. A condition with no field reads nothing and would match either
    everything or nothing depending on where the bug was."""
    for raw, why in (({"op": "eq", "value": 1}, "no field"),
                     (_atom("f", "sideways", 1), "an unknown operator"),
                     ({"all": []}, "an empty group")):
        try:
            Condition.parse(raw, path="when")
        except RuleError as exc:
            if "when" not in f"{exc}":
                return FAIL, f"the refusal for {why} does not name the path"
            continue
        return FAIL, f"a condition with {why} parsed"
    return PASS, "no field, unknown operator and empty group all refused by path"


@case("QA-FX-4835", "The rule count bound")
def fx_4835(ctx: Ctx) -> Result:
    """A table of five hundred rules is a table nobody reviews, and the
    shadow analysis is quadratic in the count. The bound exists so a rule set
    that would take an hour to check is refused rather than accepted and
    unchecked."""
    if MAX_RULES <= 0:
        return FAIL, f"the rule bound is {MAX_RULES}"
    if MAX_RULES > 5000:
        return FAIL, (f"the bound is {MAX_RULES}, which at a quadratic shadow "
                      f"analysis is {MAX_RULES ** 2:,} comparisons")
    return PASS, f"bounded at {MAX_RULES} rules"


@case("QA-FX-299",
      "A date field compared against an ISO string and against an epoch")
def fx_299(ctx: Ctx) -> Result:
    """Both accepted. A firm importing a decision table has dates in one form
    and a firm writing rules by hand has them in the other, and refusing
    either would make the same policy expressible only one way."""
    for value in ("2026-03-01", 1_772_323_200.0):
        try:
            condition = _cond(_atom("as_of", "ge", value))
        except RuleError as exc:
            return FAIL, f"a date given as {value!r} was refused: {f'{exc}'[:90]}"
        if not satisfiable(condition):
            return FAIL, f"a date bound given as {value!r} is unsatisfiable"
    return PASS, "an ISO date and an epoch are both accepted"


@case("QA-FX-317", "A catch-all row that is not last")
def fx_317(ctx: Ctx) -> Result:
    """Every row below a catch-all is unreachable, and the checker has to say
    so about EACH of them rather than only the first — an author who fixes
    one and republishes should not discover the next one at a time."""
    # A genuine catch-all covers the whole line. `ltv >= 0` is not one: it
    # excludes the negatives, so it does not cover `ltv < 0.2`.
    catch_all = _cond({"any": [_atom("ltv", "ge", 0.0),
                               _atom("ltv", "lt", 0.0)]})
    below = [_cond(_atom("ltv", "gt", 0.5)),
             _cond(_atom("ltv", "lt", 0.2))]
    if covers(_cond(_atom("ltv", "ge", 0.0)), below[1]):
        return FAIL, ("`ltv >= 0` is treated as covering `ltv < 0.2`, so a "
                      "half-line is being read as a catch-all")
    # `covers` compares ONE earlier rule and a disjunctive catch-all is not
    # one; the union pass is what sees it, which is why both passes exist.
    halves = [_cond(_atom("ltv", "ge", 0.0)), _cond(_atom("ltv", "lt", 0.0))]
    for rule in below:
        if covers(catch_all, rule):
            continue
        if not union_covers(halves, rule):
            return FAIL, ("a catch-all does not cover a rule below it, so "
                          "unreachable rows are published")
    return PASS, (f"the catch-all covers all {len(below)} rows below it, the "
                  f"disjunctive half through the union pass")


@case("QA-FX-318", "A table with no catch-all row")
def fx_318(ctx: Ctx) -> Result:
    """No `otherwise` is manufactured. A checker that invented a default
    would decide the policy for the input nobody thought about, and the whole
    point of the analysis is to make that input visible."""
    import inspect

    from core.rules import ruleset as module
    source = inspect.getsource(module.RuleSet)
    for invented in ("otherwise = {", 'otherwise or {"', "otherwise=dict("):
        if invented in source:
            return FAIL, (f"the checker manufactures an otherwise clause: "
                          f"{invented}")
    if "otherwise" not in source:
        return FAIL, "the rule set has no notion of an otherwise clause at all"
    return PASS, "an otherwise clause is carried, never invented"
