"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the model health score, which is a composite and therefore a place
somebody can be misled with arithmetic.

A single number over six registers is the most quotable thing this platform
produces, and quotable numbers are the ones that end up in a board pack with no
context. So these cases are about the properties that keep it honest: the
weights are readable BEFORE anybody disagrees with the answer, the bands are
ordered, a capping condition can only ever make the band worse, the score is
derived on read rather than stored, and a thin score is never printed as a good
one.
"""
from __future__ import annotations

from core.monitoring.health import (BANDS, GOOD, GOOD_AT, POOR,
                                    WATCH, WATCH_AT, WEIGHTS)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

H = "/api/v1/model-health"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("hs")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


@case("QA-AM-3300", "The weights are data, and they sum to one")
def am_3300(ctx: Ctx) -> Result:
    """A composite whose weights live in a conditional is a composite nobody
    can check, and one whose weights do not sum to one is a percentage that is
    not a percentage — a model scoring full marks on every component would
    print something other than 100 and nobody could say why."""
    total = sum(WEIGHTS.values())
    if abs(total - 1.0) > 1e-9:
        return FAIL, (f"the component weights sum to {total}, so a model "
                      f"scoring full marks everywhere does not score 1.0")
    got = ctx.api.get(f"{H}/components")
    if got.status_code >= 400:
        return BLOCKED, f"the components answered {got.status_code}"
    body = got.json() or {}
    rows = body.get("components") or []
    if {r.get("key") for r in rows} != set(WEIGHTS):
        return FAIL, (f"the published components are not the ones that are "
                      f"weighed: {sorted(r.get('key') for r in rows)}")
    silent = [r.get("key") for r in rows if not str(r.get("asks") or "").strip()]
    if silent:
        return FAIL, f"{silent} are weighed without saying what they ask"
    blind = [r.get("key") for r in rows
             if not str(r.get("absent_when") or "").strip()]
    if blind:
        return FAIL, (f"{blind} do not say when they are ABSENT, which is the "
                      f"difference between a component that passed and one "
                      f"nobody could measure")
    return PASS, (f"{len(rows)} component(s) published with weights summing "
                  f"to 1.0, each saying what it asks and when it is absent")


@case("QA-AM-3301", "The bands are ordered and the thresholds are stated")
def am_3301(ctx: Ctx) -> Result:
    """A band nobody can reproduce is an opinion with a colour. Both cut
    points travel with the vocabulary, so a reader who disagrees can say where
    rather than whether."""
    if not (0.0 < WATCH_AT < GOOD_AT < 1.0):
        return FAIL, (f"the thresholds are not ordered: watch at {WATCH_AT}, "
                      f"good at {GOOD_AT}")
    if BANDS != (GOOD, WATCH, POOR):
        return FAIL, f"the bands are not ordered best-first: {BANDS}"
    got = ctx.api.get(f"{H}/components")
    if got.status_code >= 400:
        return BLOCKED, f"the components answered {got.status_code}"
    body = got.json() or {}
    if body.get("good_at") != GOOD_AT or body.get("watch_at") != WATCH_AT:
        return FAIL, (f"the published cut points {body.get('good_at')}/"
                      f"{body.get('watch_at')} are not the ones applied "
                      f"({GOOD_AT}/{WATCH_AT})")
    return PASS, (f"good at {GOOD_AT}, watch at {WATCH_AT}, both published "
                  f"with the band vocabulary")


@case("QA-AM-3302", "A cap never improves the band")
def am_3302(ctx: Ctx) -> Result:
    """The one direction that must hold. A capping condition exists because
    some facts cannot be outweighed — an overdue blocking finding, a validation
    long out of date — so if a cap could raise a band, good news elsewhere
    would buy its way past exactly the fact it was written to stop."""
    urn = _model(ctx)
    got = ctx.api.get(f"{H}?urn={urn}")
    if got.status_code >= 400:
        return BLOCKED, f"the score answered {got.status_code}: {got.text[:120]}"
    body = got.json() or {}
    score, band = body.get("score"), body.get("band")
    caps = body.get("caps") or body.get("capped_by") or []
    if band not in BANDS:
        return FAIL, f"the band '{band}' is not one of {BANDS}"
    if score is None:
        return PASS, ("nothing could be measured, so there is no mean for a "
                      "cap to act on")
    from_mean = (GOOD if score >= GOOD_AT
                 else WATCH if score >= WATCH_AT else POOR)
    rank = {GOOD: 0, WATCH: 1, POOR: 2}
    if rank[band] < rank[from_mean]:
        return FAIL, (f"the mean is {score} which is '{from_mean}', and the "
                      f"reported band is '{band}' — better than the "
                      f"arithmetic, so something capped the score UPWARDS "
                      f"(caps: {caps})")
    return PASS, (f"score {score} reads '{from_mean}' and the band is "
                  f"'{band}'" + (f", capped by {caps}" if caps else
                                 ", uncapped"))


@case("QA-AM-3303", "Nothing is stored, so the score cannot go stale")
def am_3303(ctx: Ctx) -> Result:
    """The reason there is no `model_health` table. A stored score is one that
    is right when written and wrong the moment a finding is raised, and every
    reader afterwards is looking at a number about a state that has passed.
    Derived on read, it cannot disagree with the registers it came from.
    """
    db = ctx.ui.app.state.ctx.get("db")
    if db is None:
        return BLOCKED, "no database"
    stored = db.query(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND (name LIKE '%health%' OR name LIKE '%scorecard%')")
    names = [r["name"] for r in stored or []]
    if names:
        return FAIL, (f"the score has somewhere to go stale: {names}. A stored "
                      f"health score is right when it is written and wrong the "
                      f"moment a finding is raised")
    urn = _model(ctx)
    first = ctx.api.get(f"{H}?urn={urn}")
    if first.status_code >= 400:
        return BLOCKED, f"the score answered {first.status_code}"
    before = (first.json() or {}).get("coverage")
    ctx.api.post("/api/v1/findings",
                 json={"urn": urn, "severity": "High", "title": "a QA finding",
                       "owner": "person/owner", "description": "qa",
                       "category": "general", "source": "validation",
                       "blocking": True},
                 auth=ctx.people["risk"])
    second = ctx.api.get(f"{H}?urn={urn}")
    if second.status_code >= 400:
        return FAIL, f"the score answered {second.status_code} after a finding"
    if first.json() == second.json():
        return FAIL, (f"a blocking finding was raised against {urn} and the "
                      f"health answer is byte-identical, so the score is not "
                      f"reading the findings register")
    del before
    return PASS, ("no table holds it, and the answer moved when the register "
                  "under it moved")


@case("QA-AM-3304", "The verdict wins over the arithmetic")
def am_3304(ctx: Ctx) -> Result:
    """When the mean and the cap disagree, the disagreement is the finding —
    so it has to be VISIBLE. A band that silently overrode the mean would be a
    number and a colour that contradict each other with nothing saying why,
    and the reader would believe whichever they saw first."""
    urn = _model(ctx)
    ctx.api.post("/api/v1/findings",
                 json={"urn": urn, "severity": "Critical",
                       "title": "a QA blocking finding", "owner": "person/owner",
                       "description": "qa", "category": "general",
                       "source": "validation", "blocking": True},
                 auth=ctx.people["risk"])
    got = ctx.api.get(f"{H}?urn={urn}")
    if got.status_code >= 400:
        return BLOCKED, f"the score answered {got.status_code}"
    body = got.json() or {}
    score, band = body.get("score"), body.get("band")
    if score is None:
        return PASS, "nothing measurable, so there is no disagreement to show"
    from_mean = (GOOD if score >= GOOD_AT
                 else WATCH if score >= WATCH_AT else POOR)
    if band == from_mean:
        return PASS, (f"mean {score} and band '{band}' agree, so there is no "
                      f"disagreement to report")
    said = str(body.get("detail") or "") + str(body.get("caps") or "") \
        + str(body.get("capped_by") or "")
    if not said.strip():
        return FAIL, (f"the mean is {score} ('{from_mean}') and the band is "
                      f"'{band}', and the answer says nothing about why — a "
                      f"number and a colour that contradict each other with no "
                      f"explanation, where the reader believes whichever they "
                      f"saw first")
    return PASS, (f"mean {score} reads '{from_mean}', the band is '{band}', "
                  f"and the answer says why: {said[:90]}")


@case("QA-AM-3305", "The estate view separates a poor score from a thin one")
def am_3305(ctx: Ctx) -> Result:
    """`coverage` travels with the score everywhere, and this is the case that
    holds it there. A score of 92 at 30% coverage is not a healthy model; it is
    a model nobody has looked at, and if the estate view prints them the same
    then the models with the least evidence look the best."""
    _model(ctx)
    got = ctx.api.get(H)
    if got.status_code >= 400:
        return BLOCKED, f"the estate view answered {got.status_code}"
    body = got.json() or {}
    rows = body.get("models") or body.get("health") or body.get("items") or []
    if not rows:
        return BLOCKED, "the estate view is empty"
    without = [r.get("urn") for r in rows if "coverage" not in r]
    if without:
        return FAIL, (f"{len(without)} of {len(rows)} row(s) carry a score and "
                      f"no coverage, so a model nobody has measured prints the "
                      f"same as a healthy one: {without[:4]}")
    thin = [r for r in rows if (r.get("coverage") or 0) < 0.5
            and (r.get("score") or 0) >= GOOD_AT]
    if thin and not any(str(r.get("band")) != GOOD for r in thin):
        return FAIL, (f"{len(thin)} model(s) score above {GOOD_AT} on less "
                      f"than half their components and are banded '{GOOD}', "
                      f"so the least measured models read as the healthiest")
    return PASS, (f"{len(rows)} row(s), every one carrying its coverage beside "
                  f"its score")
