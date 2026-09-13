"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the platform's own machine assistance.

MAYA uses a model to help write things, and the rules it applies to itself are
the rules it applies to a bank's models. Two tiers only: **A**, where a formal
oracle checks the output, and **B**, where every claim cites evidence and a
person approves it. There is deliberately no Tier C — a capability whose
output can be neither checked nor grounded is advisory, and advisory AI is a
person using a chat window.
"""
from __future__ import annotations

from tools.qa.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, expect_accepted,
                                       expect_refused)


def _capability(ctx: Ctx, **over) -> dict:
    body = {"capability_key": ctx.unique("cap"), "tier": "B",
            "base_model": "qa-model", "description": "a QA capability",
            "owner": "owner", "prompt_digest": "sha256:" + "0" * 64}
    body.update(over)
    return body


def _register(ctx: Ctx, **over):
    return ctx.api.post("/api/v1/assist/capabilities",
                        json=_capability(ctx, **over))


@case("QA-PLT-180", "Register a Tier C capability")
def plt_180(ctx: Ctx) -> Result:
    return expect_refused(_register(ctx, tier="C"),
                          "advisory_not_registrable")


@case("QA-PLT-181", "Register with tier 'c', lower case")
def plt_181(ctx: Ctx) -> Result:
    """The same mistake deserves the same answer.

    `tier == "C"` is case-sensitive, so a lower-case `c` fell through to
    `unknown_tier` — "expected A or B" — and the caller never learned that C
    is a deliberate refusal with a reason behind it.
    """
    return expect_refused(_register(ctx, tier="c"),
                          "advisory_not_registrable")


@case("QA-PLT-182", "Tier A registered without an oracle")
def plt_182(ctx: Ctx) -> Result:
    return expect_refused(_register(ctx, tier="A"), "oracle_required")


@case("QA-PLT-183", "Tier C and a bogus oracle together")
def plt_183(ctx: Ctx) -> Result:
    """The ORDER of the checks is the case. Being told the oracle is unknown
    would send somebody to find a real one for a tier that cannot be
    registered at all."""
    return expect_refused(_register(ctx, tier="C", oracle_key="no-such"),
                          "advisory_not_registrable")


@case("QA-PLT-184", "A capability naming an oracle that does not exist")
def plt_184(ctx: Ctx) -> Result:
    return expect_refused(_register(ctx, tier="A", oracle_key="no-such"),
                          "unknown_oracle")


@case("QA-PLT-186", "review_sample outside 0..1")
def plt_186(ctx: Ctx) -> Result:
    """A review sample is a fraction of generations a person checks. 1.5 is
    not a fraction and -1 means nobody checks anything — and a negative one
    reads, in every screen that shows it, as a control that is switched on."""
    for value in (1.5, -1.0):
        got = _register(ctx, review_sample=value)
        if got.status_code < 400:
            return FAIL, (f"review_sample={value} was accepted; a sample "
                          f"outside 0..1 is not a sample")
    return PASS, "both refused"


@case("QA-PLT-187", "A Tier B capability registers with an oracle it does not need")
def plt_187(ctx: Ctx) -> Result:
    """Not a refusal: a Tier B capability may name an oracle as extra
    assurance. What must not happen is a 500."""
    got = _register(ctx, tier="B", oracle_key="no-such")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-PLT-188", "A valid Tier B capability")
def plt_188(ctx: Ctx) -> Result:
    return expect_accepted(_register(ctx), status=201)


@case("QA-PLT-189", "Draft against a subject with no evidence at all")
def plt_189(ctx: Ctx) -> Result:
    made = _register(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    key = made.json().get("capability_key") or made.json().get("key")
    return expect_refused(
        ctx.api.post("/api/v1/assist/drafts",
                     json={"capability_key": key, "subject_type": "model",
                           "subject_id": "qa-nothing-here",
                           "instruction": "summarise"}),
        "nothing_to_ground", "not_found", "registry_refused")


@case("QA-PLT-190", "A generation whose claims cite nothing")
def plt_190(ctx: Ctx) -> Result:
    made = _register(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    key = made.json().get("capability_key") or made.json().get("key")
    return expect_refused(
        ctx.api.post("/api/v1/assist/generations",
                     json={"capability_key": key, "subject_type": "model",
                           "subject_id": "qa-nothing-here",
                           "output": {"text": "the model is fine"},
                           "claims": [{"text": "the model is fine"}],
                           "known_evidence": []}),
        "nothing_grounded", "nothing_to_ground", "not_found",
        "registry_refused")


@case("QA-PLT-191", "Use a suspended capability")
def plt_191(ctx: Ctx) -> Result:
    made = _register(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    key = made.json().get("capability_key") or made.json().get("key")
    stopped = ctx.api.post(f"/api/v1/assist/capabilities/{key}/suspend",
                           json={"reason": "QA"})
    if stopped.status_code >= 400:
        return BLOCKED, f"could not suspend: {stopped.status_code}"
    return expect_refused(
        ctx.api.post("/api/v1/assist/drafts",
                     json={"capability_key": key, "subject_type": "model",
                           "subject_id": "qa-x", "instruction": "summarise"}),
        "capability_inactive", "nothing_to_ground", "not_found")


@case("QA-PLT-192", "The two tiers are the whole vocabulary")
def plt_192(ctx: Ctx) -> Result:
    """Published, so a reader can see that C is absent by design rather than
    by omission."""
    from core.assist.common import TIERS
    if set(TIERS) != {"A", "B"}:
        return FAIL, f"the tiers are {TIERS}, not A and B"
    return PASS, "A and B; C is a refusal, not a tier"
