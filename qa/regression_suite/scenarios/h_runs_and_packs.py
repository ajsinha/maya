"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — telemetry arriving, a challenger running beside a champion, a
permission a supervisor gave, and the pack that reports all three.

Four subjects, chosen together because they are the chain by which a number
reaches a board: a stream delivers, a run compares, an approval bounds what may
be done, and a pack states the result. Each of them has a way of producing a
row that reads as evidence and is not — an empty delivery that refreshes the
clock, a run concluded on divergence alone, an approval with no regulator
behind it, a pack about no period.
"""
from __future__ import annotations

import time

from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of,
                                                  refused_by_the_control)

T = "/api/v1/telemetry"
M = "/api/v1/models"
P = "/api/v1/parallel-runs"
R = "/api/v1/regulatory-approvals"
B = "/api/v1/board-packs"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _service(ctx: Ctx):
    """`monitor:observe` is held by no human role — the principal that runs
    the model hands the scores over and stops there."""
    who = ctx.made.get("runs_service")
    if who:
        return who
    name = ctx.unique("svc")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": name, "display_name": name,
                              "roles": ["service"], "password": f"{name}-pw",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        raise AssertionError(f"could not mint a service: {made.text[:170]}")
    ctx.made["runs_service"] = (name, f"{name}-pw")
    return ctx.made["runs_service"]


def _version(ctx: Ctx, semver: str = "1.0.0") -> str:
    name = ctx.unique("rp")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": semver},
                 auth=ctx.people["developer"])
    return urn


def _rows(n: int):
    now = time.time()
    return [{"entity_id": f"e{i}", "scored_at": now - 60, "score": 0.5}
            for i in range(n)]


def _ingest(ctx: Ctx, urn: str, rows, **over):
    body = {"urn": urn, "semver": "1.0.0", "stream": "scores", "rows": rows,
            "sample_rate": 1.0, "source": "qa"}
    body.update(over)
    return ctx.api.post(T, json=body, auth=_service(ctx))


# ------------------------------------------------------------- telemetry
@case("QA-AM-635", "Telemetry for a model that does not exist")
def am_635(ctx: Ctx) -> Result:
    """Refused rather than held. A batch parked against an unknown URN is a
    delivery that reports as successful and reaches no monitor, and the stream
    it was meant for goes on reading as never delivered."""
    got = _ingest(ctx, f"maya://model/{ctx.unique('absent')}", _rows(4))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a batch was accepted against a model nobody registered, "
                      "so the delivery reports successful and reaches nothing")
    return PASS, f"refused '{code_of(got)}' ({got.status_code})"


@case("QA-AM-636", "A well-formed batch is accepted")
def am_636(ctx: Ctx) -> Result:
    """The case that makes the refusals mean something — and it asserts the
    COUNT, because a delivery accepted with rows silently dropped is the
    failure the whole stream is built to avoid."""
    urn = _version(ctx)
    got = _ingest(ctx, urn, _rows(25))
    if got.status_code >= 400:
        return FAIL, (f"a well-formed batch of 25 rows was refused "
                      f"'{code_of(got)}': {got.text[:150]}")
    body = got.json() or {}
    accepted = body.get("accepted") or body.get("rows") or body.get("count")
    if accepted != 25:
        return FAIL, (f"25 rows were delivered and the answer reports "
                      f"{accepted}, so rows were dropped without a refusal: "
                      f"{got.text[:130]}")
    return PASS, "25 row(s) delivered and 25 reported"


@case("QA-AM-637", "A negative sample rate")
def am_637(ctx: Ctx) -> Result:
    """The sample rate is what every count is divided by to get a population.
    A negative one produces a negative population, and a monitor over it
    compares a negative denominator to a threshold."""
    return refused_by_the_control(
        _ingest(ctx, _version(ctx), _rows(4), sample_rate=-0.5),
        "a batch was accepted with a negative sample rate, so every "
        "population derived from it is negative")


@case("QA-AM-638", "The same batch sent twice is not counted twice")
def am_638(ctx: Ctx) -> Result:
    """Accepted and flagged, not refused. Refusing an identical redelivery
    makes an ordinary retry an incident; counting it silently doubles every
    denominator the monitors divide by. The only honest answer is to take it
    and say it was a duplicate."""
    urn = _version(ctx)
    rows = _rows(10)
    first = _ingest(ctx, urn, rows)
    if first.status_code >= 400:
        return BLOCKED, f"the first delivery answered {first.status_code}"
    second = _ingest(ctx, urn, rows)
    if second.status_code >= 400:
        return FAIL, (f"an identical redelivery was REFUSED "
                      f"'{code_of(second)}', which makes an ordinary retry an "
                      f"incident")
    body = second.json() or {}
    if not body.get("duplicate"):
        accepted = body.get("accepted") or body.get("rows")
        return FAIL, (f"an identical redelivery was accepted reporting "
                      f"{accepted} row(s) and no `duplicate` flag, so every "
                      f"denominator the monitors divide by is doubled by a "
                      f"retry: {second.text[:120]}")
    return PASS, f"accepted and reported `duplicate: {body['duplicate']}`"


# -------------------------------------------------------- parallel runs
def _run(ctx: Ctx, **over):
    urn = _version(ctx)
    ctx.api.post(f"{M}/{urn.rsplit('/', 1)[-1]}/versions",
                 json={"semver": "2.0.0"}, auth=ctx.people["developer"])
    body = {"urn": urn, "champion": "1.0.0", "challenger": "2.0.0",
            "purpose": "a QA comparison", "tolerance": 1e-9}
    body.update(over)
    return ctx.api.post(P, json=body, auth=ctx.people["risk"])


@case("QA-AM-639", "A parallel run with no stated purpose")
def am_639(ctx: Ctx) -> Result:
    """The purpose is what the run is evidence FOR. Without it the record says
    two versions were compared and nothing about what question was being
    answered — and at the end, the conclusion can be about anything."""
    return refused_by_the_control(
        _run(ctx, purpose="   "),
        "a challenger ran beside a champion with no stated purpose, so the "
        "conclusion at the end answers no recorded question")


@case("QA-AM-640", "A challenger that is the same version as the champion")
def am_640(ctx: Ctx) -> Result:
    """A version compared against itself agrees perfectly, and a run that
    concludes *no material divergence* is then a promotion argument built on
    comparing something to a copy of itself."""
    got = _run(ctx, challenger="1.0.0")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a parallel run opened with the challenger and the "
                      "champion set to one version, so it will agree perfectly "
                      "and read as evidence the challenger is safe")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-641", "Conclude a parallel run with no note")
def am_641(ctx: Ctx) -> Result:
    """The pressure at the end of an expensive run is to conclude something
    rather than nothing, and the note is the only place that pressure is
    visible afterwards."""
    opened = _run(ctx)
    if opened.status_code >= 400:
        return BLOCKED, f"the run would not open: {opened.text[:130]}"
    reference = (opened.json() or {}).get("reference") or ""
    return refused_by_the_control(
        ctx.api.post(f"{P}/{reference}/conclude",
                     json={"conclusion": "inconclusive", "note": "  "},
                     auth=ctx.people["risk"]),
        "a parallel run was concluded with no note, so the reasoning behind "
        "the verdict is not on the record")


# -------------------------------------------------- regulatory approvals
def _approval(ctx: Ctx, **over):
    # `irb` — the kinds are a closed set of real permissions, and guessing a
    # plausible-sounding one is refused before the case's own subject is
    # reached.
    body = {"kind": "irb", "regulator": "PRA",
            "scope": "the IRB PD models in scope of the 2026 review",
            "granted_at": time.time() - 86400}
    body.update(over)
    return ctx.api.post(R, json=body, auth=ctx.people["risk"])


@case("QA-AM-642", "A regulatory approval with no regulator")
def am_642(ctx: Ctx) -> Result:
    """A permission with no grantor is not a permission. Recorded, it reads on
    every report as regulatory cover, and there is nobody to go back to when
    somebody asks what exactly was approved."""
    return refused_by_the_control(
        _approval(ctx, regulator="   "),
        "a regulatory approval was recorded with no regulator, so the firm "
        "holds cover from nobody")


@case("QA-AM-643", "A regulatory approval with no scope")
def am_643(ctx: Ctx) -> Result:
    """The scope is the whole content. An approval with none is read by the
    next person as covering whatever they are looking at."""
    return refused_by_the_control(
        _approval(ctx, scope=""),
        "a regulatory approval was recorded with no scope, so the next reader "
        "takes it as covering whatever they are looking at")


@case("QA-AM-644", "Withdraw a regulatory approval with no reason")
def am_644(ctx: Ctx) -> Result:
    """Withdrawal is the act somebody is asked about. *Why did the PRA
    withdraw this* is answered by exactly this field and by nothing else in
    the register."""
    made = _approval(ctx)
    if made.status_code >= 400:
        return BLOCKED, f"no approval to withdraw: {made.text[:130]}"
    body = made.json() or {}
    reference = body.get("reference") or body.get("id") or ""
    got = ctx.api.post(f"{R}/{reference}/withdraw", json={"reason": " "},
                       auth=ctx.people["risk"])
    if got.status_code == 404:
        return BLOCKED, "no withdraw route reaches this approval"
    return refused_by_the_control(
        got, "a regulatory approval was withdrawn with no reason, leaving the "
             "one question anybody asks about it unanswerable")


# ------------------------------------------------------------ board packs
@case("QA-AM-645", "A board pack preview does not create a pack")
def am_645(ctx: Ctx) -> Result:
    """Somebody preparing for a meeting must be able to look before the
    committee is minuted against what they find. A preview that cut a pack
    would make every rehearsal a record."""
    period = "2026-Q1"
    before = ctx.api.get(B, auth=ctx.people["risk"])
    if before.status_code >= 400:
        return BLOCKED, f"the listing answered {before.status_code}"
    started = len((before.json() or {}).get("packs") or [])
    preview = ctx.api.post(f"{B}/preview", json={"period": period},
                           auth=ctx.people["risk"])
    if preview.status_code >= 400:
        return BLOCKED, f"the preview answered {preview.status_code}: {preview.text[:120]}"
    after = ctx.api.get(B, auth=ctx.people["risk"])
    now = len((after.json() or {}).get("packs") or [])
    if now != started:
        return FAIL, (f"a preview created a pack ({started} -> {now}), so "
                      f"looking at what the committee would see is itself a "
                      f"record the committee is held to")
    if not (preview.json() or {}):
        return FAIL, "the preview created nothing and also showed nothing"
    return PASS, f"the preview showed the pack and the history stayed at {now}"


@case("QA-AM-646", "A board pack with no period")
def am_646(ctx: Ctx) -> Result:
    """The period is what the figures are ABOUT. A pack with none is a set of
    numbers with no statement of when, and it is indistinguishable a year
    later from a pack about any other quarter."""
    return refused_by_the_control(
        ctx.api.post(B, json={"period": "  ", "note": "a QA pack"},
                     auth=ctx.people["risk"]),
        "a board pack was cut with no period, so its figures describe no "
        "stated span of time")
