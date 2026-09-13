"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — access recertification.

"Recertifying your own access is refused. That is the whole failure mode of an
access review, and it is not hypothetical." The reviewer is authorised by
being NAMED rather than by holding a permission, which is unusual enough to be
worth testing from both sides — and the self-review check is one of the ten
still comparing identities with `==`.
"""
from __future__ import annotations

from core.authz.recertification import ANSWERS, CONFIRMED, REVOKED
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

R = "/api/v1/recertification"


def _person(ctx: Ctx, role: str = "auditor"):
    who = ctx.unique("rc")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": [role], "password": f"{who}-pw",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        raise AssertionError(f"could not mint a principal: {made.text[:170]}")
    return who


def _open(ctx: Ctx, reviewer: str, population, **over):
    body = {"reference": ctx.unique("REC"), "reviewer": reviewer,
            "title": "A QA review", "population": list(population)}
    body.update(over)
    return ctx.api.post(R, json=body), body["reference"]


def _answer(ctx: Ctx, reference: str, principal: str, reviewer: str,
            state: str = CONFIRMED, reason: str = "still needed"):
    return ctx.api.post(f"{R}/{reference}/{principal}",
                        json={"state": state, "reason": reason},
                        auth=(reviewer, f"{reviewer}-pw"))


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-GOV-252", "Open a campaign over an explicitly empty population")
def gov_252(ctx: Ctx) -> Result:
    """A blank population reviews everybody active — but an explicitly empty
    one is a review of nobody, which closes complete on the day it opens."""
    made, _ = _open(ctx, _person(ctx), [])
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code >= 400:
        return PASS, f"refused '{code_of(made)}'"
    body = made.json() or {}
    covered = body.get("population")
    if covered is None:
        covered = body.get("items") or body.get("subjects") or body.get("total")
    size = covered if isinstance(covered, int) else len(covered or [])
    if not size:
        return FAIL, ("a campaign was opened over nobody, so it reports "
                      "complete on the day it opened")
    return PASS, f"a blank population means everybody active: {size} subject(s)"


@case("QA-GOV-259", "Answer somebody who is not in the campaign")
def gov_259(ctx: Ctx) -> Result:
    """The population is what the review covered. Answering outside it makes
    the completion figure describe a different set."""
    subject, reviewer = _person(ctx), _person(ctx)
    made, ref = _open(ctx, reviewer, [subject])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    outsider = _person(ctx)
    got = _answer(ctx, ref, outsider, reviewer)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "somebody outside the population was recertified"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-260", "Answer with a third state")
def gov_260(ctx: Ctx) -> Result:
    """"There is no third value and no timeout." A `defer` would be how a
    review completes without anybody deciding anything."""
    subject, reviewer = _person(ctx), _person(ctx)
    made, ref = _open(ctx, reviewer, [subject])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _answer(ctx, ref, subject, reviewer, state="defer")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a third answer was recorded, so a review can defer"
    if not any(a in got.text for a in ANSWERS):
        return FAIL, "the refusal does not name the two answers"
    return PASS, f"refused '{code_of(got)}', naming {' and '.join(ANSWERS)}"


@case("QA-GOV-261", "Revoke with no reason")
def gov_261(ctx: Ctx) -> Result:
    """Taking somebody's access away without recording why is the half of an
    access review that ends up in a tribunal."""
    subject, reviewer = _person(ctx), _person(ctx)
    made, ref = _open(ctx, reviewer, [subject])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _answer(ctx, ref, subject, reviewer, state=REVOKED, reason="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "access was revoked with no reason recorded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-256", "A reviewer spelled person/r against a campaign naming r")
def gov_256(ctx: Ctx) -> Result:
    """The campaign's reviewer is compared with `actor != campaign["reviewer"]`
    — one of the ten `==` duties checks QA-PLT-2700 lists. Reaching it needs
    two spellings of one human to both be accepted somewhere, and they are
    not: a principal is looked up by the string as written, so `person/x` is
    refused `no_such_principal` at the door. The `==` is shielded by a
    strict lookup rather than by being right, which is worth recording — the
    shield is in a different module and nothing ties the two together.
    """
    subject, reviewer = _person(ctx), _person(ctx)
    made, ref = _open(ctx, f"person/{reviewer}", [subject])
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code >= 400:
        if code_of(made) == "no_such_principal":
            return PASS, ("a prefixed name is refused at the door, so the "
                          "`==` reviewer check never sees two spellings")
        return BLOCKED, f"refused '{code_of(made)}' for another reason"
    got = _answer(ctx, ref, subject, reviewer)
    if got.status_code >= 400 and code_of(got) == "not_the_reviewer":
        return FAIL, (f"the campaign names 'person/{reviewer}' and the same "
                      f"human authenticating as '{reviewer}' is refused "
                      f"'not_the_reviewer' — locked out of their own review")
    return PASS, "the two spellings are recognised as one person"


@case("QA-GOV-257", "A reviewer answering their own row")
def gov_257(ctx: Ctx) -> Result:
    """The whole failure mode of an access review, and not hypothetical."""
    reviewer = _person(ctx)
    made, ref = _open(ctx, reviewer, [reviewer])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _answer(ctx, ref, reviewer, reviewer)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a reviewer confirmed their own access"
    if code_of(got) in DENIAL:
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-3500", "A reviewer answering their own row, spelled differently")
def gov_3500(ctx: Ctx) -> Result:
    """The unsafe direction of the same `==`. A population row written
    `person/x` answered by `x` would slip past `actor == principal`. It
    cannot be reached either, for the same reason: the population is resolved
    against the register and a prefixed name is not a principal.
    """
    reviewer = _person(ctx)
    made, ref = _open(ctx, reviewer, [f"person/{reviewer}"])
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code >= 400:
        if code_of(made) == "no_such_principal":
            return PASS, ("a prefixed name cannot enter a population, so the "
                          "`==` self-review check never sees two spellings")
        return BLOCKED, f"refused '{code_of(made)}' for another reason"
    got = _answer(ctx, ref, f"person/{reviewer}", reviewer)
    if got.status_code >= 400:
        if code_of(got) == "self_recertification":
            return PASS, "recognised as the same person across spellings"
        return BLOCKED, f"refused '{code_of(got)}' for another reason"
    return FAIL, (
        f"'{reviewer}' confirmed their own access by the row being written "
        f"'person/{reviewer}'; the check is `actor == principal`")


@case("QA-GOV-265", "Answer after the campaign is closed")
def gov_265(ctx: Ctx) -> Result:
    subject, reviewer = _person(ctx), _person(ctx)
    made, ref = _open(ctx, reviewer, [subject])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    closed = ctx.api.post(f"{R}/{ref}/close")
    if closed.status_code >= 400:
        return BLOCKED, f"could not close: {closed.text[:140]}"
    got = _answer(ctx, ref, subject, reviewer)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an answer landed after the review closed"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-266", "Close a campaign twice")
def gov_266(ctx: Ctx) -> Result:
    made, ref = _open(ctx, _person(ctx), [_person(ctx)])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    if ctx.api.post(f"{R}/{ref}/close").status_code >= 400:
        return BLOCKED, "the first close failed"
    got = ctx.api.post(f"{R}/{ref}/close")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a closed review was closed again"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-267", "Reuse the reference of a closed campaign")
def gov_267(ctx: Ctx) -> Result:
    """Two reviews under one reference is one completion figure covering two
    populations, whether or not the first is finished."""
    made, ref = _open(ctx, _person(ctx), [_person(ctx)])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    ctx.api.post(f"{R}/{ref}/close")
    again, _ = _open(ctx, _person(ctx), [_person(ctx)], reference=ref)
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "a closed review's reference was reused"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-GOV-268", "Reassign with no reason")
def gov_268(ctx: Ctx) -> Result:
    """Handing a review to somebody else is a change to who is accountable
    for it."""
    made, ref = _open(ctx, _person(ctx), [_person(ctx)])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{R}/{ref}/reassign",
                       json={"to": _person(ctx), "reason": "  "})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a review changed hands with no reason recorded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-269", "Reassign to a principal who does not exist")
def gov_269(ctx: Ctx) -> Result:
    """A review assigned to nobody is a review nobody will do, and it reads
    as assigned."""
    made, ref = _open(ctx, _person(ctx), [_person(ctx)])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{R}/{ref}/reassign",
                       json={"to": "qa-nobody-at-all", "reason": "handover"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a review was assigned to somebody who does not exist"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-270", "Reassign a closed campaign")
def gov_270(ctx: Ctx) -> Result:
    made, ref = _open(ctx, _person(ctx), [_person(ctx)])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    ctx.api.post(f"{R}/{ref}/close")
    got = ctx.api.post(f"{R}/{ref}/reassign",
                       json={"to": _person(ctx), "reason": "handover"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a closed review was handed to a new reviewer"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-3501", "Revoking removes roles here and says so")
def gov_3501(ctx: Ctx) -> Result:
    """"Revoking removes roles in this register and nothing else. It does not
    touch a directory, a database grant, a VPN profile or anybody's job, and
    a platform reporting *access removed* would be reporting a removal it
    cannot see."
    """
    subject, reviewer = _person(ctx), _person(ctx)
    made, ref = _open(ctx, reviewer, [subject])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _answer(ctx, ref, subject, reviewer, state=REVOKED,
                  reason="left the team")
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    text = got.text.lower()
    if "roles_removed_in_maya" not in text and "in maya" not in text \
            and "this register" not in text:
        return FAIL, ("the answer says access was revoked without saying that "
                      "only this register's roles were removed")
    return PASS, "the wording is bounded to what the platform can see"
