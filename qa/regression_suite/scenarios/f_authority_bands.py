"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — which band an approval falls in.

The dimension worth reading is AMOUNT, and it comes from the sourced exposure
fact and nowhere else: using the figure the tiering assessment was made from
would let the number that decides the approval depth be chosen by whoever
wants the approval. And where no amount is sourced the band is the DEEPEST the
tier admits, not the shallowest — an amount MAYA does not have is not a small
amount, but it compares as less than every floor, so the natural
implementation of this quietly approves everything.

Every case that publishes a band is `isolated`: the matrix is estate-wide, and
a band left behind by one case decides the answer in the next.
"""
from __future__ import annotations

from core.lifecycle.authority import BY_ABSENCE, DEFAULT_BANDS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

A = "/api/v1/authority"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
TIER_2 = {"exposure": 500_000_000.0, "purpose_class": "credit_decision",
          "feature_count": 12, "interpretable": True,
          "uses_alternative_data": False}
TIER_3 = {**TIER_2, "exposure": 1_000_000.0}


def _model(ctx: Ctx, facts=None, entity: str = "LE-US-01") -> tuple:
    name = ctx.unique("ab")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner",
                          **SHAPE, "legal_entity": entity})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess", json=dict(facts or TIER_3))
    return name, urn


def _band(ctx: Ctx, **over):
    body = {"name": ctx.unique("bd"),
            "stages": [["model_owner"], ["model_risk_manager"]],
            "tier": 3, "at_or_above": 0.0, "note": "QA"}
    body.update(over)
    return ctx.api.post(f"{A}/bands", json=body)


def _source(ctx: Ctx, urn: str, value, *, as_at: float = 1_700_000_000.0):
    """Attest an exposure to a named system of record. The band reads THIS
    and never the figure typed into the assessment form."""
    return ctx.api.post(f"/api/v1/fact-sourcing/model?urn={urn}",
                        json={"fact": "exposure", "source": "finance-gl",
                              "reference": "GL-2026-Q1", "value": str(value),
                              "as_at": as_at},
                        auth=ctx.people["risk"])


def _for(ctx: Ctx, urn: str) -> dict:
    got = ctx.api.get(f"{A}/model?urn={urn}", auth=ctx.people["risk"])
    return got.json() if got.status_code < 400 else {}


@case("QA-GOV-120", "Publish a band with tier 0")
def gov_120(ctx: Ctx) -> Result:
    """Tier 0 is not a tier. A band on one matches nothing for ever, and a
    matrix row that can never fire reads on the screen as coverage."""
    got = _band(ctx, tier=0)
    outcome = refused_by_the_control(got, "a band was published on tier 0")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "unknown_tier":
        return FAIL, f"refused '{code_of(got)}' rather than 'unknown_tier'"
    return PASS, "refused 'unknown_tier'"


@case("QA-GOV-123", "Race two publications of the same band name",
      isolated=True)
def gov_123(ctx: Ctx) -> Result:
    """The duplicate check reads and then writes. Two publications that
    interleave leave two rows with one name, and `_specificity` then decides
    between them by a tie-break that was never meant to choose between
    identical twins."""
    import threading
    name = ctx.unique("bd")
    out = {}

    def go(n):
        out[n] = _band(ctx, name=name)

    threads = [threading.Thread(target=go, args=(n,)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if len(out) != 2:
        return BLOCKED, "one of the racing publications did not return"
    won = [n for n, got in out.items() if got.status_code < 400]
    if len(won) == 2:
        return FAIL, ("both publications of the same band name were accepted "
                      "under a race: the duplicate check reads and then "
                      "writes, so the matrix now holds two rows called "
                      f"'{name}'")
    lost = next(got for got in out.values() if got.status_code >= 400)
    if code_of(lost) != "band_exists":
        return FAIL, f"the loser refused '{code_of(lost)}'"
    return PASS, "one published, the other refused 'band_exists'"


@case("QA-GOV-126",
      "Publish the first band at all — every tier 3 model now falls under a "
      "matrix", isolated=True)
def gov_126(ctx: Ctx) -> Result:
    """The matrix ships as `published or DEFAULT_BANDS`, so the first band
    anybody publishes does not ADD a row — it replaces the shipped ones. The
    shipped tier-1 band is the only place the platform requires the second
    line to sign BEFORE the validator, and a firm publishing its first tier-3
    band loses that ordering without being told."""
    shipped = {b["name"] for b in DEFAULT_BANDS}
    live = ctx.api.get(A, auth=ctx.people["risk"])
    if live.status_code >= 400:
        return BLOCKED, f"the matrix could not be read: {live.status_code}"
    names = {b.get("name") for b in (live.json() or {}).get("matrix") or []}
    if not shipped <= names:
        return BLOCKED, (f"the shipped bands are not in the matrix to start "
                         f"with: {sorted(names)}")
    mine = ctx.unique("bd")
    if _band(ctx, name=mine, tier=3).status_code >= 400:
        return BLOCKED, "the band could not be published"
    after = ctx.api.get(A, auth=ctx.people["risk"])
    now = {b.get("name") for b in (after.json() or {}).get("matrix") or []}
    if mine not in now:
        return FAIL, "the published band is not in the matrix"
    lost = sorted(shipped - now)
    if lost:
        return FAIL, (f"publishing one tier 3 band removed the shipped bands "
                      f"{lost} from the matrix: the matrix is "
                      f"`published or DEFAULT_BANDS`, so the first band a firm "
                      f"publishes silently drops the tier-1 sequencing — the "
                      f"only place the platform requires the second line to "
                      f"sign before the validator")
    return PASS, f"the shipped bands survive alongside '{mine}'"


@case("QA-GOV-127", "Publish a matrix that reaches no tier 1 model",
      isolated=True)
def gov_127(ctx: Ctx) -> Result:
    """A tier 1 model under a matrix with no tier 1 row. The answer has to be
    `band: null` and an honest fall back to the tier quorum — not an empty
    stage list that reads as *nobody need sign*."""
    if _band(ctx, tier=3).status_code >= 400:
        return BLOCKED, "the band could not be published"
    _name, urn = _model(ctx, {**TIER_2, "exposure": 5_000_000_000.0,
                              "purpose_class": "policy_decision"})
    got = _for(ctx, urn)
    if got.get("tier") != 1:
        return BLOCKED, f"the fixture is tier {got.get('tier')}, not 1"
    if got.get("band") is not None:
        return FAIL, f"a tier 3 band was applied to a tier 1 model: {got}"
    needed = ctx.api.get(
        f"/api/v1/version-approvals?urn={urn}&semver=1.0.0",
        auth=ctx.people["risk"])
    roles = (needed.json() or {}).get("required_roles") or []
    if roles:
        return PASS, f"band null, and the tier quorum still requires {roles}"
    # Not a response shape — the question is whether one person can now
    # approve a tier 1 version on their own, so ask the register.
    alone = ctx.api.post(f"{M}/{_name}/versions/1.0.0/approve", json={},
                         auth=ctx.people["risk"])
    if alone.status_code >= 400:
        return FAIL, (f"the reading says no quorum is required and the direct "
                      f"approval is still refused '{code_of(alone)}'; the two "
                      f"answers disagree")
    return FAIL, ("a tier 1 version was approved by ONE person. `banded()` "
                  "returns `required_for(urn)` whenever ANY matrix is "
                  "published, and that answer carries `required_roles: []` "
                  "for a model no band reaches — so `roles_for` reports no "
                  "quorum and `refuse_without_quorum` returns silently. "
                  "Publishing one tier 3 band therefore removes the quorum "
                  "from every tier 1 and tier 2 model in the estate, and "
                  "QA-GOV-126 is why there is no shipped row left to catch it")


@case("QA-GOV-129", "Amount one unit below the floor", isolated=True)
def gov_129(ctx: Ctx) -> Result:
    """`at_or_above` is inclusive, so one unit below belongs to the next band
    down. The boundary is where a matrix is argued about."""
    shallow, deep = ctx.unique("bd"), ctx.unique("bd")
    if _band(ctx, name=shallow, tier=3, at_or_above=0.0,
             stages=[["model_risk_manager"]]).status_code >= 400:
        return BLOCKED, "the shallow band could not be published"
    if _band(ctx, name=deep, tier=3, at_or_above=1_000_000.0,
             stages=[["model_risk_manager"], ["validator"]]).status_code >= 400:
        return BLOCKED, "the deep band could not be published"
    _name, urn = _model(ctx, TIER_3)
    if _source(ctx, urn, 999_999).status_code >= 400:
        return BLOCKED, "the exposure could not be sourced"
    got = _for(ctx, urn)
    if got.get("band") == deep:
        return FAIL, ("999,999 fell in the band floored at 1,000,000: "
                      "`at_or_above` is not a floor, it admits less than it")
    if got.get("band") != shallow:
        return FAIL, f"999,999 fell in '{got.get('band')}', neither band"
    return PASS, f"999,999 -> '{shallow}', the band below the floor"


@case("QA-GOV-130", "No sourced exposure at all", isolated=True)
def gov_130(ctx: Ctx) -> Result:
    """The case the module exists for. An unknown amount compares as less
    than every floor, so the natural implementation approves everything —
    and the answer has to say it reached the band BY ABSENCE, because a
    deepened approval that looks like a matched one is a number nobody
    questions."""
    shallow, deep = ctx.unique("bd"), ctx.unique("bd")
    _band(ctx, name=shallow, tier=3, at_or_above=0.0,
          stages=[["model_risk_manager"]])
    _band(ctx, name=deep, tier=3, at_or_above=1_000_000.0,
          stages=[["model_risk_manager"], ["validator"]])
    _name, urn = _model(ctx, TIER_3)
    got = _for(ctx, urn)
    if got.get("amount") is not None:
        return BLOCKED, f"the fixture sourced an amount: {got.get('amount')}"
    if got.get("band") != deep:
        return FAIL, (f"no sourced amount and the band is '{got.get('band')}', "
                      f"not the deepest ('{deep}'): an amount MAYA does not "
                      f"have is being read as a small one")
    if got.get("reached_by") != BY_ABSENCE:
        return FAIL, (f"reached_by reads '{got.get('reached_by')}', so a band "
                      f"chosen because nobody sourced the figure is "
                      f"indistinguishable from one that matched")
    return PASS, f"deepest band '{deep}', reached_by '{BY_ABSENCE}'"


@case("QA-GOV-131", "Sourced exposure recorded as a non-numeric string",
      isolated=True)
def gov_131(ctx: Ctx) -> Result:
    """An exposure that will not parse means the band becomes the deepest —
    which looks from outside exactly like a model nobody sourced, and the two
    want different fixing. So the record has to keep both the attestation and
    the absence."""
    deep = ctx.unique("bd")
    _band(ctx, name=ctx.unique("bd"), tier=3, at_or_above=0.0,
          stages=[["model_risk_manager"]])
    _band(ctx, name=deep, tier=3, at_or_above=1_000_000.0,
          stages=[["model_risk_manager"], ["validator"]])
    _name, urn = _model(ctx, TIER_3)
    put = _source(ctx, urn, "about half a billion")
    if put.status_code >= 400:
        return PASS, (f"refused at sourcing ('{code_of(put)}') — a figure that "
                      f"is not a figure never reaches the matrix")
    got = _for(ctx, urn)
    if got.get("amount") is not None:
        return FAIL, (f"'about half a billion' was read as "
                      f"{got.get('amount')}")
    if got.get("band") != deep:
        return FAIL, (f"an unparseable exposure gave band "
                      f"'{got.get('band')}', not the deepest")
    return PASS, (f"unparseable, so the deepest band '{deep}' — and the "
                  f"attested row is still on the record to be corrected")


@case("QA-GOV-132", "Two exposure facts, the later one dated in the future",
      isolated=True)
def gov_132(ctx: Ctx) -> Result:
    """`amount_for` takes the row with the greatest `as_at`. A figure dated
    next year therefore decides today's approval depth, and nothing refuses
    an `as_at` in the future — so the amount that sets the ceiling can be
    chosen by whoever types the later date."""
    shallow, deep = ctx.unique("bd"), ctx.unique("bd")
    _band(ctx, name=shallow, tier=3, at_or_above=0.0,
          stages=[["model_risk_manager"]])
    _band(ctx, name=deep, tier=3, at_or_above=1_000_000.0,
          stages=[["model_risk_manager"], ["validator"]])
    _name, urn = _model(ctx, TIER_3)
    import time as _t
    if _source(ctx, urn, 5_000_000, as_at=_t.time()).status_code >= 400:
        return BLOCKED, "the present-dated exposure could not be sourced"
    ahead = _source(ctx, urn, 1_000, as_at=_t.time() + 365 * 86400)
    if ahead.status_code >= 400:
        return PASS, (f"refused ('{code_of(ahead)}') — a fact cannot be "
                      f"attested as at a date that has not happened")
    got = _for(ctx, urn)
    if got.get("amount") == 5_000_000.0:
        return PASS, "the future-dated figure does not displace the current one"
    return FAIL, (f"a figure attested as at a date a year away decides today's "
                  f"band: the amount reads {got.get('amount')} and the band is "
                  f"'{got.get('band')}'. `amount_for` takes the greatest "
                  f"`as_at` and nothing refuses one in the future, so the "
                  f"number that sets the approval depth is chosen by whoever "
                  f"types the later date")


@case("QA-GOV-133", "Sourced exposure of exactly 0", isolated=True)
def gov_133(ctx: Ctx) -> Result:
    """Zero is a number somebody attested, and it is not the same fact as an
    amount nobody sourced. A falsy-check here would send every genuinely
    zero-exposure model to the deepest band and report it as absence."""
    shallow, deep = ctx.unique("bd"), ctx.unique("bd")
    _band(ctx, name=shallow, tier=3, at_or_above=0.0,
          stages=[["model_risk_manager"]])
    _band(ctx, name=deep, tier=3, at_or_above=1_000_000.0,
          stages=[["model_risk_manager"], ["validator"]])
    _name, urn = _model(ctx, TIER_3)
    if _source(ctx, urn, 0).status_code >= 400:
        return BLOCKED, "a zero exposure could not be sourced"
    got = _for(ctx, urn)
    if got.get("amount") != 0.0:
        return FAIL, (f"an attested zero reads back as {got.get('amount')!r}, "
                      f"so `0` is being treated as nothing having been said")
    if got.get("reached_by") == BY_ABSENCE:
        return FAIL, ("an attested zero was reported as reached by absence: "
                      "somebody sourcing a zero and nobody sourcing anything "
                      "are different facts")
    if got.get("band") != shallow:
        return FAIL, (f"zero fell in '{got.get('band')}' rather than the band "
                      f"floored at 0")
    return PASS, f"0 -> '{shallow}', matched rather than reached by absence"
