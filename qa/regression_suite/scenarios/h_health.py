"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the model health score.

The module's own docstring names the two ways a composite lies. A single
number hides a verdict — a Critical finding past its date, an unmeasured
overlay carrying the model's answer — so the number and the verdict are
reported separately and the verdict wins. And an unmeasured component scores
as a good one, so "a score of 92 at 30% coverage is not a healthy model; it is
a model nobody has looked at, and the two must not print the same".
"""
from __future__ import annotations

from core.monitoring.health import (BANDS, COMPONENTS, GOOD, GOOD_AT, POOR,
                                    WATCH, WATCH_AT, WEIGHTS)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

H = "/api/v1/model-health"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _bare(ctx: Ctx) -> str:
    name = ctx.unique("hl")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return f"maya://model/{name}"


def _health(ctx: Ctx, urn: str):
    return ctx.api.get(f"{H}?urn={urn}", auth=ctx.people["risk"])


@case("QA-AM-287", "A model where nothing at all is measurable")
def am_287(ctx: Ctx) -> Result:
    """A score of nothing, not a score of zero — and the platform has to be
    able to produce that state at all. A bare model is NOT it: two of six
    components (no findings, no overlays) are genuinely measurable and
    genuinely good, so it scores 100 at 25% coverage. The underivable case is
    reached by measuring nothing, which the service must answer with null
    rather than with a zero.
    """
    health = ctx.ui.app.state.ctx.get("model_health")
    if health is None:
        return BLOCKED, "no health service reachable from this run"
    empty = health._band(None) if hasattr(health, "_band") else "missing"
    if empty == "missing":
        return BLOCKED, "no band helper to call"
    if empty:
        return FAIL, (f"a score of None lands in band '{empty}'; nothing "
                      f"measured reads as a verdict")
    detail = health._detail(None, None, None, 0.0, [], []) \
        if hasattr(health, "_detail") else ""
    if "nothing" not in (detail or "").lower():
        return FAIL, (f"an underivable score is not explained: "
                      f"{str(detail)[:120]}")
    if "zero" not in (detail or "").lower():
        return FAIL, ("the explanation does not distinguish a score of "
                      "nothing from a score of zero, which is the whole "
                      "point of leaving it null")
    return PASS, str(detail)[:110]


@case("QA-AM-286", "A model with no monitors, no validation and no findings")
def am_286(ctx: Ctx) -> Result:
    """The published expectation is exact: a score null OR high, with
    coverage well under 0.5, and the DETAIL saying so. A high number beside a
    thin coverage is only safe if the prose says which it is."""
    got = _health(ctx, _bare(ctx))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    row = got.json() or {}
    coverage = row.get("coverage")
    if coverage is None:
        return FAIL, ("the health record carries no coverage, so a score "
                      "nobody could measure prints like one that was")
    if coverage >= 0.5:
        return FAIL, (f"a bare model reports coverage {coverage}; more than "
                      f"half its weight was measurable with nothing recorded")
    detail = (row.get("detail") or "").lower()
    if "how little is known" not in detail and "measurable" not in detail:
        return FAIL, (f"the score is {row.get('score')} at coverage "
                      f"{coverage} and the detail does not say the number is "
                      f"about how little is known: {detail[:120]}")
    if row.get("not_measured") is None:
        return FAIL, "the unmeasured components are not named"
    return PASS, (f"score {row.get('score')} at coverage {coverage}, and the "
                  f"detail says what that means")


@case("QA-AM-3300", "The weights are data, and they sum to one")
def am_3300(ctx: Ctx) -> Result:
    """"A composite whose weights live in a conditional is a composite nobody
    can check." They are held as data so the derivation can be rendered — and
    if they did not sum to one the arithmetic would not be a mean."""
    total = sum(WEIGHTS.values())
    if abs(total - 1.0) > 1e-9:
        return FAIL, (f"the {len(WEIGHTS)} component weights sum to {total}, "
                      f"so the score is not a weighted mean of anything")
    unasked = [c["key"] for c in COMPONENTS
               if not (c.get("asks") or c.get("question") or
                       c.get("detail") or "").strip()]
    if unasked:
        return FAIL, f"components with no stated question: {unasked}"
    return PASS, f"{len(WEIGHTS)} components, weights sum to 1, each asking something"


@case("QA-AM-3301", "The bands are ordered and the thresholds are stated")
def am_3301(ctx: Ctx) -> Result:
    """A band boundary a reader cannot see is a verdict nobody can argue
    with."""
    if GOOD_AT <= WATCH_AT:
        return FAIL, (f"the good threshold {GOOD_AT} is not above the watch "
                      f"threshold {WATCH_AT}")
    if BANDS != (GOOD, WATCH, POOR):
        return FAIL, f"the bands are not ordered best-first: {BANDS}"
    return PASS, f"{GOOD} at {GOOD_AT}, {WATCH} at {WATCH_AT}, then {POOR}"


@case("QA-AM-3304", "The verdict wins over the arithmetic")
def am_3304(ctx: Ctx) -> Result:
    """A single number hides a verdict, so the two are reported separately —
    and when they disagree, the disagreement is the finding. The record has to
    carry BOTH or there is nothing to disagree."""
    got = _health(ctx, _bare(ctx))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    row = (body.get("models") or [body])[0] if isinstance(body, dict) else body
    for field in ("band", "arithmetic_band", "caps"):
        if field not in row:
            return FAIL, (f"the health record has no '{field}', so a capped "
                          f"verdict cannot be told from the arithmetic")
    return PASS, "band, arithmetic_band and caps are all reported"


@case("QA-AM-3302", "A cap never improves the band")
def am_3302(ctx: Ctx) -> Result:
    """The verdict wins by being the WORST of the arithmetic and the caps. A
    cap that could raise a band would be a Critical finding making a model
    look better."""
    health = ctx.ui.app.state.ctx.get("model_health")
    if health is None:
        return BLOCKED, "no health service reachable from this run"
    wrong = []
    for arithmetic in BANDS:
        for cap in BANDS:
            got = health._worst([arithmetic, cap])
            rank = {GOOD: 0, WATCH: 1, POOR: 2}
            if rank[got] < max(rank[arithmetic], rank[cap]):
                wrong.append(f"{arithmetic}+{cap}={got}")
    if wrong:
        return FAIL, f"a cap improved the band: {', '.join(wrong)}"
    return PASS, f"the worst of the two always wins, over {len(BANDS)**2} pairs"


@case("QA-AM-3303", "Nothing is stored, so the score cannot go stale")
def am_3303(ctx: Ctx) -> Result:
    """"A health score that is written down is a health score that is stale,
    and staleness is exactly the condition it exists to detect." Asserted
    against the schema, because a persisted score is a table."""
    import pathlib
    import re
    schema = "\n".join(
        p.read_text(encoding="utf-8")
        for p in pathlib.Path("db/schema").rglob("*.py"))
    stored = re.findall(r'"(\w*health\w*)"', schema)
    scoring = [t for t in set(stored) if "score" in t or t.endswith("_health")]
    if scoring:
        return FAIL, (f"a health score is persisted in {scoring}, so it can "
                      f"drift away from the registers it is derived from")
    return PASS, "no health table; the score is derived on every read"


@case("QA-AM-3305", "The estate view separates a poor score from a thin one")
def am_3305(ctx: Ctx) -> Result:
    """A model scoring badly and a model nobody has looked at need different
    responses, and an estate list that ranks them together sends the wrong
    people to the wrong models."""
    _bare(ctx)
    got = ctx.api.get(H, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    text = got.text.lower()
    if "coverage" not in text:
        return FAIL, ("the estate view does not carry coverage, so a thin "
                      "score cannot be told from a real one")
    body = got.json() or {}
    if not any(k in body for k in ("thin", "underivable", "not_measurable",
                                   "declining", "detail")):
        return FAIL, f"the estate view offers no grouping at all: {sorted(body)}"
    return PASS, f"the estate view reports {sorted(body)[:6]}"
