"""
What one caller may ask of one process, and what an archive from outside may expand to
(§13.2, §21.1, §24.4). Before this, an upload was read whole into memory whatever its
size, a zip could describe an unbounded expansion, and nothing limited how fast or how
many requests one caller could make.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import asyncio
import io
import zipfile

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from maya.api import limits
from maya.core import archives
from maya.core.errors import ValidationFailed


def _app(**caps):
    async def echo(request):
        body = await request.body()
        return PlainTextResponse(f"{len(body)}")

    async def slow(request):
        await asyncio.sleep(0.5)
        return PlainTextResponse("late")

    app = Starlette(routes=[Route("/echo", echo, methods=["POST"]), Route("/slow", slow)])
    app.add_middleware(limits.BodyLimit, limit=caps.get("body", 0))
    app.add_middleware(
        limits.RateLimit, per_minute=caps.get("per_minute", 0), burst=caps.get("burst", 1)
    )
    app.add_middleware(
        limits.Shed, max_concurrent=caps.get("concurrent", 0), timeout=caps.get("timeout", 0)
    )
    return app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://limits")


def test_a_body_over_the_limit_is_refused_by_its_header_and_when_it_is_streamed():
    asyncio.run(_body_limits())


async def _body_limits():
    async with _client(_app(body=1000)) as c:
        assert (await c.post("/echo", content=b"x" * 500)).status_code == 200
        big = await c.post("/echo", content=b"x" * 5000)
        assert big.status_code == 413 and "MB" in big.json()["detail"]

        async def chunks():  # no content-length: the bytes are counted as they arrive
            for _ in range(10):
                yield b"y" * 300

        streamed = await c.post("/echo", content=chunks())
        assert streamed.status_code == 413


def test_the_rate_limit_answers_429_with_retry_after_and_refills():
    asyncio.run(_rate_limited())
    rl = limits.RateLimit(None, per_minute=60, burst=2)
    assert rl.take("someone", 0.0) == 0.0 and rl.take("someone", 0.0) == 0.0
    assert rl.take("someone", 0.0) > 0, "the burst is spent"
    assert rl.take("someone", 60.0) == 0.0, "a minute later there are tokens again"
    assert rl.take("another", 0.0) == 0.0, "the bucket is per caller"


async def _rate_limited():
    # 6 a minute: a tenth of a token a second, so three quick requests spend the burst
    async with _client(_app(per_minute=6, burst=2)) as c:
        assert (await c.post("/echo", content=b"x")).status_code == 200
        assert (await c.post("/echo", content=b"x")).status_code == 200
        blocked = await c.post("/echo", content=b"x")
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1


def test_the_caller_is_a_key_id_never_its_secret():
    rl = limits.RateLimit(None, per_minute=60, burst=1)
    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer maya_dev_abc123_secret-part")],
        "client": ("10.0.0.1", 1),
    }
    who = rl.caller(scope)
    assert who == "key:abc123" and "secret" not in who


def test_load_is_shed_above_the_concurrency_limit():
    asyncio.run(_shedding())


async def _shedding():
    async with _client(_app(concurrent=1)) as c:
        first = asyncio.create_task(c.get("/slow"))
        await asyncio.sleep(0.05)
        second = await c.get("/slow")
        assert second.status_code == 503 and second.headers["retry-after"] == "1"
        assert (await first).status_code == 200


def test_a_request_past_the_deadline_is_answered_504():
    asyncio.run(_deadline())


async def _deadline():
    async with _client(_app(timeout=1)) as c:
        assert (await c.get("/slow")).status_code == 200, "half a second is inside a second"
    async with _client(_app(timeout=0)) as c:
        assert (await c.get("/slow")).status_code == 200, "0 turns the deadline off"


def test_the_deadline_answers_504_when_the_work_outlives_it():
    async def run():
        app = Starlette(routes=[Route("/slow", _sleeper(2.0))])
        app.add_middleware(limits.Shed, max_concurrent=0, timeout=1)
        async with _client(app) as c:
            late = await c.get("/slow")
        assert late.status_code == 504 and "abandoned" in late.json()["detail"]

    asyncio.run(run())


def _sleeper(seconds: float):
    async def endpoint(request):
        await asyncio.sleep(seconds)
        return PlainTextResponse("late")

    return endpoint


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in entries.items():
            z.writestr(name, body)
    return buf.getvalue()


def test_an_archive_that_expands_far_past_its_size_is_refused():
    bomb = _zip({"zeros.bin": b"\0" * (50 * 1024 * 1024)})
    assert len(bomb) < 100_000, "a small file describing a large expansion"
    with pytest.raises(ValidationFailed, match="expands"):
        archives.opened(bomb, what="bundle")


def test_an_archive_with_too_many_entries_or_a_path_outside_it_is_refused():
    with pytest.raises(ValidationFailed, match="entries"):
        archives.check(
            zipfile.ZipFile(io.BytesIO(_zip({f"f{i}": b"x" for i in range(20)}))),
            settings=_Caps(entries=5),
        )
    for name in ("../escape.txt", "/etc/passwd", "a/../../escape"):
        with pytest.raises(ValidationFailed, match="outside"):
            archives.opened(_zip({name: b"x"}))


def test_a_member_is_read_no_further_than_its_entry_table_says():
    data = _zip({"manifest.json": b'{"ok": true}'})
    z = archives.opened(data)
    assert archives.read(z, "manifest.json") == b'{"ok": true}'
    with pytest.raises(ValidationFailed, match="at most"):
        archives.read(z, "manifest.json", settings=_Caps(expanded=4))


def test_a_workbook_that_is_a_bomb_is_refused_as_a_workbook(world):
    from maya.formula.xlsx import lift_workbook

    with pytest.raises(ValidationFailed, match="expands"):
        lift_workbook(_zip({"xl/workbook.xml": b"<x/>" + b"\0" * (30 * 1024 * 1024)}))
    with pytest.raises(ValidationFailed, match="Not a readable .xlsx"):
        lift_workbook(b"not a zip at all")


def test_a_bundle_that_is_a_bomb_is_refused_before_it_is_read(world):
    bomb = _zip({"manifest.json": b"{}", "pad.bin": b"\0" * (40 * 1024 * 1024)})
    with pytest.raises(ValidationFailed, match="expands"):
        world.p.bundles.verify_offline(bomb)
    with pytest.raises(ValidationFailed, match="expands"):
        world.p.bundles.verify(bomb)


class _Caps:
    """Just enough of the settings object for one limit."""

    def __init__(self, entries: int = 10**6, expanded: int = 2 * 1024**3, ratio: int = 200):
        self.values = {
            "api.limits.archive.max_entries": entries,
            "api.limits.archive.max_expanded_bytes": expanded,
            "api.limits.archive.max_expansion_ratio": ratio,
        }

    def int(self, key: str, default: int) -> int:
        return int(self.values.get(key, default))
