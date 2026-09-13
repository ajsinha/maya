"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — risk appetite.

A limit is a number a committee is held to, so the two things that make it
real are the rationale and the version history. **A limit nobody can explain
is one nobody will change**, so it gets ignored or obeyed without thought, and
both are worse than not having it. And a limit can be RELAXED — that is
allowed and must never be quiet: a committee raising a limit because the
estate grew is doing something reasonable, one raising it because the estate
breached it is doing something else, and only the record can tell the two
apart.

Every case is `isolated`: appetite versions accumulate per metric-and-scope
across the whole estate, so one case's declaration is the next case's prior.
"""
from __future__ import annotations

from core.reporting.common import (HIGHER_IS_BETTER, LOWER_IS_BETTER,
                                   MAX_RATIONALE, METRICS, SCOPES)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

A = "/api/v1/risk-appetite"
WHY = "the board set this at the March committee; paper MRM-2026-03"


def _named(direction: str) -> str:
    for metric in METRICS:
        if metric.direction == direction:
            return metric.key if hasattr(metric, "key") else metric.name
    return ""


def _declare(ctx: Ctx, **over):
    body = {"metric": _named(LOWER_IS_BETTER), "limit": 10.0,
            "rationale": WHY, "amber": None, "scope": {}, "owner": "person/risk",
            "review_at": None}
    body.update(over)
    return ctx.api.post(A, json=body, auth=ctx.people["risk"])


def _retire(ctx: Ctx, metric: str, **over):
    body = {"metric": metric, "scope": {}, "reason": "the paper was withdrawn"}
    body.update(over)
    return ctx.api.post(f"{A}/retire", json=body, auth=ctx.people["risk"])


def _history(ctx: Ctx, metric: str) -> list:
    got = ctx.api.get(f"{A}/history/{metric}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return []
    body = got.json() or {}
    return body.get("history") or body.get("versions") or []


@case("QA-AM-341", "Declare a limit on a metric the platform does not compute",
      isolated=True)
def am_341(ctx: Ctx) -> Result:
    """A limit on a number nobody measures is a limit that can never be
    breached, and it reads on the appetite screen exactly like one that
    can."""
    got = _declare(ctx, metric="models_that_feel_wrong")
    outcome = refused_by_the_control(
        got, "a limit on a metric the platform does not compute")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "unknown_metric":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'unknown_metric'"


@case("QA-AM-342", "Declare a limit with no rationale", isolated=True)
def am_342(ctx: Ctx) -> Result:
    """Say what the number is FOR."""
    got = _declare(ctx, rationale="   ")
    outcome = refused_by_the_control(got, "a limit nobody can explain")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "rationale_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'rationale_required' on whitespace"


@case("QA-AM-343",
      "Declare a rationale of exactly 2,000 characters, then 2,001",
      isolated=True)
def am_343(ctx: Ctx) -> Result:
    """A rationale a committee will not read is not a rationale. The bound is
    `>`, so exactly the maximum is in."""
    at = _declare(ctx, rationale="x" * MAX_RATIONALE)
    if at.status_code >= 400:
        return FAIL, (f"refused '{code_of(at)}' at exactly {MAX_RATIONALE} "
                      f"characters, so the documented bound is one short")
    over = _declare(ctx, rationale="y" * (MAX_RATIONALE + 1))
    if over.status_code < 400:
        return FAIL, f"{MAX_RATIONALE + 1} characters was accepted"
    if code_of(over) != "rationale_too_long":
        return FAIL, f"refused '{code_of(over)}'"
    if str(MAX_RATIONALE) not in over.text:
        return FAIL, "the refusal does not say what the maximum is"
    return PASS, f"{MAX_RATIONALE} in, {MAX_RATIONALE + 1} refused"


@case("QA-AM-344", "Amber equal to the limit on a lower-is-better metric",
      isolated=True)
def am_344(ctx: Ctx) -> Result:
    """A warning that can only fire after the thing it warns about has
    happened is not a warning. Equality is the boundary: amber AT the limit
    fires at the same moment the limit does."""
    metric = _named(LOWER_IS_BETTER)
    if not metric:
        return BLOCKED, "no lower-is-better metric is configured"
    got = _declare(ctx, metric=metric, limit=10.0, amber=10.0)
    outcome = refused_by_the_control(
        got, "an amber threshold that fires no earlier than the limit")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "amber_beyond_limit":
        return FAIL, f"refused '{code_of(got)}'"
    inside = _declare(ctx, metric=metric, limit=10.0, amber=8.0)
    if inside.status_code >= 400:
        return FAIL, (f"an amber inside the limit was also refused "
                      f"'{code_of(inside)}', so no amber can be set at all")
    return PASS, "amber at the limit refused, amber inside it accepted"


@case("QA-AM-345", "Amber above the limit on a higher-is-better metric",
      isolated=True)
def am_345(ctx: Ctx) -> Result:
    """The direction flips the side amber belongs on. For a higher-is-better
    metric the warning sits ABOVE the floor, and refusing it would make amber
    unusable on half the vocabulary."""
    metric = _named(HIGHER_IS_BETTER)
    if not metric:
        return BLOCKED, "no higher-is-better metric is configured"
    got = _declare(ctx, metric=metric, limit=0.6, amber=0.7)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — on a higher-is-better "
                      f"metric an amber above the floor is the only one that "
                      f"warns before the limit is reached")
    wrong = _declare(ctx, metric=metric, limit=0.6, amber=0.5)
    if wrong.status_code < 400:
        return FAIL, ("an amber BELOW the floor of a higher-is-better metric "
                      "was accepted, so the warning fires after the breach")
    return PASS, "amber above the floor accepted, below it refused"


@case("QA-AM-346", "Declare a limit scoped to `region`", isolated=True)
def am_346(ctx: Ctx) -> Result:
    """Three scopes and no fourth. A limit scoped to something the register
    does not hold matches nothing, so it is a limit that never applies and
    reads on the screen as one that does."""
    got = _declare(ctx, scope={"region": "EMEA"})
    outcome = refused_by_the_control(
        got, "a limit scoped to something the register does not hold")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "unknown_scope":
        return FAIL, f"refused '{code_of(got)}'"
    missing = [s for s in SCOPES if s not in got.text]
    if missing:
        return FAIL, f"the refusal does not name the scopes {missing}"
    return PASS, f"refused 'unknown_scope', naming all {len(SCOPES)}"


@case("QA-AM-347", "Raise a limit that was previously tighter", isolated=True)
def am_347(ctx: Ctx) -> Result:
    """The event somebody looks for later. Allowed, and never quiet — the
    evidence node has to carry `relaxed: true`, computed here rather than
    left to a reader to work out from two numbers in two rows."""
    metric = _named(LOWER_IS_BETTER)
    if not metric:
        return BLOCKED, "no lower-is-better metric is configured"
    if _declare(ctx, metric=metric, limit=5.0).status_code >= 400:
        return BLOCKED, "the first limit could not be declared"
    got = _declare(ctx, metric=metric, limit=20.0,
                   rationale="the estate grew; paper MRM-2026-07")
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a committee cannot raise a "
                      f"limit, so the register forces a retirement instead "
                      f"and the relaxation loses its history")
    engine = ctx.ui.app.state.ctx.get("evidence")
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    nodes = [n for n in engine.for_kind("risk_appetite_declared")] \
        if hasattr(engine, "for_kind") else []
    if not nodes:
        row = got.json() or {}
        nodes = [n for n in engine.for_subject(row.get("id") or "")]
    relaxed = [n for n in nodes
               if (n.get("payload") or {}).get("relaxed")]
    if not relaxed:
        return FAIL, ("the limit was raised and no evidence node carries "
                      "`relaxed: true`, so a relaxation is findable only by "
                      "comparing two numbers in two rows")
    return PASS, f"raised, and {len(relaxed)} node(s) say relaxed"


@case("QA-AM-348", "Tighten a limit", isolated=True)
def am_348(ctx: Ctx) -> Result:
    """The other direction, and it must NOT read as a relaxation — a register
    that flagged every change would make the flag meaningless."""
    metric = _named(LOWER_IS_BETTER)
    if not metric:
        return BLOCKED, "no lower-is-better metric is configured"
    if _declare(ctx, metric=metric, limit=20.0).status_code >= 400:
        return BLOCKED, "the first limit could not be declared"
    got = _declare(ctx, metric=metric, limit=5.0,
                   rationale="tightened after the review; paper MRM-2026-08")
    if got.status_code >= 400:
        return FAIL, f"refused '{code_of(got)}'"
    engine = ctx.ui.app.state.ctx.get("evidence")
    row = got.json() or {}
    nodes = engine.for_subject(row.get("id") or "") if engine else []
    if any((n.get("payload") or {}).get("relaxed") for n in nodes):
        return FAIL, ("tightening a limit was recorded as a relaxation, so "
                      "the flag says nothing about which way the number went")
    history = _history(ctx, metric)
    if len(history) < 2:
        return FAIL, (f"the history holds {len(history)} version(s); the "
                      f"previous limit did not stay in the register")
    return PASS, f"tightened, not flagged relaxed, {len(history)} versions"


@case("QA-AM-349", "Retire a limit and then declare it again", isolated=True)
def am_349(ctx: Ctx) -> Result:
    """The version number has to continue rather than restart. A restart
    would make the second declaration look like the first one and hide
    whatever the estate was held to in between."""
    metric = _named(LOWER_IS_BETTER)
    if not metric:
        return BLOCKED, "no lower-is-better metric is configured"
    first = _declare(ctx, metric=metric, limit=10.0)
    if first.status_code >= 400:
        return BLOCKED, "the first limit could not be declared"
    was = (first.json() or {}).get("version")
    if _retire(ctx, metric).status_code >= 400:
        return BLOCKED, "the limit could not be retired"
    again = _declare(ctx, metric=metric, limit=12.0,
                     rationale="re-declared after the review; MRM-2026-09")
    if again.status_code >= 400:
        return FAIL, (f"refused '{code_of(again)}' — a retired limit can "
                      f"never be declared again")
    now = (again.json() or {}).get("version")
    if now is None or was is None:
        return FAIL, "the declaration carries no version number"
    if now <= was:
        return FAIL, (f"the version went {was} -> {now} across a retirement, "
                      f"so the second declaration is indistinguishable from "
                      f"the first and what the estate was held to in between "
                      f"is lost")
    return PASS, f"version {was} -> {now} across the retirement"


@case("QA-AM-350", "Retire a limit that was never declared", isolated=True)
def am_350(ctx: Ctx) -> Result:
    """Retiring nothing must not read as having retired something. The
    remediation is the interesting half: the indicator is still MEASURED, it
    is simply not held to anything."""
    metric = _named(LOWER_IS_BETTER)
    if not metric:
        return BLOCKED, "no lower-is-better metric is configured"
    got = _retire(ctx, metric)
    outcome = refused_by_the_control(got, "a limit nobody declared was retired")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "no_appetite":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'no_appetite'"


@case("QA-AM-351", "An estate-wide limit and a Tier 1 limit on one metric",
      isolated=True)
def am_351(ctx: Ctx) -> Result:
    """Versions accumulate per metric-and-scope, so a tier 1 limit does not
    supersede the estate-wide one — they are two limits and both stand. A
    single version series would make the narrower declaration silently
    replace the broader."""
    metric = _named(LOWER_IS_BETTER)
    if not metric:
        return BLOCKED, "no lower-is-better metric is configured"
    wide = _declare(ctx, metric=metric, limit=50.0, scope={})
    narrow = _declare(ctx, metric=metric, limit=5.0, scope={"tier": 1},
                      rationale="tier 1 is held tighter; MRM-2026-10")
    if wide.status_code >= 400 or narrow.status_code >= 400:
        return BLOCKED, (f"a limit could not be declared: "
                         f"{wide.text[:80]} / {narrow.text[:80]}")
    got = ctx.api.get(A, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the in-force read answered {got.status_code}"
    live = [r for r in ((got.json() or {}).get("appetite") or [])
            if r.get("metric") == metric]
    if len(live) < 2:
        return FAIL, (f"declaring a tier 1 limit left {len(live)} live limit(s) "
                      f"on '{metric}': the narrower scope superseded the "
                      f"estate-wide one instead of sitting beside it")
    if (narrow.json() or {}).get("version") != 1:
        return FAIL, (f"the tier 1 limit is version "
                      f"{(narrow.json() or {}).get('version')}, so it "
                      f"continued the estate-wide series rather than starting "
                      f"its own")
    return PASS, f"{len(live)} limits live on '{metric}', each versioned apart"
