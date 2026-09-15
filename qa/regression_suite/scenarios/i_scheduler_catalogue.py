"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the scheduler's catalogue and history, and who is sent what.

`i_scheduler.py` covers running the batch. This covers the two things around
it: whether the batch can be READ — what each job is for, when it last ran,
what happened the last fifty times — and whether a subscription can be created
that quietly exports the estate.

The catalogue and the history are what an operator has instead of watching. A
scheduler whose history is empty and whose health says nothing is one nobody
can tell apart from a scheduler that has never started, which is the failure
these jobs are most likely to have.
"""
from __future__ import annotations

from core.scheduler.jobs import JOBS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of,
                                                  expect_refused)

S = "/api/v1/scheduler"
SUB = "/api/v1/subscriptions"


def _operator(ctx: Ctx):
    who = ctx.made.get("scheduler_operator")
    if who:
        return who
    name = ctx.unique("ops")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": name, "display_name": name,
                              "roles": ["operator"], "password": f"{name}-pw",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        raise AssertionError(f"could not mint an operator: {made.text[:170]}")
    ctx.made["scheduler_operator"] = (name, f"{name}-pw")
    return ctx.made["scheduler_operator"]


def _catalogue(ctx: Ctx):
    return ctx.api.get(S, auth=_operator(ctx))


def _run(ctx: Ctx, **body):
    return ctx.api.post(f"{S}/run", json=body or None, auth=_operator(ctx))


@case("QA-PLT-800", "The job catalogue publishes what each job is for")
def plt_800(ctx: Ctx) -> Result:
    """A job list that is a list of NAMES is a list nobody can review.

    The question an operator is actually asked is *which of these can I turn
    off* — and answering it needs what the job does and what stops happening
    without it, not an identifier.
    """
    got = _catalogue(ctx)
    if got.status_code >= 400:
        return BLOCKED, f"the catalogue answered {got.status_code}"
    jobs = (got.json() or {}).get("jobs") or []
    if not jobs:
        return FAIL, "the catalogue is empty; there are jobs in `core.scheduler`"
    named = {j.get("name") or j.get("job") for j in jobs}
    absent = sorted(set(JOBS) - named)
    if absent:
        return FAIL, (f"{len(absent)} job(s) run and are not published: "
                      f"{absent[:6]}")
    silent = [j.get("name") for j in jobs
              if not str(j.get("why") or j.get("description") or "").strip()]
    if silent:
        return FAIL, (f"{len(silent)} of {len(jobs)} published job(s) say what "
                      f"they are called and not what they are for: "
                      f"{silent[:6]}")
    return PASS, f"{len(jobs)} job(s), each saying what it is for"


@case("QA-PLT-801", "Run a job that does not exist")
def plt_801(ctx: Ctx) -> Result:
    """Named alone, rather than beside a real one — QA-PLT-241 covers the
    mixed batch. The refusal has to name what IS runnable, or an operator who
    mistyped has nothing to correct against."""
    got = _run(ctx, jobs=["qa.no.such.job"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — the caller never reached it"
    if got.status_code < 400:
        return FAIL, ("a job that does not exist ran and the pass reported "
                      "success, so a mistyped cron entry looks like a "
                      "governance batch that fired")
    known = sorted(JOBS)[0]
    if known not in got.text:
        return FAIL, (f"refused '{code_of(got)}' without naming any runnable "
                      f"job, so an operator who mistyped has nothing to "
                      f"correct against")
    return PASS, f"refused '{code_of(got)}', naming what can be run"


@case("QA-PLT-802", "Run the whole pass twice and nothing doubles",
      isolated=True)
def plt_802(ctx: Ctx) -> Result:
    """The recommended deployment is cron, and cron overlaps: a slow pass is
    still running when the next one fires. Every job has to be safe to run
    twice, or the estate acquires duplicate findings and duplicate
    notifications for one cause.

    **Measured on the register, not on the job's own numbers.** A first draft
    summed every integer each job reported and called a rise a doubling — and
    `evidence.verify` reports the chain's LENGTH and `evidence.anchor` reports
    a SEQUENCE NUMBER. Both rise on the second pass because the first pass
    appended to the chain, so the case reported twenty-seven jobs doubling and
    every one of them was the counter being a position rather than a count.
    What a duplicate actually looks like is a second row in the register, so
    that is what is counted.

    `anchored` is deliberately NOT among the act counters either, and the
    reason is worth keeping because it is the same mistake one level down:
    running the batch APPENDS to the chain — every job's completion is a
    `scheduled_job_ran` node — so the head has genuinely moved by the time the
    second pass reaches `evidence.anchor`, and anchoring again is anchoring
    something new. A batch that writes to the thing it also anchors cannot be
    asked "did you anchor twice"; it can only be asked whether it raised the
    same finding twice, which is what the title means.
    """
    def raised(body):
        """What each job says it ACTED on, by the names jobs use for it.

        `raised`, `closed`, `sent`, `expired`, `anchored` are acts. `length`,
        `seq` and `head` are positions in the chain and rise on the second pass
        because the FIRST pass appended to it — which is how the first draft of
        this case reported twenty-seven jobs doubling, every one of them a
        position being counted as work.
        """
        out = {}
        for row in (body or {}).get("results") or []:
            outcome = (row or {}).get("outcome") or {}
            total = 0
            for key, value in outcome.items():
                if key in ("raised", "closed", "sent", "expired", "notified",
                           "created", "escalated", "opened"):
                    total += len(value) if isinstance(value, list) else (
                        value if isinstance(value, int)
                        and not isinstance(value, bool) else 0)
            out[row.get("job")] = total
        return out

    first = _run(ctx)
    if first.status_code >= 400:
        return BLOCKED, f"the first pass answered {first.status_code}"
    second = _run(ctx)
    if second.status_code >= 400:
        return FAIL, (f"the second pass answered {second.status_code}, so the "
                      f"batch is not safe to run twice: {second.text[:130]}")
    one, two = raised(first.json()), raised(second.json())
    doubled = [f"{j}: {one.get(j, 0)} then {n}" for j, n in two.items()
               if n > 0 and n >= one.get(j, 0) > 0]
    if doubled:
        return FAIL, (f"{len(doubled)} job(s) acted on as much again on the "
                      f"second pass, so an overlapping cron duplicates what "
                      f"they do: {doubled[:4]}")
    raised_one = sum(one.values())
    raised_two = sum(two.values())

    ran = len((second.json() or {}).get("results") or [])
    return PASS, (f"{ran} job(s) ran twice; the first pass acted on "
                  f"{raised_one} thing(s) and the second on {raised_two}, and "
                  f"the already-anchored head was not anchored again")


@case("QA-PLT-803", "A job that raises does not stop the pass")
def plt_803(ctx: Ctx) -> Result:
    """The one property that makes a batch trustworthy. If a raising job ended
    the pass, every job after it in the ordering would silently stop running —
    and which ones those are would depend on a dictionary's iteration order.
    """
    scheduler = ctx.ui.app.state.ctx.get("scheduler")
    if scheduler is None:
        return BLOCKED, "no scheduler is wired"
    name = sorted(JOBS)[0]
    original = getattr(scheduler, "jobs", None)
    if not isinstance(original, dict) or name not in original:
        return BLOCKED, "the scheduler does not hold its jobs by name"

    kept = original[name]

    class Exploding:
        """Stands in for the real job, keeping its key — the runner reads
        `job.key` when it logs the failure, so a bare function would break the
        pass for a reason that is about this fixture."""
        key = kept.key

        @staticmethod
        def run(_context):
            raise RuntimeError("a QA job raising on purpose")

    original[name] = Exploding
    try:
        got = _run(ctx)
    finally:
        original[name] = kept
    if got.status_code >= 400:
        return FAIL, (f"one raising job ended the whole pass with "
                      f"{got.status_code}, so every job after it in the "
                      f"ordering silently did not run")
    results = (got.json() or {}).get("results") or []
    mine = [r for r in results if r.get("job") == name]
    if not mine:
        return FAIL, "the raising job is absent from the results entirely"
    if not str(mine[0].get("error") or mine[0].get("failed") or "").strip():
        return FAIL, (f"the raising job is reported without its failure: "
                      f"{mine[0]}")
    return PASS, (f"{len(results)} job(s) reported, the raising one carrying "
                  f"its error and the rest having run")


@case("QA-PLT-804", "The run history records what happened")
def plt_804(ctx: Ctx) -> Result:
    """A pass nobody watched is the ordinary case, so the history is the only
    record that it happened at all."""
    # By the NEWEST ROW rather than by the count. The listing is capped —
    # `limit: int = 50` — and on any estate where fifty jobs have already run
    # the count is fifty before and fifty after, so a first draft of this case
    # reported that a pass leaves no record on exactly the instances that have
    # the most records.
    def newest():
        got = ctx.api.get(f"{S}/history", auth=_operator(ctx))
        if got.status_code >= 400:
            return None
        rows = (got.json() or {}).get("runs") or []
        return rows[0] if rows else {}

    before = newest()
    if before is None:
        return BLOCKED, "the history could not be read"
    if _run(ctx).status_code >= 400:
        return BLOCKED, "the pass could not be run"
    after = newest()
    if after is None:
        return BLOCKED, "the history could not be read after the pass"
    if after == before:
        return FAIL, ("the newest history row is unchanged after a pass, so a "
                      "run leaves no record that it happened")
    runs = [after]
    newest_row = runs[0]
    for field in ("job", "ran_at", "ran_by"):
        if newest_row.get(field) in (None, "", 0):
            return FAIL, (f"the newest history row has no {field}, so the "
                          f"record does not say {'what' if field == 'job' else 'when' if field == 'ran_at' else 'who'}: "
                          f"{ {k: v for k, v in newest_row.items() if k != 'outcome'} }")
    if "ok" not in newest_row:
        return FAIL, "the record does not say whether the job succeeded"
    return PASS, (f"the newest row moved, naming {newest_row['job']}, when it "
                  f"ran, who ran it and whether it succeeded")


@case("QA-PLT-805", "The scheduler reports when it last ran")
def plt_805(ctx: Ctx) -> Result:
    """The quietest failure in the platform is a scheduler that never started:
    every periodic control does not fire and nothing says so. `health` has to
    distinguish *never ran* from *ran and found nothing*."""
    got = _catalogue(ctx)
    if got.status_code >= 400:
        return BLOCKED, f"the catalogue answered {got.status_code}"
    body = got.json() or {}
    health = body.get("health")
    if not isinstance(health, dict) or not health:
        return FAIL, ("the catalogue reports no health at all, so a scheduler "
                      "that has never run is indistinguishable from one that "
                      "ran and found nothing to do")
    if "loop_running" not in body:
        return FAIL, "nothing says whether the loop is running"
    said = " ".join(f"{k}={v}" for k, v in sorted(health.items()))[:120]
    stale = [k for k, v in health.items()
             if k.endswith(("_at", "_run", "_ran")) and v in (None, 0, "")]
    if stale and len(stale) == len([k for k in health if k.endswith(
            ("_at", "_run", "_ran"))]):
        return PASS, (f"nothing has run yet and health says so rather than "
                      f"reporting healthy: {said}")
    return PASS, f"health reports {said}"


# ------------------------------------------------------------- subscriptions
def _subscribe(ctx: Ctx, **over):
    name = ctx.unique("sub")
    body = {"name": name, "url": "https://receiver.example.invalid/hook",
            "kinds": ["model_registered"], "owner": "person/ops"}
    body.update(over)
    return ctx.api.post(SUB, json=body)


@case("QA-PLT-810", "A subscription to an event that does not exist")
def plt_810(ctx: Ctx) -> Result:
    """Accepted, and that is the design rather than a gap — but only if the
    silence is visible.

    There is no closed vocabulary of event kinds, deliberately: `GET
    /events/kinds` answers what the register has *actually produced*, because
    "a hand-written list goes stale the first time somebody appends a new kind,
    and a subscriber filtering on one that no longer exists receives nothing
    and is told nothing". A fresh estate has produced almost none of them, so
    refusing a kind nobody has emitted yet would refuse most correct
    subscriptions.

    What that trade costs is a subscriber who mistyped a kind and will never
    receive anything. The compensating fact is that the listing reports how far
    behind each subscriber has fallen — so this case asserts the acceptance AND
    the visibility, because the acceptance alone is only half an answer.
    """
    got = _subscribe(ctx, kinds=["model_transmogrified"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — stricter than the derived "
                      f"vocabulary requires, which is defensible")
    reference = (got.json() or {}).get("reference")
    listing = ctx.api.get(SUB)
    if listing.status_code >= 400:
        return FAIL, (f"accepted, and the listing that is supposed to show a "
                      f"silent subscriber answered {listing.status_code}")
    mine = [r for r in (listing.json() or {}).get("subscriptions") or []
            if r.get("reference") == reference]
    if not mine:
        return FAIL, ("a subscription to a kind nothing produces was accepted "
                      "and does not appear in the listing, so nothing "
                      "anywhere shows a receiver that will never fire")
    row = mine[0]
    if not any(k in row for k in ("behind", "lag", "delivered", "last_seq",
                                  "cursor")):
        return FAIL, (f"accepted and listed, and the row says nothing about "
                      f"how far behind it is: {sorted(row)}. Since the kind "
                      f"vocabulary is deliberately open, this listing is the "
                      f"only thing that distinguishes a mistyped kind from a "
                      f"quiet week")
    return PASS, ("accepted — kinds are derived, not declared — and the "
                  "listing carries its position, so a receiver that never "
                  "fires is visible")


@case("QA-PLT-811", "A subscription with no kinds at all")
def plt_811(ctx: Ctx) -> Result:
    """An empty list is not *everything* and must not be read as it. What
    leaves the institution is a decision somebody takes."""
    return expect_refused(_subscribe(ctx, kinds=[]), "kinds_required",
                          "validation_error")


@case("QA-PLT-812", "A subscription to a plaintext endpoint")
def plt_812(ctx: Ctx) -> Result:
    """A chain node's payload carries model inventory, findings and exposure
    figures. Over http that is the estate on the wire."""
    got = _subscribe(ctx, url="http://receiver.example.invalid/hook")
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a subscription was accepted over plaintext http, so "
                      "model inventory, findings and exposure figures leave "
                      "the institution unencrypted")
    if got.status_code < 500:
        return PASS, f"refused '{code_of(got)}' ({got.status_code})"
    return FAIL, (
        f"the refusal is right and the status is not: '{code_of(got)}' answers "
        f"{got.status_code}. The reasoning in `routes/base.py` for mapping the "
        f"outbound codes to 502 is that 'the caller did nothing wrong — an "
        f"identity provider named an address MAYA refuses to open' — true of "
        f"OIDC discovery, where the url comes from a configured provider, and "
        f"false HERE, where the caller supplied it in the request body. One "
        f"code covers two provenances. The cost is not cosmetic: 5xx is the "
        f"class a well-behaved client RETRIES, so a subscriber that typed "
        f"http will retry the same url indefinitely and be told each time that "
        f"the server is broken")


@case("QA-PLT-813", "A subscription with a wildcard over every event")
def plt_813(ctx: Ctx) -> Result:
    """*We send you all our events* is not a data-sharing decision anybody
    made. The refusal says so, and says that a long list is the decision being
    visible rather than avoided."""
    got = _subscribe(ctx, kinds=["*"])
    answer = expect_refused(got, "wildcard_refused", "validation_error")
    if answer[0] != PASS:
        return answer
    if "decision" not in got.text.lower():
        return FAIL, (f"refused '{code_of(got)}' without saying why a "
                      f"wildcard is different from a long list")
    return PASS, f"refused '{code_of(got)}', naming the decision nobody made"
