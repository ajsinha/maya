"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — baselining an estate that already exists.

A bank does not start with an empty register. The baseline import takes what
is already running, marks it **baselined rather than draft** — the register
must never imply that historical evidence was asserted when it was not — and
computes each model's compliance DEBT from the gaps the register can see.

**The burn-down is a measurement, not a self-report.** An item closes because
the evidence is there, not because somebody said it was; and the importer's
own declaration of what is missing is ignored, because an importer who
under-declares would set the programme's own baseline.

Debt and breach are counted apart everywhere. Debt is accepted; a breach is
debt that ran out of time, and conflating them lets a programme report
progress by letting the clock run.
"""
from __future__ import annotations

import time

from core.baseline.common import DEFAULT_EXPIRY_MONTHS
from core.baseline.gaps import GAPS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

B = "/api/v1/baseline"
M = "/api/v1/models"
DAY = 86400.0


def _spec(ctx: Ctx, **over) -> dict:
    name = ctx.unique("bl")
    body = {"urn": f"maya://model/{name}", "name": name,
            "model_class": "logistic", "domain": "credit",
            "owner": "person/owner", "legal_entity": "LE-US-01",
            "purpose": "credit_decision", "tier": 3}
    body.update(over)
    return body


def _import(ctx: Ctx, *specs, source: str = "legacy-inventory", **over):
    body = {"source": source, "models": list(specs), "note": "QA batch"}
    body.update(over)
    return ctx.api.post(f"{B}/imports", json=body, auth=ctx.people["risk"])


def _debt(ctx: Ctx, urn: str) -> dict:
    got = ctx.api.get(f"{B}/debt?urn={urn}", auth=ctx.people["risk"])
    return got.json() if got.status_code < 400 else {}


def _reconcile(ctx: Ctx, urn: str):
    return ctx.api.post(f"{B}/reconcile?urn={urn}", auth=ctx.people["risk"])


@case("QA-AM-394", "Import an empty models list")
def am_394(ctx: Ctx) -> Result:
    """An import of nothing that reported success would put a batch in the
    register saying an inventory had been taken when none had."""
    got = _import(ctx)
    outcome = refused_by_the_control(got, "an import of no models")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "nothing_to_import":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'nothing_to_import'"


@case("QA-AM-392", "Import a batch where one row is already registered")
def am_392(ctx: Ctx) -> Result:
    """One bad row must not stop 1,199. The skipped row is reported with its
    reason rather than dropped, because an import that quietly covers fewer
    models than the inventory is the thing a baseline exists to prevent."""
    first = _spec(ctx)
    if _import(ctx, first).status_code >= 400:
        return BLOCKED, "the first import failed"
    second = _spec(ctx)
    got = _import(ctx, first, second)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — one already-registered row "
                      f"stopped the whole batch")
    body = got.json() or {}
    skipped = body.get("skipped") or []
    if len(skipped) != 1:
        return FAIL, f"{len(skipped)} row(s) skipped, expected 1"
    if first["urn"] not in f"{skipped[0]}":
        return FAIL, f"the skipped row is not named: {skipped[0]}"
    if not (skipped[0].get("reason") or "").strip():
        return FAIL, "the row was skipped with no reason recorded"
    if body.get("models") != 1:
        return FAIL, f"the batch counts {body.get('models')} model(s)"
    return PASS, "1 imported, 1 skipped with a reason"


@case("QA-AM-393", "Import the identical batch twice")
def am_393(ctx: Ctx) -> Result:
    """Re-running an inventory load is the ordinary case. Every row skips as
    already registered, and the second batch must not raise a second set of
    debt against models that already carry it."""
    spec = _spec(ctx)
    first = _import(ctx, spec)
    if first.status_code >= 400:
        return BLOCKED, f"the first import failed: {first.text[:140]}"
    was = _debt(ctx, spec["urn"])
    got = _import(ctx, spec)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — re-running an inventory "
                      f"load fails rather than skipping")
    body = got.json() or {}
    if body.get("models"):
        return FAIL, f"the second import registered {body['models']} model(s)"
    if len(body.get("skipped") or []) != 1:
        return FAIL, f"the repeat row is not reported as skipped: {body}"
    now = _debt(ctx, spec["urn"])
    if len(now.get("items") or []) != len(was.get("items") or []):
        return FAIL, (f"the second import raised more debt: "
                      f"{len(was.get('items') or [])} -> "
                      f"{len(now.get('items') or [])}")
    return PASS, (f"every row skipped, and the debt is unchanged at "
                  f"{len(now.get('items') or [])} item(s)")


@case("QA-AM-405", "An importer who under-declares by naming two gaps")
def am_405(ctx: Ctx) -> Result:
    """The declaration is ignored and the gaps are COMPUTED. An importer who
    could declare its own debt would set the programme's baseline, and the
    burn-down would measure whatever the importer felt like admitting."""
    spec = _spec(ctx, gaps=["owner", "purpose"], debt=["owner"])
    got = _import(ctx, spec)
    if got.status_code >= 400:
        return BLOCKED, f"the import failed: {got.text[:140]}"
    imported = (got.json() or {}).get("imported") or []
    if not imported:
        return BLOCKED, "nothing was imported"
    computed = imported[0].get("debt") or []
    if sorted(computed) == ["owner"]:
        return FAIL, ("the importer's declared debt was taken as the debt: an "
                      "importer that names its own gaps sets the programme's "
                      "baseline")
    known = {g.key for g in GAPS}
    if not set(computed) <= known:
        return FAIL, f"debt was raised for gaps that are not gaps: {computed}"
    return PASS, (f"{len(computed)} gap(s) computed from the register, not "
                  f"the {2} the importer declared")


@case("QA-AM-403", "Plan a debt item with an empty plan")
def am_403(ctx: Ctx) -> Result:
    """A debt item needs a dated plan to close it. *Will fix* is not a plan,
    and neither is whitespace."""
    spec = _spec(ctx, owner="")
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    items = _debt(ctx, spec["urn"]).get("items") or []
    if not items:
        return BLOCKED, "the import raised no debt to plan against"
    got = ctx.api.post(f"{B}/debt/{items[0]['id']}/plan",
                       json={"plan": "   "}, auth=ctx.people["risk"])
    outcome = refused_by_the_control(got, "a debt item planned with nothing")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "plan_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'plan_required' on whitespace"


@case("QA-AM-398", "Reconcile twice")
def am_398(ctx: Ctx) -> Result:
    """Safe to run on a schedule: it only makes the stored position agree
    with what the register can already see. The second run must close
    nothing, or a nightly job reports progress every night."""
    spec = _spec(ctx, owner="")
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    first = _reconcile(ctx, spec["urn"])
    if first.status_code >= 400:
        return BLOCKED, f"the first reconcile failed: {first.text[:140]}"
    second = _reconcile(ctx, spec["urn"])
    if second.status_code >= 400:
        return FAIL, f"the second reconcile failed: {code_of(second)}"
    body = second.json() or {}
    if body.get("closed"):
        return FAIL, (f"a second reconcile closed {len(body['closed'])} more "
                      f"item(s) with nothing having changed")
    if body.get("breached"):
        return FAIL, (f"a second reconcile breached {len(body['breached'])} "
                      f"item(s) with nothing having changed")
    return PASS, f"nothing closed, nothing breached, {body.get('remaining')} left"


@case("QA-AM-400", "A Tier 1 `owner` gap at 18 months and one day")
def am_400(ctx: Ctx) -> Result:
    """Past its date, debt stops being debt. The Tier 1 window is 18 months,
    and the expiry raises a finding at the GAP's own materiality — an owner
    gap is Critical, so the breach is Critical rather than a generic
    medium."""
    debts = ctx.ui.app.state.ctx.get("debts")
    if debts is None:
        return BLOCKED, "no debt register is wired"
    spec = _spec(ctx, owner="", tier=1)
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    items = [i for i in (_debt(ctx, spec["urn"]).get("items") or [])
             if i.get("gap_key") == "owner"]
    if not items:
        return BLOCKED, "no owner debt was raised"
    item = items[0]
    months = DEFAULT_EXPIRY_MONTHS[1]
    raised = item["raised_at"]
    expected = raised + months * 30 * DAY
    if abs((item["expires_at"] or 0) - expected) > DAY:
        return FAIL, (f"a tier 1 item expires in "
                      f"{((item['expires_at'] or 0) - raised) / (30 * DAY):.0f} "
                      f"months rather than {months}")
    debts.debts.set({"expires_at": time.time() - DAY}, id=item["id"])
    got = _reconcile(ctx, spec["urn"])
    if got.status_code >= 400:
        return BLOCKED, f"the reconcile failed: {got.text[:140]}"
    breached = (got.json() or {}).get("breached") or []
    if not breached:
        return FAIL, ("an item a day past its expiry was not breached, so "
                      "debt never stops being debt")
    if breached[0].get("status") != "breached":
        return FAIL, f"the item reads '{breached[0].get('status')}'"
    if not breached[0].get("finding_id"):
        return FAIL, ("the debt expired into a breach and raised no finding, "
                      "so the breach is a status nobody is told about")
    return PASS, f"{months} months and a day: breached, with a finding"


@case("QA-AM-401", "The same gap at exactly 18 months")
def am_401(ctx: Ctx) -> Result:
    """The boundary. `expires_at < now` skips, so the item is still debt on
    the day it expires — the same exclusive boundary the ageing and extension
    windows use."""
    debts = ctx.ui.app.state.ctx.get("debts")
    if debts is None:
        return BLOCKED, "no debt register is wired"
    spec = _spec(ctx, owner="", tier=1)
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    items = [i for i in (_debt(ctx, spec["urn"]).get("items") or [])
             if i.get("gap_key") == "owner"]
    if not items:
        return BLOCKED, "no owner debt was raised"
    # `reconcile` reads the wall clock directly rather than taking a `now`,
    # unlike ageing, escalation, conditions, the triggers and the scheduler —
    # so "exactly at the expiry" cannot be held still. What CAN be shown is
    # that the comparison is `<` and not `<=`: an item expiring a second from
    # now is still debt.
    debts.debts.set({"expires_at": time.time() + 1.0}, id=items[0]["id"])
    got = _reconcile(ctx, spec["urn"])
    if got.status_code >= 400:
        return BLOCKED, f"the reconcile failed: {got.text[:140]}"
    if (got.json() or {}).get("breached"):
        return FAIL, ("an item that has not reached its expiry is already a "
                      "breach, so the window is shorter than it is written")
    import inspect
    source = inspect.getsource(type(debts).reconcile)
    if "expires_at" in source and "<" in source and "<=" not in source:
        return PASS, ("still debt up to its expiry; the comparison is `<`, so "
                      "the boundary itself is inside the window")
    return FAIL, ("the expiry comparison is not a strict `<`, so an item is "
                  "a breach on the day it is merely due")


@case("QA-AM-402", "Debt and breach on one dashboard")
def am_402(ctx: Ctx) -> Result:
    """Counted apart everywhere. Debt was accepted at import; a breach is
    debt that ran out of time. A dashboard that added them would let a
    programme report progress by letting the clock run."""
    debts = ctx.ui.app.state.ctx.get("debts")
    if debts is None:
        return BLOCKED, "no debt register is wired"
    spec = _spec(ctx, owner="", purpose="", tier=1)
    if _import(ctx, spec).status_code >= 400:
        return BLOCKED, "the import failed"
    items = _debt(ctx, spec["urn"]).get("items") or []
    if len(items) < 2:
        return BLOCKED, f"only {len(items)} debt item(s) were raised"
    debts.debts.set({"expires_at": time.time() - DAY}, id=items[0]["id"])
    if _reconcile(ctx, spec["urn"]).status_code >= 400:
        return BLOCKED, "the reconcile failed"
    status = _debt(ctx, spec["urn"])
    blob = f"{status}"
    if "breach" not in blob:
        return FAIL, (f"the model's debt reading does not mention a breach at "
                      f"all after one item expired: {blob[:160]}")
    portfolio = ctx.api.get(B, auth=ctx.people["risk"])
    if portfolio.status_code >= 400:
        return BLOCKED, f"the burn-down answered {portfolio.status_code}"
    book = portfolio.json() or {}
    if "breached" not in f"{book}" and "breaches" not in f"{book}":
        return FAIL, ("the burn-down counts no breaches separately, so debt "
                      "that ran out of time is still reported as debt")
    return PASS, "debt and breach appear apart on the model and the burn-down"


@case("QA-AM-404", "Burn-down over an estate with nothing baselined")
def am_404(ctx: Ctx) -> Result:
    """Zero raised, and no ratio inverted into a division by zero. A
    programme with nothing baselined must not read as 100% complete."""
    engine = ctx.ui.app.state.ctx.get("baseline")
    if engine is None:
        return BLOCKED, "no baseline importer is wired"

    class EmptyRepo:
        @staticmethod
        def many(**_where):
            return []

    class EmptyRegister:
        """A debt register holding nothing. `portfolio` reaches through to
        `debts.debts`, so the stand-in has to have that shape."""

        debts = EmptyRepo()

    was_imports, engine.imports = engine.imports, EmptyRepo()
    was_debts, engine.debts = engine.debts, EmptyRegister()
    try:
        book = engine.portfolio()
    except ZeroDivisionError:
        return FAIL, ("the burn-down divides by zero over an estate with "
                      "nothing baselined")
    finally:
        engine.imports, engine.debts = was_imports, was_debts
    if book.get("burn_down"):
        return FAIL, (f"an estate with nothing baselined reports a burn-down "
                      f"of {book['burn_down']}, which reads as progress")
    if book.get("debt_raised") or book.get("models_baselined"):
        return FAIL, f"an empty baseline counts models or debt: {book}"
    if "nothing has been baselined" not in (book.get("detail") or ""):
        return FAIL, (f"the burn-down over nothing does not say so: "
                      f"{book.get('detail')}")
    return PASS, f"0 raised, burn-down {book['burn_down']}, and it says why"
