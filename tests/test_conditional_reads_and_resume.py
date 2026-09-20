"""
The promise this file holds: a read MAYA has already answered costs a round trip and not a
body, an edit written against a definition that has since moved is refused rather than
applied over someone else's, and a pin download of any size survives a dropped connection.

Concretely (§18.1, §18.2.3, §18.2.5): catalog listings and definition reads carry an
``ETag`` and answer ``If-None-Match`` with 304; the SDK holds the last body against that
validator and re-serves it only when MAYA says 304; a draft edit sends the ``ETag`` of the
read it was written against as ``If-Match`` and gets MAYA's own ``ConflictError`` when the
object moved; the download endpoints advertise ``Accept-Ranges`` and serve a ``Range``,
guarded by ``If-Range`` so two halves of two different downloads are never stitched
together; and the sealed-pin cache resumes from the part file it already has, ending at the
same checksum, throwing a part that fails it away rather than caching it.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest
from starlette.testclient import TestClient

from maya.api.deps import etag
from maya.core.errors import ConflictError, ValidationFailed
from maya.sdk import Client
from maya.sdk.cache import PinCache
from maya.sdk.transport import validator_path
from maya.server import build_app
from tests.conftest import PASSWORD, World, approved_feature, build_platform, price_csv

PIN = "cond/cond_px#q1/2026-01-04"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    platform = build_platform()
    platform.jobs.start()
    w = World(platform)
    platform.access.create_namespace(w.admin, name="cond", preset="standard")
    approved_feature(w, "cond_px", price_csv(40), ns="cond")
    platform.features.pin(
        w.mick, "cond/cond_px", version_no=1, pin_name="q1", as_of=dt.date(2026, 1, 4)
    )
    platform.jobs.drain()
    app = build_app(platform)
    anon = Client(app=app, channel="sdk")
    tokens = {u: anon.auth.login(u, PASSWORD)["token"] for u in ("mick", "dana")}
    client = Client(app=app, token=tokens["mick"], channel="sdk")
    client.cache = PinCache(tmp_path_factory.mktemp("cond-cache"))
    yield {"app": app, "platform": platform, "client": client, "tokens": tokens, "w": w}
    platform.shutdown()


def http(world, user: str = "mick") -> TestClient:
    """A bare HTTP client, so a test can set a conditional header itself."""
    client = TestClient(world["app"], base_url="http://inproc/api/v1")
    client.headers["Authorization"] = f"Bearer {world['tokens'][user]}"
    return client


def watched(client: Client) -> list[int]:
    """Every status code this client's transport sees from here on."""
    seen: list[int] = []
    inner = client._transport.client
    original = inner.request

    def spy(*args, **kw):
        response = original(*args, **kw)
        seen.append(response.status_code)
        return response

    inner.request = spy
    return seen


def sent(client: Client) -> list[dict[str, str]]:
    """The headers this client's transport sends from here on, for the ones that matter."""
    out: list[dict[str, str]] = []
    inner = client._transport.client
    original = inner.stream

    def spy(*args, **kw):
        out.append(dict(kw.get("headers") or {}))
        return original(*args, **kw)

    inner.stream = spy
    return out


# -- conditional reads -------------------------------------------------------------------
def test_a_listing_answers_if_none_match_with_304_and_no_body(world):
    api = http(world)
    first = api.get("/features", params={"namespace": "cond"})
    assert first.status_code == 200 and first.headers["etag"] and first.content
    again = api.get(
        "/features",
        params={"namespace": "cond"},
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert again.status_code == 304 and not again.content
    assert again.headers["etag"] == first.headers["etag"]


def test_a_listing_that_changed_is_sent_again(world):
    api = http(world)
    tag = api.get("/features", params={"namespace": "cond"}).headers["etag"]
    w = world["w"]
    w.p.features.create(w.dana, namespace="cond", name="cond_second", definition=_px_def())
    after = api.get("/features", params={"namespace": "cond"}, headers={"If-None-Match": tag})
    assert after.status_code == 200, "a listing that gained a feature is not 304"
    assert after.headers["etag"] != tag


def test_the_catalog_browse_and_a_definition_read_both_carry_a_validator(world):
    api = http(world)
    for path, params in (
        ("/catalog/browse", {"type": "feature", "namespace": "cond"}),
        ("/features/cond/cond_px", {}),
        ("/featuresets", {}),
        ("/models", {}),
    ):
        first = api.get(path, params=params)
        assert first.status_code == 200 and first.headers.get("etag"), path
        again = api.get(path, params=params, headers={"If-None-Match": first.headers["etag"]})
        assert again.status_code == 304 and not again.content, path


def test_the_sdk_serves_an_unchanged_read_from_what_it_already_holds(world):
    client = world["client"]
    client.reads.clear()
    seen = watched(client)
    first = client.features.get("cond/cond_px")
    second = client.features.get("cond/cond_px")
    assert seen == [200, 304], "the second read cost a round trip and no body"
    assert second == first, "and returned the same answer"
    assert client.reads.stats()["reads"] >= 1
    second["name"] = "edited"
    assert client.features.get("cond/cond_px")["name"] == "cond_px", "a copy, not the cache"


def test_a_body_too_large_to_be_worth_holding_is_not_held(world):
    client = world["client"]
    client.reads.clear()
    keep, client.reads.body_limit = client.reads.body_limit, 1
    try:
        client.features.get("cond/cond_px")
        assert client.reads.stats()["reads"] == 0, "the payload was not worth the memory"
    finally:
        client.reads.body_limit = keep
    client.features.get("cond/cond_px")
    assert client.reads.stats()["reads"] == 1


def test_a_pin_is_still_never_served_from_the_read_cache(world):
    client = world["client"]
    client.reads.clear()
    client.features.download(PIN)
    assert client.reads.stats()["reads"] == 0, "bytes are the pin cache's business, sealed only"


# -- conditional writes ------------------------------------------------------------------
def test_a_draft_edit_written_against_a_definition_that_moved_is_refused(world):
    ref = approved_feature(world["w"], "cond_race", price_csv(4), ns="cond")
    one = Client(app=world["app"], token=world["tokens"]["dana"], channel="sdk")
    two = Client(app=world["app"], token=world["tokens"]["dana"], channel="sdk")
    one.features.new_draft(ref)
    before = one.features.get(ref)
    assert two.features.get(ref) == before, "both read the same feature"
    two.features.update_draft(ref, _px_def(), description="the other designer got there first")
    with pytest.raises(ConflictError, match="changed since you read it"):
        one.features.update_draft(ref, _px_def())


def test_a_write_by_a_client_that_never_read_the_object_carries_nothing_to_match(world):
    ref = approved_feature(world["w"], "cond_blind", price_csv(4), ns="cond")
    fresh = Client(app=world["app"], token=world["tokens"]["dana"], channel="sdk")
    fresh.features.new_draft(ref)
    fresh.reads.clear()
    row = fresh.features.update_draft(ref, _px_def())
    assert row["state"] == "draft", "with no read behind it there is no version to claim"


def test_two_edits_in_a_row_are_possible(world):
    """A client that sends the precondition for you has to maintain it for you.

    The validator a guarded write consumes describes the state *before* that write, so
    holding on to it would make the next write send a precondition certain to fail: two
    edits in a row would be impossible without an intervening read, which is a trap and not
    a safeguard. It is dropped instead, so the second write carries nothing to match — the
    honest position, since the client holds no read of the new state — while a genuine
    conflict with somebody else's change is still caught, as the test above shows."""
    ref = approved_feature(world["w"], "cond_twice", price_csv(4), ns="cond")
    client = Client(app=world["app"], token=world["tokens"]["dana"], channel="sdk")
    client.features.new_draft(ref)
    client.features.get(ref)  # now the client holds a validator
    client.features.update_draft(ref, _px_def(), description="first edit")
    client.features.update_draft(ref, _px_def(), description="second edit")
    assert client.features.get(ref)["description"] == "second edit"


def test_only_an_open_draft_takes_if_match(world):
    """Pins, warrants, parameter sets and audit rows are appended once and then immutable:
    there is no overwrite for an If-Match to prevent, so none of them offers one."""
    doc = world["app"].openapi()
    guarded = {
        (method.upper(), path)
        for path, ops in doc["paths"].items()
        for method, op in ops.items()
        if any(p.get("name", "").lower() == "if-match" for p in op.get("parameters") or [])
    }
    assert guarded == {
        ("PUT", "/api/v1/features/{namespace}/{name}/draft"),
        ("PUT", "/api/v1/featuresets/{namespace}/{name}/draft"),
        ("PUT", "/api/v1/models/{namespace}/{name}/draft"),
    }


# -- ranged, resumable downloads ---------------------------------------------------------
def test_a_download_advertises_ranges_and_serves_one(world):
    api = http(world)
    whole = api.get("/feature-data", params={"ref": PIN})
    assert whole.status_code == 200 and whole.headers["accept-ranges"] == "bytes"
    total = len(whole.content)
    part = api.get("/feature-data", params={"ref": PIN}, headers={"Range": f"bytes={total // 2}-"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes {total // 2}-{total - 1}/{total}"
    assert part.content == whole.content[total // 2 :]
    head = api.get("/feature-data", params={"ref": PIN}, headers={"Range": "bytes=0-9"})
    assert head.status_code == 206 and head.content == whole.content[:10]
    tail = api.get("/feature-data", params={"ref": PIN}, headers={"Range": "bytes=-8"})
    assert tail.status_code == 206 and tail.content == whole.content[-8:]


def test_a_range_past_the_end_is_416_and_a_range_maya_cannot_read_is_ignored(world):
    api = http(world)
    total = len(api.get("/feature-data", params={"ref": PIN}).content)
    over = api.get("/feature-data", params={"ref": PIN}, headers={"Range": f"bytes={total}-"})
    assert over.status_code == 416 and over.headers["content-range"] == f"bytes */{total}"
    odd = api.get("/feature-data", params={"ref": PIN}, headers={"Range": "rows=1-2"})
    assert odd.status_code == 200 and len(odd.content) == total


def test_an_if_range_that_no_longer_matches_sends_the_whole_object(world):
    api = http(world)
    whole = api.get("/feature-data", params={"ref": PIN})
    total = len(whole.content)
    moved = api.get(
        "/feature-data",
        params={"ref": PIN},
        headers={"Range": f"bytes={total // 2}-", "If-Range": '"not-this-object"'},
    )
    assert moved.status_code == 200 and len(moved.content) == total
    same = api.get(
        "/feature-data",
        params={"ref": PIN},
        headers={"Range": f"bytes={total // 2}-", "If-Range": whole.headers["etag"]},
    )
    assert same.status_code == 206


def test_an_interrupted_download_continues_instead_of_starting_again(world, tmp_path):
    client = world["client"]
    target = tmp_path / "pin.parquet"
    full = client.features.download(PIN, to=target)
    whole = target.read_bytes()
    assert full["status"] == 200 and full["resumed_from"] == 0 and full["bytes"] == len(whole)
    half = len(whole) // 2
    target.write_bytes(whole[:half])
    validator_path(target).write_text(full["etag"])
    resumed = client.features.download(PIN, to=target)
    assert resumed["status"] == 206 and resumed["resumed_from"] == half
    assert resumed["bytes"] == len(whole) and target.read_bytes() == whole


def test_a_part_without_its_validator_is_downloaded_again(world, tmp_path):
    client = world["client"]
    target = tmp_path / "unproven.parquet"
    whole = client.features.download(PIN, to=target)["bytes"]
    target.write_bytes(target.read_bytes()[: whole // 2])
    validator_path(target).unlink()
    again = client.features.download(PIN, to=target)
    assert again["status"] == 200 and again["resumed_from"] == 0
    assert again["bytes"] == whole, "a part that cannot be proved to be a part is not resumed"


# -- the sealed-pin cache, resumed -------------------------------------------------------
def _cached(cache: PinCache):
    return [p for p in cache.directory.rglob("*") if p.is_file() and p.suffix not in (".sha256",)]


def test_the_pin_cache_resumes_a_part_and_ends_at_the_same_verification(world):
    client, cache = world["client"], world["client"].cache
    pin = _sealed_pin(client)
    cache.clear()
    table = pin.to_arrow()
    entry = _cached(cache)[0]
    whole = entry.read_bytes()
    half = len(whole) // 2

    cache.clear()
    part = entry.with_suffix(".part")
    part.write_bytes(whole[:half])
    validator_path(part).write_text(etag(whole))
    headers = sent(client)
    again = pin.to_arrow()

    assert again.equals(table), "a resumed download is the same pin"
    assert any(h.get("Range") == f"bytes={half}-" for h in headers), "only the rest was asked for"
    assert _cached(cache) == [entry], "and the whole of it is cached, with no part left over"
    assert not validator_path(part).exists()


def test_a_part_that_fails_the_checksum_is_discarded_rather_than_cached(world):
    client, cache = world["client"], world["client"].cache
    pin = _sealed_pin(client)
    cache.clear()
    pin.to_arrow()
    entry = _cached(cache)[0]
    whole = entry.read_bytes()

    cache.clear()
    part = entry.with_suffix(".part")
    part.write_bytes(b"\x00" * (len(whole) // 2))  # the right length, the wrong bytes
    validator_path(part).write_text(etag(whole))
    with pytest.raises(ValidationFailed, match="not the pin's bytes"):
        pin.to_arrow()
    assert not part.exists() and not validator_path(part).exists()
    assert _cached(cache) == [], "nothing that failed verification was kept"
    assert pin.to_arrow().num_rows > 0, "and the next attempt starts clean"


# -- helpers -----------------------------------------------------------------------------
def _px_def() -> dict:
    from tests.conftest import PX_DEF

    return dict(PX_DEF)


def _sealed_pin(client: Client):
    return next(p for p in client.feature("cond/cond_px").pins() if p["state"] == "sealed")
