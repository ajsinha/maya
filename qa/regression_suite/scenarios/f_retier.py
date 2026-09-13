"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the re-tiering triggers.

An assessment is a reading of facts at a moment, and the facts move. These are
the seven questions the register can ask about whether a tier still matches
what it was made from, and the module's own principle is the thing worth
testing: **a trigger the register cannot currently answer is reported as
`cannot_check` rather than skipped**, because a control that quietly cannot
run looks exactly like one that ran and found nothing.

Three of the seven take a collaborator that an instance may not have wired.
Whether those report `cannot_check` or simply return nothing is the whole
question, and it is where this batch spends most of its cases.
"""
from __future__ import annotations

import time

from core.risk.triggers import MATERIAL_MOVE
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

T = "/api/v1/retier-triggers"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ASSESSED = 1_000_000.0
FACTS = {"exposure": ASSESSED, "purpose_class": "credit_decision",
         "feature_count": 3, "interpretable": True,
         "uses_alternative_data": False}


def _assessed(ctx: Ctx, **over) -> tuple:
    """A model with a version and an assessment. The version matters: without
    one the trainability class is undeclared and the assessment is refused
    `fact_not_supplied`, so every trigger case would block on the fixture."""
    name = ctx.unique("rt")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    got = ctx.api.post(f"{M}/{name}/assess", json={**FACTS, **over})
    return (name, urn) if got.status_code < 400 else ("", "")


def _source(ctx: Ctx, urn: str, value) -> None:
    ctx.api.post(f"/api/v1/fact-sourcing/model?urn={urn}",
                 json={"fact": "exposure", "source": "finance-gl",
                       "reference": "GL-2026-Q1", "value": str(value),
                       "as_at": time.time()},
                 auth=ctx.people["risk"])


def _of(ctx: Ctx, urn: str) -> dict:
    got = ctx.api.get(f"{T}/model?urn={urn}", auth=ctx.people["risk"])
    return got.json() if got.status_code < 400 else {}


def _fired(reading: dict) -> list:
    return [r["trigger"] for r in (reading.get("fired") or [])]


def _states(reading: dict) -> dict:
    rows = (reading.get("fired") or []) + (reading.get("cannot_check") or [])
    return {r["trigger"]: r.get("state", "fired") for r in rows}


@case("QA-GOV-194", "Exposure moved exactly 25%")
def gov_194(ctx: Ctx) -> Result:
    """`move < material_move` returns nothing, so the threshold is inclusive
    and exactly 25% fires. A boundary nobody tested is one that moves when
    the comparison is rewritten."""
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    _source(ctx, urn, ASSESSED * (1 + MATERIAL_MOVE))
    got = _of(ctx, urn)
    if "exposure_change" not in _fired(got):
        return FAIL, (f"a move of exactly {MATERIAL_MOVE:.0%} did not fire: "
                      f"{_states(got)}")
    return PASS, f"fired at exactly {MATERIAL_MOVE:.0%}"


@case("QA-GOV-195", "Exposure moved 24.9%")
def gov_195(ctx: Ctx) -> Result:
    """The other side of the same boundary."""
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    _source(ctx, urn, ASSESSED * 1.249)
    got = _of(ctx, urn)
    if "exposure_change" in _fired(got):
        return FAIL, "a move of 24.9% fired against a threshold of 25%"
    return PASS, "24.9% does not fire"


@case("QA-GOV-196", "Exposure moved downward by 40%")
def gov_196(ctx: Ctx) -> Result:
    """The move is absolute. An exposure that collapsed is as much a reason
    to re-read the tier as one that grew — and reading only upwards is how a
    tier stays high on a book nobody writes any more."""
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    _source(ctx, urn, ASSESSED * 0.6)
    got = _of(ctx, urn)
    if "exposure_change" not in _fired(got):
        return FAIL, (f"a 40% fall did not fire, so the trigger reads only "
                      f"upwards: {_states(got)}")
    return PASS, "a 40% fall fires"


@case("QA-GOV-197",
      "Assessment exposure of 0, current exposure of 5,000,000")
def gov_197(ctx: Ctx) -> Result:
    """A move from zero is not a percentage. Firing on it would fire on every
    model whose assessment recorded no exposure, and the honest answer is
    that there is nothing to compare."""
    _name, urn = _assessed(ctx, exposure=0.0)
    if not urn:
        return BLOCKED, "the model could not be assessed at zero exposure"
    _source(ctx, urn, 5_000_000.0)
    got = _of(ctx, urn)
    if "exposure_change" in _fired(got):
        return FAIL, ("a move from an assessed exposure of zero fired, which "
                      "is a division by zero dressed as a percentage")
    return PASS, "a move from zero does not fire"


@case("QA-GOV-199", "Elapsed-time trigger exactly at `next_review_due`")
def gov_199(ctx: Ctx) -> Result:
    """`now <= due` returns nothing, so the review date itself is not yet
    overdue. The only trigger that was watched before this module existed."""
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    engine = ctx.ui.app.state.ctx.get("retier_triggers")
    if engine is None:
        return BLOCKED, "no retier engine is wired"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    latest = engine._latest(model["id"])
    due = latest.get("next_review_due")
    if not due:
        return BLOCKED, "the assessment carries no next_review_due"
    at = engine.of(urn, now=due)
    if "elapsed_time" in [r["trigger"] for r in (at.get("fired") or [])]:
        return FAIL, "the review date itself reads as overdue"
    after = engine.of(urn, now=due + 86400)
    if "elapsed_time" not in [r["trigger"] for r in (after.get("fired") or [])]:
        return FAIL, "a day past the review date still does not fire"
    return PASS, "not at the date, fired a day after it"


@case("QA-GOV-202", "Sweep an estate with no assessments at all")
def gov_202(ctx: Ctx) -> Result:
    """A fresh estate must sweep to nothing rather than to an error — this is
    the scheduled job, and a job that raises on an empty register is one
    somebody switches off."""
    got = ctx.api.post(f"{T}/sweep", json={}, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, f"the sweep answered {got.status_code}: {got.text[:140]}"
    body = got.json() or {}
    for field in ("rows", "raised", "roots"):
        if field not in body:
            return FAIL, f"the sweep reports no '{field}'"
    if body.get("roots"):
        return FAIL, f"an estate with nothing stale has roots: {body['roots']}"
    return PASS, (f"swept {len(body.get('rows') or [])} stale assessment(s), "
                  f"no roots")


@case("QA-GOV-200", "Run the sweep twice")
def gov_200(ctx: Ctx) -> Result:
    """EXPECTED TO FAIL on duplication — and it does not get that far. The
    sweep detects the stale assessment and raises NOTHING, on either run."""
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    _source(ctx, urn, ASSESSED * 2)
    if "exposure_change" not in _fired(_of(ctx, urn)):
        return BLOCKED, "the trigger did not fire, so there is nothing to sweep"
    first = ctx.api.post(f"{T}/sweep", json={}, auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, f"the sweep answered {first.status_code}"
    one = (first.json() or {}).get("raised") or []
    rows = [r for r in ((first.json() or {}).get("rows") or [])
            if r.get("urn") == urn]
    if not rows:
        return BLOCKED, "the stale model is not in the sweep's rows"
    if not one:
        return FAIL, ("the sweep found the stale assessment and raised no "
                      "finding. `_raise` calls `raise_finding(model_id=..., "
                      "title=..., severity=..., source=..., detail=..., "
                      "actor=...)` and the register's signature is "
                      "`(model_id, severity, title, owner, description=...)` "
                      "— `owner` is missing and `detail` is not a parameter, "
                      "so every call raises TypeError into the bare `except "
                      "Exception` that exists to stop ONE bad finding losing "
                      "the rest of the sweep. Nothing is ever raised, and "
                      "`_correlate` needs a raised finding, so there are no "
                      "roots either")
    second = ctx.api.post(f"{T}/sweep", json={}, auth=ctx.people["risk"])
    two = (second.json() or {}).get("raised") or []
    if two:
        return FAIL, (f"the second sweep raised {len(two)} more finding(s) "
                      f"for the same stale assessment, so a job on a schedule "
                      f"adds one every night")
    return PASS, f"{len(one)} raised on the first sweep, none on the second"


@case("QA-GOV-203", "Sweep where one trigger fired on fifty models")
def gov_203(ctx: Ctx) -> Result:
    """The M-8 shape: fifty findings with fifty owners, each seeing a problem
    they cannot fix. A shared cause has to be raised under one named root, so
    the board pack can say they are one problem."""
    urns = []
    for _ in range(4):
        _name, urn = _assessed(ctx)
        if not urn:
            return BLOCKED, "a model could not be assessed"
        _source(ctx, urn, ASSESSED * 2)
        urns.append(urn)
    got = ctx.api.post(f"{T}/sweep", json={}, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the sweep answered {got.status_code}"
    body = got.json() or {}
    mine = [r for r in (body.get("rows") or []) if r.get("urn") in urns]
    if len(mine) != len(urns):
        return BLOCKED, (f"only {len(mine)} of {len(urns)} stale models are "
                         f"in the sweep")
    if not body.get("raised"):
        return FAIL, (f"{len(mine)} models share a cause and the sweep raised "
                      f"nothing, so there is nothing to correlate — see "
                      f"QA-GOV-200 for why")
    if not body.get("roots"):
        return FAIL, (f"{len(mine)} findings from one shared cause were raised "
                      f"under no named root, which is the M-8 shape this "
                      f"correlation exists to prevent")
    return PASS, (f"{len(body['raised'])} findings under "
                  f"{len(body['roots'])} root(s)")


@case("QA-GOV-191", "Exposure trigger with no fact-sourcing wired")
def gov_191(ctx: Ctx) -> Result:
    """The finding that was worth more than the trigger. Outside the
    assessment the only exposure MAYA has is the one the assessment was made
    from, so without `H-8` the question is unanswerable — and unanswerable
    has to be said out loud."""
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    got = _of(ctx, urn)
    states = _states(got)
    if states.get("exposure_change") == "cannot_check":
        return PASS, "reported 'cannot_check' with no sourced exposure"
    if "exposure_change" in _fired(got):
        return FAIL, ("the trigger fired with nothing to compare against")
    return FAIL, (f"with no sourced exposure the trigger is neither fired nor "
                  f"reported as unanswerable: {got.get('cannot_check')!r}. A "
                  f"control that quietly cannot run looks exactly like one "
                  f"that ran and found nothing")


@case("QA-GOV-192", "New-use trigger with no use register wired")
def gov_192(ctx: Ctx) -> Result:
    """EXPECTED TO FAIL. `_new_use` returns None when the register is absent,
    which is the same answer as *no use was added* — and the module's own
    `_cannot_check` docstring says that is the failure this codebase is
    arranged against."""
    engine = ctx.ui.app.state.ctx.get("retier_triggers")
    if engine is None:
        return BLOCKED, "no retier engine is wired"
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    latest = engine._latest(model["id"])
    was, engine.uses = engine.uses, None
    try:
        answer = engine._new_use(model, latest)
    finally:
        engine.uses = was
    if answer is None:
        return FAIL, ("with no use register wired the trigger answers None, "
                      "which the reading renders as *did not fire* — "
                      "indistinguishable from a model nobody added a use to. "
                      "`_cannot_check` exists for exactly this and is not used")
    if answer.get("state") == "cannot_check":
        return PASS, "reported 'cannot_check' with no use register"
    return FAIL, f"answered {answer.get('state')!r}"


@case("QA-GOV-193", "Monitoring-breach trigger with no breach register wired")
def gov_193(ctx: Ctx) -> Result:
    """The same shape as QA-GOV-192, and worth its own case because this is
    the collaborator most likely to be absent: a register with monitoring
    switched off has no breaches, and *no breaches* is what a stale tier
    looks like."""
    engine = ctx.ui.app.state.ctx.get("retier_triggers")
    if engine is None:
        return BLOCKED, "no retier engine is wired"
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    latest = engine._latest(model["id"])
    was, engine.breaches = engine.breaches, None
    try:
        answer = engine._breach(model, latest)
    finally:
        engine.breaches = was
    if answer is None:
        return FAIL, ("with no breach register wired the trigger answers "
                      "None, which reads as *no breach since the assessment* "
                      "— the one answer a monitoring-off estate must not be "
                      "given")
    if answer.get("state") == "cannot_check":
        return PASS, "reported 'cannot_check' with no breach register"
    return FAIL, f"answered {answer.get('state')!r}"


@case("QA-GOV-190",
      "Regulatory-change trigger against a regime activated *before* the "
      "assessment")
def gov_190(ctx: Ctx) -> Result:
    """The recorded defect: the comparison read
    `_as_float(_activated_at(...)) or since < 0`, which Python parses as
    `_as_float(...) or (since < 0)` — so any regime with a non-null
    activation matched and the assessment date was never compared. Because
    this is the trigger that correlates across the estate, it inflated every
    sweep and every board-pack staleness figure."""
    engine = ctx.ui.app.state.ctx.get("retier_triggers")
    if engine is None:
        return BLOCKED, "no retier engine is wired"
    if engine.regimes is None:
        return BLOCKED, "no regime register is wired"
    _name, urn = _assessed(ctx)
    if not urn:
        return BLOCKED, "the model could not be assessed"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    latest = engine._latest(model["id"])
    active = engine.regimes.active()
    if not active:
        return BLOCKED, "no regime is active, so there is nothing to compare"
    answer = engine._regulatory(latest)
    if answer is None:
        return PASS, (f"{len(active)} regime(s) active, all activated before "
                      f"this assessment, and the trigger does not fire")
    return FAIL, (f"a regime activated before the assessment fired the "
                  f"regulatory-change trigger: {answer.get('evidence')}")


@case("QA-GOV-198", "A Medium-severity breach after the assessment")
def gov_198(ctx: Ctx) -> Result:
    """Low and Medium breaches are common on a busy estate and a tier is not
    the instrument for them. The threshold is High."""
    from core.risk.triggers import BREACH_SEVERITIES
    if "Medium" in BREACH_SEVERITIES:
        return FAIL, (f"Medium is in the firing severities {BREACH_SEVERITIES}, "
                      f"so an ordinary week's breaches restate every tier")
    if "High" not in BREACH_SEVERITIES or "Critical" not in BREACH_SEVERITIES:
        return FAIL, f"the firing severities are {BREACH_SEVERITIES}"
    return PASS, f"fires on {', '.join(BREACH_SEVERITIES)} and nothing below"
