"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — single sign-on, and the line it must not cross.

SSO is **configured, not assumed**. An instance with no `auth.oidc.issuer` has
no provider at all, signs everybody in against the local principal register,
and the SSO endpoints refuse by name rather than failing in a way somebody has
to read a stack trace to understand.

**Authentication may come from a directory. Authorisation never does.** A token
is evidence about WHO is at the door and nothing else: no claim in it is a
permission, and no permission is read from one. What a directory can influence
is roles, and only through a mapping this platform declares —
`auth.oidc.roles.<group>` — with the group name as the key because that is what
the directory controls and the roles as the value because that is what MAYA
controls. The direction of that arrow is the whole point. Everything downstream
then authorises from the principal register exactly as it does for a locally
created account.

So the cases here ask three questions. Does an unconfigured instance fall back
cleanly? Can anything in a token or its claims reach the authoriser? And when
the directory does supply roles, is the register still the thing that decides?
"""
from __future__ import annotations

import inspect
import pathlib
import time

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _provider(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("oidc")


@case("QA-PLT-5202", "An instance with no identity provider configured")
def plt_5202(ctx: Ctx) -> Result:
    """SSO is configured, not assumed. With no issuer set there is no
    provider, local credentials are the way in, and the SSO endpoints say
    what is missing instead of failing obscurely."""
    from fastapi.testclient import TestClient
    provider = _provider(ctx)
    if provider is not None:
        return BLOCKED, "this instance has a provider configured"
    with TestClient(ctx.ui.app, raise_server_exceptions=False) as browser:
        began = browser.get("/auth/login", follow_redirects=False)
        landed = browser.get("/auth/callback?code=x&state=y",
                             follow_redirects=False)
        # The fallback: the local form still signs somebody in.
        browser.post("/login", data={"username": "admin",
                                     "password": "maya-admin-dev"},
                     follow_redirects=False)
        page = browser.get("/dashboard")
    if "sign in" in page.text[:4000].lower():
        return FAIL, ("with no identity provider configured, local "
                      "credentials do not sign anybody in either")
    for what, response in (("/auth/login", began), ("/auth/callback", landed)):
        if response.status_code < 400:
            return FAIL, (f"{what} answered {response.status_code} with no "
                          f"provider configured, so an unconfigured instance "
                          f"half-starts a login")
        if response.status_code >= 500 and code_of(response) != "sso_not_configured":
            return FAIL, (f"{what} answered {response.status_code} without "
                          f"naming the reason: {response.text[:140]}")
        if "sso_not_configured" not in response.text and \
                "local credentials" not in response.text:
            return FAIL, (f"{what} does not say SSO is unconfigured or point "
                          f"at local sign-in: {response.text[:150]}")
    return PASS, ("no provider is built without an issuer; both SSO endpoints "
                  "refuse 'sso_not_configured' naming local credentials, and "
                  "the local form still signs in")


@case("QA-PLT-5203", "No permission is ever read from a token or its claims")
def plt_5203(ctx: Ctx) -> Result:
    """The rule this whole module sits under: authentication may come from a
    directory, authorisation is the register's. Asserted against the
    authoriser rather than against prose — nothing on the permission path
    may consult a claim, a token or a group."""
    from core.authz.policy import AuthorizationPolicy
    hot = []
    for name in ("permits", "authorise", "visible", "scope"):
        method = getattr(AuthorizationPolicy, name, None)
        if method is None:
            continue
        source = inspect.getsource(method)
        for word in ("claims", "id_token", "groups", "oidc", "issuer"):
            if word in source:
                hot.append(f"{name} reads '{word}'")
    if hot:
        return FAIL, (f"the authoriser consults the directory: {hot}. A "
                      f"permission decided from a claim is a permission the "
                      f"directory grants")
    policy = pathlib.Path("core/authz/policy.py").read_text(encoding="utf-8")
    for word in ("claims", "id_token", "oidc"):
        if word in policy:
            return FAIL, (f"core/authz/policy.py mentions '{word}'; the "
                          f"authoriser and the directory are supposed to share "
                          f"nothing")
    principals = ctx.ui.app.state.ctx.get("principals")
    authz = ctx.ui.app.state.ctx.get("authz")
    if principals is None or authz is None:
        return BLOCKED, "no principal register or authoriser is wired"
    who = ctx.unique("claimant")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": [], "password": f"{who}-pw",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, f"the principal could not be created: {made.text[:150]}"
    person = principals.require(who)
    # A principal carrying every directory-shaped field somebody might hope
    # would be honoured.
    forged = {**person, "roles": [], "groups": ["maya-admins"],
              "claims": {"roles": ["admin"], "permissions": ["model:delete"]},
              "permissions": ["model:delete"], "scopes": ["model:delete"]}
    for permission in ("model:delete", "model:register", "principal:manage"):
        if authz.permits(forged, permission):
            return FAIL, (f"a principal with no roles was granted "
                          f"'{permission}' by a claim-shaped field on the "
                          f"principal dictionary")
    return PASS, ("the authoriser shares no vocabulary with the directory, and "
                  "claim-shaped fields on a principal grant nothing")


@case("QA-PLT-351", "Group claims mapping to two incompatible roles")
def plt_351(ctx: Ctx) -> Result:
    """Refused, and refused HERE rather than at the directory. A directory
    that can hand out a conflicting pair by mistake is the reason the check
    exists; honouring segregation of duties only for locally created
    principals would honour it where it is least needed."""
    from core.authz.common import AuthzError
    from core.authz.oidc import OidcProvider
    principals = ctx.ui.app.state.ctx.get("principals")
    evidence = ctx.ui.app.state.ctx.get("evidence")
    if principals is None or evidence is None:
        return BLOCKED, "no principal register is wired"
    from core.authz.roles import conflicts
    pairs = [("model_developer", "validator"),
             ("model_developer", "model_risk_manager")]
    conflicting = next((p for p in pairs if conflicts(list(p))), None)
    if conflicting is None:
        return BLOCKED, f"none of {pairs} is an incompatible pair"
    provider = OidcProvider(
        "https://issuer.example", "client", None,
        "https://maya.example/auth/callback", ("openid",), "groups",
        {"group-a": [conflicting[0]], "group-b": [conflicting[1]]},
        True, "preferred_username", fetch=lambda *a, **k: {})
    identity = provider.identity({
        "sub": "subject-1", "preferred_username": ctx.unique("dirperson"),
        "name": "A Directory Person", "groups": ["group-a", "group-b"]})
    if set(identity["roles"]) != set(conflicting):
        return BLOCKED, (f"the mapping produced {identity['roles']} rather "
                         f"than {list(conflicting)}")
    try:
        provider.sign_in(identity, principals, evidence, actor="qa")
    except AuthzError as exc:
        if exc.code != "incompatible_roles":
            return FAIL, f"refused '{exc.code}' rather than incompatible_roles"
        if principals.get(identity["username"]) is not None:
            return FAIL, ("refused, and the principal was created anyway")
        if "segregation of duties" not in str(getattr(exc, "remediation", "")):
            return FAIL, (f"the refusal does not say what accepting both would "
                          f"mean: {getattr(exc, 'remediation', '')[:130]}")
        return PASS, (f"refused 'incompatible_roles' for "
                      f"{list(conflicting)}, nothing created")
    return FAIL, (f"a directory placed one person in groups mapping to "
                  f"{list(conflicting)} and the login was accepted, so the "
                  f"directory decided segregation of duties")


@case("QA-PLT-350", "An unknown SSO identity with provisioning off")
def plt_350(ctx: Ctx) -> Result:
    """A governance register is not a place everybody in the directory
    should have a foothold in by default. Refused `not_provisioned`, and the
    remediation has to say what enabling it costs."""
    from core.authz.common import AuthzError
    from core.authz.oidc import OidcProvider
    principals = ctx.ui.app.state.ctx.get("principals")
    evidence = ctx.ui.app.state.ctx.get("evidence")
    if principals is None or evidence is None:
        return BLOCKED, "no principal register is wired"
    provider = OidcProvider(
        "https://issuer.example", "client", None,
        "https://maya.example/auth/callback", ("openid",), "groups",
        {"maya-validators": ["validator"]}, False, "preferred_username",
        fetch=lambda *a, **k: {})
    username = ctx.unique("stranger")
    identity = provider.identity({
        "sub": "subject-2", "preferred_username": username,
        "name": "A Stranger", "groups": ["maya-validators"]})
    try:
        provider.sign_in(identity, principals, evidence, actor="qa")
    except AuthzError as exc:
        if exc.code != "not_provisioned":
            return FAIL, f"refused '{exc.code}' rather than not_provisioned"
        if principals.get(username) is not None:
            return FAIL, "refused, and a principal was created anyway"
        remediation = str(getattr(exc, "remediation", ""))
        if "foothold" not in remediation and "deliberately" not in remediation:
            return FAIL, (f"the remediation does not say what turning "
                          f"provisioning on costs: {remediation[:130]}")
        return PASS, f"refused 'not_provisioned': {str(exc)[:110]}"
    return FAIL, ("an identity nobody registered was signed in with "
                  "provisioning off")


@case("QA-PLT-5204", "A directory sign-in overwrites locally granted roles")
def plt_5204(ctx: Ctx) -> Result:
    """When the mapping produces roles, `sign_in` writes them over whatever
    the register holds. That makes the directory the source of truth for
    roles on any instance with SSO on — which is a decision, and the
    question is whether it is a stated one and whether it is recorded."""
    from core.authz.oidc import OidcProvider
    principals = ctx.ui.app.state.ctx.get("principals")
    evidence = ctx.ui.app.state.ctx.get("evidence")
    if principals is None or evidence is None:
        return BLOCKED, "no principal register is wired"
    username = ctx.unique("bothways")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": username, "display_name": username,
                              "roles": ["model_risk_manager"],
                              "password": f"{username}-pw",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, f"the principal could not be created: {made.text[:150]}"
    provider = OidcProvider(
        "https://issuer.example", "client", None,
        "https://maya.example/auth/callback", ("openid",), "groups",
        {"maya-validators": ["validator"]}, True, "preferred_username",
        fetch=lambda *a, **k: {})
    provider.link_on_first_login = True
    identity = provider.identity({
        "sub": f"subject-{username}", "preferred_username": username,
        "name": username, "groups": ["maya-validators"]})
    before = set(principals.require(username)["roles"])
    try:
        provider.sign_in(identity, principals, evidence, actor="qa")
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        if code == "identity_not_linked":
            return PASS, ("an existing local principal is not linked to a "
                          "directory identity by matching names; an "
                          "administrator has to do it deliberately")
        return BLOCKED, f"the sign-in failed for another reason: {code}"
    after = set(principals.require(username)["roles"])
    if after == before:
        return PASS, (f"the directory sign-in left the register's roles "
                      f"unchanged: {sorted(after)}")
    recorded = [n for n in evidence.repo.many()
                if n["kind"] == "principal_signed_in_via_sso"]
    if not recorded:
        return FAIL, (f"the directory replaced {sorted(before)} with "
                      f"{sorted(after)} and nothing was appended to the chain")
    payload = recorded[-1].get("payload") or {}
    for key in ("groups", "mapped_from", "roles"):
        if key not in payload:
            return FAIL, (f"the sign-in was recorded without '{key}', so "
                          f"'why did they have that role in March' has no "
                          f"answer once the directory has moved on")
    return PASS, (
        f"the directory is the source of truth for roles while SSO is on: "
        f"{sorted(before)} → {sorted(after)} on sign-in. Authorisation is "
        f"still the register's — the roles are WRITTEN to it and read from it "
        f"— and the act is recorded with the groups, the mapping and the "
        f"resulting roles, which is what makes a past grant explainable")


@case("QA-PLT-348", "An id token dated in the future and one just expired")
def plt_348(ctx: Ctx) -> Result:
    """Both refused by name, and the leeway respected in both directions — a
    clock a few seconds out is the ordinary case, and refusing it makes
    sign-in flaky in a way somebody fixes by widening the window to hours.

    Driven through the real `_assert` with the signature step stubbed: a
    case that re-implements the comparison tests its own copy of the rule
    and would keep passing after the rule changed."""
    from core.authz.common import AuthzError
    from core.authz import oidc as module
    from core.authz.oidc import LEEWAY_SECONDS, OidcProvider
    from routes.base import STATUS
    provider = OidcProvider(
        "https://issuer.example", "client", None,
        "https://maya.example/auth/callback", ("openid",), "groups", {},
        False, "preferred_username", fetch=lambda url, form=None: {})
    provider._discovered = {"jwks_uri": "https://issuer.example/jwks"}
    provider._keys = {}
    now = 1_800_000_000.0
    base = {"iss": "https://issuer.example", "aud": "client",
            "sub": "s", "preferred_username": "u"}
    real_verify, real_keys = module.verify, OidcProvider.keys
    OidcProvider.keys = lambda self, refresh=False: {}
    outcomes = {}
    try:
        for what, claims in (
                ("expired", {**base, "exp": now - LEEWAY_SECONDS - 10}),
                ("just expired, inside leeway", {**base, "exp": now - 10}),
                ("future", {**base, "iat": now + LEEWAY_SECONDS + 10}),
                ("a moment ahead, inside leeway", {**base, "iat": now + 10})):
            module.verify = lambda token, keys, _c=claims: dict(_c)
            try:
                provider._assert({"id_token": "stub"}, None, now)
                outcomes[what] = "accepted"
            except AuthzError as exc:
                outcomes[what] = exc.code
    finally:
        module.verify, OidcProvider.keys = real_verify, real_keys
    if outcomes.get("expired") != "token_expired":
        return FAIL, f"an expired token answered {outcomes.get('expired')!r}"
    if outcomes.get("future") != "token_from_the_future":
        return FAIL, f"a future token answered {outcomes.get('future')!r}"
    inside = [v for k, v in outcomes.items() if "leeway" in k]
    if set(inside) != {"accepted"}:
        return FAIL, (f"a clock {LEEWAY_SECONDS:.0f}s out is refused: "
                      f"{outcomes}")
    for code in ("token_expired", "token_from_the_future"):
        if code not in STATUS:
            return FAIL, f"'{code}' is not mapped to a status"
    return PASS, (f"both refused by name through the real `_assert`, and both "
                  f"directions of a {LEEWAY_SECONDS:.0f}s leeway accepted: "
                  f"{outcomes}")


@case("QA-PLT-346", "A mismatched state, an expired pending login, a replayed nonce")
def plt_346(ctx: Ctx) -> Result:
    """Three separate refusals rather than one. A callback that answered the
    same thing to all three would leave nobody able to tell a misconfigured
    provider from an attack."""
    from core.authz.common import AuthzError
    from core.authz.oidc import STATE_TTL_SECONDS, OidcProvider
    from routes.base import STATUS
    discovery = {
        "authorization_endpoint": "https://issuer.example/authorize",
        "token_endpoint": "https://issuer.example/token",
        "jwks_uri": "https://issuer.example/jwks",
        "issuer": "https://issuer.example",
    }
    provider = OidcProvider(
        "https://issuer.example", "client", None,
        "https://maya.example/auth/callback", ("openid",), "groups", {},
        False, "preferred_username",
        fetch=lambda url, form=None: discovery)
    began = provider.begin("/dashboard")
    outcomes = {}
    try:
        provider.complete("code", began, "a-different-state", now=time.time())
        outcomes["state"] = "accepted"
    except AuthzError as exc:
        outcomes["state"] = exc.code
    except Exception as exc:
        outcomes["state"] = type(exc).__name__
    try:
        provider.complete("code", began, began["state"],
                          now=time.time() + STATE_TTL_SECONDS + 60)
        outcomes["expired"] = "accepted"
    except AuthzError as exc:
        outcomes["expired"] = exc.code
    except Exception as exc:
        outcomes["expired"] = type(exc).__name__
    try:
        provider.complete("code", None, began["state"], now=time.time())
        outcomes["no pending"] = "accepted"
    except AuthzError as exc:
        outcomes["no pending"] = exc.code
    except Exception as exc:
        outcomes["no pending"] = type(exc).__name__
    accepted = [k for k, v in outcomes.items() if v == "accepted"]
    if accepted:
        return FAIL, f"these were accepted: {accepted} ({outcomes})"
    if outcomes["state"] != "state_mismatch":
        return FAIL, f"a mismatched state answered {outcomes['state']!r}"
    if outcomes["expired"] != "login_expired":
        return FAIL, (f"a pending login older than "
                      f"{STATE_TTL_SECONDS:.0f}s answered "
                      f"{outcomes['expired']!r}")
    if len(set(outcomes.values())) < 3:
        return FAIL, (f"three different conditions give fewer than three "
                      f"answers: {outcomes}")
    unmapped = [v for v in outcomes.values() if v not in STATUS]
    if unmapped:
        return FAIL, f"these codes are not mapped to a status: {unmapped}"
    return PASS, f"three conditions, three named refusals: {outcomes}"
