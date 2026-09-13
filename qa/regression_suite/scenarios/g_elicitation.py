"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — elicitation: the parameters a panel asserted rather than data
produced.

"A final weight whose dissent nobody can find is a weight that looks
unanimous." That sentence is the module, and the controls around it are about
keeping a number traceable to the disagreement it came out of: a fixed panel,
a facilitator who is not a panellist, and responses that are never
overwritten.
"""
from __future__ import annotations

from core.parameters.elicitation import METHODS, MINIMUM_PANEL
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

E = "/api/v1/elicitations"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
PANEL = ["person/alice", "person/bob", "person/carol"]


def _model(ctx: Ctx) -> str:
    name = ctx.unique("el")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return f"maya://model/{name}"


def _open(ctx: Ctx, urn=None, **over):
    body = {"reference": ctx.unique("ELI"), "urn": urn or _model(ctx),
            "question": "what weight should the qualitative overlay carry",
            "panel": list(PANEL), "facilitator": "person/facilitator",
            "units": "percentage points", "method": sorted(METHODS)[0]}
    body.update(over)
    return ctx.api.post(E, json=body, auth=ctx.people["owner"]), body["reference"]


def _respond(ctx: Ctx, reference: str, panellist: str, value: float, **over):
    body = {"panellist": panellist, "value": value, "confidence": "medium",
            "reasoning": "a QA judgement", "independent": True}
    body.update(over)
    return ctx.api.post(f"{E}/{reference}/respond", json=body,
                        auth=ctx.people["owner"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-FX-5500", "A panel smaller than the minimum")
def fx_5500(ctx: Ctx) -> Result:
    """Two people agreeing is not a panel converging, and the spread of two
    numbers is a number."""
    made, _ = _open(ctx, panel=PANEL[:MINIMUM_PANEL - 1])
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if not _reached(made):
        return BLOCKED, f"answered '{code_of(made)}' — not reached"
    if made.status_code < 400:
        return FAIL, (f"a panel of {MINIMUM_PANEL - 1} was convened, below "
                      f"the minimum of {MINIMUM_PANEL}")
    return PASS, f"refused '{code_of(made)}' below {MINIMUM_PANEL}"


@case("QA-FX-5501", "The facilitator is also a panellist")
def fx_5501(ctx: Ctx) -> Result:
    """"The facilitator sets the question and sees the responses." Somebody
    doing both is running the elicitation and answering it."""
    made, _ = _open(ctx, facilitator=PANEL[0])
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code < 400:
        return FAIL, ("the person running the elicitation is also answering "
                      "it, and sees every other answer before giving theirs")
    return PASS, f"refused '{code_of(made)}'"


@case("QA-FX-5502", "An elicitation with no question")
def fx_5502(ctx: Ctx) -> Result:
    """A panel convened around nothing produces numbers nobody can interpret
    a year later."""
    made, _ = _open(ctx, question="   ")
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code < 400:
        return FAIL, "a panel was convened around no question"
    return PASS, f"refused '{code_of(made)}'"


@case("QA-FX-5503", "A method that is not one")
def fx_5503(ctx: Ctx) -> Result:
    """Delphi, nominal group and workshop differ in whether panellists see
    each other's answers, which is the whole of what makes a spread mean
    something."""
    made, _ = _open(ctx, method="a chat over coffee")
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code < 400:
        return FAIL, "an elicitation ran under a method nobody defined"
    # The vocabulary is in the remediation, not the detail.
    if not any(m in made.text for m in METHODS):
        return FAIL, f"the refusal does not name the methods: {made.text[:140]}"
    return PASS, f"refused '{code_of(made)}', naming {len(METHODS)} methods"


@case("QA-FX-5504", "A second elicitation under one reference")
def fx_5504(ctx: Ctx) -> Result:
    reference = ctx.unique("ELI")
    first, _ = _open(ctx, reference=reference)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again, _ = _open(ctx, reference=reference)
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "two elicitations share one reference"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-FX-5505", "A response from somebody not on the panel")
def fx_5505(ctx: Ctx) -> Result:
    """"The panel is fixed here and cannot be added to mid-round: a new
    member changes the denominator of a spread that has already been partly
    formed." """
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _respond(ctx, reference, "person/stranger", 12.0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("somebody outside the panel answered, changing the "
                      "denominator of a spread already partly formed")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-5506", "A response is never overwritten")
def fx_5506(ctx: Ctx) -> Result:
    """A panellist who could revise their answer after seeing the others is
    not giving an independent one, and the spread stops measuring
    disagreement."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    if _respond(ctx, reference, PANEL[0], 10.0).status_code >= 400:
        return BLOCKED, "the first response failed"
    again = _respond(ctx, reference, PANEL[0], 99.0)
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code >= 400:
        return PASS, f"refused '{code_of(again)}'"
    # Accepted — then the first answer must still be on the record.
    listed = ctx.api.get(f"{E}?reference={reference}", auth=ctx.people["owner"])
    if listed.status_code >= 400:
        return BLOCKED, listed.text[:170]
    if "10.0" not in listed.text and "10" not in listed.text:
        return FAIL, ("a revised response replaced the first, so the spread "
                      "no longer measures the disagreement there was")
    return PASS, "a revision is recorded beside the original, not over it"


@case("QA-FX-5507", "Dissent travels with the concluded value")
def fx_5507(ctx: Ctx) -> Result:
    """"A final weight whose dissent nobody can find is a weight that looks
    unanimous." """
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    for panellist, value, dissented in ((PANEL[0], 10.0, False),
                                        (PANEL[1], 11.0, False),
                                        (PANEL[2], 40.0, True)):
        sent = _respond(ctx, reference, panellist, value,
                        dissented=dissented,
                        reasoning="the overlay is doing far more than that"
                        if dissented else "about right")
        if sent.status_code >= 400:
            return BLOCKED, f"{panellist}: {sent.text[:130]}"
    # Concluding takes `parameter:approve`, which is the second line's — the
    # owner convenes the panel and somebody else records what it arrived at.
    got = ctx.api.post(f"{E}/{reference}/conclude",
                       json={"value": 11.0, "note": "the panel settled"},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    dissent = body.get("dissent")
    if not dissent:
        return FAIL, ("a concluded elicitation with a dissenting panellist "
                      "carries no dissent, so the number looks unanimous")
    if PANEL[2] not in str(dissent):
        return FAIL, f"the dissenter is not named: {dissent}"
    return PASS, f"dissent recorded: {str(dissent)[:80]}"


@case("QA-FX-5508", "Independence is recorded, not required")
def fx_5508(ctx: Ctx) -> Result:
    """"In a small firm the only person who genuinely understands the model
    is often the person who built it, and refusing would push the elicitation
    off the platform entirely." Recording it keeps the fact where a reviewer
    can see it."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _respond(ctx, reference, PANEL[0], 10.0, independent=False)
    if got.status_code >= 400:
        return FAIL, (f"a non-independent response was refused "
                      f"'{code_of(got)}', which pushes the elicitation off "
                      f"the platform rather than recording the fact")
    listed = ctx.api.get(f"{E}?reference={reference}", auth=ctx.people["owner"])
    if listed.status_code < 400 and "independent" not in listed.text:
        return FAIL, "the response is stored without its independence flag"
    return PASS, "accepted and flagged as not independent"


@case("QA-FX-5509", "Convergence is readable before concluding")
def fx_5509(ctx: Ctx) -> Result:
    """A facilitator deciding whether to run another round needs the spread,
    and discovering it only at the conclusion is discovering it too late."""
    made, reference = _open(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    for panellist, value in zip(PANEL, (10.0, 11.0, 40.0)):
        if _respond(ctx, reference, panellist, value).status_code >= 400:
            return BLOCKED, f"{panellist} could not respond"
    got = ctx.api.get(f"{E}/{reference}/convergence", auth=ctx.people["owner"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if not (body.get("detail") or "").strip():
        return FAIL, "the convergence report says nothing"
    return PASS, str(body.get("detail"))[:100]


@case("QA-FX-5510", "Every method says how it differs")
def fx_5510(ctx: Ctx) -> Result:
    """The methods differ in whether panellists see each other's answers. A
    method with no stated meaning is a spread nobody can interpret."""
    if hasattr(METHODS, "values"):
        mute = [k for k, v in METHODS.items() if not (v or "").strip()]
        if mute:
            return FAIL, f"methods with no meaning: {mute}"
    got = ctx.api.get(f"{E}/methods", auth=ctx.people["owner"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    for method in METHODS:
        if method not in got.text:
            return FAIL, f"'{method}' is accepted and not published"
    return PASS, f"{len(METHODS)} methods published"
