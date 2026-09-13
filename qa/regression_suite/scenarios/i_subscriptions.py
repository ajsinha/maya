"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — pushing events out of the institution.

A chain node's payload carries model inventory, findings and exposure figures,
so **what leaves the institution is a decision somebody takes rather than a
default**. That is why the kinds are named and `*` is refused: a subscription
receiving everything is one nobody decided the content of, and *we send you
all our events* is not a data-sharing decision anybody made.

**A subscription is suspended, never deleted, after repeated failure.**
Deleting would lose the record that somebody was being told and stopped being
told — and the cursor with it, so a receiver that came back would either miss
everything in between or be resent the whole chain.

And the secret is returned ONCE. It signs every delivery, so a receiver can
tell an event from this platform from anything else that finds the URL.
"""
from __future__ import annotations

from core.events.subscriptions import MAX_FAILURES
from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

S = "/api/v1/subscriptions"


def _engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("subscriptions") or \
        ctx.ui.app.state.ctx.get("event_subscriptions")


def _subscribe(ctx: Ctx, **over):
    body = {"name": ctx.unique("sub"), "url": "https://receiver.example/hook",
            "kinds": ["model_registered"], "owner": "person/integration"}
    body.update(over)
    return ctx.api.post(S, json=body, auth=ADMIN)


@case("QA-PLT-247", "A subscription to `*`")
def plt_247(ctx: Ctx) -> Result:
    """`*` is not a set of kinds. The refusal has to say that naming a long
    list IS the decision being made visible, or somebody reads the refusal
    as bureaucracy and looks for a way round it."""
    got = _subscribe(ctx, kinds=["*"])
    if got.status_code < 400:
        return FAIL, ("a subscription to everything was accepted, so what "
                      "leaves the institution is a default rather than a "
                      "decision")
    if code_of(got) != "wildcard_refused":
        return FAIL, f"refused '{code_of(got)}'"
    if "decision" not in got.text:
        return FAIL, "the refusal does not say what is being decided"
    empty = _subscribe(ctx, kinds=[])
    if empty.status_code < 400:
        return FAIL, "a subscription naming no kinds at all was accepted"
    if code_of(empty) != "kinds_required":
        return FAIL, f"an empty kind list refused '{code_of(empty)}'"
    return PASS, "refused 'wildcard_refused'; an empty list refuses separately"


@case("QA-PLT-248", "A subscription to a plain-HTTP URL")
def plt_248(ctx: Ctx) -> Result:
    """Findings and exposure figures over plain HTTP is the payload leaving
    in clear. `http` is admitted only against the local machine, so a
    developer can run a receiver on their own laptop — and the refusal says
    which exception exists rather than leaving somebody to guess."""
    got = _subscribe(ctx, url="http://receiver.example/hook")
    if got.status_code < 400:
        return FAIL, ("a plain-HTTP subscription was accepted, so the payload "
                      "leaves the institution in clear")
    if code_of(got) != "outbound_not_encrypted":
        return FAIL, f"refused '{code_of(got)}'"
    if "localhost" not in got.text and "local machine" not in got.text:
        return FAIL, ("the refusal does not name the local exception, so a "
                      "developer cannot run a receiver at all")
    for bad, why in (("file:///etc/passwd", "a file URL"),
                     ("ftp://receiver.example/hook", "an ftp URL")):
        refused = _subscribe(ctx, url=bad)
        if refused.status_code < 400:
            return FAIL, (f"{why} was accepted, so the platform reads its own "
                          f"host on behalf of whoever supplied the address")
        if code_of(refused) != "outbound_scheme_refused":
            return FAIL, f"{why} refused '{code_of(refused)}'"
    return PASS, "http refused naming the local exception; file and ftp refused"


@case("QA-PLT-250", "The subscription secret after creation")
def plt_250(ctx: Ctx) -> Result:
    """Returned once and never again. It signs every delivery, so a receiver
    can tell an event from this platform from anything else that finds the
    URL — and a secret readable from a listing is one every reader of the
    estate holds."""
    made = _subscribe(ctx)
    if made.status_code >= 400:
        return BLOCKED, f"the subscription failed: {made.text[:140]}"
    body = made.json() or {}
    secret = body.get("secret")
    if not secret:
        return FAIL, ("the secret is not returned at creation, so a receiver "
                      "can never verify a delivery")
    reference = body.get("reference")
    listed = ctx.api.get(S, auth=ADMIN)
    if listed.status_code >= 400:
        return BLOCKED, f"the listing answered {listed.status_code}"
    if secret in listed.text:
        return FAIL, ("the signing secret is readable from the subscription "
                      "listing, so every reader of the estate holds it")
    one = ctx.api.get(f"{S}?reference={reference}", auth=ADMIN)
    if one.status_code < 400 and secret in one.text:
        return FAIL, "the secret is readable from the single-subscription read"
    return PASS, "returned once at creation and absent from every read after"


@case("QA-PLT-249", "A subscription that fails five times in a row")
def plt_249(ctx: Ctx) -> Result:
    """Suspended, not deleted — and the cursor is kept, so a receiver that
    comes back does not miss everything in between or get resent the whole
    chain. The detail counts down before it happens, because a receiver down
    for a deploy should not be suspended silently."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no subscription register is wired"
    made = _subscribe(ctx)
    if made.status_code >= 400:
        return BLOCKED, f"the subscription failed: {made.text[:140]}"
    reference = (made.json() or {}).get("reference")
    row = engine.require(reference)
    cursor = row.get("cursor")
    outcomes = []
    for _ in range(MAX_FAILURES):
        outcomes.append(engine._failed(engine.require(reference),
                                       RuntimeError("connection refused"),
                                       1_700_000_000.0))
    early = outcomes[0]
    if early["state"] == "suspended":
        return FAIL, "one failure suspended the subscription"
    if str(MAX_FAILURES - 1) not in early["detail"]:
        return FAIL, (f"the first failure does not count down to suspension: "
                      f"{early['detail'][:110]}")
    final = outcomes[-1]
    if final["state"] != "suspended":
        return FAIL, (f"{MAX_FAILURES} consecutive failures left the state "
                      f"'{final['state']}'")
    after = engine.require(reference)
    if after.get("cursor") != cursor:
        return FAIL, (f"suspension moved the cursor from {cursor} to "
                      f"{after.get('cursor')}, so a receiver that comes back "
                      f"misses what happened while it was down")
    if not engine.repo.one(reference=reference):
        return FAIL, "the subscription was deleted rather than suspended"
    if "deleting it would lose the cursor" not in final["detail"]:
        return FAIL, "the detail does not say why it is suspended not deleted"
    return PASS, (f"suspended at {MAX_FAILURES}, cursor kept at {cursor}, "
                  f"and it counted down first")


@case("QA-PLT-4910", "Resuming a suspended subscription")
def plt_4910(ctx: Ctx) -> Result:
    """The way back. Resuming clears the failure count — otherwise the next
    single failure suspends it again — and it starts from the cursor it kept,
    so the receiver gets what it missed rather than the whole chain."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no subscription register is wired"
    made = _subscribe(ctx)
    if made.status_code >= 400:
        return BLOCKED, f"the subscription failed: {made.text[:140]}"
    reference = (made.json() or {}).get("reference")
    cursor = engine.require(reference).get("cursor")
    for _ in range(MAX_FAILURES):
        engine._failed(engine.require(reference), RuntimeError("down"),
                       1_700_000_000.0)
    if engine.require(reference)["state"] != "suspended":
        return BLOCKED, "the subscription did not suspend"
    got = ctx.api.post(f"{S}/{reference}/resume", auth=ADMIN)
    if got.status_code >= 400:
        return FAIL, (f"a suspended subscription cannot be resumed: "
                      f"'{code_of(got)}'")
    row = engine.require(reference)
    if row["state"] != "active":
        return FAIL, f"after resuming the state is '{row['state']}'"
    if row.get("failures"):
        return FAIL, (f"resuming left {row['failures']} failure(s) on the "
                      f"count, so the next single failure suspends it again")
    if row.get("cursor") != cursor:
        return FAIL, (f"resuming moved the cursor from {cursor} to "
                      f"{row.get('cursor')}")
    return PASS, f"active, failures reset, cursor still {cursor}"


@case("QA-PLT-4911", "A new subscription starts at the head")
def plt_4911(ctx: Ctx) -> Result:
    """From the head, not from zero. A new subscriber does not want the
    entire history of the register delivered to it — and one that does can
    rewind deliberately, which is a different act from a default nobody
    chose."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no subscription register is wired"
    head = engine.stream.head()
    made = _subscribe(ctx)
    if made.status_code >= 400:
        return BLOCKED, f"the subscription failed: {made.text[:140]}"
    reference = (made.json() or {}).get("reference")
    cursor = engine.require(reference).get("cursor")
    if cursor in (0, None) and head not in (0, None):
        return FAIL, (f"a new subscription starts at {cursor} with the stream "
                      f"at {head}: the whole history is queued for delivery "
                      f"to a receiver that just connected")
    if cursor != head:
        return FAIL, f"the cursor is {cursor} and the head is {head}"
    return PASS, f"cursor starts at the head, {cursor}"


@case("QA-PLT-4912", "A subscription with no name and one with no owner")
def plt_4912(ctx: Ctx) -> Result:
    """Both are about the moment it starts failing. A subscription with no
    name is a row nobody can identify on a dashboard, and one with no owner
    is an egress nobody is accountable for."""
    for field, code in (("name", "name_required"), ("owner", "owner_required")):
        got = _subscribe(ctx, **{field: "   "})
        if got.status_code < 400:
            return FAIL, f"a subscription with no {field} was accepted"
        if code_of(got) != code:
            return FAIL, f"an empty {field} refused '{code_of(got)}'"
    return PASS, "both refused on whitespace, each by its own code"


@case("QA-PLT-4913",
      "The estate view says an instance with no subscriptions is at rest")
def plt_4913(ctx: Ctx) -> Result:
    """No subscriptions is the ordinary state for an air-gapped register, and
    it must not read as a gap. A view that reported zero egress as a finding
    would train people to ignore it."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no subscription register is wired"

    class Nothing:
        @staticmethod
        def many(**_where):
            return []

    was, engine.repo = engine.repo, Nothing()
    try:
        report = engine.across_the_estate()
    finally:
        engine.repo = was
    detail = report.get("detail") or ""
    if "air-gapped" not in detail and "resting state" not in detail:
        return FAIL, (f"an instance with no subscriptions does not say that "
                      f"is a resting state rather than a gap: {detail[:130]}")
    if report.get("suspended"):
        return FAIL, "an empty register reports suspended subscriptions"
    return PASS, f"no egress reported as the resting state: {detail[:80]}"
