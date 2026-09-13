"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — approval conditions: "yes, but".

A condition attached to an approval is the commonest real governance outcome
and the easiest to lose. The interesting split is `enforced` against
`attested`: one the platform can apply itself, the other it can only ask
somebody to confirm — and a register that reported the second as though it
were the first would be claiming a control it does not have.
"""
from __future__ import annotations

from typing import Optional

from core.lifecycle.conditions import ATTESTED, KINDS, MAX_DAYS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

C = "/api/v1/approval-conditions"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ENFORCED_KIND = next(k for k, v in KINDS.items()
                     if v.get("enforcement") != ATTESTED)
ATTESTED_KIND = next(k for k, v in KINDS.items()
                     if v.get("enforcement") == ATTESTED)


def _model(ctx: Ctx) -> str:
    name = ctx.unique("cd")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return f"maya://model/{name}"


def _parameters(kind: str) -> dict:
    """What a kind's `requires` asks for. Unknown kinds take nothing — an
    unknown one is the case, and looking it up in KINDS raises inside the
    fixture rather than reaching the refusal."""
    filling = {"environments": ["uat"], "calls": 100, "window_hours": 24,
               "amount": 1_000_000.0, "currency": "USD", "share": 0.1}
    needs = (KINDS.get(kind) or {}).get("requires") or ()
    return {key: filling[key] for key in needs if key in filling}


def _attach(ctx: Ctx, urn: str, kind: Optional[str] = None, **over):
    kind = kind or ENFORCED_KIND
    body = {"urn": urn, "kind": kind, "rationale": "a QA condition",
            "days": 30.0, "parameters": _parameters(kind),
            "confirm_every_days": 30.0}
    body.update(over)
    return ctx.api.post(C, json=body, auth=ctx.people["risk"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-GOV-4500", "A condition of a kind that is not one")
def gov_4500(ctx: Ctx) -> Result:
    """The kind decides whether the platform can enforce it. An unknown one
    is a condition nothing applies and nobody confirms."""
    got = _attach(ctx, _model(ctx), kind="be careful")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a condition of an unknown kind was attached"
    if not any(k in got.text for k in KINDS):
        return FAIL, "the refusal does not name the kinds"
    return PASS, f"refused '{code_of(got)}', naming {len(KINDS)} kinds"


@case("QA-GOV-4501", "A condition with no rationale")
def gov_4501(ctx: Ctx) -> Result:
    """"Yes, but" without the but is a yes."""
    got = _attach(ctx, _model(ctx), rationale="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a condition was attached with no reason for it"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4502", "A condition window outside the permitted range")
def gov_4502(ctx: Ctx) -> Result:
    """A condition is a temporary state, not a permanent one. Zero is not a
    window and a year is a second approval nobody gave."""
    urn = _model(ctx)
    accepted = []
    for days in (0, -1, MAX_DAYS + 1, 3650):
        got = _attach(ctx, urn, days=days)
        if got.status_code >= 500:
            return FAIL, f"{days} days: {got.status_code}"
        if got.status_code < 400:
            accepted.append(days)
    inside = _attach(ctx, urn, days=MAX_DAYS)
    if inside.status_code >= 400 and _reached(inside):
        return FAIL, (f"exactly {MAX_DAYS} days was refused "
                      f"'{code_of(inside)}'; the limit excludes itself")
    if accepted:
        return FAIL, f"these windows were accepted: {accepted}"
    return PASS, f"0, -1, {MAX_DAYS + 1} and 3650 refused; {MAX_DAYS} accepted"


@case("QA-GOV-4503", "A condition missing the parameters its kind needs")
def gov_4503(ctx: Ctx) -> Result:
    """Every kind that takes parameters, not a sample. "Without them there is
    nothing to enforce" — a usage cap with no number is a condition that
    reads as a control and is not one."""
    urn = _model(ctx)
    hollow = []
    for kind, spec in KINDS.items():
        needs = spec.get("requires") or ()
        if not needs:
            continue
        for field in needs:
            parameters = {k: v for k, v in _parameters(kind).items()
                          if k != field}
            got = _attach(ctx, urn, kind=kind, parameters=parameters)
            if got.status_code >= 500:
                return FAIL, f"{kind}/{field}: {got.status_code}"
            if got.status_code < 400:
                hollow.append(f"{kind} without {field}")
            elif field not in got.text:
                return FAIL, (f"the refusal for {kind} does not name the "
                              f"missing '{field}': {got.text[:110]}")
    if hollow:
        return FAIL, f"attached with nothing to enforce: {hollow}"
    parameterised = [k for k, v in KINDS.items() if v.get("requires")]
    return PASS, (f"every required parameter of {len(parameterised)} kind(s) "
                  f"refused by name when absent")


@case("QA-GOV-4504", "An enforced condition cannot be confirmed")
def gov_4504(ctx: Ctx) -> Result:
    """Confirmation is for what the platform CANNOT apply. Asking somebody to
    confirm a condition the register already enforces would turn a real
    control into a periodic signature."""
    made = _attach(ctx, _model(ctx), kind=ENFORCED_KIND)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    reference = (made.json() or {}).get("reference")
    got = ctx.api.post(f"{C}/{reference}/confirm", json={"note": "confirmed"},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, (f"an '{ENFORCED_KIND}' condition — which the platform "
                      f"enforces — was satisfied by somebody confirming it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4505", "An attested condition can be confirmed")
def gov_4505(ctx: Ctx) -> Result:
    """The other half. A condition the platform cannot enforce is confirmed
    by a person, and the refusal must admit that or the kind is unusable."""
    made = _attach(ctx, _model(ctx), kind=ATTESTED_KIND)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    reference = (made.json() or {}).get("reference")
    got = ctx.api.post(f"{C}/{reference}/confirm", json={"note": "confirmed"},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"an '{ATTESTED_KIND}' condition could not be "
                      f"confirmed: {got.text[:130]}")
    return PASS, f"'{ATTESTED_KIND}' is confirmed by a person"


@case("QA-GOV-4506", "Discharge with no reason")
def gov_4506(ctx: Ctx) -> Result:
    """Lifting a condition is a governance decision, and the reason is the
    whole record of it."""
    made = _attach(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    reference = (made.json() or {}).get("reference")
    got = ctx.api.post(f"{C}/{reference}/discharge", json={"reason": "   "},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a condition was lifted with no reason recorded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4507", "Discharge twice")
def gov_4507(ctx: Ctx) -> Result:
    made = _attach(ctx, _model(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    reference = (made.json() or {}).get("reference")
    first = ctx.api.post(f"{C}/{reference}/discharge",
                         json={"reason": "no longer needed"},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again = ctx.api.post(f"{C}/{reference}/discharge",
                         json={"reason": "again"}, auth=ctx.people["risk"])
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "a discharged condition was discharged again"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-GOV-4508", "Confirm a discharged condition")
def gov_4508(ctx: Ctx) -> Result:
    """A confirmation arriving after the condition was lifted is a signature
    on something that no longer applies."""
    made = _attach(ctx, _model(ctx), kind=ATTESTED_KIND)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    reference = (made.json() or {}).get("reference")
    if ctx.api.post(f"{C}/{reference}/discharge",
                    json={"reason": "lifted"},
                    auth=ctx.people["risk"]).status_code >= 400:
        return BLOCKED, "the condition could not be discharged"
    got = ctx.api.post(f"{C}/{reference}/confirm", json={"note": "still fine"},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a discharged condition was confirmed"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4509", "Every kind declares how it is enforced")
def gov_4509(ctx: Ctx) -> Result:
    """The split between what the platform applies and what it can only ask
    about is the whole honesty of this feature. A kind that declared neither
    would be reported as a control with nothing behind it."""
    silent = [k for k, v in KINDS.items()
              if not (v.get("enforcement") or "").strip()]
    if silent:
        return FAIL, f"kinds declaring no enforcement: {silent}"
    got = ctx.api.get("/api/v1/condition-kinds", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    published = got.text
    for kind in KINDS:
        if kind not in published:
            return FAIL, f"'{kind}' is enforced and not published"
    if ATTESTED not in published:
        return FAIL, ("the published kinds do not distinguish enforced from "
                      "attested, so a reader cannot tell which the platform "
                      "actually applies")
    return PASS, f"{len(KINDS)} kinds published, each naming its enforcement"
