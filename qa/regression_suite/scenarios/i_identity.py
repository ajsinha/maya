"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — principals, roles, API keys and export shares.

Who somebody is decides what they may do, so the failures here are the
quietest ones in the platform: an account with incompatible roles, a key that
outlives its purpose, a share that keeps reading after the matter closed.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_refused, valid_body)

PRINCIPALS = "/api/v1/principals"
ROLES = "/api/v1/roles"
KEYS = "/api/v1/api-keys"
SHARES = "/api/v1/export-shares"


def _person(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", PRINCIPALS, username=ctx.unique("p"),
                      display_name="QA person", roles=["model_owner"],
                      password="a-long-enough-qa-password")
    body.update(over)
    return ctx.api.post(PRINCIPALS, json=body)


# ------------------------------------------------------------- principals
@case("QA-PLT-600", "A principal with no roles")
def plt_600(ctx: Ctx) -> Result:
    """An account with no roles can authenticate and do nothing, which is an
    account somebody will grant roles to in a hurry."""
    got = _person(ctx, roles=[])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-PLT-601", "A principal with a role that does not exist")
def plt_601(ctx: Ctx) -> Result:
    return expect_refused(_person(ctx, roles=["chief_vibes_officer"]),
                          "unknown_role", "validation_error",
                          "principal_refused")


@case("QA-PLT-602", "A principal with incompatible roles")
def plt_602(ctx: Ctx) -> Result:
    """Segregation of duties is the point. One account holding both sides of
    a control can walk the whole path alone."""
    got = _person(ctx, roles=["model_developer", "validator"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("one account holds both the first and second line; the "
                      "separation every approval depends on is gone for that "
                      "person and nothing said so")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-603", "A principal with a password below the minimum")
def plt_603(ctx: Ctx) -> Result:
    return expect_refused(_person(ctx, password="short"),
                          "password_too_short", "validation_error",
                          "principal_refused", "weak_password")


@case("QA-PLT-604", "Two principals with the same username")
def plt_604(ctx: Ctx) -> Result:
    name = ctx.unique("p")
    _person(ctx, username=name)
    return expect_refused(_person(ctx, username=name),
                          "duplicate_principal", "principal_exists")


@case("QA-PLT-605", "Suspend a principal, then use their credentials")
def plt_605(ctx: Ctx) -> Result:
    made = _person(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    username = made.json()["username"]
    stopped = ctx.api.post(f"{PRINCIPALS}/{username}/suspend", json={})
    if stopped.status_code >= 400:
        return BLOCKED, f"could not suspend: {stopped.text[:150]}"
    got = ctx.api.get("/api/v1/models",
                      auth=(username, "a-long-enough-qa-password"))
    if got.status_code < 400:
        return FAIL, ("a suspended principal still authenticates; suspension "
                      "that does not reach the door is a label")
    return PASS, f"refused ({got.status_code})"


@case("QA-PLT-606", "Suspend the last administrator")
def plt_606(ctx: Ctx) -> Result:
    """The one refusal that protects the platform from being locked out of
    itself."""
    got = ctx.api.post(f"{PRINCIPALS}/admin/suspend", json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the last administrator was suspended; nobody can now "
                      "grant the role back")
    return PASS, f"refused '{code_of(got)}'"


# ------------------------------------------------------------------ roles
@case("QA-PLT-610", "A role granting a permission that does not exist")
def plt_610(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", ROLES, name=ctx.unique("role"),
                      description="QA role", permissions=["model:levitate"])
    return expect_refused(ctx.api.post(ROLES, json=body),
                          "unknown_permission", "validation_error",
                          "role_refused")


@case("QA-PLT-611", "A role with no permissions")
def plt_611(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", ROLES, name=ctx.unique("role"),
                      description="QA role", permissions=[])
    got = ctx.api.post(ROLES, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-PLT-612", "Redefine a built-in role")
def plt_612(ctx: Ctx) -> Result:
    """The eight roles are the segregation argument. A deployment that can
    rewrite `validator` can grant it `model:register`."""
    got = ctx.api.put(f"{ROLES}/validator",
                      json={"permissions": ["model:register"]})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a built-in role was redefined; the separation the "
                      "whole approval model rests on is editable")
    return PASS, f"refused '{code_of(got)}'"


# ---------------------------------------------------------------- api keys
@case("QA-PLT-620", "An API key for a principal that does not exist")
def plt_620(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", KEYS, username="qa-nobody",
                      name=ctx.unique("key"))
    return expect_refused(ctx.api.post(KEYS, json=body),
                          "no_such_principal", "not_found", "api_key_refused")


@case("QA-PLT-621", "An API key with a negative lifetime")
def plt_621(ctx: Ctx) -> Result:
    made = _person(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    body = valid_body(ctx, "POST", KEYS, username=made.json()["username"],
                      name=ctx.unique("key"), lifetime_days=-1)
    got = ctx.api.post(KEYS, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a key was issued that expired before it was created"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-622", "An API key scoped to a permission its holder lacks")
def plt_622(ctx: Ctx) -> Result:
    """A key cannot be a way to grant yourself more than you hold."""
    made = _person(ctx, roles=["auditor"])
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    body = valid_body(ctx, "POST", KEYS, username=made.json()["username"],
                      name=ctx.unique("key"), scopes=["model:delete"])
    got = ctx.api.post(KEYS, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a key was issued with a permission its holder does "
                      "not have; the key is now more powerful than the person")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-623", "Revoke an API key with no reason")
def plt_623(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"{KEYS}/qa-never/revoke", json={"reason": "   "}),
        "not_found", "no_such_key", "reason_required", "validation_error")


# ------------------------------------------------------------ export shares
@case("QA-PLT-630", "A share with no stated purpose")
def plt_630(ctx: Ctx) -> Result:
    """A share sends part of the register outside the firm. Why is the only
    thing that makes it reviewable afterwards."""
    body = valid_body(ctx, "POST", SHARES, urn="maya://model/qa.any",
                      recipient="somebody@example.com", purpose="   ",
                      content_digest="sha256:" + "0" * 64)
    got = ctx.api.post(SHARES, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("part of the register was shared outside the firm with "
                      "no stated purpose")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-631", "A share with no recipient")
def plt_631(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", SHARES, urn="maya://model/qa.any",
                      recipient="   ", purpose="QA",
                      content_digest="sha256:" + "0" * 64)
    got = ctx.api.post(SHARES, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a share was created with nobody to send it to"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-632", "A share that never expires")
def plt_632(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", SHARES, urn="maya://model/qa.any",
                      recipient="somebody@example.com", purpose="QA",
                      content_digest="sha256:" + "0" * 64, days=0)
    got = ctx.api.post(SHARES, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"
