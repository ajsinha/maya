"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — versions and the alias that points at one.

An alias is what an engine resolves, so moving one is the act that changes
what actually runs. Two rules carry it: an alias may only point at an APPROVED
version, and the person who created a version may not be the person who
promotes it into an environment.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
#: A low-tier assessment. `internal_report` is NOT a purpose class — the
#: vocabulary is closed and `commercial` is the low-materiality member — and
#: an assessment refused `unknown_purpose_class` leaves the model untiered,
#: after which every version approval refuses `no_tier`.
ASSESSMENT = {"exposure": 1_000.0, "purpose_class": "commercial",
              "feature_count": 3, "interpretable": True,
              "uses_alternative_data": False}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("va")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return name


def _version(ctx: Ctx, name: str, semver: str = "1.0.0", **over):
    body = {"semver": semver}
    body.update(over)
    return ctx.api.post(f"{M}/{name}/versions", json=body,
                        auth=ctx.people["developer"])


def _approve(ctx: Ctx, name: str, semver: str = "1.0.0", who="risk"):
    return ctx.api.post(f"{M}/{name}/versions/{semver}/approve", json={},
                        auth=ctx.people[who])


def _move(ctx: Ctx, name: str, semver: str = "1.0.0", who="risk", **over):
    body = {"alias": "champion", "environment": "prod", "semver": semver,
            "justification": "qa"}
    body.update(over)
    return ctx.api.put(f"{M}/{name}/aliases", json=body, auth=ctx.people[who])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-GOV-074", "A version with a malformed artifact digest")
def gov_074(ctx: Ctx) -> Result:
    """A digest is an address. One that cannot resolve is a version pointing
    at nothing, discovered at execution rather than at registration."""
    name = _model(ctx)
    bad = []
    for digest in ("not-a-digest", "sha256:xyz", "a" * 63, "sha256:" + "a" * 63,
                   "sha256:" + "z" * 64):
        got = _version(ctx, name, semver=f"1.0.{len(bad)}",
                       artifact_digest=digest)
        if got.status_code >= 500:
            return FAIL, f"{digest[:20]}: {got.status_code}"
        if got.status_code < 400:
            bad.append(digest[:24])
    if bad:
        return FAIL, f"these digests were accepted as addresses: {bad}"
    return PASS, "five malformed digests refused"


@case("QA-GOV-076", "A version with no digest at all")
def gov_076(ctx: Ctx) -> Result:
    """Not every model has an artifact — a rule set or a calibration has
    none. Requiring one would make the register unable to hold them."""
    got = _version(ctx, _model(ctx))
    if got.status_code >= 400:
        return FAIL, (f"a version with no artifact was refused "
                      f"'{code_of(got)}'; a rule set has no artifact and "
                      f"could never be registered")
    return PASS, "a version may have no artifact"


@case("QA-GOV-079", "Semver ordering across a ten boundary")
def gov_079(ctx: Ctx) -> Result:
    """String ordering puts `0.9.0` after `0.10.0`. A register that picks the
    latest version by sorting text promotes the wrong one."""
    name = _model(ctx)
    for semver in ("0.9.0", "0.10.0"):
        if _version(ctx, name, semver=semver).status_code >= 400:
            return BLOCKED, f"could not create {semver}"
    got = ctx.api.get(f"{M}/{name}")
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    versions = (got.json() or {}).get("versions") or []
    if not versions:
        return BLOCKED, "no versions came back"
    from core.registry.versions import latest_version
    latest = latest_version(versions)
    if (latest or {}).get("semver") != "0.10.0":
        return FAIL, (f"the latest version is reported as "
                      f"{(latest or {}).get('semver')}, not 0.10.0; versions "
                      f"are being ordered as text")
    return PASS, "0.10.0 is later than 0.9.0"


@case("QA-GOV-080", "A semver that is not three numeric parts")
def gov_080(ctx: Ctx) -> Result:
    name = _model(ctx)
    accepted = []
    for semver in ("1.0", "v1.0.0", "1.0.0.0", "one.two.three", "", "1.0.x"):
        got = _version(ctx, name, semver=semver)
        if got.status_code >= 500:
            return FAIL, f"{semver!r}: {got.status_code}"
        if got.status_code < 400:
            accepted.append(semver)
    if accepted:
        return FAIL, f"these are not semvers and were accepted: {accepted}"
    return PASS, "six malformed semvers refused"


@case("QA-GOV-085", "The version's creator approves it")
def gov_085(ctx: Ctx) -> Result:
    """A version is approved by somebody who did not write it, or the
    approval is the author's own opinion recorded twice."""
    name = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    got = _approve(ctx, name, who="developer")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "the person who created a version approved it"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-GOV-087", "Move an alias to a version that is not approved")
def gov_087(ctx: Ctx) -> Result:
    """An alias is what an engine resolves. Pointing one at an unapproved
    version puts it into production without the approval."""
    name = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    got = _move(ctx, name)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("an alias points at a version nobody approved, so it "
                      "is in production without the approval")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-094", "The version's creator moves the alias")
def gov_094(ctx: Ctx) -> Result:
    """Creating and promoting are the two halves of putting a model into
    production, and one person doing both is one person."""
    name = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    if _approve(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be approved"
    got = _move(ctx, name, who="developer")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the person who created a version promoted it into "
                      "production themselves")
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-GOV-3400", "Somebody else may move the alias")
def gov_3400(ctx: Ctx) -> Result:
    """The refusal has to admit the legitimate case, or nothing reaches
    production at all."""
    name = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    if _approve(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be approved"
    got = _move(ctx, name)
    if got.status_code >= 400:
        return FAIL, (f"a second person could not move the alias: "
                      f"{got.text[:130]}")
    return PASS, "approved by one person, promoted by another"


@case("QA-GOV-090", "Move an alias to the version it already points at")
def gov_090(ctx: Ctx) -> Result:
    """A no-op move is still a decision somebody took, and the history is
    what an examiner reads to see when production changed."""
    name = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    if _approve(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be approved"
    if _move(ctx, name).status_code >= 400:
        return BLOCKED, "the first move failed"
    before = len(((ctx.api.get(f"{M}/{name}").json() or {})
                  .get("alias_history") or []))
    again = _move(ctx, name)
    if again.status_code >= 400:
        return PASS, f"a repeat move is refused '{code_of(again)}'"
    after = len(((ctx.api.get(f"{M}/{name}").json() or {})
                 .get("alias_history") or []))
    if after <= before:
        return FAIL, ("a repeat move was accepted and recorded nothing, so "
                      "the history does not show the decision was taken")
    return PASS, f"accepted, and the history grew from {before} to {after}"


@case("QA-GOV-091", "Roll an alias back to the previous version")
def gov_091(ctx: Ctx) -> Result:
    """Rolling back is what a firm does at three in the morning. Whether it
    is permitted or refused, the answer must not depend on which direction
    the version number moved by accident."""
    name = _model(ctx)
    for semver in ("1.0.0", "2.0.0"):
        if _version(ctx, name, semver=semver).status_code >= 400:
            return BLOCKED, f"could not create {semver}"
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    for semver in ("1.0.0", "2.0.0"):
        if _approve(ctx, name, semver).status_code >= 400:
            return BLOCKED, f"could not approve {semver}"
    if _move(ctx, name, "2.0.0").status_code >= 400:
        return BLOCKED, "the forward move failed"
    got = _move(ctx, name, "1.0.0")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, (f"a rollback is refused '{code_of(got)}' — an "
                      f"amendment is the route back")
    history = ((ctx.api.get(f"{M}/{name}").json() or {})
               .get("alias_history") or [])
    return PASS, (f"a rollback is permitted and recorded; {len(history)} "
                  f"history entries")


@case("QA-GOV-096", "Move an alias in an environment nobody configured")
def gov_096(ctx: Ctx) -> Result:
    """An environment is where a warrant is resolved. One nobody configured
    is an alias nothing will ever read — reported rather than asserted,
    because a firm adding an environment should not need a code change."""
    name = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    if _approve(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be approved"
    got = _move(ctx, name, environment="qa-nowhere")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' for an unknown environment"
    return PASS, ("accepted: environments are not a closed list, so a firm "
                  "may add one without a code change")


@case("QA-GOV-098", "Move an alias as a principal scoped to another entity")
def gov_098(ctx: Ctx) -> Result:
    """Scope decides what a person can see AND what they can change."""
    name = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    if _approve(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be approved"
    who = ctx.unique("scoped")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_risk_manager"],
                              "password": f"{who}-pw",
                              "legal_entities": ["LE-XX-99"], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.put(f"{M}/{name}/aliases",
                      json={"alias": "champion", "environment": "prod",
                            "semver": "1.0.0", "justification": "qa"},
                      auth=(who, f"{who}-pw"))
    if got.status_code < 400:
        return FAIL, ("a principal scoped to another legal entity moved this "
                      "model's alias")
    return PASS, f"refused '{code_of(got) or got.status_code}'"
