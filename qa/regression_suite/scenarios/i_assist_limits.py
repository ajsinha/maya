"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — what the assistance layer refuses to claim.

Three refusals define it, and each is a place where reporting nothing would be
worse than reporting a blank.

**`toxicity` and `personal_data_leakage` are reported as NOT MEASURED, never
as zero.** MAYA has no classifier and will not ship a keyword list dressed up
as one. A dashboard showing zero because nothing looked is worse than a blank,
because a blank prompts somebody to ask.

**A budget is checked before the call.** A budget checked afterwards is an
invoice — and a refused call still charges, because a capability burning its
allowance on `oracle_failed` is a different problem from one burning it on
`nothing_grounded`, and a single *wasted* count would not tell them apart.

**A rate over four samples is a number pretending to be a measurement.** Below
ten attested generations an override rate is noise, and it is named as thin
rather than printed to two decimal places.
"""
from __future__ import annotations

from core.assist.monitoring import (DEFAULT_WINDOW_DAYS, METRICS,
                                    MIN_FOR_A_RATE, NOT_MEASURED)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

A = "/api/v1/assist"


def _budgets(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("assist_budgets")


def _capabilities(ctx: Ctx):
    """The key is `capabilities`, not `assist_capabilities` — three cases
    blocked on a name that never existed."""
    return ctx.ui.app.state.ctx.get("capabilities")


@case("QA-PLT-217", "`toxicity` and `personal_data_leakage` on the metric list")
def plt_217(ctx: Ctx) -> Result:
    """Reported as not measured, never as zero. And they must still APPEAR —
    omitting them would let a reader think the platform had considered
    toxicity and found none, which is the reading a blank is meant to
    prevent."""
    from core.assist.monitoring import AssistMonitoring
    vocabulary = AssistMonitoring.vocabulary()
    listed = {m["metric"] for m in vocabulary["metrics"]}
    for metric in NOT_MEASURED:
        if metric not in listed:
            return FAIL, (f"'{metric}' is omitted from the metric list, so a "
                          f"reader cannot tell it was considered")
        if metric not in vocabulary["not_measured"]:
            return FAIL, f"'{metric}' is not named under not_measured"
        spec = METRICS[metric]
        if spec["from"] != "not measured":
            return FAIL, (f"'{metric}' claims to come from {spec['from']!r}")
        if "classifier" not in spec["means"]:
            return FAIL, (f"'{metric}' does not say why it is not measured")
    detail = vocabulary.get("detail") or ""
    if "NOT MEASURED" not in detail and "not measured" not in detail:
        return FAIL, f"the vocabulary does not say which are unmeasured: {detail[:120]}"
    if "zero" not in detail:
        return FAIL, ("the vocabulary does not say they are not reported as "
                      "zero, which is the whole distinction")
    return PASS, (f"{len(NOT_MEASURED)} of {len(METRICS)} named as not "
                  f"measured, present on the list, each with a reason")


@case("QA-PLT-216",
      "A capability with fewer than ten reviews in `never_overridden`")
def plt_216(ctx: Ctx) -> Result:
    """A rate over four samples printed to two decimal places is a number
    pretending to be a measurement. Below the floor the capability is
    reported as THIN rather than as never overridden."""
    if MIN_FOR_A_RATE < 5:
        return FAIL, (f"the floor for a rate is {MIN_FOR_A_RATE}, which is "
                      f"few enough that a rate over it is still noise")
    import inspect

    from core.assist.monitoring import AssistMonitoring
    source = inspect.getsource(AssistMonitoring)
    if "MIN_FOR_A_RATE" not in source:
        return FAIL, ("the monitoring module does not consult the sample "
                      "floor, so a rate over four reviews prints as a rate")
    if "thin" not in source.lower():
        return FAIL, ("a thin sample is not labelled, so a capability with "
                      "four reviews reads like one with four hundred")
    return PASS, f"rates floored at {MIN_FOR_A_RATE} samples and labelled thin below it"


@case("QA-PLT-215", "`citation_accuracy` reported as 1.0")
def plt_215(ctx: Ctx) -> Result:
    """The figure must travel with what it was computed over. A perfect
    score over three claims and a perfect score over three hundred are
    different facts, and only the denominator tells them apart."""
    if "citation_accuracy" not in METRICS:
        return BLOCKED, "citation_accuracy is not a metric here"
    spec = METRICS["citation_accuracy"]
    if spec["from"] == "not measured":
        return BLOCKED, "citation_accuracy is not measured on this build"
    import inspect

    from core.assist.monitoring import AssistMonitoring
    source = inspect.getsource(AssistMonitoring)
    for word in ("window", "of", "count"):
        if word in source:
            break
    else:
        return FAIL, "no metric reports what it was computed over"
    if str(int(DEFAULT_WINDOW_DAYS)) not in source and \
            "DEFAULT_WINDOW_DAYS" not in source:
        return FAIL, ("the metrics do not state the window they cover, so a "
                      "rate this month and one this year print the same")
    return PASS, (f"metrics are computed over a stated "
                  f"{DEFAULT_WINDOW_DAYS:.0f}-day window")


@case("QA-PLT-202", "Spend exactly the budget, then call once more")
def plt_202(ctx: Ctx) -> Result:
    """The gate is BEFORE the provider is asked, which is the only position
    from which a budget is a control rather than a report. The refusal says
    when the window refills, because a caller told only *no* waits without
    knowing for how long."""
    from core.assist.common import AssistError
    budgets = _budgets(ctx)
    if budgets is None:
        return BLOCKED, "no assist budget register is wired"
    import inspect
    source = inspect.getsource(type(budgets).check)
    if "before the provider is asked" not in source and \
            "before the call" not in source:
        return FAIL, "the budget gate does not state that it runs before the call"
    caps = _capabilities(ctx)
    if caps is None:
        return BLOCKED, "no capability register is wired"
    known = caps.list()
    if not known:
        return BLOCKED, "no capability is registered"
    key = known[0].get("capability_key") or known[0].get("key")
    state = budgets.of(key)
    if "exhausted" not in state:
        return FAIL, "the budget state does not say whether it is exhausted"
    if state["exhausted"]:
        try:
            budgets.check(key)
        except AssistError as exc:
            if getattr(exc, "code", "") != "budget_exhausted":
                return FAIL, f"an exhausted budget refused '{getattr(exc, 'code', exc)}'"
            if "invoice" not in f"{exc}":
                return FAIL, "the refusal does not say why the gate is before the call"
            return PASS, "refused 'budget_exhausted' before the provider was asked"
    return PASS, (f"the gate runs before the call; headroom "
                  f"{state.get('remaining') or state.get('exhausted')}")


@case("QA-PLT-203", "A refused generation still charges the budget")
def plt_203(ctx: Ctx) -> Result:
    """Charged whether or not anything survived the gate, with the OUTCOME
    recorded — a capability burning its allowance on `oracle_failed` is a
    different problem from one burning it on `nothing_grounded`, and a
    single *wasted* count would not distinguish them."""
    budgets = _budgets(ctx)
    caps = _capabilities(ctx)
    if budgets is None or caps is None:
        return BLOCKED, "the assist registers are not wired"
    known = caps.list()
    if not known:
        return BLOCKED, "no capability is registered"
    key = known[0].get("capability_key") or known[0].get("key")
    before = len(budgets.spend.many())
    row = budgets.charge(key, tokens=0, cost=0.0, steps=1,
                         generation_id=None, outcome="nothing_grounded",
                         actor="qa")
    if len(budgets.spend.many()) != before + 1:
        return FAIL, "a refused generation charged nothing"
    if row.get("generation_id") is not None:
        return FAIL, ("a refused generation recorded a generation id, so a "
                      "call that produced nothing looks like one that did")
    if row.get("outcome") != "nothing_grounded":
        return FAIL, f"the outcome reads {row.get('outcome')!r}"
    if row.get("tokens") != 0:
        return FAIL, (f"a provider that reported no token count was charged "
                      f"{row['tokens']}: a budget fed invented figures refuses "
                      f"real work for imaginary reasons")
    return PASS, "charged with outcome 'nothing_grounded' and no generation id"


@case("QA-PLT-4940", "A capability nobody set a budget for")
def plt_4940(ctx: Ctx) -> Result:
    """Not unbudgeted — it runs on a number this module chose, and reporting
    that as though somebody decided it is how a default becomes permanent.
    So `on_default` is a column."""
    budgets = _budgets(ctx)
    if budgets is None:
        return BLOCKED, "no assist budget register is wired"
    report = budgets.across_the_estate()
    if "on_default" not in report:
        return FAIL, ("the estate view does not count capabilities running on "
                      "a default, so a number this module chose reads as one "
                      "somebody decided")
    rows = report.get("capabilities") or report.get("rows") or []
    for row in rows:
        if "on_default" not in row:
            return FAIL, (f"'{row.get('capability_key')}' does not say whether "
                          f"its budget was set or defaulted")
    return PASS, (f"{report['on_default']} of {len(rows)} capabilities on a "
                  f"default, counted apart")


@case("QA-PLT-213",
      "A capability whose oracle was removed from the code in a release")
def plt_213(ctx: Ctx) -> Result:
    """Refused by name at registration. A capability pointing at an oracle
    nothing implements is one that will fail at first use, on whoever
    happened to call it rather than on whoever deployed it."""
    from core.assist.common import AssistError
    caps = _capabilities(ctx)
    if caps is None:
        return BLOCKED, "no capability register is wired"
    try:
        caps.register(ctx.unique("cap"), "a QA capability", "A",
                      base_model="mock", prompt_digest="sha256:" + "0" * 64,
                      owner="person/owner",
                      oracle_key="an-oracle-nobody-wrote", actor="qa")
    except AssistError as exc:
        if getattr(exc, "code", "") != "unknown_oracle":
            return FAIL, f"refused '{getattr(exc, 'code', exc)}'"
        return PASS, "refused 'unknown_oracle' at registration"
    except TypeError:
        return BLOCKED, "the capability register takes a different signature"
    return FAIL, ("a capability naming an oracle nothing implements was "
                  "registered, so it fails at first use on whoever calls it")


@case("QA-PLT-214",
      "A remote provider on an instance where none is configured")
def plt_214(ctx: Ctx) -> Result:
    """Refused as unavailable rather than falling back to the mock. A mock
    answer presented as a provider answer is a generation nobody can tell
    from a real one."""
    import inspect

    from core.assist import drafting
    source = inspect.getsource(drafting)
    if "provider_unavailable" not in source:
        return FAIL, "an unconfigured provider is not refused by name"
    at = source.find("provider_unavailable")
    around = source[max(0, at - 400):at + 400]
    if "fallback" in around.lower() and "refus" not in around.lower():
        return FAIL, ("an unconfigured provider falls back rather than "
                      "refusing, so a mock answer is indistinguishable from a "
                      "provider's")
    return PASS, "refused 'provider_unavailable' rather than falling back"


@case("QA-PLT-187",
      "A Tier A generation whose grounding rejects **every** claim")
def plt_187(ctx: Ctx) -> Result:
    """`nothing_grounded`, and it is a refusal rather than an empty draft.
    A generation whose every claim failed grounding has produced nothing the
    register stands behind, and returning it as prose with no claims would
    be handing somebody text to paste into a document."""
    import inspect

    from core.assist import generations
    source = inspect.getsource(generations)
    if "nothing_grounded" not in source:
        return FAIL, "a wholly ungrounded generation is not refused by name"
    at = source.find("nothing_grounded")
    around = source[max(0, at - 300):at + 500]
    if "raise" not in source[max(0, at - 120):at]:
        return FAIL, "the ungrounded case is reported rather than raised"
    if "claim" not in around:
        return FAIL, "the refusal does not mention the claims that failed"
    return PASS, "refused 'nothing_grounded' rather than returning empty prose"


@case("QA-PLT-199", "`unverified_narrative` as a state")
def plt_199(ctx: Ctx) -> Result:
    """No such field, label or state exists, and that is deliberate: a
    generation is grounded and attested, or it is not kept. A halfway state
    would be prose in the register that nobody signed and nothing checked."""
    import inspect

    from core.assist import generations
    source = inspect.getsource(generations)
    if "unverified_narrative" in source:
        return FAIL, ("an `unverified_narrative` state exists, so prose "
                      "nobody signed can sit in the register")
    states = getattr(generations, "STATES", ())
    for state in states:
        if "unverified" in f"{state}".lower():
            return FAIL, f"a state '{state}' admits ungrounded prose"
    if states and "attested" not in [f"{s}" for s in states]:
        return FAIL, f"attestation is not a state of a generation: {states}"
    return PASS, (f"no unverified narrative state; the states are "
                  f"{list(states) or 'not enumerated'}")
