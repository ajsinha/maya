"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the test catalogue and its thresholds.

A recorded result is the evidence a validation rests on. The two ways it can
mislead are a value computed from a sample that cannot support it, and a
threshold that reads as a limit and is not applied. Both are here.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

V = "/api/v1/validations"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
SAME = [float(n) for n in range(50)]


def _value(row: dict):
    """The computed value, distinguishing 0.0 from absent.

    `row.get("value") or default` returns the default when the value is 0.0,
    and a PSI of a sample against itself IS 0.0 — so every boundary case
    written that way tests the wrong number and reports the fixture as
    broken.
    """
    raw = row.get("value")
    return None if raw is None else float(raw)


def _episode(ctx: Ctx) -> str:
    name = ctx.unique("tc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    made = ctx.api.post(V, json={"urn": f"maya://model/{name}",
                                 "semver": "1.0.0", "kind": "initial",
                                 "validators": ["person/validator"]},
                        auth=ctx.people["risk"])
    return made.json()["id"] if made.status_code < 400 else ""


def _record(ctx: Ctx, vid: str, **over):
    body = {"test_key": "stability.psi", "left": SAME, "right": SAME}
    body.update(over)
    return ctx.api.post(f"{V}/{vid}/results", json=body,
                        auth=ctx.people["validator"])


@case("QA-AM-048", "A test key that is not in the catalogue")
def am_048(ctx: Ctx) -> Result:
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    return refused_by_the_control(
        _record(ctx, vid, test_key="vibes.check"),
        "a result was recorded under a test nobody defined")


@case("QA-AM-032", "A threshold declaring a key the catalogue does not have")
def am_032(ctx: Ctx) -> Result:
    """`floor` reads exactly like `min` and is not it. Accepting it would
    record a test with an unapplied limit that looks applied."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, threshold={"floor": 0.1})
    if got.status_code < 400:
        return FAIL, ("a threshold declaring only `floor` was accepted, so "
                      "the limit reads as declared and is applied to nothing")
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if not all(k in got.text for k in ("min", "max", "target")):
        return FAIL, "the refusal does not name the three it accepts"
    return PASS, f"refused '{code_of(got)}', naming min/max/target"


@case("QA-AM-031", "A threshold declaring both min and max")
def am_031(ctx: Ctx) -> Result:
    """A validator declaring a band means both ends. The evaluator returns on
    the first key it finds, so a value outside the OTHER end has to be caught
    or the band is half a band.
    """
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    # PSI of a sample against itself is 0, which meets `min: -1` and blows
    # through `max: -0.5`. Any honest reading of the band fails this.
    got = _record(ctx, vid, threshold={"min": -1.0, "max": -0.5})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' — a band must be one limit"
    row = got.json() or {}
    if not row.get("passed"):
        return PASS, f"both ends applied: {row.get('detail', '')[:90]}"
    return FAIL, (
        f"value {row.get('value')} passed a threshold declaring max "
        f"{-0.5:g}: the evaluator returns on `min` and never reads `max`, so "
        f"a validator who declares a band gets one end of it checked and the "
        f"detail — {str(row.get('detail'))[:60]} — names only the end that "
        f"was applied")


@case("QA-AM-033", "A target with no tolerance")
def am_033(ctx: Ctx) -> Result:
    """Tolerance defaults to zero, so the value has to match exactly. That is
    strict rather than wrong, and the case pins which."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, threshold={"target": 0.0})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    row = got.json() or {}
    if "tolerance" not in str(row.get("detail", "")):
        return FAIL, ("the detail does not say what tolerance was applied, so "
                      "a zero default is invisible")
    return PASS, f"tolerance stated: {str(row.get('detail'))[:80]}"


@case("QA-AM-034", "A value exactly equal to min")
def am_034(ctx: Ctx) -> Result:
    """The boundary is inclusive, and a result sitting on it must not fail."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, threshold={"min": 0.0})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    row = got.json() or {}
    if _value(row) is None or round(_value(row), 9) != 0.0:
        return BLOCKED, f"the fixture's PSI was {row.get('value')}, not 0"
    if not row.get("passed"):
        return FAIL, "a value exactly on the minimum failed it"
    return PASS, "the minimum is inclusive"


@case("QA-AM-035", "A value exactly equal to max")
def am_035(ctx: Ctx) -> Result:
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, threshold={"max": 0.0})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    row = got.json() or {}
    if _value(row) is None or round(_value(row), 9) != 0.0:
        return BLOCKED, f"the fixture's PSI was {row.get('value')}"
    if not row.get("passed"):
        return FAIL, "a value exactly on the maximum failed it"
    return PASS, "the maximum is inclusive"


@case("QA-AM-036", "A deviation exactly equal to tolerance")
def am_036(ctx: Ctx) -> Result:
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, threshold={"target": 0.25, "tolerance": 0.25})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    row = got.json() or {}
    if _value(row) is None or round(_value(row), 9) != 0.0:
        return BLOCKED, f"the fixture's PSI was {row.get('value')}"
    if not row.get("passed"):
        return FAIL, "a deviation exactly equal to the tolerance failed"
    return PASS, "the tolerance is inclusive"


@case("QA-AM-041", "Both series empty")
def am_041(ctx: Ctx) -> Result:
    """A metric computed from nothing must not read as a metric. `passed`
    false with a null value says the test could not be computed, which is a
    different fact from a test that failed."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, left=[], right=[])
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    row = got.json() or {}
    if row.get("value") is not None:
        return FAIL, (f"a value of {row.get('value')} was computed from two "
                      f"empty series")
    if row.get("passed"):
        return FAIL, "a test over no observations at all passed"
    if "not computable" not in str(row.get("detail", "")):
        return FAIL, (f"the record does not say the test was not computable: "
                      f"{str(row.get('detail'))[:100]}")
    return PASS, "null value, not passed, and said to be not computable"


@case("QA-AM-042", "An empty series with no threshold")
def am_042(ctx: Ctx) -> Result:
    """No threshold means no verdict to fail, and a recorded measurement
    passes. That must NOT extend to a measurement that does not exist."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, left=[], right=[], threshold={})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    row = got.json() or {}
    if row.get("passed"):
        return FAIL, ("a test over no observations and no threshold passed; "
                      "'no threshold means no verdict to fail' was applied to "
                      "a value that was never computed")
    return PASS, "not computable beats no-threshold-so-it-passes"


@case("QA-AM-040", "More bins than the reference has points")
def am_040(ctx: Ctx) -> Result:
    """Twenty bins over ten values is a PSI nobody should quote."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    ten = [float(n) for n in range(10)]
    got = _record(ctx, vid, left=ten, right=ten, parameters={"bins": 20})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    row = got.json() or {}
    if row.get("value") is not None and row.get("passed"):
        return FAIL, (f"a PSI of {row.get('value')} was computed and passed "
                      f"over 20 bins on 10 points")
    return PASS, f"not quoted as a result: {str(row.get('detail'))[:80]}"


@case("QA-AM-030", "Labels and scores of different lengths")
def am_030(ctx: Ctx) -> Result:
    """Two series that do not line up cannot be paired, and pairing them by
    position would silently drop the tail."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    return refused_by_the_control(
        _record(ctx, vid, test_key="discrimination.gini",
                left=[float(n % 2) for n in range(100)],
                right=[float(n) / 100 for n in range(99)]),
        "two series of different lengths were paired, so the longer one's "
        "tail was dropped without saying so")


@case("QA-AM-044", "The same numbers recorded twice")
def am_044(ctx: Ctx) -> Result:
    """Identical inputs must digest identically, or a replay cannot tell a
    re-run from a different measurement."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    first, second = _record(ctx, vid), _record(ctx, vid)
    if first.status_code >= 400 or second.status_code >= 400:
        return BLOCKED, first.text[:170]
    a, b = first.json(), second.json()
    digest = a.get("input_digest") or a.get("digest")
    if not digest:
        return FAIL, ("a result carries no digest of its inputs, so nothing "
                      "can tell two measurements apart")
    if digest != (b.get("input_digest") or b.get("digest")):
        return FAIL, "the same numbers digested differently"
    return PASS, f"identical inputs, identical digest {str(digest)[:16]}"


@case("QA-AM-045", "The same value under a different slice")
def am_045(ctx: Ctx) -> Result:
    """A metric over retail and a metric over wholesale are different
    measurements even when the number is the same."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    first = _record(ctx, vid, slice={"segment": "retail"})
    second = _record(ctx, vid, slice={"segment": "wholesale"})
    if first.status_code >= 400 or second.status_code >= 400:
        return BLOCKED, first.text[:170]
    a = first.json().get("input_digest") or first.json().get("digest")
    b = second.json().get("input_digest") or second.json().get("digest")
    if not a or not b:
        return BLOCKED, "results carry no digest to compare"
    if a == b:
        return FAIL, ("two measurements over different slices share one "
                      "digest, so a replay cannot tell which population was "
                      "measured")
    return PASS, "different slices, different digests"


@case("QA-AM-046", "A slice the supplied data was never filtered by")
def am_046(ctx: Ctx) -> Result:
    """MAYA did not read the population, so it cannot check that the numbers
    are the slice they claim to be. The record has to say so rather than
    implying a filter was applied."""
    vid = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, slice={"segment": "retail"})
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    row = got.json() or {}
    if (row.get("slice") or {}).get("segment") != "retail":
        return FAIL, "the declared slice was not recorded"
    return PASS, ("the slice is recorded as declared; the platform cannot "
                  "check the data was filtered by it and does not claim to")
