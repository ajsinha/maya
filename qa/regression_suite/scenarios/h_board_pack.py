"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the board pack.

A pack is the one document a minute refers to, so the risk is not that a
number is wrong but that a number is misleading and reads as precise. Two
things make that concrete: a value the register could not compute must come
back null with a reason rather than as zero, and an indicator with no previous
pack must say so rather than showing a flattering movement of nothing.
"""
from __future__ import annotations

from core.reporting.common import (BREACH, HIGHER_IS_BETTER, LOWER_IS_BETTER,
                                   SLACK_PACKS, SLACK_UTILISATION, WITHIN)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

B = "/api/v1/board-packs"


def _packs(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("board_packs")


def _preview(ctx: Ctx, **over):
    body = {"period": "2026-Q3", "scope": {}, "note": ""}
    body.update(over)
    return ctx.api.post(f"{B}/preview", json=body, auth=ctx.people["risk"])


def _cut(ctx: Ctx, **over):
    body = {"period": "2026-Q3", "scope": {}, "note": "QA"}
    body.update(over)
    return ctx.api.post(B, json=body, auth=ctx.people["risk"])


@case("QA-AM-352", "Preview a pack and then cut one")
def am_352(ctx: Ctx) -> Result:
    """Somebody preparing for a meeting should be able to look before the
    committee is minuted against what they find — so a preview must leave no
    pack behind."""
    before = ctx.api.get(B, auth=ctx.people["risk"])
    if before.status_code >= 400:
        return BLOCKED, before.text[:170]
    n = len((before.json() or {}).get("packs") or [])
    seen = _preview(ctx)
    if seen.status_code >= 400:
        return BLOCKED, seen.text[:170]
    after = ctx.api.get(B, auth=ctx.people["risk"])
    if len((after.json() or {}).get("packs") or []) != n:
        return FAIL, "a preview recorded a pack"
    made = _cut(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    final = ctx.api.get(B, auth=ctx.people["risk"])
    if len((final.json() or {}).get("packs") or []) != n + 1:
        return FAIL, "cutting a pack recorded nothing"
    return PASS, f"{n} packs, preview changed nothing, cut added one"


@case("QA-AM-357", "An indicator the register could not compute")
def am_357(ctx: Ctx) -> Result:
    """Null with a reason, never zero. A zero reads as a measurement and a
    committee plots it."""
    got = _preview(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    indicators = (got.json() or {}).get("indicators") or []
    if not indicators:
        return BLOCKED, "the pack carries no indicators"
    # An unmeasured indicator may state its reason in any of the fields a
    # reader actually sees — the row's own detail, its status meaning, or the
    # note beside the null.
    def _says_why(row) -> bool:
        return any((row.get(k) or "").strip()
                   for k in ("detail", "status_means", "why", "note",
                             "measurement"))

    silent = [i for i in indicators
              if i.get("value") is None and not _says_why(i)]
    if silent:
        return FAIL, (f"{len(silent)} indicator(s) came back null with no "
                      f"reason anywhere a reader looks: "
                      f"{[i.get('metric') for i in silent][:4]}")
    return PASS, (f"{len(indicators)} indicators; every unmeasured one states "
                  f"why")


@case("QA-AM-363", "Utilisation against a limit of zero")
def am_363(ctx: Ctx) -> Result:
    """A limit of zero is a limit of zero, and a utilisation of infinity
    reported as a number is a number somebody plots."""
    packs = _packs(ctx)
    if packs is None:
        return BLOCKED, "no pack builder reachable from this run"

    class _Metric:
        direction = LOWER_IS_BETTER

    for direction in (LOWER_IS_BETTER, HIGHER_IS_BETTER):
        _Metric.direction = direction
        got = packs._utilisation(_Metric, 5.0, 0.0)
        if got is not None:
            return FAIL, (f"a limit of zero gave utilisation {got} under "
                          f"{direction}; infinity arrived as a number")
    return PASS, "a zero limit gives no utilisation, in both directions"


@case("QA-AM-364", "Standing at exactly the limit")
def am_364(ctx: Ctx) -> Result:
    """The boundary is where an appetite is argued about. Sitting exactly on
    a limit is within it, not through it — in both directions."""
    packs = _packs(ctx)
    if packs is None:
        return BLOCKED, "no pack builder reachable from this run"
    wrong = []
    for direction in (LOWER_IS_BETTER, HIGHER_IS_BETTER):
        class _M:
            pass
        _M.direction = direction
        # `_status`, not `_standing` — the row field is `status`.
        standing = packs._status(_M, 10.0, 10.0, None)
        if standing == BREACH:
            wrong.append(direction)
    if wrong:
        return FAIL, (f"a value exactly on the limit reads as a breach under "
                      f"{', '.join(wrong)}")
    return PASS, f"exactly on the limit is '{WITHIN}' in both directions"


@case("QA-AM-362", "Movement with no previous pack over this scope")
def am_362(ctx: Ctx) -> Result:
    """A first pack has nothing to move from, and reporting a change of zero
    would be a flattering number about no history at all."""
    packs = _packs(ctx)
    if packs is None:
        return BLOCKED, "no pack builder reachable from this run"
    moved = packs._movement({"metric": "anything", "value": 1.0,
                             "direction": LOWER_IS_BETTER}, None)
    if moved.get("change") is not None:
        return FAIL, (f"a pack with no predecessor reported a change of "
                      f"{moved.get('change')}")
    if "no previous pack" not in (moved.get("detail") or ""):
        return FAIL, f"the reason is not stated: {moved}"
    return PASS, moved["detail"]


@case("QA-AM-361", "Movement against a pack that did not measure it")
def am_361(ctx: Ctx) -> Result:
    """"Not comparable" and "unchanged" are different facts, and showing the
    second for the first is the way a pack lies quietly."""
    packs = _packs(ctx)
    if packs is None:
        return BLOCKED, "no pack builder reachable from this run"
    previous = {"as_at": 1.0,
                "indicators": [{"metric": "anything", "value": None}]}
    moved = packs._movement({"metric": "anything", "value": 3.0,
                             "direction": LOWER_IS_BETTER}, previous)
    if moved.get("change") is not None:
        return FAIL, (f"a change of {moved.get('change')} was computed "
                      f"against a pack that did not measure the indicator")
    if "not comparable" not in (moved.get("detail") or ""):
        return FAIL, f"the reason is not stated: {moved}"
    return PASS, moved["detail"]


@case("QA-AM-366", "One pack under the slack threshold")
def am_366(ctx: Ctx) -> Result:
    """Slack needs a RUN of quiet packs. Reporting it on the first would make
    every newly-set limit look unused."""
    packs = _packs(ctx)
    if packs is None:
        return BLOCKED, "no pack builder reachable from this run"
    row = {"metric": f"qa-{ctx.unique('m')}",
           "utilisation": SLACK_UTILISATION / 2}
    if packs._slack(row, {"scope": ctx.unique("s")}) is not None:
        return FAIL, ("slack was reported on a single pack; a limit set "
                      "today would read as never approached")
    return PASS, f"no slack until {SLACK_PACKS} quiet pack(s)"


@case("QA-AM-2903", "A limit at or above the threshold is never slack")
def am_2903(ctx: Ctx) -> Result:
    """The threshold is inclusive at the top: a limit used exactly 25% is
    being approached, not ignored."""
    packs = _packs(ctx)
    if packs is None:
        return BLOCKED, "no pack builder reachable from this run"
    for utilisation in (SLACK_UTILISATION, SLACK_UTILISATION + 0.5, 1.0):
        row = {"metric": "qa", "utilisation": utilisation}
        if packs._slack(row, {}) is not None:
            return FAIL, (f"utilisation {utilisation} was reported as slack, "
                          f"at or above the {SLACK_UTILISATION} threshold")
    if packs._slack({"metric": "qa", "utilisation": None}, {}) is not None:
        return FAIL, "an indicator with no utilisation was reported as slack"
    return PASS, f"slack only below {SLACK_UTILISATION}, and never on null"


@case("QA-AM-367", "A pack carries no composite score")
def am_367(ctx: Ctx) -> Result:
    """A single number for a model's risk is the thing a committee reads
    instead of the pack, and the platform refuses to produce one. The refusal
    has to be visible, not merely an absence."""
    got = ctx.api.get(B, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if "no_composite" not in body:
        return FAIL, ("the pack listing does not say that no composite score "
                      "is produced, so its absence reads as an omission")
    if not str(body.get("no_composite") or "").strip():
        return FAIL, "the refusal to composite is stated with no reason"
    seen = _preview(ctx)
    for banned in ("model_risk_score", "composite_score", "overall_score"):
        if banned in seen.text:
            return FAIL, f"a pack carries '{banned}'"
    return PASS, str(body["no_composite"])[:100]
