"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the edges of the lifecycle machine.

Not the happy path, which the earlier governance cases walk, but the moves the
machine does not name: retiring mid-amendment, approving twice, signing into a
closed attestation, and the one edge the register takes and does not publish.
"""
from __future__ import annotations

from core.lifecycle.common import DEFAULT_REQUIRED_ROLES
from core.lifecycle.states import AMENDING, DRAFT, describe
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ASSESSMENT = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
              "feature_count": 12, "interpretable": True,
              "uses_alternative_data": False}
SIGNER = {"model_owner": "owner", "model_risk_manager": "risk"}


def _approved(ctx: Ctx) -> str:
    name = ctx.unique("le")
    api = ctx.api
    api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                      "owner": "owner", **TIER})
    api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
             auth=ctx.people["developer"])
    api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    api.post(f"{M}/{name}/submit", json={"note": "qa"})
    api.post(f"{M}/{name}/approve", json={"note": "qa"})
    return name


def _sign(ctx: Ctx, name: str, role: str, decision: str = "attest"):
    return ctx.api.post(f"{M}/{name}/attest",
                        json={"role": role, "decision": decision,
                              "statement": "qa"},
                        auth=ctx.people[SIGNER[role]])


def _attested(ctx: Ctx) -> str:
    name = _approved(ctx)
    for role in DEFAULT_REQUIRED_ROLES:
        _sign(ctx, name, role)
    return name


def _life(ctx: Ctx, name: str) -> dict:
    got = ctx.api.get(f"{M}/{name}")
    return (got.json() or {}).get("lifecycle") or {} if got.status_code < 400 \
        else {}


@case("QA-GOV-035", "Retire an amending record")
def gov_035(ctx: Ctx) -> Result:
    """Retiring mid-amendment would strand an open amendment against a
    record nobody will ever attest again."""
    name = _attested(ctx)
    opened = ctx.api.post(f"{M}/{name}/amend", json={"reason": "qa", "scope": []})
    if opened.status_code >= 400:
        return BLOCKED, opened.text[:170]
    return refused_by_the_control(
        ctx.api.post(f"{M}/{name}/retire", json={"reason": "qa"}),
        "a record was retired with an amendment still open, stranding it")


@case("QA-GOV-039", "Approve twice")
def gov_039(ctx: Ctx) -> Result:
    """A second approval must not open a second attestation — two open
    quorums against one record is two records."""
    name = _approved(ctx)
    again = ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    if again.status_code < 400:
        return FAIL, "a record was approved twice"
    if code_of(again) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    life = _life(ctx, name)
    if not life.get("open_attestation"):
        return FAIL, "the first approval left no attestation open"
    return PASS, f"refused '{code_of(again)}', exactly one attestation open"


@case("QA-GOV-041", "Sign an attestation before approval")
def gov_041(ctx: Ctx) -> Result:
    name = ctx.unique("le")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    return refused_by_the_control(
        _sign(ctx, name, "model_owner"),
        "a record was signed before anybody approved it")


@case("QA-GOV-042", "The last signature lands after the record was retired")
def gov_042(ctx: Ctx) -> Result:
    """A quorum half collected, then the model is withdrawn. The remaining
    signature has nowhere legal to move the record to, and the question is
    whether it is refused or recorded against a retired model."""
    name = _approved(ctx)
    first = _sign(ctx, name, DEFAULT_REQUIRED_ROLES[0])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    gone = ctx.api.post(f"{M}/{name}/retire", json={"reason": "withdrawn"})
    if gone.status_code >= 400:
        return BLOCKED, f"could not retire mid-quorum: {gone.text[:140]}"
    last = _sign(ctx, name, DEFAULT_REQUIRED_ROLES[1])
    life = _life(ctx, name)
    state = life.get("state")
    if last.status_code >= 400:
        return PASS, (f"the last signature was refused '{code_of(last)}'; "
                      f"the record stands at {state}")
    if state == "retired" and not life.get("open_attestation"):
        return FAIL, (
            "the quorum completed against a RETIRED record: the attestation "
            "closed and the record is retired, so the register holds a "
            "completed attestation for a model nobody may use, and no state "
            "says which of the two facts governs")
    return PASS, f"signature accepted and the record reads {state}"


@case("QA-GOV-043", "Decline an initial attestation")
def gov_043(ctx: Ctx) -> Result:
    """A decline must return the record to work, not to limbo."""
    name = _approved(ctx)
    got = _sign(ctx, name, "model_owner", decision="decline")
    if got.status_code >= 400:
        return FAIL, f"a decline was refused: {got.text[:150]}"
    life = _life(ctx, name)
    if life.get("state") != DRAFT:
        return FAIL, (f"a declined initial attestation left the record at "
                      f"'{life.get('state')}', not '{DRAFT}'")
    if life.get("open_attestation"):
        return FAIL, "the declined attestation is still open"
    return PASS, f"declined, and the record is back at {DRAFT}"


@case("QA-GOV-044", "Decline an amendment attestation")
def gov_044(ctx: Ctx) -> Result:
    """The decline target depends on which cycle it was: an amendment
    decline goes back to `amending`, not to `draft`, or the amendment is
    lost."""
    name = _attested(ctx)
    ctx.api.post(f"{M}/{name}/amend", json={"reason": "qa", "scope": []})
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    got = _sign(ctx, name, "model_owner", decision="decline")
    if got.status_code >= 400:
        return FAIL, f"a decline was refused: {got.text[:150]}"
    life = _life(ctx, name)
    if life.get("state") != AMENDING:
        return FAIL, (f"an amendment decline left the record at "
                      f"'{life.get('state')}', not '{AMENDING}'")
    if not life.get("open_amendment"):
        return FAIL, "the amendment was lost by declining its attestation"
    return PASS, f"back at {AMENDING}, amendment still open"


@case("QA-GOV-045", "The decline edge against the published machine")
def gov_045(ctx: Ctx) -> Result:
    """`GET /lifecycle` publishes the machine for an examiner. A move the
    register makes and the machine does not name is a move nobody reading
    the published version can see coming.
    """
    got = ctx.api.get("/api/v1/lifecycle")
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    published = got.json()
    edges = published.get("transitions") or published.get("states") or []
    if not edges:
        edges = describe()
    pairs = {(src, e.get("to")) for e in edges for src in (e.get("from") or [])}
    missing = [p for p in (("approved", DRAFT), ("approved", AMENDING))
               if p not in pairs]
    if missing:
        return FAIL, (
            "a declined attestation moves the record " +
            " and ".join(f"{a} -> {b}" for a, b in missing) +
            ", and the published machine names no such edge. An examiner "
            "reading GET /lifecycle cannot see that declining sends the "
            "record back, or where to")
    return PASS, "the decline edges are in the published machine"


@case("QA-GOV-046", "Sign again after a decline closed the attestation")
def gov_046(ctx: Ctx) -> Result:
    """A closed attestation must not accept a late signature; the quorum it
    recorded is the one that was in force."""
    name = _approved(ctx)
    declined = _sign(ctx, name, "model_owner", decision="decline")
    if declined.status_code >= 400:
        return BLOCKED, declined.text[:170]
    return refused_by_the_control(
        _sign(ctx, name, "model_risk_manager"),
        "a signature landed on an attestation a decline had already closed")


@case("QA-GOV-047", "Walk the whole path twice on one model")
def gov_047(ctx: Ctx) -> Result:
    name = _attested(ctx)
    if _life(ctx, name).get("state") != "attested":
        return BLOCKED, "the first cycle did not complete"
    ctx.api.post(f"{M}/{name}/amend", json={"reason": "second pass", "scope": []})
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    for role in DEFAULT_REQUIRED_ROLES:
        _sign(ctx, name, role)
    life = _life(ctx, name)
    if life.get("state") != "attested":
        return FAIL, f"the second cycle ended at '{life.get('state')}'"
    if len(life.get("amendment_history") or []) != 1:
        return FAIL, ("the amendment history does not hold exactly the one "
                      f"cycle that happened: {life.get('amendment_history')}")
    return PASS, "two full cycles, one amendment on the record"


@case("QA-GOV-048", "Walk the path as one account throughout")
def gov_048(ctx: Ctx) -> Result:
    """Segregation of duties is enforced when the ROLES are granted, not when
    the buttons are pressed — so the refusal should arrive at grant time."""
    who = ctx.unique("both")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_owner", "model_risk_manager"],
                              "password": f"{who}-password",
                              "legal_entities": [], "domains": []})
    if made.status_code < 400:
        return FAIL, ("one account was granted both halves of the quorum, so "
                      "one person can attest a model alone")
    if code_of(made) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused at grant time: '{code_of(made)}'"


@case("QA-GOV-050", "Submit from amending")
def gov_050(ctx: Ctx) -> Result:
    """`submit` names `amending` as a source; the amendment path must not
    require a detour through `draft`."""
    name = _attested(ctx)
    opened = ctx.api.post(f"{M}/{name}/amend", json={"reason": "qa", "scope": []})
    if opened.status_code >= 400:
        return BLOCKED, opened.text[:170]
    got = ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    if got.status_code >= 400:
        return FAIL, ("an amended record could not be submitted, so the "
                      f"amendment path is a dead end: {got.text[:140]}")
    return PASS, f"submitted from amending, now {_life(ctx, name).get('state')}"
