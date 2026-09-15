"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — what a grant may spend.

Three limits, and they protect different things: a **rate** protects the
serving infrastructure, a **quota** protects the budget, and a **cost** budget
protects it against a model whose price per call is not a constant. All three
are checked BEFORE the descriptor is signed, because a signed descriptor is an
authorisation and handing one out then declining to honour it means the caller
holds a warrant the platform does not intend to let it use.

**A refusal does not consume what it was refused.** A caller in a retry loop
whose retries ate the allowance the retries were waiting for could never
recover, and the grant would be dead until the window rolled despite never
having been used successfully. Refusals are counted for reporting and excluded
from the spend, and the detail line says so.

And a limit of zero is refused at the point it is set: a limit that refuses
every call is a revocation written as a number, and a revocation records a
reason and shows on every screen as what it is.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)
from qa.regression_suite.scenarios.g_execution import governed

W = "/api/v1/warrants"
L = "/api/v1/grant-limits"


def _quotas(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("grant_quotas")


def _invocations(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("invocations")


def _granted(ctx: Ctx, principal: str = "svc-pricing") -> tuple:
    """A governed model and one grant's id."""
    made = governed(ctx)
    urn = made["urn"]
    issued = ctx.api.post(W, json={"urn": urn, "principal": principal,
                                   "environment": "prod",
                                   "declared_use": "credit_decision"})
    if issued.status_code >= 400:
        return urn, ""
    body = issued.json() or {}
    return urn, (body.get("warrant_id") or body.get("id") or "")


def _invoke(ctx: Ctx, warrant_id: str, model_id: str, n: int = 1,
            at: Optional[float] = None, outcome: str = "served",
            cost: float = 0.0):
    """Record invocations directly: the limits read the invocation log, and
    driving a runtime N times would test the runtime instead.

    A fresh id per row rather than one built from the timestamp — two batches
    written inside the same second collided on the primary key, and a case that
    dies on its own fixture reports nothing about its subject."""
    db = ctx.ui.app.state.ctx["db"]
    moment = at if at is not None else time.time()
    for _ in range(n):
        db.execute(
            "INSERT INTO warrant_invocation (id, warrant_id, model_id, "
            "principal, declared_use, environment, verb, outcome, at, cost) "
            "VALUES (:i, :w, :m, 'svc-pricing', 'credit_decision', 'prod', "
            "'score', :o, :t, :c)",
            {"i": f"inv-{uuid.uuid4().hex}",
             "w": warrant_id, "m": model_id, "o": outcome,
             "t": moment, "c": cost})


@case("QA-FX-394", "A limit of zero")
def fx_394(ctx: Ctx) -> Result:
    """Refused at set time. A limit that refuses every call is a revocation
    wearing a number, and a revocation records a reason and shows on every
    screen as what it is."""
    _urn, warrant_id = _granted(ctx)
    if not warrant_id:
        return BLOCKED, "the grant could not be issued"
    outcomes = {}
    for name in ("rate", "quota", "cost"):
        got = ctx.api.put(f"{L}/{warrant_id}", json={name: 0})
        outcomes[name] = (got.status_code, code_of(got))
    wrong = {k: v for k, v in outcomes.items() if v[1] != "limit_not_positive"}
    if wrong:
        return FAIL, f"these were not refused 'limit_not_positive': {wrong}"
    said = ctx.api.put(f"{L}/{warrant_id}", json={"rate": 0}).text
    if "revocation" not in said:
        return FAIL, f"the refusal does not say what a zero limit is: {said[:150]}"
    if "revoke the grant instead" not in said:
        return FAIL, "the refusal does not offer the act that is meant"
    negative = ctx.api.put(f"{L}/{warrant_id}", json={"quota": -5})
    if code_of(negative) != "limit_not_positive":
        return FAIL, f"a negative limit answered '{code_of(negative)}'"
    return PASS, ("rate, quota, cost and a negative all refused "
                  "'limit_not_positive', naming revocation as the act meant")


@case("QA-FX-395", "A window of zero hours")
def fx_395(ctx: Ctx) -> Result:
    """A quota per no-time is not a quota. The window is how long the quota
    lasts before it refills, so zero makes the ceiling meaningless in both
    directions at once."""
    _urn, warrant_id = _granted(ctx)
    if not warrant_id:
        return BLOCKED, "the grant could not be issued"
    got = ctx.api.put(f"{L}/{warrant_id}",
                      json={"quota": 10, "window_hours": 0})
    if got.status_code < 400:
        return FAIL, "a quota window of zero hours was accepted"
    if code_of(got) != "window_not_positive":
        return FAIL, f"refused '{code_of(got)}'"
    if "how long the quota lasts" not in got.text:
        return FAIL, f"the refusal does not say what a window is: {got.text[:150]}"
    state = ctx.api.get(f"{L}/{warrant_id}")
    if (state.json() or {}).get("window_hours") in (0, 0.0):
        return FAIL, "refused, and the window was written anyway"
    return PASS, "refused 'window_not_positive', and nothing was written"


@case("QA-FX-396", "Setting no limit at all")
def fx_396(ctx: Ctx) -> Result:
    """Recording a decision nobody took is worse than recording none. An
    empty body would otherwise append a `warrant_limits_set` act to the
    chain saying somebody decided something."""
    _urn, warrant_id = _granted(ctx)
    if not warrant_id:
        return BLOCKED, "the grant could not be issued"
    evidence = ctx.ui.app.state.ctx.get("evidence")
    before = len([n for n in evidence.repo.many()
                  if n["kind"] == "warrant_limits_set"]) if evidence else 0
    got = ctx.api.put(f"{L}/{warrant_id}", json={})
    if got.status_code < 400:
        return FAIL, "an empty limit body was accepted"
    if code_of(got) != "nothing_to_set":
        return FAIL, f"refused '{code_of(got)}'"
    after = len([n for n in evidence.repo.many()
                 if n["kind"] == "warrant_limits_set"]) if evidence else 0
    if after != before:
        return FAIL, (f"refused, and {after - before} act(s) were appended to "
                      f"the chain anyway")
    return PASS, "refused 'nothing_to_set', nothing appended to the chain"


@case("QA-FX-392", "Exactly the quota, then one more", isolated=True)
def fx_392(ctx: Ctx) -> Result:
    """The boundary. `spent >= ceiling` is exhausted, so the tenth call of a
    quota of ten is the last one served and the eleventh is refused."""
    from core.execution.errors import WarrantError
    urn, warrant_id = _granted(ctx)
    quotas = _quotas(ctx)
    if not warrant_id or quotas is None:
        return BLOCKED, "no grant or quota register"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    if ctx.api.put(f"{L}/{warrant_id}",
                   json={"quota": 10}).status_code >= 400:
        return BLOCKED, "the quota could not be set"
    _invoke(ctx, warrant_id, model["id"], n=9)
    quotas.check(warrant_id)                       # nine spent: still headroom
    _invoke(ctx, warrant_id, model["id"], n=1, at=time.time() + 1)
    try:
        quotas.check(warrant_id)
    except WarrantError as exc:
        if exc.code != "quota_limit_reached":
            return FAIL, f"refused '{exc.code}' rather than quota_limit_reached"
        if "10" not in str(exc):
            return FAIL, f"the refusal does not name the ceiling: {str(exc)[:130]}"
        if "does not itself count" not in str(getattr(exc, "remediation", "")):
            return FAIL, ("the refusal does not say a refusal is not charged, "
                          "which is what stops a retry loop being permanent")
        return PASS, f"nine served, ten exhausts: {str(exc)[:110]}"
    return FAIL, "ten calls against a quota of ten left headroom"


@case("QA-FX-391", "A refused call does not consume quota", isolated=True)
def fx_391(ctx: Ctx) -> Result:
    """The property the whole design rests on. A caller in a retry loop
    whose retries consumed the allowance they were waiting for could never
    recover, and the grant would be dead until the window rolled despite
    never having been used successfully."""
    urn, warrant_id = _granted(ctx)
    quotas = _quotas(ctx)
    if not warrant_id or quotas is None:
        return BLOCKED, "no grant or quota register"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    if ctx.api.put(f"{L}/{warrant_id}",
                   json={"quota": 10}).status_code >= 400:
        return BLOCKED, "the quota could not be set"
    _invoke(ctx, warrant_id, model["id"], n=100, outcome="refused")
    state = quotas.of(warrant_id)
    if state["exhausted"]:
        return FAIL, (f"a hundred REFUSED calls exhausted {state['exhausted']} "
                      f"— a retry loop can keep its own grant dead")
    if state["calls_in_window"]:
        return FAIL, (f"{state['calls_in_window']} refused call(s) counted as "
                      f"spend")
    if state["refused_in_window"] != 100:
        return FAIL, (f"{state['refused_in_window']} of 100 refusals were "
                      f"recorded; a refusal nobody counts is one nobody "
                      f"investigates")
    if "refused" not in (state.get("detail") or ""):
        return FAIL, (f"the detail does not mention the refusals: "
                      f"{state['detail'][:140]}")
    _invoke(ctx, warrant_id, model["id"], n=1, at=time.time() + 1)
    after = quotas.of(warrant_id)
    if after["calls_in_window"] != 1:
        return FAIL, f"a served call after refusals counted {after}"
    return PASS, ("100 refusals counted and charged nothing; the first served "
                  "call is the first unit of spend")


@case("QA-FX-389", "Exactly the rate limit, then one more", isolated=True)
def fx_389(ctx: Ctx) -> Result:
    """The rate is what is spent in the last minute, so it refills by time
    passing rather than by a window rolling — which is the difference
    between a rate and a quota and the reason both exist."""
    from core.execution.errors import WarrantError
    urn, warrant_id = _granted(ctx)
    quotas = _quotas(ctx)
    if not warrant_id or quotas is None:
        return BLOCKED, "no grant or quota register"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    if ctx.api.put(f"{L}/{warrant_id}",
                   json={"rate": 60}).status_code >= 400:
        return BLOCKED, "the rate could not be set"
    now = time.time()
    _invoke(ctx, warrant_id, model["id"], n=59, at=now)
    quotas.check(warrant_id, now=now)
    _invoke(ctx, warrant_id, model["id"], n=1, at=now + 0.5)
    try:
        quotas.check(warrant_id, now=now + 1)
    except WarrantError as exc:
        if exc.code != "rate_limit_reached":
            return FAIL, f"refused '{exc.code}' rather than rate_limit_reached"
        # A minute later the same grant is serving again.
        later = quotas.of(warrant_id, now=now + 61)
        if "rate" in later["exhausted"]:
            return FAIL, ("the rate did not refill a minute later, so it is a "
                          "quota with a different name")
        return PASS, (f"59 served, the 60th exhausts, and the rate refills a "
                      f"minute later: {str(exc)[:100]}")
    return FAIL, "sixty calls in a minute against a rate of 60 left headroom"


@case("QA-FX-390", "The burst across a fixed bucket boundary", isolated=True)
def fx_390(ctx: Ctx) -> Result:
    """A fixed bucket lets 60 at 11:59:59 and 60 at 12:00:01 through — 120
    calls in two seconds against a limit of 60 a minute. A sliding window
    sees them."""
    urn, warrant_id = _granted(ctx)
    quotas = _quotas(ctx)
    if not warrant_id or quotas is None:
        return BLOCKED, "no grant or quota register"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    if ctx.api.put(f"{L}/{warrant_id}",
                   json={"rate": 60}).status_code >= 400:
        return BLOCKED, "the rate could not be set"
    # A minute boundary, to the second.
    boundary = float(int(time.time() / 60.0) * 60 + 60)
    _invoke(ctx, warrant_id, model["id"], n=60, at=boundary - 1)
    _invoke(ctx, warrant_id, model["id"], n=60, at=boundary + 1)
    state = quotas.of(warrant_id, now=boundary + 2)
    line = next(x for x in state["limits"] if x["limit"] == "rate")
    if "rate" not in state["exhausted"]:
        return FAIL, (f"120 calls two seconds apart across a minute boundary "
                      f"count {line['spent']:.0f} against a ceiling of "
                      f"{line['ceiling']:.0f} — the window is a fixed bucket, "
                      f"so a caller doubles its rate by straddling the minute")
    if line["spent"] < 61:
        return FAIL, (f"the window counts {line['spent']:.0f} of the 120, so "
                      f"it is not sliding over the full minute")
    return PASS, (f"the last minute counts {line['spent']:.0f} across the "
                  f"boundary and the rate is exhausted: a sliding window")


@case("QA-FX-393", "The cost budget on a token-metered model", isolated=True)
def fx_393(ctx: Ctx) -> Result:
    """Cost exists because a call is not a unit of spend on a model priced
    per token. The budget has to bind long before the call count is
    anywhere near the quota, or it is decoration."""
    from core.execution.errors import WarrantError
    urn, warrant_id = _granted(ctx)
    quotas = _quotas(ctx)
    if not warrant_id or quotas is None:
        return BLOCKED, "no grant or quota register"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    if ctx.api.put(f"{L}/{warrant_id}",
                   json={"quota": 1000, "cost": 5.0}).status_code >= 400:
        return BLOCKED, "the limits could not be set"
    _invoke(ctx, warrant_id, model["id"], n=5, cost=1.0)
    state = quotas.of(warrant_id)
    try:
        quotas.check(warrant_id)
    except WarrantError as exc:
        if exc.code != "cost_limit_reached":
            return FAIL, f"refused '{exc.code}' rather than cost_limit_reached"
        if state["calls_in_window"] >= 1000:
            return FAIL, "the quota was reached too, so this proves nothing"
        return PASS, (f"5 call(s) against a quota of 1000 and a budget of 5.0 "
                      f"— refused 'cost_limit_reached' with the call count "
                      f"nowhere near: {str(exc)[:100]}")
    return FAIL, (f"a spend of 5.0 against a budget of 5.0 left headroom: "
                  f"{state['exhausted']}")


@case("QA-FX-397", "Limits are per grant, not per principal", isolated=True)
def fx_397(ctx: Ctx) -> Result:
    """One principal holding four grants has four allowances. A limit that
    was per principal would mean exhausting a batch job's grant stopped the
    same service's interactive one, which is not what anybody set."""
    from core.execution.errors import WarrantError
    quotas = _quotas(ctx)
    if quotas is None:
        return BLOCKED, "no quota register is wired"
    made = governed(ctx)
    urn = made["urn"]
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    ids = []
    for use in ("credit_decision", "monitoring", "reporting", "analysis"):
        issued = ctx.api.post(W, json={"urn": urn, "principal": "svc-one",
                                       "environment": "prod",
                                       "declared_use": use})
        if issued.status_code >= 400:
            continue
        body = issued.json() or {}
        ids.append(body.get("warrant_id") or body.get("id"))
    ids = [i for i in ids if i]
    if len(ids) < 2:
        return BLOCKED, f"only {len(ids)} grant(s) could be issued"
    for warrant_id in ids:
        ctx.api.put(f"{L}/{warrant_id}", json={"quota": 5})
    _invoke(ctx, warrant_id=ids[0], model_id=model["id"], n=5)
    exhausted, serving = [], []
    for warrant_id in ids:
        try:
            quotas.check(warrant_id)
            serving.append(warrant_id)
        except WarrantError:
            exhausted.append(warrant_id)
    if exhausted != [ids[0]]:
        return FAIL, (f"exhausting one of {len(ids)} grants held by one "
                      f"principal exhausted {len(exhausted)} of them")
    if len(serving) != len(ids) - 1:
        return FAIL, f"{len(serving)} of {len(ids) - 1} grants still serve"
    return PASS, (f"one of {len(ids)} grants on one principal is exhausted and "
                  f"the other {len(serving)} still resolve")


@case("QA-FX-398", "A grant with no limits", isolated=True)
def fx_398(ctx: Ctx) -> Result:
    """Unlimited, and counted as such. An unlimited grant is a decision
    nobody took rather than one they did, so it has to be visible on the
    estate page rather than rendering as a blank."""
    _urn, warrant_id = _granted(ctx)
    quotas = _quotas(ctx)
    if not warrant_id or quotas is None:
        return BLOCKED, "no grant or quota register"
    state = quotas.of(warrant_id)
    if sorted(state["unlimited"]) != ["cost", "quota", "rate"]:
        return FAIL, (f"a grant with no limits reports unlimited "
                      f"{state['unlimited']}")
    if state["exhausted"]:
        return FAIL, "a grant with no limits reports something exhausted"
    if "nobody has taken" not in (state.get("detail") or ""):
        return FAIL, (f"the detail does not say an unlimited grant is an "
                      f"untaken decision: {state['detail'][:140]}")
    estate = ctx.api.get(L)
    if estate.status_code >= 400:
        return BLOCKED, f"the estate view was refused: {estate.text[:130]}"
    body = estate.json() or {}
    mine = [g for g in (body.get("grants") or body.get("limits") or [])
            if g.get("warrant_id") == warrant_id]
    if not mine:
        return FAIL, (f"a grant with no limits does not appear on the estate "
                      f"view at all: {sorted(body)}")
    if not mine[0].get("unlimited"):
        return FAIL, f"the estate row does not say it is unlimited: {mine[0]}"
    return PASS, ("rate, quota and cost all unlimited, named as an untaken "
                  "decision, and carried onto the estate view")
