"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — model uses: what a model is actually FOR, declared separately from
what it is.

`declared_use` is the string a warrant grant carries, which is what lets a
grant and a use be matched — a model running for a purpose nobody declared is
the shape of finding a supervisor opens with. The vocabulary around it is
deliberately open: "a closed list would be this platform having an opinion
about how a bank divides itself up".
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

U = "/api/v1/model-uses"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("mu")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return f"maya://model/{name}"


def _declare(ctx: Ctx, urn=None, **over):
    body = {"urn": urn or _model(ctx), "declared_use": "credit_decision",
            "name": "retail origination scorecard", "owner": "owner",
            "purpose": "decides retail applications", "product": "mortgages",
            "legal_entity": "LE-US-01", "geography": "US", "channel": "branch"}
    body.update(over)
    return ctx.api.post(U, json=body, auth=ctx.people["owner"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-GOV-6000", "A use with no declared_use")
def gov_6000(ctx: Ctx) -> Result:
    """The string a grant carries. Without it a use and a warrant can never
    be matched, and "running for a purpose nobody declared" becomes
    unanswerable."""
    got = _declare(ctx, declared_use="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a use was declared with no declared_use, so no grant "
                      "can ever be matched to it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-6001", "A use with no name or no owner")
def gov_6001(ctx: Ctx) -> Result:
    """"A use with no name is a row nobody will read", and an unowned use is
    one nobody reconciles."""
    for field in ("name", "owner"):
        got = _declare(ctx, **{field: "   "})
        if got.status_code >= 500:
            return FAIL, f"{field}: {got.status_code}"
        if got.status_code < 400:
            return FAIL, f"a use was declared with no {field}"
    return PASS, "both name and owner required"


@case("QA-GOV-6002", "A use whose window ends before it starts")
def gov_6002(ctx: Ctx) -> Result:
    """A use that was never in effect is a row that reads as a period of
    operation."""
    import time
    now = time.time()
    got = _declare(ctx, effective_from=now, effective_to=now - 86400)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a use was declared that ended before it began"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-6003", "The business vocabulary is deliberately open")
def gov_6003(ctx: Ctx) -> Result:
    """"A closed list would be this platform having an opinion about how a
    bank divides itself up." Product, geography and channel are the firm's
    own words."""
    got = _declare(ctx, product="islamic finance", geography="MENA",
                   channel="agent network")
    if got.status_code >= 400:
        return FAIL, (f"a firm's own product, geography and channel were "
                      f"refused '{code_of(got)}'; the platform is deciding "
                      f"how a bank divides itself up")
    return PASS, "the firm's own vocabulary is accepted"


@case("QA-GOV-6004", "A use against a model that does not exist")
def gov_6004(ctx: Ctx) -> Result:
    got = _declare(ctx, urn="maya://model/qa.never")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a use was declared against a model nobody registered"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-GOV-6005", "Retire a use with no reason")
def gov_6005(ctx: Ctx) -> Result:
    """A use stopping is a fact about the business, and why is what somebody
    reads when reconciling next year."""
    made = _declare(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    use_id = (made.json() or {}).get("id")
    got = ctx.api.post(f"{U}/{use_id}/retire", json={"reason": "   "},
                       auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a use was retired with no reason recorded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-6006", "Retire a use twice")
def gov_6006(ctx: Ctx) -> Result:
    made = _declare(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    use_id = (made.json() or {}).get("id")
    if ctx.api.post(f"{U}/{use_id}/retire", json={"reason": "withdrawn"},
                    auth=ctx.people["owner"]).status_code >= 400:
        return BLOCKED, "the first retire failed"
    again = ctx.api.post(f"{U}/{use_id}/retire", json={"reason": "again"},
                         auth=ctx.people["owner"])
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "a retired use was retired again"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-GOV-6007", "A lapsed use is reported, not deleted")
def gov_6007(ctx: Ctx) -> Result:
    """A use whose window has passed and which nobody retired is the
    interesting case: the model may still be running for it."""
    got = ctx.api.get(f"{U}/lapsed", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if "lapsed" not in body and "count" not in body:
        return FAIL, f"the lapsed report has no shape: {sorted(body)}"
    if body.get("count") is None:
        return FAIL, "the lapsed report carries no count"
    return PASS, f"{body.get('count')} lapsed use(s) reported"


@case("QA-GOV-6008", "A use and a grant are reconcilable")
def gov_6008(ctx: Ctx) -> Result:
    """The point of `declared_use`. A grant running under a use nobody
    declared, or a use with no grant, is what the reconciliation exists to
    show — and it has to show both directions."""
    urn = _model(ctx)
    if _declare(ctx, urn, declared_use="credit_decision").status_code >= 400:
        return BLOCKED, "the use could not be declared"
    # Reconciliation is per model: `urn` is required, because comparing
    # every use against every grant across an estate answers a question
    # nobody asked.
    got = ctx.api.get(f"/api/v1/use-reconciliation?urn={urn}",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    text = str(body).lower()
    if "grant" not in text and "warrant" not in text:
        return FAIL, ("the reconciliation says nothing about grants, so it "
                      "compares uses against nothing")
    if not (body.get("detail") or "").strip():
        return FAIL, "the reconciliation states no conclusion"
    return PASS, str(body.get("detail"))[:100]


@case("QA-GOV-6009", "A use is separate from the model's own purpose")
def gov_6009(ctx: Ctx) -> Result:
    """A model registered for `credit_decision` may be USED in three
    products, two geographies and a channel nobody thought of. Collapsing
    them would make "what is this model for" a single answer when it is a
    list."""
    urn = _model(ctx)
    for product, geography in (("mortgages", "US"), ("cards", "US"),
                               ("mortgages", "CA")):
        made = _declare(ctx, urn, product=product, geography=geography,
                        name=f"{product} in {geography}")
        if made.status_code >= 400:
            return FAIL, (f"a second use of one model was refused "
                          f"'{code_of(made)}': {made.text[:110]}")
    listed = ctx.api.get(f"{U}?urn={urn}", auth=ctx.people["risk"])
    if listed.status_code >= 400:
        return BLOCKED, listed.text[:170]
    rows = (listed.json() or {}).get("uses") or []
    if len(rows) < 3:
        return FAIL, (f"three uses were declared and {len(rows)} came back, "
                      f"so a model's uses are not a list")
    return PASS, f"{len(rows)} uses of one model"
