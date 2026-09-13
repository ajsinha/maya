"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A real application, a throwaway database, and two principals.

The QA run performs every mutating operation it names — it registers,
approves, revokes and deletes. Pointing that at a register anybody cares about
is destruction rather than testing, so this builds a fresh instance under a
temporary directory and takes it down afterwards.

**Two principals, not one.** Half the case list is about refusal, and a run
with only an administrator cannot tell a screen that checks its permission
from one that does not — every page renders, and the run reports a clean pass
over a control it never exercised.
"""
from __future__ import annotations

import contextlib
import re
import pathlib
import shutil
import sys
import tempfile
from typing import Iterator, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

#: A principal with an account and, deliberately, almost nothing else.
#:
#: Not "no roles at all": an unauthenticated caller is refused by the
#: authentication layer, which is a different control from the authorisation
#: one, and using it would report every permission check as working while
#: never reaching one.
UNPRIVILEGED = ("qa-observer", "qa-observer-password")
UNPRIVILEGED_ROLES = ["operator"]

ADMIN = ("admin", "maya-admin-dev")

#: One principal per duty, because an attestation cannot be signed by one
#: person however many permissions they hold.
#:
#: `admin` holds every *permission* and none of the *roles*, so signing as
#: model_owner is refused `role_not_held` — segregation of duties working
#: exactly as designed, and the reason a QA estate needs real people in it
#: rather than one superuser.
PEOPLE = {
    "owner": (["model_owner"], "qa-owner-password"),
    "developer": (["model_developer"], "qa-developer-password"),
    "validator": (["validator"], "qa-validator-password"),
    "risk": (["model_risk_manager"], "qa-risk-password"),
    "auditor": (["auditor"], "qa-auditor-password"),
}

CONFIG = """
app: {{name: MAYA, version: "0.1.0", tagline: "Model & AI Lifecycle Assurance",
       slogan: "Evidence, not assertion.",
       principle: "A model is a representation of the world. Governance is knowing the difference."}}
server: {{host: 0.0.0.0, port: 5006}}
database: {{url: "sqlite:///{root}/data/sqlite/maya.db"}}
data: {{dir: "{root}/data", artifacts: "{root}/data/artifacts",
        attachments: "{root}/data/attachments",
        delta: {{dir: "{root}/data/delta", features: "{root}/data/delta/features",
                snapshots: "{root}/data/delta/snapshots",
                telemetry: "{root}/data/delta/telemetry",
                monitoring: "{root}/data/delta/monitoring"}}}}
risk:
  exposure_bands: {{negligible: 0, low: 1000000, moderate: 50000000,
                   material: 500000000, critical: 5000000000}}
  purpose_ranks: {{commercial: 1, valuation: 2, risk_management: 2,
                  customer_facing: 3, credit_decision: 3,
                  financial_reporting: 3, policy_decision: 4,
                  clinical_decision: 4, regulatory_capital: 4}}
  review_months: {{1: 12, 2: 18, 3: 24, 4: 36}}
warrants: {{jitter_pct: 0, signing_key: qa-signing-secret,
         ttl_seconds: {{1: 60, 2: 300, 3: 3600, 4: 3600}},
         grace_seconds: {{1: 0, 2: 0, 3: 900, 4: 900}}}}
execution: {{captive: {{enabled: true, max_seconds: 5}}}}
logging: {{level: ERROR}}
"""


def carry_csrf(client) -> None:
    """Read the session's CSRF token off a page and send it on every request.

    A session-authenticated request that changes something is refused
    `csrf_token_invalid` without it — and 403 is under 500, so the case
    *passed*. **238 of 611 operations in section A were answered
    `csrf_token_invalid` and recorded as exercised.** They were never reached.

    Same shape as every other harness defect in this run: a check that passes
    for a reason other than the one it names. It is also the reason the API
    half now uses its own Basic-authenticated client — an API caller is not a
    browser, does not carry a session, and is not subject to CSRF, so making
    the API section pass by bolting a browser token onto it would be testing a
    combination nothing in production produces.
    """
    from core.authz.csrf import HEADER, META
    page = client.get("/dashboard")
    found = re.search(rf'name="{META}"[^>]*content="([^"]+)"', page.text)
    if not found:
        found = re.search(rf'content="([^"]+)"[^>]*name="{META}"', page.text)
    if not found:
        raise RuntimeError(
            "no CSRF token in the page: every mutating UI request would be "
            "refused and, being a 403, would be recorded as a considered "
            "answer rather than as never having run")
    client.headers[HEADER] = found.group(1)


def sign_in(client) -> None:
    """Establish a UI session. Safe to call again at any point.

    Needed as a *re-usable* step, not just a setup step: the run calls every
    operation the platform publishes, and one of them is `GET /logout`. Sorted
    by path, `/logout` lands before `/model/...`, so a single sign-in at the
    start left every UI case afterwards signed out — answering 200 with the
    sign-in form and reporting twenty-one screens as broken when the runner had
    simply logged itself out.
    """
    posted = client.post("/login",
                         data={"username": ADMIN[0], "password": ADMIN[1],
                               "next": "/dashboard"},
                         follow_redirects=False)
    if posted.status_code not in (200, 302, 303):
        raise RuntimeError(
            f"could not sign in to the interface ({posted.status_code}) — "
            f"every screen would answer 200 with the sign-in form and the run "
            f"would report a pass over pages it never opened")


@contextlib.contextmanager
def live_client() -> Iterator[Tuple[object, Tuple[str, str]]]:
    """A client authenticated as an administrator, and one that is not."""
    from fastapi.testclient import TestClient

    from core.config import PropertiesConfigurator
    from run_maya_web import create_app

    workspace = pathlib.Path(tempfile.mkdtemp(prefix="maya-qa-"))
    cfg = workspace / "application.yaml"
    cfg.write_text(CONFIG.format(root=workspace), encoding="utf-8")
    PropertiesConfigurator.reset()
    app = create_app(PropertiesConfigurator(str(cfg), reload_interval=0))
    try:
        # `raise_server_exceptions=False` so an unhandled exception comes
        # back as the 500 a real caller would receive, instead of propagating
        # into the runner and ending the pass. The first unhandled error found
        # by this run — a `KeyError` on a missing body field — would otherwise
        # have stopped it at case 60 of 603 and reported nothing about the
        # other 543.
        with TestClient(app, raise_server_exceptions=False) as client:
            client.auth = ADMIN
            made = client.post("/api/v1/principals", json={
                "username": UNPRIVILEGED[0], "display_name": "QA observer",
                "roles": UNPRIVILEGED_ROLES, "password": UNPRIVILEGED[1]})
            if made.status_code not in (200, 201, 409):
                raise RuntimeError(
                    f"could not create the unprivileged principal "
                    f"({made.status_code} {made.text[:200]}) — a run without "
                    f"one reports every permission check as working while "
                    f"never reaching one")
            # Sign in through the FORM, not only with Basic credentials.
            #
            # The API accepts HTTP Basic; the interface wants a session cookie,
            # and a UI route without one answers **200 with the sign-in page**.
            # A run authenticated only with Basic sees every screen return 200
            # and reports a clean pass over pages it never opened — while
            # `/model/does-not-exist` looks like a 200 that should have been a
            # 404, when the runner was simply never logged in.
            #
            # Second time that trap has been hit here: a performance spike once
            # timed the sign-in page and reported it as a fast dashboard.
            # Status is not evidence of having reached a page.
            sign_in(client)
            carry_csrf(client)
            landing = client.get("/dashboard")
            if "sign in" in landing.text[:4000].lower():
                raise RuntimeError(
                    "signed in, and /dashboard still renders the sign-in "
                    "form — the session cookie is not being carried")
            # A SEPARATE client for the unprivileged principal.
            #
            # Passing `auth=` on the signed-in client does not make a request
            # unprivileged: the admin session cookie travels with it and the
            # app authenticates from the session, so every "refused without
            # the permission" case was actually being made as an
            # administrator. It reported a clean pass — the pages rendered,
            # and before the session existed both halves of every screen case
            # were the sign-in form, so the refusal check passed trivially in
            # both directions.
            #
            # Two clients, no shared cookie jar, and the distinction is real.
            # A THIRD client for the API: Basic credentials, no session
            # cookie, no CSRF. That is what an API caller actually is, and it
            # is the only configuration under which the API half of this run
            # exercises the operations rather than the CSRF guard.
            with (TestClient(app, raise_server_exceptions=False) as observer,
                  TestClient(app, raise_server_exceptions=False) as api):
                observer.auth = UNPRIVILEGED
                api.auth = ADMIN
                for username, (roles, password) in PEOPLE.items():
                    made = api.post("/api/v1/principals", json={
                        "username": username, "display_name": username,
                        "roles": roles, "password": password})
                    if made.status_code not in (200, 201, 409):
                        raise RuntimeError(
                            f"could not create {username}: "
                            f"{made.status_code} {made.text[:160]}")
                yield client, api, observer
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
