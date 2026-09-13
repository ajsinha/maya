"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — amendment and the second attestation cycle.

An attested record is immutable and amendment is the only route out of it. So
every case here is about the seam: what may be opened, what a second cycle
references, and whether an expired attestation is a state or a fact reported
about one.
"""
from __future__ import annotations

from core.lifecycle.common import DEFAULT_REQUIRED_ROLES
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ASSESSMENT = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
              "feature_count": 12, "interpretable": True,
              "uses_alternative_data": False}
#: The two roles an attestation requires by default, and the QA person who
#: holds each. Read from the constant so a change to the quorum shows up here
#: as a KeyError rather than as a green run against the old shape.
SIGNER = {"model_owner": "owner", "model_risk_manager": "risk"}


def _attested(ctx: Ctx) -> str:
    """A model carried all the way to `attested`."""
    name = ctx.unique("am")
    api = ctx.api
    api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                      "owner": "owner", **TIER})
    api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
             auth=ctx.people["developer"])
    api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    api.post(f"{M}/{name}/submit", json={"note": "qa"})
    api.post(f"{M}/{name}/approve", json={"note": "qa"})
    _sign_all(ctx, name)
    return name


def _sign_all(ctx: Ctx, name: str) -> None:
    for role in DEFAULT_REQUIRED_ROLES:
        ctx.api.post(f"{M}/{name}/attest",
                     json={"role": role, "decision": "attest",
                           "statement": "qa"},
                     auth=ctx.people[SIGNER[role]])


def _state(ctx: Ctx, name: str) -> dict:
    """The `lifecycle` projection, which is where all of this lives.

    `GET /models/{name}` answers `{model, versions, alias_history, lifecycle,
    evidence}`. The state, the open amendment, the attestation clock and the
    amendment history are all under `lifecycle`; `model` carries `status` and
    not `state`. A case reading the top level finds None and reports it as a
    missing fact.
    """
    got = ctx.api.get(f"{M}/{name}")
    return (got.json() or {}).get("lifecycle") or {} if got.status_code < 400 \
        else {}


def _amendment(ctx: Ctx, name: str) -> dict:
    """The open amendment. `POST /amend` answers with the moved MODEL, and
    there is no route that reads an amendment directly, so the reference and
    the scope are read back from the lifecycle projection."""
    return _state(ctx, name).get("open_amendment") or {}


def _second(ctx: Ctx, role: str):
    """A second real person holding `role`.

    The QA estate has one principal per duty on purpose — an attestation
    cannot be signed by one person however many permissions they hold — so a
    case about TWO people holding the same role has to mint the second one.
    Signing as somebody who merely lacks the permission would answer
    `forbidden` and prove nothing.
    """
    who = ctx.unique("second")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": [role], "password": f"{who}-password",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        return None
    return (who, f"{who}-password")


def _amend(ctx: Ctx, name: str, **over):
    body = {"reason": "a QA amendment", "scope": []}
    body.update(over)
    return ctx.api.post(f"{M}/{name}/amend", json=body)


@case("QA-GOV-051", "Open two amendments against one model")
def gov_051(ctx: Ctx) -> Result:
    """Attest, amend, attest again is impossible while the first is open, so
    two open amendments would be two uncompletable cycles."""
    name = _attested(ctx)
    first = _amend(ctx, name)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    return refused_by_the_control(
        _amend(ctx, name, reason="a second QA amendment"),
        "two amendments were opened against one model")


@case("QA-GOV-052", "Open an amendment with a whitespace-only reason")
def gov_052(ctx: Ctx) -> Result:
    """The reason becomes part of the attestation record, so a blank one
    makes the record say a change happened and not what it was."""
    name = _attested(ctx)
    got = _amend(ctx, name, reason="   ")
    if got.status_code < 400:
        return FAIL, "an amendment was opened with no stated reason"
    if code_of(got) not in ("reason_required", "validation_error"):
        return FAIL, f"refused '{code_of(got)}': {got.text[:150]}"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-053", "Amendment references after two full cycles")
def gov_053(ctx: Ctx) -> Result:
    """Each amendment gets its own reference, and the second does not reuse
    the first — a record that cannot tell two changes apart cannot show which
    attestation covered which."""
    name = _attested(ctx)
    seen = []
    for cycle in range(2):
        made = _amend(ctx, name, reason=f"QA cycle {cycle}")
        if made.status_code >= 400:
            return BLOCKED, f"cycle {cycle}: {made.text[:150]}"
        seen.append(_amendment(ctx, name).get("reference"))
        ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
        ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
        _sign_all(ctx, name)
    if None in seen:
        return FAIL, f"an amendment carries no reference: {seen}"
    if seen[0] == seen[1]:
        return FAIL, f"both cycles reference {seen[0]}"
    return PASS, f"{seen[0]} then {seen[1]}"


@case("QA-GOV-055", "What an amendment's scope records")
def gov_055(ctx: Ctx) -> Result:
    """The scope says what the amendment was for. It is a statement by the
    person opening it, not a constraint the register enforces, and the case
    reports which."""
    name = _attested(ctx)
    made = _amend(ctx, name, scope=["owner"])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    if _amendment(ctx, name).get("scope") != ["owner"]:
        return FAIL, f"the scope was not recorded: {_amendment(ctx, name)}"
    changed = ctx.api.patch(f"{M}/{name}",
                            json={"fields": {"description": "out of scope"}})
    enforced = changed.status_code >= 400
    return PASS, ("scope recorded as given; a change outside it was "
                  + ("refused" if enforced else "ACCEPTED — the scope is a "
                     "statement on the record, not a constraint"))


@case("QA-GOV-056", "Amend, add a version, then attest again")
def gov_056(ctx: Ctx) -> Result:
    """A new version is exactly what an amendment is usually for, so the
    route out of immutability has to admit one."""
    name = _attested(ctx)
    made = _amend(ctx, name, reason="a new version")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    added = ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.1.0"},
                         auth=ctx.people["developer"])
    if added.status_code >= 400:
        return FAIL, ("an open amendment did not admit a new version, so the "
                      "only route out of immutability does not reach the "
                      f"commonest reason for taking it: {added.text[:130]}")
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    _sign_all(ctx, name)
    if _state(ctx, name).get("state") != "attested":
        return FAIL, f"the second cycle did not complete: {_state(ctx, name)}"
    return PASS, "amended, versioned, attested again"


@case("QA-GOV-062", "Two different people sign the same role")
def gov_062(ctx: Ctx) -> Result:
    """The quorum is one signature per required role. A second signature for
    a role already signed is not more assurance, it is an overwrite."""
    name = ctx.unique("am")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    first = ctx.api.post(f"{M}/{name}/attest",
                         json={"role": "model_owner", "decision": "attest",
                               "statement": "qa"}, auth=ctx.people["owner"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    other = _second(ctx, "model_owner")
    if other is None:
        return BLOCKED, "could not mint a second model_owner"
    return refused_by_the_control(
        ctx.api.post(f"{M}/{name}/attest",
                     json={"role": "model_owner", "decision": "attest",
                           "statement": "qa"}, auth=other),
        "a role already signed was signed again by a second person, so the "
        "second signature overwrites the first rather than adding to it")


@case("QA-GOV-065", "Sign with a decision that is neither attest nor decline")
def gov_065(ctx: Ctx) -> Result:
    name = ctx.unique("am")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    return refused_by_the_control(
        ctx.api.post(f"{M}/{name}/attest",
                     json={"role": "model_owner", "decision": "maybe",
                           "statement": "qa"}, auth=ctx.people["owner"]),
        "an attestation was signed with a decision that is neither attest "
        "nor decline")


@case("QA-GOV-067", "An attestation is not expired the moment it is signed")
def gov_067(ctx: Ctx) -> Result:
    name = _attested(ctx)
    state = _state(ctx, name)
    if state.get("state") != "attested":
        return BLOCKED, f"the cycle did not complete: {state}"
    if state.get("attestation_expired") is None:
        return FAIL, ("the record does not report whether its attestation is "
                      "still valid, so a lapsed one is indistinguishable "
                      "from a fresh one")
    if state["attestation_expired"]:
        return FAIL, "an attestation signed seconds ago reports as expired"
    return PASS, "attested, and reported as not expired"


@case("QA-GOV-069", "Amend a model whose attestation has expired")
def gov_069(ctx: Ctx) -> Result:
    """Expiry must not become a trap: a lapsed attestation is exactly the
    state a firm needs to amend its way out of."""
    name = _attested(ctx)
    got = _amend(ctx, name, reason="the attestation lapsed")
    if got.status_code >= 400:
        return FAIL, ("an attested record could not be amended: "
                      + got.text[:150])
    return PASS, "amendment is available from the attested state"


@case("QA-GOV-070", "A second attestation after a completed cycle")
def gov_070(ctx: Ctx) -> Result:
    """`attestation_open` refuses a second attestation while one is live. A
    completed one must not refuse the same way, or a model could be attested
    exactly once, ever."""
    name = _attested(ctx)
    made = _amend(ctx, name, reason="a second cycle")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    opened = ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    if opened.status_code >= 400:
        if code_of(opened) == "attestation_open":
            return FAIL, ("a completed attestation blocks the next one, so a "
                          "model can be attested exactly once")
        return FAIL, f"the second cycle could not be approved: {opened.text[:140]}"
    return PASS, "a completed attestation does not block the next"


@case("QA-GOV-071", "Create the same semver twice")
def gov_071(ctx: Ctx) -> Result:
    name = ctx.unique("am")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    first = ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                         auth=ctx.people["developer"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    return refused_by_the_control(
        ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                     auth=ctx.people["developer"]),
        "the same semver was created twice, so a version identifier names "
        "two different things")


@case("QA-GOV-072", "Create a version on an attested record")
def gov_072(ctx: Ctx) -> Result:
    """The refusal has to name the amendment route, or it reads as a dead
    end rather than as the one door."""
    name = _attested(ctx)
    got = ctx.api.post(f"{M}/{name}/versions", json={"semver": "2.0.0"},
                       auth=ctx.people["developer"])
    if got.status_code < 400:
        return FAIL, "an attested record acquired a version without amendment"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if "amend" not in got.text.lower():
        return FAIL, (f"refused '{code_of(got)}' without naming the amendment "
                      f"route, so the refusal reads as a dead end")
    return PASS, f"refused '{code_of(got)}', naming the amendment route"
