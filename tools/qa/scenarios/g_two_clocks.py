"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the two clocks.

Point-in-time assembly is bounded by `min(label_ts, as_of)`: a fact is
admissible when it was **true** by the decision moment and **knowable** by it.
Two clocks, and the bugs live on the boundary between them.

One fixture drives all of these. The estate is a single feature with two rows
that differ only in when they were *learned*: a value of 1.20 known at 100,
restated to 0.40 and learned at 800. Every case below is a different pair of
clock readings over that one disagreement, which is the cheapest way to ask
whether the boundary is `<` or `<=` and whether it is applied to the right
clock.
"""
from __future__ import annotations

from itertools import pairwise

from tools.qa.scenarios.common import FAIL, PASS, Ctx, Result, case

VIEW = "cov"
ROWS = [
    # true at 100, learned at 100 — the original
    {"entity_id": "b1", "dscr": 1.20, "event_ts": 100.0, "ingest_ts": 100.0},
    # true at 100, learned at 800 — the restatement
    {"entity_id": "b1", "dscr": 0.40, "event_ts": 100.0, "ingest_ts": 800.0},
]


def _fixture(ctx: Ctx) -> None:
    """Build the view once per run; re-running is a no-op."""
    if ctx.made.get("two_clocks"):
        return
    ctx.api.post("/api/v1/features",
                 json={"name": "dscr", "description": "debt service cover",
                       "dtype": "float", "entity": "borrower",
                       "owner": "admin"})
    ctx.api.post("/api/v1/feature-views",
                 json={"name": VIEW, "entity": "borrower",
                       "features": ["dscr"], "owner": "admin"})
    made = ctx.api.post(f"/api/v1/feature-views/{VIEW}/materialise",
                        json={"rows": ROWS})
    if made.status_code >= 400:
        raise AssertionError(f"could not materialise: {made.text[:200]}")
    ctx.made["two_clocks"] = True


def _assemble(ctx: Ctx, as_of: float, label_ts: float):
    _fixture(ctx)
    return ctx.api.post(f"/api/v1/feature-views/{VIEW}/versions/1/as-of",
                        json={"as_of": as_of, "label_ts": label_ts,
                              "entity_id": "b1"})


def _chosen(response):
    """The value the assembly settled on, or None.

    The answer carries `candidates` — every row with a verdict and a reason —
    and `read`, the one row that was actually taken. The value lives on
    `read`; the candidates carry the clocks and the refusal, not the payload.
    Reading the wrong one reported nine correct assemblies as `None`.
    """
    body = response.json()
    for entity in body.get("entities", []):
        if entity.get("entity_id") != "b1":
            continue
        read = entity.get("read")
        if isinstance(read, dict):
            return read.get("dscr")
        return None
    return None


def _expect_value(ctx: Ctx, as_of: float, label_ts: float, want) -> Result:
    got = _assemble(ctx, as_of, label_ts)
    if got.status_code >= 400:
        return FAIL, f"{got.status_code} {got.text[:160]}"
    value = _chosen(got)
    if want is None:
        if value is None:
            return PASS, "no admissible row, and the column is null"
        return FAIL, (f"expected no admissible row and the assembly chose "
                      f"{value} — a fact from the future reached the row")
    if value != want:
        return FAIL, (f"expected {want}, assembled {value} "
                      f"(as_of={as_of}, label_ts={label_ts})")
    return PASS, f"assembled {value}"


@case("QA-FX-001", "A restatement landing after the label cannot reach the row")
def fx_001(ctx: Ctx) -> Result:
    """The restatement was learned at 800; the decision was made at 500. It
    must not be visible, however much later the assembly is run."""
    return _expect_value(ctx, as_of=900.0, label_ts=500.0, want=1.20)


@case("QA-FX-002", "Saturation — moving as_of past the label does not move it")
def fx_002(ctx: Ctx) -> Result:
    return _expect_value(ctx, as_of=100_000.0, label_ts=500.0, want=1.20)


@case("QA-FX-003", "A later label reaches the restatement")
def fx_003(ctx: Ctx) -> Result:
    return _expect_value(ctx, as_of=900.0, label_ts=900.0, want=0.40)


@case("QA-FX-004", "A label before any fact was true")
def fx_004(ctx: Ctx) -> Result:
    return _expect_value(ctx, as_of=900.0, label_ts=50.0, want=None)


@case("QA-FX-005", "as_of strictly before the label bounds the assembly")
def fx_005(ctx: Ctx) -> Result:
    """The bound is `min(label_ts, as_of)`, so a low `as_of` wins over a high
    label — and re-running later with a higher `as_of` gives a different
    answer, which is the property that makes a replay meaningful."""
    early = _expect_value(ctx, as_of=200.0, label_ts=900.0, want=1.20)
    if early[0] != PASS:
        return early
    return _expect_value(ctx, as_of=900.0, label_ts=900.0, want=0.40)


@case("QA-FX-006", "Monotone in as_of — a later cut only ever widens")
def fx_006(ctx: Ctx) -> Result:
    seen = []
    for as_of in (100.0, 500.0, 900.0):
        got = _assemble(ctx, as_of, 900.0)
        if got.status_code >= 400:
            return FAIL, f"{as_of}: {got.text[:120]}"
        admissible = {
            (c["event_ts"], c["ingest_ts"])
            for e in got.json().get("entities", [])
            for c in e.get("candidates", []) if c.get("admissible")}
        seen.append((as_of, admissible))
    for (a, first), (b, second) in pairwise(seen):
        if not first <= second:
            return FAIL, (f"the admissible set shrank between as_of={a} and "
                          f"as_of={b}: {first} not a subset of {second}")
    return PASS, f"admissible sets nest: {[len(s) for _, s in seen]}"


@case("QA-FX-007", "Idempotence over the same request")
def fx_007(ctx: Ctx) -> Result:
    first = _assemble(ctx, 900.0, 500.0)
    second = _assemble(ctx, 900.0, 500.0)
    a, b = first.json(), second.json()
    for volatile in ("assembled_at", "took_ms", "request_id"):
        a.pop(volatile, None)
        b.pop(volatile, None)
    if a != b:
        return FAIL, "two identical requests assembled different answers"
    return PASS, "identical"


@case("QA-FX-008", "event_ts exactly equal to label_ts is included")
def fx_008(ctx: Ctx) -> Result:
    """The bound is `<=`. At exactly the decision moment the fact was true,
    and excluding it would silently drop the row a decision was made on."""
    return _expect_value(ctx, as_of=900.0, label_ts=100.0, want=1.20)


@case("QA-FX-009", "ingest_ts exactly equal to the knowable bound is included")
def fx_009(ctx: Ctx) -> Result:
    return _expect_value(ctx, as_of=800.0, label_ts=800.0, want=0.40)


@case("QA-FX-010", "ingest_ts one tick past the label, as_of far ahead")
def fx_010(ctx: Ctx) -> Result:
    return _expect_value(ctx, as_of=100_000.0, label_ts=799.0, want=1.20)


@case("QA-FX-013", "event_ts supplied as an ISO string rather than epoch")
def fx_013(ctx: Ctx) -> Result:
    """A 500 out of the comparison is the defect. A refusal is the feature."""
    _fixture(ctx)
    got = ctx.api.post("/api/v1/feature-views/cov/materialise", json={"rows": [
        {"entity_id": "b2", "dscr": 1.0,
         "event_ts": "2026-01-01T00:00:00Z", "ingest_ts": 100.0}]})
    if got.status_code >= 500:
        return FAIL, (f"an ISO string in a numeric clock produced "
                      f"{got.status_code} — an unhandled comparison")
    if got.status_code < 400:
        return FAIL, ("an ISO string was accepted into a numeric clock; the "
                      "two clocks are compared with <= and a string that "
                      "sorts is worse than one that raises")
    return PASS, f"refused ({got.status_code})"


@case("QA-FX-014", "NaN in ingest_ts")
def fx_014(ctx: Ctx) -> Result:
    """`NaN <= x` is false, so the row would vanish without a word.

    Sent as raw JSON text rather than through the client's encoder, which
    refuses NaN itself — a case that cannot even be transmitted by a
    well-behaved client is not a case about the platform.
    """
    _fixture(ctx)
    got = ctx.api.post(
        "/api/v1/feature-views/cov/materialise",
        content=('{"rows":[{"entity_id":"b3","dscr":1.0,'
                 '"event_ts":100.0,"ingest_ts":NaN}]}'),
        headers={"Content-Type": "application/json"})
    if got.status_code >= 500:
        return FAIL, f"NaN in a clock produced {got.status_code}"
    return PASS, (f"NaN answered {got.status_code}: {got.text[:130]}")


@case("QA-FX-015", "An as_of before the view existed")
def fx_015(ctx: Ctx) -> Result:
    return _expect_value(ctx, as_of=1.0, label_ts=1.0, want=None)


@case("QA-FX-016", "A negative as_of")
def fx_016(ctx: Ctx) -> Result:
    _fixture(ctx)
    got = _assemble(ctx, -1.0, 500.0)
    if got.status_code >= 500:
        return FAIL, f"a negative as_of produced {got.status_code}"
    return PASS, f"answered {got.status_code}"


@case("QA-FX-017", "An entity that has no rows")
def fx_017(ctx: Ctx) -> Result:
    _fixture(ctx)
    got = ctx.api.post("/api/v1/feature-views/cov/versions/1/as-of",
                       json={"as_of": 900.0, "label_ts": 900.0,
                             "entity_id": "nobody"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if got.status_code >= 400:
        return PASS, f"refused ({got.status_code})"
    entities = got.json().get("entities", [])
    if entities and any(c.get("admissible")
                        for e in entities for c in e.get("candidates", [])):
        return FAIL, "an entity with no rows assembled an admissible fact"
    return PASS, "no admissible facts for an unknown entity"


@case("QA-FX-018", "An assembly on a view version that does not exist")
def fx_018(ctx: Ctx) -> Result:
    _fixture(ctx)
    got = ctx.api.post("/api/v1/feature-views/cov/versions/99/as-of",
                       json={"as_of": 900.0, "label_ts": 900.0,
                             "entity_id": "b1"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — an unknown version must not crash"
    if got.status_code < 400:
        return FAIL, "an unknown view version assembled an answer"
    return PASS, f"refused ({got.status_code})"
