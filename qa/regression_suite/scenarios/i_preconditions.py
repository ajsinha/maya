"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — conditional writes.

**Silently dropping a precondition header is strictly worse than not
supporting preconditions at all.** The client believes it has optimistic
concurrency, has none, and has stopped checking for itself — and the lost
update it thinks it is preventing is the quietest failure in any register:
two people edit, both save, the second write discards the first, nothing is
refused, and the only trace is a field nobody typed.

So a path with no readable representation refuses `precondition_unevaluable`
rather than passing, and the tag is evaluated by dispatching a real GET
through the whole app — the precondition is compared against exactly the
representation the caller read, not a reconstruction of it.

The tag is WEAK and correctly so: a digest of the semantic content with
rendering noise removed. Claiming octet equality would be claiming something
it does not check.
"""
from __future__ import annotations

from core.concurrency.etags import (ETAG_HEADER, IF_MATCH, VOLATILE, etag_of,
                                    matches)
from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("pc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **SHAPE},
                 auth=ctx.people["owner"])
    return name


def _tag(ctx: Ctx, path: str) -> str:
    got = ctx.api.get(path, auth=ctx.people["risk"])
    return got.headers.get(ETAG_HEADER, "") if got.status_code < 400 else ""


#: A precondition is evaluated by dispatching a GET to THE SAME PATH, so it
#: is only usable where a path answers both verbs. `POST /models/{name}/
#: versions` has no GET, and every conditional write against it is refused
#: `precondition_unevaluable` however fresh the tag — which is correct, and
#: is why these cases write to a collection that reads back.
CONDITIONAL = "/api/v1/api-keys"


def _keyable(ctx: Ctx) -> dict:
    return {"username": "risk", "name": ctx.unique("key"),
            "scopes": ["model:read"], "lifetime_days": 30}


@case("QA-PLT-052", "A stale `If-Match` after somebody else wrote")
def plt_052(ctx: Ctx) -> Result:
    """The lost update, refused. A caller reads, somebody else writes, and
    the first caller's write is decided against something that is no longer
    true."""
    before = _tag(ctx, CONDITIONAL)
    if not before:
        return BLOCKED, f"{CONDITIONAL} carries no ETag"
    moved = ctx.api.post(CONDITIONAL, json=_keyable(ctx), auth=ADMIN)
    if moved.status_code >= 400:
        return BLOCKED, f"the intervening write failed: {moved.text[:140]}"
    after = _tag(ctx, CONDITIONAL)
    if after == before:
        return BLOCKED, ("the representation did not change, so there is no "
                         "stale tag to send")
    got = ctx.api.post(CONDITIONAL, json=_keyable(ctx),
                       headers={IF_MATCH: before}, auth=ADMIN)
    if got.status_code < 400:
        return FAIL, ("a write carrying a stale If-Match was accepted, so the "
                      "caller believes it has optimistic concurrency and has "
                      "none")
    if code_of(got) != "precondition_failed":
        return FAIL, f"refused '{code_of(got)}'"
    if got.headers.get(ETAG_HEADER) != after:
        return FAIL, ("the refusal does not carry the current tag, so the "
                      "caller cannot retry without a second read")
    return PASS, "refused 'precondition_failed', carrying the current tag"


@case("QA-PLT-4780", "A fresh `If-Match` is accepted")
def plt_4780(ctx: Ctx) -> Result:
    """The other half of QA-PLT-052, and the one that makes the header
    usable. A control that refused every conditional write would be
    indistinguishable from one nobody can satisfy."""
    tag = _tag(ctx, CONDITIONAL)
    if not tag:
        return BLOCKED, f"{CONDITIONAL} carries no ETag"
    got = ctx.api.post(CONDITIONAL, json=_keyable(ctx),
                       headers={IF_MATCH: tag}, auth=ADMIN)
    if got.status_code >= 400:
        return FAIL, (f"a write carrying the CURRENT tag was refused "
                      f"'{code_of(got)}', so no conditional write can succeed")
    return PASS, "the current tag satisfies the precondition"


@case("QA-PLT-053",
      "`If-Match: *` against a resource that exists, and one that does not")
def plt_053(ctx: Ctx) -> Result:
    """`*` is the header's way of saying *only if it is there*. Against a
    path with no representation it must NOT pass, or the one form of the
    header that means *check existence* would be the one that checks
    nothing."""
    live = ctx.api.post(CONDITIONAL, json=_keyable(ctx),
                        headers={IF_MATCH: "*"}, auth=ADMIN)
    if live.status_code >= 400:
        return FAIL, (f"`If-Match: *` against a resource that exists was "
                      f"refused '{code_of(live)}'")
    gone = ctx.api.post(f"{M}/never-registered/versions",
                        json={"semver": "1.0.0"}, headers={IF_MATCH: "*"},
                        auth=ctx.people["developer"])
    if gone.status_code < 400:
        return FAIL, ("`If-Match: *` passed against a path with no "
                      "representation, so the form that means *only if it is "
                      "there* is the one that checks nothing")
    return PASS, (f"`*` accepted where the resource exists, refused "
                  f"'{code_of(gone)}' where it does not")


@case("QA-PLT-054",
      "`If-Match` sent to a route that has no representation to compare")
def plt_054(ctx: Ctx) -> Result:
    """The rule the module exists for. Ignoring the header would give the
    caller optimistic concurrency they do not have, and the refusal has to
    say that rather than 404 — the path is fine, the precondition is what
    cannot be evaluated."""
    name = _model(ctx)
    got = ctx.api.post(f"{M}/{name}/assess",
                       json={"exposure": 1000.0, "purpose_class": "commercial",
                             "feature_count": 3, "interpretable": True,
                             "uses_alternative_data": False},
                       headers={IF_MATCH: 'W/"nothing"'},
                       auth=ctx.people["risk"])
    if got.status_code < 400:
        return FAIL, ("a precondition on a path with no GET was silently "
                      "dropped: the caller believes it has optimistic "
                      "concurrency and has none")
    if code_of(got) == "precondition_unevaluable":
        if "optimistic concurrency" not in got.text:
            return FAIL, "the refusal does not say what the caller would lose"
        return PASS, "refused 'precondition_unevaluable'"
    if code_of(got) == "precondition_failed":
        return PASS, ("the path does read back, and the invented tag is "
                      "refused as stale")
    return FAIL, f"refused '{code_of(got)}'"


@case("QA-PLT-057", "A strong tag sent where a weak one was issued")
def plt_057(ctx: Ctx) -> Result:
    """The weak prefix is compared as given rather than normalised away. A
    caller sending a strong tag is asking a stronger question than this can
    answer — octet equality — and quietly treating it as weak would answer a
    different question from the one asked."""
    weak = _tag(ctx, CONDITIONAL)
    if not weak.startswith('W/'):
        return FAIL, f"the issued tag is not weak: {weak!r}"
    strong = weak[2:]
    if matches(strong, weak):
        return FAIL, ("a strong tag matches a weak one, so a caller asking "
                      "about the octets is answered about the semantics")
    got = ctx.api.post(CONDITIONAL, json=_keyable(ctx),
                       headers={IF_MATCH: strong}, auth=ADMIN)
    if got.status_code < 400:
        return FAIL, "a strong tag satisfied a weak precondition over HTTP"
    if code_of(got) != "precondition_failed":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "the strong form is not silently normalised to the weak one"


@case("QA-PLT-056",
      "A change confined to a field named `detail` produces an unchanged "
      "ETag")
def plt_056(ctx: Ctx) -> Result:
    """`detail` is in `VOLATILE` on purpose: a tag that changes when nothing
    did makes every conditional request a full one and teaches clients to
    stop sending the header. The risk is the other direction — a real change
    hidden inside a volatile field — so the case pins that the exclusion is
    by NAME and narrow."""
    base = {"model": {"urn": "maya://model/x", "owner": "a"},
            "detail": "one sentence"}
    changed = {"model": {"urn": "maya://model/x", "owner": "a"},
               "detail": "a completely different sentence"}
    if etag_of(base) != etag_of(changed):
        return FAIL, ("a change confined to `detail` moves the tag, so every "
                      "conditional request becomes a full one")
    real = {"model": {"urn": "maya://model/x", "owner": "b"},
            "detail": "one sentence"}
    if etag_of(base) == etag_of(real):
        return FAIL, ("a change to the owner does NOT move the tag, so the "
                      "volatile exclusion is hiding real state")
    if "detail" not in VOLATILE:
        return FAIL, f"`detail` is not in VOLATILE: {VOLATILE}"
    leaking = [f for f in VOLATILE if f not in
               ("detail", "as_at", "now", "generated_at", "seconds_left")]
    if leaking:
        return FAIL, (f"VOLATILE has grown beyond rendering noise: {leaking} "
                      f"— each one is state a conditional write cannot see")
    return PASS, f"`detail` excluded, real state still tagged; {len(VOLATILE)} volatile fields"


@case("QA-PLT-060", "Two writers, no `If-Match` at all")
def plt_060(ctx: Ctx) -> Result:
    """Without the header the second write wins silently, and that is the
    correct behaviour — a server that refused unconditional writes would be
    imposing a concurrency model nobody asked for. What matters is that the
    tag was OFFERED, so a client that wants the guarantee can have it."""
    name = _model(ctx)
    path = f"{M}/{name}"
    got = ctx.api.get(path, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the model reading answered {got.status_code}"
    if not got.headers.get(ETAG_HEADER):
        return FAIL, ("a readable representation is served with no ETag, so a "
                      "client that wants optimistic concurrency has no tag to "
                      "send")
    first = ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                         auth=ctx.people["developer"])
    second = ctx.api.post(f"{M}/{name}/versions", json={"semver": "2.0.0"},
                          auth=ctx.people["developer"])
    if first.status_code >= 400 or second.status_code >= 400:
        return BLOCKED, "the unconditional writes did not both land"
    return PASS, ("both unconditional writes land, and the tag is offered on "
                  "the read so a client can opt in")


@case("QA-PLT-4781", "The ETag is served on a GET and is stable")
def plt_4781(ctx: Ctx) -> Result:
    """A tag that changes when nothing did is the failure that teaches
    clients to stop sending the header, so two reads of an unchanged
    resource have to agree."""
    name = _model(ctx)
    path = f"{M}/{name}"
    first, second = _tag(ctx, path), _tag(ctx, path)
    if not first:
        return FAIL, "a JSON reading is served with no ETag at all"
    if first != second:
        return FAIL, (f"two reads of an unchanged model gave {first} then "
                      f"{second}")
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    after = _tag(ctx, path)
    if after == first:
        return FAIL, ("adding a version did not move the tag, so a "
                      "conditional write cannot see a real change")
    return PASS, "stable across reads, moved by a write"


@case("QA-PLT-063", "A read-then-write check under concurrency")
def plt_063(ctx: Ctx) -> Result:
    """Whatever a race does here, it must answer a NAMED refusal rather than
    a 500. An unhandled integrity error at the edge is a caller told nothing
    about a request that may or may not have landed."""
    import threading
    # ROUNDS, not one race. Four threads against a read-then-write win or lose
    # on timing, and a single round reports the control working whenever the
    # scheduler happens to serialise it — which is the false pass QA-PLT-160
    # was caught giving. The worst round is the answer.
    rounds, crashed, winners, seen = 6, [], [], []
    for _round in range(rounds):
        name = _model(ctx)
        out = {}

        def go(n, model=name, sink=out):
            sink[n] = ctx.api.post(f"{M}/{model}/versions",
                                   json={"semver": "1.0.0"},
                                   auth=ctx.people["developer"])

        threads = [threading.Thread(target=go, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if len(out) != 4:
            return BLOCKED, "not every racing request returned"
        crashed += [r for r in out.values() if r.status_code >= 500]
        won = [r for r in out.values() if r.status_code < 400]
        winners.append(len(won))
        seen.append({code_of(r) for r in out.values() if r.status_code >= 400})
    if crashed:
        return FAIL, (f"{len(crashed)} of {rounds * 4} racing writes across "
                      f"{rounds} rounds answered {crashed[0].status_code} with "
                      f"no code: {crashed[0].text[:110]}")
    if set(winners) != {1}:
        return FAIL, (f"racing creations of one version succeeded "
                      f"{winners} times across {rounds} rounds; versions are "
                      f"immutable so exactly one should win each time")
    codes = set().union(*seen)
    if not codes or "" in codes:
        return FAIL, f"a loser refused with no code: {codes}"
    return PASS, (f"{rounds} rounds of four: one winner each time, "
                  f"losers refused {sorted(codes)}, no 500")


@case("QA-PLT-062", "An evidence append racing another evidence append")
def plt_062(ctx: Ctx) -> Result:
    """The recorded defect. The chain is a read-then-write and it was neither
    atomic nor retried: at four threads 7% of appends raised, and every
    service commits its own row BEFORE appending evidence — so the model
    existed and the record of its registration did not. Worse than a missing
    row: segregation of duties is decided by reading the chain, so a lost
    `version_created` node meant *you cannot approve what you created* had
    nothing to read."""
    import threading
    engine = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    before, _head = engine.head()
    out = {}

    def go(n):
        spec = {"urn": f"maya://model/{n}-{ctx.unique('rc')}",
                "name": ctx.unique("rc"), "owner": "owner", **SHAPE}
        out[n] = ctx.api.post(M, json=spec, auth=ADMIN)

    threads = [threading.Thread(target=go, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    made = [r for r in out.values() if r.status_code < 400]
    if not made:
        return BLOCKED, "no concurrent registration succeeded"
    after, _ = engine.head()
    if after - before < len(made):
        return FAIL, (f"{len(made)} models were registered concurrently and "
                      f"the chain grew by {after - before} node(s): a "
                      f"governance act exists with no record of it")
    report = engine.verify_chain()
    if not report.get("valid"):
        return FAIL, f"the chain does not verify after concurrent appends: {report}"
    seqs = sorted(n["seq"] for n in engine.repo.many())
    if seqs != list(range(1, len(seqs) + 1)):
        return FAIL, "the sequence is not contiguous after concurrent appends"
    return PASS, (f"{len(made)} concurrent registrations, {after - before} "
                  f"nodes, contiguous and verifying")
