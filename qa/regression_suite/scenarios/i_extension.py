"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — extension: plugins a firm installs, and rulebooks it already has.

Two doors into the platform from outside, and both are dangerous in the same
way. A plugin takes effect because somebody ran `pip install`, and a rule
importer turns a spreadsheet into something that decides. Neither failure is
loud: a control changed by a dependency bump is a control nobody changed on
purpose, and a misread threshold produces a rule set that loads, validates,
publishes and decides differently from the rulebook it claims to be.
"""
from __future__ import annotations

import inspect

from core.plugins.registry import AXES, OPEN
from core.rules.importing import (DECISION_TABLE, DMN, NOT_TRANSLATED,
                                  UNMAPPABLE)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

PLUGINS = "/api/v1/plugins"
IMPORT = "/api/v1/rule-import"

#: Every row needs a `because`: an imported rule that cannot say why it
#: decided is a rule the register cannot explain back, and the importer
#: reports the omission as an untranslated row rather than inventing one.
CLEAN = ("score,out:decision,because\n"
         ">=650,approve,score at or above the cut\n"
         "<650,refer,score below the cut\n")
#: The same table with one unreadable cell. `>=650` parses; `good credit` is
#: a human judgement and does not.
TABLE = ("score,history,out:decision,because\n"
         ">=650,clean,approve,clean file above the cut\n"
         "<650,good credit,refer,judgement call\n")


def _read(ctx: Ctx, **over):
    body = {"format": DECISION_TABLE, "document": CLEAN, "note": "QA"}
    body.update(over)
    return ctx.api.post(IMPORT, json=body, auth=ctx.people["developer"])


@case("QA-PLT-1200", "Discovery reads packaging metadata and imports nothing")
def plt_1200(ctx: Ctx) -> Result:
    """The separation is the whole module: an entry point can be SEEN without
    being trusted. Asserted against the source, because the property is "this
    code path never executes third-party code" and no response body can show
    that.
    """
    from core.plugins import discovery
    source = inspect.getsource(discovery.PluginDiscovery.discover)
    described = inspect.getsource(discovery.PluginDiscovery._describe)
    for name, body in (("discover", source), ("_describe", described)):
        if ".load()" in body:
            return FAIL, (f"{name}() calls load(), so listing what is "
                          f"installed executes it — installing would then be "
                          f"enabling")
    if ".load()" not in inspect.getsource(discovery.PluginDiscovery.enable):
        return FAIL, "enable() does not import, so nothing is ever loaded"
    return PASS, "discover reads, enable imports, and only enable calls load()"


@case("QA-PLT-1201", "Enabling something configuration does not name")
def plt_1201(ctx: Ctx) -> Result:
    """Installing a package makes an extension available; a person naming it
    makes it used."""
    return refused_by_the_control(
        ctx.api.post(f"{PLUGINS}/enable",
                     json={"axis": "test_types", "name": "qa-never-named"},
                     auth=ctx.people["risk"]),
        "a plugin was imported that this firm's configuration never named")


@case("QA-PLT-1202", "Enabling against a closed axis")
def plt_1202(ctx: Ctx) -> Result:
    """A closed axis is reported rather than silently skipped: somebody either
    misunderstood the boundary or disagrees with it, and both are worth a
    conversation."""
    closed = sorted(a for a, s in AXES.items() if s["state"] != OPEN)
    if not closed:
        return BLOCKED, "no axis is closed, so there is nothing to refuse"
    got = ctx.api.post(f"{PLUGINS}/enable",
                       json={"axis": closed[0], "name": "qa-probe"},
                       auth=ctx.people["risk"])
    if got.status_code < 400:
        return FAIL, f"a plugin was enabled against closed axis {closed[0]}"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}' for closed axis {closed[0]}"


@case("QA-PLT-1203", "The contract says which axes are closed and what each protects")
def plt_1203(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{PLUGINS}/contract", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    closed = body.get("closed") or {}
    expected = {a for a, s in AXES.items() if s["state"] != OPEN}
    if set(closed) != expected:
        return FAIL, ("the published closed-axis list is not the one enable() "
                      "refuses by")
    unexplained = [a for a, why in closed.items() if not str(why).strip()]
    if unexplained:
        return FAIL, f"closed with no stated reason: {unexplained}"
    if body.get("installing_is_not_enabling") is not True:
        return FAIL, "the contract does not state that installing is not enabling"
    return PASS, f"{len(closed)} closed axes, each naming what it protects"


@case("QA-PLT-1204", "A fibre may add obligations and never remove one")
def plt_1204(ctx: Ctx) -> Result:
    """A fibre that could drop an obligation is a way to loosen every control
    on that class from outside the platform."""
    from core.plugins.discovery import PluginDiscovery
    source = inspect.getsource(PluginDiscovery._check_fibre)
    if "fibre_narrows_obligations" not in source:
        return FAIL, "nothing refuses a fibre that drops an obligation"
    if "ours - theirs" not in source and "- theirs" not in source:
        return FAIL, ("the comparison is not shipped-minus-theirs, so a "
                      "narrowing would not be what is detected")
    return PASS, "a narrowing is refused by name at load time"


@case("QA-PLT-1205", "Discovery is listable without enabling anything")
def plt_1205(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{PLUGINS}/discovered", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    enabled = [p for p in (body.get("plugins") or body.get("found") or [])
               if p.get("state") == "enabled"]
    if enabled:
        return FAIL, f"listing what is installed enabled {len(enabled)}"
    return PASS, "listed, nothing enabled"


@case("QA-PLT-1206", "An import format that is refused by name")
def plt_1206(ctx: Ctx) -> Result:
    """A format named with a reason is a conversation; a format missing is a
    support ticket."""
    fmt = sorted(NOT_TRANSLATED)[0]
    got = _read(ctx, format=fmt, document="anything")
    if got.status_code < 400:
        return FAIL, f"'{fmt}' was translated into a rule set"
    if code_of(got) != "format_not_translated":
        return FAIL, f"refused '{code_of(got)}': {got.text[:150]}"
    if len(got.json().get("remediation", "")) < 40:
        return FAIL, "refused by name with no reason and no alternative"
    return PASS, f"refused '{fmt}' by name, with what to do instead"


@case("QA-PLT-1207", "An import format nobody has heard of")
def plt_1207(ctx: Ctx) -> Result:
    return refused_by_the_control(
        _read(ctx, format="spreadsheet"),
        "an unknown format was parsed into a rule set")


@case("QA-PLT-1208", "A row a parser cannot read refuses the whole document")
def plt_1208(ctx: Ctx) -> Result:
    """The rows a parser finds hard are the judgement calls, and those are
    what the rulebook exists for. A partial import drops exactly them."""
    got = _read(ctx, document=TABLE)
    body = got.json() if got.status_code < 500 else {}
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    untranslated = body.get("untranslated") or []
    if got.status_code < 400 and body.get("candidate"):
        return FAIL, ("a document with an unreadable row produced an "
                      "importable rule set; the hard rows are the ones that "
                      "went missing")
    if got.status_code < 400 and not untranslated:
        return FAIL, "the unreadable row was neither translated nor reported"
    return PASS, (f"{len(untranslated)} untranslated row(s) named, no "
                  f"importable document")


@case("QA-PLT-1209", "A hit policy that does not map is refused, not approximated")
def plt_1209(ctx: Ctx) -> Result:
    """First-match would agree with a COLLECT table on most inputs, which is
    worse than disagreeing on all of them."""
    policy = sorted(UNMAPPABLE)[0]
    got = _read(ctx, document=f"hit_policy,{policy}\n{CLEAN}")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' for hit policy {policy}"
    body = got.json()
    if body.get("hit_policy") == policy and body.get("candidate"):
        return FAIL, (f"a {policy} table was carried as first-match, which "
                      f"agrees with the source on most inputs")
    return PASS, f"no rule set produced from a {policy} table"


@case("QA-PLT-1210", "An import produces a candidate, never a parameter set")
def plt_1210(ctx: Ctx) -> Result:
    """An importer that wrote into the register would be authoring a
    parameter set on somebody else's behalf."""
    got = _read(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if body.get("parameter_set_id") or body.get("published"):
        return FAIL, "the import wrote a parameter set into the register"
    # `candidate`, not `document` — the key names what it is: something that
    # still has to go through check, trial and a second person.
    if not body.get("candidate"):
        return BLOCKED, f"nothing parsed from a clean table: {got.text[:150]}"
    if body.get("imports_anything") is not False:
        return FAIL, "the report does not state that it imported nothing"
    return PASS, f"a candidate of {body['rules']} rule(s), and nothing written"


@case("QA-PLT-1211", "The catch-all is not invented from the last row")
def plt_1211(ctx: Ctx) -> Result:
    """A decision table's final row is often a catch-all and often is not.
    Guessing wrong produces a rule set that decides confidently on the inputs
    nobody thought about."""
    got = _read(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    candidate = body.get("candidate")
    if not candidate:
        return BLOCKED, ("nothing parsed, so there is no candidate to check "
                         "for an invented catch-all: " + got.text[:130])
    if candidate.get("otherwise"):
        return FAIL, ("an `otherwise` was invented from a table that declared "
                      "none: " + str(candidate["otherwise"])[:90])
    if body.get("needs_an_otherwise") is not True:
        return FAIL, ("the report does not say the rule set still needs a "
                      "catch-all, so the omission is silent")
    return PASS, "no catch-all invented, and the gap is reported"


@case("QA-PLT-1212", "The published formats are the ones actually read")
def plt_1212(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{IMPORT}/formats", auth=ctx.people["developer"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    reads = {e.get("format") for e in body.get("reads") or []}
    if reads != {DECISION_TABLE, DMN}:
        return FAIL, f"published as readable: {sorted(reads)}"
    refused = {e.get("format") for e in body.get("not_translated") or []}
    if refused != set(NOT_TRANSLATED):
        return FAIL, "the published refused-format list is not the enforced one"
    if body.get("imports_anything") is not False:
        return FAIL, "the endpoint does not state that it imports nothing"
    return PASS, f"{len(reads)} read, {len(refused)} refused by name"
