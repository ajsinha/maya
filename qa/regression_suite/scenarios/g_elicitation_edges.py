"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the parts of an elicitation that are about the PANEL rather than
about the number.

`g_elicitation.py` covers who may answer and when. These are the cases where
the exercise as a whole is misdescribed: a method that is not one, a second
exercise under one reference, independence recorded as though it were enforced,
convergence that can only be read after the fact, and a vocabulary of methods
that does not say how they differ.

They share a subject. An elicited parameter is a number with no data behind it,
so everything that makes it defensible is a fact about how it was obtained —
and every one of these failures loses one of those facts while keeping the
number.
"""
from __future__ import annotations

from core.parameters.elicitation import METHODS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of,
                                                  refused_by_the_control)

E = "/api/v1/elicitations"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("ee")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE},
                 auth=ctx.people["owner"])
    return urn


def _open(ctx: Ctx, **over):
    body = {"reference": ctx.unique("ELI"), "urn": _model(ctx),
            "question": "what loss rate should the overlay assume?",
            "panel": ["person/a", "person/b", "person/c"],
            "facilitator": "person/facilitator", "units": "bps",
            "method": next(iter(METHODS)), "semver": ""}
    body.update(over)
    return ctx.api.post(E, json=body, auth=ctx.people["developer"])


def _respond(ctx: Ctx, reference: str, panellist: str, value: float, **over):
    body = {"panellist": panellist, "value": value, "confidence": "medium",
            "reasoning": "qa", "independent": True, "dissented": False}
    body.update(over)
    return ctx.api.post(f"{E}/{reference}/respond", json=body,
                        auth=ctx.people["developer"])


@case("QA-FX-5503", "A method that is not one")
def fx_5503(ctx: Ctx) -> Result:
    """The method changes what the answer MEANS. A Delphi number is a
    convergence after seeing the spread; a simple average is not, and a reader
    told only 'elicited' cannot tell which they are being given."""
    got = _open(ctx, method="we_had_a_chat")
    answer = refused_by_the_control(
        got, "an elicitation was opened under a method that is not one, so the "
             "number it produces cannot be interpreted")
    if answer[0] != PASS:
        return answer
    if not any(m in got.text for m in METHODS):
        return FAIL, (f"refused '{code_of(got)}' without naming the "
                      f"{len(METHODS)} methods")
    return PASS, f"refused '{code_of(got)}', naming the methods"


@case("QA-FX-5504", "A second elicitation under one reference")
def fx_5504(ctx: Ctx) -> Result:
    """The reference is how the exercise is cited in the parameter set that
    results. Two exercises sharing one means the citation points at whichever
    is read second, and the panel that produced the number is not the panel
    the record names."""
    reference = ctx.unique("ELI")
    first = _open(ctx, reference=reference)
    if first.status_code >= 400:
        return BLOCKED, f"the first would not open: {first.text[:130]}"
    return refused_by_the_control(
        _open(ctx, reference=reference),
        "two elicitations were opened under one reference, so the parameter "
        "set citing it points at whichever is read second")


@case("QA-FX-5508", "Independence is recorded, not required")
def fx_5508(ctx: Ctx) -> Result:
    """Deliberate, and the deliberateness is the case. MAYA cannot know
    whether three people in a room answered independently — asserting it would
    be the register vouching for something it cannot see. So the flag is
    recorded as the panellist's own claim and a non-independent answer is
    ACCEPTED, because refusing it would make the honest answer the expensive
    one and every response would arrive marked independent."""
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, f"the elicitation would not open: {opened.text[:130]}"
    reference = (opened.json() or {}).get("reference") or ""
    got = _respond(ctx, reference, "person/a", 30.0, independent=False)
    if got.status_code >= 400:
        return FAIL, (f"an answer marked NOT independent was refused "
                      f"'{code_of(got)}', which makes the honest answer the "
                      f"costly one — every response will arrive marked "
                      f"independent")
    read = ctx.api.get(f"{E}?reference={reference}", auth=ctx.people["developer"])
    if read.status_code >= 400:
        return BLOCKED, f"the elicitation could not be read: {read.status_code}"
    if "independen" not in read.text.lower():
        return FAIL, ("a non-independent answer was accepted and the record "
                      "does not carry the fact, so the one thing that "
                      "distinguishes it from an independent answer is lost")
    if "false" not in read.text.lower():
        return FAIL, (f"the record mentions independence and not that THIS "
                      f"answer was not independent: {read.text[:140]}")
    return PASS, "accepted, and the claim travels with the response"


@case("QA-FX-5509", "Convergence is readable before concluding")
def fx_5509(ctx: Ctx) -> Result:
    """A spread that WIDENED across rounds is the finding, and it is only a
    finding if somebody can see it while there is still a decision to make.
    Readable only after the conclusion, it is a fact about a number already
    recorded."""
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, f"the elicitation would not open: {opened.text[:130]}"
    reference = (opened.json() or {}).get("reference") or ""
    for who, value in (("person/a", 20.0), ("person/b", 60.0),
                       ("person/c", 100.0)):
        if _respond(ctx, reference, who, value).status_code >= 400:
            return BLOCKED, f"{who} could not answer"
    got = ctx.api.get(f"{E}/{reference}/convergence",
                      auth=ctx.people["developer"])
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return FAIL, (f"convergence is not readable on an OPEN elicitation "
                      f"({got.status_code}), so a spread that widened can only "
                      f"be seen after the number it argues against is recorded")
    body = got.json() or {}
    numbers = [v for v in body.values()
               if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not numbers and not body.get("rounds"):
        return FAIL, f"convergence answers nothing measurable: {got.text[:130]}"
    return PASS, f"readable while open: {got.text[:110]}"


@case("QA-FX-5510", "Every method says how it differs")
def fx_5510(ctx: Ctx) -> Result:
    """A closed vocabulary of three that does not say what separates them is a
    dropdown. The method is the difference between a number somebody can
    interpret and a number with a label."""
    got = ctx.api.get(f"{E}/methods", auth=ctx.people["developer"])
    if got.status_code >= 400:
        return BLOCKED, f"the methods answered {got.status_code}"
    body = got.json() or {}
    rows = body.get("methods") or []
    named = {r.get("method") or r.get("key") for r in rows}
    absent = sorted(set(METHODS) - named)
    if absent:
        return FAIL, f"these methods are accepted and not published: {absent}"
    silent = [r.get("method") for r in rows
              if len(str(r.get("means") or r.get("description") or "")) < 20]
    if silent:
        return FAIL, (f"{silent} are published without saying how they differ, "
                      f"so the method is a label rather than an "
                      f"interpretation")
    return PASS, (f"{len(rows)} method(s), each saying what the number it "
                  f"produces means")
