"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — a template that fills in what a caller could have typed.

The line a profile may not cross is the whole design. **A profile fills in
convenience and never authority**: anything deciding who may act, for what, or
until when is refused AT CREATION, because a check performed when the profile
is written is a check nobody can forget to perform at use. If it is an
obligation rather than a convenience it belongs as a policy on the
`warrant:resolve` gate, which refuses instead of suggesting.

A profile also selects only on facts the platform DERIVES. Selecting on a
category attached to the model would be a second taxonomy able to disagree
with the first — and the disagreement would decide which template applied.

And every filled value names its origin. A default whose provenance cannot be
named is a value nobody can argue with later.
"""
from __future__ import annotations

from core.execution.profiles import (AUTHORITY_KEYS, DEFAULTABLE,
                                     SELECTABLE_FACTS, ProfileError,
                                     WarrantProfileRegister)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)


def _engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("warrant_profiles") or \
        ctx.ui.app.state.ctx.get("profiles")


def _code(exc) -> str:
    return getattr(exc, "code", "") or f"{exc}"


@case("QA-FX-446", "A profile supplying `principal`")
def fx_446(ctx: Ctx) -> Result:
    """Filling in the principal would decide who may act rather than save
    them typing. Refused at creation, and the refusal names where an
    obligation belongs instead — a policy on the resolve gate, which refuses
    rather than suggesting."""
    try:
        WarrantProfileRegister._check_defaults({"principal": "svc-pricing"})
    except ProfileError as exc:
        if _code(exc) != "authority_not_defaultable":
            return FAIL, f"refused '{_code(exc)}'"
        if "warrant:resolve" not in getattr(exc, "remediation", ""):
            return FAIL, ("the refusal does not say where an obligation "
                          "belongs, so somebody writes it as a profile anyway")
        return PASS, "refused 'authority_not_defaultable', naming the gate"
    return FAIL, "a profile supplying the principal was accepted"


@case("QA-FX-447", "A profile supplying the TTL or the grace")
def fx_447(ctx: Ctx) -> Result:
    """*Until when* is authority. A profile lengthening a TTL would extend
    every warrant it matched without anybody deciding to, and grace extends
    authorisation currency — never revocation ignorance."""
    for key in ("ttl_seconds", "grace_seconds"):
        try:
            WarrantProfileRegister._check_defaults({key: 3600})
        except ProfileError as exc:
            if _code(exc) != "authority_not_defaultable":
                return FAIL, f"'{key}' refused '{_code(exc)}'"
            continue
        return FAIL, f"a profile supplying '{key}' was accepted"
    return PASS, "both the ttl and the grace are refused as authority"


@case("QA-FX-4870", "Every authority key is refused, and only those")
def fx_4870(ctx: Ctx) -> Result:
    """A sweep rather than a case per key. The two sets must not overlap: a
    key in both would be refused or accepted depending on which check ran
    first, and the answer would depend on the order of two constants."""
    overlap = sorted(set(AUTHORITY_KEYS) & set(DEFAULTABLE))
    if overlap:
        return FAIL, (f"{overlap} are both authority and defaultable, so "
                      f"whether a profile may supply them depends on which "
                      f"check runs first")
    for key in AUTHORITY_KEYS:
        try:
            WarrantProfileRegister._check_defaults({key: "x"})
        except ProfileError as exc:
            if _code(exc) != "authority_not_defaultable":
                return FAIL, (f"'{key}' is an authority key and refused "
                              f"'{_code(exc)}'")
            continue
        return FAIL, f"the authority key '{key}' may be supplied by a profile"
    for key in DEFAULTABLE:
        try:
            WarrantProfileRegister._check_defaults({key: "x"})
        except ProfileError as exc:
            return FAIL, f"the defaultable key '{key}' refused '{_code(exc)}'"
    return PASS, (f"{len(AUTHORITY_KEYS)} authority keys refused, "
                  f"{len(DEFAULTABLE)} defaultable keys accepted, no overlap")


@case("QA-FX-448", "A profile with no defaults")
def fx_448(ctx: Ctx) -> Result:
    """A profile that matches and changes nothing reads as a control that
    ran. It is refused rather than stored inert."""
    try:
        WarrantProfileRegister._check_defaults({})
    except ProfileError as exc:
        if _code(exc) != "empty_profile":
            return FAIL, f"refused '{_code(exc)}'"
        return PASS, "refused 'empty_profile'"
    return FAIL, "a profile supplying nothing was accepted"


@case("QA-FX-449", "A profile selecting on a fact outside the nine")
def fx_449(ctx: Ctx) -> Result:
    """Selecting on a category attached to the model would be a second
    taxonomy able to disagree with the first, and the disagreement would
    decide which template applied. The refusal names the derived facts."""
    try:
        WarrantProfileRegister._check_predicate({"business_line": ["retail"]})
    except ProfileError as exc:
        if _code(exc) != "unknown_profile_fact":
            return FAIL, f"refused '{_code(exc)}'"
        # The list lives in the remediation, not the detail — reading only
        # `str(exc)` finds none of the nine.
        said = f"{exc} {getattr(exc, 'remediation', '')}"
        missing = [f for f in SELECTABLE_FACTS if f not in said]
        if missing:
            return FAIL, f"the refusal does not name {missing}"
        if "derive" not in said.lower():
            return FAIL, ("the refusal does not say the facts must be derived")
        return PASS, (f"refused 'unknown_profile_fact', naming all "
                      f"{len(SELECTABLE_FACTS)} derived facts")
    return FAIL, "a profile selecting on an attached category was accepted"


@case("QA-FX-450", "A predicate that allows nothing")
def fx_450(ctx: Ctx) -> Result:
    """A key allowing no values can never match, and an ABSENT key matches
    everything — so the empty list is not a stricter version of the absent
    key, it is a profile that is dead on arrival. The refusal has to say
    both."""
    fact = next(iter(SELECTABLE_FACTS))
    try:
        WarrantProfileRegister._check_predicate({fact: []})
    except ProfileError as exc:
        if _code(exc) != "empty_predicate":
            return FAIL, f"refused '{_code(exc)}'"
        if "matches everything" not in f"{exc}" + getattr(exc, "remediation", ""):
            return FAIL, ("the refusal does not say that an absent key "
                          "matches everything, so the author narrows it again")
        return PASS, "refused 'empty_predicate', naming the alternative"
    return FAIL, "a predicate allowing nothing was accepted"


@case("QA-FX-4871", "A single value is accepted where a list is expected")
def fx_4871(ctx: Ctx) -> Result:
    """`{"tier": 1}` and `{"tier": [1]}` mean the same thing, and refusing
    the first would be refusing the form everybody writes."""
    got = WarrantProfileRegister._check_predicate({"tier": 1})
    if got != {"tier": [1]}:
        return FAIL, f"a scalar predicate normalised to {got}"
    listed = WarrantProfileRegister._check_predicate({"tier": [1, 2]})
    if listed != {"tier": [1, 2]}:
        return FAIL, f"a list predicate came back as {listed}"
    return PASS, "a scalar is normalised to a one-element list"


@case("QA-FX-451", "Two matching profiles fold rightmost-wins per key")
def fx_451(ctx: Ctx) -> Result:
    """Ordered by SPECIFICITY, so the general profile supplies what the
    specific one is silent about and the specific one wins where they
    disagree — *this is the default unless something more specific says
    otherwise*."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no warrant profile engine is wired"
    general = {"name": "general", "version": 1, "specificity": 0,
               "when_facts": {}, "defaults": {"mode": "batch",
                                              "max_seconds": 30}}
    specific = {"name": "specific", "version": 1, "specificity": 1,
                "when_facts": {"tier": [1]}, "defaults": {"max_seconds": 5}}

    class Fixed(type(engine)):
        def __init__(self, rows):
            self._rows = rows

        def matching(self, facts):
            return list(self._rows)

    folded = Fixed([general, specific]).apply({"tier": 1}, {})
    request = folded["request"]
    if request.get("mode") != "batch":
        return FAIL, (f"the general profile's key was lost: mode reads "
                      f"{request.get('mode')!r}")
    if request.get("max_seconds") != 5:
        return FAIL, (f"the specific profile did not win on the shared key: "
                      f"max_seconds reads {request.get('max_seconds')}")
    return PASS, ("the general supplies what the specific is silent about, "
                  "the specific wins where they overlap")


@case("QA-FX-453", "A profile default identical to the caller's value")
def fx_453(ctx: Ctx) -> Result:
    """The value is the CALLER'S, and `applied` must not claim it. A profile
    credited with a value the caller typed would make the derivation say a
    template decided something a person did."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no warrant profile engine is wired"
    profile = {"name": "p", "version": 1, "specificity": 0,
               "when_facts": {}, "defaults": {"mode": "batch"}}

    class Fixed(type(engine)):
        def __init__(self, rows):
            self._rows = rows

        def matching(self, facts):
            return list(self._rows)

    folded = Fixed([profile]).apply({}, {"mode": "batch"})
    if folded["request"].get("mode") != "batch":
        return FAIL, "the caller's value was lost"
    if "mode" in (folded.get("applied") or {}):
        return FAIL, ("the profile is credited with a value the caller typed, "
                      "so the derivation says a template decided it")
    return PASS, "the caller's value stands and the profile claims nothing"


@case("QA-FX-456", "Every filled value names its origin")
def fx_456(ctx: Ctx) -> Result:
    """A default whose origin cannot be named is a value nobody can argue
    with later — and the origin has to carry the VERSION, because a profile
    is republished as a new immutable version and *which one filled this in*
    is the question somebody asks."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no warrant profile engine is wired"
    profile = {"name": "shape", "version": 7, "specificity": 0,
               "when_facts": {}, "defaults": {"mode": "batch",
                                              "max_seconds": 30}}

    class Fixed(type(engine)):
        def __init__(self, rows):
            self._rows = rows

        def matching(self, facts):
            return list(self._rows)

    folded = Fixed([profile]).apply({}, {})
    applied = folded.get("applied") or {}
    if set(applied) != {"mode", "max_seconds"}:
        return FAIL, f"the filled keys are not all attributed: {applied}"
    for key, origin in applied.items():
        if "shape" not in origin:
            return FAIL, f"'{key}' names no profile: {origin!r}"
        if "7" not in origin:
            return FAIL, (f"'{key}' names the profile and not its version: "
                          f"{origin!r} — a republished profile is a new "
                          f"immutable version and which one filled this in "
                          f"is the question somebody asks")
    if not folded.get("profiles"):
        return FAIL, "the derivation does not list the profiles that matched"
    return PASS, f"both keys attributed to {sorted(set(applied.values()))}"


@case("QA-FX-4872", "No matching profile leaves the request untouched")
def fx_4872(ctx: Ctx) -> Result:
    """And says so. A request that came back unchanged with no explanation
    is indistinguishable from one a profile filled with the same values."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no warrant profile engine is wired"

    class Fixed(type(engine)):
        def __init__(self):
            pass

        def matching(self, facts):
            return []

    folded = Fixed().apply({"tier": 4}, {"verb": "score"})
    if folded["request"] != {"verb": "score"}:
        return FAIL, f"the request was changed: {folded['request']}"
    if folded.get("applied"):
        return FAIL, f"nothing matched and something was applied: {folded['applied']}"
    detail = folded.get("detail") or ""
    if "no profile matches" not in detail:
        return FAIL, (f"an untouched request does not say why: {detail!r}")
    if "as the caller wrote it" not in detail:
        return FAIL, "the detail does not say the request stands as written"
    return PASS, "unchanged, nothing applied, and it says so"
