"""
Cursor pagination (§18.1 conventions): keyset pages over any list that can grow.

A ``Listing`` says what a list is — its table, the sorts it offers, its filters
and search, a per-row ``keep`` (authorization, where rows are filtered one by
one) and an ``enrich`` (or a bulk ``enrich_many``) applied to the rows of one
page only. The pager walks the table in keyset order (the sort column, then the
primary key as tiebreak, both in the sort's direction), drops the rows ``keep``
refuses, and stops as soon as it holds one row more than the page: that extra
row is how it knows a next page exists, without counting.

A cursor is opaque to callers and bound to its query. It carries the last row's
(sort value, primary key) and a digest of the table, sort, filters and search it
was issued for, and it is signed with the platform's secret. A tampered cursor,
or one replayed against a different query, is refused as ``InvalidCursor``
(400) rather than silently answering some other page.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from maya.core.errors import InvalidCursor, ValidationFailed

DEFAULT_PAGE = 100
MAX_PAGE = 1000
_BATCH = 64


@dataclass
class Listing:
    table: str
    sorts: dict[str, str]  # public sort name -> column ("name", "-created_at")
    default: str
    filters: dict[str, Any] = field(default_factory=dict)
    search: tuple[list[str], str] | None = None
    keep: Callable[[Any, dict[str, Any]], bool] | None = None
    enrich: Callable[[Any, dict[str, Any]], dict[str, Any]] | None = None
    enrich_many: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]] | None = None
    scope: dict[str, Any] = field(default_factory=dict)  # conditions ``keep`` applies

    def finish(self, uow: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The rows as callers see them: ``enrich_many`` in bulk, else ``enrich`` per row."""
        if self.enrich_many:
            return self.enrich_many(uow, rows)
        return [self.enrich(uow, r) for r in rows] if self.enrich else rows

    def collect(self, uow: Any, sort: str | None = None) -> list[dict[str, Any]]:
        """Every kept row, enriched, in the sort's order: the unpaged list."""
        order = self.sorts[sort or self.default]
        pk = uow.repo(self.table).model.__mapper__.primary_key[0].key
        tiebreak = ("-" if order.startswith("-") else "") + pk
        rows = uow.repo(self.table).list(
            order_by=[order, tiebreak], search=self.search, **self.filters
        )
        return self.finish(uow, [r for r in rows if self.keep is None or self.keep(uow, r)])


def _enc(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, dt.date):
        return {"$d": value.isoformat()}
    return value


def _dec(value: Any) -> Any:
    if isinstance(value, dict) and "$dt" in value:
        return dt.datetime.fromisoformat(value["$dt"])
    if isinstance(value, dict) and "$d" in value:
        return dt.date.fromisoformat(value["$d"])
    return value


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Pager:
    def __init__(self, secret: str) -> None:
        self._key = hashlib.sha256(b"maya-cursor:" + secret.encode()).digest()

    @staticmethod
    def shape(listing: Listing, sort: str) -> str:
        """The query a cursor belongs to: table, sort, filters and search, as a digest."""
        body = json.dumps(
            {
                "t": listing.table,
                "s": sort,
                "f": listing.filters,
                "c": listing.scope,
                "q": list(listing.search) if listing.search else None,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(body.encode()).hexdigest()[:24]

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._key, payload.encode(), hashlib.sha256).digest()[:18])

    def encode(self, shape: str, key: tuple[Any, Any]) -> str:
        payload = _b64(
            json.dumps(
                {"h": shape, "k": [_enc(key[0]), _enc(key[1])]}, separators=(",", ":")
            ).encode()
        )
        return f"{payload}.{self._sign(payload)}"

    def decode(self, token: str, shape: str) -> tuple[Any, Any]:
        payload, _, sig = token.partition(".")
        if not payload or not hmac.compare_digest(sig, self._sign(payload)):
            raise InvalidCursor(
                "The cursor is not one MAYA issued (it was altered or "
                "truncated); start again without a cursor"
            )
        try:
            body = json.loads(_unb64(payload))
            if body["h"] != shape:
                raise InvalidCursor(
                    "The cursor belongs to a different query (sort, filter or "
                    "search changed); start again without a cursor"
                )
            value, key = body["k"]
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidCursor("The cursor is malformed; start again without a cursor") from exc
        return _dec(value), _dec(key)

    def page(
        self,
        uow: Any,
        listing: Listing,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        size = DEFAULT_PAGE if page_size is None else int(page_size)
        if not 1 <= size <= MAX_PAGE:
            raise ValidationFailed(f"page_size must be between 1 and {MAX_PAGE}", page_size=size)
        sort = sort or listing.default
        if sort not in listing.sorts:
            raise ValidationFailed(f"sort must be one of {', '.join(listing.sorts)}", sort=sort)
        order = listing.sorts[sort]
        column = order.lstrip("-")
        shape = self.shape(listing, sort)
        after = self.decode(cursor, shape) if cursor else None
        repo = uow.repo(listing.table)
        pk = repo.model.__mapper__.primary_key[0].key
        kept: list[dict[str, Any]] = []
        last: tuple[Any, Any] | None = None
        more = False
        batch = max(size + 1, _BATCH)
        while not more:
            rows = repo.keyset(
                order, after=after, limit=batch, search=listing.search, **listing.filters
            )
            for row in rows:
                after = (row[column], row[pk])
                if listing.keep is not None and not listing.keep(uow, row):
                    continue
                if len(kept) == size:
                    more = True
                    break
                kept.append(row)
                last = after
            if len(rows) < batch:
                break
        items = listing.finish(uow, kept)
        out: dict[str, Any] = {
            "items": items,
            "page_size": size,
            "sort": sort,
            "next_cursor": self.encode(shape, last) if more and last else None,
        }
        if total:
            counter = getattr(listing.keep, "count", None)
            out["total"] = (
                repo.count(search=listing.search, **listing.filters)
                if listing.keep is None
                else counter(uow, listing.table, listing.search, listing.filters)
                if counter is not None
                else sum(1 for _ in _kept_all(uow, listing))
            )
        return out


def _kept_all(uow: Any, listing: Listing) -> Any:
    repo = uow.repo(listing.table)
    columns = [
        c for c in ("id", "namespace_id", "owner_id") if c in repo.model.__mapper__.columns
    ]  # all ``keep`` ever reads
    for row in repo.slim(columns, search=listing.search, **listing.filters):
        if listing.keep is None or listing.keep(uow, row):
            yield row


def pager(platform: Any) -> Pager:
    """The platform's pager, keyed by the same secret that signs sessions."""
    cached = getattr(platform, "_pager", None)
    if cached is None:
        cached = Pager(platform.settings.session_secret())
        platform._pager = cached
    return cached


def run_page(
    platform: Any,
    build: Callable[[Any], Listing],
    *,
    page_size: int | None = None,
    cursor: str | None = None,
    sort: str | None = None,
    total: bool = False,
) -> dict[str, Any]:
    """One page of the listing ``build(uow)`` describes, in one unit of work."""
    with platform.uow() as uow:
        return pager(platform).page(
            uow, build(uow), page_size=page_size, cursor=cursor, sort=sort, total=total
        )
