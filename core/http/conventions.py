"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Three conventions a long-lived API needs, and the reasons they are not cosmetic.

`ETag`/`If-Match` and `Idempotency-Key` were built first, in
`core/concurrency/`, because they are about **correctness under retry and
concurrency**. These three are about something slower and just as damaging:
what happens to a governance API over the years somebody depends on it.

## Keyset cursors, for the lists offsets are wrong for

`core/domain/paging.py` already pages every ordinary listing, with offsets, and
its argument for them is right *for what it covers*: a governance register is
read by people who want page four, and an offset is what says "page four". This
module does not replace it and the two are not in competition.

What an offset cannot do is page a list that **grows at the head while somebody
walks it**. The discovery queue is the case — a scanner posts candidates while
a triager works down them — and there the failure is silent. A candidate
arriving above your position shifts everything down by one, page 2 starts where
page 1 ended plus one, and you **skip a row**. Nothing errors. You receive a
complete-looking queue with a hole in it, and the hole is a model nobody
triaged.

A keyset cursor names *the last row seen* rather than a position, so a write
above it changes nothing. The cursor is opaque and carries the sort it was
issued under, because a cursor from one ordering resumed under another is a
silently different query — and the caller cannot tell.

So the rule is: **offsets where a human wants page four, cursors where a
machine is draining a queue that is being filled.** Stating which is which is
the part that matters; either one applied to the other case is a defect that
produces plausible answers.

## Field projection, because a caller should not have to receive everything

`?fields=urn,tier,status` over a listing. Small and worth having for one
reason: the alternative a caller reaches for is a second, narrower endpoint,
and a second endpoint is a second answer to one question that can disagree with
the first.

**What it will not do is hide a refusal.** The projection runs over rows a
caller was already entitled to see, and never removes the fields that say a
result is partial — `detail`, `gaps`, `not_projected` and their kin are always
kept. A response that looked complete because somebody projected away the
sentence saying it was not is the exact failure this codebase spends most of its
effort avoiding.

## Sunset, because an endpoint that disappears without warning is an outage

RFC 8594. An endpoint on its way out answers with `Sunset: <date>` and a `Link`
to what replaced it, for as long as it still works. Two things make this a
governance concern rather than a nicety.

An integration built against a MAYA endpoint is often a **control** — a CI gate,
a nightly reconciliation, an export that feeds a regulatory return. When one of
those stops, the thing that stops is a control, and the firm's first signal is
usually that the control has been silently absent for a month.

And a deprecation that lives only in a release note is one nobody reads. The
header reaches the machine that is actually calling, which is the only place the
warning can arrive in time.
"""
from __future__ import annotations

import base64
import binascii
import json
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

from core.log import get_logger

logger = get_logger(__name__)

#: The query parameter, and the fields no projection removes. Every one of them
#: is how an answer says it is incomplete, and an answer that can hide its own
#: incompleteness is worse than a short one.
FIELDS = "fields"
ALWAYS_KEPT = frozenset({
    "detail", "gaps", "not_projected", "why", "why_not", "remediation",
    "coverage", "unavailable", "partial", "refused", "warning", "limits",
    "must_still_be_established", "do_not_read_as", "cannot_check",
})

#: How long a cursor is honoured. Bounded because the sort it encodes is a fact
#: about the query that issued it, and a caller resuming a week-old walk of a
#: register that has moved is not resuming anything.
CURSOR_TTL = 3600.0

MAX_PAGE = 1000


class CursorError(ValueError):
    """A cursor that cannot be honoured. Carries the platform's three parts."""

    def __init__(self, code: str, detail: str, remediation: str):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


class Cursor:
    """An opaque marker for *the last row seen*, not for a position.

    It carries the ordering it was issued under and the key value it stopped
    at. Both are checked on resume: a cursor from one ordering replayed under
    another is a different query producing a plausible answer, and the caller
    has no way to notice.
    """

    __slots__ = ("after", "desc", "issued_at", "order")

    def __init__(self, order: str, desc: bool, after: Any,
                 issued_at: Optional[float] = None):
        self.order, self.desc, self.after = order, desc, after
        self.issued_at = issued_at if issued_at is not None else time.time()

    def encode(self) -> str:
        """Opaque on purpose.

        Not encryption and not pretending to be: base64 is trivially readable
        and that is fine, because the cursor holds nothing a caller is not
        entitled to. What opacity buys is that nobody builds a client that
        *constructs* one — a hand-built cursor is a client depending on an
        internal ordering, which is then something that can never change.
        """
        payload = json.dumps({"o": self.order, "d": self.desc,
                              "a": self.after, "t": round(self.issued_at, 3)},
                             separators=(",", ":"), sort_keys=True)
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")

    @classmethod
    def decode(cls, token: str, *, order: str, desc: bool,
               now: Optional[float] = None) -> "Cursor":
        """Read one back, refusing the three ways it can be wrong."""
        try:
            raw = base64.urlsafe_b64decode(token.encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
            logger.warning("undecodable cursor rejected: %s", exc)
            raise CursorError(
                "cursor_malformed",
                "this cursor cannot be read",
                "drop it and start the listing again. A cursor is issued by "
                "this platform and is not meant to be constructed — a "
                "hand-built one is a client depending on an internal ordering, "
                "which is then an ordering that can never change") from exc
        if payload.get("o") != order or bool(payload.get("d")) != desc:
            raise CursorError(
                "cursor_ordering_changed",
                f"this cursor was issued for an ordering of "
                f"{payload.get('o')!r} and the request asks for {order!r}",
                "resume with the ordering the cursor was issued under, or "
                "start again. Replaying a cursor under a different sort is a "
                "different query that produces a plausible answer, and nothing "
                "in the result would show it")
        moment = now if now is not None else time.time()
        if moment - float(payload.get("t") or 0) > CURSOR_TTL:
            raise CursorError(
                "cursor_expired",
                "this cursor is older than the window it is honoured for",
                "start the listing again. The register has moved underneath "
                "it, and resuming a walk of a register that has moved is not "
                "resuming anything")
        return cls(order, desc, payload.get("a"), float(payload.get("t") or 0))


def page(rows: Sequence[Dict[str, Any]], *, order: str, desc: bool = False,
         limit: int = 100, cursor: Optional[str] = None,
         now: Optional[float] = None) -> Dict[str, Any]:
    """One page of an ordered listing, and the cursor to continue it.

    **Why this pages in Python rather than in SQL.** It is the honest shape for
    what the repositories currently do — `many()` returns a list — and pretending
    otherwise would be a paging API whose guarantee is a lie at the layer below.
    What it buys even so is the *contract*: a caller that walks with cursors is
    a caller whose walk keeps its guarantee the day the repositories learn to
    page in the database, and nothing about their code changes. The alternative
    — ship offsets now, fix it later — means changing every client.
    """
    limit = max(1, min(int(limit), MAX_PAGE))
    ordered = sorted(rows, key=lambda r: _key(r, order), reverse=desc)
    if cursor:
        mark = Cursor.decode(cursor, order=order, desc=desc, now=now)
        ordered = [r for r in ordered
                   if _after(_key(r, order), mark.after, desc)]
    window = ordered[:limit]
    more = len(ordered) > limit
    return {
        "rows": window,
        "count": len(window),
        "has_more": more,
        "next_cursor": (Cursor(order, desc, _key(window[-1], order),
                               now).encode()
                        if more and window else None),
        "ordered_by": order,
        "descending": desc,
        "detail": (
            f"{len(window)} row(s), ordered by {order}"
            + (". More remain: pass `next_cursor` back as `cursor`. It names "
               "the last row you saw rather than a position, so a write above "
               "it does not make you skip one — which is what LIMIT/OFFSET "
               "does, silently, over a register that is being written to"
               if more else ". This is the end of the listing")),
    }


def _key(row: Dict[str, Any], order: str) -> Any:
    value = row.get(order)
    # A null sorts before everything rather than crashing the comparison. A
    # listing that raised because one row had no timestamp would be a listing
    # nobody could page through, which is worse than an arguable ordering.
    return (value is not None, value if value is not None else "")


def _after(value: Any, mark: Any, desc: bool) -> bool:
    mark = tuple(mark) if isinstance(mark, list) else mark
    try:
        return value < mark if desc else value > mark
    except TypeError:
        # Mixed types in the sort column. Keep the row rather than dropping it:
        # a page that silently omitted rows it could not compare would be the
        # exact hole this whole mechanism exists to prevent. Logged because it
        # means a column somewhere holds two shapes of value, which is a defect
        # worth finding rather than a condition worth tolerating quietly.
        logger.warning("cursor comparison hit mixed types in the sort column "
                       "(%r against %r); keeping the row", value, mark)
        return True


# ---------------------------------------------------------------- projection
def project(payload: Any, fields: Optional[str]) -> Any:
    """Narrow a payload to the named fields, keeping what says it is partial.

    Applied to a dict, to a list of dicts, and to the `rows` of a paged answer.
    Anything else is returned whole — projecting a scalar is not a thing a
    caller can have meant.
    """
    wanted = _wanted(fields)
    if not wanted:
        return payload
    if isinstance(payload, list):
        return [_narrow(item, wanted) for item in payload]
    if isinstance(payload, dict):
        if isinstance(payload.get("rows"), list):
            return {**payload,
                    "rows": [_narrow(r, wanted) for r in payload["rows"]],
                    "projected_to": sorted(wanted)}
        return _narrow(payload, wanted)
    return payload


def _wanted(fields: Optional[str]) -> set:
    if not fields:
        return set()
    return {f.strip() for f in str(fields).split(",") if f.strip()}


def _narrow(row: Any, wanted: Iterable[str]) -> Any:
    if not isinstance(row, dict):
        return row
    keep = set(wanted)
    return {k: v for k, v in row.items() if k in keep or k in ALWAYS_KEPT}


# -------------------------------------------------------------------- sunset
#: Endpoints on their way out: the date they stop, and what replaced them.
#:
#: Empty, and that is the correct state rather than an oversight — nothing in
#: this API has been retired yet. The mechanism ships before the first
#: deprecation on purpose: adding it at the moment something is being retired
#: means the first endpoint to go is the one with no warning, which is the one
#: case it existed for.
SUNSET: Dict[str, "Sunsetting"] = {}


class Sunsetting:
    """One endpoint's retirement, announced to the machine that is calling.

    A deprecation that lives only in a release note is one nobody reads. An
    integration built against a MAYA endpoint is usually a *control* — a CI
    gate, a nightly reconciliation, an export feeding a regulatory return — and
    when one of those stops, the firm's first signal is normally that the
    control has been silently absent for a month.
    """

    __slots__ = ("at", "path", "successor", "why")

    def __init__(self, path: str, at: float, successor: str = "",
                 why: str = ""):
        self.path, self.at, self.successor, self.why = path, at, successor, why

    def headers(self, now: Optional[float] = None) -> Dict[str, str]:
        moment = now if now is not None else time.time()
        out = {
            # RFC 8594: an HTTP-date, and `Deprecation` alongside it because
            # the two answer different questions — *is it deprecated now* and
            # *when does it stop*.
            "Sunset": time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                    time.gmtime(self.at)),
            "Deprecation": "true",
        }
        if self.successor:
            out["Link"] = f'<{self.successor}>; rel="successor-version"'
        remaining = self.at - moment
        out["X-Sunset-Detail"] = (
            (f"this endpoint stops in {int(remaining // 86400)} day(s). "
             if remaining > 0 else "this endpoint has passed its sunset date. ")
            + (self.why or "")
            + (f" Use {self.successor}." if self.successor else ""))
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "at": self.at,
                "successor": self.successor, "why": self.why}


def sunset_headers(path: str, now: Optional[float] = None
                   ) -> Dict[str, str]:
    """Headers for one request, or nothing.

    Matched on the route template rather than the resolved path, so an endpoint
    with an id in it is announced for every id rather than for none.
    """
    entry = SUNSET.get(path)
    return entry.headers(now) if entry else {}


def deprecations() -> List[Dict[str, Any]]:
    """Everything on its way out, for a client that wants to ask once.

    A caller should be able to find out what is retiring without waiting to
    receive a header from an endpoint they happen to still be calling — the
    integration they have not touched in two years is exactly the one that will
    break, and it is the one nobody is looking at.
    """
    return sorted((s.as_dict() for s in SUNSET.values()),
                  key=lambda s: s["at"])


# ---------------------------------------------------------------- derivations
def derivation_of(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The derivation inside an answer, if it carries one.

    Several answers here are *computed* — a tier, a remediation plan, a
    concentration — and each already carries the working that produced it.
    `/derivations/{id}` is a stable address for that working, so a committee
    paper can cite the arithmetic rather than paste it.
    """
    for key in ("derivation", "working", "plan", "provenance"):
        if isinstance(payload.get(key), (dict, list)):
            return {"kind": key, "derivation": payload[key]}
    return None
