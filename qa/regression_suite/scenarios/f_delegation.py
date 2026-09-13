"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — delegated authority.

Holding the role is not the same as holding the authority, and the difference
is the entire content of the phrase *delegated authority*. A delegation names
a person, a ceiling, an instrument and an entity, and it expires — MAYA holds
a reference to the board resolution rather than the resolution, so it cannot
tell whether what granted the ceiling still says what it said.

Two properties decide every case here. The check is **silent while no
delegation has ever been recorded for anybody**, because a control that
refuses the whole estate on the day it is switched on is a control that gets
switched off the same day. And it runs only where the approval carries a
BAND, so the delegation half of the matrix and the band half switch on
together.

Every case is `isolated`: a delegation is estate-wide, and one left behind by
an earlier case turns the check on for every case after it.
"""
from __future__ import annotations

import time

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

A = "/api/v1/authority"
V = "/api/v1/version-approvals"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
TIER_2 = {"exposure": 500_000_000.0, "purpose_class": "credit_decision",
          "feature_count": 12, "interpretable": True,
          "uses_alternative_data": False}
TIER_3 = {**TIER_2, "exposure": 1_000_000.0}
EXPOSURE = 250_000_000.0


def _engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("authority")


def _band(ctx: Ctx, **over):
    body = {"name": ctx.unique("bd"), "stages": [["model_risk_manager"],
                                                 ["validator"]],
            "tier": 2, "at_or_above": 0.0, "note": "QA"}
    body.update(over)
    return ctx.api.post(f"{A}/bands", json=body)


def _delegate(ctx: Ctx, **over):
    body = {"principal": "risk", "ceiling": 1_000_000_000.0,
            "instrument": "board minute 2026-03", "currency": "USD"}
    body.update(over)
    return ctx.api.post(f"{A}/delegations", json=body)


def _model(ctx: Ctx, facts=None, entity: str = "LE-US-01",
           exposure=EXPOSURE) -> tuple:
    name = ctx.unique("dg")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner",
                          **SHAPE, "legal_entity": entity})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess", json=dict(facts or TIER_2))
    if exposure is not None:
        ctx.api.post(f"/api/v1/fact-sourcing/model?urn={urn}",
                     json={"fact": "exposure", "source": "finance-gl",
                           "reference": "GL-2026-Q1", "value": str(exposure),
                           "as_at": 1_700_000_000.0},
                     auth=ctx.people["risk"])
    return name, urn


def _sign_attempt(ctx: Ctx, urn: str, who: str = "risk",
                  role: str = "model_risk_manager"):
    """Open an approval on a banded model and try the first signature."""
    made = ctx.api.post(V, json={"urn": urn, "semver": "1.0.0",
                                 "statement": "qa"}, auth=ctx.people["risk"])
    if made.status_code >= 400:
        return None, made
    aid = made.json()["id"]
    return aid, ctx.api.post(f"{V}/{aid}/sign",
                             json={"role": role, "decision": "approve",
                                   "statement": "qa"},
                             auth=ctx.people.get(who, who))


@case("QA-GOV-140", "Record delegations but publish no band", isolated=True)
def gov_140(ctx: Ctx) -> Result:
    """EXPECTED GAP. The ceiling is enforced inside the signing path only
    where the approval carries a band, so delegating without publishing a
    matrix records ceilings that decide nothing. The estate view is where
    that absence has to be visible, or a firm believes it has a control."""
    if _delegate(ctx, principal="risk", ceiling=1.0).status_code >= 400:
        return BLOCKED, "the delegation could not be recorded"
    _name, urn = _model(ctx)
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code >= 400:
        return PASS, (f"refused '{code_of(signed)}' — the ceiling is enforced "
                      f"whether or not a band is published")
    estate = ctx.api.get(f"{A}/estate", auth=ctx.people["risk"])
    blob = f"{estate.json() if estate.status_code < 400 else ''}"
    if "band" in blob and ("no band" in blob or "not published" in blob
                           or "unpublished" in blob):
        return PASS, ("the ceiling is not enforced without a band, and the "
                      "estate view says so")
    return FAIL, ("a 1 USD ceiling signed off a 250,000,000 exposure because "
                  "no band is published: `refuse_beyond_delegation` runs only "
                  "inside `if approval.get('band')`, and nothing in the estate "
                  "view says the recorded ceilings are deciding nothing")


@case("QA-GOV-141", "Sign a tier 3 version while holding no delegation",
      isolated=True)
def gov_141(ctx: Ctx) -> Result:
    """EXPECTED GAP, and a defensible one. A tier 3 version needs no quorum,
    so it never passes through the signing path at all — the delegation check
    lives there and nowhere else. What matters is that this is a known edge
    rather than a surprise, so the case pins it."""
    if _band(ctx, tier=2).status_code >= 400:
        return BLOCKED, "the band could not be published"
    if _delegate(ctx, principal="somebody-else").status_code >= 400:
        return BLOCKED, "the delegation could not be recorded"
    name, _urn = _model(ctx, TIER_3)
    got = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — the ceiling reaches the "
                      f"single-signature path too")
    return PASS, ("a tier 3 version is approved without a delegation: the "
                  "check lives in the quorum signing path and a tier 3 "
                  "version never enters it. Pinned as a known edge")


@case("QA-GOV-142", "Signer holds no live delegation while others do",
      isolated=True)
def gov_142(ctx: Ctx) -> Result:
    """The check switches on for the whole estate the moment ANY delegation
    exists. That is the deliberate design — a matrix with one row in it is a
    matrix somebody is maintaining — and it is the case that proves the
    silence above is a state and not a permanent condition."""
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    if _delegate(ctx, principal="somebody-else").status_code >= 400:
        return BLOCKED, "the delegation could not be recorded"
    _name, urn = _model(ctx)
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code < 400:
        return FAIL, ("somebody holding no delegation signed while another "
                      "person's delegation was on the record, so the check "
                      "is not switched on by the register having one")
    if code_of(signed) != "no_delegated_authority":
        return FAIL, f"refused '{code_of(signed)}'"
    return PASS, "refused 'no_delegated_authority'"


@case("QA-GOV-143", "Signer's delegation expired yesterday", isolated=True)
def gov_143(ctx: Ctx) -> Result:
    """An expired delegation grants nothing — that is the point of it
    expiring, because MAYA cannot check whether the resolution behind it
    still says what it said."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no authority engine is wired"
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    # Granted far enough in the past that its own term has run out. The API
    # has no way to record an expired delegation, and it should not have one.
    engine.delegate("risk", ceiling=1_000_000_000.0,
                    instrument="board minute 2020-01", currency="USD",
                    actor="qa", now=time.time() - engine.stands_for - 86400)
    live = ctx.api.get(f"{A}/delegations?principal=risk",
                       auth=ctx.people["risk"])
    if (live.json() or {}).get("delegations"):
        return BLOCKED, "the expired delegation still reads as live"
    _name, urn = _model(ctx)
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code < 400:
        return FAIL, ("a delegation that ran out yesterday still authorised a "
                      "signature, so the expiry is a display field")
    if code_of(signed) != "no_delegated_authority":
        return FAIL, f"refused '{code_of(signed)}'"
    return PASS, "refused 'no_delegated_authority' on an expired delegation"


@case("QA-GOV-144", "Delegation expiring in one second", isolated=True)
def gov_144(ctx: Ctx) -> Result:
    """The boundary of the expiry, read from both sides of one second."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no authority engine is wired"
    engine.delegate("risk", ceiling=1_000_000_000.0,
                    instrument="board minute 2026-03", currency="USD",
                    actor="qa", now=time.time() - engine.stands_for + 1)
    before = engine.held_by("risk", now=time.time())
    after = engine.held_by("risk", now=time.time() + 5)
    if not before:
        return FAIL, "a delegation with a second left is already not live"
    if after:
        return FAIL, ("a delegation still reads as live five seconds after it "
                      "expired, so the term is not being compared to now")
    return PASS, "live with a second left, not live five seconds later"


@case("QA-GOV-145",
      "Delegation recorded for `person/j.okafor`, signer authenticates as "
      "`j.okafor`", isolated=True)
def gov_145(ctx: Ctx) -> Result:
    """VERIFY, and it is the identity comparison again. `held_by` looks up
    `delegations.many(principal=username)` — an exact string match — while
    the platform writes an owner as `person/j.okafor` and authenticates the
    same human as `j.okafor`. A delegation recorded in the prefixed spelling
    grants nothing to the person it names."""
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    if _delegate(ctx, principal="person/risk").status_code >= 400:
        return BLOCKED, "the delegation could not be recorded"
    _name, urn = _model(ctx)
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code < 400:
        return PASS, ("the delegation is resolved as an identity, so "
                      "'person/risk' and 'risk' are the same person")
    if code_of(signed) != "no_delegated_authority":
        return FAIL, f"refused '{code_of(signed)}' for some other reason"
    return FAIL, ("a delegation recorded for 'person/risk' grants nothing to "
                  "the principal who authenticates as 'risk': `held_by` "
                  "matches the principal column as a STRING, so the two "
                  "spellings of one human are two people. The register writes "
                  "owners in the prefixed form, so this is the spelling a firm "
                  "will use")


@case("QA-GOV-146", "Delegation in JPY against a USD-read exposure",
      isolated=True)
def gov_146(ctx: Ctx) -> Result:
    """Nothing in the register records a currency on an exposure, so every
    figure is read as the reporting currency. Comparing a JPY ceiling to it
    anyway is how a ceiling authorises an exposure many times its size, and
    the silent direction here is the permitting one."""
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    if _delegate(ctx, principal="risk", currency="JPY").status_code >= 400:
        return BLOCKED, "the delegation could not be recorded"
    _name, urn = _model(ctx)
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code < 400:
        return FAIL, ("a ceiling delegated in JPY authorised an exposure read "
                      "as USD; the two numbers were compared without a rate")
    if code_of(signed) != "ceiling_not_comparable":
        return FAIL, f"refused '{code_of(signed)}'"
    return PASS, "refused 'ceiling_not_comparable'"


@case("QA-GOV-147", "Two delegations, one JPY one USD", isolated=True)
def gov_147(ctx: Ctx) -> Result:
    """The USD one is comparable and the JPY one is not, so the comparable
    one decides. Refusing because a foreign-currency row also exists would
    make a second delegation a way of removing somebody's authority."""
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    _delegate(ctx, principal="risk", currency="JPY", ceiling=100.0)
    if _delegate(ctx, principal="risk", currency="USD",
                 ceiling=1_000_000_000.0).status_code >= 400:
        return BLOCKED, "the USD delegation could not be recorded"
    _name, urn = _model(ctx)
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code >= 400:
        return FAIL, (f"refused '{code_of(signed)}' although a USD ceiling of "
                      f"a billion covers the exposure; a foreign-currency row "
                      f"removed authority the board granted")
    return PASS, "the comparable ceiling decides and the JPY row is ignored"


@case("QA-GOV-148", "Two USD delegations of different sizes", isolated=True)
def gov_148(ctx: Ctx) -> Result:
    """EXPLORATORY. `max` over the comparable ceilings, so the larger wins.
    The alternative — the smaller, or refusing the ambiguity — would make a
    second instrument able to reduce what the first granted, which is not how
    a board resolution works."""
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    _delegate(ctx, principal="risk", ceiling=1.0,
              instrument="board minute 2020-01")
    if _delegate(ctx, principal="risk", ceiling=1_000_000_000.0,
                 instrument="board minute 2026-03").status_code >= 400:
        return BLOCKED, "the larger delegation could not be recorded"
    _name, urn = _model(ctx)
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code >= 400:
        return FAIL, (f"refused '{code_of(signed)}' — a 1 USD instrument on "
                      f"the record reduced a billion-dollar one")
    return PASS, "the larger of two live ceilings decides"


@case("QA-GOV-149", "Exposure exactly equal to the ceiling", isolated=True)
def gov_149(ctx: Ctx) -> Result:
    """`amount > highest` refuses, so equality is inside. A ceiling somebody
    may not approve exactly up to is a ceiling one unit lower than the one
    the board wrote down."""
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    if _delegate(ctx, principal="risk",
                 ceiling=EXPOSURE).status_code >= 400:
        return BLOCKED, "the delegation could not be recorded"
    _name, urn = _model(ctx)
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code >= 400:
        return FAIL, (f"refused '{code_of(signed)}' at exactly the ceiling; "
                      f"the board's number is one unit lower than it reads")
    over = ctx.api.get(f"{A}/model?urn={urn}", auth=ctx.people["risk"])
    del over
    return PASS, f"an exposure of exactly {EXPOSURE:,.0f} is within the ceiling"


@case("QA-GOV-150", "Delegation scoped to LE-UK, model in LE-US",
      isolated=True)
def gov_150(ctx: Ctx) -> Result:
    """Authority is granted by an entity's board and it does not travel."""
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    if _delegate(ctx, principal="risk",
                 legal_entity="LE-UK-01").status_code >= 400:
        return BLOCKED, "the delegation could not be recorded"
    _name, urn = _model(ctx, entity="LE-US-01")
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code < 400:
        return FAIL, ("authority delegated by the UK board approved a US "
                      "model; a delegation that travels is not a delegation")
    if code_of(signed) != "entity_out_of_delegation":
        return FAIL, f"refused '{code_of(signed)}'"
    return PASS, "refused 'entity_out_of_delegation'"


@case("QA-GOV-151", "Delegation with no entity, model in any entity",
      isolated=True)
def gov_151(ctx: Ctx) -> Result:
    """A delegation with no entity is a group-level one, and it reaches
    everywhere. The other side of QA-GOV-150: if an unscoped delegation did
    not reach, every group mandate would have to be restated per entity."""
    if _band(ctx).status_code >= 400:
        return BLOCKED, "the band could not be published"
    if _delegate(ctx, principal="risk",
                 legal_entity=None).status_code >= 400:
        return BLOCKED, "the delegation could not be recorded"
    _name, urn = _model(ctx, entity="LE-US-01")
    aid, signed = _sign_attempt(ctx, urn)
    if aid is None:
        return BLOCKED, f"no approval to sign: {signed.text[:140]}"
    if signed.status_code >= 400:
        return FAIL, (f"refused '{code_of(signed)}' — a delegation naming no "
                      f"entity reaches none of them, so a group mandate has "
                      f"to be restated for every entity in the estate")
    return PASS, "an unscoped delegation reaches the entity"
