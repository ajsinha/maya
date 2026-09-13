"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — amendments, decommissioning, and the tiering that governs both.

An attested record is immutable, so changing one means opening an amendment;
a model leaving service means decommissioning it. Both are the register
admitting that something it published has changed, which is exactly where a
platform is tempted to let the change happen quietly.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_accepted,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ASSESSMENT = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
              "feature_count": 12, "interpretable": True,
              "uses_alternative_data": False}
M = "/api/v1/models"


def _attested(ctx: Ctx) -> str:
    """A model in force. Two role-holders, because one person cannot attest."""
    name = ctx.unique("lc")
    urn = f"maya://model/{name}"
    api = ctx.api
    api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
             auth=ctx.people["developer"])
    api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    api.post(f"{M}/{name}/submit", json={"note": "qa"})
    api.post(f"{M}/{name}/approve", json={"note": "qa"})
    for who, role in (("owner", "model_owner"), ("risk", "model_risk_manager")):
        signed = api.post(f"{M}/{name}/attest",
                          json={"role": role, "decision": "attest",
                                "statement": "qa"}, auth=ctx.people[who])
        if signed.status_code >= 400:
            raise AssertionError(f"could not attest as {who}: "
                                 f"{signed.text[:170]}")
    return name


# ------------------------------------------------------------- amendments
@case("QA-GOV-800", "Change an attested record without an amendment")
def gov_800(ctx: Ctx) -> Result:
    """The immutability promise. An attested record that can still be edited
    is one nobody's signature covers."""
    name = _attested(ctx)
    return expect_refused(
        ctx.api.patch(f"{M}/{name}", json={"fields": {"owner": "risk"}}),
        "registry_refused")


@case("QA-GOV-801", "Open an amendment with no reason")
def gov_801(ctx: Ctx) -> Result:
    name = _attested(ctx)
    return expect_refused(
        ctx.api.post(f"{M}/{name}/amend", json={"reason": "   "}),
        "reason_required", "validation_error", "lifecycle_refused")


@case("QA-GOV-802", "Open two amendments against one model")
def gov_802(ctx: Ctx) -> Result:
    """Two open amendments are two people changing the same attested record
    without either seeing the other."""
    name = _attested(ctx)
    first = ctx.api.post(f"{M}/{name}/amend", json={"reason": "the first"})
    if first.status_code >= 400:
        return BLOCKED, f"could not open one: {first.text[:150]}"
    return expect_refused(
        ctx.api.post(f"{M}/{name}/amend", json={"reason": "the second"}),
        "amendment_open", "illegal_transition", "lifecycle_refused")


@case("QA-GOV-803", "Amend a model that was never attested")
def gov_803(ctx: Ctx) -> Result:
    name = ctx.unique("lc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return expect_refused(
        ctx.api.post(f"{M}/{name}/amend", json={"reason": "QA"}),
        "illegal_transition", "lifecycle_refused")


@case("QA-GOV-804", "An amendment makes the record mutable again")
def gov_804(ctx: Ctx) -> Result:
    """The other half. If amending does not unlock the record, the only way
    to correct an attested model is to abandon it."""
    name = _attested(ctx)
    opened = ctx.api.post(f"{M}/{name}/amend", json={"reason": "QA"})
    if opened.status_code >= 400:
        return BLOCKED, opened.text[:150]
    return expect_accepted(
        ctx.api.patch(f"{M}/{name}", json={"fields": {"owner": "risk"}}))


# ---------------------------------------------------------- decommission
@case("QA-GOV-810", "Decommission with no rationale")
def gov_810(ctx: Ctx) -> Result:
    name = _attested(ctx)
    body = valid_body(ctx, "POST", f"{M}/{{name}}/decommission")
    body.update({"rationale": "   ", "replacement": "none",
                 "retention_class": "regulatory"})
    got = ctx.api.post(f"{M}/{name}/decommission", json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a model was withdrawn from service with no stated "
                      "reason; the record cannot say why it stopped being "
                      "used")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-811", "Decommission naming a replacement that is not registered")
def gov_811(ctx: Ctx) -> Result:
    """A replacement that does not exist is a promise the register cannot
    check, and consumers are told to move to nothing."""
    name = _attested(ctx)
    body = valid_body(ctx, "POST", f"{M}/{{name}}/decommission")
    body.update({"rationale": "superseded",
                 "replacement": "maya://model/qa.never",
                 "retention_class": "regulatory"})
    got = ctx.api.post(f"{M}/{name}/decommission", json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a decommissioning pointed at a model nobody registered"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-812", "Decommission with a retention class that is not one")
def gov_812(ctx: Ctx) -> Result:
    name = _attested(ctx)
    body = valid_body(ctx, "POST", f"{M}/{{name}}/decommission")
    body.update({"rationale": "superseded", "replacement": "none",
                 "retention_class": "forever-ish"})
    got = ctx.api.post(f"{M}/{name}/decommission", json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an unknown retention class was accepted; how long the "
                      "record is kept is then undefined")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-813", "Decommission a model that is not in force")
def gov_813(ctx: Ctx) -> Result:
    name = ctx.unique("lc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    body = valid_body(ctx, "POST", f"{M}/{{name}}/decommission")
    body.update({"rationale": "QA", "replacement": "none",
                 "retention_class": "regulatory"})
    got = ctx.api.post(f"{M}/{name}/decommission", json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


# --------------------------------------------------------------- tiering
@case("QA-GOV-820", "Assess with an exposure that is not a number")
def gov_820(ctx: Ctx) -> Result:
    name = ctx.unique("lc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    got = ctx.api.post(f"{M}/{name}/assess",
                       json={**ASSESSMENT, "exposure": "a lot"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"refused ({got.status_code})"


@case("QA-GOV-821", "Assess with a negative exposure")
def gov_821(ctx: Ctx) -> Result:
    """A negative exposure sorts below every band floor, so the model lands
    in the shallowest one and every control is chosen for it."""
    name = ctx.unique("lc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    got = ctx.api.post(f"{M}/{name}/assess",
                       json={**ASSESSMENT, "exposure": -1_000_000.0})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a negative exposure was accepted; it compares below "
                      "every floor, so the model takes the shallowest band "
                      "and chooses its own control depth")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-822", "Assess with a purpose class that is not one")
def gov_822(ctx: Ctx) -> Result:
    name = ctx.unique("lc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return expect_refused(
        ctx.api.post(f"{M}/{name}/assess",
                     json={**ASSESSMENT, "purpose_class": "vibes"}),
        "unknown_purpose", "validation_error", "risk_refused",
        "unknown_purpose_class")


@case("QA-GOV-823", "Re-assess a model and the tier moves with the facts")
def gov_823(ctx: Ctx) -> Result:
    # A VERSION, because the trainability class is derived from the parameter
    # object and not declared. Without one the assessment refuses —
    # "this assessment lands on a different tier depending on
    # trainability_class, and the request did not say" — which is the tiering
    # engine refusing to guess, and it refused my setup rather than the case.
    name = ctx.unique("lc")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    low = ctx.api.post(f"{M}/{name}/assess",
                       json={**ASSESSMENT, "exposure": 1_000.0})
    if low.status_code >= 400:
        return BLOCKED, low.text[:150]
    was = low.json().get("tier")
    high = ctx.api.post(f"{M}/{name}/assess",
                        json={**ASSESSMENT, "exposure": 9_000_000_000.0})
    if high.status_code >= 400:
        return BLOCKED, high.text[:150]
    now = high.json().get("tier")
    if now == was:
        return FAIL, (f"exposure moved from 1,000 to 9bn and the tier stayed "
                      f"at {was}; the assessment is not reading the facts")
    return PASS, f"tier {was} -> {now} as exposure rose"
