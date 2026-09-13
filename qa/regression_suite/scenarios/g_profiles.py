"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — warrant profiles: defaults that must not become authority.

A profile fills holes in a warrant request. The whole risk of the feature is
one sentence: a default that decides WHO may act, FOR WHAT, or UNTIL WHEN is
not a convenience, it is authority granted by a template nobody reviewed. The
cases here push on that line from both sides, and on whether a profile that
was retired actually stops applying.
"""
from __future__ import annotations

from core.execution.profiles import AUTHORITY_KEYS, DEFAULTABLE
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

PROFILES = "/api/v1/warrant-profiles"
#: `warrant:issue` is a FIRST-LINE act — it sits with the model owner, not
#: with the model risk manager. Running these as `risk` had every case
#: answering `forbidden`, which is a refusal, which read as a pass. A
#: permission refusal proves nothing about the control being tested, so
#: `refused_by_the_control` rejects it explicitly rather than trusting the
#: fixture to keep using the right identity.
DENIAL = ("forbidden", "unauthorised", "unauthorized")
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _profile(ctx: Ctx, **over):
    body = {"name": ctx.unique("prof"), "when": {"environment": ["dev"]},
            "defaults": {"max_seconds": 30}, "note": "QA"}
    body.update(over)
    return ctx.api.post(PROFILES, json=body, auth=ctx.people["owner"])


def refused_by_the_control(got, subject: str) -> Result:
    """Refused, and NOT merely because the caller lacked permission."""
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:150]}"
    if got.status_code < 400:
        return FAIL, subject
    code = code_of(got)
    if code in DENIAL:
        return BLOCKED, (f"answered '{code}' — the caller could not reach the "
                         f"control, so this proves nothing about it")
    return PASS, f"refused '{code or got.status_code}'"


def _versioned_model(ctx: Ctx) -> str:
    """Returns the bare NAME, not the urn.

    The preview normalises whatever it is given through `model_urn`, so a
    full urn comes back as `maya://model/maya://model/...` and the case is
    refused `registry_refused` — a refusal, and therefore a pass, for a
    reason that has nothing to do with profiles.
    """
    name = ctx.unique("pf")
    ctx.api.post("/api/v1/models",
                 json={"urn": f"maya://model/{name}", "name": name,
                       "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return name


@case("QA-FX-1200", "A profile that selects on a fact nobody derives")
def fx_1200(ctx: Ctx) -> Result:
    """Selecting on a typed-in category would be a second taxonomy, able to
    disagree with the first."""
    return refused_by_the_control(
        _profile(ctx, when={"criticality": ["high"]}),
        "a profile selects on a fact the platform never derives")


@case("QA-FX-1201", "A predicate that allows nothing")
def fx_1201(ctx: Ctx) -> Result:
    """A profile that can never match is not inert, it is a control somebody
    will believe is running."""
    return refused_by_the_control(
        _profile(ctx, when={"environment": []}),
        "a profile was registered that can never match anything")


@case("QA-FX-1202", "A profile that supplies no defaults")
def fx_1202(ctx: Ctx) -> Result:
    return refused_by_the_control(
        _profile(ctx, defaults={}),
        "a profile that matches and changes nothing was registered; it "
        "reads as a control that ran")


@case("QA-FX-1203", "Every authority key is refused as a default")
def fx_1203(ctx: Ctx) -> Result:
    """Not a sample — the whole tuple. The list is the control, and a single
    member that slipped through would be authority by template."""
    leaked, unreached = [], []
    for key in AUTHORITY_KEYS:
        got = _profile(ctx, defaults={key: "x"})
        if got.status_code < 400:
            leaked.append(key)
        elif code_of(got) in DENIAL:
            unreached.append(key)
    if leaked:
        return FAIL, ("a profile may fill in " + ", ".join(leaked)
                      + " — each decides who may act, for what, or until when")
    if unreached:
        return BLOCKED, f"{len(unreached)} key(s) answered a permission denial"
    return PASS, (f"all {len(AUTHORITY_KEYS)} authority keys refused by the "
                  f"control itself")


@case("QA-FX-1204", "A default that is neither authority nor defaultable")
def fx_1204(ctx: Ctx) -> Result:
    return refused_by_the_control(
        _profile(ctx, defaults={"colour": "blue"}),
        "a profile fills in a key no warrant request has")


@case("QA-FX-1205", "A profile with no name")
def fx_1205(ctx: Ctx) -> Result:
    return refused_by_the_control(
        _profile(ctx, name="   "),
        "a profile was registered with no name to retire it by")


@case("QA-FX-1206", "A profile needs authority over the whole estate")
def fx_1206(ctx: Ctx) -> Result:
    """A profile is not about one model: it sets defaults for every model its
    predicate matches, in every entity. A partially scoped principal does not
    reach that far."""
    got = _profile(ctx)
    if got.status_code >= 400:
        return BLOCKED, f"the privileged case could not run: {got.text[:150]}"
    denied = ctx.api.post(PROFILES,
                          json={"name": ctx.unique("prof"),
                                "when": {"environment": ["dev"]},
                                "defaults": {"max_seconds": 30}},
                          auth=ctx.people["observer"])
    if denied.status_code < 400:
        return FAIL, ("an unprivileged principal registered warrant defaults "
                      "for every model in the estate")
    return PASS, f"refused ({denied.status_code})"


@case("QA-FX-1207", "Retire a profile that was never registered")
def fx_1207(ctx: Ctx) -> Result:
    return refused_by_the_control(
        ctx.api.post(f"{PROFILES}/qa-never/retire", auth=ctx.people["owner"]),
        "a profile that does not exist was retired")


@case("QA-FX-1208", "Retiring a profile stops it applying")
def fx_1208(ctx: Ctx) -> Result:
    """Registering the same name twice makes a second VERSION. If retire only
    marks the current one, retiring v2 uncovers v1 and the profile carries on
    filling in defaults under a name somebody believes is withdrawn.
    """
    name = ctx.unique("prof")
    for seconds in (30, 60):
        made = _profile(ctx, name=name, defaults={"max_seconds": seconds})
        if made.status_code >= 400:
            return BLOCKED, made.text[:170]
    gone = ctx.api.post(f"{PROFILES}/{name}/retire", auth=ctx.people["owner"])
    if gone.status_code >= 400:
        return BLOCKED, gone.text[:170]
    listing = ctx.api.get(PROFILES, auth=ctx.people["owner"])
    if listing.status_code >= 400:
        return BLOCKED, listing.text[:170]
    still = [p for p in listing.json().get("profiles", [])
             if p.get("name") == name]
    if still:
        return FAIL, ("retiring '%s' left version %s live — retire marks the "
                      "current version, so the previous one is uncovered and "
                      "the profile goes on filling in defaults under a name "
                      "the register reports as withdrawn"
                      % (name, still[0].get("version")))
    return PASS, "the name is gone from the live profiles"


@case("QA-FX-1209", "A profile never overrides what the caller wrote")
def fx_1209(ctx: Ctx) -> Result:
    made = _profile(ctx, when={}, defaults={"max_seconds": 30})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{PROFILES}/preview",
                       json={"urn": _versioned_model(ctx), "environment": "dev",
                             "request": {"max_seconds": 5}},
                       auth=ctx.people["owner"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if body.get("request", {}).get("max_seconds") != 5:
        return FAIL, ("a profile overwrote a value the caller supplied: "
                      f"asked for 5, got {body.get('request', {}).get('max_seconds')}")
    if "max_seconds" in (body.get("applied") or {}):
        return FAIL, "the derivation reports filling a value the caller wrote"
    return PASS, "the caller's value stands and is not reported as filled"


@case("QA-FX-1210", "Every filled value names the profile it came from")
def fx_1210(ctx: Ctx) -> Result:
    """A default whose origin cannot be named is a value nobody can argue
    with later."""
    name = ctx.unique("prof")
    made = _profile(ctx, name=name, when={}, defaults={"max_seconds": 30})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{PROFILES}/preview",
                       json={"urn": _versioned_model(ctx), "environment": "dev",
                             "request": {}}, auth=ctx.people["owner"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    applied = got.json().get("applied") or {}
    unattributed = [k for k, v in applied.items() if not v]
    if not applied:
        return FAIL, "a matching profile filled nothing"
    if unattributed:
        return FAIL, f"filled without naming a source: {unattributed}"
    return PASS, f"{len(applied)} value(s), each naming profile@version"


@case("QA-FX-1211", "Preview against a model with no version")
def fx_1211(ctx: Ctx) -> Result:
    """The facts a predicate reads come from the version's kernel. With no
    version there are no facts, and guessing them would make the preview a
    different fold from the one the issuer runs."""
    name = ctx.unique("pf")
    ctx.api.post("/api/v1/models", json={"urn": f"maya://model/{name}",
                                         "name": name, "owner": "owner", **TIER})
    got = ctx.api.post(f"{PROFILES}/preview",
                       json={"urn": name, "request": {}},
                       auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a preview reported defaults against no version at all"
    if code_of(got) == "registry_refused":
        return FAIL, ("the model it was asked about was not found: "
                      + got.text[:140])
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-FX-1212", "The vocabulary is published, not documented")
def fx_1212(ctx: Ctx) -> Result:
    """The two lists ARE the design, so they have to be readable by a caller
    rather than only by a reader of the source."""
    got = ctx.api.get("/api/v1/warrant-profile-vocabulary",
                      auth=ctx.people["owner"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if set(body.get("defaultable") or {}) != set(DEFAULTABLE):
        return FAIL, ("the published defaultable list disagrees with the one "
                      "the register enforces")
    if set(body.get("never_defaultable") or []) != set(AUTHORITY_KEYS):
        return FAIL, ("the published never-defaultable list disagrees with "
                      "the tuple that is actually refused")
    return PASS, "published lists match the enforced ones"
