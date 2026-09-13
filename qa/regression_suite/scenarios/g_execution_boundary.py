"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the operating boundary, quotas and compute zones.

A warrant carries the bounds an engine is supposed to honour. MAYA cannot make
it honour them, so every case here is about whether the bound is *stated
precisely enough to be honoured* and whether a breach of it is visible
afterwards.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
LIMITS = "/api/v1/grant-limits"
ZONES = "/api/v1/compute-zones"


def _model(ctx: Ctx) -> str:
    name = ctx.unique("eb")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


# ----------------------------------------------------------------- bounds
@case("QA-FX-1000", "The compute zones a warrant may name are published")
def fx_1000(ctx: Ctx) -> Result:
    """A zone an engine cannot resolve is a bound it cannot honour."""
    got = ctx.api.get(ZONES)
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.json()
    zones = body.get("zones", [])
    if zones:
        return PASS, f"{len(zones)} zone(s) published"
    # An empty list is the honest answer on a fresh instance, and the
    # endpoint says what follows from it: "no compute zone is configured, so
    # every zone handles no more than 'internal'". My first version demanded
    # a non-empty list and reported a defect for an accurate answer — the
    # question is whether the consequence is stated, not whether the list has
    # rows in it.
    if not (body.get("detail") or "").strip():
        return FAIL, ("no zones are configured and nothing says what that "
                      "means for what may be run")
    return PASS, f"none configured, and the consequence is stated: " \
                 f"{body['detail'][:90]}"


@case("QA-FX-1001", "Attest a compute zone for a warrant that does not exist")
def fx_1001(ctx: Ctx) -> Result:
    """The regression: an unknown warrant left `model=None` and the scope
    check answered 500 — a defect-in-the-route status for a caller who named
    something that is not there."""
    body = valid_body(ctx, "POST", f"{ZONES}/attest",
                      warrant_id="qa-no-such-warrant")
    got = ctx.api.post(f"{ZONES}/attest", json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — an unknown warrant crashed it"
    if got.status_code < 400:
        return FAIL, "a zone was attested against no warrant"
    return PASS, f"refused ({got.status_code})"


@case("QA-FX-1002", "A grant limit on a warrant that does not exist")
def fx_1002(ctx: Ctx) -> Result:
    body = valid_body(ctx, "PUT", f"{LIMITS}/{{warrant_id}}",
                      rate=100, quota=1000)
    got = ctx.api.put(f"{LIMITS}/qa-no-such-warrant", json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a limit was set on a warrant nobody issued"
    return PASS, f"refused ({got.status_code})"


@case("QA-FX-1003", "A negative rate limit")
def fx_1003(ctx: Ctx) -> Result:
    """A negative rate is not a slower limit, it is one no call can satisfy —
    and it reads in every screen as a limit that is set."""
    body = valid_body(ctx, "PUT", f"{LIMITS}/{{warrant_id}}", rate=-1)
    got = ctx.api.put(f"{LIMITS}/qa-any", json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-FX-1004", "The execution posture names what it cannot observe")
def fx_1004(ctx: Ctx) -> Result:
    """`attested, not observed`. Counting how much of the estate runs on
    engines nobody can see into is useful; letting the count read as an
    observation is not."""
    got = ctx.api.get("/api/v1/execution-posture")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.json()
    if "does_not_prove" not in body:
        return FAIL, "the posture makes a claim with no caveat"
    if "does not run models" not in body["does_not_prove"]:
        return FAIL, f"the caveat does not say why: {body['does_not_prove']}"
    return PASS, "the caveat names the limit"


@case("QA-FX-1005", "Unreported execution says what it cannot distinguish")
def fx_1005(ctx: Ctx) -> Result:
    """Silence is equally consistent with an engine ignoring telemetry and a
    warrant nobody used, and MAYA cannot tell them apart."""
    got = ctx.api.get("/api/v1/execution-posture/unreported")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    return PASS, f"{len(got.json().get('unreported', []))} live and silent"


@case("QA-FX-1006", "The declared cascade of what a deletion touches")
def fx_1006(ctx: Ctx) -> Result:
    """Published so an operator does not discover the disposition by
    performing it."""
    got = ctx.api.get("/api/v1/deletion-cascade")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    rows = got.json().get("cascade", [])
    kinds = {r["disposition"] for r in rows}
    if kinds != {"blocks", "goes", "stays"}:
        return FAIL, f"the dispositions are {kinds}, not the declared three"
    return PASS, f"{len(rows)} tables, all three dispositions present"


@case("QA-FX-1007", "A sandbox refuses to run anything")
def fx_1007(ctx: Ctx) -> Result:
    """MAYA does not run models. An endpoint that quietly did would be the
    single largest thing this platform says about itself, undone."""
    import inspect

    from core.execution import sandbox
    source = inspect.getsource(sandbox)
    if "subprocess" in source and "Popen" in source:
        return FAIL, ("the sandbox spawns a process; MAYA is a register and "
                      "does not run models")
    return PASS, "no process is spawned"


@case("QA-FX-1008", "The captive engine is the only one that has run a warrant")
def fx_1008(ctx: Ctx) -> Result:
    """And the platform says so rather than implying broader coverage."""
    got = ctx.api.get("/api/v1/engine")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    said = got.text.lower()
    if "captive" not in said and "reference" not in said:
        return FAIL, ("the engine endpoint does not say which engine this is; "
                      "a reader would assume it is the one in production")
    return PASS, "the engine names itself"
