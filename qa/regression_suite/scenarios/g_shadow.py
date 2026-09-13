"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — shadow running: a model answering alongside the live one.

The refusal worth the whole module is that a shadow grant may not use a
PRODUCTION declared use — because "that is how a shadow answer reaches a
decision: not by anybody deciding to use it, but by nothing being able to tell
the two apart". MAYA is not in the serving path, so `share` is an attestation
rather than a control, and the platform says which.
"""
from __future__ import annotations

from core.execution.shadow import MAX_SHADOW_DAYS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

S = "/api/v1/shadow"
U = "/api/v1/model-uses"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("sd")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return f"maya://model/{name}"


def _use(ctx: Ctx, urn: str, declared_use: str):
    return ctx.api.post(U, json={"urn": urn, "declared_use": declared_use,
                                 "name": "the live use", "owner": "owner",
                                 "purpose": "decides applications"},
                        auth=ctx.people["owner"])


def _shadow(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "environment": "prod", "principal": "svc-pricing",
            "declared_use": "shadow_evaluation",
            "mirrors": "maya://model/the-live-one", "share": 0.1}
    body.update(over)
    return ctx.api.post(S, json=body, auth=ctx.people["owner"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-FX-6100", "A shadow under a production declared use")
def fx_6100(ctx: Ctx) -> Result:
    """The refusal the whole module exists for. If nothing can tell a shadow
    answer from a live one at the point of use, the shadow reaches a
    decision without anybody deciding it should."""
    urn = _model(ctx)
    if _use(ctx, urn, "credit_decision").status_code >= 400:
        return BLOCKED, "the production use could not be declared"
    got = _shadow(ctx, urn, declared_use="credit_decision")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a shadow grant was issued under a production declared "
                      "use, so nothing can tell a shadow answer from a live "
                      "one at the point of use")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-6101", "A shadow under its own declared use")
def fx_6101(ctx: Ctx) -> Result:
    """The refusal has to admit the legitimate case, or nothing can be
    shadowed at all."""
    urn = _model(ctx)
    if _use(ctx, urn, "credit_decision").status_code >= 400:
        return BLOCKED, "the production use could not be declared"
    got = _shadow(ctx, urn, declared_use="shadow_evaluation")
    if got.status_code >= 400:
        return FAIL, (f"a shadow under its own declared use was refused "
                      f"'{code_of(got)}': {got.text[:120]}")
    return PASS, "a distinct declared use is accepted"


@case("QA-FX-6102", "A shadow that mirrors nothing")
def fx_6102(ctx: Ctx) -> Result:
    """A shadow with nothing to compare against is a second model running in
    production under another name."""
    got = _shadow(ctx, _model(ctx), mirrors="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a shadow grant was issued mirroring nothing, which is "
                      "a second model in production under another name")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-6103", "A share outside the unit interval")
def fx_6103(ctx: Ctx) -> Result:
    """A share is a proportion. Zero is not a shadow and more than one is
    not a share."""
    urn = _model(ctx)
    accepted = []
    for share in (0.0, -0.1, 1.5, 100):
        got = _shadow(ctx, urn, share=share)
        if got.status_code >= 500:
            return FAIL, f"share {share}: {got.status_code}"
        if got.status_code < 400:
            accepted.append(share)
    if accepted:
        return FAIL, f"these shares were accepted: {accepted}"
    whole = _shadow(ctx, urn, share=1.0)
    if whole.status_code >= 400 and _reached(whole):
        return FAIL, (f"a share of 1.0 was refused '{code_of(whole)}'; "
                      f"mirroring every request is a legitimate shadow")
    return PASS, "0, -0.1, 1.5 and 100 refused; 1.0 accepted"


@case("QA-FX-6104", "The share is an attestation, not a control")
def fx_6104(ctx: Ctx) -> Result:
    """MAYA is not in the serving path — somebody else's router performs the
    mirror — and a platform reporting a share it cannot observe would be
    claiming to enforce a split it never sees."""
    import inspect

    from core.execution import shadow
    doc = " ".join((inspect.getdoc(shadow) or "").split())
    from routes.warrant_routes import ShadowIn
    body = " ".join((inspect.getdoc(ShadowIn) or "").split())
    whole = doc + " " + body
    if "attestation" not in whole:
        return FAIL, ("nothing records that the share is attested rather than "
                      "enforced, so a reader takes it for a control")
    if "serving path" not in whole and "not in the serving" not in whole:
        return FAIL, "it does not say the platform is outside the serving path"
    return PASS, "the share is stated to be an attestation"


@case("QA-FX-6105", "A shadow grant has an end")
def fx_6105(ctx: Ctx) -> Result:
    """A shadow with no end is a model running in production that nobody
    calls production."""
    got = _shadow(ctx, _model(ctx))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    ends = body.get("until") or body.get("expires_at") or body.get("ends_at")
    if not ends:
        return FAIL, (f"a shadow grant carries no end date: {sorted(body)}")
    return PASS, f"bounded by default at {MAX_SHADOW_DAYS:g} days"


@case("QA-FX-6106", "An overstaying shadow is reported")
def fx_6106(ctx: Ctx) -> Result:
    """"Temporarily in shadow" is the most durable state in model risk, and
    the register is the only thing that can notice."""
    import inspect

    from core.execution import shadow
    # `ShadowTraffic` — the noun is the traffic, not the running.
    source = inspect.getsource(shadow.ShadowTraffic.status)
    if "overstayed" not in source:
        return FAIL, ("nothing reports a shadow that has outlived its window, "
                      "so 'temporarily in shadow' is never noticed")
    if "MAX_SHADOW_DAYS" not in source:
        return FAIL, "the overstay is judged against no stated limit"
    return PASS, f"an overstay past {MAX_SHADOW_DAYS:g} days is reported"


@case("QA-FX-6107", "The shadow posture is readable")
def fx_6107(ctx: Ctx) -> Result:
    """What is running in shadow, right now, across the estate — the
    question somebody asks after finding one that had been there two
    years."""
    got = ctx.api.get(f"{S}/posture", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if not (body.get("detail") or "").strip():
        return FAIL, ("the shadow posture says nothing, so an estate with no "
                      "shadows and a broken report look the same")
    return PASS, str(body.get("detail"))[:100]


@case("QA-FX-6108", "A shadow against a model that does not exist")
def fx_6108(ctx: Ctx) -> Result:
    got = _shadow(ctx, "maya://model/qa.never")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a shadow was authorised over a model nobody registered"
    return PASS, f"refused '{code_of(got) or got.status_code}'"
