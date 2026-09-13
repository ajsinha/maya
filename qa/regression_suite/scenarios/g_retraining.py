"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the standing retraining policy.

This is the most delegated thing in the register: a judgement made once about
every future re-fit of a model. So the refusals are about what may be
delegated and to whom — and the sharpest is that automatic acceptance needs a
tolerance the PLATFORM checks, because "a policy whose tolerance is evaluated
by whatever produced the parameters is a model marking its own homework".
"""
from __future__ import annotations

from core.parameters.retraining import TRIGGERS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

R = "/api/v1/retraining"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
LOW_TIER = {"exposure": 1_000.0, "purpose_class": "commercial",
            "feature_count": 3, "interpretable": True,
            "uses_alternative_data": False}
HIGH_TIER = {"exposure": 5_000_000_000.0, "purpose_class": "credit_decision",
             "feature_count": 400, "interpretable": False,
             "uses_alternative_data": True}


def _model(ctx: Ctx, assessment=None) -> str:
    name = ctx.unique("rt")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    if assessment:
        ctx.api.post(f"{M}/{name}/assess", json=assessment)
    return urn


def _declare(ctx: Ctx, urn: str, **over):
    body = {"triggers": [sorted(TRIGGERS)[0]], "tolerance": {},
            "auto_accept": False,
            "rationale": "the model is re-fitted monthly on fresh data"}
    body.update(over)
    # Declaring a standing policy takes `parameter:approve` — the SECOND
    # line's permission, not the owner's. A standing delegation over every
    # future re-fit is not something a first-line owner grants themselves.
    return ctx.api.post(f"{R}?urn={urn}", json=body, auth=ctx.people["risk"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-FX-5700", "A policy with no trigger")
def fx_5700(ctx: Ctx) -> Result:
    """A standing policy that nothing fires is a delegation with no
    occasion — it reads as governance and never runs."""
    got = _declare(ctx, _model(ctx, LOW_TIER), triggers=[])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a standing policy was declared that nothing can fire"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-5701", "A trigger that is not one")
def fx_5701(ctx: Ctx) -> Result:
    """The triggers are the occasions a re-fit is expected. An unknown one is
    an occasion that never arrives."""
    got = _declare(ctx, _model(ctx, LOW_TIER), triggers=["a hunch"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a policy fires on a trigger nobody defined"
    if not any(t in got.text for t in TRIGGERS):
        return FAIL, "the refusal does not name the triggers"
    return PASS, f"refused '{code_of(got)}', naming {len(TRIGGERS)} triggers"


@case("QA-FX-5702", "A policy with no rationale")
def fx_5702(ctx: Ctx) -> Result:
    """A delegation over every future re-fit, with no stated reason, is the
    one nobody can withdraw because nobody knows why it exists."""
    got = _declare(ctx, _model(ctx, LOW_TIER), rationale="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a standing policy was declared with no reason"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-5703", "Automatic acceptance with no tolerance")
def fx_5703(ctx: Ctx) -> Result:
    """"A policy whose tolerance is evaluated by whatever produced the
    parameters is a model marking its own homework." The tolerance is checked
    HERE or the delegation is unbounded."""
    got = _declare(ctx, _model(ctx, LOW_TIER), auto_accept=True, tolerance={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("automatic acceptance was granted with no tolerance, so "
                      "whatever produced the parameters decides whether they "
                      "are acceptable")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-5704", "Automatic acceptance on a high tier")
def fx_5704(ctx: Ctx) -> Result:
    """Some models may never accept a parameter set without a person, and
    which ones is a tier question rather than an owner's preference."""
    urn = _model(ctx, HIGH_TIER)
    got = _declare(ctx, urn, auto_accept=True,
                   tolerance={"r_squared": {"min": 0.6}})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        if "tier" not in got.text.lower():
            return FAIL, f"refused '{code_of(got)}' for another reason"
        return PASS, f"refused '{code_of(got)}' on a high tier"
    return PASS, ("this tier may delegate acceptance with a declared "
                  "tolerance")


@case("QA-FX-5705", "Automatic acceptance on an untiered model")
def fx_5705(ctx: Ctx) -> Result:
    """"An untiered model takes the strictest treatment — a model nobody has
    tiered is not a safe model." The same reading the risk lattice applies
    to an unassessed component."""
    got = _declare(ctx, _model(ctx), auto_accept=True,
                   tolerance={"r_squared": {"min": 0.6}})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an untiered model was granted automatic acceptance, so "
                      "not being assessed bought a looser treatment than any "
                      "tier")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-5706", "The author approves their own policy")
def fx_5706(ctx: Ctx) -> Result:
    """"The person who wrote a standing approval may not approve it. It
    delegates a judgement over every future re-fit of this model." """
    urn = _model(ctx, LOW_TIER)
    made = _declare(ctx, urn)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    retraining = ctx.ui.app.state.ctx.get("retraining")
    if retraining is None:
        return BLOCKED, "no retraining register reachable from this run"
    declared_by = (made.json() or {}).get("declared_by") or "risk"
    from core.parameters.common import ParameterError
    try:
        retraining.approve(urn, actor=declared_by)
    except ParameterError as exc:
        if exc.code != "author_may_not_approve":
            return FAIL, f"refused '{exc.code}', not author_may_not_approve"
        return PASS, "the author cannot approve their own standing policy"
    return FAIL, ("the person who wrote a standing approval approved it, so "
                  "one person delegated every future re-fit of this model")


@case("QA-FX-5707", "Somebody else may approve it")
def fx_5707(ctx: Ctx) -> Result:
    """The refusal has to admit the legitimate case, or a standing policy can
    never take effect."""
    urn = _model(ctx, LOW_TIER)
    if _declare(ctx, urn).status_code >= 400:
        return BLOCKED, "the policy could not be declared"
    # A DIFFERENT holder of `parameter:approve`: the validator.
    got = ctx.api.post(f"{R}/approve?urn={urn}", json={},
                       auth=ctx.people["validator"])
    if got.status_code >= 400:
        return FAIL, (f"a second person could not approve the policy: "
                      f"{got.text[:130]}")
    return PASS, "declared by one person, approved by another"


@case("QA-FX-5708", "Every trigger says what it is")
def fx_5708(ctx: Ctx) -> Result:
    """A trigger nobody can define is an occasion nobody can argue about."""
    if hasattr(TRIGGERS, "values"):
        mute = [k for k, v in TRIGGERS.items() if not (v or "").strip()]
        if mute:
            return FAIL, f"triggers with no meaning: {mute}"
    got = ctx.api.get(f"{R}/triggers", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    for trigger in TRIGGERS:
        if trigger not in got.text:
            return FAIL, f"'{trigger}' is accepted and not published"
    return PASS, f"{len(TRIGGERS)} triggers published"


@case("QA-FX-5709", "A policy can be revoked")
def fx_5709(ctx: Ctx) -> Result:
    """A standing delegation nobody can withdraw is a permanent one, and this
    is the delegation most worth being able to stop."""
    urn = _model(ctx, LOW_TIER)
    if _declare(ctx, urn).status_code >= 400:
        return BLOCKED, "the policy could not be declared"
    got = ctx.api.post(f"{R}/revoke?urn={urn}&reason=no+longer+needed",
                       json={}, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"a standing policy could not be revoked: "
                      f"{got.text[:130]}")
    listed = ctx.api.get(f"{R}?urn={urn}", auth=ctx.people["risk"])
    if listed.status_code < 400 and '"state": "active"' in listed.text:
        return FAIL, "the policy is still active after being revoked"
    return PASS, "revoked"
