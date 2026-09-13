"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — one human, two spellings.

`same_person` exists because the platform writes an identity as
`person/j.okafor` and authenticates the same human as `j.okafor`, and "a
duties check that compares the two with `==` is one anybody can step around by
dropping seven characters". Its own docstring says it lives in `core/authz`
rather than beside any one register because *every subsystem that enforces a
duties rule has to ask it the same way*, and that "two of them were asking it
differently".

This module asks how many still are.
"""
from __future__ import annotations

import pathlib
import re

from core.authz.common import same_person
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

#: A comparison between an actor and a recorded identity, written with `==`
#: or `!=`. The names on the right are the columns a register keeps an
#: identity in.
HELD = ("reviewer", "requested_by", "raised_by", "declared_by", "principal",
        "owner", "username", "proposed_by", "created_by", "opened_by",
        "author", "signer", "actor")
COMPARISON = re.compile(
    r"\b(actor|who|username|caller)\b\s*(==|!=)\s*"
    r"(?:[A-Za-z_]+\[\"(?P<a>[a-z_]+)\"\]|(?P<b>[a-z_]+))"
    r"|(?:[A-Za-z_]+\[\"(?P<c>[a-z_]+)\"\]|\b(?P<d>[a-z_]+)\b)\s*(==|!=)\s*"
    r"\b(actor|who|caller)\b")


def _offenders() -> list:
    """Every `==`/`!=` between an actor and a held identity, in core/."""
    found = []
    for path in sorted(pathlib.Path("core").rglob("*.py")):
        for n, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "same_person" in line:
                continue
            match = COMPARISON.search(line)
            if not match:
                continue
            held = next((match.group(g) for g in ("a", "b", "c", "d")
                         if match.group(g)), "")
            if held in HELD:
                found.append(f"{path}:{n} {stripped[:60]}")
    return found


@case("QA-PLT-2700", "Every duties comparison asks identity the same way")
def plt_2700(ctx: Ctx) -> Result:
    """`same_person` is not a helper somebody may use. It is the answer to
    "are these the same human", and a subsystem answering it with `==` has a
    different answer from every other subsystem — which is the condition its
    own docstring records as having already happened twice.
    """
    offenders = _offenders()
    if offenders:
        return FAIL, (
            f"{len(offenders)} duties comparison(s) use `==`/`!=` on an "
            f"identity rather than `same_person`, so each is stepped around "
            f"by writing the same human the other way: "
            + "; ".join(offenders[:6]))
    return PASS, "every duties comparison in core/ goes through same_person"


@case("QA-PLT-2701", "same_person itself is right")
def plt_2701(ctx: Ctx) -> Result:
    """Before reporting anybody for not using it. Prefix, case and
    surrounding space must not separate one human from themselves, and it
    must not merge two."""
    wrong = []
    for a, b in (("person/j.okafor", "j.okafor"),
                 ("PERSON/J.OKAFOR", "j.okafor"),
                 ("  person/j.okafor  ", "j.okafor"),
                 ("svc/decisioning", "decisioning")):
        if not same_person(a, b):
            wrong.append(f"{a!r} and {b!r} read as different people")
    for a, b in (("j.okafor", "j.okafors"), ("person/a", "person/b"),
                 ("", ""), ("j.okafor", "")):
        if same_person(a, b):
            wrong.append(f"{a!r} and {b!r} read as the same person")
    if wrong:
        return FAIL, "; ".join(wrong)
    return PASS, "prefix, case and space collapse; different names do not"


@case("QA-PLT-2702", "Break-glass dual authorisation under two spellings")
def plt_2702(ctx: Ctx) -> Result:
    """"Dual authorisation with one person is one person" — and the check is
    `actor == row["requested_by"]`. Break-glass is the act with the least
    margin for this: it exists precisely for the moment normal controls are
    bypassed.
    """
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    import inspect

    from core.authz.common import AuthzError
    source = inspect.getsource(breakglass.authorise)
    # `same_person(` — the CALL. The bare token is also the refusal CODE this
    # method raises, so searching for it finds the string and reports the
    # control as present in the very method that lacks it.
    if "same_person(" in source:
        return PASS, "the authorisation check goes through same_person()"
    # Establish it behaviourally rather than resting on the source read.
    # The principal being elevated has to exist; break-glass grants a real
    # person more than they normally hold, not a name.
    who = ctx.unique("elev")
    ctx.api.post("/api/v1/principals",
                 json={"username": who, "display_name": who,
                       "roles": ["auditor"], "password": f"{who}-password",
                       "legal_entities": [], "domains": []})
    try:
        opened = breakglass.request(principal=who,
                                    reason="a QA emergency", actor="risk")
    except Exception as exc:
        return BLOCKED, f"no break-glass grant could be opened: {exc}"
    asked_by = opened.get("requested_by") or ""
    other = (asked_by.split("/", 1)[-1] if "/" in asked_by
             else f"person/{asked_by}")
    try:
        breakglass.authorise(opened.get("reference"), actor=other)
    except AuthzError as exc:
        if exc.code == "same_person":
            return PASS, f"'{other}' is recognised as '{asked_by}'"
        return BLOCKED, f"refused '{exc.code}' for another reason"
    return FAIL, (
        f"the person who asked for a break-glass elevation authorised it by "
        f"writing their name as '{other}' instead of '{asked_by}'. Dual "
        f"authorisation with one person is one person, and the check is `==`")


@case("QA-PLT-2703", "The refusal codes for one-person duties are distinct")
def plt_2703(ctx: Ctx) -> Result:
    """Six subsystems refuse the same shape of act under six different codes
    — `same_person`, `self_approval`, `self_extension`, `self_suspension`,
    `raiser_may_not_close`, `author_may_not_approve`, `proposer_may_not_
    approve`. That is right, because each names what was attempted. This case
    records the set so a seventh is a decision rather than an accident.
    """
    import pathlib as _p
    codes = set()
    for path in sorted(_p.Path("core").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for code in ("same_person", "self_approval", "self_extension",
                     "self_suspension", "raiser_may_not_close",
                     "author_may_not_approve", "proposer_may_not_approve",
                     "reviewed_by_the_user", "not_the_reviewer",
                     "already_signed_personally"):
            if f'"{code}"' in text:
                codes.add(code)
    if len(codes) < 6:
        return FAIL, (f"only {len(codes)} one-person refusal code(s) found: "
                      f"{sorted(codes)}")
    return PASS, f"{len(codes)} distinct codes: {', '.join(sorted(codes))}"
