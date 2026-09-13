"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — replaying a validation.

**A test whose data cannot be supplied is reported as skipped, never as
reproduced.** That is the whole discipline: a replay is reproducible only if
everything was checked AND matched, so a partial replay cannot round up to a
clean one. `ok = not mismatched and not skipped and total > 0` — three
conditions, and the third is what stops an episode with no results reading as
perfectly reproducible.

Replaying from storage is the unattended form: nothing is supplied by the
caller, so a mismatch is about the test rather than about who handed over
which file. An episode that pins no snapshot is a normal thing that simply
cannot be replayed that way, and that is a finding rather than an error.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

V = "/api/v1/validations"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
#: Two identical series: a PSI of exactly 0.
SAME = [float(n) for n in range(50)]


def _episode(ctx: Ctx) -> tuple:
    name = ctx.unique("rp")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    made = ctx.api.post(V, json={"urn": urn, "semver": "1.0.0",
                                 "kind": "initial",
                                 "validators": ["person/validator"]},
                        auth=ctx.people["risk"])
    return ((made.json() or {}).get("id", "") if made.status_code < 400
            else ""), urn


def _record(ctx: Ctx, vid: str, **over):
    body = {"test_key": "stability.psi", "left": SAME, "right": list(SAME)}
    body.update(over)
    return ctx.api.post(f"{V}/{vid}/results", json=body,
                        auth=ctx.people["validator"])


def _provider(ctx: Ctx):
    """The snapshot provider, which is reachable only through the replayer —
    there is no `snapshot_provider` in the application context, and looking
    for one blocks every case here on a key that never existed."""
    replayer = ctx.ui.app.state.ctx.get("replayer")
    return getattr(replayer, "storage", None) if replayer else None


def _replay(ctx: Ctx, vid: str, data: dict):
    return ctx.api.post(f"{V}/{vid}/replay", json={"data": data},
                        auth=ctx.people["risk"])


@case("QA-AM-052",
      "The stored threshold is edited in the register, then replay is run "
      "with the original data")
def am_052(ctx: Ctx) -> Result:
    """The digest covers the threshold, so editing it makes the replay
    mismatch even though the VALUE is identical. That is right: a result is
    the number and what it was judged against, and changing the second one
    changes what was concluded."""
    vid, _urn = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    if _record(ctx, vid, threshold={"max": 0.2}).status_code >= 400:
        return BLOCKED, "the result could not be recorded"
    service = ctx.ui.app.state.ctx.get("validation")
    if service is None:
        return BLOCKED, "no validation service is wired"
    rows = service.results_for(vid)
    if not rows:
        return BLOCKED, "the result is not readable"
    stored_value = rows[0]["value"]
    service.results.set({"threshold": {"max": 0.9}}, id=rows[0]["id"])
    got = _replay(ctx, vid, {"stability.psi": [SAME, list(SAME)]})
    if got.status_code >= 400:
        return BLOCKED, f"the replay answered {got.status_code}"
    body = got.json() or {}
    if body.get("reproducible"):
        return FAIL, ("the threshold was edited under a stored result and the "
                      "replay still reports it reproduced, so the digest does "
                      "not cover what the number was judged against")
    mismatched = body.get("mismatched") or []
    if not mismatched:
        return FAIL, "not reproducible and nothing is listed as mismatched"
    if mismatched[0].get("replayed_value") != stored_value:
        return FAIL, (f"the value changed too "
                      f"({stored_value} -> "
                      f"{mismatched[0].get('replayed_value')}), so this run "
                      f"does not isolate the threshold")
    return PASS, (f"mismatched with the value unchanged at {stored_value}: "
                  f"the digest covers the threshold")


@case("QA-AM-062",
      "Same data supplied with the pairing broken (both series shuffled "
      "independently)")
def am_062(ctx: Ctx) -> Result:
    """The same multiset of numbers in a different pairing is a different
    dataset. A replay that reproduced here would be checking the values and
    not the observations, and every paired test would be replayable by
    handing over the right numbers in any order."""
    vid, _urn = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    labels = [i % 2 for i in range(40)]
    scores = [i / 40.0 for i in range(40)]
    if _record(ctx, vid, test_key="discrimination.auc", left=labels,
               right=scores, threshold={"min": 0.5}).status_code >= 400:
        return BLOCKED, "the result could not be recorded"
    broken = list(reversed(scores))
    got = _replay(ctx, vid, {"discrimination.auc": [labels, broken]})
    if got.status_code >= 400:
        return BLOCKED, f"the replay answered {got.status_code}"
    body = got.json() or {}
    if body.get("reproducible"):
        return FAIL, ("the same numbers in a different pairing reproduced "
                      "exactly, so a replay checks the values and not which "
                      "score belongs to which outcome")
    if not (body.get("mismatched") or []):
        return FAIL, "not reproducible and nothing is listed as mismatched"
    return PASS, "the broken pairing is reported as mismatched"


@case("QA-AM-059", "Frame carrying both `actual` and `label` columns")
def am_059(ctx: Ctx) -> Result:
    """`actual` wins, because it comes first in `DEFAULT_LEFT`. Deterministic
    and documented in the constant — but nothing in a replay report says
    WHICH column was read, so a frame carrying both replays against one of
    them and a mismatch reads as a problem with the test."""
    provider = _provider(ctx)
    if provider is None:
        return BLOCKED, "no snapshot provider is wired"
    try:
        import pandas
    except ImportError:
        return BLOCKED, "pandas is not available to build a frame"
    frame = pandas.DataFrame({"actual": [1, 0, 1, 0],
                              "label": [0, 1, 0, 1],
                              "score": [0.9, 0.1, 0.8, 0.2]})
    series = provider.series(frame)
    if series is None:
        return BLOCKED, "the provider returned no series"
    left, _right = series
    if list(left) != [1, 0, 1, 0]:
        return FAIL, (f"the provider read {list(left)}, so 'label' won over "
                      f"'actual' — the opposite of the documented order")
    return PASS, "'actual' wins over 'label', as DEFAULT_LEFT orders them"


@case("QA-AM-060", "Frame where the label column is entirely null")
def am_060(ctx: Ctx) -> Result:
    """The pair drops to empty, so the test is SKIPPED rather than run over
    nothing. Running it would produce a number over an empty frame, and a
    replay that reported one would be the worst possible answer."""
    provider = _provider(ctx)
    if provider is None:
        return BLOCKED, "no snapshot provider is wired"
    try:
        import pandas
    except ImportError:
        return BLOCKED, "pandas is not available to build a frame"
    frame = pandas.DataFrame({"actual": [None, None, None],
                             "score": [0.9, 0.1, 0.8]})
    if provider.series(frame) is not None:
        return FAIL, ("a frame whose label column is entirely null yielded a "
                      "series, so a test would run over nothing")
    return PASS, "the pair drops to empty and the test is skipped"


@case("QA-AM-057",
      "Replay-from-storage with a slice naming a column the frame does not "
      "have")
def am_057(ctx: Ctx) -> Result:
    """A slice silently ignored is a replay of a different population, so a
    column the frame does not have yields NOTHING rather than the whole
    frame — the direction that fails safe."""
    provider = _provider(ctx)
    if provider is None:
        return BLOCKED, "no snapshot provider is wired"
    try:
        import pandas
    except ImportError:
        return BLOCKED, "pandas is not available to build a frame"
    frame = pandas.DataFrame({"actual": [1, 0, 1], "score": [0.9, 0.1, 0.8]})
    whole = provider.apply_slice(frame, None)
    if len(whole) != 3:
        return FAIL, "no slice did not return the whole frame"
    sliced = provider.apply_slice(frame, {"region": "EMEA"})
    if len(sliced) == 3:
        return FAIL, ("a slice on a column the frame does not have returned "
                      "the WHOLE frame, so the replay is of a different "
                      "population than the test was")
    if len(sliced) != 0:
        return FAIL, f"the slice returned {len(sliced)} rows"
    if provider.series(frame, {"region": "EMEA"}) is not None:
        return FAIL, "the empty slice still produced a series"
    return PASS, "an unknown slice column yields nothing, not everything"


@case("QA-AM-058", "Replay-from-storage with a slice matching zero rows")
def am_058(ctx: Ctx) -> Result:
    """A slice that matches nothing is a real slice over a real column, and
    it must be skipped for the same reason: there is nothing to compute
    over, and computing anyway would answer about a population of none."""
    provider = _provider(ctx)
    if provider is None:
        return BLOCKED, "no snapshot provider is wired"
    try:
        import pandas
    except ImportError:
        return BLOCKED, "pandas is not available to build a frame"
    frame = pandas.DataFrame({"actual": [1, 0, 1], "score": [0.9, 0.1, 0.8],
                              "region": ["US", "US", "US"]})
    if len(provider.apply_slice(frame, {"region": "US"})) != 3:
        return BLOCKED, "the matching slice does not select the rows"
    if provider.series(frame, {"region": "EMEA"}) is not None:
        return FAIL, ("a slice matching zero rows produced a series, so a "
                      "test would be replayed over a population of none")
    return PASS, "a zero-row slice is skipped rather than computed over"


@case("QA-AM-064",
      "`GET /replayable` where a snapshot row exists but its table is gone")
def am_064(ctx: Ctx) -> Result:
    """Counted in `with_snapshot` and NOT in `readable`. The two numbers say
    different things — how much was pinned, and how much can actually be
    re-read — and collapsing them would let an estate that lost its tables
    report full replay coverage."""
    provider = _provider(ctx)
    if provider is None:
        return BLOCKED, "no snapshot provider is wired"
    import time
    table = ctx.unique("no_table").replace("-", "_")
    # `as_of`, `digest` and `created_at` are NOT NULL with no default: a row
    # built from the fields this case cares about does not insert.
    provider.snapshots.add({
        "name": ctx.unique("snap"), "kind": "training", "delta_table": table,
        "delta_version": 3, "row_count": 100, "as_of": time.time(),
        "pit_verified": 0, "digest": "sha256:" + "0" * 64,
        "created_at": time.time()})
    snapshot_id = provider.snapshots.one(delta_table=table)["id"]
    report = provider.replayable([{"id": "v1", "snapshot_id": snapshot_id},
                                  {"id": "v2", "snapshot_id": None}])
    if report.get("with_snapshot") != 1:
        return FAIL, (f"the pinned episode is not counted in with_snapshot: "
                      f"{report}")
    if report.get("readable"):
        return FAIL, ("an episode whose table is gone is counted as readable, "
                      "so an estate that lost its data reports replay "
                      "coverage it does not have")
    if report.get("coverage"):
        return FAIL, f"coverage reads {report['coverage']} with nothing readable"
    return PASS, (f"with_snapshot 1, readable 0, coverage "
                  f"{report.get('coverage')}")


@case("QA-AM-055",
      "Replay-from-storage when the snapshot's table has been removed")
def am_055(ctx: Ctx) -> Result:
    """The describe has to say the table is gone rather than raising an
    unhandled error, because this is the state an estate reaches by ordinary
    housekeeping and the answer a reader needs is *a replay would be skipped
    rather than guessed at*."""
    provider = _provider(ctx)
    if provider is None:
        return BLOCKED, "no snapshot provider is wired"
    import time
    table = ctx.unique("gone_table").replace("-", "_")
    provider.snapshots.add({"name": ctx.unique("snap"), "kind": "training",
                            "delta_table": table, "delta_version": 2,
                            "row_count": 50, "as_of": time.time(),
                            "pit_verified": 0,
                            "digest": "sha256:" + "1" * 64,
                            "created_at": time.time()})
    snapshot_id = provider.snapshots.one(delta_table=table)["id"]
    described = provider.describe(snapshot_id)
    if described.get("readable"):
        return FAIL, "a snapshot whose table is gone reports readable"
    if described.get("restated"):
        return FAIL, ("a snapshot whose table is gone is reported as "
                      "restated, which says the data moved rather than went")
    if "gone" not in (described.get("detail") or "").lower():
        return FAIL, f"the detail does not say the table is gone: {described}"
    from core.validation.common import ValidationError
    try:
        provider.frame(snapshot_id)
    except ValidationError as exc:
        if "removed" not in f"{exc}" and "not in the store" not in f"{exc}":
            return FAIL, f"the frame read failed for another reason: {exc}"
        return PASS, "described as unreadable, and the frame read refuses by name"
    return FAIL, ("the frame read returned something for a table that is not "
                  "in the store")


@case("QA-AM-065",
      "`GET /replayable` on an instance with no storage provider wired")
def am_065(ctx: Ctx) -> Result:
    """A replayer built without storage can only replay from data supplied by
    the caller, and it says so rather than reporting nothing to replay — the
    two look identical on a coverage screen."""
    replayer = ctx.ui.app.state.ctx.get("replayer")
    if replayer is None:
        return BLOCKED, "no replayer is wired"
    vid, _urn = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    _record(ctx, vid)
    was, replayer.storage = replayer.storage, None
    try:
        replayer.from_storage(vid)
    except Exception as exc:
        if "storage provider" not in f"{exc}":
            return FAIL, f"refused for another reason: {exc}"
        return PASS, f"refused: {f'{exc}'[:90]}"
    finally:
        replayer.storage = was
    return FAIL, ("a replayer with no storage provider replayed from storage "
                  "anyway, so an instance that cannot re-read anything "
                  "reports a replay")


@case("QA-AM-4750", "A replay of an episode with no results at all")
def am_4750(ctx: Ctx) -> Result:
    """`total > 0` is the third condition on `reproducible`, and it is the
    one that matters most: without it an episode that examined nothing would
    report `reproducible: true` — perfectly replayable, because there was
    nothing to replay."""
    vid, _urn = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _replay(ctx, vid, {})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' — there is nothing to replay"
    body = got.json() or {}
    if body.get("reproducible"):
        return FAIL, ("an episode with no recorded results reports "
                      "`reproducible: true`, so a validation that examined "
                      "nothing is perfectly reproducible")
    if body.get("total") != 0:
        return FAIL, f"the replay counts {body.get('total')} result(s)"
    if "no results" not in (body.get("detail") or ""):
        return FAIL, f"the detail does not say why: {body.get('detail')}"
    return PASS, "reproducible false, total 0, 'no results to replay'"
