"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — parallel running: two versions answering the same inputs.

The thing that makes a parallel run evidence rather than an anecdote is the
PAIRING: two answers to the same input, keyed so they can be compared. So the
cases are about what happens when a pair is half-formed, when there are too
few of them to read a rate over, and when outcomes never arrive.
"""
from __future__ import annotations

from core.lifecycle.parallel import MIN_OUTCOME_COVERAGE, MIN_PAIRED
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

P = "/api/v1/parallel-runs"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("pr")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    for semver in ("1.0.0", "2.0.0"):
        ctx.api.post(f"{M}/{name}/versions", json={"semver": semver},
                     auth=ctx.people["developer"])
    return urn


def _open(ctx: Ctx, urn=None, **over):
    body = {"urn": urn or _model(ctx), "champion": "1.0.0",
            "challenger": "2.0.0",
            "purpose": "does the new scorecard decide differently",
            "tolerance": 1e-9}
    body.update(over)
    made = ctx.api.post(P, json=body, auth=ctx.people["risk"])
    return made, ((made.json() or {}).get("reference")
                  if made.status_code < 400 else "")


def _service(ctx: Ctx):
    """A principal holding `monitor:observe`.

    An observation is delivered by whatever ran the two models, not by a
    governance role — the same separation telemetry uses. Posting as `risk`
    answers `forbidden`, which is a refusal, which scores as a pass.
    """
    who = ctx.made.get("parallel_service")
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
                             f"{made.text[:170]}")
    ctx.made["parallel_service"] = (name, f"{name}-pw")
    return ctx.made["parallel_service"]


def _observe(ctx: Ctx, reference: str, key: str, champion=None,
             challenger=None):
    return ctx.api.post(f"{P}/{reference}/observations",
                        json={"input_key": key, "champion": champion,
                              "challenger": challenger},
                        auth=_service(ctx))


def _divergence(got) -> dict:
    """The pairing figures live under `divergence`, beside `run`."""
    return (got.json() or {}).get("divergence") or {}


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-GOV-6200", "A run comparing a version against itself")
def gov_6200(ctx: Ctx) -> Result:
    made, _ = _open(ctx, challenger="1.0.0")
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if not _reached(made):
        return BLOCKED, f"answered '{code_of(made)}' — not reached"
    if made.status_code < 400:
        return FAIL, "a version was run in parallel against itself"
    return PASS, f"refused '{code_of(made)}'"


@case("QA-GOV-6201", "A run with no stated purpose")
def gov_6201(ctx: Ctx) -> Result:
    """A comparison with no question produces a difference nobody can
    interpret."""
    made, _ = _open(ctx, purpose="   ")
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code < 400:
        return FAIL, "a parallel run was opened with no question"
    return PASS, f"refused '{code_of(made)}'"


@case("QA-GOV-6202", "Two runs open on one model")
def gov_6202(ctx: Ctx) -> Result:
    """Two comparisons over one model at once produce two answers to "is the
    challenger better", and neither is the one somebody reads."""
    urn = _model(ctx)
    first, _ = _open(ctx, urn)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again, _ = _open(ctx, urn)
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "two parallel runs are open on one model at once"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-GOV-6203", "An observation with no input key")
def gov_6203(ctx: Ctx) -> Result:
    """The key is what makes two answers a PAIR. Without it there are two
    numbers."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _observe(ctx, reference, "   ", champion=0.5, challenger=0.6)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an observation was recorded with no key, so two "
                      "answers cannot be paired")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-6204", "A half-formed pair is not a pair")
def gov_6204(ctx: Ctx) -> Result:
    """One side answering and the other not is the ordinary consequence of a
    router. Counting it as a comparison would make the difference rate
    describe whichever side happened to reply."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    for i in range(5):
        _observe(ctx, reference, f"k{i}", champion=0.5)
    # There is no `GET /parallel-runs/{reference}` — the reading is
    # `GET /parallel-runs?reference=`, and the item path answers 404.
    got = ctx.api.get(f"{P}?reference={reference}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    divergence = _divergence(got)
    if not divergence:
        return BLOCKED, f"no divergence block: {sorted(got.json() or {})}"
    if divergence.get("paired"):
        return FAIL, (f"{divergence['paired']} pair(s) were counted from five "
                      f"one-sided observations")
    if divergence.get("unpaired") != 5:
        return FAIL, (f"five one-sided observations report "
                      f"{divergence.get('unpaired')} unpaired")
    return PASS, f"{divergence['unpaired']} unpaired, 0 paired"


@case("QA-GOV-6205", "A pair completed by a second observation")
def gov_6205(ctx: Ctx) -> Result:
    """The other half: a champion answer and a challenger answer arriving
    separately under one key must join into a pair."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    if _observe(ctx, reference, "k1", champion=0.5).status_code >= 400:
        return BLOCKED, "the first side failed"
    if _observe(ctx, reference, "k1", challenger=0.6).status_code >= 400:
        return BLOCKED, "the second side failed"
    # There is no `GET /parallel-runs/{reference}` — the reading is
    # `GET /parallel-runs?reference=`, and the item path answers 404.
    got = ctx.api.get(f"{P}?reference={reference}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    if not _divergence(got).get("paired"):
        return FAIL, ("two sides of one input key did not join into a pair, "
                      "so a router answering asynchronously produces nothing")
    return PASS, "the two sides joined under one key"


@case("QA-GOV-6206", "Fewer pairs than a rate can be read over")
def gov_6206(ctx: Ctx) -> Result:
    """"Fewer than 30 pairs, so a rate over them is..." — the report has to
    say that rather than quoting a percentage of four."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    for i in range(4):
        _observe(ctx, reference, f"k{i}", champion=0.5, challenger=0.6)
    # There is no `GET /parallel-runs/{reference}` — the reading is
    # `GET /parallel-runs?reference=`, and the item path answers 404.
    got = ctx.api.get(f"{P}?reference={reference}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = _divergence(got)
    if body.get("enough_to_read") is not False:
        return FAIL, (f"four pairs report enough_to_read "
                      f"{body.get('enough_to_read')}, against a minimum of "
                      f"{MIN_PAIRED}")
    if str(MIN_PAIRED) not in str(body.get("detail") or ""):
        return FAIL, (f"the report does not state the {MIN_PAIRED}-pair "
                      f"threshold: {str(body.get('detail'))[:110]}")
    return PASS, f"four pairs, enough_to_read false, {MIN_PAIRED} named"


@case("QA-GOV-6207", "A run with nothing paired at all")
def gov_6207(ctx: Ctx) -> Result:
    """"Nothing has been paired yet, so there is nothing to..." — an empty
    run must not read as a run that found no differences."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    # There is no `GET /parallel-runs/{reference}` — the reading is
    # `GET /parallel-runs?reference=`, and the item path answers 404.
    got = ctx.api.get(f"{P}?reference={reference}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    detail = _divergence(got).get("detail") or ""
    if "nothing has been paired" not in detail.lower():
        return FAIL, (f"an empty run does not say it is empty, so it reads as "
                      f"one that found no differences: {detail[:110]}")
    return PASS, detail[:90]


@case("QA-GOV-6208", "Observe after the run concluded")
def gov_6208(ctx: Ctx) -> Result:
    """A comparison's figures are about a period. An observation arriving
    afterwards changes a number somebody already reported."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    # The conclusion vocabulary is closed: promote, reject, inconclusive.
    # Unlike the champion/challenger COMPARISON — which never recommends
    # promotion because MAYA does not run models — a parallel run is a
    # decision somebody took, and recording which they took is the point.
    done = ctx.api.post(f"{P}/{reference}/conclude",
                        json={"conclusion": "inconclusive",
                              "note": "too few pairs to read"},
                        auth=ctx.people["risk"])
    if done.status_code >= 400:
        return BLOCKED, f"could not conclude: {done.text[:140]}"
    got = _observe(ctx, reference, "late", champion=0.5, challenger=0.6)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an observation landed after the run concluded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-6209", "Outcome coverage is reported")
def gov_6209(ctx: Ctx) -> Result:
    """Two models disagreeing tells you they differ. Which is RIGHT needs
    outcomes, and a run with almost none has to say so rather than letting
    the disagreement rate stand in for an accuracy comparison."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    for i in range(10):
        _observe(ctx, reference, f"k{i}", champion=0.5, challenger=0.6)
    # There is no `GET /parallel-runs/{reference}` — the reading is
    # `GET /parallel-runs?reference=`, and the item path answers 404.
    got = ctx.api.get(f"{P}?reference={reference}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    text = str(got.json() or {})
    if "outcome" not in text:
        return FAIL, ("the run says nothing about outcome coverage, so a "
                      "disagreement rate stands in for an accuracy "
                      "comparison")
    return PASS, (f"outcome coverage reported; minimum "
                  f"{MIN_OUTCOME_COVERAGE:g}")
