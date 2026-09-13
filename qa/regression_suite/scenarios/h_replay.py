"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — replaying a validation.

The claim being tested is narrow and important: a replay is reproducible only
if EVERYTHING was checked and matched. A test whose data cannot be supplied is
skipped, never silently passed, because a replay that reports success over the
subset somebody happened to hand back is worse than no replay.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

V = "/api/v1/validations"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
LEFT = [float(n) for n in range(50)]
RIGHT = [float(n) + 1.0 for n in range(50)]
PSI, KS = "stability.psi", "discrimination.ks"


def _episode(ctx: Ctx) -> str:
    name = ctx.unique("rp")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    made = ctx.api.post(V, json={"urn": f"maya://model/{name}",
                                 "semver": "1.0.0", "kind": "initial",
                                 "validators": ["person/validator"]},
                        auth=ctx.people["risk"])
    return made.json()["id"] if made.status_code < 400 else ""


def _record(ctx: Ctx, vid: str, test_key: str = PSI, left=None, right=None):
    return ctx.api.post(f"{V}/{vid}/results",
                        json={"test_key": test_key,
                              "left": list(left if left is not None else LEFT),
                              "right": list(right if right is not None else RIGHT)},
                        auth=ctx.people["validator"])


def _replay(ctx: Ctx, vid: str, data: dict):
    return ctx.api.post(f"{V}/{vid}/replay", json={"data": data},
                        auth=ctx.people["auditor"])


@case("QA-AM-050", "Replay an episode with zero recorded results")
def am_050(ctx: Ctx) -> Result:
    """Nothing to replay must not report as reproducible. An episode that
    recorded nothing would otherwise be the most reproducible in the estate.
    """
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _replay(ctx, vid, {})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    body = got.json() or {}
    if body.get("reproducible"):
        return FAIL, ("an episode with no results at all reported as "
                      "reproducible, so recording nothing is the surest way "
                      "to pass a replay")
    if body.get("total") != 0:
        return FAIL, f"total is {body.get('total')} with nothing recorded"
    if "no results" not in (body.get("detail") or ""):
        return FAIL, f"the reason is not stated: {(body.get('detail') or '')[:90]}"
    return PASS, "not reproducible, and the reason is that there is nothing"


@case("QA-AM-049", "Replay supplying data for one of two recorded tests")
def am_049(ctx: Ctx) -> Result:
    """The half that was checked must not stand for the whole. A skipped test
    is reported as skipped and drags `reproducible` to false."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    for key in (PSI, KS):
        made = _record(ctx, vid, test_key=key)
        if made.status_code >= 400:
            return BLOCKED, f"{key}: {made.text[:140]}"
    got = _replay(ctx, vid, {PSI: [LEFT, RIGHT]})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if body.get("reproducible"):
        return FAIL, ("a replay covering one of two tests reported as "
                      "reproducible; the test nobody could check counted as "
                      "checked")
    if len(body.get("skipped") or []) != 1:
        return FAIL, f"skipped: {body.get('skipped')}"
    if (body["skipped"][0].get("test_key")) != KS:
        return FAIL, f"the wrong test was skipped: {body['skipped']}"
    return PASS, "1 reproduced, 1 skipped, reproducible false"


@case("QA-AM-051", "Replay twice with identical data")
def am_051(ctx: Ctx) -> Result:
    """A replay is a read. Running it twice must produce the same report, or
    the report is evidence of when it ran rather than of what is true."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    if _record(ctx, vid).status_code >= 400:
        return BLOCKED, "the result could not be recorded"
    first = _replay(ctx, vid, {PSI: [LEFT, RIGHT]})
    second = _replay(ctx, vid, {PSI: [LEFT, RIGHT]})
    if first.status_code >= 400 or second.status_code >= 400:
        return BLOCKED, first.text[:170]
    a, b = first.json(), second.json()
    for field in ("reproducible", "total", "reproduced", "detail"):
        if a.get(field) != b.get(field):
            return FAIL, (f"two replays of the same episode disagree on "
                          f"'{field}': {a.get(field)} then {b.get(field)}")
    return PASS, f"identical both times: {a.get('detail')}"


@case("QA-AM-061", "The same data in a different row order")
def am_061(ctx: Ctx) -> Result:
    """PSI is a function of the distribution, not of the order rows arrived
    in, so reordering must reproduce."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    if _record(ctx, vid).status_code >= 400:
        return BLOCKED, "the result could not be recorded"
    got = _replay(ctx, vid, {PSI: [list(reversed(LEFT)), list(reversed(RIGHT))]})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if not body.get("reproducible"):
        return FAIL, (f"reordering the rows broke the replay: "
                      f"{body.get('detail')}. A distribution test that "
                      f"depends on row order is not the test it claims to be")
    return PASS, "reordered and still reproduced"


@case("QA-AM-1900", "Replay with data that is not the data")
def am_1900(ctx: Ctx) -> Result:
    """The whole point. Different numbers must come back mismatched rather
    than reproduced."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    if _record(ctx, vid).status_code >= 400:
        return BLOCKED, "the result could not be recorded"
    other = [v * 3.0 + 7.0 for v in RIGHT]
    got = _replay(ctx, vid, {PSI: [LEFT, other]})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if body.get("reproducible"):
        return FAIL, "a replay over different numbers reported as reproduced"
    if not body.get("mismatched"):
        return FAIL, f"nothing was reported as mismatched: {body.get('detail')}"
    row = body["mismatched"][0]
    if row.get("stored_digest") == row.get("replayed_digest"):
        return FAIL, "the mismatch reports identical digests"
    if row.get("stored_value") is None:
        return FAIL, "the mismatch does not carry the stored value"
    return PASS, (f"mismatched: stored {row.get('stored_value')}, replayed "
                  f"{row.get('replayed_value')}")


@case("QA-AM-1901", "Replay data for a test the episode never recorded")
def am_1901(ctx: Ctx) -> Result:
    """Supplying data for a test nobody ran must not add to the count of
    things reproduced."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    if _record(ctx, vid).status_code >= 400:
        return BLOCKED, "the result could not be recorded"
    got = _replay(ctx, vid, {PSI: [LEFT, RIGHT], KS: [LEFT, RIGHT]})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if body.get("total") != 1:
        return FAIL, (f"the replay counted {body.get('total')} results when "
                      f"one was recorded; data for a test nobody ran was "
                      f"counted as a reproduction")
    return PASS, "extra data supplied, and only the recorded test counted"


@case("QA-AM-066", "Replay, conclude the episode, replay again")
def am_066(ctx: Ctx) -> Result:
    """Concluding makes results immutable. It must not make them
    unreplayable — an examiner arrives after the episode closes, never
    before."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    if _record(ctx, vid).status_code >= 400:
        return BLOCKED, "the result could not be recorded"
    before = _replay(ctx, vid, {PSI: [LEFT, RIGHT]})
    if before.status_code >= 400:
        return BLOCKED, before.text[:170]
    done = ctx.api.post(f"{V}/{vid}/conclude",
                        json={"outcome": "rejected",
                              "tier_verdict": "remains_appropriate",
                              "tier_note": "qa", "conditions": []},
                        auth=ctx.people["validator"])
    if done.status_code >= 400:
        return BLOCKED, done.text[:170]
    after = _replay(ctx, vid, {PSI: [LEFT, RIGHT]})
    if after.status_code >= 400:
        return FAIL, (f"a concluded episode cannot be replayed: "
                      f"{after.text[:130]}")
    if after.json().get("detail") != before.json().get("detail"):
        return FAIL, (f"the report changed when the episode concluded: "
                      f"{before.json().get('detail')} -> "
                      f"{after.json().get('detail')}")
    return PASS, "the same report before and after concluding"


@case("QA-AM-053", "Replay-from-storage on an episode pinning no snapshot")
def am_053(ctx: Ctx) -> Result:
    """There is nothing to re-read, and the report has to say so rather than
    reporting every test as skipped without a reason."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    if _record(ctx, vid).status_code >= 400:
        return BLOCKED, "the result could not be recorded"
    got = ctx.api.post(f"{V}/{vid}/replay-from-storage",
                       auth=ctx.people["auditor"])
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    body = got.json() or {}
    if body.get("reproducible"):
        return FAIL, ("an episode pinning no snapshot replayed from storage "
                      "as reproducible")
    data = body.get("data") or {}
    if data.get("readable") is not False:
        return FAIL, f"the report does not say the data is unreadable: {data}"
    if "snapshot" not in (data.get("detail") or ""):
        return FAIL, f"the reason does not name the missing snapshot: {data}"
    return PASS, "unreadable, and the missing snapshot is the stated reason"


@case("QA-AM-063", "Replayability over a model with no episodes")
def am_063(ctx: Ctx) -> Result:
    """Zero coverage must be reported as zero with a reason, not as an
    absence that reads like completeness."""
    name = ctx.unique("rp")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    made = _episode(ctx)
    if not made:
        return BLOCKED, "the fixture could not be built"
    got = ctx.api.get(f"{V}/{made}/replayable", auth=ctx.people["auditor"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if not (body.get("detail") or "").strip():
        return FAIL, ("the replayability report carries no statement, so a "
                      "model nobody validated is indistinguishable from one "
                      "fully covered")
    return PASS, str(body.get("detail"))[:90]
