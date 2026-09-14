"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the conventions every route shares.

Three of them carry governance weight rather than tidiness.

**A refusal has three parts.** `error` is what a client branches on, `detail`
is what a person reads, and `remediation` is what they do next. A refusal
missing the third is a refusal that tells somebody they may not and not how to
become somebody who may — which is how a control gets routed around instead of
satisfied.

**A projection never hides a refusal.** `?fields=` runs over rows the caller
was already entitled to see, and the fields that say a result is PARTIAL —
`detail`, `gaps`, `not_projected`, `coverage` and their kin — survive every
projection. An answer that looked complete because somebody projected away the
sentence saying it was not is the failure this codebase spends most of its
effort avoiding.

**And an empty answer says which kind of empty it is.** "Nothing matched" and
"you may not see it" are opposite facts that render identically.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx, **over) -> str:
    name = ctx.unique("hc")
    body = {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **SHAPE}
    body.update(over)
    ctx.api.post(M, json=body, auth=ctx.people["owner"])
    return name


@case("QA-PLT-356", "An unknown field in a request body")
def plt_356(ctx: Ctx) -> Result:
    """Refused, naming the field. A body model that ignored what it did not
    recognise would accept `blocking: true` spelled `blockng` and register a
    finding that does not block — the caller believing otherwise."""
    name = ctx.unique("hc")
    got = ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                                "owner": "owner", "tier_override": 1, **SHAPE},
                       auth=ctx.people["owner"])
    if got.status_code < 400:
        return FAIL, ("a body carrying an unknown field was accepted, so a "
                      "misspelt governance flag is silently dropped")
    if got.status_code != 422:
        return FAIL, f"refused {got.status_code} rather than 422"
    if "tier_override" not in got.text:
        return FAIL, f"the refusal does not name the field: {got.text[:170]}"
    if "extra_forbidden" not in got.text:
        return FAIL, f"refused for another reason: {got.text[:170]}"
    body = got.json() or {}
    if not isinstance(body.get("detail"), list):
        return FAIL, ("the framework's shape changed; a client parsing this "
                      "sees something other than a list of field errors")
    if "error" in body:
        return FAIL, (f"this refusal carries an `error` code "
                      f"({body['error']!r}) and the taxonomy's other 422s do "
                      f"too — then a client can read one shape after all")
    return PASS, ("refused 422 `extra_forbidden` naming the field, in the "
                  "framework's `detail` list shape rather than the platform's "
                  "error/detail/remediation")


@case("QA-PLT-357", "`?fields=` projecting away a partial answer")
def plt_357(ctx: Ctx) -> Result:
    """Every field that says an answer is incomplete survives every
    projection. This is the property the whole projection mechanism is
    allowed to exist on."""
    from core.http.conventions import ALWAYS_KEPT, project
    survived, lost = [], []
    for key in sorted(ALWAYS_KEPT):
        payload = {"rows": [{"urn": "maya://model/x", key: "this is partial",
                             "secret": "narrow me away"}],
                   key: "this is partial"}
        out = project(payload, "urn")
        row = (out.get("rows") or [{}])[0]
        (survived if row.get(key) and out.get(key) else lost).append(key)
    if lost:
        return FAIL, (f"{len(lost)} of {len(ALWAYS_KEPT)} incompleteness "
                      f"field(s) are projected away: {lost}")
    payload = {"rows": [{"urn": "u", "secret": "s"}]}
    narrowed = project(payload, "urn")
    if "secret" in (narrowed["rows"][0] or {}):
        return FAIL, "the projection kept a field nobody asked for"
    if "projected_to" not in narrowed:
        return FAIL, ("a narrowed answer does not say it was narrowed, so a "
                      "reader cannot tell a projection from a thin record")
    return PASS, (f"all {len(survived)} incompleteness field(s) survive a "
                  f"projection that removes everything else, and the answer "
                  f"says `projected_to`")


@case("QA-PLT-358", "`?fields=` naming a field that does not exist")
def plt_358(ctx: Ctx) -> Result:
    """A projection onto a field nobody has produces rows that are empty
    rather than an error. Whether that is right is a design call; whether
    the caller can TELL is not."""
    from core.http.conventions import project
    payload = {"rows": [{"urn": "maya://model/x", "tier": 1},
                        {"urn": "maya://model/y", "tier": 2}]}
    out = project(payload, "invented_field")
    rows = out.get("rows") or []
    if any(r for r in rows):
        return PASS, f"unknown fields do not empty the rows: {rows[0]}"
    if out.get("projected_to") != ["invented_field"]:
        return FAIL, f"the answer does not say what it projected to: {out}"
    return FAIL, (
        f"`?fields=invented_field` answers {len(rows)} empty object(s) with "
        f"200 and no refusal. The only thing distinguishing it from a listing "
        f"of rows that genuinely have no values is `projected_to: "
        f"{out['projected_to']}` — which says what was asked for, not that "
        f"nothing matched it. A client mapping a mistyped field name gets a "
        f"page of empty rows and a success, and the register looks empty")


@case("QA-PLT-359", "A search over the models listing that matches nothing")
def plt_359(ctx: Ctx) -> Result:
    """"Nothing matched" and "you may not see it" render identically, and
    only the answer can tell them apart."""
    _model(ctx)
    got = ctx.api.get(f"{M}?q=zzzzzznothingmatchesthis", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the listing was refused: {got.text[:150]}"
    body = got.json() or {}
    if body.get("returned"):
        return FAIL, f"a nonsense search returned {body['returned']} row(s)"
    if body.get("total"):
        return FAIL, (f"nothing was returned and the total reads "
                      f"{body['total']}")
    detail = (body.get("detail") or "").lower()
    if not detail:
        return FAIL, ("an empty listing says nothing, so a reader cannot tell "
                      "'nothing matched' from 'you may see nothing'")
    if "nothing matched" not in detail and "no " not in detail:
        return FAIL, f"the detail does not say what kind of empty: {detail[:140]}"
    wide = ctx.api.get(M, auth=ctx.people["risk"])
    if (wide.json() or {}).get("total", 0) < 1:
        return BLOCKED, "the reader can see nothing at all, so this proves little"
    return PASS, (f"total 0, returned 0, detail {detail[:70]!r} while the "
                  f"unfiltered listing shows "
                  f"{(wide.json() or {}).get('total')} model(s)")


@case("QA-PLT-360", "The models listing with no ordering parameter")
def plt_360(ctx: Ctx) -> Result:
    """Whatever order the register returns, it has to be the same order
    twice — an unstable listing makes every page boundary a place where a
    row is shown twice or not at all, and nothing says so."""
    for _ in range(6):
        _model(ctx)
    first = ctx.api.get(f"{M}?limit=100", auth=ctx.people["risk"])
    second = ctx.api.get(f"{M}?limit=100", auth=ctx.people["risk"])
    if first.status_code >= 400 or second.status_code >= 400:
        return BLOCKED, "the listing could not be read"
    a = [m["urn"] for m in (first.json() or {}).get("models") or []]
    b = [m["urn"] for m in (second.json() or {}).get("models") or []]
    if not a:
        return BLOCKED, "the listing is empty"
    if a != b:
        return FAIL, (f"two reads of the same listing came back in different "
                      f"orders; the first three were {a[:3]} then {b[:3]}")
    # A write BETWEEN the two pages, which is the condition offset paging is
    # weakest under. Compared against a listing read after the write, not
    # before it: a page that differs from a snapshot taken earlier differs
    # because the register moved, which is not the question.
    page_one = ctx.api.get(f"{M}?limit=3&offset=0", auth=ctx.people["risk"])
    # A name that sorts BEFORE every row on page one, so the insert
    # definitely lands inside the window already read. A random name sorts
    # wherever it likes and makes this case pass or fail by luck.
    first = f"0000-{ctx.unique('hc')}"
    ctx.api.post(M, json={"urn": f"maya://model/{first}", "name": first,
                          "owner": "owner", **SHAPE},
                 auth=ctx.people["owner"])
    page_two = ctx.api.get(f"{M}?limit=3&offset=3", auth=ctx.people["risk"])
    one = [m["urn"] for m in (page_one.json() or {}).get("models") or []]
    two = [m["urn"] for m in (page_two.json() or {}).get("models") or []]
    overlap = set(one) & set(two)
    if overlap:
        import inspect

        from core.http import conventions
        note = inspect.getdoc(conventions.page) or ""
        return FAIL, (
            f"page one and page two share {len(overlap)} row(s) after one "
            f"registration between the two reads: {sorted(overlap)[:3]}. "
            f"`/models` pages with LIMIT/OFFSET, so an insert that sorts "
            f"before the boundary shifts every later row down and the last "
            f"row of page one arrives again as the first of page two — the "
            f"reader sees it twice and, symmetrically, a delete makes them "
            f"miss one. `core/http/conventions.page` exists for exactly this "
            f"and says so — {note.splitlines()[0][:60]!r} — and has one caller "
            f"in the whole API. Same root as the `?fields=` finding: the "
            f"paging contract was built and almost nothing adopted it")
    if one != a[:3]:
        return FAIL, (f"the first page is not the head of the listing read a "
                      f"moment earlier: {one} against {a[:3]}")
    return PASS, (f"{len(a)} rows in the same order twice, and two pages that "
                  f"do not overlap across an intervening write")


@case("QA-PLT-361", "A 429 from the quota path")
def plt_361(ctx: Ctx) -> Result:
    """429 is the right status — the caller did nothing wrong and the answer
    is *later*, which is what 429 means and 403 does not. *Later* is an
    instruction a machine acts on, and without `Retry-After` every client
    invents its own interval."""
    from routes.base import STATUS
    rated = sorted(code for code, status in STATUS.items() if status == 429)
    if not rated:
        return BLOCKED, "nothing maps to 429"
    import pathlib
    sources = list(pathlib.Path("routes").rglob("*.py"))
    sources += list(pathlib.Path("core").rglob("*.py"))
    named = [p.name for p in sources
             if "Retry-After" in p.read_text(encoding="utf-8")
             or "retry-after" in p.read_text(encoding="utf-8")]
    if named:
        return PASS, f"Retry-After is set in {named}"
    return FAIL, (
        f"{len(rated)} refusal code(s) map to 429 — {rated} — and no route or "
        f"service anywhere sets a `Retry-After` header. The status says *come "
        f"back later*; the header is the only part of that a client can act "
        f"on, and every one of these limits is a window MAYA knows the length "
        f"of. A machine told 429 with no interval either retries immediately, "
        f"which is the behaviour the limit exists against, or backs off by a "
        f"guess that is nothing to do with the window")


@case("QA-PLT-362", "Every refusal carries all three parts")
def plt_362(ctx: Ctx) -> Result:
    """`error` is what a client branches on, `detail` is what a person
    reads, `remediation` is what they do next. A refusal without the third
    tells somebody they may not and not how to become somebody who may."""
    urn = f"maya://model/{_model(ctx)}"
    probes = [
        ("unknown model", ctx.api.get(f"{M}/maya://model/nope",
                                      auth=ctx.people["risk"])),
        ("no permission", ctx.api.post(M, json={"urn": "maya://model/x",
                                                "name": "x", "owner": "o",
                                                **SHAPE},
                                       auth=ctx.people["observer"]
                                       if "observer" in ctx.people
                                       else ctx.people["risk"])),
        ("duplicate urn", ctx.api.post(M, json={"urn": urn, "name": "dup",
                                                "owner": "owner", **SHAPE},
                                       auth=ctx.people["owner"])),
        ("unknown severity", ctx.api.post(
            "/api/v1/findings",
            json={"urn": urn, "severity": "Catastrophic", "title": "t",
                  "owner": "person/owner", "description": "d",
                  "category": "general", "source": "validation"},
            auth=ctx.people["risk"])),
        ("unknown document kind", ctx.api.post(
            f"/api/v1/documents?urn={urn}&kind=nonsense",
            auth=ctx.people["validator"])),
    ]
    thin = []
    checked = 0
    for what, response in probes:
        if response.status_code < 400:
            continue
        body = response.json() if response.headers.get(
            "content-type", "").startswith("application/json") else {}
        if not isinstance(body, dict) or "error" not in body:
            continue                       # a framework 422, its own shape
        checked += 1
        missing = [part for part in ("error", "detail", "remediation")
                   if not (body.get(part) or "").strip()]
        if missing:
            thin.append(f"{what} ({body.get('error')}): missing {missing}")
    if not checked:
        return BLOCKED, "no coded refusal was produced by these probes"
    if thin:
        return FAIL, (f"{len(thin)} of {checked} coded refusal(s) omit a part: "
                      f"{thin}")
    return PASS, (f"{checked} coded refusal(s), every one carrying error, "
                  f"detail and remediation")
