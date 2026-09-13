"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — baselining a legacy inventory.

The day a firm turns this on it has 1,200 models and no evidence for any of
them. The register must not imply that historical evidence was asserted when
it was not, and must not block everything that is already running. Both are
true at once only if `baselined` is a real state with real debt attached, so
these cases are about whether the debt is honest.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

BASE = "/api/v1/baseline"
M = "/api/v1/models"


def _spec(ctx: Ctx, **over) -> dict:
    name = ctx.unique("bl")
    spec = {"urn": f"maya://model/{name}", "name": name,
            "model_class": "logistic", "domain": "credit", "owner": "owner",
            "legal_entity": "LE-US-01", "purpose": "credit_decision"}
    spec.update(over)
    return spec


def _import(ctx: Ctx, *specs, source: str = "legacy-inventory"):
    return ctx.api.post(f"{BASE}/imports",
                        json={"source": source, "models": list(specs),
                              "note": "QA"})


def _life(ctx: Ctx, name: str) -> dict:
    got = ctx.api.get(f"{M}/{name}")
    return (got.json() or {}).get("lifecycle") or {} if got.status_code < 400 \
        else {}


@case("QA-GOV-024", "Amend a baselined record")
def gov_024(ctx: Ctx) -> Result:
    """`amend` is reachable only from `attested`. A baselined record was
    never attested, so amending one would be a route out of an immutability
    that was never entered."""
    spec = _spec(ctx)
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    return refused_by_the_control(
        ctx.api.post(f"{M}/{spec['name']}/amend",
                     json={"reason": "qa", "scope": []}),
        "a baselined record was amended, so it left an immutability it was "
        "never in")


@case("QA-GOV-025", "Retire a baselined record with open debt")
def gov_025(ctx: Ctx) -> Result:
    """Retiring is how a firm gets a legacy model off the books, so open debt
    must not block it — but the debt has to survive the retirement or the
    inventory loses what it owed."""
    spec = _spec(ctx)
    made = _import(ctx, spec)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    owed = ctx.api.get(f"{BASE}/debt")
    before = owed.text.count(spec["urn"])
    got = ctx.api.post(f"{M}/{spec['name']}/retire", json={"reason": "legacy"})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' while debt is open"
    after = ctx.api.get(f"{BASE}/debt").text.count(spec["urn"])
    if before and not after:
        return FAIL, ("retiring a baselined model erased its open debt, so "
                      "the inventory no longer records what was owed")
    return PASS, f"retired; {after} debt item(s) still recorded"


@case("QA-GOV-026", "Submit a baselined record with open debt")
def gov_026(ctx: Ctx) -> Result:
    """`submit` names `baselined` as a source, so a legacy model can be
    brought into the governed path. The question is whether it can reach
    `attested` while still owing the evidence it never had."""
    spec = _spec(ctx)
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    name = spec["name"]
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess",
                 json={"exposure": 1e6, "purpose_class": "credit_decision",
                       "feature_count": 12, "interpretable": True,
                       "uses_alternative_data": False})
    got = ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' with debt open"
    owed = ctx.api.get(f"{BASE}/debt").text.count(spec["urn"])
    return PASS, (f"submitted from baselined with {owed} debt item(s) still "
                  f"open — the debt is governance owed, not a gate on the "
                  f"path")


@case("QA-GOV-027", "Import the same legacy model twice")
def gov_027(ctx: Ctx) -> Result:
    """A re-run of the importer must not double the inventory. One bad row
    must not stop the other 1,199 either, so the duplicate is reported as
    skipped rather than failing the batch."""
    spec = _spec(ctx)
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the first import failed"
    again = _import(ctx, spec)
    if again.status_code >= 400:
        return PASS, f"the whole re-run refused '{code_of(again)}'"
    body = again.json()
    if body.get("models"):
        return FAIL, ("a re-run imported the same model again; running the "
                      "importer twice doubles the inventory")
    skipped = body.get("skipped") or []
    if not skipped:
        return FAIL, ("the duplicate was neither imported nor reported as "
                      "skipped, so a re-run says nothing about what it did")
    # The skip carries a `reason` in prose, not a refusal code — this is a
    # per-row report inside a 201, not a refusal, so it reads like one.
    if not all((row.get("reason") or "").strip() for row in skipped):
        return FAIL, f"skipped without saying why: {str(skipped)[:130]}"
    if not all("already in the register" in (row.get("reason") or "")
               for row in skipped):
        return FAIL, f"skipped for the wrong reason: {str(skipped)[:130]}"
    return PASS, f"0 imported, {len(skipped)} skipped, each naming the reason"


@case("QA-GOV-1402", "One bad row does not stop the batch")
def gov_1402(ctx: Ctx) -> Result:
    """The design says so in a comment — "one bad row must not stop 1,199" —
    and a batch importer that fails whole is one nobody can run against a
    real inventory."""
    good, dup = _spec(ctx), _spec(ctx)
    if _import(ctx, dup).status_code >= 400:
        return BLOCKED, "the setup import failed"
    got = _import(ctx, dup, good)
    if got.status_code >= 400:
        return FAIL, (f"a batch with one duplicate failed whole: "
                      f"{got.text[:140]}")
    body = got.json()
    if body.get("models") != 1:
        return FAIL, f"{body.get('models')} imported from a batch of 1 good row"
    if len(body.get("skipped") or []) != 1:
        return FAIL, f"skipped: {body.get('skipped')}"
    return PASS, "1 imported, 1 skipped, batch completed"


@case("QA-GOV-1403", "An import of nothing")
def gov_1403(ctx: Ctx) -> Result:
    return refused_by_the_control(
        _import(ctx),
        "an empty batch was recorded as an import, so the inventory shows a "
        "baselining that happened and covered nothing")


@case("QA-GOV-1404", "A baselined record is not a draft")
def gov_1404(ctx: Ctx) -> Result:
    """The register must never imply that historical evidence was asserted
    when it was not. `draft` says somebody is working on it; `baselined` says
    it is running and undocumented, which is the truth."""
    spec = _spec(ctx)
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    life = _life(ctx, spec["name"])
    if life.get("state") != "baselined":
        return FAIL, (f"an imported legacy model entered at "
                      f"'{life.get('state')}', not 'baselined'")
    if not life.get("meaning"):
        return FAIL, "the state carries no meaning for a reader"
    return PASS, f"baselined: {life['meaning'][:80]}"


@case("QA-GOV-1405", "Every baselined model carries its debt")
def gov_1405(ctx: Ctx) -> Result:
    """A baseline that records no debt is an inventory claiming 1,200 models
    are documented."""
    spec = _spec(ctx)
    made = _import(ctx, spec)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    body = made.json()
    if not body.get("debt_items"):
        return FAIL, ("a legacy model was baselined owing nothing, so the "
                      "inventory reports it as documented")
    gaps = ctx.api.get(f"{BASE}/gaps")
    if gaps.status_code >= 400:
        return BLOCKED, gaps.text[:170]
    named = gaps.json().get("gaps") or []
    if not named:
        return BLOCKED, "no gap catalogue to check the debt against"
    return PASS, (f"{body['debt_items']} debt item(s) against "
                  f"{len(named)} named gaps")


@case("QA-GOV-028", "Record the same debt gap twice against one model")
def gov_028(ctx: Ctx) -> Result:
    """Two open items for one gap is one gap that gets closed twice and
    reported as two."""
    spec = _spec(ctx)
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    debts = ctx.made.get("debts")
    if debts is None:
        app = getattr(getattr(ctx.ui, "app", None), "state", None)
        debts = (getattr(app, "ctx", {}) or {}).get("debts")
    if debts is None:
        return BLOCKED, ("no route raises debt directly, and the service is "
                         "not reachable from this run")
    model = (ctx.api.get(f"{M}/{spec['name']}").json() or {}).get("model") or {}
    # `debts` is the repository attribute on DebtRegister, not `repo`.
    open_items = list(debts.debts.many(model_id=model.get("id")))
    if not open_items:
        return BLOCKED, "the import raised no debt to duplicate"
    gap = open_items[0]["gap_key"]
    from core.baseline.common import BaselineError
    try:
        debts.raise_debt(model["id"], gap, owner="owner", actor="qa")
    except BaselineError as exc:
        if exc.code != "already_recorded":
            return FAIL, f"refused '{exc.code}', not already_recorded"
        return PASS, f"refused 'already_recorded' for gap '{gap}'"
    return FAIL, (f"gap '{gap}' was recorded twice against one model, so it "
                  f"will be closed twice and counted as two")
