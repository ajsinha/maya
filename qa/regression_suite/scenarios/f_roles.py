"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — roles, and the duties a role set can quietly combine.

Roles were a Python dictionary, which is fine for the eight this platform
ships and wrong for everything a bank has. Making them definable opened two
doors the shipped set could not: a custom role holding both halves of a
separated duty, and — the one that is easy to miss — a HARMLESS role that is
granted to somebody and then amended to hold both halves, which is two steps
each individually allowed.

Removal has the same shape. A role nobody holds can still be one a quorum
REQUIRES, and the holders check passes precisely because nobody holds it.
"""
from __future__ import annotations

from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

P = "/api/v1/principals"
R = "/api/v1/roles"


def _principal(ctx: Ctx, roles, **over):
    who = over.pop("username", None) or ctx.unique("rl")
    body = {"username": who, "display_name": who, "roles": list(roles),
            "password": f"{who}-password", "legal_entities": [],
            "domains": []}
    body.update(over)
    return who, ctx.api.post(P, json=body, auth=ADMIN)


def _role(ctx: Ctx, permissions, **over):
    name = over.pop("name", None) or ctx.unique("role")
    body = {"name": name, "description": "a QA role",
            "permissions": list(permissions)}
    body.update(over)
    return name, ctx.api.post(R, json=body, auth=ADMIN)


@case("QA-GOV-216",
      "Grant `model_owner` and `model_risk_manager` to one principal")
def gov_216(ctx: Ctx) -> Result:
    """The first line owning a model and the second line challenging it are
    the two halves the whole three-lines arrangement is made of."""
    _who, got = _principal(ctx, ["model_owner", "model_risk_manager"])
    outcome = refused_by_the_control(
        got, "one principal holds the first and second lines")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "incompatible_roles":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'incompatible_roles'"


@case("QA-GOV-217", "Grant the same pair with `allow_conflicts: true`")
def gov_217(ctx: Ctx) -> Result:
    """The escape hatch the refusal itself recommends. It has to work — a
    bank with six people has to be able to make the exception — and it has to
    be ENUMERABLE afterwards, because an exception nobody can list is not an
    exception, it is a gap."""
    who, got = _principal(ctx, ["model_owner", "model_risk_manager"],
                          allow_conflicts=True)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — the documented override "
                      f"does not work, so a small firm cannot use the "
                      f"platform at all")
    # Enumerable means findable without knowing who to look for, so every
    # route that lists principals is asked, not only the one for this one.
    looked = {}
    for where in (f"{P}/{who}", P, "/api/v1/recertification",
                  "/api/v1/roles?detailed=true"):
        got = ctx.api.get(where, auth=ADMIN)
        looked[where] = got.text if got.status_code < 400 else ""
    naming = [where for where, text in looked.items()
              if who in text and "conflict" in text.lower()]
    if naming:
        return PASS, f"accepted, and the exception is enumerable at {naming[0]}"
    return FAIL, ("the override was accepted and no route that lists "
                  "principals says an exception was made: `conflicts_allowed` "
                  "goes onto the evidence chain payload and onto no column, "
                  "so listing who holds separated duties in one pair of hands "
                  "means walking the chain — which is the thing the comment "
                  "beside it says an exception must not require")


@case("QA-GOV-218", "Grant `model_developer` and `validator`")
def gov_218(ctx: Ctx) -> Result:
    """Building a version and concluding its validation. The same pair
    QA-GOV-106 established cannot be reached any other way."""
    _who, got = _principal(ctx, ["model_developer", "validator"])
    outcome = refused_by_the_control(
        got, "one principal builds a version and validates it")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "incompatible_roles":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'incompatible_roles'"


@case("QA-GOV-219",
      "Grant a conflicting pair to a principal who also holds `admin`")
def gov_219(ctx: Ctx) -> Result:
    """A third role in the set must not dilute the pair. The conflict is
    between two of the roles held, not a property of the whole set."""
    _who, got = _principal(ctx, ["model_owner", "model_risk_manager",
                                 "auditor"])
    if got.status_code < 400:
        return FAIL, ("adding a third role to an incompatible pair made it "
                      "acceptable: the check is over the SET rather than over "
                      "the pairs in it, so any conflict can be diluted by "
                      "granting one more role")
    if code_of(got) != "incompatible_roles":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'incompatible_roles' with a third role in the set"


@case("QA-GOV-220",
      "Define a custom role holding `version:create` and `version:approve`")
def gov_220(ctx: Ctx) -> Result:
    """The reason the permission list exists beside the role pairs. A role
    somebody defines can hold both halves of a separated duty, and a check
    over role NAMES sees one unfamiliar name and passes it."""
    _name, got = _role(ctx, ["version:create", "version:approve"])
    outcome = refused_by_the_control(
        got, "a custom role holds both halves of a separated duty")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "incompatible_permissions":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'incompatible_permissions'"


@case("QA-GOV-221",
      "Amend a role so an existing holder gains both halves")
def gov_221(ctx: Ctx) -> Result:
    """The recorded defect. Every conflict check ran at the moment a role was
    GIVEN, and a role's permissions are mutable afterwards — so the check was
    avoidable in two steps each individually allowed. The direct path returns
    409; this one returned 200 and every holder silently acquired the pair."""
    name, made = _role(ctx, ["version:create"])
    if made.status_code >= 400:
        return BLOCKED, f"the harmless role could not be defined: {made.text[:140]}"
    _who, held = _principal(ctx, [name])
    if held.status_code >= 400:
        return BLOCKED, f"the role could not be granted: {held.text[:140]}"
    got = ctx.api.put(f"{R}/{name}",
                      json={"permissions": ["version:create",
                                            "version:approve"]},
                      auth=ADMIN)
    outcome = refused_by_the_control(
        got, "a role held by somebody was amended to hold both halves")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "incompatible_permissions":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'incompatible_permissions' on the amendment"


@case("QA-GOV-223", "Delete a role somebody holds")
def gov_223(ctx: Ctx) -> Result:
    """The reference rule, one layer up: a role that stops existing while
    somebody holds it makes their next request resolve against a name that is
    not there."""
    name, made = _role(ctx, ["model:read"])
    if made.status_code >= 400:
        return BLOCKED, f"the role could not be defined: {made.text[:140]}"
    _who, held = _principal(ctx, [name])
    if held.status_code >= 400:
        return BLOCKED, f"the role could not be granted: {held.text[:140]}"
    got = ctx.api.delete(f"{R}/{name}", auth=ADMIN)
    outcome = refused_by_the_control(got, "a role somebody holds was deleted")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "role_in_use":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'role_in_use'"


@case("QA-GOV-225", "Delete a role named in a published authority band",
      isolated=True)
def gov_225(ctx: Ctx) -> Result:
    """EXPECTED TO FAIL. `_awaited_by_a_quorum` reads the open attestation
    and version_approval tables, and a band is neither — it is the matrix
    that DECIDES what a future approval will require. Deleting a role a band
    names leaves a row that can never be satisfied, and the check that would
    catch it only looks at quorums already open."""
    name, made = _role(ctx, ["version:sign"])
    if made.status_code >= 400:
        return BLOCKED, f"the role could not be defined: {made.text[:140]}"
    band = ctx.api.post("/api/v1/authority/bands",
                        json={"name": ctx.unique("bd"),
                              "stages": [["model_risk_manager"], [name]],
                              "tier": 2, "at_or_above": 0.0, "note": "QA"},
                        auth=ctx.people["risk"])
    if band.status_code >= 400:
        return BLOCKED, f"the band could not be published: {band.text[:140]}"
    got = ctx.api.delete(f"{R}/{name}", auth=ADMIN)
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — the matrix is checked as "
                      f"well as the open quorums")
    return FAIL, (f"the role '{name}' was deleted while a published band "
                  f"names it as a required signature: `_awaited_by_a_quorum` "
                  f"reads the open attestation and version_approval tables "
                  f"only, so the matrix row survives naming a role that no "
                  f"longer exists — and it is unsatisfiable from the next "
                  f"approval onwards, not from one already open")


@case("QA-GOV-227", "Delete a built-in role")
def gov_227(ctx: Ctx) -> Result:
    """Every document, tutorial and test refers to the shipped roles by
    name; removing one would make all of them wrong without touching any."""
    got = ctx.api.delete(f"{R}/validator", auth=ADMIN)
    outcome = refused_by_the_control(got, "a shipped role was deleted")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "built_in_role":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'built_in_role'"


@case("QA-GOV-228", "Define a role granting no permissions")
def gov_228(ctx: Ctx) -> Result:
    """Somebody holding it could sign in and do nothing, which reads as a
    fault rather than as the empty grant it is."""
    _name, got = _role(ctx, [])
    outcome = refused_by_the_control(got, "a role that grants nothing")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "role_grants_nothing":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'role_grants_nothing'"


@case("QA-GOV-229", "Define a role with a misspelled permission")
def gov_229(ctx: Ctx) -> Result:
    """A role granting something nothing checks reads as authority and is
    not — and a typo is the ordinary way that happens."""
    _name, got = _role(ctx, ["model:reed"])
    outcome = refused_by_the_control(got, "a role granting an unknown permission")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "unknown_permission":
        return FAIL, f"refused '{code_of(got)}'"
    if "model:read" not in got.text and "model:reed" not in got.text:
        return FAIL, "the refusal does not name the permission it rejected"
    return PASS, "refused 'unknown_permission'"
