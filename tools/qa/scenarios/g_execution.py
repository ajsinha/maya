"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — warrants, aliases and the execution boundary.

These need a **governed** model: registered, versioned, tiered, submitted,
approved and attested by two different people. That last part is the reason
this fixture exists at all — `admin` holds every permission and none of the
roles, so it cannot sign an attestation, and a QA estate built on one
superuser cannot reach the state most of these cases are about.
"""
from __future__ import annotations

from tools.qa.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       expect_accepted, expect_refused)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ASSESSMENT = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
              "feature_count": 12, "interpretable": True,
              "uses_alternative_data": False}


def governed(ctx: Ctx, *, alias: bool = True) -> dict:
    """A model in force: attested, version approved, `prod/champion` bound.

    Longer than it looks, and every step is a control that refuses if it is
    skipped — which is what makes this fixture worth writing down:

    1. register, version, assess, submit, approve  — the record
    2. attest as **two different role-holders** — `admin` holds every
       permission and none of the roles, so it cannot sign at all
    3. approve the **version**, which is a separate act from approving the
       record: "an alias may only point at an approved version"
    4. move the alias as somebody who did **not** create the version —
       "the person who created a version may not promote it into an
       environment"

    Step 4 is why the developer creates the version and the risk manager moves
    the alias. Getting it wrong does not raise here; the alias move simply
    fails, and every later case about resolution then fails for a reason that
    has nothing to do with what it was asking.
    """
    name = ctx.unique("gx")
    urn = f"maya://model/{name}"
    api = ctx.api
    api.post("/api/v1/models",
             json={"urn": urn, "name": name, "owner": "owner", **TIER})
    api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
             auth=ctx.people["developer"])
    api.post(f"/api/v1/models/{name}/assess", json=ASSESSMENT)
    api.post(f"/api/v1/models/{name}/submit", json={"note": "qa"})
    api.post(f"/api/v1/models/{name}/approve", json={"note": "qa"})
    for who, role in (("owner", "model_owner"), ("risk", "model_risk_manager")):
        signed = api.post(f"/api/v1/models/{name}/attest",
                          json={"role": role, "decision": "attest",
                                "statement": "qa"},
                          auth=ctx.people[who])
        if signed.status_code >= 400:
            raise AssertionError(
                f"could not attest as {who}: {signed.text[:180]}")
    approved = api.post(f"/api/v1/models/{name}/versions/1.0.0/approve",
                        json={}, auth=ctx.people["risk"])
    if approved.status_code >= 400:
        raise AssertionError(
            f"could not approve the version: {approved.text[:180]}")
    if alias:
        moved = api.put(f"/api/v1/models/{name}/aliases",
                        json={"alias": "champion", "environment": "prod",
                              "semver": "1.0.0", "justification": "qa"},
                        auth=ctx.people["risk"])
        if moved.status_code >= 400:
            raise AssertionError(
                f"could not move the alias: {moved.text[:180]}")
    return {"name": name, "urn": urn}


def _issue(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "principal": "svc-pricing", "environment": "prod",
            "declared_use": "credit_decision"}
    body.update(over)
    return ctx.api.post("/api/v1/warrants", json=body)


# ------------------------------------------------------------------ warrants
@case("QA-FX-300", "A warrant over an attested model with an alias")
def fx_300(ctx: Ctx) -> Result:
    return expect_accepted(_issue(ctx, governed(ctx)["urn"]))


@case("QA-FX-301", "Resolving over a model that was never attested")
def fx_301(ctx: Ctx) -> Result:
    """Asserted on RESOLUTION, not on issue.

    Issuing is permitted over a draft model and that is the design: a grant
    records who may run what, and resolution is the gate that asks whether
    there is anything in force to run. The case originally asserted the
    refusal on the wrong act and reported the platform as broken for letting
    an intention be recorded.
    """
    name = ctx.unique("gx")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    _issue(ctx, urn)
    return expect_refused(
        ctx.api.post("/api/v1/resolve",
                     json={"urn": urn, "principal": "svc-pricing",
                           "environment": "prod",
                           "declared_use": "credit_decision"}),
        "not_found", "no_alias", "not_in_force")


@case("QA-FX-302", "A warrant over a model that does not exist")
def fx_302(ctx: Ctx) -> Result:
    return expect_refused(_issue(ctx, "maya://model/qa.never"),
                          "registry_refused", "not_found")


@case("QA-FX-303", "A warrant with an undeclared use")
def fx_303(ctx: Ctx) -> Result:
    return expect_refused(
        _issue(ctx, governed(ctx)["urn"], declared_use=""),
        "declared_use_required", "unknown_use", "validation_error",
        "use_not_declared")


@case("QA-FX-304", "Resolving in an environment with no alias")
def fx_304(ctx: Ctx) -> Result:
    """An alias is what an environment binds to. Without one there is nothing
    to point at, and guessing a version would be the register choosing what
    runs. Asserted at resolution, for the same reason as QA-FX-301."""
    made = governed(ctx, alias=False)
    _issue(ctx, made["urn"])
    return expect_refused(
        ctx.api.post("/api/v1/resolve",
                     json={"urn": made["urn"], "principal": "svc-pricing",
                           "environment": "prod",
                           "declared_use": "credit_decision"}),
        "not_found", "no_alias", "not_in_force")


@case("QA-FX-305", "Resolve a warrant after it is revoked")
def fx_305(ctx: Ctx) -> Result:
    made = governed(ctx)
    issued = _issue(ctx, made["urn"])
    if issued.status_code >= 400:
        return BLOCKED, f"could not issue: {issued.text[:160]}"
    revoked = ctx.api.post("/api/v1/warrants/revoke",
                           json={"urn": made["urn"], "reason": "qa"})
    if revoked.status_code >= 400:
        return BLOCKED, f"could not revoke: {revoked.text[:160]}"
    return expect_refused(
        ctx.api.post("/api/v1/resolve",
                     json={"urn": made["urn"], "principal": "svc-pricing",
                           "environment": "prod",
                           "declared_use": "credit_decision"}),
        "revoked", "revoked_epoch", "no_warrant", "not_found")


@case("QA-FX-306", "Revoking a warrant that was never issued")
def fx_306(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post("/api/v1/warrants/revoke",
                     json={"urn": "maya://model/qa.never", "reason": "qa"}),
        "registry_refused", "not_found", "no_warrant")


@case("QA-FX-307", "Revoking with an empty reason")
def fx_307(ctx: Ctx) -> Result:
    made = governed(ctx)
    _issue(ctx, made["urn"])
    return expect_refused(
        ctx.api.post("/api/v1/warrants/revoke",
                     json={"urn": made["urn"], "reason": "   "}),
        "reason_required", "validation_error")


# -------------------------------------------------------------------- aliases
@case("QA-FX-310", "Move an alias to a version that does not exist")
def fx_310(ctx: Ctx) -> Result:
    made = governed(ctx)
    return expect_refused(
        ctx.api.put(f"/api/v1/models/{made['name']}/aliases",
                    json={"alias": "champion", "environment": "prod",
                          "semver": "9.9.9", "justification": "qa"}),
        "registry_refused", "not_found", "unknown_version")


@case("QA-FX-311", "A second alias move where neither version declares a schema")
def fx_311(ctx: Ctx) -> Result:
    """Refused, and deliberately.

    The first move into an empty environment has no incumbent, so there is
    nothing to compare and it is allowed. A *second* move runs the variance
    proof — and when neither version declares an input schema the proof would
    be taken over the empty set and hold for any pair at all. The platform
    refuses rather than reporting a proof about nothing:

        an undeclared schema is not a permissive one, it is an unchecked one

    The case originally read this as a defect for refusing a no-op move. It is
    the same gate every move goes through, and it fails closed and names what
    to declare, which is the behaviour to keep.
    """
    made = governed(ctx)
    return expect_refused(
        ctx.api.put(f"/api/v1/models/{made['name']}/aliases",
                    json={"alias": "champion", "environment": "prod",
                          "semver": "1.0.0", "justification": "qa"},
                    auth=ctx.people["risk"]),
        "registry_refused")


@case("QA-FX-312", "An alias on a model that is not in force")
def fx_312(ctx: Ctx) -> Result:
    name = ctx.unique("gx")
    ctx.api.post("/api/v1/models", json={"urn": f"maya://model/{name}",
                                         "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"})
    got = ctx.api.put(f"/api/v1/models/{name}/aliases",
                      json={"alias": "champion", "environment": "prod",
                            "semver": "1.0.0", "justification": "qa"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} on a draft model"
    return PASS, (f"answered {got.status_code} "
                  f"{'(refused)' if got.status_code >= 400 else '(accepted)'}")


# ------------------------------------------------------- the execution boundary
@case("QA-FX-320", "The published cascade of what a warrant carries")
def fx_320(ctx: Ctx) -> Result:
    made = governed(ctx)
    issued = _issue(ctx, made["urn"])
    if issued.status_code >= 400:
        return BLOCKED, issued.text[:160]
    # The GRANT is not the descriptor. Issuing records who may run what;
    # resolving mints the signed, time-bounded document an engine acts on, and
    # the signature belongs to the second. Asserting it on the first was
    # asking the wrong object.
    resolved = ctx.api.post("/api/v1/resolve",
                            json={"urn": made["urn"],
                                  "principal": "svc-pricing",
                                  "environment": "prod",
                                  "declared_use": "credit_decision"})
    if resolved.status_code >= 400:
        return FAIL, f"could not resolve: {resolved.text[:180]}"
    body = str(resolved.json())
    missing = [f for f in ("signature", "expires_at") if f not in body]
    if missing:
        return FAIL, (f"the descriptor carries no {missing}; an engine cannot "
                      f"tell a live one from an expired one")
    return PASS, "the descriptor is signed and time-bounded"


@case("QA-FX-321", "A warrant states what it does NOT prove")
def fx_321(ctx: Ctx) -> Result:
    """`attested, not observed`. A descriptor that reads as proof of a
    governed run is the claim this platform refuses to make."""
    posture = ctx.api.get("/api/v1/execution-posture")
    if posture.status_code >= 400:
        return FAIL, f"{posture.status_code} {posture.text[:140]}"
    if "does_not_prove" not in posture.json():
        return FAIL, "the execution posture makes a claim with no caveat"
    return PASS, posture.json()["does_not_prove"][:110]


@case("QA-FX-322", "Unreported execution is visible")
def fx_322(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/execution-posture/unreported")
    if got.status_code >= 400:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    return PASS, f"{len(got.json().get('unreported', []))} live and silent"
