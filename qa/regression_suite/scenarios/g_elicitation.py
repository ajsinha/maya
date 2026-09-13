"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — a number a panel of people arrived at.

The register offers `fitted` as its strongest claim — estimated from data
under a warrant MAYA issued — and an elicited weight is not that. What makes
one reviewable is the panel, the question, the spread and the DISSENT, and
those are exactly what nobody looks for once a row says `fitted`. So the
provenance is `declared` and the dissent travels with the parameter set: a
final weight whose dissent nobody can find is a weight that looks unanimous.

Two refusals carry the integrity of the exercise. One expert's judgement is
not an elicitation, it is an assumption — and the assumption register is where
an assumption belongs, with a materiality and an owner. And the facilitator
sets the question and sees the responses before the panel does, so somebody in
both roles can shape the spread they are about to report.
"""
from __future__ import annotations

from core.parameters.elicitation import METHODS, MINIMUM_PANEL
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

E = "/api/v1/elicitations"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("el")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE},
                 auth=ctx.people["owner"])
    return urn


#: `parameter:record` is the FIRST line's permission — the risk manager does
#: not hold it, and opening as `risk` answers `forbidden`, which is a refusal
#: at the door and says nothing about the panel checks behind it.
def _open(ctx: Ctx, urn: str, **over):
    body = {"reference": ctx.unique("ELI"), "urn": urn,
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


def _conclude(ctx: Ctx, reference: str, **over):
    """Concluding is `parameter:approve` — the SECOND line's — while opening
    and responding are `parameter:record`. The split is the point: the panel
    produces the number and somebody else records that it is the answer."""
    body = {"value": 42.0, "note": "the panel settled after two rounds"}
    body.update(over)
    return ctx.api.post(f"{E}/{reference}/conclude", json=body,
                        auth=ctx.people["risk"])


def _reference(made) -> str:
    if made.status_code >= 400:
        return ""
    body = made.json() or {}
    return (body.get("elicitation") or body).get("reference", "")


@case("QA-FX-273", "A panel below the minimum")
def fx_273(ctx: Ctx) -> Result:
    """One expert's judgement is not an elicitation, it is an assumption —
    and the refusal has to say where an assumption belongs, or somebody
    invents a second panellist to get past it."""
    urn = _model(ctx)
    got = _open(ctx, urn, panel=["person/a"])
    if got.status_code < 400:
        return FAIL, "a panel of one was accepted as an elicitation"
    if code_of(got) != "panel_too_small":
        return FAIL, f"refused '{code_of(got)}'"
    if str(MINIMUM_PANEL) not in got.text:
        return FAIL, "the refusal does not say what the floor is"
    if "assumption" not in got.text:
        return FAIL, ("the refusal does not say where a single judgement "
                      "belongs, so somebody invents a panellist to get past it")
    at_floor = _open(ctx, urn,
                     panel=[f"person/{n}" for n in range(MINIMUM_PANEL)])
    if at_floor.status_code >= 400:
        return FAIL, (f"a panel of exactly {MINIMUM_PANEL} was refused "
                      f"'{code_of(at_floor)}'")
    return PASS, f"below {MINIMUM_PANEL} refused, exactly {MINIMUM_PANEL} accepted"


@case("QA-FX-4860", "A panel with the same person listed twice")
def fx_4860(ctx: Ctx) -> Result:
    """The panel is deduplicated before it is counted, so three entries
    naming two people is a panel of two. Counting the list rather than the
    set would let the floor be met by repeating a name."""
    urn = _model(ctx)
    got = _open(ctx, urn, panel=["person/a", "person/a", "person/b"])
    if got.status_code < 400:
        body = (got.json() or {})
        panel = (body.get("elicitation") or body).get("panel") or []
        if len(panel) != len(set(panel)):
            return FAIL, f"the panel is stored with a duplicate: {panel}"
        if len(panel) >= MINIMUM_PANEL:
            return PASS, (f"deduplicated to {len(panel)}, which still meets "
                          f"the floor of {MINIMUM_PANEL}")
        return FAIL, f"a panel of {len(panel)} met a floor of {MINIMUM_PANEL}"
    if code_of(got) != "panel_too_small":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, ("three entries naming two people is refused as a panel of "
                  "two, so a name cannot be repeated to meet the floor")


@case("QA-FX-274", "The facilitator on their own panel")
def fx_274(ctx: Ctx) -> Result:
    """The facilitator sets the question and sees the responses before the
    panel does. Somebody in both roles can shape the spread they are about to
    report, and the spread is the whole output."""
    urn = _model(ctx)
    got = _open(ctx, urn, panel=["person/a", "person/b", "person/f"],
                facilitator="person/f")
    if got.status_code < 400:
        return FAIL, "the facilitator was accepted onto their own panel"
    if code_of(got) != "facilitator_is_a_panellist":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'facilitator_is_a_panellist'"


@case("QA-FX-275", "An elicitation with no question")
def fx_275(ctx: Ctx) -> Result:
    """Two experts answering slightly different questions produce a spread
    that means nothing, and the spread is what the exercise reports."""
    urn = _model(ctx)
    got = _open(ctx, urn, question="   ")
    if got.status_code < 400:
        return FAIL, "an elicitation with no recorded question was opened"
    if code_of(got) != "question_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'question_required' on whitespace"


@case("QA-FX-276", "A second response in one round")
def fx_276(ctx: Ctx) -> Result:
    """Never overwritten. A panellist who could revise inside a round would
    be answering after seeing where the others landed, which is the thing the
    rounds exist to control."""
    urn = _model(ctx)
    reference = _reference(_open(ctx, urn))
    if not reference:
        return BLOCKED, "the elicitation could not be opened"
    if _respond(ctx, reference, "person/a", 10.0).status_code >= 400:
        return BLOCKED, "the first response failed"
    got = _respond(ctx, reference, "person/a", 99.0)
    if got.status_code < 400:
        return FAIL, ("a panellist answered twice in one round, so a revision "
                      "after seeing the others is possible")
    if code_of(got) != "already_answered":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'already_answered'"


@case("QA-FX-277", "A response from somebody not on the panel")
def fx_277(ctx: Ctx) -> Result:
    """The panel is fixed at the outset and cannot be added to mid-round: a
    new member changes the denominator of a spread that has already been
    partly formed."""
    urn = _model(ctx)
    reference = _reference(_open(ctx, urn))
    if not reference:
        return BLOCKED, "the elicitation could not be opened"
    got = _respond(ctx, reference, "person/nobody", 10.0)
    if got.status_code < 400:
        return FAIL, "somebody not on the panel answered"
    if code_of(got) != "not_on_the_panel":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'not_on_the_panel'"


@case("QA-FX-279", "Advancing an empty round")
def fx_279(ctx: Ctx) -> Result:
    """A round nobody answered is not a round, and advancing past it would
    make the round count say the panel deliberated more than it did."""
    urn = _model(ctx)
    reference = _reference(_open(ctx, urn))
    if not reference:
        return BLOCKED, "the elicitation could not be opened"
    got = ctx.api.post(f"{E}/{reference}/next-round",
                       auth=ctx.people["developer"])
    if got.status_code < 400:
        return FAIL, "an empty round was advanced"
    if code_of(got) != "round_is_empty":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'round_is_empty'"


@case("QA-FX-280", "Concluding with no responses at all")
def fx_280(ctx: Ctx) -> Result:
    """A conclusion with no responses behind it is one person's number
    wearing a panel's name."""
    urn = _model(ctx)
    reference = _reference(_open(ctx, urn))
    if not reference:
        return BLOCKED, "the elicitation could not be opened"
    got = _conclude(ctx, reference)
    if got.status_code < 400:
        return FAIL, "an elicitation nobody answered was concluded"
    if code_of(got) != "nothing_to_conclude":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'nothing_to_conclude'"


@case("QA-FX-281", "Concluding with no note")
def fx_281(ctx: Ctx) -> Result:
    """The number is the least interesting thing an elicitation produces, and
    a year later the note is the only part anybody can act on."""
    urn = _model(ctx)
    reference = _reference(_open(ctx, urn))
    if not reference:
        return BLOCKED, "the elicitation could not be opened"
    for who, value in (("person/a", 10.0), ("person/b", 12.0)):
        if _respond(ctx, reference, who, value).status_code >= 400:
            return BLOCKED, "a response failed"
    got = _conclude(ctx, reference, note="  ")
    if got.status_code < 400:
        return FAIL, "a conclusion with no reasoning was recorded"
    if code_of(got) != "note_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'note_required' on whitespace"


@case("QA-FX-278", "A response after the conclusion")
def fx_278(ctx: Ctx) -> Result:
    """The exercise is over. A response arriving afterwards would change a
    spread that has already been reported, and the conclusion cites it."""
    urn = _model(ctx)
    reference = _reference(_open(ctx, urn))
    if not reference:
        return BLOCKED, "the elicitation could not be opened"
    for who, value in (("person/a", 10.0), ("person/b", 12.0)):
        if _respond(ctx, reference, who, value).status_code >= 400:
            return BLOCKED, "a response failed"
    if _conclude(ctx, reference).status_code >= 400:
        return BLOCKED, "the conclusion failed"
    got = _respond(ctx, reference, "person/c", 99.0)
    if got.status_code < 400:
        return FAIL, ("a response landed after the conclusion, so a reported "
                      "spread can still change")
    if code_of(got) != "elicitation_closed":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'elicitation_closed'"


@case("QA-FX-283", "A spread that widens across rounds")
def fx_283(ctx: Ctx) -> Result:
    """Convergence says it did NOT converge. A Delphi that reports narrowing
    whatever happened is a ritual, and the widening case is the one worth
    reading — it means the question was ambiguous or the panel disagrees
    about something they have not said out loud."""
    urn = _model(ctx)
    reference = _reference(_open(ctx, urn))
    if not reference:
        return BLOCKED, "the elicitation could not be opened"
    for who, value in (("person/a", 10.0), ("person/b", 11.0)):
        if _respond(ctx, reference, who, value).status_code >= 400:
            return BLOCKED, "a first-round response failed"
    if ctx.api.post(f"{E}/{reference}/next-round",
                    auth=ctx.people["developer"]).status_code >= 400:
        return BLOCKED, "the round could not be advanced"
    for who, value in (("person/a", 1.0), ("person/b", 90.0)):
        if _respond(ctx, reference, who, value).status_code >= 400:
            return BLOCKED, "a second-round response failed"
    got = ctx.api.get(f"{E}/{reference}/convergence",
                      auth=ctx.people["developer"])
    if got.status_code >= 400:
        return BLOCKED, f"the convergence read answered {got.status_code}"
    body = got.json() or {}
    if body.get("narrowed"):
        return FAIL, (f"a spread that went from 1.0 to 89.0 is reported as "
                      f"narrowed: {body.get('spreads')}")
    spreads = body.get("spreads") or []
    if len(spreads) < 2 or spreads[-1] <= spreads[0]:
        return FAIL, f"the spreads do not show the widening: {spreads}"
    if not (body.get("detail") or "").strip():
        return FAIL, "convergence reports no detail"
    return PASS, f"narrowed false, spreads {spreads}"


@case("QA-FX-284", "The dissent travels with the conclusion")
def fx_284(ctx: Ctx) -> Result:
    """Carried on the chain, not only in a column. A final weight whose
    dissent nobody can find is one that looks unanimous — and a reader of the
    parameter set is the person who most needs to know somebody objected."""
    urn = _model(ctx)
    reference = _reference(_open(ctx, urn))
    if not reference:
        return BLOCKED, "the elicitation could not be opened"
    if _respond(ctx, reference, "person/a", 10.0).status_code >= 400:
        return BLOCKED, "a response failed"
    if _respond(ctx, reference, "person/b", 90.0,
                dissented=True).status_code >= 400:
        return BLOCKED, "the dissenting response failed"
    got = _conclude(ctx, reference)
    if got.status_code >= 400:
        return BLOCKED, f"the conclusion failed: {got.text[:140]}"
    engine = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    nodes = [n for n in engine.repo.many()
             if n.get("kind") == "elicitation_concluded"]
    mine = [n for n in nodes
            if reference in f"{n.get('payload') or {}}"]
    if not mine:
        return FAIL, "the conclusion wrote no evidence node"
    payload = mine[-1].get("payload") or {}
    if "person/b" not in f"{payload.get('dissent')}":
        return FAIL, (f"the dissenting panellist is not on the chain: "
                      f"{payload.get('dissent')}")
    reading = got.json() or {}
    if "person/b" not in f"{reading}":
        return FAIL, ("the conclusion reading does not carry the dissent, so "
                      "a reader of the parameter set sees a unanimous number")
    return PASS, f"dissent {payload.get('dissent')} on the chain and in the reading"
