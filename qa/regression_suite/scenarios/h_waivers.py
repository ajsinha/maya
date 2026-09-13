"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — waivers: a control relaxed, on purpose, for a bounded time.

The register's position is that an exception with no end date is not an
exception, it is a decision to stop applying a control. Everything here tests
the boundedness: who may grant one, how long it runs, what renewing costs, and
whether the window means what a reader would assume it means.
"""
from __future__ import annotations

from core.waivers.register import QUORUM_BY_TIER, WAIVABLE
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

W = "/api/v1/waivers"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
#: A tier-1 assessment: large exposure, a decision about people, opaque.
TIER_ONE = {"exposure": 5_000_000_000.0, "purpose_class": "credit_decision",
            "feature_count": 400, "interpretable": False,
            "uses_alternative_data": True}
CONTROL = WAIVABLE[0]


def _model(ctx: Ctx, *, tiered: bool = True) -> str:
    name = ctx.unique("wv")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    if tiered:
        ctx.api.post(f"{M}/{name}/assess", json=TIER_ONE)
    return f"maya://model/{name}"


def _tier(ctx: Ctx, urn: str):
    got = ctx.api.get(f"{M}/{urn.rsplit('/', 1)[-1]}")
    return ((got.json() or {}).get("model") or {}).get("tier")


def _propose(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "control": CONTROL, "rationale": "a QA rationale",
            "compensating_control": "daily manual review", "days": 30}
    body.update(over)
    return ctx.api.post(W, json=body, auth=ctx.people["owner"])


def _second(ctx: Ctx, role: str):
    who = ctx.unique("wsign")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": [role], "password": f"{who}-password",
                              "legal_entities": [], "domains": []})
    return (who, f"{who}-password") if made.status_code < 400 else None


@case("QA-AM-184", "Propose a waiver with no compensating control")
def am_184(ctx: Ctx) -> Result:
    """A waiver with nothing compensating records the gap and not the
    containment. If the answer is nothing, it is an accepted risk and belongs
    in a finding somebody owns."""
    return refused_by_the_control(
        _propose(ctx, _model(ctx), compensating_control="   "),
        "a control was relaxed with nothing recorded in its place")


@case("QA-AM-185", "Propose a waiver of a control no tier requires")
def am_185(ctx: Ctx) -> Result:
    """Waiving it would relax nothing while reading on a report as though it
    had — which is worse than not waiving it."""
    got = _propose(ctx, _model(ctx), control="quarterly_vibes")
    if got.status_code < 400:
        return FAIL, "a waiver was granted against a control that is not one"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if not any(c in got.text for c in WAIVABLE[:3]):
        return FAIL, "the refusal does not name what may be waived"
    return PASS, f"refused '{code_of(got)}', naming the {len(WAIVABLE)} controls"


@case("QA-AM-183", "Propose a waiver for zero days")
def am_183(ctx: Ctx) -> Result:
    return refused_by_the_control(
        _propose(ctx, _model(ctx), days=0),
        "a waiver was granted with no window, which is a decision to stop "
        "applying the control")


@case("QA-AM-174", "The proposer approves their own waiver")
def am_174(ctx: Ctx) -> Result:
    """One person who can both ask for a control to be relaxed and relax it
    is not a control."""
    made = _propose(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    wid = made.json()["id"]
    # Over HTTP this cannot happen at all: no role holds both
    # `waiver:propose` and `waiver:approve`, so the proposer is stopped by
    # the permission gate before the register's own check is consulted.
    over_http = ctx.api.post(f"{W}/{wid}/approve",
                             json={"role": "model_risk_manager"},
                             auth=ctx.people["owner"])
    if over_http.status_code < 400:
        return FAIL, "the proposer approved their own waiver over HTTP"
    # Two layers, so the inner one is checked directly rather than assumed.
    # A check that is only ever shadowed by another check is a check nobody
    # has run.
    from core.waivers.common import WaiverError
    waivers = ctx.ui.app.state.ctx.get("waivers")
    if waivers is None:
        return PASS, (f"refused '{code_of(over_http)}' at the permission "
                      f"gate; the register's own check was not reachable")
    try:
        waivers.approve(wid, "model_risk_manager",
                        actor=made.json().get("proposed_by") or "admin")
    except WaiverError as exc:
        if exc.code != "proposer_may_not_approve":
            return FAIL, f"the register refused '{exc.code}' instead"
        return PASS, (f"refused '{code_of(over_http)}' at the gate and "
                      f"'proposer_may_not_approve' in the register")
    return FAIL, ("the register let the proposer grant their own waiver; "
                  "only the permission gate stands between one person and "
                  "both halves of the act")


@case("QA-AM-176", "One person signs a tier 1 waiver twice under two roles")
def am_176(ctx: Ctx) -> Result:
    """A quorum is a count of PEOPLE. One account signing twice satisfies the
    arithmetic and defeats the control."""
    urn = _model(ctx)
    if QUORUM_BY_TIER.get(_tier(ctx, urn) or 4, 1) < 2:
        return BLOCKED, f"this model tiered at {_tier(ctx, urn)}, quorum 1"
    made = _propose(ctx, urn)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    wid = made.json()["id"]
    first = ctx.api.post(f"{W}/{wid}/approve",
                         json={"role": "model_risk_manager"},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    return refused_by_the_control(
        ctx.api.post(f"{W}/{wid}/approve", json={"role": "validator"},
                     auth=ctx.people["risk"]),
        "one person signed both halves of a tier 1 waiver quorum")


@case("QA-AM-177", "Two people sign a tier 1 waiver under the same role")
def am_177(ctx: Ctx) -> Result:
    """A quorum in two roles means two DIFFERENT roles, or it is one opinion
    held twice."""
    urn = _model(ctx)
    if QUORUM_BY_TIER.get(_tier(ctx, urn) or 4, 1) < 2:
        return BLOCKED, f"this model tiered at {_tier(ctx, urn)}, quorum 1"
    made = _propose(ctx, urn)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    wid = made.json()["id"]
    if ctx.api.post(f"{W}/{wid}/approve", json={"role": "model_risk_manager"},
                    auth=ctx.people["risk"]).status_code >= 400:
        return BLOCKED, "the first signature failed"
    other = _second(ctx, "model_risk_manager")
    if other is None:
        return BLOCKED, "could not mint a second risk manager"
    return refused_by_the_control(
        ctx.api.post(f"{W}/{wid}/approve", json={"role": "model_risk_manager"},
                     auth=other),
        "one role signed a tier 1 waiver twice, so a two-role quorum was met "
        "by one opinion held twice")


@case("QA-AM-178", "A tier 1 waiver with one of two signatures")
def am_178(ctx: Ctx) -> Result:
    """A half-signed exception must look like a half-signed exception, not
    like an approved one or an absent one."""
    urn = _model(ctx)
    needed = QUORUM_BY_TIER.get(_tier(ctx, urn) or 4, 1)
    if needed < 2:
        return BLOCKED, f"this model tiered at {_tier(ctx, urn)}, quorum 1"
    made = _propose(ctx, urn)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    signed = ctx.api.post(f"{W}/{made.json()['id']}/approve",
                          json={"role": "model_risk_manager"},
                          auth=ctx.people["risk"])
    if signed.status_code >= 400:
        return BLOCKED, signed.text[:170]
    row = signed.json()
    if row.get("status") == "active":
        return FAIL, (f"a waiver needing {needed} signatures became active on "
                      f"one")
    if len(row.get("approvals") or []) != 1:
        return FAIL, f"the signature was not recorded: {row.get('approvals')}"
    return PASS, f"still '{row['status']}' with 1 of {needed} signatures"


@case("QA-AM-179", "A waiver on an untiered model")
def am_179(ctx: Ctx) -> Result:
    """A model nobody has tiered is not a safe model, so it takes the
    strictest quorum rather than the loosest."""
    urn = _model(ctx, tiered=False)
    if _tier(ctx, urn) is not None:
        return BLOCKED, "the model acquired a tier without being assessed"
    made = _propose(ctx, urn)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    signed = ctx.api.post(f"{W}/{made.json()['id']}/approve",
                          json={"role": "model_risk_manager"},
                          auth=ctx.people["risk"])
    if signed.status_code >= 400:
        return BLOCKED, signed.text[:170]
    if signed.json().get("status") == "active":
        return FAIL, ("an untiered model's waiver became active on one "
                      "signature, so being unassessed bought a looser quorum "
                      f"than any tier (strictest is {max(QUORUM_BY_TIER.values())})")
    return PASS, "one signature is not enough on an untiered model"


@case("QA-AM-182", "Renew a proposed waiver")
def am_182(ctx: Ctx) -> Result:
    made = _propose(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    return refused_by_the_control(
        ctx.api.post(f"{W}/{made.json()['id']}/renew", json={"days": 30},
                     auth=ctx.people["risk"]),
        "a waiver nobody approved was renewed")


@case("QA-AM-188", "Revoke a waiver with no reason")
def am_188(ctx: Ctx) -> Result:
    """What was relaxed, and why it stopped being relaxed, is part of what
    this model's governance actually was."""
    made = _propose(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    return refused_by_the_control(
        ctx.api.post(f"{W}/{made.json()['id']}/revoke", json={"reason": "  "},
                     auth=ctx.people["risk"]),
        "a waiver was revoked with no reason recorded")


@case("QA-AM-173", "Approve a waiver whose window has already passed")
def am_173(ctx: Ctx) -> Result:
    """`expires_at` is fixed when the waiver is PROPOSED, not when it is
    granted. A waiver that sat in the approval queue longer than its own
    window is therefore granted already expired — and the question is whether
    anything notices."""
    urn = _model(ctx, tiered=False)
    made = _propose(ctx, urn, days=1)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    wid = made.json()["id"]
    waivers = (getattr(getattr(ctx.ui, "app", None), "state", None) and
               ctx.ui.app.state.ctx.get("waivers"))
    if waivers is None:
        return BLOCKED, "no waiver register reachable from this run"
    # Wind the window back rather than waiting a day for it.
    waivers.waivers.set({"expires_at": 1.0}, id=wid)
    needed = max(QUORUM_BY_TIER.values())
    for n in range(needed):
        signer = _second(ctx, "model_risk_manager") if n else ctx.people["risk"]
        if signer is None:
            return BLOCKED, "could not mint a signer"
        got = ctx.api.post(f"{W}/{wid}/approve",
                           json={"role": ["model_risk_manager", "validator",
                                          "auditor"][n]}, auth=signer)
        if got.status_code >= 400 and n + 1 < needed:
            return BLOCKED, got.text[:170]
    row = waivers.require(wid)
    if row["status"] != "active":
        return PASS, f"the expired waiver was not activated; it is '{row['status']}'"
    return FAIL, (
        "a waiver whose window had already run became 'active': `expires_at` "
        "is set at PROPOSE time and `approve` does not check it, so a waiver "
        "that waited out its own window in the approval queue is granted "
        "already expired and reads as a live exception")


@case("QA-AM-180", "Renew an active waiver early, with most of it left to run")
def am_180(ctx: Ctx) -> Result:
    """`renew` sets the window to `now + days`, so renewing a waiver that
    still has a long run left SHORTENS it. Renewal reads as an extension."""
    urn = _model(ctx, tiered=False)
    # 90 days is the ceiling for a single waiver, so 80 leaves a long run
    # for a 30-day "renewal" to eat into.
    made = _propose(ctx, urn, days=80)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    wid = made.json()["id"]
    for n in range(max(QUORUM_BY_TIER.values())):
        signer = _second(ctx, "model_risk_manager") if n else ctx.people["risk"]
        if signer is None:
            return BLOCKED, "could not mint a signer"
        ctx.api.post(f"{W}/{wid}/approve",
                     json={"role": ["model_risk_manager", "validator",
                                    "auditor"][n]}, auth=signer)
    waivers = ctx.ui.app.state.ctx.get("waivers")
    before = waivers.require(wid)
    if before["status"] != "active":
        return BLOCKED, f"the waiver did not become active: {before['status']}"
    got = ctx.api.post(f"{W}/{wid}/renew", json={"days": 30},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    after = waivers.require(wid)
    if after["expires_at"] < before["expires_at"]:
        lost = (before["expires_at"] - after["expires_at"]) / 86400.0
        return FAIL, (
            f"renewing shortened the window by {lost:.0f} days: `renew` sets "
            f"`expires_at` to now + days rather than extending from the "
            f"existing expiry, so renewing a waiver early takes time away "
            f"from it under a verb that reads as adding time")
    return PASS, "the window did not shrink"


@case("QA-AM-186", "Run the expiry sweep twice")
def am_186(ctx: Ctx) -> Result:
    """A sweep that expires the same waiver on every run reports a wave of
    expiries that already happened."""
    waivers = ctx.ui.app.state.ctx.get("waivers")
    if waivers is None:
        return BLOCKED, "no waiver register reachable"
    first = waivers.expire_due()
    second = waivers.expire_due()
    n1 = first.get("expired") if isinstance(first, dict) else first
    n2 = second.get("expired") if isinstance(second, dict) else second
    if n2 and n2 == n1 and n1:
        return FAIL, f"the second sweep expired the same {n2} waiver(s) again"
    return PASS, f"first sweep {n1}, second {n2}"


@case("QA-AM-187", "A proposed waiver whose window passed, after the sweep")
def am_187(ctx: Ctx) -> Result:
    """The sweep expires ACTIVE waivers. A proposal that was never approved
    and whose window has run stays `proposed` — and can still be approved,
    which is the same hole QA-AM-173 names, reached from the other side."""
    urn = _model(ctx, tiered=False)
    made = _propose(ctx, urn, days=1)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    wid = made.json()["id"]
    waivers = ctx.ui.app.state.ctx.get("waivers")
    waivers.waivers.set({"expires_at": 1.0}, id=wid)
    waivers.expire_due()
    row = waivers.require(wid)
    if row["status"] == "proposed":
        return FAIL, (
            "a proposal whose window ran out is still 'proposed' after the "
            "expiry sweep, which only looks at active waivers. It stays "
            "proposed for ever and can still be approved into an exception "
            "that expired before anybody granted it")
    return PASS, f"the sweep moved it to '{row['status']}'"


@case("QA-AM-189", "Revoke an already closed waiver")
def am_189(ctx: Ctx) -> Result:
    made = _propose(ctx, _model(ctx, tiered=False))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    wid = made.json()["id"]
    first = ctx.api.post(f"{W}/{wid}/revoke", json={"reason": "qa"},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    return refused_by_the_control(
        ctx.api.post(f"{W}/{wid}/revoke", json={"reason": "again"},
                     auth=ctx.people["risk"]),
        "a waiver already closed was revoked a second time")
