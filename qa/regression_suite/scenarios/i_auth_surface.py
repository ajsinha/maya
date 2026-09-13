"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the HTTP door: sessions, CSRF and API keys.

Two doors into the same platform, and the interesting cases are the ones where
one door's rules leak into the other. A CSRF token is a browser control and
must not be demanded of a service; a service credential must not be usable to
walk through a browser session's authority.
"""
from __future__ import annotations

from core.authz.csrf import HEADER, META
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
KEYS = "/api/v1/api-keys"
#: The harness sets the CSRF header on the browser client for EVERY request,
#: so `headers={}` on one call removes nothing — httpx merges per-request
#: headers over the client's. Sending the header explicitly empty is what
#: actually drops it.
NO_CSRF = {HEADER: ""}


def _body(ctx: Ctx) -> dict:
    name = ctx.unique("ax")
    return {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **TIER}


@case("QA-PLT-325", "An API route under a session cookie with no CSRF token")
def plt_325(ctx: Ctx) -> Result:
    """A session cookie travels on every request the browser makes, including
    ones another site caused. The token is what distinguishes the two."""
    got = ctx.ui.post("/api/v1/models", json=_body(ctx), headers=NO_CSRF)
    if got.status_code < 400:
        return FAIL, ("a write was accepted on a session cookie with no CSRF "
                      "token, so any site can act as a signed-in user")
    if code_of(got) not in ("csrf_token_invalid", "csrf_token_missing"):
        return FAIL, f"refused '{code_of(got)}': {got.text[:130]}"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-326", "The same route under HTTP Basic with no CSRF token")
def plt_326(ctx: Ctx) -> Result:
    """A service has no cookie and no browser, so demanding a token of it
    would be a browser control applied where it protects nothing — and would
    make every API client carry a session."""
    got = ctx.api.post("/api/v1/models", json=_body(ctx))
    if got.status_code >= 400:
        return FAIL, (f"a service call with no CSRF token was refused "
                      f"'{code_of(got)}'; the browser control leaked onto the "
                      f"API door")
    return PASS, "accepted; CSRF is a browser control only"


@case("QA-PLT-327", "A CSRF token from one session used with another")
def plt_327(ctx: Ctx) -> Result:
    """A token that is not bound to the session it came from is a token
    anybody can obtain and everybody can use."""
    # The token lives in a `<meta name="csrf-token">` tag, not in a form
    # field, and the harness already holds this session's copy on the client.
    import re
    page = ctx.ui.get("/dashboard")
    found = re.search(rf'name="{META}"[^>]*content="([^"]+)"', page.text) or \
        re.search(rf'content="([^"]+)"[^>]*name="{META}"', page.text)
    token = found.group(1) if found else None
    if not token:
        return BLOCKED, "no CSRF token could be read from a page"
    got = ctx.observer.post("/api/v1/models", json=_body(ctx),
                            headers={HEADER: token})
    if got.status_code < 400:
        return FAIL, ("one session's CSRF token was accepted on another "
                      "session, so the token binds to nobody")
    return PASS, f"refused ({got.status_code}) across sessions"


@case("QA-PLT-330", "Sign in with the wrong password")
def plt_330(ctx: Ctx) -> Result:
    """The refusal must not say which half was wrong, or it is an account
    enumeration oracle."""
    wrong = ctx.ui.post("/login", data={"username": "admin",
                                        "password": "not-the-password"},
                        follow_redirects=False)
    unknown = ctx.ui.post("/login", data={"username": "qa-no-such-person",
                                          "password": "not-the-password"},
                          follow_redirects=False)
    if wrong.status_code < 400 and wrong.status_code not in (302, 303):
        return FAIL, f"a wrong password answered {wrong.status_code}"
    for word in ("no such user", "unknown user", "user not found",
                 "wrong password", "incorrect password"):
        if word in wrong.text.lower() or word in unknown.text.lower():
            return FAIL, (f"the sign-in refusal says '{word}', which tells an "
                          f"attacker which half was wrong")
    return PASS, "refused without saying which half was wrong"


@case("QA-PLT-331", "A next= parameter pointing off-site")
def plt_331(ctx: Ctx) -> Result:
    """An open redirect on a sign-in page is a phishing primitive: the link
    is genuinely this firm's domain."""
    got = ctx.ui.get("/login?next=https://evil.example.com/steal",
                     follow_redirects=False)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    landing = got.headers.get("location", "")
    if "evil.example.com" in landing or "evil.example.com" in got.text:
        return FAIL, (f"the sign-in page carries an off-site destination "
                      f"({landing or 'in the page body'}), which makes it a "
                      f"phishing link on this firm's own domain")
    return PASS, "the off-site destination is not carried"


@case("QA-PLT-332", "A principal suspended mid-session")
def plt_332(ctx: Ctx) -> Result:
    """Suspension has to bite on the next request, not at the next sign-in.
    A session that outlives the account is a leaver who still has access."""
    who = ctx.unique("susp")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["auditor"],
                              "password": f"{who}-password",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    creds = (who, f"{who}-password")
    if ctx.api.get("/api/v1/models", auth=creds).status_code >= 400:
        return BLOCKED, "the new principal could not read before suspension"
    gone = ctx.api.post(f"/api/v1/principals/{who}/suspend",
                        json={"reason": "left the firm"})
    if gone.status_code >= 400:
        return BLOCKED, f"could not suspend: {gone.text[:140]}"
    after = ctx.api.get("/api/v1/models", auth=creds)
    if after.status_code < 400:
        return FAIL, ("a suspended principal still authenticates, so a leaver "
                      "keeps access until their session happens to end")
    return PASS, f"refused ({after.status_code}) on the next request"


@case("QA-PLT-334", "Security headers on every response class")
def plt_334(ctx: Ctx) -> Result:
    """A header applied only to the happy path is a header an attacker
    reaches around by causing an error."""
    wanted = ("x-content-type-options", "x-frame-options",
              "content-security-policy")
    probes = {
        "200": ctx.ui.get("/dashboard"),
        "404": ctx.ui.get("/qa-no-such-page"),
        "403": ctx.observer.get("/admin/principals"),
    }
    missing = []
    for label, got in probes.items():
        if got is None:
            continue
        for header in wanted:
            if header not in {k.lower() for k in got.headers}:
                missing.append(f"{label}:{header}")
    if missing:
        return FAIL, f"security headers absent on some responses: {missing}"
    return PASS, f"{len(wanted)} headers present on 200, 404 and 403"


@case("QA-PLT-337", "An API key issued for an impossible lifetime")
def plt_337(ctx: Ctx) -> Result:
    """A key with no end is a credential nobody rotates; a key with no life
    is one nobody can use, and both are worth refusing at issue."""
    wrong = []
    for days in (0, -1, 366, 100_000):
        got = ctx.api.post(KEYS, json={"username": "admin",
                                       "name": ctx.unique("k"),
                                       "lifetime_days": days})
        if got.status_code < 400:
            wrong.append(days)
        elif got.status_code >= 500:
            return FAIL, f"{days} days crashed the endpoint ({got.status_code})"
    if wrong:
        return FAIL, f"these lifetimes were accepted: {wrong}"
    return PASS, "0, -1, 366 and 100000 days all refused"


@case("QA-PLT-339", "Revoke an API key twice")
def plt_339(ctx: Ctx) -> Result:
    made = ctx.api.post(KEYS, json={"username": "admin",
                                    "name": ctx.unique("k"),
                                    "lifetime_days": 30})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    kid = (made.json() or {}).get("id") or (made.json() or {}).get("key_id")
    if not kid:
        return BLOCKED, f"the issued key carries no id: {made.text[:130]}"
    first = ctx.api.post(f"{KEYS}/{kid}/revoke", json={"reason": "qa"})
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again = ctx.api.post(f"{KEYS}/{kid}/revoke", json={"reason": "qa"})
    if again.status_code < 400:
        return FAIL, ("a revoked key was revoked again, so the record shows "
                      "two revocations of one credential")
    return PASS, f"refused '{code_of(again) or again.status_code}'"


@case("QA-PLT-338", "A revoked key stops working")
def plt_338(ctx: Ctx) -> Result:
    """Revocation that does not bite immediately is a note in a table."""
    made = ctx.api.post(KEYS, json={"username": "admin",
                                    "name": ctx.unique("k"),
                                    "lifetime_days": 30})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    body = made.json() or {}
    secret = body.get("key") or body.get("secret") or body.get("token")
    kid = body.get("id") or body.get("key_id")
    if not secret or not kid:
        return BLOCKED, f"no usable key came back: {sorted(body)}"
    header = {"X-API-Key": secret}
    before = ctx.api.get("/api/v1/models", headers=header, auth=None)
    if before.status_code >= 400:
        return BLOCKED, f"the fresh key does not work: {before.text[:130]}"
    ctx.api.post(f"{KEYS}/{kid}/revoke", json={"reason": "qa"})
    after = ctx.api.get("/api/v1/models", headers=header, auth=None)
    if after.status_code < 400:
        return FAIL, "a revoked key still authenticates"
    return PASS, f"refused '{code_of(after) or after.status_code}' once revoked"


@case("QA-PLT-344", "SSO status on an instance with SSO unconfigured")
def plt_344(ctx: Ctx) -> Result:
    """Answering that it is not enabled is a fact; refusing the status
    endpoint would leave a caller unable to tell unconfigured from broken."""
    got = ctx.api.get("/api/v1/sso")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return FAIL, (f"the status endpoint refuses '{code_of(got)}' when SSO "
                      f"is unconfigured, so unconfigured and broken look the "
                      f"same")
    if "enabled" not in got.text.lower() and "configured" not in got.text.lower():
        return FAIL, f"the answer does not say whether SSO is on: {got.text[:120]}"
    return PASS, "answers that SSO is not enabled"


@case("QA-PLT-345", "The SSO login door on an instance with SSO unconfigured")
def plt_345(ctx: Ctx) -> Result:
    """The door itself must refuse rather than half-work."""
    got = ctx.ui.get("/auth/login", follow_redirects=False)
    if got.status_code >= 500 and got.status_code != 501:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400 and got.status_code not in (302, 303):
        return FAIL, ("the SSO login door answered normally with no provider "
                      "configured")
    return PASS, f"refused ({got.status_code})"
