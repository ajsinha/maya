"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the risk tier, and the lattice it comes out of.

`tau` maps materiality x complexity to a tier and must be monotone in both
(law L-4). `supports_tier` is its adjoint. The cases here walk the boundaries
of both, and push on the one failure the module's own docstring records: an
unrecognised purpose class used to default to the LOWEST rank, so five case
studies tiered as commercially trivial.
"""
from __future__ import annotations

from core.risk.lattices import COMPLEXITY, CONTROLS, MATERIALITY
from core.risk.tiering import TieringEngine
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FACTS = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
         "feature_count": 12, "interpretable": True,
         "uses_alternative_data": False}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("tr")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return name


def _engine(ctx: Ctx):
    """The wired engine. `TieringEngine()` takes the exposure bands, purpose
    ranks and review months from configuration — constructing a bare one
    would be testing a lattice this instance does not use."""
    return ctx.ui.app.state.ctx.get("tiering")


def _assess(ctx: Ctx, name: str, **over):
    body = dict(FACTS)
    body.update(over)
    return ctx.api.post(f"{M}/{name}/assess", json=body)


@case("QA-GOV-174", "Assess with a purpose class outside the vocabulary")
def gov_174(ctx: Ctx) -> Result:
    """The recorded failure: `.get(purpose, 1)` gave an unknown class the rank
    of `commercial`, the lowest there is, and wrote a rationale that read the
    string back as though it had been understood. A field MAYA does not read
    does not merely fail to constrain here — it LOWERS the tier."""
    got = _assess(ctx, _model(ctx), purpose_class="saving the world")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an unrecognised purpose class was assessed, and an "
                      "unread field that lowers a tier is worse than one that "
                      "does nothing")
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if "vocabulary" not in got.text and "declare one of" not in got.text:
        return FAIL, "the refusal does not name the vocabulary"
    return PASS, f"refused '{code_of(got)}', naming the vocabulary"


@case("QA-GOV-171", "Assess twice with identical facts and no note")
def gov_171(ctx: Ctx) -> Result:
    """Re-running the formula on unchanged facts moves the review date
    without anything having been reviewed."""
    name = _model(ctx)
    if _assess(ctx, name).status_code >= 400:
        return BLOCKED, "the first assessment failed"
    return refused_by_the_control(
        _assess(ctx, name),
        "the same facts were assessed twice with nothing said, so the review "
        "date moved without a review")


@case("QA-GOV-173", "Assess twice with a whitespace-only review note")
def gov_173(ctx: Ctx) -> Result:
    """A blank note must not discharge the review, and the guard has a
    `(note or "").strip()` test that says so. The test is unreachable.

    `facts = {**body.model_dump(), ...}` sweeps `review_note` in with
    exposure, purpose and the rest, and `refuse_a_review_that_says_nothing`
    returns early when the facts differ from last time. Supplying ANY note —
    including three spaces — makes the facts differ from a previous
    assessment that carried none, so the guard concludes something moved and
    never reaches the whitespace test.
    """
    name = _model(ctx)
    if _assess(ctx, name).status_code >= 400:
        return BLOCKED, "the first assessment failed"
    got = _assess(ctx, name, review_note="   ")
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    # Establish the mechanism rather than only the symptom: the note is
    # stored as one of the model's risk facts.
    repo = ctx.ui.app.state.ctx.get("risk_repo")
    stored = ""
    if repo is not None:
        model = (ctx.api.get(f"{M}/{name}").json() or {}).get("model") or {}
        rows = repo.many(model_id=model.get("id"))
        if rows and "review_note" in (rows[0].get("facts") or {}):
            stored = (" — and `review_note` is stored inside `facts`, so the "
                      "note is compared as though it were a fact about the "
                      "model")
    return FAIL, (
        "three spaces discharged a periodic review: the same numbers, "
        "re-POSTed, moved the next review date with nothing examined" + stored)


@case("QA-GOV-172", "Assess twice with identical facts and a real note")
def gov_172(ctx: Ctx) -> Result:
    """The refusal has to admit the legitimate case: a periodic review that
    finds nothing changed is a review, and saying so is the work."""
    name = _model(ctx)
    if _assess(ctx, name).status_code >= 400:
        return BLOCKED, "the first assessment failed"
    got = _assess(ctx, name, review_note="reviewed the exposure and the "
                                         "feature set; unchanged")
    if got.status_code >= 400:
        return FAIL, (f"a review that says what it examined was refused "
                      f"'{code_of(got)}', so an unchanged model can never be "
                      f"re-reviewed")
    return PASS, "an unchanged model can be re-reviewed with a note"


@case("QA-GOV-170", "Assess, add a version, assess again")
def gov_170(ctx: Ctx) -> Result:
    """Something moved, and that IS the review — no note required."""
    name = _model(ctx)
    if _assess(ctx, name).status_code >= 400:
        return BLOCKED, "the first assessment failed"
    got = _assess(ctx, name, feature_count=400)
    if got.status_code >= 400:
        return FAIL, (f"changed facts were refused '{code_of(got)}'; the "
                      f"change is the review")
    return PASS, "changed facts need no note"


@case("QA-GOV-175", "Feature count at the complexity boundary")
def gov_175(ctx: Ctx) -> Result:
    """The band is "> 50", so 50 must not bump and 51 must. A boundary read
    the wrong way moves every model with fifty features."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no tiering engine reachable from this run"
    at = engine.complexity("T2", feature_count=50)
    over = engine.complexity("T2", feature_count=51)
    if COMPLEXITY.index(over) <= COMPLEXITY.index(at):
        return FAIL, (f"51 features ({over}) is not more complex than 50 "
                      f"({at}), so the band does not bite")
    if at != engine.complexity("T2", feature_count=0):
        return FAIL, f"50 features already bumped complexity to {at}"
    return PASS, f"50 -> {at}, 51 -> {over}"


@case("QA-GOV-2300", "tau is monotone in both arguments")
def gov_2300(ctx: Ctx) -> Result:
    """Law L-4, checked over the whole lattice rather than at a sample.
    Monotone means a MORE material or MORE complex model is never given a
    weaker tier — and tier 1 is the strongest, so the number must not rise.
    """
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no tiering engine reachable from this run"
    broken = []
    for mi, m in enumerate(MATERIALITY):
        for ci, c in enumerate(COMPLEXITY):
            here = engine.tau(m, c)
            if mi + 1 < len(MATERIALITY):
                up = engine.tau(MATERIALITY[mi + 1], c)
                if up > here:
                    broken.append(f"materiality {m}->{MATERIALITY[mi+1]} at "
                                  f"{c}: tier {here}->{up}")
            if ci + 1 < len(COMPLEXITY):
                up = engine.tau(m, COMPLEXITY[ci + 1])
                if up > here:
                    broken.append(f"complexity {c}->{COMPLEXITY[ci+1]} at "
                                  f"{m}: tier {here}->{up}")
    if broken:
        return FAIL, ("tau is not monotone, so a more serious model gets a "
                      "weaker tier: " + "; ".join(broken[:4]))
    return PASS, (f"monotone over all {len(MATERIALITY)}x{len(COMPLEXITY)} "
                  f"cells")


@case("QA-GOV-2301", "Materiality dominates: a critical model is never below tier 2")
def gov_2301(ctx: Ctx) -> Result:
    """Stated in the source as the reason the lattice is not a plain sum."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no tiering engine reachable from this run"
    worst = MATERIALITY[-1]
    weak = [c for c in COMPLEXITY if engine.tau(worst, c) > 2]
    if weak:
        return FAIL, (f"a {worst}-exposure model tiers below 2 at complexity "
                      f"{weak}, however simple it is")
    return PASS, f"every {worst} model is tier 1 or 2"


@case("QA-GOV-184", "supports_tier over an empty control list")
def gov_184(ctx: Ctx) -> Result:
    """The adjoint's floor. No controls defends the weakest tier, not the
    strongest, or an unprotected model would read as tier 1 compliant."""
    got = TieringEngine.supports_tier([])
    if got != 4:
        return FAIL, (f"no controls at all supports tier {got}; an "
                      f"unprotected model reads as defended")
    return PASS, "no controls supports tier 4"


@case("QA-GOV-185", "supports_tier over tier 1's controls minus one")
def gov_185(ctx: Ctx) -> Result:
    """Every control, not most of them. A subset that answers 1 makes the
    adjoint a rounding rule."""
    full = list(CONTROLS[1])
    if len(full) < 2:
        return BLOCKED, f"tier 1 declares only {len(full)} control(s)"
    weak = []
    for dropped in full:
        held = [c for c in full if c != dropped]
        if TieringEngine.supports_tier(held) == 1:
            weak.append(dropped)
    if weak:
        return FAIL, (f"tier 1 is supported without these controls: {weak}")
    if TieringEngine.supports_tier(full) != 1:
        return FAIL, "the full tier 1 control set does not support tier 1"
    return PASS, f"all {len(full)} tier 1 controls are necessary"


@case("QA-GOV-2302", "The adjoint reads tier controls and only tier controls")
def gov_2302(ctx: Ctx) -> Result:
    """An adjoint that also read designation controls would answer "which
    tier do these defend" with a number depending on facts the tier lattice
    does not contain, and L-5 would stop holding without anything obviously
    breaking."""
    base = list(CONTROLS[4])
    with_noise = base + ["sox_control_testing", "qa-not-a-control"]
    if TieringEngine.supports_tier(with_noise) != TieringEngine.supports_tier(base):
        return FAIL, ("controls outside the tier lattice changed the adjoint's "
                      "answer, so L-5 depends on facts the lattice does not "
                      "contain")
    return PASS, "controls outside the tier lattice do not move the answer"


@case("QA-GOV-178", "Assess with an exposure of zero")
def gov_178(ctx: Ctx) -> Result:
    """Zero exposure is a fact, not a missing one, and materiality then comes
    from the purpose alone."""
    got = _assess(ctx, _model(ctx), exposure=0.0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    tier = (got.json() or {}).get("tier")
    if tier is None:
        return FAIL, "a zero-exposure model was assessed to no tier at all"
    return PASS, f"tier {tier} from the purpose alone"


@case("QA-GOV-179", "Assess with a negative exposure")
def gov_179(ctx: Ctx) -> Result:
    """A negative exposure is not a smaller exposure. Whether it is refused
    or read as zero, it must not tier BELOW a zero-exposure model."""
    zero = _assess(ctx, _model(ctx), exposure=0.0)
    got = _assess(ctx, _model(ctx), exposure=-5_000_000.0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    if zero.status_code >= 400:
        return BLOCKED, "the zero-exposure comparison could not be made"
    here, floor = (got.json() or {}).get("tier"), (zero.json() or {}).get("tier")
    if here is not None and floor is not None and here > floor:
        return FAIL, (f"a negative exposure tiers {here}, weaker than the "
                      f"{floor} a zero exposure gets, so writing a minus sign "
                      f"buys a lower tier")
    return PASS, f"accepted at tier {here}, no weaker than zero's {floor}"


@case("QA-GOV-187", "Assess an attested model")
def gov_187(ctx: Ctx) -> Result:
    """An attested record is immutable, and a tier is a fact ABOUT it rather
    than part of what it says — so re-assessing must be possible, and the
    case reports which reading the platform takes."""
    name = _model(ctx)
    if _assess(ctx, name).status_code >= 400:
        return BLOCKED, "the first assessment failed"
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    for role, who in (("model_owner", "owner"), ("model_risk_manager", "risk")):
        ctx.api.post(f"{M}/{name}/attest",
                     json={"role": role, "decision": "attest",
                           "statement": "qa"}, auth=ctx.people[who])
    got = _assess(ctx, name, feature_count=400)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' on an attested record — a "
                      f"re-tier needs an amendment")
    return PASS, (f"accepted on an attested record: the tier is a fact about "
                  f"the record rather than part of what it says (now tier "
                  f"{(got.json() or {}).get('tier')})")
