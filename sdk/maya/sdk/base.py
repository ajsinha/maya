"""
The SDK's resource base: the endpoint registry every method is filed in, the paging
helpers, and the reference-to-path helper.

Its own module so that resources defined outside ``resources.py`` (which is at the file
size gate's limit) can share it without an import cycle.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Callable

from maya.sdk.transport import AsyncTransport, Call, seg, split_ref

ENDPOINTS: dict[tuple[str, str], str] = {}


def endpoint(method: str, path: str) -> Callable[[Any], Any]:
    def deco(fn: Any) -> Any:
        ENDPOINTS[(method, path)] = f"{fn.__qualname__}"
        fn.__maya_endpoint__ = (method, path)
        return fn

    return deco


PAGE_SIZE = 100


class _Resource:
    def __init__(self, transport: Any) -> None:
        self._t = transport

    def _c(self, method: str, path: str, **kw: Any) -> Any:
        return self._t.call(Call(method, path, **kw))

    # -- cursor paging (opt-in on the list endpoints) ----------------------------------
    def _page(
        self,
        path: str,
        params: dict[str, Any],
        page_size: int = PAGE_SIZE,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> Any:
        """One page: ``{items, next_cursor, page_size, sort[, total]}``."""
        return self._c(
            "GET",
            path,
            params={
                **params,
                "page_size": page_size,
                "cursor": cursor,
                "sort": sort,
                "total": total or None,
            },
        )

    def _iter(
        self, path: str, params: dict[str, Any], page_size: int = PAGE_SIZE, sort: str | None = None
    ) -> Any:
        """Every item, fetched a page at a time by following ``next_cursor``.

        A generator on a sync client, an async generator on an async one."""
        if isinstance(self._t, AsyncTransport):
            return self._aiter(path, params, page_size, sort)
        return self._siter(path, params, page_size, sort)

    def _siter(self, path: str, params: dict[str, Any], page_size: int, sort: str | None) -> Any:
        cursor = None
        while True:
            page = self._page(path, params, page_size, cursor, sort)
            yield from page["items"]
            cursor = page["next_cursor"]
            if not cursor:
                return

    async def _aiter(
        self, path: str, params: dict[str, Any], page_size: int, sort: str | None
    ) -> Any:
        cursor = None
        while True:
            page = await self._page(path, params, page_size, cursor, sort)
            for item in page["items"]:
                yield item
            cursor = page["next_cursor"]
            if not cursor:
                return


def _nn(ref: str, kind: str) -> str:
    ns, name = split_ref(ref, kind)
    return f"{seg(ns)}/{seg(name)}"
