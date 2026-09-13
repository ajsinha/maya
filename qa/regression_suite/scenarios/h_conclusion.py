"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — concluding a validation episode.

The conclusion is where effective challenge either happens or is recorded as
having happened. A validation with no results is not one that found nothing;
it is one that did not happen, and both leave `failed` empty. These cases push
on every way an episode can end up saying `approved` without having examined
anything.
"""
from __future__ import annotations

from core.validation.common import OUTCOMES, TIER_VERDICTS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

V = "/api/v1/validations"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
#: Two identical distributions: a PSI of 0, which passes any threshold.
SAME = [float(n) for n in range(50)]
#: Two that are nothing alike, so the test fails on its own merits.
APART = [float(n) + 500.0 for n in range(50)]
#: A threshold declares `min`, `max` or `target` — not an operator and a
#: value. A threshold in the wrong vocabulary is refused at record time, and
#: a case built on one never gets a failing result to conclude over.
FAILS = {"max": 0.1}


def _findings(ctx: Ctx, urn: str, category: str) -> list:
    """`GET /findings` is keyed by `urn` — `model_id` is not a parameter it
    has — and answers `{model, summary, open: [...]}`. There is no `findings`
    key, so reading one returns an empty list against any behaviour at all."""
    got = ctx.api.get(f"/api/v1/findings?urn={urn}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return []
    return [f for f in (got.json().get("open") or [])
            if f.get("category") == category]


def _episode(ctx: Ctx) -> tuple:
    name = ctx.unique("cn")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    urn = f"maya://model/{name}"
    made = ctx.api.post(V, json={"urn": urn, "semver": "1.0.0",
                                 "kind": "initial",
                                 "validators": ["person/validator"]},
                        auth=ctx.people["risk"])
    return (made.json()["id"] if made.status_code < 400 else ""), urn


def _record(ctx: Ctx, vid: str, right=None, **over):
    body = {"test_key": "stability.psi", "left": SAME,
            "right": list(right if right is not None else SAME)}
    body.update(over)
    return ctx.api.post(f"{V}/{vid}/results", json=body,
                        auth=ctx.people["validator"])


def _conclude(ctx: Ctx, vid: str, **over):
    body = {"outcome": "approved", "tier_verdict": "remains_appropriate",
            "tier_note": "", "conditions": []}
    body.update(over)
    return ctx.api.post(f"{V}/{vid}/conclude", json=body,
                        auth=ctx.people["validator"])


@case("QA-AM-014", "Conclude approved with no test result at all")
def am_014(ctx: Ctx) -> Result:
    """`failed` is empty for an episode that found nothing AND for one that
    did not happen. Effective challenge is the control the second line exists
    to be."""
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    return refused_by_the_control(
        _conclude(ctx, vid),
        "an episode was approved having examined nothing at all")


@case("QA-AM-009", "Conclude with no tier verdict")
def am_009(ctx: Ctx) -> Result:
    """An episode concluded without a verdict reads exactly like one where
    the validator looked and agreed."""
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    _record(ctx, vid)
    return refused_by_the_control(
        _conclude(ctx, vid, tier_verdict=None),
        "an episode concluded with no verdict on the tier, which reads as "
        "the validator having looked and agreed")


@case("QA-AM-010", "Conclude should_be_higher with a blank note")
def am_010(ctx: Ctx) -> Result:
    """Saying the tier is wrong without saying why is a finding nobody can
    act on."""
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    _record(ctx, vid)
    return refused_by_the_control(
        _conclude(ctx, vid, tier_verdict="should_be_higher", tier_note=" "),
        "the tier was called wrong with no reason recorded")


@case("QA-AM-011", "should_be_higher raises a finding")
def am_011(ctx: Ctx) -> Result:
    """A validator saying a model is riskier than the register says, and
    nothing happening, is the failure this verdict exists to prevent."""
    vid, urn = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    _record(ctx, vid)
    got = _conclude(ctx, vid, tier_verdict="should_be_higher",
                    tier_note="the exposure is understated")
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    tiering = _findings(ctx, urn, "tiering")
    if not tiering:
        return FAIL, ("a validator said the tier understates the risk and no "
                      "finding was raised, so the verdict went into a field "
                      "nobody reads")
    return PASS, f"{len(tiering)} tiering finding(s) raised"


@case("QA-AM-012", "should_be_lower raises nothing")
def am_012(ctx: Ctx) -> Result:
    """A request to REDUCE control belongs in a re-assessment somebody signs,
    not in a backlog. So the two directions must differ."""
    vid, urn = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    _record(ctx, vid)
    got = _conclude(ctx, vid, tier_verdict="should_be_lower",
                    tier_note="the exposure is overstated")
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    tiering = _findings(ctx, urn, "tiering")
    if tiering:
        return FAIL, ("asking to reduce control raised a finding, so the two "
                      "directions are treated alike and a request to relax "
                      "sits in the remediation queue")
    return PASS, "no finding; reducing control needs a re-assessment"


@case("QA-AM-017", "Conclude rejected over a failed test")
def am_017(ctx: Ctx) -> Result:
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    recorded = _record(ctx, vid, right=APART,
                       threshold=FAILS)
    if recorded.status_code >= 400:
        return BLOCKED, recorded.text[:170]
    if (recorded.json() or {}).get("passed"):
        return BLOCKED, "the fixture's failing test passed"
    got = _conclude(ctx, vid, outcome="rejected")
    if got.status_code >= 400:
        return FAIL, f"an episode could not be rejected: {got.text[:140]}"
    return PASS, "rejected over a failed test"


@case("QA-AM-1700", "Conclude approved over a failed test")
def am_1700(ctx: Ctx) -> Result:
    """The refusal has to name the alternative, or a validator's only move is
    to delete the result."""
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    recorded = _record(ctx, vid, right=APART,
                       threshold=FAILS)
    if recorded.status_code >= 400 or (recorded.json() or {}).get("passed"):
        return BLOCKED, "the fixture's failing test did not fail"
    got = _conclude(ctx, vid)
    if got.status_code < 400:
        return FAIL, "an episode was approved over a test that failed"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if "approved_with_conditions" not in got.text and "rejected" not in got.text:
        return FAIL, "the refusal names no alternative"
    return PASS, f"refused '{code_of(got)}', naming the alternatives"


@case("QA-AM-019", "Conclude approved_with_conditions with no conditions")
def am_019(ctx: Ctx) -> Result:
    """The failed-test refusal tells a validator to "conclude
    'approved_with_conditions' with the conditions written down". The check
    that a condition was written down is what makes that a real alternative
    rather than a rename of `approved`.
    """
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    recorded = _record(ctx, vid, right=APART,
                       threshold=FAILS)
    if recorded.status_code >= 400 or (recorded.json() or {}).get("passed"):
        return BLOCKED, "the fixture's failing test did not fail"
    got = _conclude(ctx, vid, outcome="approved_with_conditions",
                    conditions=[])
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    return FAIL, (
        "an episode with a failed test concluded 'approved_with_conditions' "
        "and NO conditions. `_check_approvable` runs only for 'approved', so "
        "the route the failure refusal points a validator towards accepts "
        "everything 'approved' refuses — a model with a failed test is "
        "approved under a longer name and the conditions the outcome is "
        "named for are absent")


@case("QA-AM-1701", "Conclude approved_with_conditions with no results either")
def am_1701(ctx: Ctx) -> Result:
    """The same door, reached from the no-evidence side."""
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _conclude(ctx, vid, outcome="approved_with_conditions",
                    conditions=["do better"])
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    return FAIL, (
        "an episode that examined nothing concluded "
        "'approved_with_conditions'; the no-results check guards 'approved' "
        "alone, so an unexamined model can be passed under a neighbouring "
        "outcome")


@case("QA-AM-018", "Conclude deferred while a blocking finding is open")
def am_018(ctx: Ctx) -> Result:
    """Deferring is the honest answer when something blocks, so it must not
    be refused for the reason approving is."""
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    _record(ctx, vid)
    got = _conclude(ctx, vid, outcome="deferred")
    if got.status_code >= 400:
        return FAIL, (f"an episode could not be deferred: {got.text[:140]}")
    return PASS, "deferred"


@case("QA-AM-1702", "An outcome that is not one")
def am_1702(ctx: Ctx) -> Result:
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _conclude(ctx, vid, outcome="mostly_fine")
    if got.status_code < 400:
        return FAIL, "an episode concluded with an outcome that is not one"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if not any(o in got.text for o in OUTCOMES):
        return FAIL, "the refusal does not name the four outcomes"
    return PASS, f"refused '{code_of(got)}', naming the {len(OUTCOMES)} outcomes"


@case("QA-AM-1703", "A tier verdict that is not one")
def am_1703(ctx: Ctx) -> Result:
    vid, _ = _episode(ctx)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _conclude(ctx, vid, tier_verdict="about_right")
    if got.status_code < 400:
        return FAIL, "a tier verdict outside the vocabulary was recorded"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if not any(t in got.text for t in TIER_VERDICTS):
        return FAIL, "the refusal does not name the three verdicts"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-013", "The tier moves between open and conclude")
def am_013(ctx: Ctx) -> Result:
    """`tier_at_open` is stamped at open, not read at conclude. A verdict of
    "remains appropriate" is unreadable without knowing which tier the
    validator was looking at when they formed it."""
    name = ctx.unique("cn")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess",
                 json={"exposure": 1_000.0, "purpose_class": "internal_report",
                       "feature_count": 3, "interpretable": True,
                       "uses_alternative_data": False})
    made = ctx.api.post(V, json={"urn": urn, "semver": "1.0.0",
                                 "kind": "initial",
                                 "validators": ["person/validator"]},
                        auth=ctx.people["risk"])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    vid, at_open = made.json()["id"], made.json().get("tier_at_open")
    ctx.api.post(f"{M}/{name}/assess",
                 json={"exposure": 5_000_000_000.0,
                       "purpose_class": "credit_decision",
                       "feature_count": 400, "interpretable": False,
                       "uses_alternative_data": True})
    now = ((ctx.api.get(f"{M}/{name}").json() or {}).get("model") or {}).get("tier")
    if now == at_open:
        return BLOCKED, f"the tier did not move in this fixture (still {now})"
    _record(ctx, vid)
    done = _conclude(ctx, vid)
    if done.status_code >= 400:
        return BLOCKED, done.text[:170]
    if done.json().get("tier_at_open") != at_open:
        return FAIL, (f"the episode now reports tier_at_open "
                      f"{done.json().get('tier_at_open')}; it was {at_open} "
                      f"when the validator formed their verdict, and the "
                      f"verdict is unreadable against the wrong tier")
    return PASS, f"tier_at_open stays {at_open} while the model moved to {now}"
