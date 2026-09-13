"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — retrying a request that may already have arrived.

Idempotency exists so a client unsure whether its request landed can safely
send it again. Everything here follows from that one sentence, and the two
recorded defects are both places where the control failed in the direction
that makes the SAFE retry the thing guaranteed to break.

The key is claimed **before** the work, so a retry that races the original is
refused rather than duplicated. Only a SUCCESS is kept: a recorded failure
would make the client's retry replay that failure for ever, and the key would
become a tombstone for an act that never happened. And the digest is taken
over what the request MEANS rather than how it was serialised — byte equality
refused a client whose JSON library ordered keys differently, and told them
the key had been used for a different request, which was not true.

Scoped by CREDENTIAL rather than principal, because the middleware runs before
authentication and cannot know who the caller is.
"""
from __future__ import annotations

from core.concurrency.idempotency import HEADER, MAX_KEY, REPLAYED
from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _spec(ctx: Ctx, **over) -> dict:
    name = ctx.unique("id")
    body = {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **SHAPE}
    body.update(over)
    return body


def _post(ctx: Ctx, body: dict, key: str, who=None):
    """`model:register` is the OWNER's permission, not the risk manager's —
    posting as `risk` answers `forbidden`, and a refusal at the door tells
    nothing about the retry guard behind it."""
    return ctx.api.post(M, json=body, headers={HEADER: key},
                        auth=who or ctx.people["owner"])


@case("QA-PLT-041", "The same idempotency key, same body, twice in sequence")
def plt_041(ctx: Ctx) -> Result:
    """The whole point. The second call replays the first answer and does not
    register a second model — and it says it replayed, so a client can tell a
    replay from a fresh success."""
    body = _spec(ctx)
    key = ctx.unique("key")
    first = _post(ctx, body, key)
    if first.status_code >= 400:
        return BLOCKED, f"the first request failed: {first.text[:140]}"
    second = _post(ctx, body, key)
    if second.status_code != first.status_code:
        return FAIL, (f"the retry answered {second.status_code} where the "
                      f"first answered {first.status_code}")
    if second.text != first.text:
        return FAIL, "the retry answered a different body"
    if second.headers.get(REPLAYED) != "true":
        return FAIL, ("the retry is not marked as a replay, so a client "
                      "cannot tell it from a second act")
    listed = ctx.api.get(f"{M}/{body['name']}", auth=ctx.people["risk"])
    if listed.status_code >= 400:
        return BLOCKED, "the model is not readable"
    return PASS, "the first answer replayed, marked as a replay"


@case("QA-PLT-043",
      "The same key with the same fields in a different order")
def plt_043(ctx: Ctx) -> Result:
    """The recorded defect. A digest over raw bytes made
    `{"a":1,"b":2}` and `{"b":2,"a":1}` different requests, so a client
    retrying through a different JSON library, a proxy that re-serialised, or
    a language whose mapping order differs was refused — and told the key had
    been used for a different POST, which was not true."""
    body = _spec(ctx)
    key = ctx.unique("key")
    first = _post(ctx, body, key)
    if first.status_code >= 400:
        return BLOCKED, f"the first request failed: {first.text[:140]}"
    shuffled = dict(reversed(list(body.items())))
    if list(shuffled) == list(body):
        return BLOCKED, "the body has no order to reverse"
    second = _post(ctx, shuffled, key)
    if second.status_code >= 400:
        return FAIL, (f"the same request with its keys in another order was "
                      f"refused '{code_of(second)}': the safe retry is the "
                      f"one thing guaranteed to fail")
    if second.headers.get(REPLAYED) != "true":
        return FAIL, "the reordered retry ran again rather than replaying"
    return PASS, "reordered keys replay rather than conflict"


@case("QA-PLT-042", "The same key with a **corrected** body")
def plt_042(ctx: Ctx) -> Result:
    """The other direction, and it must still refuse. Replaying the earlier
    answer would tell a caller that a request they have since corrected
    succeeded."""
    body = _spec(ctx)
    key = ctx.unique("key")
    if _post(ctx, body, key).status_code >= 400:
        return BLOCKED, "the first request failed"
    corrected = {**body, "owner": "somebody-else"}
    got = _post(ctx, corrected, key)
    if got.status_code < 400:
        if got.headers.get(REPLAYED) == "true":
            return FAIL, ("a corrected body replayed the earlier answer, so "
                          "the caller is told a request they have since fixed "
                          "succeeded")
        return FAIL, "a corrected body under a used key ran as a new act"
    if code_of(got) != "idempotency_key_reused":
        return FAIL, f"refused '{code_of(got)}'"
    if "new key" not in got.text:
        return FAIL, ("the refusal does not tell the caller to use a new key, "
                      "so they retry the same one for ever")
    return PASS, "refused 'idempotency_key_reused', naming the way forward"


@case("QA-PLT-047", "A key of 256 characters")
def plt_047(ctx: Ctx) -> Result:
    """An idempotency key of 256 characters is not a key, it is a payload.
    The bound is `>`, so exactly the maximum is in."""
    at = _post(ctx, _spec(ctx), "k" * MAX_KEY)
    if at.status_code >= 400 and code_of(at) == "idempotency_key_too_long":
        return FAIL, (f"a key of exactly {MAX_KEY} characters was refused, so "
                      f"the documented bound is one short")
    over = _post(ctx, _spec(ctx), "k" * (MAX_KEY + 1))
    if over.status_code < 400:
        return FAIL, f"a key of {MAX_KEY + 1} characters was accepted"
    if code_of(over) != "idempotency_key_too_long":
        return FAIL, f"refused '{code_of(over)}'"
    if str(MAX_KEY) not in over.text:
        return FAIL, "the refusal does not say what the maximum is"
    return PASS, f"{MAX_KEY} accepted, {MAX_KEY + 1} refused"


@case("QA-PLT-045", "A key whose first attempt was **refused**, retried")
def plt_045(ctx: Ctx) -> Result:
    """Only a success is kept. A recorded failure would make the retry replay
    that failure for ever, and the key would become a tombstone for an act
    that never happened — so the retry has to really run."""
    key = ctx.unique("key")
    bad = _post(ctx, {"urn": "", "name": ""}, key)
    if bad.status_code < 400:
        return BLOCKED, "the malformed request was accepted"
    good = _post(ctx, _spec(ctx), key)
    if good.status_code >= 400:
        if code_of(good) == "idempotency_key_reused":
            return PASS, ("the key is bound to the first request's shape, so "
                          "a corrected retry needs a new key")
        return FAIL, (f"the retry after a refusal was refused "
                      f"'{code_of(good)}': a failed attempt poisoned the key")
    if good.headers.get(REPLAYED) == "true":
        return FAIL, ("the retry replayed the earlier FAILURE, so the key is "
                      "a tombstone for an act that never happened")
    return PASS, "the retry after a refusal really runs"


@case("QA-PLT-048", "Two principals choosing the same key")
def plt_048(ctx: Ctx) -> Result:
    """The scope is the credential, so two callers cannot collide. A shared
    key space would let one caller's retry replay another caller's answer,
    which is the worst outcome this whole mechanism could produce."""
    key = ctx.unique("key")
    mine, theirs = _spec(ctx), _spec(ctx)
    first = _post(ctx, mine, key)
    if first.status_code >= 400:
        return BLOCKED, f"the first request failed: {first.text[:140]}"
    second = _post(ctx, theirs, key, who=ADMIN)
    if second.status_code >= 400:
        return FAIL, (f"a second principal using the same key was refused "
                      f"'{code_of(second)}': the key space is shared, so one "
                      f"caller can block another by guessing a key")
    if second.headers.get(REPLAYED) == "true":
        return FAIL, ("a second principal's request replayed the FIRST "
                      "caller's answer, so a guessed key returns somebody "
                      "else's response")
    for spec in (mine, theirs):
        got = ctx.api.get(f"{M}/{spec['name']}", auth=ctx.people["risk"])
        if got.status_code >= 400:
            return FAIL, f"{spec['name']} was not registered"
    return PASS, "both acts happened, neither replayed the other"


@case("QA-PLT-044", "Two requests with one key arriving at the same moment")
def plt_044(ctx: Ctx) -> Result:
    """The key is claimed BEFORE the work precisely so this can be answered.
    A retry that races the original is the ordinary case, and the loser must
    be told the first is still running rather than being told it failed or
    being allowed to duplicate the act."""
    import threading
    body = _spec(ctx)
    key = ctx.unique("key")
    out = {}

    def go(n):
        out[n] = _post(ctx, body, key)

    threads = [threading.Thread(target=go, args=(n,)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if len(out) != 2:
        return BLOCKED, "one of the racing requests did not return"
    won = [r for r in out.values() if r.status_code < 400
           and r.headers.get(REPLAYED) != "true"]
    if len(won) == 2:
        return FAIL, ("both racing requests ran the act: the key is claimed "
                      "after the work rather than before it")
    lost = [r for r in out.values() if r not in won]
    if not lost:
        return BLOCKED, "no loser to inspect"
    code = code_of(lost[0])
    if lost[0].status_code < 400 and lost[0].headers.get(REPLAYED) == "true":
        return PASS, "the loser replayed the winner's answer"
    if code != "idempotency_in_flight":
        return FAIL, (f"the loser answered '{code or lost[0].status_code}' "
                      f"rather than saying the first is still running")
    return PASS, "refused 'idempotency_in_flight'"


@case("QA-PLT-4770", "A key on a GET")
def plt_4770(ctx: Ctx) -> Result:
    """A GET is idempotent by definition, so a key on one is claimed by
    nothing — and claiming it would make a read hold a lock that a later
    write under the same key then collides with."""
    key = ctx.unique("key")
    first = ctx.api.get(M, headers={HEADER: key}, auth=ctx.people["owner"])
    if first.status_code >= 400:
        return BLOCKED, f"the read failed: {first.status_code}"
    if first.headers.get(REPLAYED):
        return FAIL, "a GET was treated as a replayable act"
    got = _post(ctx, _spec(ctx), key)
    if got.status_code >= 400:
        return FAIL, (f"a write under a key a GET had already used was "
                      f"refused '{code_of(got)}': a read is holding a key")
    return PASS, "a GET claims nothing, and the key is free for a write"


@case("QA-PLT-051",
      "An idempotent act whose *effects* are not in the response")
def plt_051(ctx: Ctx) -> Result:
    """The replay returns the stored BODY. Everything the act did besides
    answering — the evidence node, the derived state — happened once, and a
    replay must not do it again. This is what makes the mechanism a retry
    guard rather than a response cache."""
    engine = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    body = _spec(ctx)
    key = ctx.unique("key")
    if _post(ctx, body, key).status_code >= 400:
        return BLOCKED, "the first request failed"
    made = ctx.api.get(f"{M}/{body['name']}", auth=ctx.people["risk"])
    if made.status_code >= 400:
        return BLOCKED, "the model is not readable"
    model_id = (made.json() or {}).get("model", {}).get("id")
    before = len(engine.for_subject(model_id))
    replay = _post(ctx, body, key)
    if replay.headers.get(REPLAYED) != "true":
        return BLOCKED, "the second request did not replay"
    after = len(engine.for_subject(model_id))
    if after != before:
        return FAIL, (f"the replay appended {after - before} more evidence "
                      f"node(s), so the act happened twice and only the "
                      f"answer was reused")
    return PASS, f"the answer replayed and the chain is unchanged at {before}"


@case("QA-PLT-4771", "A key released by a failure is usable again")
def plt_4771(ctx: Ctx) -> Result:
    """The other half of *only a success is kept*: after a refusal the key
    must be genuinely free, not merely un-replayable. A key left in flight by
    a failed request is one the client can never retry with — which turns one
    failure into a permanent one."""
    store = ctx.ui.app.state.ctx.get("idempotency")
    if store is None:
        return BLOCKED, "no idempotency store is wired"
    key = ctx.unique("key")
    bad = _post(ctx, {"urn": "", "name": ""}, key)
    if bad.status_code < 400:
        return BLOCKED, "the malformed request was accepted"
    rows = [r for r in store.repo.many() if r.get("idempotency_key") == key]
    if not rows:
        return PASS, "the failed attempt left no row at all"
    if rows[0].get("state") == "in_flight":
        return FAIL, ("a refused request left its key in flight, so the "
                      "client cannot retry with it until the stale window "
                      "expires — one failure made permanent for a quarter of "
                      "an hour")
    if rows[0].get("state") == "complete":
        return FAIL, (f"a refused request was recorded complete with status "
                      f"{rows[0].get('status')}, so the retry replays the "
                      f"failure for ever")
    return PASS, f"the key is left '{rows[0].get('state')}', not complete"
