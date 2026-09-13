"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — writing rows into a feature view.

Every row carries two clocks — `event_ts`, when it was true, and `ingest_ts`,
when we learned it — and point-in-time assembly compares both against the
bounds it was given. So the clocks are checked for PRESENCE and for
COMPARABILITY, and the second was the recorded defect: an `event_ts` of
`"2026-01-01T00:00:00Z"` was accepted at materialise with a 201 and a pinned
Delta table, and then every assembly over that view answered 500. Not one row
— the whole view, for every entity, because the comparison walks all
candidates before choosing.

A failing ASSERTION is treated differently from a failing clock, and the
difference is deliberate. A bad load is quarantined rather than refused: the
rows are written and the report says which assertion failed and by how much,
because deleting the evidence of a bad load is how nobody finds out what
arrived. What quarantine buys is that nothing may pin it.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)
from qa.regression_suite.scenarios.g_transfer import VIEWS, _view


def _rows(n: int, **over) -> list:
    out = []
    for i in range(n):
        row = {"entity_id": f"e{i}", "event_ts": 1_000.0 + i,
               "ingest_ts": 2_000.0 + i, "score": float(i)}
        row.update(over)
        out.append(row)
    return out


def _materialise(ctx: Ctx, name: str, rows, **over):
    body = {"rows": rows}
    body.update(over)
    return ctx.api.post(f"{VIEWS}/{name}/materialise", json=body,
                        auth=ctx.people["developer"])


def _versions(ctx: Ctx, name: str) -> list:
    got = ctx.api.get(f"{VIEWS}/{name}/versions", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return []
    body = got.json() or {}
    return body.get("versions") or body.get("rows") or []


@case("QA-FX-043", "A row missing `ingest_ts`")
def fx_043(ctx: Ctx) -> Result:
    """Without it there is no answer to *when did we learn this*, and the
    whole point-in-time story rests on that clock."""
    name = _view(ctx)
    rows = _rows(3)
    del rows[1]["ingest_ts"]
    got = _materialise(ctx, name, rows)
    if got.status_code < 400:
        return FAIL, "a row with no ingest clock was written"
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} rather than a named refusal"
    if "ingest_ts" not in got.text:
        return FAIL, f"the refusal does not name the clock: {got.text[:120]}"
    return PASS, f"refused '{code_of(got)}', naming ingest_ts"


@case("QA-FX-044", "A row missing `event_ts`")
def fx_044(ctx: Ctx) -> Result:
    """The other clock. A row that does not say when it was true cannot be
    read as-at anything."""
    name = _view(ctx)
    rows = _rows(3)
    del rows[2]["event_ts"]
    got = _materialise(ctx, name, rows)
    if got.status_code < 400:
        return FAIL, "a row with no event clock was written"
    if "event_ts" not in got.text:
        return FAIL, f"the refusal does not name the clock: {got.text[:120]}"
    return PASS, f"refused '{code_of(got)}', naming event_ts"


@case("QA-FX-045", "A row missing `entity_id`")
def fx_045(ctx: Ctx) -> Result:
    """A feature value belongs to somebody. A row with no entity is a number
    with nowhere to go, and it would join to everything or nothing."""
    name = _view(ctx)
    rows = _rows(3)
    del rows[0]["entity_id"]
    got = _materialise(ctx, name, rows)
    if got.status_code < 400:
        return FAIL, "a row with no entity was written"
    if "entity_id" not in got.text:
        return FAIL, f"the refusal does not name the field: {got.text[:120]}"
    return PASS, f"refused '{code_of(got)}', naming entity_id"


@case("QA-FX-046", "One row of a hundred missing a clock")
def fx_046(ctx: Ctx) -> Result:
    """Refused WHOLE, and nothing written. A partial write would leave a
    version whose row count disagrees with the load somebody sent, and the
    ninety-nine good rows would be pinned as though the hundredth had never
    existed."""
    name = _view(ctx)
    rows = _rows(100)
    del rows[57]["ingest_ts"]
    got = _materialise(ctx, name, rows)
    if got.status_code < 400:
        return FAIL, "a load with one bad row in a hundred was written"
    if _versions(ctx, name):
        return FAIL, ("the refused load left a version behind, so part of a "
                      "rejected batch is pinned")
    good = _materialise(ctx, name, _rows(100))
    if good.status_code >= 400:
        return BLOCKED, f"a clean load then failed: {good.text[:140]}"
    rows_written = (good.json() or {}).get("row_count")
    if rows_written != 100:
        return FAIL, (f"the clean load recorded {rows_written} rows, so the "
                      f"refused batch left something behind")
    return PASS, "refused whole, nothing written, a clean load then records 100"


@case("QA-FX-4840", "A clock that is a string rather than a number")
def fx_4840(ctx: Ctx) -> Result:
    """The recorded defect. Presence was checked and TYPE was not, so an ISO
    timestamp was accepted with a 201 and a pinned Delta table, and every
    assembly over that view then answered 500 — the whole view, for every
    entity. It is refused here instead, where the row can still be corrected
    and the message can name which row and which clock."""
    name = _view(ctx)
    rows = _rows(3)
    rows[1]["event_ts"] = "2026-01-01T00:00:00Z"
    got = _materialise(ctx, name, rows)
    if got.status_code < 400:
        return FAIL, ("an ISO string was accepted as a clock, so every "
                      "point-in-time read of this view will fail with a type "
                      "error")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} rather than a named refusal"
    said = got.text
    if "row 1" not in said and "event_ts" not in said:
        return FAIL, f"the refusal names neither the row nor the clock: {said[:130]}"
    return PASS, f"refused '{code_of(got)}', naming the row and the clock"


@case("QA-FX-4841", "A clock that is a boolean")
def fx_4841(ctx: Ctx) -> Result:
    """`bool` is excluded deliberately: `True <= 100.0` is perfectly legal in
    Python and completely meaningless as a timestamp, so it would pass a
    comparability check and silently sort as 1 — a row that reads as having
    been known at the very beginning of time."""
    name = _view(ctx)
    rows = _rows(3)
    rows[0]["ingest_ts"] = True
    got = _materialise(ctx, name, rows)
    if got.status_code < 400:
        return FAIL, ("a boolean was accepted as a clock: it compares legally "
                      "and sorts as 1, so the row reads as known at the "
                      "beginning of time")
    if "bool" not in got.text.lower():
        return FAIL, f"the refusal does not say what the value is: {got.text[:120]}"
    return PASS, f"refused '{code_of(got)}', naming the type"


@case("QA-FX-041", "Materialise exactly one row")
def fx_041(ctx: Ctx) -> Result:
    """One row is a load. A version numbered from one, with a row count that
    matches — the smallest case, and the one a bound written as `> 1` would
    quietly reject."""
    name = _view(ctx)
    got = _materialise(ctx, name, _rows(1))
    if got.status_code >= 400:
        return FAIL, f"a single-row load was refused '{code_of(got)}'"
    body = got.json() or {}
    if body.get("version") != 1:
        return FAIL, f"the first version is numbered {body.get('version')}"
    if body.get("row_count") != 1:
        return FAIL, f"one row recorded as {body.get('row_count')}"
    return PASS, "version 1, row_count 1"


@case("QA-FX-042", "Materialise identical rows twice")
def fx_042(ctx: Ctx) -> Result:
    """Two versions, and each in its own namespace. Deduplicating would make
    a re-load invisible, and a re-load is exactly the event somebody
    investigating a number needs to see."""
    name = _view(ctx)
    rows = _rows(5)
    first = _materialise(ctx, name, rows)
    second = _materialise(ctx, name, rows)
    if first.status_code >= 400 or second.status_code >= 400:
        return FAIL, (f"a repeated load failed: {first.status_code} then "
                      f"{second.status_code}")
    one, two = (first.json() or {}), (second.json() or {})
    if one.get("version") == two.get("version"):
        return FAIL, (f"two loads produced one version "
                      f"{one.get('version')}, so a re-load is invisible")
    if two.get("version") != (one.get("version") or 0) + 1:
        return FAIL, (f"the versions are {one.get('version')} and "
                      f"{two.get('version')}, which do not follow")
    if two.get("row_count") != len(rows):
        return FAIL, (f"the second load records {two.get('row_count')} rows "
                      f"of {len(rows)} — the two loads merged")
    return PASS, f"versions {one.get('version')} and {two.get('version')}, {len(rows)} rows each"


@case("QA-FX-047", "A row carrying a column the view does not list")
def fx_047(ctx: Ctx) -> Result:
    """Recorded rather than dropped. A loader sending an extra column is
    usually sending something somebody will want, and silently discarding it
    means the data exists upstream and not here with nothing saying why."""
    name = _view(ctx)
    rows = _rows(3, unlisted=7.0)
    got = _materialise(ctx, name, rows)
    if got.status_code >= 400:
        return FAIL, (f"a row carrying an extra column was refused "
                      f"'{code_of(got)}'")
    features = (got.json() or {}).get("features") or []
    if "unlisted" not in features:
        return FAIL, (f"the extra column was dropped silently: recorded "
                      f"features are {features}")
    return PASS, f"the extra column is recorded: {sorted(features)}"


@case("QA-FX-048", "`feature_names` naming a column no row carries")
def fx_048(ctx: Ctx) -> Result:
    """Accepted and reported. The declared name is what a contract pins
    against, so refusing would break a load whose upstream simply had nothing
    for that column today — but a column present in the schema and absent
    from every row is a fact a reader needs."""
    name = _view(ctx)
    got = _materialise(ctx, name, _rows(3),
                       feature_names=["score", "never_sent"])
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a declared column no row "
                       f"carries is rejected at the load")
    body = got.json() or {}
    features = body.get("features") or []
    if "never_sent" not in features:
        return FAIL, (f"the declared column is not recorded: {features}")
    quality = f"{body.get('quality_report') or {}}"
    if "never_sent" not in quality:
        return FAIL, ("a column declared and never sent does not appear in "
                      "the quality report, so it reads as a column with data")
    return PASS, "recorded, and the quality report names it"


@case("QA-FX-049", "A column that is null in every row")
def fx_049(ctx: Ctx) -> Result:
    """Accepted, and the quality report is where the fact lives. Refusing
    would stop a load whose column is legitimately empty this period; hiding
    it would let a feature that never arrives look like one that did."""
    name = _view(ctx)
    got = _materialise(ctx, name, _rows(4, score=None))
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' — an all-null column is rejected"
    report = (got.json() or {}).get("quality_report") or {}
    if not report:
        return FAIL, "an all-null column was accepted with no quality report"
    said = f"{report}"
    if "score" not in said:
        return FAIL, f"the quality report does not mention the column: {said[:130]}"
    if "1.0" not in said and "100" not in said:
        return FAIL, (f"the report does not show the column as wholly null: "
                      f"{said[:130]}")
    return PASS, "accepted, and the quality report shows the null rate"


@case("QA-FX-039", "Materialise zero rows")
def fx_039(ctx: Ctx) -> Result:
    """EXPLORATORY. An empty load pins a Delta version holding nothing, and
    anything that assembles from it gets an empty frame — so the question is
    whether the emptiness is visible at the load or discovered at layer two,
    where the caller is somebody else."""
    name = _view(ctx)
    got = _materialise(ctx, name, [])
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' at the load, where the "
                      f"person who sent it is still there")
    body = got.json() or {}
    if body.get("row_count") != 0:
        return FAIL, f"an empty load recorded {body.get('row_count')} rows"
    report = f"{body.get('quality_report') or {}}{body.get('assertion_report') or {}}"
    if body.get("quarantined") or "empty" in report.lower() or "0 row" in report:
        return PASS, (f"accepted and marked: quarantined="
                      f"{body.get('quarantined')}, and the report says so")
    return FAIL, ("an empty version was pinned with nothing marking it empty: "
                  "whatever assembles from it gets an empty frame, and the "
                  "refusal lands on somebody who did not send the load")
