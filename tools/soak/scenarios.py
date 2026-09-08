"""
MAYA — what the soak actually does, and what it asserts while doing it.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Two kinds of thing live here and they answer different questions.

**Scenarios** drive real work: register a model, take it through a quorum,
issue a warrant, load a matrix feature, resolve a featureset. Each one is a
path a bank would actually walk, and each asserts the refusals along the way as
firmly as the successes — because on this platform a control that permits what
it should refuse is the defect, and it is invisible unless somebody tries.

**Invariants** assert what must be true at every instant, whatever has
happened. They run between batches, over and over, and they are the reason a
soak is worth six hours rather than six minutes. A hash chain verifies easily
after ten appends; the question is whether it still verifies after ten thousand
from four writers. A sequence with no gaps is unremarkable until something has
been contending for it all afternoon.

Every scenario is written to be repeatable against a database that is filling
up. Names are suffixed with the cycle number, and nothing assumes it is the
only thing that has ever run — a soak whose scenarios interfere with each other
is measuring itself.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

#: The kernel and contract the unit fixtures use, so the soak is asking the
#: platform the same question the suite does. Written from `tests/conftest.py`
#: rather than invented: a first draft here declared `reads`/`writes`/`form`
#: and was refused with a sentence naming every field a kernel actually takes,
#: which is the platform working and the harness being wrong.
KERNEL = {
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "input_schema": [{"name": "dscr", "dtype": "float",
                      "minimum": -5, "maximum": 20}],
    "output_schema": [{"name": "pd_12m", "dtype": "float"}],
}
CONTRACT = {
    "assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
    "guarantees": [{"key": "gini", "minimum": 0.42}],
    "on_boundary_violation": "reject",
}

#: Everybody the soak acts as. Duties are separated because they are separated
#: in the platform: one account cannot walk the whole path, and a soak that ran
#: as `admin` throughout would exercise none of the segregation this system's
#: argument rests on.
PEOPLE = {
    "soak.dev": (["model_developer"], "soak-dev-password-long"),
    "soak.owner": (["model_owner"], "soak-owner-password-long"),
    "soak.val": (["validator"], "soak-val-password-long"),
    "soak.mrm": (["model_risk_manager"], "soak-mrm-password-long"),
    "soak.audit": (["auditor"], "soak-audit-password-long"),
    "soak.ops": (["operator"], "soak-ops-password-long"),
}


def creds(username: str):
    return (username, PEOPLE[username][1])


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def refusal_code(body: Any) -> str:
    return (body or {}).get("error", "") if isinstance(body, dict) else ""


# =========================================================================
#  Set-up: done once, and checked, because everything after it assumes it
# =========================================================================
def bootstrap(client, journal) -> None:
    for username, (roles, password) in PEOPLE.items():
        status, _ = client.post("/principals", {
            "username": username, "display_name": username,
            "roles": roles, "password": password})
        journal.check("bootstrap", f"create {username}",
                      status in (201, 409), "201 or already there", status)
    status, _ = client.post("/principals", {
        "username": "svc/soak-runner", "display_name": "soak runner",
        "kind": "service", "roles": ["service"]})
    journal.check("bootstrap", "create the service principal",
                  status in (201, 409), "201 or already there", status)


# =========================================================================
#  Scenarios
# =========================================================================
def governed_lifecycle(client, journal, cycle: int) -> Dict[str, Any]:
    """A model from registration to a signed, executable warrant.

    The whole promise in one path, and the reason it is repeated rather than
    run once: every step reads state the previous cycles have left behind, and
    a control that works on an empty database and not a full one is a control
    that fails in production and nowhere else.
    """
    name = f"soak.pd.{cycle:05d}"
    urn = f"maya://model/{name}"
    family = "lifecycle"
    out = {"name": name, "urn": urn, "reached": "none"}

    status, body = client.post("/models", {
        "urn": urn, "name": f"Soak PD {cycle}", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/soak.owner",
        "legal_entity": "LE-UK-01",
        "purpose": "12-month PD at origination"}, auth=creds("soak.owner"))
    if not journal.check(family, "register a model", status == 201, 201, status,
                         json.dumps(body)[:300]):
        return out
    out["reached"] = "registered"

    status, body = client.post(f"/models/{name}/assess", {
        "exposure": 2.0e9, "purpose_class": "regulatory_capital",
        "feature_count": 12, "uses_alternative_data": False,
        "interpretable": True}, auth=creds("soak.owner"))
    journal.check(family, "tier it from its exposure and purpose",
                  status == 200 and (body or {}).get("tier") in (1, 2, 3, 4),
                  "200 with a tier", f"{status} {(body or {}).get('tier')}")

    # A DEVELOPER creates the version. The owner may not, and the developer may
    # not then approve it: that is the whole point of the next three checks.
    status, body = client.post(f"/models/{name}/versions", {
        "semver": "1.0.0", "kernel": KERNEL, "contract": CONTRACT,
        "artifact_digest": digest(f"{name}-1.0.0")}, auth=creds("soak.dev"))
    if not journal.check(family, "a developer creates a version",
                         status == 201, 201, status, json.dumps(body)[:300]):
        return out
    out["reached"] = "versioned"

    status, body = client.post(f"/models/{name}/versions/1.0.0/approve",
                               auth=creds("soak.dev"))
    journal.check(family, "the creator may NOT approve their own version",
                  status in (403, 409, 422), "a refusal",
                  f"{status} {refusal_code(body)}")

    # Opened by the risk manager, not the owner: opening a quorum needs
    # `version:approve`, which `model_owner` does not carry. The refusal named
    # the permission and the role, which is how this was found.
    status, body = client.post("/version-approvals",
                               {"urn": urn, "semver": "1.0.0"},
                               auth=creds("soak.mrm"))
    approval = (body or {}).get("id") or (body or {}).get("approval_id")
    if not journal.check(family, "open a quorum on the version",
                         status in (200, 201) and approval, "an approval id",
                         f"{status} {json.dumps(body)[:200]}"):
        return out

    signed = 0
    for who, role in (("soak.mrm", "model_risk_manager"), ("soak.val", "validator")):
        status, body = client.post(f"/version-approvals/{approval}/sign",
                                   {"role": role, "decision": "approve"},
                                   auth=creds(who))
        if journal.check(family, f"{role} signs the quorum",
                         status in (200, 201), "200/201",
                         f"{status} {json.dumps(body)[:200]}"):
            signed += 1
    out["reached"] = "quorum" if signed else out["reached"]

    # The RECORD, not the version. Two different things go through two
    # different gates, and the soak's first draft did only the version — so
    # every resolve was refused with `policy_refused`: "a warrant resolves only
    # against an approved version of a model whose own record has been put
    # through the register". Which is the platform working, and the scenario
    # being an incomplete description of the job.
    status, body = client.post(f"/models/{name}/submit", {},
                               auth=creds("soak.owner"))
    journal.check(family, "submit the model RECORD to the register",
                  status in (200, 201), "200/201",
                  f"{status} {json.dumps(body)[:200]}")
    status, body = client.post(f"/models/{name}/approve", {},
                               auth=creds("soak.mrm"))
    journal.check(family, "the risk manager approves the record",
                  status in (200, 201), "200/201",
                  f"{status} {json.dumps(body)[:200]}")
    for who, role in (("soak.mrm", "model_risk_manager"),
                      ("soak.owner", "model_owner")):
        status, body = client.post(f"/models/{name}/attest",
                                   {"role": role, "decision": "attest"},
                                   auth=creds(who))
        journal.check(family, f"{role} attests the record",
                      status in (200, 201), "200/201",
                      f"{status} {json.dumps(body)[:200]}")

    status, body = client.put(f"/models/{name}/aliases", {
        "environment": "prod", "alias": "champion", "semver": "1.0.0"},
        auth=creds("soak.mrm"))
    if not journal.check(family, "promote it to prod champion",
                         status in (200, 201), "200/201",
                         f"{status} {json.dumps(body)[:250]}"):
        return out
    out["reached"] = "promoted"

    status, body = client.post("/warrants", {
        "urn": f"{urn}#champion", "environment": "prod",
        "principal": "svc/soak-runner", "declared_use": "origination_decision"},
        auth=creds("soak.owner"))
    if not journal.check(family, "issue a standing warrant",
                         status in (200, 201), "200/201",
                         f"{status} {json.dumps(body)[:250]}"):
        return out
    out["reached"] = "warranted"

    status, body = client.post("/resolve", {
        "urn": f"{urn}#champion", "environment": "prod",
        "principal": "svc/soak-runner", "declared_use": "origination_decision"},
        auth=creds("soak.owner"))
    journal.check(family, "resolve a signed descriptor",
                  status == 200 and (body or {}).get("signature"),
                  "200 with a signature",
                  f"{status} {json.dumps(body)[:300]}")
    if status == 200:
        out["reached"] = "resolved"
        out["descriptor"] = body
    return out


def refusals_that_must_hold(client, journal, cycle: int, model: Dict[str, Any]) -> None:
    """The controls, tried directly. A refusal nobody attempts is a claim.

    Every one of these has a specific failure mode where the platform would
    say yes, and every one of them would be invisible to a test suite that only
    walked the happy path.
    """
    family = "refusals"
    name = model.get("name")
    if not name or model.get("reached") == "none":
        return
    urn = model["urn"]

    status, body = client.post("/resolve", {
        "urn": f"{urn}#champion", "environment": "prod",
        "principal": "svc/soak-runner", "declared_use": "something_else"},
        auth=creds("soak.owner"))
    journal.check(family, "a use that was never approved is refused",
                  status >= 400, "a refusal", f"{status} {refusal_code(body)}")

    status, body = client.post("/resolve", {
        "urn": f"{urn}#champion", "environment": "prod",
        "principal": "svc/nobody-asked", "declared_use": "origination_decision"},
        auth=creds("soak.owner"))
    journal.check(family, "a principal with no entitlement is refused",
                  status >= 400 and refusal_code(body) in
                  ("no_entitlement", "forbidden", "not_found", "restricted"),
                  "no_entitlement", f"{status} {refusal_code(body)}")

    status, body = client.post("/resolve", {
        "urn": f"{urn}#champion", "environment": "uat",
        "principal": "svc/soak-runner", "declared_use": "origination_decision"},
        auth=creds("soak.owner"))
    journal.check(family, "an environment it was never promoted to is refused",
                  status >= 400, "a refusal", f"{status} {refusal_code(body)}")

    status, body = client.post(f"/models/{name}/versions", {
        "semver": "1.0.0", "kernel": KERNEL, "contract": CONTRACT,
        "artifact_digest": digest("different-bytes-same-semver")},
        auth=creds("soak.dev"))
    journal.check(family, "the same semver cannot be created twice",
                  status >= 400, "a refusal", f"{status} {refusal_code(body)}")

    status, body = client.post("/models", {
        "urn": urn, "name": "duplicate", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/soak.owner",
        "legal_entity": "LE-UK-01", "purpose": "a second registration"},
        auth=creds("soak.owner"))
    journal.check(family, "a urn cannot be registered twice",
                  status >= 400, "a refusal", f"{status} {refusal_code(body)}")

    status, body = client.post(f"/models/{name}/versions", {
        "semver": "9.9.9", "kernel": KERNEL, "contract": CONTRACT,
        "artifact_digest": digest("audit")}, auth=creds("soak.audit"))
    journal.check(family, "an auditor may read everything and write nothing",
                  status == 403, 403, f"{status} {refusal_code(body)}")

    status, body = client.put(f"/models/{name}/aliases", {
        "environment": "prod", "alias": "champion", "semver": "1.0.0"},
        auth=creds("soak.dev"))
    journal.check(family, "a developer may not promote into an environment",
                  status >= 400, "a refusal", f"{status} {refusal_code(body)}")

    status, body = client.post("/principals", {
        "username": f"soak.dualhat.{cycle}", "display_name": "dual hat",
        "roles": ["model_developer", "model_risk_manager"],
        "password": "dual-hat-password-long"})
    journal.check(family, "incompatible roles cannot be held by one person",
                  status >= 400 and refusal_code(body) in
                  ("incompatible_roles", "incompatible_permissions"),
                  "incompatible_roles", f"{status} {refusal_code(body)}")

    status, body = client.post("/principals", {
        "username": f"soak.weak.{cycle}", "display_name": "weak",
        "roles": ["auditor"], "password": "short"})
    journal.check(family, "a password below the floor is refused AT CREATION",
                  status >= 400, "a refusal", f"{status} {refusal_code(body)}")

    status, body = client.get("/models", auth=("soak.dev", "wrong-password"))
    journal.check(family, "a wrong password is refused",
                  status == 401, 401, status)

    status, body = client.get("/models", auth=None)
    journal.check(family, "an anonymous caller is refused",
                  status == 401, 401, status)


def features_and_shapes(client, journal, cycle: int) -> None:
    """A scalar, a twelve-element array and a 3x3 matrix, defined and read back.

    Shapes are here because they were broken and nobody noticed: an array or
    matrix feature could be defined and then not loaded, which is a definition
    the platform accepted and could not honour.
    """
    family = "features"
    suffix = f"_{cycle:05d}"
    for spec, label in (
            ({"name": "soak_dscr" + suffix, "entity": "borrower",
              "dtype": "numeric", "description": "debt service coverage",
              "owner": "person/soak.dev"}, "a scalar"),
            ({"name": "soak_balances" + suffix, "entity": "borrower",
              "dtype": "numeric", "shape": [12],
              "description": "twelve monthly balances",
              "owner": "person/soak.dev"}, "an array of twelve"),
            ({"name": "soak_corr" + suffix, "entity": "borrower",
              "dtype": "numeric", "shape": [3, 3],
              "description": "a 3x3 correlation matrix",
              "owner": "person/soak.dev"}, "a 3x3 matrix")):
        status, body = client.post("/features", spec, auth=creds("soak.dev"))
        journal.check(family, f"define {label}", status == 201, 201,
                      f"{status} {json.dumps(body)[:200]}")
        # `/resolved` rather than `/features/{name}`: the latter does not
        # exist, and finding that out from a 405 rather than from a guess is
        # the reason the smoke run happens before the six-hour one.
        status, body = client.get(f"/features/{spec['name']}/resolved",
                                  auth=creds("soak.dev"))
        journal.check(family, f"read {label} back",
                      status == 200, "200 with its resolved definition",
                      f"{status} {json.dumps(body)[:200]}")

    status, body = client.get("/features", auth=creds("soak.audit"))
    journal.check(family, "the catalogue lists what was defined",
                  status == 200 and isinstance(
                      (body or {}).get("features", body), (list, dict)),
                  "200 with a list", status)


def detail_pages(client, journal, cycle: int, model: Dict[str, Any]) -> None:
    """The pages that answer *what is this thing*, on things this run made.

    Added because two of them were unreachable and nothing noticed: a detail
    page that renders only when somebody types its URL is a page no test and no
    person ever opens. Driven here against a REAL feature and a REAL model that
    this cycle created, so the pages are asked about data rather than about
    nothing.
    """
    family = "details"
    feature = f"soak_dscr_{cycle:05d}"
    status, html = client.page(f"/feature/{feature}", creds("soak.dev"))
    journal.check(family, "the feature detail page renders",
                  status == 200 and not client.is_sign_in(html), 200, status)
    journal.check(family, "and shows the seal and lifetime the register holds",
                  "Declared shape" in html and "Created" in html,
                  "the defining attributes",
                  "shown" if "Declared shape" in html else "MISSING")

    status, html = client.page("/features", creds("soak.dev"))
    linked = f'href="/feature/{feature}"' in html
    journal.check(family, "and the catalogue links to it",
                  linked, "a link in the catalogue",
                  "linked" if linked else "NOT LINKED")

    matrix = f"soak_corr_{cycle:05d}"
    status, html = client.page(f"/feature/{matrix}", creds("soak.dev"))
    journal.check(family, "a matrix feature's page shows its declared shape",
                  status == 200 and "Declared shape" in html,
                  "200 naming the shape", status)

    name = model.get("name")
    if name and model.get("reached") != "none":
        status, html = client.page(f"/model/{name}", creds("soak.mrm"))
        journal.check(family, "the model page renders",
                      status == 200 and not client.is_sign_in(html), 200, status)
        journal.check(family, "and offers the specification editor",
                      "/specification" in html, "a link to the LaTeX editor",
                      "offered" if "/specification" in html else "MISSING")
        # Written by whoever writes the model's mathematics, which is not the
        # person who approves it. `soak.mrm` is refused here and that refusal
        # is correct — the harness was asking as the wrong persona.
        status, html = client.page(f"/model/{name}/specification",
                                   creds("soak.dev"))
        journal.check(family, "the LaTeX specification editor opens",
                      status == 200 and "katex" in html.lower(),
                      "200 with the maths renderer", status)


def evidence_and_chain(client, journal) -> Dict[str, Any]:
    """Read the chain. The invariant checks verify it; this reads it as a user."""
    family = "evidence"
    status, body = client.get("/evidence/chain?limit=5", auth=creds("soak.audit"))
    journal.check(family, "an auditor may read the chain",
                  status == 200, 200, status)
    return body if isinstance(body, dict) else {}


def platform_surfaces(client, journal) -> None:
    """The read surfaces a person or a script actually calls.

    Cheap, and worth repeating: these are the endpoints most likely to be
    broken by something else changing, and a 500 in any of them is the one
    outcome this platform has no story for.
    """
    family = "surfaces"
    for path, who in (
            ("/me", creds("soak.audit")),
            ("/models", creds("soak.audit")),
            ("/features", creds("soak.audit")),
            ("/featuresets", creds("soak.audit")),
            ("/warrants", creds("soak.audit")),
            ("/policies", creds("soak.audit")),
            ("/roles", creds("soak.audit")),
            ("/principals", creds("soak.mrm")),
            ("/scheduler", creds("soak.ops")),
            ("/grammar", creds("soak.audit")),
            ("/references?kind=feature&id=soak_dscr_00001", creds("soak.audit")),
            ("/version-approval-quorum", creds("soak.audit")),
            ("/engine", creds("soak.audit")),
            ("/logs?limit=5", creds("soak.ops")),
    ):
        status, _ = client.get(path, auth=who)
        journal.check(family, f"GET {path}", status == 200, 200, status)


def ui_pages(client, journal) -> None:
    """Every screen a signed-in person can reach, still rendering.

    Server-rendered HTML, so a 200 with a body is a real answer. A screen
    nobody can click to is not built — and a screen that 500s after six hours
    of use is worse than one that was never there.
    """
    family = "screens"
    # Authoring screens are driven as the developer; everything else as the
    # risk manager. A screen refusing the wrong persona is the platform
    # working, and asserting a 200 there would be asserting that it does not.
    for path in ("/features/new", "/features/load", "/featuresets/author"):
        status, html = client.page(path, creds("soak.dev"))
        journal.check(family, f"screen {path}",
                      status == 200 and not client.is_sign_in(html),
                      "200, and the page itself", status)
    for path in ("/dashboard", "/features", "/featuresets",
                 "/featuresets/lattice",
                 "/features/point-in-time", "/models/new", "/model-algebra",
                 "/warrants", "/warrants/estate", "/limitations", "/findings",
                 "/dependencies", "/notifications", "/telemetry", "/board-pack",
                 "/admin", "/admin/principals", "/admin/scheduler",
                 "/admin/evidence", "/admin/runtimes", "/admin/logs",
                 "/admin/api-keys", "/admin/regimes",
                 "/policies", "/packages", "/tutorials", "/docs",
                 "/help", "/about", "/health"):
        status, html = client.page(path, creds("soak.mrm"))
        journal.check(family, f"screen {path}",
                      status == 200 and not client.is_sign_in(html),
                      "200, and the page itself",
                      f"{status}{' — the SIGN-IN FORM' if client.is_sign_in(html) else ''}")


def scheduler_batch(client, journal) -> None:
    """Run the governance batch. Idempotent by design, so running it every
    cycle is a test of that claim rather than a cost."""
    family = "batch"
    status, body = client.post("/scheduler/run", {}, auth=creds("soak.ops"))
    journal.check(family, "the batch runs on demand",
                  status == 200, 200, f"{status} {json.dumps(body)[:200]}")
    status, body = client.get("/scheduler", auth=creds("soak.ops"))
    journal.check(family, "and reports its own health",
                  status == 200 and "health" in (body or {}),
                  "200 with health", status)


def api_keys(client, journal, cycle: int) -> None:
    """A key that works, then a key that does not, and the difference stated."""
    family = "apikeys"
    status, body = client.post("/api-keys", {
        "username": "svc/soak-runner", "name": f"soak-{cycle}",
        "lifetime_days": 1}, auth=("admin", "maya-admin-dev"))
    if not journal.check(family, "issue a key", status in (200, 201),
                         "200/201", f"{status} {json.dumps(body)[:200]}"):
        return
    secret = (body or {}).get("secret")
    key_id = (body or {}).get("id")
    if not secret:
        journal.check(family, "the secret is returned once", False,
                      "a secret", sorted((body or {}).keys()))
        return

    status, body = client.get("/me", auth=None,
                              headers={"X-API-Key": secret})
    journal.check(family, "the key authenticates", status == 200, 200, status)

    status, body = client.post(f"/api-keys/{key_id}/revoke",
                               {"reason": "soak"}, auth=("admin", "maya-admin-dev"))
    journal.check(family, "revoke it", status in (200, 204), "200/204", status)

    status, body = client.get("/me", auth=None,
                              headers={"X-API-Key": secret})
    journal.check(family, "a revoked key is refused, and says which",
                  status == 401 and "revoked" in json.dumps(body).lower(),
                  "401 key_revoked", f"{status} {refusal_code(body)}")


