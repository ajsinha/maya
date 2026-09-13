"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — telemetry delivery.

Everything a monitor later computes rests on what arrived here, so the
interesting failures are the quiet ones: a batch truncated instead of refused,
a duplicate counted twice, a malformed row dropped while its 499 neighbours
land. Each of those produces a population nobody chose, which is the shape
this module has to make impossible.
"""
from __future__ import annotations

import time

from core.telemetry.common import (ENTITY, LABEL, LABEL_TS, MAX_BATCH,
                                   OUTCOMES, REQUIRED, SCORE, SCORED_AT,
                                   SCORES, STREAMS)
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

T = "/api/v1/telemetry"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _service(ctx: Ctx):
    """A principal holding `monitor:observe`.

    No human role has it, and that is the design: "the principal that runs
    the model is the one holding the scores, so it hands them over — and
    stops there". Delivering telemetry as `owner` answers `forbidden`, which
    is a refusal, which scores as a pass on any case checking only the status.
    """
    who = ctx.made.get("telemetry_service")
    if who:
        return who
    name = ctx.unique("svc")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": name, "display_name": name,
                              "roles": ["service"], "password": f"{name}-pw",
                              "kind": "service",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        raise AssertionError(f"could not mint a service principal: "
                             f"{made.text[:180]}")
    ctx.made["telemetry_service"] = (name, f"{name}-pw")
    return ctx.made["telemetry_service"]


def _version(ctx: Ctx) -> str:
    name = ctx.unique("tm")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    made = ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        raise AssertionError(f"could not create a version: {made.text[:180]}")
    return urn


def _rows(n: int, start: int = 0):
    now = time.time()
    return [{ENTITY: f"e{start + i}", SCORED_AT: now - 60, SCORE: 0.5}
            for i in range(n)]


def _ingest(ctx: Ctx, urn: str, rows, **over):
    body = {"urn": urn, "semver": "1.0.0", "stream": SCORES, "rows": rows,
            "sample_rate": 1.0, "source": "qa"}
    body.update(over)
    return ctx.api.post(T, json=body, auth=_service(ctx))


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-AM-236", "Deliver an empty batch")
def am_236(ctx: Ctx) -> Result:
    """An empty batch accepted is a delivery that happened and covered
    nothing, and the freshness clock then says the stream is healthy."""
    got = _ingest(ctx, _version(ctx), [])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("an empty batch was accepted, so a stream that "
                      "delivered nothing reads as fresh")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-234", "A scores row with no scored_at")
def am_234(ctx: Ctx) -> Result:
    """Naming the field is the point. Every required field of every stream,
    not a sample — a missing one that is silently defaulted puts a row in the
    wrong window."""
    urn = _version(ctx)
    accepted = []
    for stream, required in REQUIRED.items():
        for field in required:
            row = ({ENTITY: "e1", SCORED_AT: time.time(), SCORE: 0.5}
                   if stream == SCORES
                   else {ENTITY: "e1", LABEL: 1, LABEL_TS: time.time()})
            row.pop(field)
            got = _ingest(ctx, urn, [row], stream=stream)
            if got.status_code >= 500:
                return FAIL, f"{stream}.{field}: {got.status_code}"
            if got.status_code < 400:
                accepted.append(f"{stream}.{field}")
            elif field not in got.text:
                return FAIL, (f"the refusal for a missing {stream}.{field} "
                              f"does not name it: {got.text[:120]}")
    if accepted:
        return FAIL, f"rows accepted with a required field absent: {accepted}"
    total = sum(len(f) for f in REQUIRED.values())
    return PASS, f"all {total} required fields refused by name when absent"


@case("QA-AM-235", "Deliver row 400 of 500 malformed")
def am_235(ctx: Ctx) -> Result:
    """Refused WHOLE. Landing the 499 well-formed rows would produce a
    population nobody chose, and the caller would have no way to know which
    rows are in it."""
    urn = _version(ctx)
    rows = _rows(500)
    rows[399].pop(SCORE)
    got = _ingest(ctx, urn, rows)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a batch with a malformed row was accepted"
    clean = _ingest(ctx, urn, _rows(3, start=9000))
    if clean.status_code >= 400:
        return BLOCKED, f"a clean batch afterwards failed: {clean.text[:120]}"
    landed = (clean.json() or {}).get("rows")
    if landed not in (3, None):
        return FAIL, (f"the refused batch left rows behind: a following clean "
                      f"batch of 3 reports {landed}")
    return PASS, f"refused '{code_of(got)}' whole"


@case("QA-AM-237", "A sample rate of zero")
def am_237(ctx: Ctx) -> Result:
    """A rate of zero means these rows represent nothing, which makes every
    figure derived from them undefined rather than small."""
    urn = _version(ctx)
    accepted = []
    for rate in (0, -1, 1.5, 100):
        got = _ingest(ctx, urn, _rows(2), sample_rate=rate)
        if got.status_code >= 500:
            return FAIL, f"rate {rate}: {got.status_code}"
        if got.status_code < 400:
            accepted.append(rate)
    if accepted:
        return FAIL, f"these sample rates were accepted: {accepted}"
    return PASS, "0, -1, 1.5 and 100 all refused"


@case("QA-AM-243", "A batch of exactly the maximum size, and one row more")
def am_243(ctx: Ctx) -> Result:
    """Refused rather than accepted and truncated. Truncation is the quiet
    failure: the batch succeeds and the population is short."""
    urn = _version(ctx)
    over = _ingest(ctx, urn, _rows(MAX_BATCH + 1))
    if over.status_code >= 500:
        return FAIL, f"{over.status_code}"
    if over.status_code < 400:
        landed = (over.json() or {}).get("rows")
        if landed and landed <= MAX_BATCH:
            return FAIL, (f"{MAX_BATCH + 1} rows were accepted and truncated "
                          f"to {landed}; the batch succeeded and the "
                          f"population is short")
        return FAIL, f"{MAX_BATCH + 1} rows were accepted"
    if str(MAX_BATCH) not in over.text.replace(",", ""):
        return FAIL, f"the refusal does not state the limit: {over.text[:120]}"
    return PASS, f"refused '{code_of(over)}', naming the {MAX_BATCH:,} limit"


@case("QA-AM-231", "Deliver the identical batch twice")
def am_231(ctx: Ctx) -> Result:
    """A redelivery is the ordinary consequence of a retry. Counting it twice
    doubles a denominator; refusing it outright makes a retry an incident. It
    is accepted and REPORTED as a duplicate."""
    urn = _version(ctx)
    rows = _rows(5, start=100)
    first = _ingest(ctx, urn, rows)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again = _ingest(ctx, urn, rows)
    if again.status_code >= 400:
        return FAIL, (f"an identical redelivery was refused '{code_of(again)}'; "
                      f"an ordinary retry is an incident")
    body = again.json() or {}
    if not body.get("duplicate"):
        return FAIL, ("a redelivered batch is not reported as a duplicate, so "
                      "a retry doubles whatever is counted from it")
    if first.json().get("duplicate"):
        return FAIL, "the FIRST delivery was reported as a duplicate"
    return PASS, "first delivery clean, redelivery reported as duplicate"


@case("QA-AM-232", "The same rows plus one more")
def am_232(ctx: Ctx) -> Result:
    """A batch is identified by its content, so one extra row makes a
    different batch — and every original row arrives again inside it."""
    urn = _version(ctx)
    rows = _rows(5, start=200)
    if _ingest(ctx, urn, rows).status_code >= 400:
        return BLOCKED, "the first batch failed"
    got = _ingest(ctx, urn, rows + _rows(1, start=999))
    if got.status_code >= 400:
        return FAIL, f"a superset batch was refused '{code_of(got)}'"
    if (got.json() or {}).get("duplicate"):
        return FAIL, ("a batch with an extra row was called a duplicate, so "
                      "the new row never arrives")
    return PASS, "a superset is a different batch"


@case("QA-AM-3200", "A stream that is not one")
def am_3200(ctx: Ctx) -> Result:
    """`scores` is what the model produced and `outcomes` is what actually
    happened. A third name would be rows nothing reads."""
    got = _ingest(ctx, _version(ctx), _rows(2), stream="predictions")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "rows were delivered to a stream that does not exist"
    if not any(s in got.text for s in STREAMS):
        return FAIL, "the refusal does not name the streams"
    return PASS, f"refused '{code_of(got)}', naming {len(STREAMS)} streams"


@case("QA-AM-242", "Read the cohort before anything was delivered")
def am_242(ctx: Ctx) -> Result:
    """Empty, not an error. A cohort with no rows in the window is a real
    answer, and refusing it would make an unmonitored model indistinguishable
    from a broken query."""
    urn = _version(ctx)
    got = ctx.api.get(f"{T}/cohort?urn={urn}&semver=1.0.0",
                      auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return FAIL, (f"an empty cohort refused '{code_of(got)}' rather than "
                      f"answering that it is empty")
    return PASS, "an empty cohort is an answer"


@case("QA-AM-239", "A scored row whose outcome never arrives")
def am_239(ctx: Ctx) -> Result:
    """The row still belongs to the cohort — it is an unlabelled member, not
    an absent one. Dropping it would make the labelled fraction 100%."""
    urn = _version(ctx)
    if _ingest(ctx, urn, _rows(4, start=300)).status_code >= 400:
        return BLOCKED, "the scores batch failed"
    got = ctx.api.get(f"{T}/cohort?urn={urn}&semver=1.0.0",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    # `rows` and `labelled` — a count and a count, not a fraction. Reading a
    # `labelled_fraction` finds nothing and reports the cohort as silent.
    rows, labelled = body.get("rows"), body.get("labelled")
    if rows is None or labelled is None:
        return BLOCKED, f"the cohort reports no counts: {sorted(body)}"
    if not rows:
        return FAIL, ("the scored rows are not in the cohort at all, so an "
                      "unlabelled member reads as an absent one")
    if labelled:
        return FAIL, (f"a cohort with no outcomes reports {labelled} of "
                      f"{rows} labelled")
    return PASS, f"{rows} row(s) in the cohort, {labelled} labelled"


@case("QA-AM-241", "More outcomes than scores")
def am_241(ctx: Ctx) -> Result:
    """A labelled fraction above one is arithmetic nobody can read, and it
    means outcomes are arriving for entities this version never scored."""
    urn = _version(ctx)
    if _ingest(ctx, urn, _rows(2, start=400)).status_code >= 400:
        return BLOCKED, "the scores batch failed"
    now = time.time()
    outcomes = [{ENTITY: f"e{400 + i}", LABEL: 1, LABEL_TS: now}
                for i in range(6)]
    sent = _ingest(ctx, urn, outcomes, stream=OUTCOMES)
    if sent.status_code >= 400:
        return BLOCKED, sent.text[:170]
    got = ctx.api.get(f"{T}/cohort?urn={urn}&semver=1.0.0",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    rows, labelled = body.get("rows") or 0, body.get("labelled") or 0
    if labelled > rows:
        return FAIL, (f"{labelled} labelled of {rows} scored: outcomes "
                      f"arrived for entities this version never scored, and "
                      f"any fraction taken from these is above 100%")
    return PASS, f"{labelled} labelled of {rows} scored, bounded by the scores"
