"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — overlays: the judgement applied on top of the model's answer.

An overlay is the part of a firm's decision the model did not make, and the
thing a supervisor asks about first. An unmeasured one is the sharpest version
of the problem — nobody can say how much of the answer was the model and how
much was the adjustment — so measurement, not approval, is what this module is
really about.
"""
from __future__ import annotations

from core.overlays.common import DIRECTIONS, KIND_MEANING, KINDS, STATUSES
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

O = "/api/v1/overlays"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("ov")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return f"maya://model/{name}"


def _propose(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "name": ctx.unique("adj"), "kind": KINDS[0],
            "rationale": "the model understates recent defaults",
            "owner": "owner", "direction": DIRECTIONS[0], "basis": {},
            "days": 30}
    body.update(over)
    return ctx.api.post(O, json=body, auth=ctx.people["owner"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-GOV-4800", "An overlay of a kind that is not one")
def gov_4800(ctx: Ctx) -> Result:
    """The kind says what the adjustment touches — a parameter, an output, an
    exclusion, a judgement. An unknown one is an adjustment nobody can
    classify or aggregate."""
    got = _propose(ctx, _model(ctx), kind="a tweak")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "an overlay of an unknown kind was proposed"
    if not any(k in got.text for k in KINDS):
        return FAIL, "the refusal does not name the kinds"
    return PASS, f"refused '{code_of(got)}', naming {len(KINDS)} kinds"


@case("QA-GOV-4801", "An overlay direction that is not one")
def gov_4801(ctx: Ctx) -> Result:
    """`increase`, `decrease` or `either`. The direction is what makes a
    portfolio of overlays addable — an adjustment with no stated direction
    cannot be netted against another."""
    got = _propose(ctx, _model(ctx), direction="sideways")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an overlay with no stated direction was proposed"
    if not any(d in got.text for d in DIRECTIONS):
        return FAIL, "the refusal does not name the directions"
    return PASS, f"refused '{code_of(got)}', naming {DIRECTIONS}"


@case("QA-GOV-4802", "An overlay with no rationale")
def gov_4802(ctx: Ctx) -> Result:
    """An overlay is a departure from what the model said. Without a reason
    it is a number somebody changed."""
    got = _propose(ctx, _model(ctx), rationale="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an overlay was proposed with no reason for it"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4803", "An overlay window past the limit")
def gov_4803(ctx: Ctx) -> Result:
    """An overlay is a temporary judgement. Past the limit it is the model,
    and should be in the model."""
    overlays = ctx.ui.app.state.ctx.get("overlays")
    if overlays is None:
        return BLOCKED, "no overlay register reachable from this run"
    limit = overlays.max_days
    urn = _model(ctx)
    over = _propose(ctx, urn, days=limit + 1)
    if over.status_code >= 500:
        return FAIL, f"{over.status_code}"
    if over.status_code < 400:
        return FAIL, f"a window of {limit + 1} days was accepted"
    at = _propose(ctx, urn, days=limit)
    if at.status_code >= 400 and _reached(at):
        return FAIL, (f"exactly {limit} days was refused '{code_of(at)}'; "
                      f"the limit excludes itself")
    return PASS, f"{limit} accepted, {limit + 1} refused '{code_of(over)}'"


@case("QA-GOV-4804", "An overlay is not active until it is approved")
def gov_4804(ctx: Ctx) -> Result:
    """Proposing is not applying. An overlay that took effect on being
    written down would be a judgement nobody approved."""
    made = _propose(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    body = made.json() or {}
    if body.get("status") != "proposed":
        return FAIL, (f"a proposed overlay is '{body.get('status')}', not "
                      f"'proposed'")
    if body.get("effective_from"):
        return FAIL, "a proposed overlay already has an effective date"
    return PASS, "proposed, not in force"


@case("QA-GOV-4805", "The proposer approves their own overlay")
def gov_4805(ctx: Ctx) -> Result:
    """An adjustment somebody proposed and approved alone is one person
    deciding what the model's answer should have been."""
    made = _propose(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    overlay_id = (made.json() or {}).get("id")
    got = ctx.api.post(f"{O}/{overlay_id}/approve", json={},
                       auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the person who proposed an overlay approved it, so one "
                      "person decided what the model's answer should have "
                      "been")
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-GOV-4806", "Measure an overlay that was never approved")
def gov_4806(ctx: Ctx) -> Result:
    """A measurement of an adjustment nobody applied is a number about
    nothing."""
    made = _propose(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{O}/{(made.json() or {}).get('id')}/measure",
                       json={"period": "2026-Q3", "base_value": 100.0,
                             "adjusted_value": 120.0},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an overlay nobody approved was measured"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4807", "An approved overlay that is never measured")
def gov_4807(ctx: Ctx) -> Result:
    """The sharpest version: an active adjustment nobody has quantified.
    Nothing can say how much of the answer was the model. The disclosure has
    to report it rather than counting it as zero."""
    urn = _model(ctx)
    made = _propose(ctx, urn)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    approved = ctx.api.post(f"{O}/{(made.json() or {}).get('id')}/approve",
                            json={}, auth=ctx.people["risk"])
    if approved.status_code >= 400:
        return BLOCKED, approved.text[:170]
    # `period` is required on the disclosure: an overlay figure with no
    # stated period is a number nobody can put on a return.
    got = ctx.api.get(f"/api/v1/overlay-disclosure?urn={urn}&period=2026-Q3",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    text = got.text.lower()
    if "unmeasured" not in text and "not measured" not in text and \
            "never measured" not in text:
        return FAIL, ("an active overlay nobody measured is not reported as "
                      "unmeasured, so it counts as an adjustment of zero: "
                      + got.text[:130])
    return PASS, "an unmeasured overlay is reported as unmeasured"


@case("QA-GOV-4808", "Close an overlay with no reason")
def gov_4808(ctx: Ctx) -> Result:
    made = _propose(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{O}/{(made.json() or {}).get('id')}/close",
                       json={"status": "withdrawn", "reason": "   "},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an overlay was withdrawn with no reason recorded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4809", "Close an overlay into a status that is not one")
def gov_4809(ctx: Ctx) -> Result:
    """`absorbed` means the judgement went into the model, and it is the
    outcome a supervisor most wants to see. A free-text status would lose
    that distinction."""
    made = _propose(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{O}/{(made.json() or {}).get('id')}/close",
                       json={"status": "finished", "reason": "done"},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an overlay was closed into a status outside the set"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4810", "Every overlay kind says what it means")
def gov_4810(ctx: Ctx) -> Result:
    """The kinds are what a disclosure aggregates over. One with no stated
    meaning is a column on a supervisory return nobody can define."""
    mute = [k for k in KINDS if not (KIND_MEANING.get(k) or "").strip()]
    if mute:
        return FAIL, f"kinds with no meaning: {mute}"
    got = ctx.api.get("/api/v1/overlay-kinds", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    for kind in KINDS:
        if kind not in got.text:
            return FAIL, f"'{kind}' is accepted and not published"
    return PASS, f"{len(KINDS)} kinds, each published with its meaning"


@case("QA-GOV-4811", "The status vocabulary distinguishes absorbed from withdrawn")
def gov_4811(ctx: Ctx) -> Result:
    """Withdrawn means somebody stopped applying it; absorbed means the model
    changed to make it unnecessary. Reporting the second as the first loses
    the only outcome that shows the overlay did its job."""
    for status in ("withdrawn", "absorbed", "expired"):
        if status not in STATUSES:
            return FAIL, f"'{status}' is not a status the register has"
    return PASS, f"{len(STATUSES)} statuses: {', '.join(STATUSES)}"
