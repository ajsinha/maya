"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the interface, and what a screen must not do.

Section E already opens every screen twice. These ask the questions a status
code cannot: that a page reachable from the bar is reachable by clicking, that
a refusal renders as a sentence rather than a stack trace, and that no screen
prints something the person reading it is not entitled to see.
"""
from __future__ import annotations

import re

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("ui")
    ctx.api.post("/api/v1/models", json={"urn": f"maya://model/{name}",
                                         "name": name, "owner": "owner",
                                         **TIER})
    return name


@case("QA-PLT-900", "Every navbar entry is reachable by clicking")
def plt_900(ctx: Ctx) -> Result:
    """A screen nobody can click to is not built. The bar is permission
    driven, so a page missing from it is a page only its author knows."""
    from qa.regression_suite.enumerate import screens
    page = ctx.ui.get("/dashboard")
    if page.status_code >= 400:
        return BLOCKED, f"{page.status_code}"
    linked = set(re.findall(r'href="(/[a-z0-9/_-]*)"', page.text))
    listed = {path for path, _title, _perm in screens()}
    # The dashboard links the top level; a section page links the rest.
    unreachable = []
    for path in sorted(listed):
        if path in linked or path == "/dashboard":
            continue
        parent = "/" + path.strip("/").split("/")[0]
        if parent in linked:
            continue
        unreachable.append(path)
    if unreachable:
        return FAIL, (f"these navbar entries are not linked from the "
                      f"dashboard or a parent: {unreachable[:8]}")
    return PASS, f"{len(listed)} navbar entries, all reachable"


@case("QA-PLT-901", "A refused screen renders a sentence, not a stack trace")
def plt_901(ctx: Ctx) -> Result:
    """The refusal is the thing the person reads. A traceback teaches them
    the platform is broken when it is working."""
    got = ctx.observer.get("/admin/principals")
    body = got.text.lower()
    # Markers that only a traceback produces. `"line "` was in the first
    # version and matched `line-height` in the stylesheet, so the case
    # reported a stack trace on a page that had none — a probe loose enough
    # to match ordinary English is a probe that finds it everywhere.
    for leak in ("traceback (most recent call last)", 'file "/',
                 "sqlalchemy.exc", "self.app(scope"):
        if leak in body:
            return FAIL, f"the refused page contains {leak!r}"
    return PASS, f"answered {got.status_code}, no trace in the body"


@case("QA-PLT-902", "A screen for a subject that does not exist says so")
def plt_902(ctx: Ctx) -> Result:
    got = ctx.ui.get("/model/qa-no-such-model")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code == 200 and "not found" not in got.text.lower():
        return FAIL, ("a page for a model that does not exist rendered as a "
                      "model page")
    return PASS, f"answered {got.status_code}"


@case("QA-PLT-903", "No screen prints a configured secret")
def plt_903(ctx: Ctx) -> Result:
    """A settings screen that renders the signing key has published it to
    everybody who can read settings."""
    for path in ("/dashboard", "/admin", "/admin/configuration", "/settings"):
        got = ctx.ui.get(path)
        if got.status_code >= 400:
            continue
        for secret in ("qa-signing-secret", "maya-admin-dev"):
            if secret in got.text:
                return FAIL, f"{path} contains {secret!r}"
    return PASS, "no configured secret appears on any screen checked"


@case("QA-PLT-904", "Every page carries a CSRF token")
def plt_904(ctx: Ctx) -> Result:
    """Without it every mutating control on the page is refused, and the
    person is told their session is wrong when it is not."""
    from core.authz.csrf import META
    got = ctx.ui.get("/dashboard")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    if META not in got.text:
        return FAIL, f"no {META!r} meta tag on the dashboard"
    return PASS, "the token is on the page"


@case("QA-PLT-905", "A model page shows the state and what may follow it")
def plt_905(ctx: Ctx) -> Result:
    """Somebody looking at a record needs to know what they may do next, or
    they find out by trying and being refused."""
    name = _model(ctx)
    got = ctx.ui.get(f"/model/{name}")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.text.lower()
    if "draft" not in body:
        return FAIL, "the model page does not show the lifecycle state"
    if "submit" not in body and "retire" not in body:
        return FAIL, ("the page shows the state and not what may follow it")
    return PASS, "state and available transitions are both shown"


@case("QA-PLT-906", "The evidence screen renders without walking the chain")
def plt_906(ctx: Ctx) -> Result:
    """The regression: `/dashboard` re-hashed the whole chain on every load,
    2.9 seconds and 83MB at forty thousand nodes."""
    import inspect

    from routes import ui_routes
    source = inspect.getsource(ui_routes)
    if "verify_chain()" in source:
        return FAIL, "a UI route still walks the whole chain on every load"
    return PASS, "the interface takes the incremental path"


@case("QA-PLT-907", "A page renders for a principal with almost no permissions")
def plt_907(ctx: Ctx) -> Result:
    """The observer holds `model:read`. The estate page must render for them
    rather than erroring, because a refusal and a crash look the same to
    somebody who only sees the result."""
    got = ctx.observer.get("/models")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code}"


@case("QA-PLT-908", "Sign in, sign out, and the session is really gone")
def plt_908(ctx: Ctx, ) -> Result:
    from fastapi.testclient import TestClient
    app = getattr(ctx.ui, "app", None)
    if app is None:
        return BLOCKED, "no application handle"
    with TestClient(app, raise_server_exceptions=False) as browser:
        browser.post("/login", data={"username": "admin",
                                     "password": "maya-admin-dev"},
                     follow_redirects=False)
        inside = browser.get("/dashboard")
        if "sign in" in inside.text[:4000].lower():
            return BLOCKED, "could not sign in"
        browser.get("/logout")
        after = browser.get("/dashboard")
        if "sign in" not in after.text[:4000].lower():
            return FAIL, ("the dashboard still renders after signing out; "
                          "the session outlived the logout")
    return PASS, "signed out, and the page asks for credentials again"
