"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — independence, which is the control this whole module exists for.

The failure mode is never a validator boldly declaring they built the model.
It is one human under two spellings — `person/d.hall` and `d.hall`, or the
same name in different case — slipping past a check written with `==`. Each
case here is one spelling of that.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

V = "/api/v1/validations"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _built(ctx: Ctx) -> tuple:
    """A version created by `developer`, which is the name to disguise."""
    name = ctx.unique("iv")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return f"maya://model/{name}", "1.0.0"


def _open(ctx: Ctx, urn: str, semver: str, validators, **over):
    body = {"urn": urn, "semver": semver, "validators": list(validators),
            "kind": "initial"}
    body.update(over)
    return ctx.api.post(V, json=body, auth=ctx.people["risk"])


@case("QA-AM-001", "The builder's name spelled with a person/ prefix")
def am_001(ctx: Ctx) -> Result:
    """Production writes `created_by` as the bare authenticated username and
    validators are conventionally written `person/...`. A check using `==`
    never matches the two spellings of one human, and the control is inert
    over HTTP while every unit test passes."""
    urn, semver = _built(ctx)
    return refused_by_the_control(
        _open(ctx, urn, semver, ["person/developer"]),
        "the person who built the version validated it, under a `person/` "
        "prefix the builder's own name does not carry")


@case("QA-AM-002", "The builder's name with the case flipped")
def am_002(ctx: Ctx) -> Result:
    urn, semver = _built(ctx)
    return refused_by_the_control(
        _open(ctx, urn, semver, ["PERSON/DEVELOPER"]),
        "the builder validated their own version under a different case")


@case("QA-AM-003", "Two validators, one of whom built the version")
def am_003(ctx: Ctx) -> Result:
    """A second, genuinely independent validator does not launder the first.
    The episode must be refused whole rather than opened with a note."""
    urn, semver = _built(ctx)
    got = _open(ctx, urn, semver, ["person/validator", "person/developer"])
    if got.status_code < 400:
        return FAIL, ("an episode opened with the builder among its "
                      "validators; a second independent name laundered the "
                      "first")
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    listed = ctx.api.get(f"{V}?urn={urn}", auth=ctx.people["risk"])
    if listed.status_code < 400 and semver in listed.text and \
            "in_progress" in listed.text:
        return FAIL, "the refused episode was recorded anyway"
    return PASS, f"refused '{code_of(got)}', and no episode was recorded"


@case("QA-AM-004", "A validator who resolves to nobody")
def am_004(ctx: Ctx) -> Result:
    """An independence test on a name that resolves to nobody passes by
    construction: the string is compared against the builder's username and
    of course differs. A validation names who challenged the model, and a
    name nobody can look up is not that record."""
    urn, semver = _built(ctx)
    return refused_by_the_control(
        _open(ctx, urn, semver, ["person/nobody.at.all"]),
        "an episode was opened naming a validator who does not exist, so "
        "independence passed by construction")


@case("QA-AM-005", "A validator who exists but is not active")
def am_005(ctx: Ctx) -> Result:
    who = ctx.unique("gone")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["validator"],
                              "password": f"{who}-password",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    suspended = ctx.api.post(f"/api/v1/principals/{who}/suspend",
                             json={"reason": "left the firm"})
    if suspended.status_code >= 400:
        return BLOCKED, f"could not suspend: {suspended.text[:140]}"
    urn, semver = _built(ctx)
    return refused_by_the_control(
        _open(ctx, urn, semver, [f"person/{who}"]),
        "a suspended principal was recorded as having challenged this version")


@case("QA-AM-007", "A version with no recorded builder")
def am_007(ctx: Ctx) -> Result:
    """`same_person` is false when either side is empty, so a version whose
    `created_by` were blank would pass independence against ANY validator and
    record `independent: true`. An unknown builder is not a known-different
    builder.

    The case is whether that state is reachable. It is not: `created_by` is
    immutable in the database, so the hole cannot be opened after the fact,
    and no route creates a version without an actor. Both halves are checked
    — the trigger, and the estate — because either alone would leave the
    other as an assumption.
    """
    name = ctx.unique("iv")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    registry = ctx.ui.app.state.ctx.get("registry")
    if registry is None:
        return BLOCKED, "no registry reachable from this run"
    urn = f"maya://model/{name}"
    version = registry.version(urn, "1.0.0")
    if not (version.get("created_by") or "").strip():
        return FAIL, "a version was created with no builder recorded"
    try:
        registry.version_service.versions.set({"created_by": ""},
                                              id=version["id"])
    except Exception as exc:
        if "immutable" not in str(exc):
            return FAIL, f"blanking the builder failed for another reason: {exc}"
        blank = [v for v in registry.version_service.versions.many()
                 if not (v.get("created_by") or "").strip()]
        if blank:
            return FAIL, (f"{len(blank)} version(s) carry no builder despite "
                          f"the column being immutable")
        return PASS, ("the builder cannot be blanked — the column is "
                      "immutable in the database — and no version in the "
                      "estate carries an empty one, so independence is never "
                      "evaluated against nothing")
    return FAIL, ("the builder's name was erased after the fact, which turns "
                  "independence into a check against an empty string that "
                  "any validator passes")


@case("QA-AM-025", "Open an episode with no validators")
def am_025(ctx: Ctx) -> Result:
    urn, semver = _built(ctx)
    return refused_by_the_control(
        _open(ctx, urn, semver, []),
        "a validation was opened with nobody recorded as challenging it")


@case("QA-AM-026", "Open with the same validator listed twice")
def am_026(ctx: Ctx) -> Result:
    """One person named twice is one validator. If the count is used
    anywhere — capacity, a quorum, a report of how many challenged this — a
    duplicate inflates it."""
    urn, semver = _built(ctx)
    got = _open(ctx, urn, semver, ["person/validator", "person/validator"])
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    stored = (got.json() or {}).get("validators") or []
    if len(stored) == len(set(v.lower() for v in stored)):
        return PASS, f"stored once: {stored}"
    # Not a finding on the strength of the duplicate alone — the capacity
    # view walks `episode["validators"]` and appends the episode once per
    # entry, so the same episode is counted twice against one person's load.
    load = ctx.api.get("/api/v1/validation-capacity", auth=ctx.people["risk"])
    inflated = ""
    if load.status_code < 400:
        for row in (load.json() or {}).get("validators") or []:
            if "validator" in str(row.get("validator", "")) and \
                    (row.get("open_episodes") or row.get("carrying") or 0) > 1:
                inflated = (f" and the capacity view has them carrying "
                            f"{row.get('open_episodes') or row.get('carrying')}"
                            f" episodes")
    return FAIL, (f"one validator is recorded twice: {stored}{inflated}. The "
                  f"capacity view appends the episode once per entry, so a "
                  f"duplicate inflates that person's open load")


@case("QA-AM-1600", "A validation kind that is not one")
def am_1600(ctx: Ctx) -> Result:
    urn, semver = _built(ctx)
    return refused_by_the_control(
        _open(ctx, urn, semver, ["person/validator"], kind="a look over"),
        "an episode was opened of a kind the catalogue does not have")


@case("QA-AM-1601", "Open against a version that does not exist")
def am_1601(ctx: Ctx) -> Result:
    urn, _ = _built(ctx)
    return refused_by_the_control(
        _open(ctx, urn, "9.9.9", ["person/validator"]),
        "a validation was opened against a version nobody created")


@case("QA-AM-1602", "The independence verdict names who built it")
def am_1602(ctx: Ctx) -> Result:
    """A record saying only `independent: true` is one nobody can re-check.
    The builder's name has to be in it."""
    urn, semver = _built(ctx)
    got = _open(ctx, urn, semver, ["person/validator"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    independence = (got.json() or {}).get("independence") or {}
    if not independence.get("version_created_by"):
        return FAIL, ("the episode records independence without recording "
                      "who built the version, so nobody can re-check it")
    if not (independence.get("reason") or "").strip():
        return FAIL, "the independence verdict carries no reason"
    return PASS, (f"independent of '{independence['version_created_by']}': "
                  f"{independence['reason'][:60]}")


@case("QA-AM-023", "Conclude an already concluded episode")
def am_023(ctx: Ctx) -> Result:
    urn, semver = _built(ctx)
    made = _open(ctx, urn, semver, ["person/validator"])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    vid = made.json()["id"]
    body = {"outcome": "rejected", "tier_verdict": "remains_appropriate",
            "tier_note": "qa", "conditions": []}
    first = ctx.api.post(f"{V}/{vid}/conclude", json=body,
                         auth=ctx.people["validator"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    return refused_by_the_control(
        ctx.api.post(f"{V}/{vid}/conclude",
                     json={**body, "outcome": "approved"},
                     auth=ctx.people["validator"]),
        "a concluded episode was concluded again with a different outcome")


@case("QA-AM-022", "Record a result after the episode concluded")
def am_022(ctx: Ctx) -> Result:
    """Its results are immutable once it is complete, or the conclusion rests
    on evidence that arrived after it."""
    urn, semver = _built(ctx)
    made = _open(ctx, urn, semver, ["person/validator"])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    vid = made.json()["id"]
    done = ctx.api.post(f"{V}/{vid}/conclude",
                        json={"outcome": "rejected",
                              "tier_verdict": "remains_appropriate",
                              "tier_note": "qa", "conditions": []},
                        auth=ctx.people["validator"])
    if done.status_code >= 400:
        return BLOCKED, done.text[:170]
    return refused_by_the_control(
        ctx.api.post(f"{V}/{vid}/results",
                     json={"test_key": "stability.psi",
                           "left": [1.0, 2.0, 3.0], "right": [1.0, 2.0, 3.0]},
                     auth=ctx.people["validator"]),
        "a test result was added to a concluded episode, so the conclusion "
        "rests on evidence that arrived after it")
