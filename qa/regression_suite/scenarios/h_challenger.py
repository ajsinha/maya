"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — champion against challenger, and the portfolio cut.

"The recommendation is never to promote. MAYA is a register: it does not run
models." What it can do is say whether the difference between two versions is
significant, whether it is material, and — most often — that there is not
enough evidence to say either. That last one is the answer a promotion
decision most needs and the one a comparison tool is least likely to give.
"""
from __future__ import annotations

from core.estate.portfolio import DIMENSIONS
from core.monitoring.challengers import (CHALLENGER_AHEAD, CHAMPION_AHEAD,
                                         INSUFFICIENT, MATERIAL_BY_DEFAULT,
                                         MINIMUM_PAIRS, NO_DIFFERENCE,
                                         RECOMMENDATIONS)
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

CC = "/api/v1/champion-challenger"
P = "/api/v1/portfolio"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("cc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    for semver in ("1.0.0", "2.0.0"):
        ctx.api.post(f"{M}/{name}/versions", json={"semver": semver},
                     auth=ctx.people["developer"])
    return f"maya://model/{name}"


def _compare(ctx: Ctx, urn: str, champion="1.0.0", challenger="2.0.0"):
    return ctx.api.get(f"{CC}?urn={urn}&champion={champion}"
                       f"&challenger={challenger}", auth=ctx.people["risk"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-AM-273", "Compare a version against itself")
def am_273(ctx: Ctx) -> Result:
    """A comparison of a thing with itself has a p-value and means nothing,
    and somebody would put it in a promotion paper."""
    got = _compare(ctx, _model(ctx), champion="1.0.0", challenger="1.0.0")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a version was compared against itself"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-274", "Two versions that share no monitor definition")
def am_274(ctx: Ctx) -> Result:
    """Comparing two versions measured by different things is comparing two
    numbers, not two models."""
    got = _compare(ctx, _model(ctx))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        body = got.json() or {}
        if body.get("tests"):
            return FAIL, ("two versions with no monitors in common produced "
                          "test results")
        return PASS, f"no tests, recommendation {body.get('recommendation')}"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-5200", "The recommendation vocabulary never says promote")
def am_5200(ctx: Ctx) -> Result:
    """"MAYA is a register: it does not run models." A recommendation to
    promote would be the register making the decision it exists to record.
    """
    for word in ("promote", "deploy", "switch", "adopt", "replace"):
        if any(word in r for r in RECOMMENDATIONS):
            return FAIL, (f"'{word}' appears in the recommendations "
                          f"{RECOMMENDATIONS}; the register is deciding")
    if CHALLENGER_AHEAD not in RECOMMENDATIONS or \
            CHAMPION_AHEAD not in RECOMMENDATIONS:
        return FAIL, f"the directional verdicts are missing: {RECOMMENDATIONS}"
    if INSUFFICIENT not in RECOMMENDATIONS:
        return FAIL, ("there is no way to say the evidence is insufficient, "
                      "which is the commonest honest answer")
    return PASS, f"{len(RECOMMENDATIONS)}: {', '.join(RECOMMENDATIONS)}"


@case("QA-AM-276", "Fewer paired windows than the minimum")
def am_276(ctx: Ctx) -> Result:
    """A sign test on four pairs has a best possible p-value of 0.0625 — it
    cannot reach significance at any conventional threshold, so reporting one
    would be arithmetic dressed as evidence."""
    import inspect

    from core.monitoring.challengers import ChampionChallenger
    source = inspect.getsource(ChampionChallenger)
    if "MINIMUM_PAIRS" not in source:
        return FAIL, "no minimum pair count is applied"
    if MINIMUM_PAIRS < 5:
        return FAIL, (f"the minimum is {MINIMUM_PAIRS}; below five a sign "
                      f"test cannot reach significance at 0.05")
    return PASS, f"{MINIMUM_PAIRS} pairs minimum, reported as {INSUFFICIENT}"


@case("QA-AM-282", "Significant and immaterial")
def am_282(ctx: Ctx) -> Result:
    """The distinction the whole comparison turns on. A difference can be
    statistically certain and too small to act on, and a tool reporting only
    the p-value would promote on noise measured precisely."""
    import inspect

    from core.monitoring import challengers
    source = inspect.getsource(challengers)
    if "material" not in source:
        return FAIL, "materiality is not considered at all"
    if MATERIAL_BY_DEFAULT <= 0:
        return FAIL, f"the materiality threshold is {MATERIAL_BY_DEFAULT}"
    verdict = inspect.getsource(challengers._verdict)
    if "material" not in verdict:
        return FAIL, ("the verdict is reached without consulting materiality, "
                      "so a significant but trivial difference reads as a win")
    # The CONSTANT's name, not its value. `_verdict` returns `NO_DIFFERENCE`
    # and never spells out "no_material_difference", so searching for the
    # string reports an implemented branch as absent.
    if "NO_DIFFERENCE" not in verdict:
        return FAIL, f"'{NO_DIFFERENCE}' is not reachable from the verdict"
    return PASS, (f"significance and materiality both required; threshold "
                  f"{MATERIAL_BY_DEFAULT} declared")


@case("QA-AM-5201", "The materiality threshold is declared, never inferred")
def am_5201(ctx: Ctx) -> Result:
    """"That threshold is a business judgement and is declared, never
    [inferred]." A threshold the platform chose would be the register making
    a business decision."""
    import inspect

    from core.monitoring import challengers
    doc = " ".join((inspect.getdoc(challengers) or "").split())
    if "business judgement" not in doc:
        return FAIL, ("the module does not record that the materiality "
                      "threshold is a business judgement")
    if "declared" not in doc:
        return FAIL, "it does not say the threshold is declared"
    return PASS, "the threshold is declared by the firm, not chosen here"


@case("QA-AM-320", "Cut the register by an unknown dimension")
def am_320(ctx: Ctx) -> Result:
    """A cut by a dimension that does not exist is an empty report that reads
    like an estate with nothing in it."""
    # `dimension`, not `by`. An unrecognised query parameter is ignored, so
    # the cut runs on its default and the case reports a defect that is its
    # own spelling.
    got = ctx.api.get(f"{P}?dimension=favourite_colour",
                      auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "the estate was cut by a dimension that does not exist"
    if not any(d in got.text for d in DIMENSIONS):
        return FAIL, "the refusal does not name the dimensions"
    return PASS, f"refused '{code_of(got)}', naming {len(DIMENSIONS)} dimensions"


@case("QA-AM-321", "Heatmap of a dimension against itself")
def am_321(ctx: Ctx) -> Result:
    """A diagonal grid, every off-diagonal cell empty by construction. It
    looks like a finding about the estate and is a fact about the request."""
    dimension = sorted(DIMENSIONS)[0]
    got = ctx.api.get(f"{P}/heatmap?rows={dimension}&columns={dimension}",
                      auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, (f"a heatmap of {dimension} against itself was produced; "
                      f"every off-diagonal cell is empty by construction")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-323", "A heatmap over an empty estate")
def am_323(ctx: Ctx) -> Result:
    """An empty grid is a real answer. Refusing it would make a new instance
    indistinguishable from a broken query."""
    rows, columns = sorted(DIMENSIONS)[:2]
    got = ctx.api.get(f"{P}/heatmap?rows={rows}&columns={columns}",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"a heatmap was refused '{code_of(got)}' rather than "
                      f"answering with whatever the estate holds")
    body = got.json() or {}
    if not (body.get("detail") or "").strip():
        return FAIL, ("the heatmap carries no statement, so an empty estate "
                      "and a failed query look the same")
    return PASS, str(body.get("detail"))[:90]


@case("QA-AM-327", "Aggregate exposure where no model records one")
def am_327(ctx: Ctx) -> Result:
    """A share of an exposure nobody recorded must be null and say so, not
    zero. Zero is a measurement."""
    got = ctx.api.get(f"{P}/aggregate", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    text = str(body)
    if "exposure" not in text:
        return BLOCKED, f"the aggregate reports no exposure: {sorted(body)}"
    share = body.get("share_of_exposure_known")
    if share is None and not (body.get("detail") or "").strip():
        return FAIL, ("the exposure share is null with nothing saying how "
                      "much of the estate it rests on")
    return PASS, f"exposure reported with its coverage: {str(body.get('detail'))[:80]}"


@case("QA-AM-5202", "Every portfolio dimension says what it is")
def am_5202(ctx: Ctx) -> Result:
    """A cut is a report somebody takes to a committee. A dimension nobody
    can define is a column nobody can defend."""
    mute = [k for k, v in DIMENSIONS.items() if not (v or "").strip()]
    if mute:
        return FAIL, f"dimensions with no meaning: {mute}"
    got = ctx.api.get(f"{P}/dimensions", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    for dimension in DIMENSIONS:
        if dimension not in got.text:
            return FAIL, f"'{dimension}' is accepted and not published"
    return PASS, f"{len(DIMENSIONS)} dimensions, each published with a meaning"
