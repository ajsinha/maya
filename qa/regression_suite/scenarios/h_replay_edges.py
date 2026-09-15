"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — replaying a validation, and the ways a replay can agree for the
wrong reason.

Replay is the strongest claim the validation register makes: the same test key,
the same parameters and the same data produce the same digest years later, and
when they do not, the difference IS the finding. Everything that weakens it
weakens it the same way — by producing a report that says *matched* about
something that was not compared.

`h_replay.py` covers a replay that runs. These are the cases where there is
nothing to run against, or where the caller supplies the answer.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

V = "/api/v1/validations"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
LABELS = [0, 1, 0, 1, 1, 0, 1, 0]
SCORES = [0.1, 0.9, 0.2, 0.8, 0.7, 0.3, 0.95, 0.05]
KEY = "discrimination.auc"


def _episode(ctx: Ctx, *, with_result: bool = True) -> str:
    name = ctx.unique("rp")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    got = ctx.api.post(V, json={"urn": urn, "semver": "1.0.0",
                                "validators": ["validator"], "kind": "initial"})
    if got.status_code >= 400:
        return ""
    episode = (got.json() or {}).get("id", "")
    if episode and with_result:
        ctx.api.post(f"{V}/{episode}/results",
                     json={"test_key": KEY, "left": LABELS, "right": SCORES,
                           "threshold": {"min": 0.6}},
                     auth=ctx.people["validator"])
    return episode


def _replay(ctx: Ctx, episode: str, data=None):
    return ctx.api.post(f"{V}/{episode}/replay", json={"data": data or {}},
                        auth=ctx.people["validator"])


@case("QA-AM-700", "Replay a validation that has no results")
def am_700(ctx: Ctx) -> Result:
    """Nothing recorded means nothing to disagree with, and a comparison over
    an empty set agrees trivially. An episode with no results must not report
    a replay that MATCHED — that sentence would appear in a pack as evidence
    the validation had been reproduced."""
    episode = _episode(ctx, with_result=False)
    if not episode:
        return BLOCKED, "no episode could be opened"
    got = _replay(ctx, episode)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    body = got.json() or {}
    count = body.get("total")
    if count is None:
        compared = body.get("compared") or body.get("tests") or []
        count = len(compared) if isinstance(compared, list) else compared
    if body.get("reproducible") is True and not count:
        return FAIL, (f"an episode with no recorded results reports "
                      f"`matched: true` over {count} test(s), so a replay of "
                      f"nothing reads as a validation reproduced: "
                      f"{got.text[:130]}")
    said = str(body.get("detail") or "")
    if not count and "no result" not in said.lower() and "nothing" not in said.lower():
        return FAIL, (f"replayed zero tests without saying the episode has "
                      f"none: {said[:110]!r}")
    return PASS, f"{count} test(s) compared; {said[:90]}"


@case("QA-AM-701", "Replay a validation that does not exist")
def am_701(ctx: Ctx) -> Result:
    """404, and specifically not an empty report. The replay endpoint takes
    the caller's own data, so an unknown id that answered 200 would compare
    the caller's numbers against nothing and report agreement."""
    got = _replay(ctx, ctx.unique("no-such-episode"),
                  {KEY: [LABELS, SCORES]})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, (f"replaying an episode that does not exist answered "
                      f"{got.status_code}: {got.text[:130]}")
    return PASS, f"refused '{code_of(got)}' ({got.status_code})"


@case("QA-AM-702", "Replay the same episode twice gives the same report")
def am_702(ctx: Ctx) -> Result:
    """Determinism is the property, so the test is the obvious one and it is
    worth having: a replay that disagreed with ITSELF would make every replay
    finding unattributable, because nobody could say whether the difference
    was in the model or in the comparison."""
    episode = _episode(ctx)
    if not episode:
        return BLOCKED, "no episode could be opened"
    first = _replay(ctx, episode, {KEY: [LABELS, SCORES]})
    if first.status_code >= 400:
        return BLOCKED, f"the first replay answered {first.status_code}: {first.text[:120]}"
    second = _replay(ctx, episode, {KEY: [LABELS, SCORES]})
    if second.status_code >= 400:
        return FAIL, f"a second replay answered {second.status_code}"

    def comparable(body):
        """Everything but the timestamps, which are allowed to move."""
        return {k: v for k, v in (body or {}).items()
                if not k.endswith(("_at", "_seconds", "_ms"))}

    one, two = comparable(first.json()), comparable(second.json())
    if one != two:
        moved = sorted(k for k in set(one) | set(two) if one.get(k) != two.get(k))
        return FAIL, (f"two replays of one episode over identical data "
                      f"disagree on {moved}, so a replay finding cannot be "
                      f"attributed to the model rather than to the comparison")
    return PASS, f"identical over {sorted(one)[:5]}"


@case("QA-AM-703", "Replay from storage with no snapshot pinned")
def am_703(ctx: Ctx) -> Result:
    """The honest answer is *skipped, and here is why* — not *matched*. An
    episode that pins no snapshot has nothing to re-read, and a replay-from-
    storage that reported agreement would be reporting that it compared the
    recorded digest against the recorded digest."""
    episode = _episode(ctx)
    if not episode:
        return BLOCKED, "no episode could be opened"
    readable = ctx.api.get(f"{V}/{episode}/replayable",
                           auth=ctx.people["validator"])
    if readable.status_code < 400 and (readable.json() or {}).get("readable"):
        return BLOCKED, "this episode pins a snapshot, so there is nothing to test"
    got = ctx.api.post(f"{V}/{episode}/replay-from-storage",
                       auth=ctx.people["validator"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    body = got.json() or {}
    if body.get("matched") is True:
        return FAIL, (f"an episode pinning no snapshot reports `matched: true` "
                      f"from storage, so a comparison that read nothing is "
                      f"reported as a validation reproduced: {got.text[:120]}")
    # Over the WHOLE answer: the skipped tests are their own list, so reading
    # only `detail` reported a correct skip as silence.
    said = got.text.lower()
    if "skip" not in said and "snapshot" not in said:
        return FAIL, (f"replayed from storage with no snapshot and the answer "
                      f"does not say so: {got.text[:130]}")
    return PASS, "every test reported skipped, naming the absent snapshot"


@case("QA-AM-1900", "Replay with data that is not the data")
def am_1900(ctx: Ctx) -> Result:
    """The case the whole mechanism exists for. Supply DIFFERENT numbers under
    the right test key: the digest must move and the report must say the test
    did not match. A replay that agreed here would agree with anything."""
    episode = _episode(ctx)
    if not episode:
        return BLOCKED, "no episode could be opened"
    other = [round(1.0 - s, 4) for s in SCORES]       # the ranking reversed
    got = _replay(ctx, episode, {KEY: [LABELS, other]})
    if got.status_code >= 400:
        return BLOCKED, f"the replay answered {got.status_code}: {got.text[:120]}"
    body = got.json() or {}
    if body.get("matched") is True:
        return FAIL, (f"a replay over REVERSED scores reports `matched: true`, "
                      f"so the comparison agrees with data that is not the "
                      f"data and every replay result is worthless: "
                      f"{got.text[:130]}")
    text = got.text.lower()
    if "differ" not in text and "mismatch" not in text and "not match" not in text:
        return FAIL, (f"the replay did not match and does not say what "
                      f"differed: {got.text[:140]}")
    return PASS, "the reversed scores are reported as not matching"


@case("QA-AM-1901", "Replay data for a test the episode never recorded")
def am_1901(ctx: Ctx) -> Result:
    """Supplying data under a key the episode does not hold must not create a
    comparison. If it did, a validator could add a passing test to a completed
    episode by replaying it — the strongest possible version of *a check that
    passes for the wrong reason*."""
    episode = _episode(ctx)
    if not episode:
        return BLOCKED, "no episode could be opened"
    got = _replay(ctx, episode,
                  {KEY: [LABELS, SCORES],
                   "calibration.brier": [LABELS, SCORES]})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    body = got.json() or {}
    compared = body.get("compared") or body.get("tests") or []
    keys = [c.get("test_key") or c.get("key") for c in compared] \
        if isinstance(compared, list) and compared \
        and isinstance(compared[0], dict) else []
    if "calibration.brier" in keys:
        return FAIL, ("the replay compared a test the episode never recorded, "
                      "so replaying an episode can add a result to it")
    if keys and set(keys) - {KEY}:
        return FAIL, f"the replay compared {sorted(set(keys))}, not just {KEY}"
    return PASS, ("only the recorded test was compared"
                  + (f" ({keys})" if keys else ""))
