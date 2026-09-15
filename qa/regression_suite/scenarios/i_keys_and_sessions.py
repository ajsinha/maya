"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the three ways in, and what each one narrows.

A **session** is ambient authority: the browser sends it whether or not the
person meant to act, which is why a state-changing request under one must carry
a CSRF token and a request under a credential the caller had to hold need not.

An **API key** narrows what its principal may do and never widens it. The
narrowing is applied at authentication rather than at issue, against what the
principal holds NOW — so a role removed or an account suspended reaches every
key that principal ever issued, immediately, with nobody remembering to revoke
them.

And **`last_used_at` is what says whether anybody noticed** a key still in use
after it lapsed. It is bumped on success only, which was once the whole problem:
a job hammering an expired key left no log line, no counter and nothing an
operator could find.
"""
from __future__ import annotations

import time

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
K = "/api/v1/api-keys"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _keys(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("api_keys")


def _issue(ctx: Ctx, username: str = "risk", scopes=("model:read",),
           days: float = 30.0, **over):
    body = {"username": username, "name": ctx.unique("key"),
            "scopes": list(scopes), "lifetime_days": days}
    body.update(over)
    return ctx.api.post(K, json=body)


def _bearer(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _service(ctx: Ctx):
    """A client carrying no credentials of its own.

    `ctx.api` has Basic credentials on the client, and httpx keeps them unless
    the request overrides — so a bearer token sent through it arrives beside an
    admin's Basic header and the case proves nothing about the key."""
    from fastapi.testclient import TestClient
    return TestClient(ctx.ui.app, raise_server_exceptions=False)


@case("QA-PLT-335", "An API key used on an endpoint that takes no permission")
def plt_335(ctx: Ctx) -> Result:
    """The scope check lives in `authorise`. A route that only
    AUTHENTICATES never reaches it, so a key narrowed to one permission
    reaches every such route regardless of its scope."""
    import pathlib
    issued = _issue(ctx, scopes=["model:read"])
    if issued.status_code >= 400:
        return BLOCKED, f"the key could not be issued: {issued.text[:150]}"
    secret = (issued.json() or {}).get("secret")
    service = _service(ctx)
    if not secret:
        return BLOCKED, f"the key carries no secret: {sorted(issued.json() or {})}"
    scoped = service.get(f"{M}", headers=_bearer(secret))
    if scoped.status_code >= 400:
        return BLOCKED, (f"the key cannot read models, which is its own scope: "
                         f"{scoped.text[:130]}")
    # A REAL model, so the scope check is what refuses rather than the
    # registry refusing an urn that does not resolve first.
    name = ctx.unique("ks")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **SHAPE}, auth=ctx.people["owner"])
    outside = service.post("/api/v1/findings",
                           json={"urn": f"maya://model/{name}",
                                 "severity": "High", "title": "t",
                                 "owner": "person/owner", "description": "d",
                                 "category": "general", "source": "validation"},
                           headers=_bearer(secret))
    if code_of(outside) != "outside_key_scope":
        return FAIL, (f"a permission outside the key's scope answered "
                      f"'{code_of(outside)}' rather than 'outside_key_scope'")
    unpermissioned = [
        "/api/v1/document-kinds", "/api/v1/document-subjects",
        "/api/v1/model-relations", "/api/v1/export-packs",
    ]
    reached = []
    for path in unpermissioned:
        got = service.get(path, headers=_bearer(secret))
        if got.status_code < 400:
            reached.append(path)
    if not reached:
        return PASS, ("every route this key touched went through the scope "
                      "check")
    authorising = sum(
        p.read_text(encoding="utf-8").count("self.authorise(")
        for p in pathlib.Path("routes").rglob("*.py"))
    only_principal = sum(
        p.read_text(encoding="utf-8").count("self.principal(request)")
        for p in pathlib.Path("routes").rglob("*.py"))
    return FAIL, (
        f"a key scoped to `model:read` alone read {len(reached)} route(s) that "
        f"take no permission — {reached}. The scope check is inside "
        f"`Routes.authorise`, and about {only_principal} call sites use "
        f"`self.principal(request)` instead (against {authorising} that "
        f"authorise), so none of those consults `api_key_scopes`. Every one of "
        f"them is informational, which is why this is narrow — but the stated "
        f"rule is that a key narrows what its principal may do, and on those "
        f"routes it narrows nothing. A key issued for one read reaches the "
        f"document taxonomy, the relation vocabulary and the pack contents")


@case("QA-PLT-336", "A key whose owner loses the role after it was issued")
def plt_336(ctx: Ctx) -> Result:
    """The narrowing happens at authentication against what the principal
    holds NOW. A role removed reaches every key that principal issued, with
    nobody remembering to revoke them."""
    who = ctx.unique("keyowner")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_risk_manager"],
                              "password": f"{who}-pw",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, f"the principal could not be created: {made.text[:150]}"
    issued = _issue(ctx, username=who, scopes=["model:read"])
    if issued.status_code >= 400:
        return BLOCKED, f"the key could not be issued: {issued.text[:150]}"
    secret = (issued.json() or {})["secret"]
    service = _service(ctx)
    before = service.get(M, headers=_bearer(secret))
    if before.status_code >= 400:
        return BLOCKED, f"the key does not work to begin with: {before.text[:130]}"
    stripped = ctx.api.put(f"/api/v1/principals/{who}/roles",
                           json={"roles": []})
    if stripped.status_code >= 400:
        return BLOCKED, f"the role could not be removed: {stripped.text[:150]}"
    after = service.get(M, headers=_bearer(secret))
    if after.status_code < 400:
        return FAIL, (f"the key still reads models after its owner lost every "
                      f"role ({after.status_code}); the narrowing is frozen at "
                      f"issue rather than read at use")
    if after.status_code not in (401, 403):
        return FAIL, f"refused {after.status_code}: {after.text[:140]}"
    return PASS, (f"the same key answers {before.status_code} before the role "
                  f"is removed and {after.status_code} ('{code_of(after)}') "
                  f"after, with nothing revoked")


@case("QA-PLT-342", "An expired key used repeatedly")
def plt_342(ctx: Ctx) -> Result:
    """Refused by name rather than as an unknown credential — an anonymous
    401 tells the caller to send an API key, which is the credential they
    are already sending. And `last_used_at` must not move: it is what makes
    *this key stopped being used* answerable."""
    keys = _keys(ctx)
    if keys is None:
        return BLOCKED, "no API key register is wired"
    issued = _issue(ctx, scopes=["model:read"], days=30)
    if issued.status_code >= 400:
        return BLOCKED, f"the key could not be issued: {issued.text[:150]}"
    body = issued.json() or {}
    secret, key_id = body["secret"], body.get("id") or body.get("key_id")
    service = _service(ctx)
    service.get(M, headers=_bearer(secret))
    row = keys.repo.one(id=key_id) if key_id else None
    if row is None:
        rows = [r for r in keys.repo.many() if r["name"] == body["name"]]
        row = rows[0] if rows else None
    if row is None:
        return BLOCKED, "the issued key cannot be found in the register"
    keys.repo.set({"expires_at": time.time() - 86400}, id=row["id"])
    used_at = keys.repo.one(id=row["id"])["last_used_at"]
    codes = set()
    for _ in range(20):
        got = service.get(M, headers=_bearer(secret))
        codes.add((got.status_code, code_of(got)))
    after = keys.repo.one(id=row["id"])
    if any(status < 400 for status, _ in codes):
        return FAIL, f"an expired key still authenticated: {codes}"
    if codes != {(401, "key_expired")}:
        return FAIL, (f"twenty calls with an expired key answered {codes} "
                      f"rather than a single 401 'key_expired'")
    if after["last_used_at"] != used_at:
        return FAIL, (f"`last_used_at` moved on a refused call "
                      f"({used_at} → {after['last_used_at']}), so a lapsed key "
                      f"in heavy use reads as a key in healthy use")
    return PASS, ("twenty calls, all 401 'key_expired' by name, and "
                  "`last_used_at` unchanged")


@case("QA-PLT-341", "Concurrent authentications with one key",
      isolated=True)
def plt_341(ctx: Ctx) -> Result:
    """`use_count = use_count + 1` in SQL rather than read-then-write in
    Python. A key is authenticated on every request a service makes, so this
    is the most concurrent write in the platform, and an undercount hides an
    unused key rather than inventing traffic."""
    from concurrent.futures import ThreadPoolExecutor
    keys = _keys(ctx)
    if keys is None:
        return BLOCKED, "no API key register is wired"
    issued = _issue(ctx, scopes=["model:read"])
    if issued.status_code >= 400:
        return BLOCKED, f"the key could not be issued: {issued.text[:150]}"
    body = issued.json() or {}
    secret = body["secret"]
    service = _service(ctx)
    rows = [r for r in keys.repo.many() if r["name"] == body["name"]]
    if not rows:
        return BLOCKED, "the issued key cannot be found in the register"
    key_id = rows[0]["id"]
    before = keys.repo.one(id=key_id)["use_count"]
    calls = 50
    outcomes = []

    def call(_n):
        got = service.get(M, headers=_bearer(secret))
        outcomes.append(got.status_code)

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(call, range(calls)))
    after = keys.repo.one(id=key_id)["use_count"]
    served = sum(1 for s in outcomes if s < 400)
    if served != calls:
        return FAIL, (f"{calls - served} of {calls} concurrent calls were "
                      f"refused: {sorted(set(outcomes))}")
    if after - before != calls:
        return FAIL, (f"{calls} authentications incremented the count by "
                      f"{after - before}; an undercount makes a key in daily "
                      f"use look abandoned")
    return PASS, f"{calls} concurrent calls, use_count {before} → {after}"


@case("QA-PLT-343", "A session cookie, HTTP Basic and an API key on one request")
def plt_343(ctx: Ctx) -> Result:
    """Three credentials, one request. Whichever wins has to win
    deterministically and be the one the answer is authorised against —
    silently picking the widest is how a narrowly-scoped key becomes a full
    session."""
    from fastapi.testclient import TestClient
    issued = _issue(ctx, scopes=["model:read"])
    if issued.status_code >= 400:
        return BLOCKED, f"the key could not be issued: {issued.text[:150]}"
    secret = (issued.json() or {})["secret"]
    with TestClient(ctx.ui.app, raise_server_exceptions=False) as browser:
        browser.post("/login", data={"username": "admin",
                                     "password": "maya-admin-dev"},
                     follow_redirects=False)
        landing = browser.get("/dashboard")
        if "sign in" in landing.text[:4000].lower():
            return BLOCKED, "could not establish a session"
        #  A permission the KEY does not carry but the session's admin does.
        all_three = browser.post(
            "/api/v1/findings",
            json={"urn": "maya://model/nope", "severity": "High",
                  "title": "t", "owner": "o", "description": "d",
                  "category": "general", "source": "validation"},
            headers={**_bearer(secret),
                     "Authorization": f"Bearer {secret}"})
    code = code_of(all_three)
    if code == "outside_key_scope":
        return PASS, ("the key wins and narrows the request, so the widest "
                      "credential does not silently take over")
    if all_three.status_code in (401, 403):
        return PASS, (f"refused '{code or all_three.status_code}' — the "
                      f"request is authorised against one credential")
    if all_three.status_code < 400:
        return FAIL, (
            f"a request carrying a session cookie AND a key scoped to "
            f"`model:read` performed `finding:raise` ({all_three.status_code}). "
            f"The session won and the key's narrowing was discarded, so "
            f"presenting a narrowly-scoped key alongside a browser session "
            f"widens it back to the session's authority")
    return PASS, f"refused {all_three.status_code}: {all_three.text[:110]}"


@case("QA-PLT-328", "A CSRF token replayed after sign-out and back in")
def plt_328(ctx: Ctx) -> Result:
    """A token belongs to a session. Signing out ends the session, so the
    token minted under it must not act under the next one — a token that
    outlived its session is a token an attacker can hold."""
    from core.authz import csrf
    from fastapi.testclient import TestClient
    import re
    with TestClient(ctx.ui.app, raise_server_exceptions=False) as browser:
        browser.post("/login", data={"username": "admin",
                                     "password": "maya-admin-dev"},
                     follow_redirects=False)
        page = browser.get("/dashboard")
        found = re.search(rf'name="{csrf.META}"[^>]*content="([^"]+)"',
                          page.text)
        if not found:
            return BLOCKED, "no CSRF token on the dashboard"
        stale = found.group(1)
        browser.get("/logout")
        browser.post("/login", data={"username": "admin",
                                     "password": "maya-admin-dev"},
                     follow_redirects=False)
        again = browser.get("/dashboard")
        fresh = re.search(rf'name="{csrf.META}"[^>]*content="([^"]+)"',
                          again.text)
        if not fresh:
            return BLOCKED, "no CSRF token after signing back in"
        if fresh.group(1) == stale:
            return FAIL, ("the same CSRF token is minted for the session "
                          "before and after a sign-out, so signing out does "
                          "not invalidate it")
        name = ctx.unique("csrf")
        replayed = browser.post(
            M, json={"urn": f"maya://model/{name}", "name": name,
                     "owner": "owner", **SHAPE},
            headers={csrf.HEADER: stale})
    if replayed.status_code < 400:
        return FAIL, ("a CSRF token from a previous session was accepted "
                      "after signing out and back in")
    if code_of(replayed) != "csrf_token_invalid":
        return FAIL, f"refused '{code_of(replayed)}' rather than csrf_token_invalid"
    return PASS, ("a new token is minted on the new session and the old one "
                  "is refused 'csrf_token_invalid'")


@case("QA-PLT-329", "Two tabs, one form submitted after the other signed out")
def plt_329(ctx: Ctx) -> Result:
    """The ordinary way this is met: a page open in one tab, a sign-out in
    another. The refusal has to say RELOAD, because a person told only that
    their token is invalid has no idea they are looking at a dead page."""
    from core.authz import csrf
    from fastapi.testclient import TestClient
    import re
    with TestClient(ctx.ui.app, raise_server_exceptions=False) as browser:
        browser.post("/login", data={"username": "admin",
                                     "password": "maya-admin-dev"},
                     follow_redirects=False)
        page = browser.get("/models/new")
        found = re.search(rf'name="{csrf.META}"[^>]*content="([^"]+)"',
                          page.text)
        if not found:
            page = browser.get("/dashboard")
            found = re.search(rf'name="{csrf.META}"[^>]*content="([^"]+)"',
                              page.text)
        if not found:
            return BLOCKED, "no CSRF token on the form page"
        held = found.group(1)
        browser.get("/logout")                       # the other tab
        name = ctx.unique("tab")
        submitted = browser.post(
            M, json={"urn": f"maya://model/{name}", "name": name,
                     "owner": "owner", **SHAPE},
            headers={csrf.HEADER: held})
    if submitted.status_code < 400:
        return FAIL, "a form submitted after signing out was accepted"
    code = code_of(submitted)
    if code == "unauthenticated":
        return PASS, ("the session is gone before the token is looked at, so "
                      "the refusal is 'unauthenticated'")
    if code != "csrf_token_invalid":
        return FAIL, f"refused '{code}' at {submitted.status_code}"
    remediation = (submitted.json() or {}).get("remediation") or ""
    if "reload" not in remediation.lower():
        return FAIL, (f"the refusal does not tell the person to reload: "
                      f"{remediation[:140]}")
    return PASS, f"refused 'csrf_token_invalid': {remediation[:110]}"


@case("QA-PLT-333", "A session older than its maximum age")
def plt_333(ctx: Ctx) -> Result:
    """A session that outlives its maximum age is an unattended browser
    somebody walked away from. The cookie's own `max_age` is what ends it,
    so the value has to reach the cookie rather than only the config."""
    import inspect

    import run_maya_web
    source = inspect.getsource(run_maya_web)
    setting = [ln.strip() for ln in source.splitlines()
               if "session_max_age" in ln]
    if not setting:
        return FAIL, ("nothing reads `auth.session_max_age`, so a session "
                      "never expires on its own")
    line = setting[0]
    if "max_age=" not in line:
        return FAIL, (f"`auth.session_max_age` is read and not passed as the "
                      f"cookie's max_age: {line[:120]}")
    import re
    found = re.search(r"session_max_age\", (\d+)", line)
    if not found:
        return FAIL, (f"`auth.session_max_age` is passed to the cookie with no "
                      f"shipped default, so an instance that does not set it "
                      f"has no maximum: {line[:120]}")
    shipped = int(found.group(1))
    if shipped <= 0:
        return FAIL, f"the shipped default session maximum age is {shipped}"
    if shipped > 86400:
        return FAIL, (f"the shipped default is {shipped / 3600:.0f} hours; an "
                      f"unattended browser stays signed in for more than a day")
    cfg = ctx.ui.app.state.ctx["config"]
    configured = cfg.get_int("auth.session_max_age", shipped)
    return PASS, (f"`auth.session_max_age` is read and passed as the cookie's "
                  f"max_age with a shipped default of {shipped}s "
                  f"({shipped / 3600:.0f}h); this instance resolves "
                  f"{configured}s")
