"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — sealing a feature, and transferring who owns it.

A seal says *this definition will not move again*, which is what makes it safe
for something else to compose from. Every case here is about the two ways that
promise can be broken: the definition changing anyway, or the seal coming off
without a record.
"""
from __future__ import annotations

from tools.qa.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, expect_accepted,
                                       expect_refused, valid_body)

FEATURE = "/api/v1/features"


def _feature(ctx: Ctx, **over) -> str:
    """A defined feature, returned as its name."""
    body = valid_body(ctx, "POST", FEATURE,
                      name=ctx.unique("sf"), description="a QA feature",
                      dtype="float", entity="borrower", owner="owner")
    body.update(over)
    made = ctx.api.post(FEATURE, json=body)
    if made.status_code >= 400:
        raise AssertionError(f"could not define a feature: {made.text[:170]}")
    return body["name"]


def _seal(ctx: Ctx, name: str, **kw):
    return ctx.api.post(f"{FEATURE}/{name}/seal",
                        json={"note": "QA seal", **kw})


@case("QA-FX-104", "Amend a sealed feature")
def fx_104(ctx: Ctx) -> Result:
    """The whole promise. If a sealed definition can still move, everything
    composed from it is composed against something that no longer exists."""
    name = _feature(ctx)
    sealed = _seal(ctx, name)
    if sealed.status_code >= 400:
        return BLOCKED, f"could not seal: {sealed.text[:150]}"
    return expect_refused(
        ctx.api.post(f"{FEATURE}/{name}/amend",
                     json={"fields": {"description": "changed"}}),
        "feature_refused", "sealed", "registry_refused")


@case("QA-FX-106", "Seal an ephemeral feature")
def fx_106(ctx: Ctx) -> Result:
    """One of the two is wrong: a seal is a promise of permanence and
    `ephemeral` is a promise of the opposite."""
    name = _feature(ctx, ephemeral=True)
    got = _seal(ctx, name)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an ephemeral feature was sealed; the seal says this "
                      "will not move and the flag says it will be destroyed")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-107", "Seal a feature that is already sealed")
def fx_107(ctx: Ctx) -> Result:
    name = _feature(ctx)
    _seal(ctx, name)
    return expect_refused(_seal(ctx, name),
                          "feature_refused", "already_sealed")


@case("QA-FX-108", "Break a seal with no reason")
def fx_108(ctx: Ctx) -> Result:
    name = _feature(ctx)
    _seal(ctx, name)
    return expect_refused(
        ctx.api.post(f"{FEATURE}/{name}/break-seal", json={"reason": "   "}),
        "feature_refused", "reason_required", "validation_error")


@case("QA-FX-109", "Break a seal as somebody without the authority")
def fx_109(ctx: Ctx) -> Result:
    name = _feature(ctx)
    _seal(ctx, name)
    return expect_refused(
        ctx.api.post(f"{FEATURE}/{name}/break-seal",
                     json={"reason": "QA"}, auth=ctx.people["observer"]),
        "forbidden", "scope_insufficient", "feature_refused")


@case("QA-FX-110", "Seal, break, amend, re-seal — and the chain records all four")
def fx_110(ctx: Ctx) -> Result:
    name = _feature(ctx)
    before = ctx.made["evidence"].verify_chain()["length"]
    steps = [
        ("seal", _seal(ctx, name)),
        ("break", ctx.api.post(f"{FEATURE}/{name}/break-seal",
                               json={"reason": "the definition was wrong"})),
        ("amend", ctx.api.post(f"{FEATURE}/{name}/amend",
                               json={"fields": {"description": "corrected"}})),
        ("re-seal", _seal(ctx, name)),
    ]
    refused = [what for what, got in steps if got.status_code >= 400]
    if refused:
        return FAIL, (f"the sequence a seal is FOR could not be performed; "
                      f"refused at: {refused}")
    after = ctx.made["evidence"].verify_chain()["length"]
    if after - before < 4:
        return FAIL, (f"four acts and only {after - before} evidence node(s); "
                      f"a seal broken without a record is a seal that was "
                      f"never there")
    return PASS, f"four acts, {after - before} evidence nodes"


@case("QA-FX-111", "Transfer ownership of a sealed feature")
def fx_111(ctx: Ctx) -> Result:
    name = _feature(ctx)
    _seal(ctx, name)
    got = ctx.api.post(f"{FEATURE}/{name}/transfer",
                       json={"to": "risk", "reason": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-FX-112", "Transfer ownership to the current owner")
def fx_112(ctx: Ctx) -> Result:
    """A transfer that moves nothing still writes an evidence node saying
    ownership changed hands."""
    name = _feature(ctx)
    got = ctx.api.post(f"{FEATURE}/{name}/transfer",
                       json={"to": "owner", "reason": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a transfer to the current owner was recorded; the "
                      "chain now says ownership moved when it did not")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-113", "Transfer ownership to an empty name")
def fx_113(ctx: Ctx) -> Result:
    name = _feature(ctx)
    return expect_refused(
        ctx.api.post(f"{FEATURE}/{name}/transfer",
                     json={"to": "   ", "reason": "QA"}),
        "feature_refused", "validation_error", "owner_required",
        "unknown_principal")


@case("QA-FX-114", "created_by survives an ownership transfer")
def fx_114(ctx: Ctx) -> Result:
    """Who owns a thing now and who first defined it are different facts, and
    a transfer that overwrote the second would erase the only record of where
    a definition came from."""
    name = _feature(ctx)
    # There is no `GET /features/{name}`; a feature is read resolved.
    first = ctx.api.get(f"{FEATURE}/{name}/resolved")
    if first.status_code >= 400:
        return BLOCKED, first.text[:150]
    was = (first.json().get("feature") or first.json()).get("created_by")
    moved = ctx.api.post(f"{FEATURE}/{name}/transfer",
                         json={"to": "risk", "reason": "QA"})
    if moved.status_code >= 400:
        return BLOCKED, f"could not transfer: {moved.text[:150]}"
    after = ctx.api.get(f"{FEATURE}/{name}/resolved").json()
    after = after.get("feature") or after
    if after.get("created_by") != was:
        return FAIL, (f"created_by moved with the ownership: {was!r} -> "
                      f"{after.get('created_by')!r}")
    if after.get("owner") == "owner":
        return FAIL, "the owner did not move"
    return PASS, f"owner is now {after.get('owner')!r}, created_by unchanged"


@case("QA-FX-116", "Seal a feature that does not exist")
def fx_116(ctx: Ctx) -> Result:
    got = _seal(ctx, "qa-no-such-feature")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "sealing something that does not exist reported success"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-117", "Break a seal on a feature that was never sealed")
def fx_117(ctx: Ctx) -> Result:
    name = _feature(ctx)
    got = ctx.api.post(f"{FEATURE}/{name}/break-seal", json={"reason": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("breaking a seal that was never applied reported "
                      "success, and the chain now records a seal being broken "
                      "that never existed")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-118", "An unsealed feature can still be amended")
def fx_118(ctx: Ctx) -> Result:
    """The control has to be narrow. If nothing can be amended, the seal is
    not doing the work — the platform is."""
    name = _feature(ctx)
    return expect_accepted(
        ctx.api.post(f"{FEATURE}/{name}/amend",
                     json={"fields": {"description": "revised"}}))
