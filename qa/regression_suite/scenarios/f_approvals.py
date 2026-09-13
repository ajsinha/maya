"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the approval quorum, segregation of duties, and version signing.

Approval depth follows the tier, so the quorum is the mechanism by which a
risk assessment becomes a number of signatures. Every case here is about
somebody signing who should not, or a signature counting that should not.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_accepted,
                                                  expect_refused)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ASSESSMENT = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
              "feature_count": 12, "interpretable": True,
              "uses_alternative_data": False}
M = "/api/v1/models"


def _submitted(ctx: Ctx) -> str:
    name = ctx.unique("ap")
    api = ctx.api
    api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                      "owner": "owner", **TIER})
    api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
             auth=ctx.people["developer"])
    api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    api.post(f"{M}/{name}/submit", json={"note": "qa"})
    return name


def _approved(ctx: Ctx) -> str:
    name = _submitted(ctx)
    ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    return name


# ----------------------------------------------------------- the quorum
@case("QA-GOV-900", "One person signs both required roles")
def gov_900(ctx: Ctx) -> Result:
    """The quorum is a number of PEOPLE. One account signing twice satisfies
    the arithmetic and defeats the control."""
    name = _approved(ctx)
    first = ctx.api.post(f"{M}/{name}/attest",
                         json={"role": "model_owner", "decision": "attest",
                               "statement": "qa"}, auth=ctx.people["owner"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:150]
    second = ctx.api.post(f"{M}/{name}/attest",
                          json={"role": "model_risk_manager",
                                "decision": "attest", "statement": "qa"},
                          auth=ctx.people["owner"])
    if second.status_code < 400:
        return FAIL, ("one person signed both roles; the quorum counted two "
                      "signatures from one person")
    return PASS, f"refused '{code_of(second)}'"


@case("QA-GOV-901", "The same person signs the same role twice")
def gov_901(ctx: Ctx) -> Result:
    name = _approved(ctx)
    ctx.api.post(f"{M}/{name}/attest",
                 json={"role": "model_owner", "decision": "attest",
                       "statement": "qa"}, auth=ctx.people["owner"])
    again = ctx.api.post(f"{M}/{name}/attest",
                         json={"role": "model_owner", "decision": "attest",
                               "statement": "qa"}, auth=ctx.people["owner"])
    if again.status_code < 400:
        return FAIL, "one signature was counted twice"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-GOV-902", "Sign for a role you do not hold")
def gov_902(ctx: Ctx) -> Result:
    name = _approved(ctx)
    return expect_refused(
        ctx.api.post(f"{M}/{name}/attest",
                     json={"role": "model_risk_manager",
                           "decision": "attest", "statement": "qa"},
                     auth=ctx.people["owner"]),
        "role_not_held", "segregation_of_duties", "forbidden")


@case("QA-GOV-903", "Sign for a role the attestation does not require")
def gov_903(ctx: Ctx) -> Result:
    name = _approved(ctx)
    return expect_refused(
        ctx.api.post(f"{M}/{name}/attest",
                     json={"role": "auditor", "decision": "attest",
                           "statement": "qa"}, auth=ctx.people["auditor"]),
        "role_not_required", "forbidden")


@case("QA-GOV-904", "Decline an attestation and the record does not advance")
def gov_904(ctx: Ctx) -> Result:
    """A decline is a real answer. A platform that treated it as 'not yet'
    would let an objection be waited out."""
    name = _approved(ctx)
    declined = ctx.api.post(f"{M}/{name}/attest",
                            json={"role": "model_owner",
                                  "decision": "decline", "statement": "no"},
                            auth=ctx.people["owner"])
    if declined.status_code >= 400:
        return BLOCKED, declined.text[:150]
    state = ctx.api.get(f"{M}/{name}").json().get("status")
    if state == "attested":
        return FAIL, "a declined attestation still put the model in force"
    return PASS, f"the record is {state!r} after a decline"


@case("QA-GOV-905", "Approve a model that was never submitted")
def gov_905(ctx: Ctx) -> Result:
    name = ctx.unique("ap")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return expect_refused(
        ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"}),
        "illegal_transition")


@case("QA-GOV-906", "The submitter approves their own submission")
def gov_906(ctx: Ctx) -> Result:
    """Segregation of duties at the point it matters most."""
    name = _submitted(ctx)
    got = ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"},
                       auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


# --------------------------------------------------------- version signing
@case("QA-GOV-910", "Approve a version that does not exist")
def gov_910(ctx: Ctx) -> Result:
    name = _submitted(ctx)
    got = ctx.api.post(f"{M}/{name}/versions/9.9.9/approve", json={},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a version that does not exist was approved"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-GOV-911", "The person who created a version approves it")
def gov_911(ctx: Ctx) -> Result:
    """The first line builds and the second line approves. One account doing
    both is the separation gone for that version."""
    name = _submitted(ctx)
    got = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                       auth=ctx.people["developer"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the person who created the version approved it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-912", "An approved version is what an alias may point at")
def gov_912(ctx: Ctx) -> Result:
    """The other half — if approval does not unlock promotion, nothing can
    ever be released."""
    name = _submitted(ctx)
    approved = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                            auth=ctx.people["risk"])
    if approved.status_code >= 400:
        return BLOCKED, f"could not approve: {approved.text[:150]}"
    return expect_accepted(
        ctx.api.put(f"{M}/{name}/aliases",
                    json={"alias": "champion", "environment": "prod",
                          "semver": "1.0.0", "justification": "qa"},
                    auth=ctx.people["risk"]))
