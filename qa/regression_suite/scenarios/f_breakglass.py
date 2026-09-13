"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — break-glass: the control for the moment the controls are in the way.

Every refusal here is load-bearing in a way the rest of the platform's are
not, because break-glass is used at three in the morning by somebody who has
already decided the normal path is too slow. "Dual authorisation with one
person is one person", and "a post-hoc review by the person being reviewed is
the record of a review rather than a review".
"""
from __future__ import annotations

from core.authz.breakglass import OUTCOMES
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

B = "/api/v1/break-glass"


def _person(ctx: Ctx, role: str = "auditor"):
    who = ctx.unique("bg")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": [role], "password": f"{who}-pw",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        raise AssertionError(f"could not mint a principal: {made.text[:170]}")
    return who


def _request(ctx: Ctx, principal: str, who="risk", **over):
    body = {"reason": "a QA emergency", "principal": principal}
    body.update(over)
    made = ctx.api.post(B, json=body, auth=ctx.people[who])
    reference = ((made.json() or {}).get("reference")
                 if made.status_code < 400 else "")
    return made, reference


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-GOV-250", "Request for a principal who does not exist")
def gov_250(ctx: Ctx) -> Result:
    """Break-glass grants a real person more than they normally hold. A name
    is not a person, and elevating one would be an elevation nobody can
    later review."""
    made, _ = _request(ctx, "qa-nobody-at-all")
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if not _reached(made):
        return BLOCKED, f"answered '{code_of(made)}' — not reached"
    if made.status_code < 400:
        return FAIL, "an elevation was requested for somebody who is not there"
    return PASS, f"refused '{code_of(made)}'"


@case("QA-GOV-251", "Request with an empty reason")
def gov_251(ctx: Ctx) -> Result:
    """"A break-glass request with no reason is a request nobody can review."
    The review is the entire justification for allowing the mechanism."""
    made, _ = _request(ctx, _person(ctx), reason="   ")
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code < 400:
        return FAIL, "an elevation was requested with no reason recorded"
    return PASS, f"refused '{code_of(made)}'"


@case("QA-GOV-236", "Authorise your own request")
def gov_236(ctx: Ctx) -> Result:
    """"Dual authorisation with one person is one person." """
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    from core.authz.common import AuthzError
    opened = breakglass.request(principal=_person(ctx),
                                reason="a QA emergency", actor="risk")
    try:
        breakglass.authorise(opened["reference"], actor="risk")
    except AuthzError as exc:
        if exc.code != "same_person":
            return FAIL, f"refused '{exc.code}', not same_person"
        return PASS, "the requester cannot authorise their own elevation"
    return FAIL, ("the person who asked for an elevation granted it; dual "
                  "authorisation with one person is one person")


@case("QA-GOV-237", "Authorise your own request unilaterally")
def gov_237(ctx: Ctx) -> Result:
    """`unilateral` exists because "refusing outright at three in the morning
    is how an institution ends up with a shared password in a safe". It buys
    a shorter window and a flag — it must not buy the second signature.
    """
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    opened = breakglass.request(principal=_person(ctx),
                                reason="a QA emergency", actor="risk")
    from core.authz.common import AuthzError
    try:
        granted = breakglass.authorise(opened["reference"], actor="risk",
                                       unilateral=True)
    except AuthzError as exc:
        return PASS, f"refused '{exc.code}' even unilaterally"
    if not granted.get("unilateral"):
        return FAIL, ("a unilateral grant is not recorded as unilateral, so "
                      "it reads on the register as dually authorised")
    return PASS, ("a unilateral self-authorisation is permitted and flagged: "
                  "the shorter window and the flag are the whole difference")


@case("QA-GOV-240", "Authorise twice")
def gov_240(ctx: Ctx) -> Result:
    """"A grant is authorised once." A second signature on a live grant is a
    second answer to a question already answered."""
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    from core.authz.common import AuthzError
    opened = breakglass.request(principal=_person(ctx),
                                reason="a QA emergency", actor="risk")
    other = _person(ctx, "model_risk_manager")
    breakglass.authorise(opened["reference"], actor=other)
    try:
        breakglass.authorise(opened["reference"], actor=_person(ctx))
    except AuthzError as exc:
        if exc.code != "not_requested":
            return FAIL, f"refused '{exc.code}', not not_requested"
        return PASS, "a grant is authorised once"
    return FAIL, "an authorised grant was authorised again"


@case("QA-GOV-244", "The elevated principal reviews their own grant")
def gov_244(ctx: Ctx) -> Result:
    """"A post-hoc review by the person being reviewed is the record of a
    review rather than a review." """
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    from core.authz.common import AuthzError
    elevated = _person(ctx)
    opened = breakglass.request(principal=elevated, reason="a QA emergency",
                                actor="risk")
    breakglass.authorise(opened["reference"],
                         actor=_person(ctx, "model_risk_manager"))
    breakglass.close(opened["reference"], reason="done")
    try:
        breakglass.review(opened["reference"], "appropriate",
                          "I was fine", actor=elevated)
    except AuthzError as exc:
        if exc.code != "reviewed_by_the_user":
            return FAIL, f"refused '{exc.code}', not reviewed_by_the_user"
        return PASS, "the elevated principal cannot review their own grant"
    return FAIL, ("the person who used an elevation reviewed it; the review "
                  "is the entire justification for allowing the mechanism")


@case("QA-GOV-247", "Review with an outcome outside the closed set")
def gov_247(ctx: Ctx) -> Result:
    """Three outcomes, each meaning something specific. A fourth would be a
    review that decided nothing."""
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    from core.authz.common import AuthzError
    opened = breakglass.request(principal=_person(ctx),
                                reason="a QA emergency", actor="risk")
    breakglass.authorise(opened["reference"],
                         actor=_person(ctx, "model_risk_manager"))
    breakglass.close(opened["reference"], reason="done")
    try:
        breakglass.review(opened["reference"], "fine I guess", "a note",
                          actor=_person(ctx))
    except AuthzError as exc:
        if exc.code != "unknown_outcome":
            return FAIL, f"refused '{exc.code}', not unknown_outcome"
        # `str(exc)` is the DETAIL. The vocabulary is in the remediation,
        # which is the field that exists to say what to do instead.
        whole = f"{exc} {getattr(exc, 'remediation', '')}"
        if not all(o in whole for o in OUTCOMES):
            return FAIL, f"the refusal does not name the outcomes: {whole[:120]}"
        return PASS, f"refused, naming {', '.join(OUTCOMES)}"
    return FAIL, "a review recorded an outcome outside the closed set"


@case("QA-GOV-246", "Review with an empty note")
def gov_246(ctx: Ctx) -> Result:
    """The outcome is one word. The note is the review."""
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    from core.authz.common import AuthzError
    opened = breakglass.request(principal=_person(ctx),
                                reason="a QA emergency", actor="risk")
    breakglass.authorise(opened["reference"],
                         actor=_person(ctx, "model_risk_manager"))
    breakglass.close(opened["reference"], reason="done")
    try:
        breakglass.review(opened["reference"], "appropriate", "   ",
                          actor=_person(ctx))
    except AuthzError as exc:
        return PASS, f"refused '{exc.code}'"
    return FAIL, ("a break-glass review was recorded with no note; the "
                  "outcome is one word and the note is the review")


@case("QA-GOV-243", "Review a grant that is still open")
def gov_243(ctx: Ctx) -> Result:
    """A review of an elevation still in use is a review of something that
    has not finished happening."""
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    from core.authz.common import AuthzError
    opened = breakglass.request(principal=_person(ctx),
                                reason="a QA emergency", actor="risk")
    breakglass.authorise(opened["reference"],
                         actor=_person(ctx, "model_risk_manager"))
    try:
        breakglass.review(opened["reference"], "appropriate",
                          "looked fine to me", actor=_person(ctx))
    except AuthzError as exc:
        return PASS, f"refused '{exc.code}' while the grant is live"
    return FAIL, ("a live elevation was reviewed, so the review covers "
                  "something that had not finished happening")


@case("QA-GOV-245", "Review twice")
def gov_245(ctx: Ctx) -> Result:
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    from core.authz.common import AuthzError
    opened = breakglass.request(principal=_person(ctx),
                                reason="a QA emergency", actor="risk")
    breakglass.authorise(opened["reference"],
                         actor=_person(ctx, "model_risk_manager"))
    breakglass.close(opened["reference"], reason="done")
    breakglass.review(opened["reference"], "appropriate", "fine",
                      actor=_person(ctx))
    try:
        breakglass.review(opened["reference"], "unwarranted",
                          "changed my mind", actor=_person(ctx))
    except AuthzError as exc:
        return PASS, f"refused '{exc.code}'"
    return FAIL, "a reviewed grant was reviewed again with a different outcome"


@case("QA-GOV-248", "Run the expiry sweep twice")
def gov_248(ctx: Ctx) -> Result:
    """An elevation that expires twice is an incident reported twice."""
    breakglass = ctx.ui.app.state.ctx.get("break_glass")
    if breakglass is None:
        return BLOCKED, "no break-glass register reachable from this run"
    first = breakglass.expire_due()
    second = breakglass.expire_due()
    a = first.get("expired") if isinstance(first, dict) else first
    b = second.get("expired") if isinstance(second, dict) else second
    if a and b and a == b:
        return FAIL, f"the second sweep expired the same {b} grant(s) again"
    return PASS, f"first sweep {a}, second {b}"


@case("QA-GOV-4400", "Every review outcome means something specific")
def gov_4400(ctx: Ctx) -> Result:
    """Three outcomes with three meanings. A set where two said the same
    thing would make the review a formality."""
    mute = [k for k, v in OUTCOMES.items() if not (v or "").strip()]
    if mute:
        return FAIL, f"outcomes with no meaning: {mute}"
    if len(set(OUTCOMES.values())) != len(OUTCOMES):
        return FAIL, "two outcomes share a meaning"
    return PASS, ", ".join(f"{k} ({v[:28]})" for k, v in OUTCOMES.items())
