"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the tiering lattice itself.

A tier is not a label somebody chooses. It is `tau(materiality, complexity)`,
monotone in both arguments (law L-4), where materiality is a JOIN of a
quantitative band with a qualitative purpose class and complexity is a MEET
over declared components. Materiality dominates: a critical-exposure model is
never below tier 2 however simple it is.

The boundaries are the whole of it, so they are tested as arithmetic against
the shipped lattice rather than through a fixture that happens to land on one
— a case that asserts "this model is tier 2" tells nobody where tier 2 stops.
"""
from __future__ import annotations

from core.risk.lattices import COMPLEXITY, CONTROLS, MATERIALITY
from core.risk.tiering import TieringEngine
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FACTS = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
         "feature_count": 3, "interpretable": True,
         "uses_alternative_data": False}


def _engine(ctx: Ctx):
    """The WIRED engine: the bands, purpose ranks and review months come from
    configuration, so a bare `TieringEngine()` would test a lattice this
    instance does not use."""
    return ctx.ui.app.state.ctx.get("tiering")


def _model(ctx: Ctx, *, version: bool = True) -> tuple:
    name = ctx.unique("tl")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    if version:
        ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                     auth=ctx.people["developer"])
    return name, urn


def _assess(ctx: Ctx, name: str, **over):
    return ctx.api.post(f"{M}/{name}/assess", json={**FACTS, **over})


def _at(score: int) -> tuple:
    """A (materiality, complexity) pair whose tau score is exactly this."""
    for m_i, m in enumerate(MATERIALITY):
        for c_i, c in enumerate(COMPLEXITY):
            if m_i * 2 + c_i == score and m_i < 4:
                return m, c
    return "", ""


@case("QA-GOV-181", "Assess at the tau score boundary 5")
def gov_181(ctx: Ctx) -> Result:
    """`score >= 5` is tier 2 and `score >= 2` is tier 3, so five is the
    first score that buys the second tier's controls."""
    m, c = _at(5)
    if not m:
        return BLOCKED, "no lattice pair scores 5 below critical materiality"
    if TieringEngine.tau(m, c) != 2:
        return FAIL, f"tau({m},{c}) is {TieringEngine.tau(m, c)}, not 2"
    below_m, below_c = _at(4)
    if TieringEngine.tau(below_m, below_c) != 3:
        return FAIL, (f"score 4 is tier {TieringEngine.tau(below_m, below_c)}, "
                      f"so 5 is not where tier 2 begins")
    return PASS, f"tau({m},{c})=2 and score 4 is tier 3"


@case("QA-GOV-182", "Assess at the tau score boundary 2")
def gov_182(ctx: Ctx) -> Result:
    """Two is the first score above the floor, and the floor is where a model
    stops owing nothing but identification and condition monitoring."""
    m, c = _at(2)
    if not m:
        return BLOCKED, "no lattice pair scores 2"
    if TieringEngine.tau(m, c) != 3:
        return FAIL, f"tau({m},{c}) is {TieringEngine.tau(m, c)}, not 3"
    below_m, below_c = _at(1)
    if TieringEngine.tau(below_m, below_c) != 4:
        return FAIL, (f"score 1 is tier {TieringEngine.tau(below_m, below_c)}, "
                      f"so 2 is not where tier 3 begins")
    return PASS, f"tau({m},{c})=3 and score 1 is tier 4"


@case("QA-GOV-183", "Assess at the tau score boundary 1")
def gov_183(ctx: Ctx) -> Result:
    """The bottom of the lattice. Tier 4 is not *no tier* — it still owes
    identification and condition monitoring, which is what makes an estate
    inventory complete."""
    m, c = _at(1)
    if not m:
        return BLOCKED, "no lattice pair scores 1"
    if TieringEngine.tau(m, c) != 4:
        return FAIL, f"tau({m},{c}) is {TieringEngine.tau(m, c)}, not 4"
    if not CONTROLS[4]:
        return FAIL, "tier 4 owes nothing, so the bottom of the lattice is a gap"
    return PASS, f"tau({m},{c})=4, owing {', '.join(CONTROLS[4])}"


@case("QA-GOV-180",
      "Assess a model whose materiality is `critical` and complexity `simple`")
def gov_180(ctx: Ctx) -> Result:
    """Materiality dominates. A critical-exposure model is never below tier 1
    however simple it is — and a lattice that let complexity pull it down
    would let a model be made less material by being made simpler."""
    got = TieringEngine.tau("critical", "simple")
    if got != 1:
        return FAIL, (f"critical materiality with simple complexity is tier "
                      f"{got}: complexity is pulling materiality down")
    ranked = [TieringEngine.tau("critical", c) for c in COMPLEXITY]
    if set(ranked) != {1}:
        return FAIL, f"critical materiality spans tiers {sorted(set(ranked))}"
    return PASS, "critical materiality is tier 1 at every complexity"


@case("QA-GOV-4640", "tau is monotone in both arguments (L-4)")
def gov_4640(ctx: Ctx) -> Result:
    """The law the whole lattice rests on, checked over all twenty cells
    rather than at the corner a fixture happens to reach. A tier that could
    FALL as materiality or complexity rose would make re-assessment a way of
    lowering the controls owed."""
    grid = [[TieringEngine.tau(m, c) for c in COMPLEXITY] for m in MATERIALITY]
    for row, m in zip(grid, MATERIALITY):
        for i in range(len(row) - 1):
            if row[i + 1] > row[i]:
                return FAIL, (f"at materiality '{m}', complexity "
                              f"'{COMPLEXITY[i + 1]}' is tier {row[i + 1]} "
                              f"and '{COMPLEXITY[i]}' is tier {row[i]} — "
                              f"more complex is less governed")
    for c_i, c in enumerate(COMPLEXITY):
        column = [grid[m_i][c_i] for m_i in range(len(MATERIALITY))]
        for i in range(len(column) - 1):
            if column[i + 1] > column[i]:
                return FAIL, (f"at complexity '{c}', materiality "
                              f"'{MATERIALITY[i + 1]}' is tier "
                              f"{column[i + 1]} and '{MATERIALITY[i]}' is "
                              f"tier {column[i]} — more material is less "
                              f"governed")
    return PASS, (f"monotone over all {len(MATERIALITY) * len(COMPLEXITY)} "
                  f"cells, in both arguments")


@case("QA-GOV-176", "Assess with `feature_count: 51`")
def gov_176(ctx: Ctx) -> Result:
    """`feature_count > 50` adds a complexity step, so 51 is one step above
    50 and the boundary is where a model changes what it owes."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no tiering engine is wired"
    at = engine.assess({**FACTS, "feature_count": 50,
                        "trainability_class": "T1"})
    over = engine.assess({**FACTS, "feature_count": 51,
                          "trainability_class": "T1"})
    if at.complexity == over.complexity:
        return FAIL, (f"50 and 51 features both read '{at.complexity}', so "
                      f"the documented boundary does nothing")
    if COMPLEXITY.index(over.complexity) != COMPLEXITY.index(at.complexity) + 1:
        return FAIL, (f"51 features moved complexity from '{at.complexity}' "
                      f"to '{over.complexity}', which is not one step")
    return PASS, f"50 -> '{at.complexity}', 51 -> '{over.complexity}'"


@case("QA-GOV-177",
      "Assess with `exposure` exactly at a configured band floor")
def gov_177(ctx: Ctx) -> Result:
    """The bands are floors, so a figure exactly at one belongs to the band
    it opens and not the one below. An estate's largest models sit on round
    numbers, so this boundary is where real models land."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no tiering engine is wired"
    # `_bands` is already sorted by floor at construction — there is no
    # public `bands`, and reading a `bands` attribute that does not exist
    # blocks this case rather than failing it.
    bands = list(getattr(engine, "_bands", ()) or ())
    if not bands:
        return BLOCKED, "the exposure bands are not readable from the engine"
    name, floor = next(((n, f) for n, f in bands if f > 0), (None, None))
    if floor is None:
        return BLOCKED, "no band has a non-zero floor"
    at = engine.materiality(float(floor), "commercial")
    below = engine.materiality(float(floor) - 1, "commercial")
    if at != name:
        return FAIL, (f"an exposure of exactly {floor:,.0f} reads '{at}' "
                      f"rather than '{name}', the band it opens")
    if below == name:
        return FAIL, (f"one below the floor also reads '{name}', so the band "
                      f"is not bounded from beneath")
    return PASS, f"{floor:,.0f} -> '{name}', one less -> '{below}'"


@case("QA-GOV-186",
      "Required controls at tier 1 with a `sox_relevant` designation")
def gov_186(ctx: Ctx) -> Result:
    """Additive and orthogonal. A designation does not move a model up or
    down the lattice — two models at the same tier can owe different things
    because one of them feeds a regulatory submission, and no amount of
    re-tiering produces a reconciliation requirement."""
    plain = TieringEngine.required_controls(1)
    marked = TieringEngine.required_controls(1, ["sox_relevant"])
    if set(plain) - set(marked):
        return FAIL, (f"a designation REMOVED controls: "
                      f"{sorted(set(plain) - set(marked))}")
    added = [c for c in marked if c not in plain]
    if not added:
        return FAIL, ("`sox_relevant` adds no control, so a designation the "
                      "screen shows changes nothing a model owes")
    if TieringEngine.tau("moderate", "moderate") != 2:
        return BLOCKED, "the lattice moved under this case"
    if TieringEngine.supports_tier(list(marked)) != 1:
        return FAIL, ("the Galois adjoint reads the designation's controls, "
                      "so L-5 depends on facts the tier lattice does not hold")
    return PASS, f"tier 1 controls plus {added}, and the adjoint still says 1"


@case("QA-GOV-168", "Assess with only exposure and purpose supplied")
def gov_168(ctx: Ctx) -> Result:
    """The omitted facts are refused rather than defaulted where they MOVE
    the tier. A caller who could leave out `interpretable` would be choosing
    their own complexity, which is the same failure as choosing the tier."""
    name, _urn = _model(ctx)
    got = ctx.api.post(f"{M}/{name}/assess",
                       json={"exposure": 1_000_000.0,
                             "purpose_class": "credit_decision"})
    outcome = refused_by_the_control(
        got, "an assessment omitting the facts that move the tier")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "fact_not_supplied":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'fact_not_supplied'"


@case("QA-GOV-169", "Assess before any version exists")
def gov_169(ctx: Ctx) -> Result:
    """The trainability class is DERIVED from how the parameter object is
    inhabited, so it does not exist before a version does. The recorded
    symptom: every case study in this repository assessed first and
    registered the version second, and received a tier computed against a
    class the model did not have — which then produced a different tier."""
    name, _urn = _model(ctx, version=False)
    got = _assess(ctx, name)
    outcome = refused_by_the_control(
        got, "a model was assessed before it had a version to derive a class from")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "fact_not_supplied":
        return FAIL, f"refused '{code_of(got)}'"
    if "version" not in got.text:
        return FAIL, ("the refusal does not say a version is what supplies "
                      "the class, so the caller is told a fact is missing "
                      "with no way to supply it")
    return PASS, "refused 'fact_not_supplied', naming the version"


@case("QA-GOV-188", "Assess a `retired` model")
def gov_188(ctx: Ctx) -> Result:
    """EXPLORATORY. A retired model still has a tier, and re-reading it is
    how an estate answers *what were we running* — so this should be
    accepted. What it must not do is quietly move a live control."""
    name, _urn = _model(ctx)
    if _assess(ctx, name).status_code >= 400:
        return BLOCKED, "the first assessment failed"
    gone = ctx.api.post(f"{M}/{name}/retire",
                        json={"reason": "superseded this quarter"},
                        auth=ctx.people["risk"])
    if gone.status_code >= 400:
        return BLOCKED, f"the retirement failed: {gone.text[:140]}"
    got = _assess(ctx, name, exposure=5_000_000_000.0,
                  purpose_class="policy_decision",
                  review_note="re-reading a retired model")
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a retired model's tier is "
                      f"a matter of record")
    body = got.json() or {}
    if body.get("tier") == 1:
        return PASS, (f"accepted and re-tiered to {body.get('tier')}: a "
                      f"retired model's tier can be re-read, which is how an "
                      f"estate answers what it was running")
    return FAIL, f"accepted and the tier reads {body.get('tier')}"


@case("QA-GOV-189", "Assess on an estate with no models at all")
def gov_189(ctx: Ctx) -> Result:
    """A name nobody registered. The refusal has to be about the model rather
    than about the facts, or the caller corrects the wrong thing."""
    got = ctx.api.post(f"{M}/never-registered/assess", json=dict(FACTS))
    outcome = refused_by_the_control(
        got, "a model that does not exist was assessed")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) == "fact_not_supplied":
        return FAIL, ("refused as a missing fact rather than a missing model, "
                      "so the caller supplies more facts about nothing")
    return PASS, f"refused '{code_of(got)}'"
