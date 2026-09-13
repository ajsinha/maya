"""
MAYA — the QA pass, as 314 runnable cases.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

    python docs/QA/qa_cases.py --enumerate            # the case table, no calls
    python docs/QA/qa_cases.py --run                  # run all of them
    python docs/QA/qa_cases.py --run QA-1             # run one prefix
    python docs/QA/qa_cases.py --run holds            # or one area
    python docs/QA/qa_cases.py --run --markdown       # results as a table

**The IDs are stable and are never renumbered.** `QA-001` means the same case
in every pass, so two passes can be compared rather than re-read. New cases are
appended; a case that turns out to be wrongly designed is re-stated in place
and its expectation changed, which is a visible edit rather than a silent one.

**Every case states its expectation before it runs**, as one of

    accepted    the act is permitted and the register records it
    refused:X   the platform says no, with the code named here in advance
    reported    no refusal, but the answer carries something to read
    EXPLORATORY the expectation could not be stated; what was learned is logged

A case whose expectation cannot be stated in advance is a case nobody
understands yet. It is written down anyway, marked EXPLORATORY.

**Run it against a throwaway instance.** These cases register, approve, attest,
decommission and delete; several depend on the estate `qa_setup.py` builds, and
they mutate it. Never point this at anything whose register matters.

    python run_maya_web.py --config /tmp/qa/application.yaml   # a temp data dir
    python docs/QA/qa_setup.py --url http://127.0.0.1:5399
    python docs/QA/qa_cases.py --url http://127.0.0.1:5399 --run

Ordering matters: the cases walk one estate forward through its lifecycle, so
they are written to run in ID order, once, against a freshly built estate.
"""
from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import pathlib
import re
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:5399"
V = "/api/v1"

#: The accounts `qa_setup.py` creates, plus the two this file makes itself.
USERS = {
    "admin": "maya-admin-dev",
    "q.tester": "qa-password-long",
    "s.iqbal": "mrm-password-long",
    "j.okafor": "owner-password-long",
    "a.mehta": "val-password-long",
    "d.raman": "dev-pw-long-enough",
    "r.hale": "aud-password-long",
    "o.perez": "ops-password-long",
    "p.dual": "dual-password-long",
    "uk.reader": "uk-password-long",
}

CTX: dict = {}
CASES: list = []
LAST: dict = {}
RESULTS: list = []
_SESSIONS: dict = {}


def call(method, path, user="admin", body=None, headers=None, form=None):
    """One API call, with HTTP Basic. `path` is absolute from the root."""
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("content-type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs.setdefault("content-type", "application/x-www-form-urlencoded")
    if user:
        secret = USERS.get(user)
        pair = f"{user}:{secret}" if secret else user
        hdrs["authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            payload, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        payload, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:                                # connection level
        return 0, None, f"TRANSPORT: {e}"
    try:
        parsed = json.loads(payload)
    except Exception:
        parsed = None
    LAST.update(status=status, parsed=parsed, payload=payload,
                call=f"{method} {path} (as {user or 'anonymous'})")
    return status, parsed, payload


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def page(path, user="admin"):
    """One SCREEN, through a browser session.

    The UI routes ignore HTTP Basic: they answer 200 and render the sign-in
    page. So a screen driven with Basic proves only that the login form still
    renders, which is how a whole pass of screen tests came to pass without
    reaching a single screen.
    """
    if user and user not in _SESSIONS:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar), _NoRedirect())
        data = urllib.parse.urlencode(
            {"username": user, "password": USERS[user], "next": "/dashboard"}).encode()
        try:
            opener.open(urllib.request.Request(BASE + "/login", data=data))
        except urllib.error.HTTPError:
            pass
        _SESSIONS[user] = opener
    opener = _SESSIONS.get(user) or urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(BASE + path) as r:
            payload, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        payload, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:
        return 0, None, f"TRANSPORT: {e}"
    LAST.update(status=status, parsed=None, payload=payload,
                call=f"GET {path} (session as {user or 'anonymous'})")
    return status, None, payload


def navbar_links(body):
    """Every in-app link the rendered page offers."""
    return sorted({h for h in re.findall(r'href="(/[a-z0-9\-/._]*)"', body or "")
                   if h not in ("/logout", "/docs")})


def case(cid, area, action, expect):
    def deco(fn):
        CASES.append(dict(id=cid, area=area, action=action, expect=expect, fn=fn))
        return fn
    return deco


def verdict_of(expect, status, parsed):
    if expect.startswith("EXPLORATORY"):
        return "EXPLORATORY"
    if expect.startswith("refused"):
        if status < 400:
            return "FAIL"
        want = expect.split(":", 1)[1].strip() if ":" in expect else "*"
        if want == "*":
            return "PASS"
        code = parsed.get("error") if isinstance(parsed, dict) else None
        for one in (w.strip() for w in want.split("|")):
            if (one.isdigit() and int(one) == status) or code == one:
                return "PASS"
        return "FAIL"
    if expect in ("accepted", "reported"):
        return "PASS" if 0 < status < 400 else "FAIL"
    return "EXPLORATORY"
# ==================================================================== A. auth
@case("QA-001", "auth", "GET /me with valid Basic credentials", "accepted")
def _(c): return call("GET", V + "/me")

@case("QA-002", "auth", "GET /me with no credentials at all", "refused:401")
def _(c): return call("GET", V + "/me", user=None)

@case("QA-003", "auth", "GET /me with a wrong password", "refused:401")
def _(c): return call("GET", V + "/me", user="admin:not-the-password")

@case("QA-004", "auth", "GET /me for a username that does not exist", "refused:401")
def _(c): return call("GET", V + "/me", user="nobody.here:some-password-12")

@case("QA-005", "auth", "GET /health unauthenticated (liveness must not need auth)", "accepted")
def _(c): return call("GET", "/health", user=None)

@case("QA-006", "auth", "GET /health/ready unauthenticated", "accepted")
def _(c): return call("GET", "/health/ready", user=None)

@case("QA-007", "auth", "GET a protected API path unauthenticated (/models)", "refused:401")
def _(c): return call("GET", V + "/models", user=None)

@case("QA-008", "auth", "Browser login with correct password (form POST)", "accepted")
def _(c): return call("POST", "/login", user=None,
                      form={"username": "admin", "password": "maya-admin-dev", "next": "/dashboard"})

@case("QA-009", "auth", "Browser login with a wrong password", "refused:401")
def _(c): return call("POST", "/login", user=None,
                      form={"username": "admin", "password": "wrong-password", "next": "/dashboard"})

@case("QA-010", "auth", "A password shorter than 12 characters is refused at creation", "refused:*")
def _(c): return call("POST", V + "/principals",
                      body={"username": "short.pw", "display_name": "Short", "roles": ["auditor"], "password": "short"})

@case("QA-011", "auth", "Empty Basic header value", "refused:401")
def _(c): return call("GET", V + "/me", user=None, headers={"authorization": "Basic "})

@case("QA-012", "auth", "Bearer token that is not an API key", "refused:401")
def _(c): return call("GET", V + "/me", user=None, headers={"authorization": "Bearer not-a-key"})

@case("QA-013", "auth", "X-API-Key header with a garbage value", "refused:401")
def _(c): return call("GET", V + "/me", user=None, headers={"x-api-key": "maya_sk_garbage"})

@case("QA-014", "auth", "Suspended principal cannot authenticate", "refused:401|403")
def _(c):
    call("POST", V + "/principals/o.perez/suspend", body={"reason": "QA-014"})
    r = call("GET", V + "/me", user="o.perez")
    call("POST", V + "/principals/o.perez/reinstate", body={"reason": "QA-014 done"})
    return r

@case("QA-015", "auth", "Reinstated principal can authenticate again", "accepted")
def _(c): return call("GET", V + "/me", user="o.perez")

# ==================================================================== B. RBAC
@case("QA-016", "rbac", "feature_curator may not register a model", "refused:forbidden")
def _(c): return call("POST", V + "/models", user="q.tester",
                      body={"urn": "maya://model/nope", "name": "nope", "model_class": "c",
                            "domain": "credit", "owner": "person/q", "legal_entity": "uk", "purpose": "p"})

@case("QA-017", "rbac", "A role defined without a description is refused", "refused:*")
def _(c): return call("POST", V + "/roles", body={"name": "nodesc", "permissions": ["model:read"]})

@case("QA-018", "rbac", "A role holding both halves of a separated duty", "refused:incompatible_permissions")
def _(c): return call("POST", V + "/roles",
                      body={"name": "solo", "description": "one person, the whole lifecycle",
                            "permissions": ["model:register", "model:submit", "version:approve"]})

@case("QA-019", "rbac", "Deleting a role somebody still holds", "refused:role_in_use")
def _(c): return call("DELETE", V + "/roles/feature_curator")

@case("QA-020", "rbac", "Suspending yourself", "refused:self_suspension")
def _(c): return call("POST", V + "/principals/admin/suspend", body={"reason": "QA-020"})

@case("QA-021", "rbac", "A role granting a permission that does not exist", "refused:*")
def _(c): return call("POST", V + "/roles", body={"name": "bogus", "description": "grants a permission nobody defined",
                                                  "permissions": ["model:levitate"]})

@case("QA-022", "rbac", "Creating a principal with a role that does not exist", "refused:*")
def _(c): return call("POST", V + "/principals", body={"username": "ghost.role", "display_name": "G",
                                                       "roles": ["not_a_role"], "password": "long-enough-pw"})

@case("QA-023", "rbac", "Duplicate username", "refused:*")
def _(c): return call("POST", V + "/principals", body={"username": "s.iqbal", "display_name": "dup",
                                                       "roles": ["auditor"], "password": "long-enough-pw"})

@case("QA-024", "rbac", "An auditor may not register a model", "refused:forbidden")
def _(c): return call("POST", V + "/models", user="r.hale",
                      body={"urn": "maya://model/aud.nope", "name": "n", "model_class": "c",
                            "domain": "credit", "owner": "person/x", "legal_entity": "uk", "purpose": "p"})

@case("QA-025", "rbac", "An operator may not approve a version", "refused:forbidden")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/versions/1.0.0/approve", user="o.perez", body={})

@case("QA-026", "rbac", "A validator may not manage principals", "refused:forbidden")
def _(c): return call("POST", V + "/principals", user="a.mehta",
                      body={"username": "val.made", "display_name": "V", "roles": ["auditor"], "password": "long-enough-pw"})

@case("QA-027", "rbac", "/me reports the caller's effective permissions", "reported")
def _(c): return call("GET", V + "/me", user="q.tester")

@case("QA-028", "rbac", "Changing a principal's roles as admin", "accepted")
def _(c): return call("PUT", V + "/principals/o.perez/roles", body={"roles": ["operator", "auditor"]})

@case("QA-029", "rbac", "Reverting that role change", "accepted")
def _(c): return call("PUT", V + "/principals/o.perez/roles", body={"roles": ["operator"]})

@case("QA-030", "rbac", "A non-admin may not change their own roles", "refused:forbidden")
def _(c): return call("PUT", V + "/principals/q.tester/roles", user="q.tester", body={"roles": ["admin"]})

@case("QA-031", "rbac", "Setting a password shorter than the minimum", "refused:*")
def _(c): return call("POST", V + "/principals/o.perez/password", body={"password": "short"})

@case("QA-032", "rbac", "A model_developer may not move an alias", "refused:forbidden")
def _(c): return call("PUT", V + "/models/qa.pd.scorecard/aliases", user="d.raman",
                      body={"environment": "prod", "alias": "champion", "semver": "1.0.0",
                            "justification": "QA-032 should never land"})

@case("QA-033", "rbac", "Suspending another principal, then reinstating", "accepted")
def _(c):
    call("POST", V + "/principals/r.hale/suspend", body={"reason": "QA-033"})
    return call("POST", V + "/principals/r.hale/reinstate", body={"reason": "QA-033 done"})

@case("QA-034", "rbac", "Amending a role's permission list", "accepted")
def _(c): return call("PUT", V + "/roles/feature_curator",
                      body={"permissions": ["feature:read", "feature:define", "feature:materialise", "featureset:define"]})

@case("QA-035", "rbac", "Reading the role catalogue as an auditor", "accepted")
def _(c): return call("GET", V + "/roles", user="r.hale")

# ================================================================ C. API keys
@case("QA-036", "apikeys", "Issue a key for the service principal", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/api-keys",
                     body={"username": "svc/qa-runner", "name": "qa-nightly",
                           "scopes": ["model:read", "warrant:resolve"], "lifetime_days": 30})
    if isinstance(p, dict):
        CTX["key_secret"] = p.get("secret")
        CTX["key_id"] = p.get("id")
    return s, p, raw

@case("QA-037", "apikeys", "Authenticate with the key via X-API-Key", "accepted")
def _(c): return call("GET", V + "/me", user=None, headers={"x-api-key": CTX.get("key_secret", "")})

@case("QA-038", "apikeys", "Authenticate with the key as a Bearer token", "accepted")
def _(c): return call("GET", V + "/models", user=None,
                      headers={"authorization": "Bearer " + CTX.get("key_secret", "")})

@case("QA-039", "apikeys", "A key narrower than its principal is refused outside its scope", "refused:outside_key_scope")
def _(c): return call("GET", V + "/evidence/chain", user=None, headers={"x-api-key": CTX.get("key_secret", "")})

@case("QA-040", "apikeys", "A key scope wider than the principal's roles", "refused:scope_exceeds_principal")
def _(c): return call("POST", V + "/api-keys", body={"username": "svc/qa-runner", "name": "too-wide",
                                                     "scopes": ["principal:manage"], "lifetime_days": 30})

@case("QA-041", "apikeys", "A key lifetime of 99999 days", "refused:lifetime_refused")
def _(c): return call("POST", V + "/api-keys", body={"username": "svc/qa-runner", "name": "forever",
                                                     "scopes": ["model:read"], "lifetime_days": 99999})

@case("QA-042", "apikeys", "A key for a principal that does not exist", "refused:*")
def _(c): return call("POST", V + "/api-keys", body={"username": "svc/ghost", "name": "k",
                                                     "scopes": ["model:read"], "lifetime_days": 30})

@case("QA-043", "apikeys", "The secret is not returned again by the list endpoint", "reported")
def _(c): return call("GET", V + "/api-keys")

@case("QA-044", "apikeys", "A key whose principal is suspended", "refused:key_principal_not_active|401")
def _(c):
    call("POST", V + "/principals/svc%2Fqa-runner/suspend", body={"reason": "QA-044"})
    r = call("GET", V + "/me", user=None, headers={"x-api-key": CTX.get("key_secret", "")})
    call("POST", V + "/principals/svc%2Fqa-runner/reinstate", body={"reason": "QA-044 done"})
    return r

@case("QA-045", "apikeys", "Revoke the key", "accepted")
def _(c): return call("POST", V + f"/api-keys/{CTX.get('key_id')}/revoke", body={"reason": "QA finished"})

@case("QA-046", "apikeys", "Using a revoked key names it as revoked, not a generic 401", "refused:key_revoked")
def _(c): return call("GET", V + "/me", user=None, headers={"x-api-key": CTX.get("key_secret", "")})

@case("QA-047", "apikeys", "Revoking an already-revoked key", "EXPLORATORY: idempotent or refused")
def _(c): return call("POST", V + f"/api-keys/{CTX.get('key_id')}/revoke", body={"reason": "again"})

@case("QA-048", "apikeys", "A non-admin issuing a key for somebody else", "refused:forbidden")
def _(c): return call("POST", V + "/api-keys", user="q.tester",
                      body={"username": "svc/qa-runner", "name": "sneaky", "scopes": ["model:read"], "lifetime_days": 30})


KERNEL = {
    "runtime": "formula", "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "entry": {"expression": "1 / (1 + exp(-(intercept + beta_dscr * dscr + beta_ltv * ltv)))",
              "target": "pd_12m"},
    "input_schema": [
        {"name": "dscr", "dtype": "numeric", "symbol": "\\mathrm{DSCR}", "unit": "ratio"},
        {"name": "ltv", "dtype": "numeric", "symbol": "\\mathrm{LTV}", "unit": "ratio"},
        {"name": "intercept", "dtype": "numeric", "symbol": "\\alpha"},
        {"name": "beta_dscr", "dtype": "numeric", "symbol": "\\beta_{1}"},
        {"name": "beta_ltv", "dtype": "numeric", "symbol": "\\beta_{2}"}],
    "output_schema": [{"name": "pd_12m", "dtype": "numeric", "unit": "probability"}]}


def reg(urn, name, owner="person/j.okafor", purpose="12-month PD at origination", user="admin"):
    return call("POST", V + "/models", user=user,
                body={"urn": urn, "name": name, "model_class": "credit.pd.scorecard",
                      "domain": "credit", "owner": owner, "legal_entity": "LE-US-01",
                      "purpose": purpose})

# ============================================== D. model registration + tiering
@case("QA-049", "models", "Register a second model (tier-1 candidate)", "accepted")
def _(c): return reg("maya://model/qa.ews.tier1", "QA early warning")

@case("QA-050", "models", "Register a third model, left untiered on purpose", "accepted")
def _(c): return reg("maya://model/qa.untiered", "QA untiered")

@case("QA-051", "models", "Register a model whose urn is already taken", "refused:*")
def _(c): return reg("maya://model/qa.pd.scorecard", "duplicate")

@case("QA-052", "models", "Register a model with no purpose", "EXPLORATORY: is a purpose load-bearing?")
def _(c): return call("POST", V + "/models", body={"urn": "maya://model/qa.nopurpose", "name": "n",
                                                   "model_class": "c", "domain": "credit",
                                                   "owner": "person/x", "legal_entity": "uk", "purpose": ""})

@case("QA-053", "models", "Register a model with a urn that is not a maya urn", "refused:*")
def _(c): return reg("not-a-urn", "bad urn")

@case("QA-054", "models", "Register a model with an unknown field in the body", "refused:422")
def _(c): return call("POST", V + "/models", body={"urn": "maya://model/qa.extra", "name": "n",
                                                   "model_class": "c", "domain": "credit", "owner": "person/x",
                                                   "legal_entity": "uk", "purpose": "p", "sneaky": 1})

@case("QA-055", "models", "GET a model that does not exist", "refused:404")
def _(c): return call("GET", V + "/models/does.not.exist")

@case("QA-056", "models", "Assess a tier before any version exists, where the answer does not turn on it", "accepted")
def _(c): return call("POST", V + "/models/qa.ews.tier1/assess",
                      body={"exposure": 50000000000, "purpose_class": "credit_decision",
                            "feature_count": 80, "uses_alternative_data": True, "interpretable": False})

@case("QA-057", "models", "Create version 1.0.0 on the tier-1 candidate", "accepted")
def _(c): return call("POST", V + "/models/qa.ews.tier1/versions", body={"semver": "1.0.0", "kernel": KERNEL})

@case("QA-058", "models", "Assess with an unknown purpose class", "refused:unknown_purpose_class")
def _(c): return call("POST", V + "/models/qa.ews.tier1/assess",
                      body={"exposure": 1000, "purpose_class": "vibes",
                            "feature_count": 1, "uses_alternative_data": False, "interpretable": True})

@case("QA-059", "models", "Assess the tier-1 candidate at critical exposure", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/models/qa.ews.tier1/assess",
                     body={"exposure": 50000000000, "purpose_class": "credit_decision",
                           "feature_count": 80, "uses_alternative_data": True, "interpretable": False})
    CTX["ews_tier"] = (p or {}).get("tier")
    return s, p, raw

@case("QA-060", "models", "Submit an untiered model for approval", "refused:*")
def _(c): return call("POST", V + "/models/qa.untiered/submit", body={})

@case("QA-061", "models", "Approve an untiered model", "refused:*")
def _(c): return call("POST", V + "/models/qa.untiered/approve", user="s.iqbal", body={})

@case("QA-062", "models", "Attest a model that was never approved", "refused:*")
def _(c): return call("POST", V + "/models/qa.untiered/attest", user="s.iqbal",
                      body={"role": "model_risk_manager", "decision": "attest"})

@case("QA-063", "models", "PATCH a model's description as its owner", "accepted")
def _(c): return call("PATCH", V + "/models/qa.untiered", user="j.okafor",
                      body={"fields": {"description": "left untiered deliberately, for QA"}})

@case("QA-064", "models", "Version approval on a model with no version", "refused:*")
def _(c): return call("POST", V + "/models/qa.untiered/versions/9.9.9/approve", user="s.iqbal", body={})

# ================================================ E. the tier-3 governed path
@case("QA-065", "lifecycle", "Approve version 1.0.0 as the person who created it", "refused:segregation_of_duties")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/versions/1.0.0/approve", user="admin", body={})

@case("QA-066", "lifecycle", "Approve version 1.0.0 as the second line (tier 3, one signature)", "accepted")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/versions/1.0.0/approve", user="s.iqbal", body={})

@case("QA-067", "lifecycle", "Approve the same version twice", "EXPLORATORY: idempotent or refused")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/versions/1.0.0/approve", user="s.iqbal", body={})

@case("QA-068", "lifecycle", "Submit the model record", "accepted")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/submit", body={})

@case("QA-069", "lifecycle", "Approve the model record as the submitter (admin holds both)", "EXPLORATORY: is submit/approve segregated?")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/approve", user="admin", body={})

@case("QA-070", "lifecycle", "Approve the model record as the second line", "EXPLORATORY: already approved by QA-069")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/approve", user="s.iqbal", body={})

@case("QA-071", "attestation", "First attestation signature (model_risk_manager)", "reported")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/attest", user="s.iqbal",
                      body={"role": "model_risk_manager", "decision": "attest"})

@case("QA-072", "attestation", "The same person signing under a second role they do not hold", "refused:role_not_held")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/attest", user="s.iqbal",
                      body={"role": "model_owner", "decision": "attest"})

@case("QA-073", "attestation", "Signing an attestation without model:attest at all", "refused:forbidden")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/attest", user="a.mehta",
                      body={"role": "model_owner", "decision": "attest"})

@case("QA-074", "attestation", "The same role signing twice", "refused:already_signed")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/attest", user="s.iqbal",
                      body={"role": "model_risk_manager", "decision": "attest"})

@case("QA-075", "attestation", "The owner completes the attestation", "accepted")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/attest", user="j.okafor",
                      body={"role": "model_owner", "decision": "attest"})

@case("QA-076", "attestation", "The model now reads as attested and immutable", "reported")
def _(c): return call("GET", V + "/models/qa.pd.scorecard")

@case("QA-077", "lifecycle", "Add a version to an attested model", "refused:*")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/versions", body={"semver": "3.0.0", "kernel": KERNEL})

@case("QA-078", "lifecycle", "Amend the attested model as a model_risk_manager (lacks model:amend)", "refused:forbidden")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/amend", user="s.iqbal",
                      body={"reason": "add a version with a third regressor", "scope": ["version"]})

@case("QA-079", "lifecycle", "Open an amendment as the owner", "accepted")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/amend", user="j.okafor",
                      body={"reason": "add a version with a third regressor", "scope": ["version"]})

@case("QA-080", "lifecycle", "Add version 2.0.0 under the amendment", "accepted")
def _(c): return call("POST", V + "/models/qa.pd.scorecard/versions", body={"semver": "2.0.0", "kernel": KERNEL})


# =================================================== F. the tier-1 quorum path
@case("QA-081", "quorum", "Assigning two incompatible roles to one person", "refused:incompatible_roles")
def _(c):
    call("POST", V + "/principals", body={"username": "p.dual", "display_name": "P Dual",
                                          "roles": ["model_risk_manager"], "password": "dual-password-long"})
    return call("PUT", V + "/principals/p.dual/roles", body={"roles": ["model_developer", "validator"]})

@case("QA-082", "quorum", "One person holding model_risk_manager and validator (a supported pair)", "accepted")
def _(c): return call("PUT", V + "/principals/p.dual/roles",
                      body={"roles": ["model_risk_manager", "validator"]})

@case("QA-083", "quorum", "The published quorum by tier", "reported")
def _(c): return call("GET", V + "/version-approval-quorum")

@case("QA-084", "quorum", "Single-signature approval of a tier-1 version", "refused:quorum_required")
def _(c): return call("POST", V + "/models/qa.ews.tier1/versions/1.0.0/approve", user="s.iqbal", body={})

@case("QA-085", "quorum", "What this version's approval needs", "reported")
def _(c): return call("GET", V + "/version-approvals?urn=maya://model/qa.ews.tier1&semver=1.0.0")

@case("QA-086", "quorum", "Open a quorum on the tier-1 version", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/version-approvals",
                     user="s.iqbal", body={"urn": "maya://model/qa.ews.tier1", "semver": "1.0.0"})
    CTX["approval_id"] = (p or {}).get("id")
    return s, p, raw

@case("QA-087", "quorum", "Open a second quorum while one is open", "refused:approval_open")
def _(c): return call("POST", V + "/version-approvals", user="s.iqbal",
                      body={"urn": "maya://model/qa.ews.tier1", "semver": "1.0.0"})

@case("QA-088", "quorum", "Sign for a role the signer does not hold", "refused:role_not_held")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/sign", user="s.iqbal",
                      body={"role": "validator", "decision": "approve", "statement": "borrowed hat"})

@case("QA-089", "quorum", "Sign for a role this quorum does not require", "refused:role_not_required")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/sign", user="s.iqbal",
                      body={"role": "model_owner", "decision": "approve", "statement": "wrong role"})

@case("QA-090", "quorum", "First signature (model_risk_manager) by a dual-hatted person", "reported")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/sign", user="p.dual",
                      body={"role": "model_risk_manager", "decision": "approve", "statement": "coefficients match"})

@case("QA-091", "quorum", "The same person signing the second role: a quorum is people, not hats", "refused:already_signed_personally")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/sign", user="p.dual",
                      body={"role": "validator", "decision": "approve", "statement": "second hat"})

@case("QA-092", "quorum", "The same role signed twice by two different people", "refused:already_signed")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/sign", user="s.iqbal",
                      body={"role": "model_risk_manager", "decision": "approve", "statement": "me too"})

@case("QA-093", "quorum", "Quorum progress names who is outstanding", "reported")
def _(c): return call("GET", V + f"/version-approvals/{CTX.get('approval_id')}")

@case("QA-094", "quorum", "The second person completes the quorum", "accepted")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/sign", user="a.mehta",
                      body={"role": "validator", "decision": "approve", "statement": "effective challenge complete"})

@case("QA-095", "quorum", "Signing a closed approval", "refused:approval_closed")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/sign", user="s.iqbal",
                      body={"role": "model_risk_manager", "decision": "approve", "statement": "late"})

@case("QA-096", "quorum", "Withdrawing a closed approval", "refused:*")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/withdraw", user="s.iqbal", body={})

@case("QA-097", "quorum", "Single-signature approval after the quorum approved it", "EXPLORATORY: idempotent or refused")
def _(c): return call("POST", V + "/models/qa.ews.tier1/versions/1.0.0/approve", user="s.iqbal", body={})

@case("QA-098", "quorum", "An unknown decision word on a signature", "refused:unknown_decision|404|409")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('approval_id')}/sign", user="a.mehta",
                      body={"role": "validator", "decision": "maybe", "statement": ""})

@case("QA-099", "quorum", "Open a quorum on a model with no tier", "refused:no_tier|not_tiered|no_such_version")
def _(c):
    """`qa.untiered` gets its first version at QA-108, which runs later — so on
    a clean estate this refuses for the version rather than the tier. Both are
    the register refusing to approve something it cannot place; the code that
    comes back says which, and the case names both."""
    return call("POST", V + "/version-approvals", user="s.iqbal",
                body={"urn": "maya://model/qa.untiered", "semver": "1.0.0"})

# ==================================================================== G. aliases
@case("QA-100", "aliases", "Promote a version into prod as the person who created it", "refused:segregation_of_duties")
def _(c): return call("PUT", V + "/models/qa.pd.scorecard/aliases", user="admin",
                      body={"environment": "prod", "alias": "champion", "semver": "1.0.0",
                            "justification": "QA-100: the creator promoting their own build"})

@case("QA-101", "aliases", "Promote as the second line", "accepted")
def _(c): return call("PUT", V + "/models/qa.pd.scorecard/aliases", user="s.iqbal",
                      body={"environment": "prod", "alias": "champion", "semver": "1.0.0",
                            "justification": "QA-101: the approved version goes to prod"})

@case("QA-102", "aliases", "Promote a version that was never approved", "refused:*")
def _(c): return call("PUT", V + "/models/qa.pd.scorecard/aliases", user="s.iqbal",
                      body={"environment": "prod", "alias": "champion", "semver": "2.0.0",
                            "justification": "QA-102: 2.0.0 has no approval"})

@case("QA-103", "aliases", "Promote a semver that does not exist", "refused:*")
def _(c): return call("PUT", V + "/models/qa.pd.scorecard/aliases", user="s.iqbal",
                      body={"environment": "prod", "alias": "champion", "semver": "7.7.7",
                            "justification": "QA-103: no such version"})

@case("QA-104", "aliases", "Promote with an empty justification", "EXPLORATORY: is a justification required?")
def _(c): return call("PUT", V + "/models/qa.ews.tier1/aliases", user="s.iqbal",
                      body={"environment": "prod", "alias": "champion", "semver": "1.0.0",
                            "justification": ""})

@case("QA-105", "aliases", "Re-promote the same version to the same alias", "EXPLORATORY: idempotent or refused")
def _(c): return call("PUT", V + "/models/qa.pd.scorecard/aliases", user="s.iqbal",
                      body={"environment": "prod", "alias": "champion", "semver": "1.0.0",
                            "justification": "QA-105: the same move again"})

@case("QA-106", "versions", "Duplicate semver on the same model", "refused:*")
def _(c): return call("POST", V + "/models/qa.ews.tier1/versions", body={"semver": "1.0.0", "kernel": KERNEL})

@case("QA-107", "versions", "A semver that is not a semver", "refused:*")
def _(c): return call("POST", V + "/models/qa.ews.tier1/versions", body={"semver": "one point oh", "kernel": KERNEL})

@case("QA-108", "versions", "A version with an empty kernel", "EXPLORATORY: is a kernel required?")
def _(c): return call("POST", V + "/models/qa.untiered/versions", body={"semver": "1.0.0"})

@case("QA-109", "versions", "A kernel naming a runtime that does not exist", "refused:*")
def _(c): return call("POST", V + "/models/qa.untiered/versions",
                      body={"semver": "1.1.0", "kernel": dict(KERNEL, runtime="telepathy")})

@case("QA-110", "versions", "Version history for one model", "reported")
def _(c): return call("GET", V + "/version-history?urn=maya://model/qa.pd.scorecard")


M = "maya://model/qa.pd.scorecard"

# ============================================ H. features, views, featuresets
@case("QA-111", "features", "Define a feature as a curator", "accepted")
def _(c): return call("POST", V + "/features", user="q.tester",
                      body={"name": "utilisation", "entity": "borrower", "dtype": "numeric",
                            "description": "credit line utilisation", "owner": "person/d.raman"})

@case("QA-112", "features", "Define a feature with a name already taken", "refused:*")
def _(c): return call("POST", V + "/features", user="q.tester",
                      body={"name": "dscr", "entity": "borrower", "dtype": "numeric",
                            "description": "duplicate", "owner": "person/d.raman"})

@case("QA-113", "features", "Define a feature with no description", "refused:*")
def _(c): return call("POST", V + "/features", user="q.tester",
                      body={"name": "nodesc_feature", "entity": "borrower", "dtype": "numeric",
                            "description": "", "owner": "person/d.raman"})

@case("QA-114", "features", "Define a feature with an unknown dtype", "refused:*")
def _(c): return call("POST", V + "/features", user="q.tester",
                      body={"name": "weird", "entity": "borrower", "dtype": "vibes",
                            "description": "an unknown dtype", "owner": "person/d.raman"})

@case("QA-115", "features", "A curator may not register a model but may load data", "accepted")
def _(c): return call("GET", V + "/features", user="q.tester")

@case("QA-116", "features", "Materialise rows missing a required clock", "refused:*")
def _(c): return call("POST", V + "/feature-views/qa_borrower/materialise", user="q.tester",
                      body={"rows": [{"entity_id": "C9", "event_ts": 100.0, "dscr": 1.0, "ltv": 0.5}]})

@case("QA-117", "features", "Materialise a row for a feature the view does not carry", "refused:*")
def _(c): return call("POST", V + "/feature-views/qa_borrower/materialise", user="q.tester",
                      body={"rows": [{"entity_id": "C9", "event_ts": 100.0, "ingest_ts": 110.0,
                                      "not_in_the_view": 1.0}]})

@case("QA-118", "features", "Read a view version's data point-in-time", "reported")
def _(c): return call("GET", V + "/feature-views/qa_borrower/versions/1/data?as_of=1000.0")

@case("QA-119", "features", "Read a view version that does not exist", "refused:feature_refused|404")
def _(c): return call("GET", V + "/feature-views/qa_borrower/versions/99/data?as_of=1000.0")

@case("QA-120", "featuresets", "Define a featureset whose slots match the kernel", "accepted")
def _(c): return call("POST", V + "/featuresets",
                      body={"name": "qa_pd_training", "entity": "borrower",
                            "slots": {"dscr": "numeric", "ltv": "numeric", "defaulted": "numeric"},
                            "label_slot": "defaulted", "outcome_window_days": 365,
                            "description": "slot names match the kernel input names"})

@case("QA-121", "featuresets", "A label slot that is not one of the slots", "refused:*")
def _(c): return call("POST", V + "/featuresets",
                      body={"name": "qa_bad_label", "entity": "borrower",
                            "slots": {"a": "numeric"}, "label_slot": "not_a_slot",
                            "outcome_window_days": 365, "description": "bad label"})

@case("QA-122", "featuresets", "Publish a version leaving a slot unbound", "refused:*")
def _(c): return call("POST", V + "/featuresets/qa_pd_training/versions",
                      body={"bindings": {"dscr": "dscr", "ltv": "ltv"}})

@case("QA-123", "featuresets", "Bind a slot to a feature nothing has materialised", "refused:*")
def _(c): return call("POST", V + "/featuresets/qa_pd_training/versions",
                      body={"bindings": {"dscr": "dscr", "ltv": "ltv", "defaulted": "utilisation"}})

@case("QA-124", "featuresets", "Publish a version pinning every slot", "accepted")
def _(c): return call("POST", V + "/featuresets/qa_pd_training/versions",
                      body={"bindings": {"dscr": "dscr", "ltv": "ltv", "defaulted": "defaulted_12m"}})

@case("QA-125", "featuresets", "A featureset composed from another", "accepted")
def _(c): return call("POST", V + "/featuresets",
                      body={"name": "qa_pd_extended", "entity": "borrower",
                            "composes": ["qa_pd_training"], "slots": {"balances": "numeric"},
                            "description": "everything the training set has, plus balances"})

@case("QA-126", "featuresets", "What the composed featureset resolves to", "reported")
def _(c): return call("GET", V + "/featuresets/qa_pd_extended/resolved")

@case("QA-127", "featuresets", "Compose from a featureset that does not exist", "refused:*")
def _(c): return call("POST", V + "/featuresets",
                      body={"name": "qa_pd_ghost", "entity": "borrower", "composes": ["nope"],
                            "slots": {"x": "numeric"}, "description": "composes nothing real"})

@case("QA-128", "featuresets", "A derived feature from an expression", "accepted")
def _(c): return call("POST", V + "/derived-features",
                      body={"name": "coverage_ratio", "expression": "dscr / ltv", "dtype": "numeric",
                            "description": "cover per unit of leverage"})

@case("QA-129", "featuresets", "A derived feature whose expression names an unknown feature", "refused:*")
def _(c): return call("POST", V + "/derived-features",
                      body={"name": "nonsense_ratio", "expression": "dscr / unknown_thing",
                            "dtype": "numeric", "description": "reads a feature nobody defined"})

@case("QA-130", "featuresets", "A derived feature whose expression calls a function nobody allows", "refused:*")
def _(c): return call("POST", V + "/derived-features",
                      body={"name": "sneaky", "expression": "__import__('os').system('id')",
                            "dtype": "numeric", "description": "an injection attempt"})

# ================================================== I. warrants and execution
@case("QA-131", "warrants", "Grant a standing warrant to the service account", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/warrants", user="j.okafor",
                     body={"urn": M, "principal": "svc/qa-runner",
                           "declared_use": "model_development", "environment": "lab",
                           "flavour": "formula"})
    CTX["grant_id"] = (p or {}).get("id")
    return s, p, raw

@case("QA-132", "warrants", "Resolve before any parameters are approved", "refused:no_approved_parameters")
def _(c): return call("POST", V + "/resolve?verb=score",
                      body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "environment": "lab"})

@case("QA-133", "warrants", "A fit warrant whose featureset cannot fill the kernel's slots (L-W10)", "refused:schema_not_satisfied")
def _(c): return call("POST", V + "/fit-warrants", user="j.okafor",
                      body={"urn": M + "@1.0.0", "environment": "lab", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "featureset": "qa_pd_inputs",
                            "featureset_version": 1, "window": {"from": 0.0, "to": 1000.0},
                            "as_of": 1000.0})

@case("QA-134", "warrants", "A fit warrant whose featureset does fill them", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/fit-warrants", user="j.okafor",
                     body={"urn": M + "@1.0.0", "environment": "lab", "principal": "svc/qa-runner",
                           "declared_use": "model_development", "featureset": "qa_pd_training",
                           "featureset_version": 1, "window": {"from": 0.0, "to": 1000.0},
                           "as_of": 1000.0})
    CTX["fit"] = p
    return s, p, raw

@case("QA-135", "warrants", "Assemble a point-in-time training set", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/featuresets/qa_pd_training/training-sets",
                     body={"version": 1, "name": "qa_pd_train_v1", "as_of": 1000.0,
                           "spine": [{"entity_id": "C1", "label_ts": 500.0},
                                     {"entity_id": "C2", "label_ts": 500.0}]})
    CTX["snapshot_id"] = (p or {}).get("id")
    return s, p, raw

@case("QA-136", "warrants", "The training set carries the RESTATED value, not the first-known one", "reported")
def _(c): return call("GET", V + "/featuresets/qa_pd_training/versions/1/data?as_of=1000.0")

@case("QA-137", "parameters", "Record parameters with no warrant id", "refused:*")
def _(c): return call("POST", V + "/parameters", user="j.okafor",
                      body={"urn": M, "semver": "1.0.0", "name": "no-warrant",
                            "kind": "estimated_coefficients",
                            "values": {"intercept": -2.31, "beta_dscr": -0.84, "beta_ltv": 3.02},
                            "provenance": "fitted"})

@case("QA-138", "parameters", "Record parameters against a warrant id that does not exist", "refused:unknown_warrant|*")
def _(c): return call("POST", V + "/parameters", user="j.okafor",
                      body={"urn": M, "semver": "1.0.0", "name": "ghost-warrant",
                            "kind": "estimated_coefficients",
                            "values": {"intercept": -2.31, "beta_dscr": -0.84, "beta_ltv": 3.02},
                            "provenance": "fitted", "warrant_id": "not-a-warrant"})

@case("QA-139", "parameters", "Record parameters against the grant", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/parameters", user="j.okafor",
                     body={"urn": M, "semver": "1.0.0", "name": "qa-fit-2026Q1",
                           "kind": "estimated_coefficients",
                           "values": {"intercept": -2.31, "beta_dscr": -0.84, "beta_ltv": 3.02},
                           "provenance": "fitted", "diagnostics": {"auc": 0.78, "n": 2},
                           "featureset": "qa_pd_training", "featureset_version": 1,
                           "window": {"from": 0.0, "to": 1000.0}, "as_of": 1000.0,
                           "snapshot_id": CTX.get("snapshot_id"),
                           "warrant_id": CTX.get("grant_id"),
                           "note": "fitted by an engine outside MAYA"})
    CTX["pset"] = (p or {}).get("id")
    return s, p, raw

@case("QA-140", "parameters", "The owner who recorded a set has no parameter:approve", "refused:forbidden")
def _(c): return call("POST", V + f"/parameter-sets/{CTX.get('pset')}/review", user="j.okafor",
                      body={"accept": True, "note": "my own numbers"})

@case("QA-141", "parameters", "Somebody else approves it", "accepted")
def _(c): return call("POST", V + f"/parameter-sets/{CTX.get('pset')}/review", user="s.iqbal",
                      body={"accept": True, "note": "reviewed against the training record"})

@case("QA-142", "warrants", "Resolve now that parameters are approved", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/resolve?verb=score",
                     body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                           "declared_use": "model_development", "environment": "lab"})
    CTX["descriptor"] = p
    return s, p, raw

@case("QA-143", "warrants", "Resolve in somebody else's name, without warrant:issue", "refused:principal_not_self")
def _(c):
    """`warrant:issue` is what makes minting a warrant for a third party a
    deliberate act. So the caller has to be one who may resolve and may not
    issue — a second service account, not a person in the second line, who
    would be refused for the permission before the identity is looked at."""
    call("POST", V + "/principals",
         body={"username": "svc/qa-other", "display_name": "Another runner",
               "kind": "service", "roles": ["service"]})
    _s, p, _raw = call("POST", V + "/api-keys",
                      body={"username": "svc/qa-other", "name": "qa-other",
                            "scopes": ["warrant:resolve"], "lifetime_days": 30})
    secret = (p or {}).get("secret", "")
    return call("POST", V + "/resolve?verb=score", user=None,
                headers={"x-api-key": secret},
                body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                      "declared_use": "model_development", "environment": "lab"})

@case("QA-144", "warrants", "Resolve for a use the grant does not cover", "refused:use_not_approved|no_entitlement")
def _(c): return call("POST", V + "/resolve?verb=score",
                      body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                            "declared_use": "origination_decision", "environment": "lab"})

@case("QA-145", "warrants", "Resolve in an environment the grant does not cover", "refused:no_entitlement|restricted")
def _(c): return call("POST", V + "/resolve?verb=score",
                      body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "environment": "prod"})

@case("QA-146", "execution", "Execute inside MAYA at the approved point", "accepted")
def _(c): return call("POST", V + "/execute?verb=score",
                      body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "environment": "lab",
                            "inputs": {"features": {"dscr": 1.2, "ltv": 0.6}}})

@case("QA-147", "execution", "A caller supplying one of the coefficients", "refused:parameter_overridden")
def _(c): return call("POST", V + "/execute?verb=score",
                      body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "environment": "lab",
                            "inputs": {"features": {"dscr": 1.2, "ltv": 0.6, "beta_dscr": 99.0}}})

@case("QA-148", "execution", "Execute with a required feature missing", "refused:*")
def _(c): return call("POST", V + "/execute?verb=score",
                      body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "environment": "lab",
                            "inputs": {"features": {"dscr": 1.2}}})

@case("QA-149", "execution", "Execute a version that does not exist", "refused:*")
def _(c): return call("POST", V + "/execute?verb=score",
                      body={"urn": M + "@8.8.8", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "environment": "lab",
                            "inputs": {"features": {"dscr": 1.2, "ltv": 0.6}}})

@case("QA-150", "warrants", "Revoke the grant", "accepted")
def _(c): return call("POST", V + "/warrants/revoke", user="s.iqbal",
                      body={"urn": M, "reason": "QA-150 finished with it"})

@case("QA-151", "warrants", "Resolve after revocation", "refused:revoked|no_entitlement|410")
def _(c): return call("POST", V + "/resolve?verb=score",
                      body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "environment": "lab"})

@case("QA-152", "warrants", "Every standing grant across the estate", "reported")
def _(c): return call("GET", V + "/warrants")


DEC = "maya://model/qa.decom"

# ================================================ J. decommissioning
@case("QA-153", "decommission", "Posture with no model named", "reported")
def _(c): return call("GET", V + "/decommission")

@case("QA-154", "decommission", "Register and attest a model to decommission", "accepted")
def _(c):
    call("POST", V + "/models", body={"urn": DEC, "name": "QA decommission target",
                                      "model_class": "credit.pd.scorecard", "domain": "credit",
                                      "owner": "person/j.okafor", "legal_entity": "LE-US-01",
                                      "purpose": "a model that exists to be withdrawn"})
    call("POST", V + "/models/qa.decom/versions",
         body={"semver": "1.0.0", "kernel": {"runtime": "formula", "parameter_kind": "none",
                                             "fit_procedure": "none",
                                             "entry": {"expression": "dscr", "target": "y"},
                                             "input_schema": [{"name": "dscr", "dtype": "numeric"}],
                                             "output_schema": [{"name": "y", "dtype": "numeric"}]}})
    call("POST", V + "/models/qa.decom/assess",
         body={"exposure": 1000000, "purpose_class": "credit_decision", "feature_count": 1,
               "uses_alternative_data": False, "interpretable": True})
    call("POST", V + "/models/qa.decom/submit", user="j.okafor", body={})
    return call("POST", V + "/models/qa.decom/approve", user="s.iqbal", body={})

@case("QA-155", "decommission", "Decommission with a rationale of three characters", "refused:rationale_required")
def _(c): return call("POST", V + "/decommission?urn=" + DEC, user="j.okafor",
                      body={"rationale": "n/a", "replacement": "none",
                            "retention_class": "model_record", "acknowledged": True})

@case("QA-156", "decommission", "Decommission naming no replacement at all", "refused:replacement_required")
def _(c): return call("POST", V + "/decommission?urn=" + DEC, user="j.okafor",
                      body={"rationale": "superseded by the 2026 rebuild", "replacement": "",
                            "retention_class": "model_record", "acknowledged": True})

@case("QA-157", "decommission", "Decommission naming a replacement nobody registered", "refused:replacement_not_registered")
def _(c): return call("POST", V + "/decommission?urn=" + DEC, user="j.okafor",
                      body={"rationale": "superseded by the 2026 rebuild",
                            "replacement": "maya://model/does.not.exist",
                            "retention_class": "model_record", "acknowledged": True})

@case("QA-158", "decommission", "Decommission under a retention class nobody defined", "refused:unknown_retention_class")
def _(c): return call("POST", V + "/decommission?urn=" + DEC, user="j.okafor",
                      body={"rationale": "superseded by the 2026 rebuild", "replacement": "none",
                            "retention_class": "forever_and_ever", "acknowledged": True})

@case("QA-159", "decommission", "Who consumes this model", "reported")
def _(c): return call("GET", V + "/decommission/consumers?urn=" + DEC)

@case("QA-160", "decommission", "A model_risk_manager decommissioning (needs model:retire)", "EXPLORATORY: does mrm hold model:retire?")
def _(c): return call("POST", V + "/decommission?urn=" + DEC, user="a.mehta",
                      body={"rationale": "the validator should not be able to do this",
                            "replacement": "none", "retention_class": "model_record",
                            "acknowledged": True})

@case("QA-161", "decommission", "Decommission properly", "accepted")
def _(c): return call("POST", V + "/decommission?urn=" + DEC, user="j.okafor",
                      body={"rationale": "superseded by the 2026 rebuild",
                            "replacement": "maya://model/qa.pd.scorecard",
                            "retention_class": "model_record", "notified": [], "acknowledged": True})

@case("QA-162", "decommission", "Decommission the same model twice", "refused:already_decommissioned")
def _(c): return call("POST", V + "/decommission?urn=" + DEC, user="j.okafor",
                      body={"rationale": "superseded by the 2026 rebuild",
                            "replacement": "maya://model/qa.pd.scorecard",
                            "retention_class": "model_record", "acknowledged": True})

@case("QA-163", "decommission", "Decommission a model in a state retire cannot be reached from", "refused:illegal_transition|*")
def _(c): return call("POST", V + "/decommission?urn=maya://model/qa.pd.scorecard", user="j.okafor",
                      body={"rationale": "the amending record should refuse this",
                            "replacement": "none", "retention_class": "model_record",
                            "acknowledged": True})

@case("QA-164", "decommission", "What the estate still owes on decommissioning", "reported")
def _(c): return call("GET", V + "/decommission/estate")

# ==================================================== K. legal holds, retention
@case("QA-165", "holds", "The retention schedule", "reported")
def _(c): return call("GET", V + "/retention")

@case("QA-166", "holds", "Place a hold with no matter named", "refused:matter_required")
def _(c): return call("POST", V + "/legal-holds", user="s.iqbal",
                      body={"matter": "", "owner": "s.iqbal", "scope_kind": "estate", "classes": []})

@case("QA-167", "holds", "Place a hold under a scope kind nobody defined", "refused:unknown_scope")
def _(c): return call("POST", V + "/legal-holds", user="s.iqbal",
                      body={"matter": "FCA request 2026-08", "owner": "s.iqbal",
                            "scope_kind": "galaxy", "classes": []})

@case("QA-168", "holds", "An auditor may not place a hold", "refused:forbidden")
def _(c): return call("POST", V + "/legal-holds", user="r.hale",
                      body={"matter": "FCA request 2026-08", "owner": "r.hale",
                            "scope_kind": "estate", "classes": []})

@case("QA-169", "holds", "Place an estate-wide hold", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/legal-holds", user="s.iqbal",
                     body={"matter": "FCA request 2026-08", "owner": "s.iqbal",
                           "scope_kind": "estate", "classes": []})
    CTX["hold"] = (p or {}).get("reference")
    return s, p, raw

@case("QA-170", "holds", "Delete a model while a hold covers it", "refused:under_legal_hold")
def _(c): return call("DELETE", V + "/models/qa.nopurpose?reason=QA-170%20under%20hold")


@case("QA-171", "holds", "Lift a hold that does not exist", "refused:no_hold")
def _(c): return call("POST", V + "/legal-holds/HOLD-9999/lift", user="s.iqbal",
                      body={"reason": "there is no such hold"})

@case("QA-172", "holds", "Lift a hold with no reason", "refused:reason_required")
def _(c): return call("POST", V + f"/legal-holds/{CTX.get('hold')}/lift", user="s.iqbal",
                      body={"reason": ""})

@case("QA-173", "holds", "Lift the hold", "accepted")
def _(c): return call("POST", V + f"/legal-holds/{CTX.get('hold')}/lift", user="s.iqbal",
                      body={"reason": "the matter closed 2026-09-01"})

@case("QA-174", "holds", "Lift the same hold twice", "refused:not_active")
def _(c): return call("POST", V + f"/legal-holds/{CTX.get('hold')}/lift", user="s.iqbal",
                      body={"reason": "again"})

@case("QA-175", "holds", "Delete a model as somebody who is not an administrator", "refused:forbidden|deletion_refused")
def _(c): return call("DELETE", V + "/models/qa.nopurpose?reason=QA-175%20owner", user="j.okafor")


@case("QA-176", "holds", "Delete a model with no reason", "refused:reason_required")
def _(c): return call("DELETE", V + "/models/qa.nopurpose?reason=")

@case("QA-177", "holds", "Delete the throwaway model as an administrator, hold lifted", "accepted")
def _(c): return call("DELETE", V + "/models/qa.nopurpose?reason=QA-177%20registered%20by%20mistake")



# ============================================== L. the delegated authority matrix
@case("QA-178", "authority", "The authority posture with nothing published", "reported")
def _(c): return call("GET", V + "/authority")

@case("QA-179", "authority", "Publish a band with no name", "refused:band_name_required")
def _(c): return call("POST", V + "/authority/bands", user="s.iqbal",
                      body={"name": "", "stages": [["model_risk_manager"], ["validator"]], "tier": 1})

@case("QA-180", "authority", "Publish a band with no stages", "refused:stages_required")
def _(c): return call("POST", V + "/authority/bands", user="s.iqbal",
                      body={"name": "qa-nostages", "stages": [], "tier": 1})

@case("QA-181", "authority", "Publish a band for a tier outside 1..4", "refused:unknown_tier")
def _(c): return call("POST", V + "/authority/bands", user="s.iqbal",
                      body={"name": "qa-tier9", "stages": [["model_risk_manager"]], "tier": 9})

@case("QA-182", "authority", "Publish a band with a negative floor", "refused:negative_floor")
def _(c): return call("POST", V + "/authority/bands", user="s.iqbal",
                      body={"name": "qa-negative", "stages": [["model_risk_manager"]],
                            "tier": 1, "at_or_above": -1})

@case("QA-183", "authority", "An operator may not publish a band", "refused:forbidden")
def _(c): return call("POST", V + "/authority/bands", user="o.perez",
                      body={"name": "qa-operator", "stages": [["model_risk_manager"]], "tier": 1})

@case("QA-184", "authority", "Publish a tier-1 band: first line signs, then second", "accepted")
def _(c): return call("POST", V + "/authority/bands", user="s.iqbal",
                      body={"name": "qa-tier1-band", "stages": [["model_risk_manager"], ["validator"]],
                            "tier": 1, "at_or_above": 0, "note": "QA band"})

@case("QA-185", "authority", "Publish a band whose name is taken", "refused:band_exists")
def _(c): return call("POST", V + "/authority/bands", user="s.iqbal",
                      body={"name": "qa-tier1-band", "stages": [["validator"]], "tier": 1})

@case("QA-186", "authority", "Delegate with no principal named", "refused:principal_required")
def _(c): return call("POST", V + "/authority/delegations", user="s.iqbal",
                      body={"principal": "", "ceiling": 1000000, "instrument": "BR-2026-04"})

@case("QA-187", "authority", "Delegate with no instrument", "refused:instrument_required")
def _(c): return call("POST", V + "/authority/delegations", user="s.iqbal",
                      body={"principal": "a.mehta", "ceiling": 1000000, "instrument": ""})

@case("QA-188", "authority", "Delegate a ceiling of zero", "refused:ceiling_required")
def _(c): return call("POST", V + "/authority/delegations", user="s.iqbal",
                      body={"principal": "a.mehta", "ceiling": 0, "instrument": "BR-2026-04"})

@case("QA-189", "authority", "A new tier-1 version, so the band binds to a fresh approval", "accepted")
def _(c): return call("POST", V + "/models/qa.ews.tier1/versions", body={"semver": "2.0.0", "kernel": KERNEL})

@case("QA-190", "authority", "Open a quorum that the band should shape into stages", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/version-approvals", user="s.iqbal",
                     body={"urn": "maya://model/qa.ews.tier1", "semver": "2.0.0"})
    CTX["band_approval"] = (p or {}).get("id")
    return s, p, raw

@case("QA-191", "authority", "The second stage signs before the first", "refused:out_of_sequence")
def _(c): return call("POST", V + f"/version-approvals/{CTX.get('band_approval')}/sign", user="a.mehta",
                      body={"role": "validator", "decision": "approve", "statement": "out of turn"})

@case("QA-192", "authority", "The first stage signs, with no delegation on record at all", "EXPLORATORY: no_delegated_authority or permitted")
def _(c):
    """Silent where the delegation table is empty — a control that refuses the
    whole estate the day it is switched on is a control that gets switched off
    the same day, and `/authority/estate` reports the absence instead."""
    return call("POST", V + f"/version-approvals/{CTX.get('band_approval')}/sign",
                user="s.iqbal",
                body={"role": "model_risk_manager", "decision": "approve",
                      "statement": "first stage"})

@case("QA-193", "authority", "Delegate a ceiling far below the model's exposure", "accepted")
def _(c): return call("POST", V + "/authority/delegations", user="s.iqbal",
                      body={"principal": "a.mehta", "ceiling": 1000, "instrument": "BR-2026-04",
                            "currency": "USD"})

@case("QA-194", "authority", "Signing above the delegated ceiling", "refused:beyond_delegated_authority")
def _(c):
    """The precondition is the whole finding. `refuse_beyond_delegation` tests
    the ceiling against an exposure that is ATTESTED to a system of record, and
    reports rather than refuses when there is none — so in an estate where
    nobody has recorded a fact source, the ceiling never binds and the control
    looks broken. It is not: it is silent, and `/authority/estate` is where the
    silence is reported. Source the figure and it fires."""
    call("POST", V + "/fact-sourcing/model?urn=maya://model/qa.ews.tier1",
         user="s.iqbal",
         body={"fact": "exposure", "source": "finance_ledger",
               "reference": "GL-2026-Q3-EWS", "value": "50000000000",
               "as_at": 1789000000})
    call("POST", V + "/authority/delegations", user="s.iqbal",
         body={"principal": "s.iqbal", "ceiling": 100000000000,
               "instrument": "BR-2026-06", "currency": "USD"})
    call("POST", V + f"/version-approvals/{CTX.get('band_approval')}/sign",
         user="s.iqbal",
         body={"role": "model_risk_manager", "decision": "approve",
               "statement": "first stage, within my writ"})
    return call("POST", V + f"/version-approvals/{CTX.get('band_approval')}/sign",
                user="a.mehta",
                body={"role": "validator", "decision": "approve",
                      "statement": "beyond my writ"})

@case("QA-195", "authority", "A ceiling in a currency the estate does not report in", "EXPLORATORY: ceiling_not_comparable at delegation or at signing")
def _(c): return call("POST", V + "/authority/delegations", user="s.iqbal",
                      body={"principal": "p.dual", "ceiling": 500000000000, "instrument": "BR-2026-05",
                            "currency": "JPY"})

@case("QA-196", "authority", "What authority applies to one model", "reported")
def _(c): return call("GET", V + "/authority/model?urn=maya://model/qa.ews.tier1")

@case("QA-197", "authority", "The signing sequence for one model", "reported")
def _(c): return call("GET", V + "/authority/sequence?urn=maya://model/qa.ews.tier1")

@case("QA-198", "authority", "Delegations on record", "reported")
def _(c): return call("GET", V + "/authority/delegations")

@case("QA-199", "authority", "Withdraw a band that does not exist", "refused:unknown_band")
def _(c): return call("DELETE", V + "/authority/bands/no-such-band", user="s.iqbal")

# ================================================== M. access recertification
@case("QA-200", "recert", "Open a campaign with a reference nobody quoted", "refused:reference_required")
def _(c): return call("POST", V + "/recertification",
                      body={"reference": "", "reviewer": "s.iqbal", "title": "Q3"})

@case("QA-201", "recert", "Open a campaign whose reviewer is not a principal", "refused:no_such_principal")
def _(c): return call("POST", V + "/recertification",
                      body={"reference": "REC-QA-X", "reviewer": "nobody.here", "title": "Q3"})

@case("QA-202", "recert", "Open a campaign over somebody who is not a principal", "refused:no_such_principal")
def _(c): return call("POST", V + "/recertification",
                      body={"reference": "REC-QA-EMPTY", "reviewer": "s.iqbal", "title": "nobody",
                            "population": ["ghost.person"]})

@case("QA-203", "recert", "Open a campaign over three named people", "accepted")
def _(c): return call("POST", V + "/recertification",
                      body={"reference": "REC-QA-1", "reviewer": "s.iqbal", "title": "QA access review",
                            "population": ["j.okafor", "a.mehta", "s.iqbal"]})

@case("QA-204", "recert", "Open a second campaign under the same reference", "refused:campaign_exists")
def _(c): return call("POST", V + "/recertification",
                      body={"reference": "REC-QA-1", "reviewer": "s.iqbal", "title": "again",
                            "population": ["j.okafor"]})

@case("QA-205", "recert", "The named reviewer answers a row", "accepted")
def _(c): return call("POST", V + "/recertification/REC-QA-1/j.okafor", user="s.iqbal",
                      body={"state": "confirmed", "reason": "still on the desk"})

@case("QA-206", "recert", "Somebody who is not the reviewer answers", "refused:not_the_reviewer")
def _(c): return call("POST", V + "/recertification/REC-QA-1/a.mehta", user="admin",
                      body={"state": "confirmed", "reason": "not my campaign"})

@case("QA-207", "recert", "The reviewer answers their own row", "refused:self_recertification")
def _(c): return call("POST", V + "/recertification/REC-QA-1/s.iqbal", user="s.iqbal",
                      body={"state": "confirmed", "reason": "I certify myself"})

@case("QA-208", "recert", "An answer outside the vocabulary", "refused:unknown_answer")
def _(c): return call("POST", V + "/recertification/REC-QA-1/a.mehta", user="s.iqbal",
                      body={"state": "unsure", "reason": "I do not know"})

@case("QA-209", "recert", "Revoking with no reason", "refused:reason_required")
def _(c): return call("POST", V + "/recertification/REC-QA-1/a.mehta", user="s.iqbal",
                      body={"state": "revoked", "reason": ""})

@case("QA-210", "recert", "Answering for somebody not in the population", "refused:not_in_population")
def _(c): return call("POST", V + "/recertification/REC-QA-1/r.hale", user="s.iqbal",
                      body={"state": "confirmed", "reason": "not in this round"})

@case("QA-211", "recert", "Answering under a reference that does not exist", "refused:forbidden|unknown_recertification")
def _(c): return call("POST", V + "/recertification/REC-NOPE/j.okafor", user="s.iqbal",
                      body={"state": "confirmed", "reason": "no such campaign"})

@case("QA-212", "recert", "Reassign the review with no reason", "refused:reason_required")
def _(c): return call("POST", V + "/recertification/REC-QA-1/reassign",
                      body={"to": "admin", "reason": ""})

@case("QA-213", "recert", "Reassign the review", "accepted")
def _(c): return call("POST", V + "/recertification/REC-QA-1/reassign",
                      body={"to": "admin", "reason": "reviewer on leave"})

@case("QA-214", "recert", "The old reviewer answers after reassignment", "refused:forbidden|not_the_reviewer")
def _(c): return call("POST", V + "/recertification/REC-QA-1/a.mehta", user="s.iqbal",
                      body={"state": "confirmed", "reason": "still mine?"})

@case("QA-215", "recert", "Close the campaign", "accepted")
def _(c): return call("POST", V + "/recertification/REC-QA-1/close")

@case("QA-216", "recert", "Answer a closed campaign", "refused:campaign_closed")
def _(c): return call("POST", V + "/recertification/REC-QA-1/a.mehta",
                      body={"state": "confirmed", "reason": "too late"})

@case("QA-217", "recert", "Read one campaign", "reported")
def _(c): return call("GET", V + "/recertification/REC-QA-1")

@case("QA-218", "recert", "The recertification posture across the estate", "reported")
def _(c): return call("GET", V + "/recertification")

# ==================================================== N. document search
@case("QA-219", "docsearch", "Search with no query at all", "refused:422")
def _(c): return call("GET", V + "/document-search")

@case("QA-220", "docsearch", "Search for a stopword only", "refused:empty_query")
def _(c): return call("GET", V + "/document-search?q=the")

@case("QA-221", "docsearch", "Search with a limit outside the range", "refused:limit_out_of_range")
def _(c): return call("GET", V + "/document-search?q=model&limit=500")

@case("QA-222", "docsearch", "Search with a limit of zero", "refused:limit_out_of_range")
def _(c): return call("GET", V + "/document-search?q=model&limit=0")

@case("QA-223", "docsearch", "Search an estate with no documents", "reported")
def _(c): return call("GET", V + "/document-search?q=backtest")

@case("QA-224", "docsearch", "What the search can and cannot read", "reported")
def _(c): return call("GET", V + "/document-search/coverage")

@case("QA-225", "docsearch", "An operator with no document:read may not search", "refused:forbidden")
def _(c): return call("GET", V + "/document-search?q=backtest", user="o.perez")


M = "maya://model/qa.pd.scorecard"

# ============================================== O. validation and findings
@case("QA-226", "validation", "Open a validation naming the version's author as validator", "EXPLORATORY: refused or permitted at open")
def _(c):
    s, p, raw = call("POST", V + "/validations", user="a.mehta",
                     body={"urn": M, "semver": "1.0.0", "validators": ["a.mehta"], "kind": "initial"})
    CTX["val"] = (p or {}).get("id")
    return s, p, raw

@case("QA-227", "validation", "Record a test result", "accepted")
def _(c): return call("POST", V + f"/validations/{CTX.get('val')}/results", user="a.mehta",
                      body={"test_key": "discrimination.gini",
                            "left": [0.1, 0.2, 0.3, 0.9], "right": [0, 0, 1, 1],
                            "threshold": {"minimum": 0.4}})

@case("QA-228", "validation", "Conclude with no tier verdict", "refused:*")
def _(c): return call("POST", V + f"/validations/{CTX.get('val')}/conclude", user="a.mehta",
                      body={"outcome": "approved", "conditions": []})

@case("QA-229", "validation", "Conclude with a tier verdict that is not remains_appropriate and no note", "refused:*")
def _(c): return call("POST", V + f"/validations/{CTX.get('val')}/conclude", user="a.mehta",
                      body={"outcome": "approved", "tier_verdict": "should_be_higher", "tier_note": ""})

@case("QA-230", "validation", "Conclude a validation the concluder did not run", "EXPLORATORY")
def _(c): return call("POST", V + f"/validations/{CTX.get('val')}/conclude", user="s.iqbal",
                      body={"outcome": "approved", "tier_verdict": "remains_appropriate"})

@case("QA-231", "findings", "Raise a finding against the model", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/findings", user="a.mehta",
                     body={"urn": M, "severity": "High", "title": "QA finding",
                           "owner": "j.okafor", "description": "raised by QA to exercise the workflow",
                           "category": "general", "source": "validation"})
    CTX["finding"] = (p or {}).get("id")
    return s, p, raw

@case("QA-232", "findings", "Raise a finding with a severity nobody defined", "refused:*")
def _(c): return call("POST", V + "/findings", user="a.mehta",
                      body={"urn": M, "severity": "apocalyptic", "title": "bad severity",
                            "owner": "j.okafor"})

@case("QA-233", "findings", "The person who raised a finding closes it", "refused:raiser_may_not_close|verifier_not_self|*")
def _(c): return call("POST", V + f"/findings/{CTX.get('finding')}/close", user="a.mehta",
                      body={"evidence": {"what": "the QA re-fit", "where": "run 1"}})

@case("QA-234", "findings", "Acknowledge the finding as its owner", "accepted")
def _(c): return call("POST", V + f"/findings/{CTX.get('finding')}/acknowledge", user="j.okafor",
                      body={"days": 30, "plan": "re-fit the coefficients and re-validate"})

@case("QA-235", "findings", "The owner who acknowledged it has no finding:extend", "refused:forbidden|self_extension")
def _(c): return call("POST", V + f"/findings/{CTX.get('finding')}/extend", user="j.okafor",
                      body={"reason": "slipped", "days": 30})

@case("QA-236", "findings", "Extend as somebody in the second line", "accepted")
def _(c): return call("POST", V + f"/findings/{CTX.get('finding')}/extend", user="s.iqbal",
                      body={"reason": "the original date was never realistic", "days": 30})

@case("QA-237", "findings", "Findings ageing across the estate", "reported")
def _(c): return call("GET", V + "/findings/ageing")

@case("QA-238", "findings", "A blocking finding stops a warrant resolving", "EXPLORATORY: is high severity blocking?")
def _(c): return call("POST", V + "/resolve?verb=score",
                      body={"urn": M + "@1.0.0", "principal": "svc/qa-runner",
                            "declared_use": "model_development", "environment": "lab"})

@case("QA-239", "findings", "Assign the finding to somebody else", "accepted")
def _(c): return call("POST", V + f"/findings/{CTX.get('finding')}/assign", user="s.iqbal",
                      body={"to": "d.raman", "reason": "the developer owns the re-fit"})

@case("QA-240", "findings", "Close it as somebody who did not raise it", "EXPLORATORY: what closure requires")
def _(c): return call("POST", V + f"/findings/{CTX.get('finding')}/close", user="s.iqbal",
                      body={"evidence": {"what": "the QA re-fit", "where": "run 1"}})

# ============================================================= P. monitoring
@case("QA-241", "monitoring", "The monitor kinds this platform knows", "reported")
def _(c): return call("GET", V + "/monitor-kinds")

@case("QA-242", "monitoring", "Define a monitor", "accepted")
def _(c):
    s, p, raw = call("POST", V + "/monitors", user="j.okafor",
                     body={"urn": M, "name": "qa-psi", "kind": "input_drift", "test_key": "stability.psi",
                           "threshold": {"max": 0.25}, "owner": "j.okafor",
                           "cadence_days": 30})
    CTX["monitor"] = (p or {}).get("id")
    return s, p, raw

@case("QA-243", "monitoring", "Define a monitor with a test key nobody implements", "refused:*")
def _(c): return call("POST", V + "/monitors", user="j.okafor",
                      body={"urn": M, "name": "qa-nonsense", "kind": "input_drift",
                            "test_key": "stability.vibes", "threshold": {"max": 0.25},
                            "owner": "j.okafor"})

@case("QA-244", "monitoring", "Ingest an externally computed value", "accepted")
def _(c):
    """`monitor:observe` belongs to the SERVICE principal and to nobody else:
    the party that runs the model holds the scores, so it hands them over — and
    stops there. Deciding that a monitor has breached is a governance act."""
    _s, p, _raw = call("POST", V + "/api-keys",
                      body={"username": "svc/qa-runner", "name": "qa-observer",
                            "scopes": ["monitor:observe"], "lifetime_days": 30})
    CTX["observer_key"] = (p or {}).get("secret", "")
    return call("POST", V + f"/monitors/{CTX.get('monitor')}/ingest", user=None,
                headers={"x-api-key": CTX.get("observer_key", "")},
                      body={"value": 0.11, "computed_by": "the bank's own drift job",
                            "method": "psi over 10 deciles",
                            "window_start": 1.79e9, "window_end": 1.7905e9})

@case("QA-245", "monitoring", "An ingest that tries to mark its own homework", "refused:422")
def _(c): return call("POST", V + f"/monitors/{CTX.get('monitor')}/ingest", user=None,
                      headers={"x-api-key": CTX.get("observer_key", "")},
                      body={"value": 0.99, "computed_by": "an optimistic engine",
                            "window_start": 1.79e9, "window_end": 1.7905e9, "passed": True})

@case("QA-246", "monitoring", "Ingest a value that breaches the threshold", "reported")
def _(c): return call("POST", V + f"/monitors/{CTX.get('monitor')}/ingest", user=None,
                      headers={"x-api-key": CTX.get("observer_key", "")},
                      body={"value": 0.91, "computed_by": "the bank's own drift job",
                            "method": "psi over 10 deciles",
                            "window_start": 1.7906e9, "window_end": 1.791e9})

@case("QA-247", "monitoring", "Observations on the monitor", "reported")
def _(c): return call("GET", V + f"/monitors/{CTX.get('monitor')}/observations")

@case("QA-248", "monitoring", "Evaluate a drift monitor with no rows and no reference", "refused:no_reference")
def _(c): return call("POST", V + f"/monitors/{CTX.get('monitor')}/evaluate", user="o.perez",
                      body={"rows": []})

@case("QA-249", "monitoring", "Run the governance batch", "accepted")
def _(c): return call("POST", V + "/scheduler/run", user="o.perez", body={})

@case("QA-250", "monitoring", "Scheduler history after the run", "reported")
def _(c): return call("GET", V + "/scheduler/history", user="o.perez")


# ============================================== Q. portfolio and the fold cache
@case("QA-251", "portfolio", "The dimensions a portfolio may be cut by", "reported")
def _(c): return call("GET", V + "/portfolio/dimensions")

@case("QA-252", "portfolio", "Portfolio by tier (enters the estate fold)", "accepted")
def _(c): return call("GET", V + "/portfolio?dimension=tier")

@case("QA-253", "portfolio", "Portfolio by a dimension nobody defined", "refused:unknown_dimension")
def _(c): return call("GET", V + "/portfolio?dimension=nonsense")

@case("QA-254", "portfolio", "A heatmap of one dimension against itself", "refused:same_dimension")
def _(c): return call("GET", V + "/portfolio/heatmap?rows=tier&columns=tier")

@case("QA-255", "portfolio", "A heatmap of domain against tier", "accepted")
def _(c): return call("GET", V + "/portfolio/heatmap?rows=domain&columns=tier")

@case("QA-256", "portfolio", "Portfolio by trainability class", "accepted")
def _(c): return call("GET", V + "/portfolio?dimension=trainability_class")

@case("QA-257", "portfolio", "The portfolio trend over twelve points", "accepted")
def _(c): return call("GET", V + "/portfolio/trend?points=12&span_days=365")

@case("QA-258", "portfolio", "Aggregate risk across the estate", "accepted")
def _(c): return call("GET", V + "/portfolio/aggregate")

@case("QA-259", "portfolio", "The notification batch dry run (folds over the whole estate)", "accepted")
def _(c): return call("POST", V + "/notifications/run", user="o.perez", body={"dry_run": True})

@case("QA-260", "portfolio", "An operator with no report:read may not cut the portfolio", "EXPLORATORY: does operator hold report:read?")
def _(c): return call("GET", V + "/portfolio?dimension=tier", user="o.perez")

# =============================================================== R. the screens
PAGES = [
    ("/dashboard", "Dashboard"), ("/models/new", "Register a model"),
    ("/features", "Features"), ("/features/new", "Define a feature"),
    ("/features/load", "Load values"), ("/features/point-in-time", "Point in time"),
    ("/featuresets", "Featuresets"), ("/featuresets/author", "Compose a featureset"),
    ("/featuresets/lattice", "The featureset lattice"),
    ("/model-algebra", "Model algebra"), ("/warrants", "Warrants"),
    ("/warrants/estate", "Who may run what"), ("/findings", "Findings"),
    ("/portfolio", "Portfolio"), ("/model-health", "Model health"),
    ("/documents/search", "Document search"), ("/query", "Query"),
    ("/notifications", "Notifications"), ("/policies", "Policies"),
    ("/waivers", "Waivers"), ("/limitations", "Limitations"),
    ("/assumptions", "Assumptions"), ("/classification", "Classification"),
    ("/campaigns", "Campaigns"), ("/break-glass", "Break glass"),
    ("/supervisory", "Supervisory matters"), ("/vendor-models", "Vendor models"),
    ("/board-pack", "Board pack"), ("/dependencies", "Dependencies"),
    ("/telemetry", "Telemetry"), ("/lifecycle-profiles", "Lifecycle profiles"),
    ("/packages", "Packages"), ("/assist", "Assist"), ("/tutorials", "Tutorials"),
    ("/help", "Help"), ("/about", "About"),
    ("/admin", "Admin"), ("/admin/principals", "People and roles"),
    ("/admin/api-keys", "API keys"), ("/admin/evidence", "Evidence"),
    ("/admin/logs", "Live log"), ("/admin/regimes", "Regimes"),
    ("/admin/runtimes", "Runtimes"), ("/admin/scheduler", "Scheduler"),
    ("/admin/perimeter", "Perimeter"),
]

# A SCREEN is driven through a browser session, not HTTP Basic. The UI routes
# ignore Basic entirely and render the sign-in page with 200, so a screen test
# authenticated the way an API test is authenticated proves nothing at all —
# it was passing on the login page for every one of these paths.
for _i, (_path, _label) in enumerate(PAGES, start=261):
    @case(f"QA-{_i}", "screens", f"{_label} ({_path}) as admin", "accepted")
    def _(c, p=_path): return page(p, "admin")

@case("QA-306", "screens", "The dashboard with no session at all", "reported")
def _(c): return page("/dashboard", None)

@case("QA-307", "screens", "Admin -> People and roles as an auditor", "accepted")
def _(c):
    """The third line reads everything, and `auditor` carries `principal:read`.
    Expected 403 first time round, which was the case being wrong rather than
    the screen: who holds what access is exactly what an auditor looks at."""
    return page("/admin/principals", "r.hale")

@case("QA-308", "screens", "Admin -> API keys as a feature curator", "refused:403")
def _(c): return page("/admin/api-keys", "q.tester")

@case("QA-309", "screens", "The live log as a model developer", "EXPLORATORY: does model_developer hold log:read?")
def _(c): return page("/admin/logs", "d.raman")

@case("QA-310", "screens", "A model page for a model that does not exist", "refused:404")
def _(c): return page("/model/no.such.model", "admin")

@case("QA-311", "screens", "A model page as somebody scoped to another legal entity", "refused:403")
def _(c):
    call("POST", V + "/principals",
         body={"username": "uk.reader", "display_name": "UK reader",
               "roles": ["auditor"], "password": USERS["uk.reader"],
               "legal_entities": ["LE-UK-99"]})
    return page("/model/qa.pd.scorecard", "uk.reader")

@case("QA-312", "screens", "The dashboard as every non-admin role in turn", "reported")
def _(c):
    out = []
    for who in ("q.tester", "s.iqbal", "j.okafor", "a.mehta", "d.raman",
                "r.hale", "o.perez"):
        s, _, _ = page("/dashboard", who)
        out.append(f"{who}={s}")
    ok = all(x.endswith("=200") for x in out)
    return (200 if ok else 500), {"seen": out}, "; ".join(out)

@case("QA-313", "screens", "The navbar offers no page the role is then refused", "reported")
def _(c):
    """A screen that offers a control and then refuses it is the thing the QA
    cheatsheet asks a tester to report."""
    broken = []
    for who in ("q.tester", "s.iqbal", "j.okafor", "a.mehta", "d.raman",
                "r.hale", "o.perez"):
        _s, _p, body = page("/dashboard", who)
        for link in navbar_links(body):
            st, _, _ = page(link, who)
            if st >= 400:
                broken.append(f"{who} is offered {link} and gets {st}")
    return (200 if not broken else 500), {"broken": broken}, \
        "; ".join(broken) or "every navbar link the role is offered, it can open"

@case("QA-314", "screens", "No navbar link points at a model the register cannot address", "reported")
def _(c):
    _s, _p, body = page("/dashboard", "admin")
    dead = []
    for link in navbar_links(body):
        if link.startswith("/model/"):
            st, _, _ = page(link, "admin")
            if st >= 400:
                dead.append(f"{link} -> {st}")
    return (200 if not dead else 500), {"dead": dead}, \
        "; ".join(dead) or "no dead model links on the dashboard"


def run_all(only=None):
    counts: dict = {}
    for c in CASES:
        if only and not c["id"].startswith(only) and only != c["area"]:
            continue
        LAST.clear()
        try:
            answer = c["fn"](CTX)
            if isinstance(answer, tuple) and len(answer) == 3:
                status, parsed, payload = answer
            else:
                status = LAST.get("status", 0)
                parsed, payload = LAST.get("parsed"), LAST.get("payload", "")
        except Exception:
            status, parsed, payload = -1, None, traceback.format_exc()[-600:]
        v = verdict_of(c["expect"], status, parsed)
        RESULTS.append(dict(id=c["id"], area=c["area"], action=c["action"],
                            expect=c["expect"], call=LAST.get("call", ""),
                            status=status, body=(payload or "")[:1500], verdict=v))
        counts[v] = counts.get(v, 0) + 1
        print(f"{c['id']:8} {v:12} {status:4} {c['expect'][:32]:32} {c['action'][:56]}")
        if v != "PASS":
            print("         ->", (payload or "")[:280].replace("\n", " "))
    print("\n", counts)
    return counts


def enumerate_table():
    print("| ID | Area | Action | Expectation |")
    print("|---|---|---|---|")
    for c in CASES:
        print(f"| {c['id']} | {c['area']} | {c['action']} | `{c['expect']}` |")


def markdown():
    print("| ID | Result | Status | Answer |")
    print("|---|---|---|---|")
    for r in RESULTS:
        answer = r["body"][:160].replace("|", "\\|").replace("\n", " ")
        print(f"| {r['id']} | {r['verdict']} | {r['status']} | `{answer}` |")


def main() -> int:
    global BASE
    p = argparse.ArgumentParser(description="Run the MAYA QA cases.")
    p.add_argument("--url", default=BASE)
    p.add_argument("--run", nargs="?", const="", default=None,
                   help="run everything, or one ID prefix or area")
    p.add_argument("--enumerate", action="store_true")
    p.add_argument("--markdown", action="store_true")
    p.add_argument("--out", default="")
    args = p.parse_args()
    BASE = args.url.rstrip("/")
    if args.enumerate or args.run is None:
        enumerate_table()
        return 0
    counts = run_all(args.run or None)
    if args.markdown:
        markdown()
    if args.out:
        pathlib.Path(args.out).write_text(
            "\n".join(json.dumps(r) for r in RESULTS), encoding="utf-8")
    return 0 if not counts.get("FAIL") else 1


if __name__ == "__main__":
    sys.exit(main())
