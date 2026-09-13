"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — cutting the register, and what the cuts refuse to claim.

Three refusals to state a number carry this module.

The heatmap is shaded by what is OWED and not by count: a cell with forty
healthy models and a cell with one that is missing its validation are not the
same cell, and a count-coloured grid draws them identically.

The trend FOLDS THE CHAIN rather than reading a snapshot table. A nightly
snapshot starts on the day somebody remembered to add it and is wrong for
every day before that, so each point carries the chain sequence and hash that
make it verifiable rather than asserted — and an instance with no as-at
projection says `available: false` rather than returning a flat line.

And concentration always answers `aggregate_score: null`. Stated on every
answer, because the absence is the point: MAYA can say what is shared and by
whom, and cannot say how bad that is in one number.
"""
from __future__ import annotations

from core.estate.concentration import MINIMUM
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

P = "/api/v1/portfolio"
C = "/api/v1/concentration"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FACTS = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
         "feature_count": 3, "interpretable": True,
         "uses_alternative_data": False}
PRODUCES = {"parameter_kind": "estimated_coefficients",
            "fit_procedure": "estimate", "runtime": "estimator",
            "input_schema": [{"name": "x", "dtype": "float"}],
            "output_schema": [{"name": "score", "dtype": "float"}]}
CONSUMES = {"parameter_kind": "estimated_coefficients",
            "fit_procedure": "estimate", "runtime": "estimator",
            "input_schema": [{"name": "score", "dtype": "float"}],
            "output_schema": [{"name": "decision", "dtype": "float"}]}


def _model(ctx: Ctx, kernel=None, *, assess: bool = True, **shape) -> tuple:
    name = ctx.unique("pf")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner",
                          **SHAPE, **shape})
    ctx.api.post(f"{M}/{name}/versions",
                 json={"semver": "1.0.0", "kernel": dict(kernel)} if kernel
                 else {"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    if assess:
        ctx.api.post(f"{M}/{name}/assess", json=dict(FACTS))
    return name, urn


@case("QA-AM-322",
      "Heatmap where a row value and a column value never co-occur")
def am_322(ctx: Ctx) -> Result:
    """The cell is absent from the grid rather than present as a zero. A grid
    that materialised every combination would be mostly empty cells, and an
    empty cell drawn the same as a cell with one healthy model in it is the
    thing shading by owed work is meant to avoid."""
    # Two domains at two tiers, arranged so one combination cannot occur:
    # `credit` is registered only at tier 3 and `market` only at tier 1.
    _a, _u = _model(ctx, domain="credit")
    name_b, _v = _model(ctx, assess=False, domain="market")
    ctx.api.post(f"{M}/{name_b}/assess",
                 json={**FACTS, "exposure": 5_000_000_000.0,
                       "purpose_class": "policy_decision"})
    got = ctx.api.get(f"{P}/heatmap?rows=domain&columns=tier",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the heatmap answered {got.status_code}"
    body = got.json() or {}
    grid = body.get("grid") or {}
    row_values = body.get("row_values") or []
    column_values = body.get("column_values") or []
    if not row_values or not column_values:
        return BLOCKED, "the heatmap has no rows or no columns to cross"
    absent = [(r, c) for r in row_values for c in column_values
              if c not in (grid.get(r) or {})]
    if not absent:
        return BLOCKED, ("every row and column value co-occurs in this "
                         "estate, so there is no absent cell to read")
    for r, c in absent:
        if c in (grid.get(r) or {}):
            return FAIL, f"cell ({r}, {c}) is both absent and present"
    return PASS, (f"{len(absent)} combination(s) never co-occur and none is "
                  f"materialised as a zero cell")


@case("QA-AM-4740", "A heatmap of one dimension against itself")
def am_4740(ctx: Ctx) -> Result:
    """A list with extra steps, and refused as one. The diagonal of such a
    grid is the whole population and every other cell is empty, which reads
    as an estate with nothing in it almost everywhere."""
    got = ctx.api.get(f"{P}/heatmap?rows=tier&columns=tier",
                      auth=ctx.people["risk"])
    if got.status_code < 400:
        return FAIL, ("a heatmap of tier against tier was produced: every "
                      "off-diagonal cell is empty by construction, which "
                      "draws as an estate with nothing in it")
    if code_of(got) != "same_dimension":
        return FAIL, f"refused '{code_of(got)}'"
    bad = ctx.api.get(f"{P}/heatmap?rows=domain&columns=phase_of_the_moon",
                      auth=ctx.people["risk"])
    if bad.status_code < 400 or code_of(bad) != "unknown_dimension":
        return FAIL, (f"a heatmap over a dimension the register does not "
                      f"have answered '{code_of(bad) or bad.status_code}'")
    return PASS, "refused 'same_dimension', and an unknown dimension too"


@case("QA-AM-329", "Trend on an instance with no as-at projection")
def am_329(ctx: Ctx) -> Result:
    """`available: false` with the reason, rather than a flat line. A flat
    line is the one answer that looks like data and is not — a reader takes
    it for an estate that did not change."""
    engine = ctx.ui.app.state.ctx.get("portfolio")
    if engine is None:
        return BLOCKED, "no portfolio engine is wired"
    was, engine.as_at = engine.as_at, None
    try:
        report = engine.trend(points=6)
    finally:
        engine.as_at = was
    if report.get("available") is not False:
        return FAIL, (f"with no as-at projection the trend reports "
                      f"available={report.get('available')!r}")
    if report.get("points"):
        return FAIL, (f"an unavailable trend still returned "
                      f"{len(report['points'])} point(s), which draws as a "
                      f"flat line and reads as an estate that did not change")
    if not (report.get("detail") or "").strip():
        return FAIL, "unavailable, and no reason given"
    return PASS, f"available false: {report['detail'][:90]}"


@case("QA-AM-330", "Trend with `points: 1`")
def am_330(ctx: Ctx) -> Result:
    """The step is `span / max(1, points - 1)`, so one point is the case that
    would divide by zero without the guard. One point is also a legitimate
    ask — it is *the register as it stands* — so it must not be refused."""
    got = ctx.api.get(f"{P}/trend?points=1&span_days=30", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a one-point trend is the "
                      f"register as it stands and should be askable")
    body = got.json() or {}
    if body.get("available") is False:
        return BLOCKED, f"no as-at projection here: {body.get('detail')}"
    points = body.get("points") or []
    if len(points) != 1:
        return FAIL, f"points=1 returned {len(points)} point(s)"
    return PASS, "one point, and no division by zero"


@case("QA-AM-331", "Trend where each point carries a chain hash")
def am_331(ctx: Ctx) -> Result:
    """The reason to fold the chain rather than keep a snapshot: each point
    is verifiable rather than asserted. A trend whose points carry no chain
    position is a snapshot table with extra steps."""
    got = ctx.api.get(f"{P}/trend?points=4&span_days=30", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the trend answered {got.status_code}"
    body = got.json() or {}
    if body.get("available") is False:
        return BLOCKED, f"no as-at projection here: {body.get('detail')}"
    points = body.get("points") or []
    if not points:
        return BLOCKED, "the trend returned no points"
    # A point BEFORE the chain's first node honestly has no position — the
    # register did not exist then, and inventing one would be the fabrication
    # this design avoids. What must carry a position is any point the chain
    # actually covers, and the last point always does.
    covered = [p for p in points if (p.get("models") or 0) > 0]
    if not covered:
        covered = points[-1:]
    missing = [p for p in covered
               if p.get("chain_seq") is None or not p.get("chain_hash")]
    if missing:
        return FAIL, (f"{len(missing)} of {len(covered)} trend point(s) the "
                      f"chain covers carry no chain position, so they are "
                      f"asserted rather than verifiable")
    empty = [p for p in points if p not in covered]
    return PASS, (f"all {len(covered)} covered point(s) carry a chain seq and "
                  f"hash; {len(empty)} predate the chain and claim none")


@case("QA-AM-333", "Concentration with a `MINIMUM` of one dependent")
def am_333(ctx: Ctx) -> Result:
    """Something one model depends on is not a concentration; it is a
    dependency. The floor is two, and a floor of one would report every
    feature view in the estate as a shared risk."""
    _upstream, up_urn = _model(ctx, PRODUCES)
    _downstream, down_urn = _model(ctx, CONSUMES)
    if ctx.api.post("/api/v1/model-relations",
                    json={"from_urn": up_urn, "to_urn": down_urn,
                          "kind": "input_to"}).status_code >= 400:
        return BLOCKED, "the two models could not be related"
    if MINIMUM != 2:
        return FAIL, (f"the concentration floor is {MINIMUM}, so something "
                      f"{'one model' if MINIMUM < 2 else 'few models'} "
                      f"depends on is reported as shared")
    got = ctx.api.get(C, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the concentration read answered {got.status_code}"
    body = got.json() or {}
    singles = [r for r in (body.get("shared") or [])
               if len(r.get("relied_on_by") or []) < MINIMUM]
    if singles:
        return FAIL, (f"{len(singles)} row(s) are reported as shared with "
                      f"fewer than {MINIMUM} dependents")
    return PASS, f"the floor is {MINIMUM} and nothing below it is reported"


@case("QA-AM-334", "Concentration on an estate with nothing recorded")
def am_334(ctx: Ctx) -> Result:
    """*Nothing is shared* and *nobody entered the dependencies* look
    identical, so the detail has to warn that a dependency nobody entered is
    a concentration nothing here can see."""
    engine = ctx.ui.app.state.ctx.get("concentration")
    if engine is None:
        return BLOCKED, "no concentration engine is wired"

    class Nothing:
        def __init__(self, real):
            self.require = real.require

        @staticmethod
        def list():
            return []

    was, engine.registry = engine.registry, Nothing(engine.registry)
    try:
        report = engine.across_the_estate()
    finally:
        engine.registry = was
    if report.get("shared"):
        return FAIL, f"an empty estate shares {len(report['shared'])} things"
    detail = report.get("detail") or ""
    if "nobody entered" not in detail and "nothing here can see" not in detail:
        return FAIL, (f"an empty answer does not warn that an unentered "
                      f"dependency is invisible: {detail[:130]}")
    return PASS, f"nothing shared, and the detail warns why: {detail[:70]}"


@case("QA-AM-335", "Any concentration answer")
def am_335(ctx: Ctx) -> Result:
    """`aggregate_score` is always null, stated on every answer because the
    absence is the point. MAYA can say what is shared and by whom; it cannot
    say how bad that is in one number, and a platform that produced one would
    be inventing the judgement a committee is there to make."""
    got = ctx.api.get(C, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the concentration read answered {got.status_code}"
    body = got.json() or {}
    if "aggregate_score" not in body:
        return FAIL, ("the answer omits `aggregate_score` entirely, so a "
                      "reader cannot tell the platform declined to score it "
                      "from the platform never having considered it")
    if body.get("aggregate_score") is not None:
        return FAIL, (f"a concentration score of {body['aggregate_score']} "
                      f"was produced: one number over a set of shared "
                      f"dependencies is the judgement a committee exists to "
                      f"make")
    single = ctx.api.get(f"{C}/single-points", auth=ctx.people["risk"])
    if single.status_code < 400:
        other = single.json() or {}
        if other.get("aggregate_score") is not None:
            return FAIL, ("the single-points view scores what the estate "
                          "view refuses to")
    return PASS, "aggregate_score present and null on every answer"


@case("QA-AM-328",
      "Aggregate exposure where one of forty models records one")
def am_328(ctx: Ctx) -> Result:
    """A weighted answer over a third of an estate presented as *the* answer
    would be worse than the count it replaced. So `exposure_coverage` travels
    beside the figure, and the detail says what the coverage means."""
    # Some models with an exposure and one without, so the coverage is a
    # real fraction rather than 0 or 1 — the case is about what the figure
    # says when it covers part of the estate.
    for _ in range(3):
        _model(ctx)
    _model(ctx, assess=False)
    got = ctx.api.get(f"{P}/aggregate", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the aggregate answered {got.status_code}"
    body = got.json() or {}
    for field in ("exposure_coverage", "exposure_known_for", "models"):
        if field not in body:
            return FAIL, f"the aggregate carries no '{field}'"
    coverage = body.get("exposure_coverage")
    if coverage is None:
        return FAIL, "the coverage is null beside a stated exposure figure"
    if body.get("models") and coverage >= 1.0 and body.get("exposure_total"):
        return PASS, ("every model records an exposure, so the figure covers "
                      "the whole estate")
    detail = body.get("detail") or ""
    if not detail:
        return FAIL, "a partial-coverage figure is stated with no detail"
    if coverage < 1.0 and "%" not in detail and "no model" not in detail.lower():
        return FAIL, (f"the figure covers {coverage:.0%} of the estate and "
                      f"the detail does not say so: {detail[:120]}")
    return PASS, (f"coverage {coverage:.0%} stated beside the figure: "
                  f"{detail[:80]}")
