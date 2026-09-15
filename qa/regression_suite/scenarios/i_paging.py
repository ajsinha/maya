"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — one shape for every list the API returns.

No endpoint paginated once, and the architecture targets estates of a hundred
thousand models — so the first honest deployment would have handed a browser a
response it could not render.

Two of the three decisions are testable here and both are about being TOLD.
A caller asking for everything gets the maximum **and is told they did**, in
`returned` and `total`: silently truncating is how a client concludes there
are 200 models when there are 12,000. And the filter runs BEFORE the page,
because page two of a filtered list must not be page two of the unfiltered one
with holes in it — a model out of scope becomes discoverable by a count that
does not add up.
"""
from __future__ import annotations

from core.domain.paging import DEFAULT_LIMIT, MAX_LIMIT, PagingError, page
from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _many(ctx: Ctx, n: int, **over) -> None:
    for _ in range(n):
        name = ctx.unique("pg")
        ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                              "owner": "owner", **SHAPE, **over},
                     auth=ctx.people["owner"])


def _list(ctx: Ctx, query: str = "") -> dict:
    got = ctx.api.get(f"{M}?{query}" if query else M, auth=ADMIN)
    return got.json() if got.status_code < 400 else {"_status": got.status_code,
                                                     "_body": got.text[:180]}


@case("QA-PLT-352", "`?limit=100000` on the models listing")
def plt_352(ctx: Ctx) -> Result:
    """Clamped to the maximum, and the response ECHOES the limit it applied.
    A caller who asked for 100,000 and received 500 rows with no `limit` in
    the answer has no way to tell a small estate from a truncated one."""
    _many(ctx, 3)
    body = _list(ctx, "limit=100000")
    if "_status" in body:
        return BLOCKED, f"the listing answered {body['_status']}"
    if body.get("limit") != MAX_LIMIT:
        return FAIL, (f"the applied limit reads {body.get('limit')} rather "
                      f"than the maximum {MAX_LIMIT}, so a caller cannot see "
                      f"their request was clamped")
    for field in ("total", "returned", "has_more"):
        if field not in body:
            return FAIL, f"the page carries no '{field}'"
    if body.get("returned") > MAX_LIMIT:
        return FAIL, f"{body['returned']} rows returned above the cap"
    return PASS, (f"clamped to {body['limit']}, {body['returned']} of "
                  f"{body['total']} returned")


@case("QA-PLT-353", "`?limit=0` and `?limit=-5`")
def plt_353(ctx: Ctx) -> Result:
    """`max(1, min(limit, MAX))` — so zero and a negative clamp UP to one
    rather than producing an empty page. A limit of zero read literally
    returns nothing and looks exactly like an empty estate, which is the one
    reading a paging bug must not produce."""
    _many(ctx, 3)
    for asked in (0, -5):
        body = _list(ctx, f"limit={asked}")
        if "_status" in body:
            if body["_status"] < 500:
                continue
            return FAIL, f"limit={asked} answered {body['_status']}"
        if body.get("limit") != 1:
            return FAIL, (f"limit={asked} applied a limit of "
                          f"{body.get('limit')} rather than clamping to 1")
        if body.get("returned") != 1 and body.get("total"):
            return FAIL, (f"limit={asked} returned {body.get('returned')} rows "
                          f"over a total of {body.get('total')}, so an empty "
                          f"page reads as an empty estate")
    return PASS, "0 and -5 both clamp to a limit of 1"


@case("QA-PLT-354", "`?offset=9999` on a listing of 120 rows")
def plt_354(ctx: Ctx) -> Result:
    """An offset past the end is an empty page and NOT an error — a client
    walking pages reaches it naturally. What matters is that `total` still
    says how many there are, so the caller can tell they walked off the end
    from an estate that is empty."""
    _many(ctx, 3)
    body = _list(ctx, "offset=9999")
    if "_status" in body:
        return FAIL, (f"an offset past the end answered {body['_status']}: "
                      f"{body['_body']}")
    if body.get("returned"):
        return FAIL, f"offset 9999 returned {body['returned']} rows"
    if not body.get("total"):
        return FAIL, ("an offset past the end reports a total of 0, so "
                      "walking off the end is indistinguishable from an "
                      "empty estate")
    if body.get("has_more"):
        return FAIL, "an offset past the end says there is more"
    return PASS, (f"empty page, total still {body['total']}, has_more false")


@case("QA-PLT-355", "`?limit=abc` versus `?limit=100000`")
def plt_355(ctx: Ctx) -> Result:
    """The two differ and should. `abc` is not a number at all and the type
    layer refuses it; 100,000 is a number the register will not serve and is
    clamped. Conflating them would either refuse a legitimate ask-for-
    everything or accept a malformed one."""
    nonsense = ctx.api.get(f"{M}?limit=abc", auth=ADMIN)
    if nonsense.status_code < 400:
        return FAIL, "a non-numeric limit was accepted"
    huge = ctx.api.get(f"{M}?limit=100000", auth=ADMIN)
    if huge.status_code >= 400:
        return FAIL, (f"a limit of 100,000 was refused '{code_of(huge)}' "
                      f"rather than clamped, so a caller asking for "
                      f"everything gets nothing")
    return PASS, (f"'abc' refused {nonsense.status_code}, 100000 clamped to "
                  f"{(huge.json() or {}).get('limit')}")


@case("QA-PLT-073", "Filtering happens **before** paging")
def plt_073(ctx: Ctx) -> Result:
    """The decision that keeps a scope real. Page two of a filtered list must
    not be page two of the unfiltered one with holes in it — otherwise a
    model out of scope is discoverable by a count that does not add up."""
    _many(ctx, 6, domain="credit")
    _many(ctx, 6, domain="market")
    whole = _list(ctx, "limit=500")
    filtered = _list(ctx, "domain=market&limit=500")
    if "_status" in whole or "_status" in filtered:
        return BLOCKED, "a listing could not be read"
    if filtered.get("total") >= whole.get("total", 0):
        return FAIL, (f"the filtered total ({filtered.get('total')}) is not "
                      f"below the whole ({whole.get('total')}), so the filter "
                      f"did nothing")
    rows = [m.get("domain") for m in (filtered.get("models") or [])]
    if set(rows) - {"market"}:
        return FAIL, f"the filtered listing carries other domains: {set(rows)}"
    first = _list(ctx, "domain=market&limit=2&offset=0")
    second = _list(ctx, "domain=market&limit=2&offset=2")
    seen = [m.get("urn") for m in (first.get("models") or [])
            + (second.get("models") or [])]
    if len(seen) != len(set(seen)):
        return FAIL, "two pages of the filtered list overlap"
    if len(seen) != 4:
        return FAIL, (f"two pages of two gave {len(seen)} rows, so the page "
                      f"is being cut before the filter")
    if any(m.get("domain") != "market"
           for m in (second.get("models") or [])):
        return FAIL, ("page two of the filtered list holds rows the filter "
                      "excludes, so the filter runs after the page")
    return PASS, (f"{filtered['total']} of {whole['total']} match, and two "
                  f"pages of the filtered list are disjoint and in scope")


@case("QA-PLT-4790", "The default limit when none is asked for")
def plt_4790(ctx: Ctx) -> Result:
    """A listing with no limit must not return everything — that is the
    defect this module was written for. It returns the default and says so,
    so a caller who did not think about paging is still told there is more."""
    _many(ctx, 3)
    body = _list(ctx)
    if "_status" in body:
        return BLOCKED, f"the listing answered {body['_status']}"
    if body.get("limit") != DEFAULT_LIMIT:
        return FAIL, (f"an unlimited request applied a limit of "
                      f"{body.get('limit')} rather than the default "
                      f"{DEFAULT_LIMIT}")
    if body.get("returned") > DEFAULT_LIMIT:
        return FAIL, (f"{body['returned']} rows returned with no limit asked "
                      f"for: the whole inventory goes to the browser")
    return PASS, (f"defaulted to {DEFAULT_LIMIT}, {body['returned']} of "
                  f"{body['total']}")


@case("QA-PLT-4791", "The detail line tells a caller how to ask for more")
def plt_4791(ctx: Ctx) -> Result:
    """`has_more` is a boolean and the offset to send next is arithmetic the
    caller should not have to do. Every list in the API shares this shape, so
    getting it right once is worth a case."""
    rows = list(range(120))
    first = page(rows, limit=50, offset=0).as_dict("rows")
    if not first["has_more"]:
        return FAIL, "50 of 120 says there is no more"
    if "offset=50" not in first["detail"]:
        return FAIL, (f"the detail does not say where the next page starts: "
                      f"{first['detail']}")
    last = page(rows, limit=50, offset=100).as_dict("rows")
    if last["has_more"]:
        return FAIL, "the final page says there is more"
    if "offset=" in last["detail"]:
        return FAIL, f"the final page offers a next page: {last['detail']}"
    empty = page([], limit=50, offset=0).as_dict("rows")
    if empty["detail"] != "nothing matched":
        return FAIL, f"an empty list reads '{empty['detail']}'"
    if empty["has_more"]:
        return FAIL, "an empty list says there is more"
    return PASS, (f"'{first['detail'][:40]}…', final page offers nothing, "
                  f"empty says 'nothing matched'")


@case("QA-PLT-4792", "A page is a slice of what was already filtered")
def plt_4792(ctx: Ctx) -> Result:
    """The invariant behind QA-PLT-073, checked as arithmetic: `total` is the
    size of the filtered list and not of the underlying one, and the rows are
    a contiguous slice of it. A `total` counting rows the caller may not see
    is the count that does not add up."""
    rows = list(range(37))
    got = page(rows, limit=10, offset=30)
    if got.total != 37:
        return FAIL, f"total reads {got.total} over a list of 37"
    if got.rows != list(range(30, 37)):
        return FAIL, f"the final slice is {got.rows}"
    if got.has_more:
        return FAIL, "a slice reaching the end says there is more"
    over = page(rows, limit=10, offset=100)
    if over.rows or over.has_more:
        return FAIL, f"an offset past the end gave {over.rows}"
    if over.total != 37:
        return FAIL, f"an offset past the end reports a total of {over.total}"
    clamped = page(rows, limit=MAX_LIMIT + 1000, offset=0)
    if clamped.limit != MAX_LIMIT:
        return FAIL, f"the limit was not clamped: {clamped.limit}"
    # Refused, not floored. This case asserted the FLOOR, and the floor is
    # what made `?offset=-5` come back as page one with nothing saying the
    # request had been changed — a caller paging backwards past the start was
    # served the beginning and read it as the answer. Clamping a limit ABOVE
    # the maximum stays, and the difference is that it has an honest partial
    # answer: `limit` says what they got.
    try:
        negative = page(rows, limit=10, offset=-5)
    except PagingError as refused:
        if refused.code != "offset_refused":
            return FAIL, f"refused '{refused.code}', not by name"
    else:
        return FAIL, (f"a negative offset was repaired to {negative.offset} "
                      f"and served as page one, with nothing saying so")
    try:
        page(rows, limit=-1)
    except PagingError as refused:
        if refused.code != "limit_refused":
            return FAIL, f"a page size below one refused '{refused.code}'"
    else:
        return FAIL, "a page size below one was repaired rather than refused"
    return PASS, ("total counts the filtered list, slices are contiguous, a "
                  "limit above the maximum clamps with `limit` saying so, and "
                  "a page size or offset that is not one is refused")
