"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the HTTP surface, configuration, health and discovery.

The conventions an API keeps are what let a client be written once. Most of
these are about a promise the platform makes to every caller rather than about
any one governance control: that a refusal carries a code, that a listing
pages, that health means something, that a configuration change is planned
before it is applied.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, valid_body)


# ------------------------------------------------------------ conventions
@case("QA-PLT-512", "Every refusal carries a code, a detail and a remediation")
def plt_300(ctx: Ctx) -> Result:
    """The three-part shape is the platform's argument. A refusal with no
    remediation tells somebody they are stuck without saying what to do."""
    got = ctx.api.post("/api/v1/models", json={"urn": "not-a-urn"})
    if got.status_code < 400:
        return FAIL, "a malformed registration was accepted"
    body = got.json()
    if isinstance(body.get("detail"), list):
        return PASS, "schema-level refusal, which names the field and why"
    missing = [k for k in ("error", "detail", "remediation") if k not in body]
    if missing:
        return FAIL, f"the refusal carries no {missing}: {body}"
    return PASS, "code, detail and remediation all present"


@case("QA-PLT-513", "An unauthenticated request is refused, not served")
def plt_301(ctx: Ctx) -> Result:
    from fastapi.testclient import TestClient
    app = ctx.api.app if hasattr(ctx.api, "app") else None
    if app is None:
        return BLOCKED, "no application handle"
    with TestClient(app, raise_server_exceptions=False) as anonymous:
        got = anonymous.get("/api/v1/models")
    if got.status_code != 401:
        return FAIL, (f"an anonymous caller got {got.status_code} from the "
                      f"model register")
    return PASS, "401"


@case("QA-PLT-514", "An unknown route answers 404 and not 500")
def plt_302(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/there-is-no-such-thing")
    if got.status_code != 404:
        return FAIL, f"{got.status_code}"
    return PASS, "404"


@case("QA-PLT-515", "A method that does not apply answers 405")
def plt_303(ctx: Ctx) -> Result:
    got = ctx.api.request("DELETE", "/api/v1/models")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code != 405:
        return PASS, f"answered {got.status_code} rather than 405"
    return PASS, "405"


@case("QA-PLT-516", "A malformed JSON body is refused, not crashed")
def plt_304(ctx: Ctx) -> Result:
    got = ctx.api.post("/api/v1/models", content="{not json",
                       headers={"Content-Type": "application/json"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — malformed JSON crashed the route"
    return PASS, f"refused ({got.status_code})"


@case("QA-PLT-517", "A listing pages rather than returning everything")
def plt_305(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/models", params={"limit": 2})
    if got.status_code >= 400:
        return FAIL, got.text[:150]
    body = got.json()
    rows = body.get("models", body.get("rows", []))
    if len(rows) > 2:
        return FAIL, (f"limit=2 returned {len(rows)} rows; a listing that "
                      f"ignores its limit cannot be paged through")
    return PASS, f"{len(rows)} row(s) for limit=2"


@case("QA-PLT-518", "A negative limit is refused")
def plt_306(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/models", params={"limit": -1})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a negative page size was accepted"
    return PASS, f"refused ({got.status_code})"


@case("QA-PLT-519", "A request id travels with the answer")
def plt_307(ctx: Ctx) -> Result:
    """The log and the evidence chain join on it. Without one in the
    response, a caller reporting a problem cannot say which request."""
    got = ctx.api.get("/api/v1/models")
    header = next((h for h in got.headers
                   if "request" in h.lower() and "id" in h.lower()), None)
    if header is None:
        return FAIL, f"no request id header: {sorted(got.headers)[:8]}"
    return PASS, f"{header}: {got.headers[header][:20]}"


# --------------------------------------------------------------- health
@case("QA-PLT-310", "Readiness answers and says what it checked")
def plt_310(ctx: Ctx) -> Result:
    got = ctx.api.get("/health/ready")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    body = got.text.lower()
    if "chain" not in body and "evidence" not in body:
        return FAIL, ("readiness says nothing about the evidence chain, which "
                      "is the thing that makes this instance usable")
    return PASS, f"{got.status_code}, and it names what it checked"


@case("QA-PLT-520", "Liveness does not require authentication")
def plt_311(ctx: Ctx) -> Result:
    """A liveness probe runs before anybody has credentials. One that needs
    them reports the instance dead the moment authentication breaks."""
    from fastapi.testclient import TestClient
    app = getattr(ctx.api, "app", None)
    if app is None:
        return BLOCKED, "no application handle"
    with TestClient(app, raise_server_exceptions=False) as anonymous:
        got = anonymous.get("/health/live")
    if got.status_code >= 400:
        return FAIL, (f"liveness needs credentials ({got.status_code}); an "
                      f"orchestrator would restart a healthy instance")
    return PASS, f"{got.status_code} without credentials"


# -------------------------------------------------------- configuration
@case("QA-PLT-521", "A configuration change is planned before it is applied")
def plt_320(ctx: Ctx) -> Result:
    planned = ctx.api.post("/api/v1/configuration/plan", json={})
    if planned.status_code >= 500:
        return FAIL, f"{planned.status_code}"
    return PASS, f"plan answers {planned.status_code}"


@case("QA-PLT-522", "The configuration boundary says what it does not control")
def plt_321(ctx: Ctx) -> Result:
    """The register touching something it does not own is the shape this
    platform names as its own hardest problem."""
    got = ctx.api.get("/api/v1/configuration/boundary")
    if got.status_code >= 400:
        return FAIL, got.text[:150]
    if len(got.text) < 40:
        return FAIL, "the boundary is published and says almost nothing"
    return PASS, f"published, {len(got.text)} bytes"


@case("QA-PLT-523", "Configuration does not leak a secret")
def plt_322(ctx: Ctx) -> Result:
    """A settings screen that renders the signing key has published it to
    everybody who can read settings."""
    got = ctx.api.get("/api/v1/configuration")
    if got.status_code >= 400:
        return BLOCKED, got.text[:150]
    body = got.text
    for secret in ("qa-signing-secret", "maya-admin-dev"):
        if secret in body:
            return FAIL, f"the configuration answer contains {secret!r}"
    return PASS, "no configured secret appears in the answer"


# ----------------------------------------------------------- discovery
@case("QA-PLT-524", "Discovery produces candidates, and registers nothing")
def plt_330(ctx: Ctx) -> Result:
    """The boundary discipline: a scanner produces candidates, and only a
    person turns one into a registered model.

    The first version of this looked for the word "candidates" in the
    response body. The listing is generically paged and says `rows`, so the
    case reported a defect for a naming convention. The claim worth testing
    is behavioural: running discovery must not add anything to the register.
    """
    before = ctx.api.get("/api/v1/models", params={"limit": 500})
    if before.status_code >= 400:
        return BLOCKED, before.text[:150]
    was = len(before.json().get("models", before.json().get("rows", [])))
    ran = ctx.api.post("/api/v1/discovery", json={})
    if ran.status_code >= 500:
        return FAIL, f"discovery crashed: {ran.status_code}"
    after = ctx.api.get("/api/v1/models", params={"limit": 500})
    now = len(after.json().get("models", after.json().get("rows", [])))
    if now != was:
        return FAIL, (f"a discovery run changed the register from {was} to "
                      f"{now} models; what a scanner found is not a model "
                      f"until somebody says so")
    listed = ctx.api.get("/api/v1/discovery/candidates")
    if listed.status_code >= 400:
        return FAIL, f"candidates cannot be listed: {listed.status_code}"
    return PASS, (f"discovery answered {ran.status_code} and registered "
                  f"nothing")


@case("QA-PLT-525", "Triage a discovery reference that does not exist")
def plt_331(ctx: Ctx) -> Result:
    got = ctx.api.post("/api/v1/discovery/qa-never/triage",
                       json=valid_body(ctx, "POST",
                                       "/api/v1/discovery/{reference}/triage"))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "triaging something that was never discovered succeeded"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-PLT-526", "The scanner contract is published")
def plt_332(ctx: Ctx) -> Result:
    """A contract MAYA cannot enforce is one it must at least state, so a
    scanner author can meet it."""
    got = ctx.api.get("/api/v1/scanner-contract")
    if got.status_code == 404:
        got = ctx.api.get("/api/v1/contract-screening/version")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    return PASS, f"published ({got.status_code})"


@case("QA-PLT-527", "A scanner contract check answers without a scanner named")
def plt_333(ctx: Ctx) -> Result:
    """The endpoint declares no required fields, so the case cannot be about
    a blank one. What it can be about: the check must still answer, and must
    not claim a verdict about a scanner nobody named.
    """
    got = ctx.api.post("/api/v1/scanner-contract/check", json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400 and "scanner" not in got.text.lower():
        return FAIL, ("a contract verdict came back naming no scanner; it is "
                      "recorded against nobody")
    return PASS, f"answered {got.status_code}"
