"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the model health score, and what it refuses to say.

The score is a weighted mean over six components, and almost everything worth
testing is about what it does when a component cannot be measured. **A score
of nothing is not a score of zero**, and printing a number over one measured
component would be inventing one — so `coverage` travels beside the score and
the detail says when the number says more about how little is known than about
the model.

The caps are the other half. A band that is `poor` because the validation
lapsed is a different piece of work from one that is `poor` because three
monitors are failing, so the arithmetic band and the capped band are reported
separately and the cap says why. **No amount of good news elsewhere outweighs
a cap** — which is what stops a model with one Critical finding past its date
averaging its way back to `good`.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

HEALTH = "/api/v1/model-health"
M = "/api/v1/models"
F = "/api/v1/findings"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FACTS = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
         "feature_count": 3, "interpretable": True,
         "uses_alternative_data": False}
DAY = 86400.0


def _model(ctx: Ctx, *, assess: bool = True) -> tuple:
    name = ctx.unique("hl")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    if assess:
        ctx.api.post(f"{M}/{name}/assess", json=dict(FACTS))
    return name, urn


def _health(ctx: Ctx, urn: str) -> dict:
    got = ctx.api.get(f"{HEALTH}?urn={urn}", auth=ctx.people["risk"])
    return got.json() if got.status_code < 400 else {}


def _component(reading: dict, key: str) -> dict:
    for part in reading.get("components") or []:
        if part.get("component") == key:
            return part
    return {}


def _raise(ctx: Ctx, urn: str, **over) -> str:
    body = {"urn": urn, "severity": "Critical", "title": ctx.unique("finding"),
            "owner": "person/owner", "description": "qa",
            "category": "general", "source": "validation"}
    body.update(over)
    made = ctx.api.post(F, json=body, auth=ctx.people["risk"])
    return made.json().get("id", "") if made.status_code < 400 else ""


@case("QA-AM-290", "A model with no overlays at all")
def am_290(ctx: Ctx) -> Result:
    """Not absent, and this is the distinction the component turns on. A
    model carrying no overlay is a MEASURED fact and a good one — nothing is
    being adjusted, so nothing is being relied on. Reporting it as absent
    would drop 15% of the weight for every model that never needed an
    overlay."""
    _name, urn = _model(ctx)
    part = _component(_health(ctx, urn), "overlay_reliance")
    if not part:
        return BLOCKED, "the health reading carries no overlay component"
    if not part.get("measured"):
        return FAIL, ("a model with no overlays reports overlay_reliance as "
                      "ABSENT, so every model that never needed an overlay "
                      "loses 15% of its measurable weight")
    if part.get("score") != 1.0:
        return FAIL, f"no overlays scores {part.get('score')} rather than 1.0"
    if "no active overlay" not in (part.get("detail") or ""):
        return FAIL, f"the detail reads '{part.get('detail')}'"
    return PASS, "measured at 1.0: nothing adjusted, nothing relied on"


@case("QA-AM-291", "A model with one Critical finding past its date")
def am_291(ctx: Ctx) -> Result:
    """The cap that stops averaging. A Critical finding past its remediation
    date caps the band at `poor` however well everything else scores, and the
    reading has to report the arithmetic band separately so a reader can see
    the cap did the work."""
    _name, urn = _model(ctx)
    fid = _raise(ctx, urn, severity="Critical")
    if not fid:
        return BLOCKED, "the finding could not be raised"
    engine = ctx.ui.app.state.ctx.get("findings")
    if engine is None:
        return BLOCKED, "no findings register is wired"
    row = engine.require(fid)
    # Wound back rather than waited out: there is no API for a due date in
    # the past and there should not be one.
    engine.findings.set({"due_at": row["raised_at"] - DAY}, id=fid)
    reading = _health(ctx, urn)
    if reading.get("band") != "poor":
        return FAIL, (f"a Critical finding past its date leaves the band "
                      f"'{reading.get('band')}'")
    caps = [c for c in (reading.get("caps") or [])
            if c.get("component") == "open_findings"]
    if not caps:
        return FAIL, "the band is poor and no cap says why"
    if "past their remediation date" not in caps[0].get("why", ""):
        return FAIL, f"the cap reads '{caps[0].get('why')}'"
    # The arithmetic band is poor here as well, because a model built for
    # this case has also never been validated. The cap is still the thing
    # being tested: it must be PRESENT and name the finding, so that a model
    # scoring well everywhere else cannot average its way past it.
    return PASS, (f"arithmetic {reading.get('arithmetic_band')}, band poor, "
                  f"and the findings cap says: {caps[0]['why'][:70]}")


@case("QA-AM-292", "A model with twenty open Observation findings")
def am_292(ctx: Ctx) -> Result:
    """Weighted by severity, because five Observations and one Critical are
    not the same estate and must not divide to the same number. Twenty
    Observations should not cap the band at all — nothing about them is past
    a date or blocking."""
    _name, urn = _model(ctx)
    for _ in range(20):
        if not _raise(ctx, urn, severity="Observation"):
            return BLOCKED, "an observation finding could not be raised"
    reading = _health(ctx, urn)
    part = _component(reading, "open_findings")
    if not part.get("measured"):
        return BLOCKED, "the findings component is not measured"
    caps = [c for c in (reading.get("caps") or [])
            if c.get("component") == "open_findings"]
    if caps:
        return FAIL, (f"twenty Observation findings capped the band: "
                      f"{caps[0].get('why')}")
    critical = _model(ctx)[1]
    _raise(ctx, critical, severity="Critical")
    one = _component(_health(ctx, critical), "open_findings")
    # A HIGHER component score is healthier, so twenty Observations must score
    # ABOVE one Critical. Reading it the other way round is how a health
    # score comes to reward the estate that raises fewer findings.
    if part.get("score", 0.0) <= one.get("score", 1.0):
        return FAIL, (f"twenty Observations score {part.get('score')} and one "
                      f"Critical scores {one.get('score')}: the weighting "
                      f"reads severity backwards, so twenty trivia are worse "
                      f"than one Critical")
    return PASS, (f"twenty Observations score {part.get('score')} against "
                  f"{one.get('score')} for one Critical, and nothing is capped")


@case("QA-AM-293", "A model that has never been validated")
def am_293(ctx: Ctx) -> Result:
    """Never validated is not an absence of a window; it is a model standing
    on nothing. So `validation_currency` is measured at 0.0 with a `poor`
    cap, rather than dropped from the mean — dropping it would let a model
    nobody has ever validated score higher than one whose validation lapsed
    last week."""
    _name, urn = _model(ctx)
    reading = _health(ctx, urn)
    part = _component(reading, "validation_currency")
    if not part:
        return BLOCKED, "the health reading carries no validation component"
    if not part.get("measured"):
        return FAIL, ("a model that has never been validated reports "
                      "validation_currency as ABSENT, so it is dropped from "
                      "the mean and scores higher than one whose validation "
                      "lapsed last week")
    if part.get("score") != 0.0:
        return FAIL, f"never validated scores {part.get('score')}"
    caps = [c for c in (reading.get("caps") or [])
            if c.get("component") == "validation_currency"]
    if not caps or caps[0].get("band") != "poor":
        return FAIL, "never validated does not cap the band at poor"
    return PASS, "measured 0.0, capped poor, 'never been validated'"


@case("QA-AM-299", "Estate health over an empty estate")
def am_299(ctx: Ctx) -> Result:
    """A fresh estate must read as zero models rather than as an estate in
    perfect health — and a by-band summary over nothing must not report every
    band at zero as though it had counted them."""
    engine = ctx.ui.app.state.ctx.get("model_health")
    if engine is None:
        return BLOCKED, "no health engine is wired"

    class Nothing:
        """An estate with no models. It cannot be built through the API —
        the QA harness registers models — so the catalogue is emptied here."""

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
    if report.get("models") not in (0, [], None):
        rows = report.get("models")
        if isinstance(rows, list) and rows:
            return FAIL, f"an empty estate reports {len(rows)} model(s)"
    detail = report.get("detail") or ""
    if not detail:
        return FAIL, "an empty estate reports no detail at all"
    by_band = report.get("by_band") or {}
    if by_band and sum(by_band.values()):
        return FAIL, f"an empty estate counts models by band: {by_band}"
    return PASS, f"no models, and the detail reads: {detail[:90]}"


@case("QA-AM-4730",
      "The score is absent rather than zero when nothing is measurable")
def am_4730(ctx: Ctx) -> Result:
    """The sentence the module is built around: *that is a score of nothing,
    not a score of zero, and printing a number here would be inventing one*.
    A model with no monitors, no validation and no findings must come back
    with a null score and `derivable: false` rather than 0."""
    _name, urn = _model(ctx, assess=False)
    reading = _health(ctx, urn)
    if not reading:
        return BLOCKED, "the health reading could not be read"
    measured = reading.get("measured") or []
    if reading.get("score") is None:
        if reading.get("derivable"):
            return FAIL, "the score is null and `derivable` says true"
        if "not a score of zero" not in (reading.get("detail") or ""):
            return FAIL, (f"the score is absent and the detail does not say "
                          f"why: {reading.get('detail')}")
        return PASS, "score null, derivable false, and the detail says so"
    if reading.get("score") == 0.0 and not measured:
        return FAIL, ("nothing about this model is measurable and the score "
                      "reads 0.0, which is a number invented from an absence")
    if reading.get("coverage", 1.0) < 0.5:
        detail = reading.get("detail") or ""
        if "how little is known" not in detail:
            return FAIL, (f"coverage is {reading.get('coverage')} and the "
                          f"detail does not warn that the number says more "
                          f"about what is unknown: {detail[:120]}")
        return PASS, (f"scored over {reading.get('coverage'):.0%} of the "
                      f"weight, and the detail says so")
    return PASS, (f"score {reading.get('score')} over "
                  f"{reading.get('coverage'):.0%} of the weight "
                  f"({', '.join(measured)})")
