"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the returns that get sent to a supervisor.

Unlike every other output in this codebase, these leave the building. So a
field the register genuinely does not know — the authorised representative,
the notified body, the serial number of a declaration of conformity — is
emitted as `not_held`, named, counted, and the header says the return is
INCOMPLETE. A firm that files it anyway is making a decision; a firm handed a
full-looking spreadsheet is not.

**The population is derived and published, and so is the exclusion.** Which
models are high-risk is computed from the designations and purpose classes the
register already carries, not from a checkbox somebody ticked at onboarding —
because a checkbox is the field that is wrong. A regulator's first question
about a population of eleven is what happened to the twelfth, so the models
out of scope are listed with the reason they are out.

And no return is a legal opinion: where the reading of Annex III is
contestable the extract names the fact it turned on, so counsel can disagree
with a derivation rather than with a number.
"""
from __future__ import annotations

from core.reporting.returns import DERIVED, HELD, NOT_HELD, RETURNS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

R = "/api/v1/regulatory-returns"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx, **over) -> str:
    name = ctx.unique("rr")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner",
                          **SHAPE, **over}, auth=ctx.people["owner"])
    return urn


def _baselined(ctx: Ctx) -> str:
    """A model with NO purpose, through the only door that still admits one.

    An ordinary registration now refuses a blank purpose, and that is the
    point of the refusal. The baseline import is the deliberate exception: a
    model that arrived from a spreadsheet carries its missing purpose as a
    dated debt rather than being kept off the register, and that population is
    exactly the one an AI Act return has to say something honest about.
    """
    name = ctx.unique("rrb")
    urn = f"maya://model/{name}"
    got = ctx.api.post("/api/v1/baseline/imports",
                       json={"source": "qa-inventory.csv",
                             "models": [{"urn": urn, "name": name,
                                         "owner": "person/o", "tier": 2}]},
                       auth=ctx.people["risk"])
    return urn if got.status_code < 400 else ""


def _extract(ctx: Ctx, name: str) -> dict:
    got = ctx.api.get(f"{R}/{name}", auth=ctx.people["risk"])
    return got.json() if got.status_code < 400 else {"_status": got.status_code,
                                                     "_code": code_of(got)}


@case("QA-AM-368", "Catalogue before running anything")
def am_368(ctx: Ctx) -> Result:
    """Each return declares what it cannot answer BEFORE anybody runs it, so
    a firm knows what it is committing to file rather than discovering the
    gaps in the spreadsheet."""
    got = ctx.api.get(R, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the catalogue answered {got.status_code}"
    body = got.json() or {}
    returns = body.get("returns") or []
    if len(returns) != len(RETURNS):
        return FAIL, (f"the catalogue lists {len(returns)} of "
                      f"{len(RETURNS)} returns")
    for row in returns:
        if "not_held" not in row:
            return FAIL, (f"'{row.get('return')}' does not declare what it "
                          f"cannot answer before it is run")
    naming = [r for r in returns if r.get("not_held")]
    if not naming:
        return FAIL, ("no return declares an unanswerable field, so a firm "
                      "learns of the gaps only from the spreadsheet")
    return PASS, (f"{len(returns)} returns, {len(naming)} declaring "
                  f"unanswerable fields up front")


@case("QA-AM-372", "Every `not_held` field in the output")
def am_372(ctx: Ctx) -> Result:
    """Emitted empty, named and counted — never omitted and never guessed.
    A tool that put a plausible value in one of those boxes would produce the
    single most dangerous artefact in this codebase."""
    _model(ctx)
    name = next(iter(RETURNS))
    body = _extract(ctx, name)
    if "_status" in body:
        return BLOCKED, f"the extract answered {body['_status']}"
    declared = [f["field"] for f in RETURNS[name]["fields"]
                if f["source"] == NOT_HELD]
    if not declared:
        name = next((k for k, spec in RETURNS.items()
                     if any(f["source"] == NOT_HELD for f in spec["fields"])),
                    "")
        if not name:
            return BLOCKED, "no return declares an unanswerable field"
        body = _extract(ctx, name)
        declared = [f["field"] for f in RETURNS[name]["fields"]
                    if f["source"] == NOT_HELD]
    if sorted(body.get("not_held") or []) != sorted(declared):
        return FAIL, (f"the extract names {body.get('not_held')} as not held "
                      f"and the spec declares {declared}")
    for field in declared:
        if field not in (body.get("fields") or []):
            return FAIL, (f"'{field}' is not held and is omitted from the "
                          f"columns, so the spreadsheet looks complete")
        for row in body.get("rows") or []:
            if row.get(field) not in (None, "", []):
                return FAIL, (f"'{field}' is declared not held and carries "
                              f"{row.get(field)!r} — a plausible value in a "
                              f"box the register cannot answer")
    if body.get("complete"):
        return FAIL, ("a return with unanswerable fields reports itself "
                      "complete")
    return PASS, (f"{len(declared)} not-held field(s), present as columns, "
                  f"empty in every row, and the return says incomplete")


@case("QA-AM-373",
      "A field the register could hold and every row leaves blank")
def am_373(ctx: Ctx) -> Result:
    """Reported under `empty_in_this_extract` and NOT under `not_held`. The
    two are different facts: one is a limit of the platform and the other is
    a gap in this firm's data, and only the second is somebody's to fix."""
    _model(ctx)
    name = next(iter(RETURNS))
    body = _extract(ctx, name)
    if "_status" in body:
        return BLOCKED, f"the extract answered {body['_status']}"
    if "empty_in_this_extract" not in body:
        return FAIL, ("the extract does not separate a field this firm left "
                      "blank from one the platform cannot answer")
    overlap = set(body.get("empty_in_this_extract") or []) & \
        set(body.get("not_held") or [])
    if overlap:
        return FAIL, (f"{sorted(overlap)} are reported both as not held and "
                      f"as empty in this extract, so a platform limit reads "
                      f"as somebody's data gap")
    answerable = {f["field"] for f in RETURNS[name]["fields"]
                  if f["source"] in (HELD, DERIVED)}
    stray = set(body.get("empty_in_this_extract") or []) - answerable
    if stray:
        return FAIL, (f"{sorted(stray)} are reported as empty and are not "
                      f"fields the register could hold")
    return PASS, (f"{len(body.get('empty_in_this_extract') or [])} blank, "
                  f"{len(body.get('not_held') or [])} not held, no overlap")


@case("QA-AM-374", "An extract over zero rows")
def am_374(ctx: Ctx) -> Result:
    """Nothing in scope is a real answer and must not read as a clean
    return. `empty_in_this_extract` over no rows would list every field,
    which is true and useless — what matters is that the count is zero and
    the detail says so."""
    engine = ctx.ui.app.state.ctx.get("regulatory_returns") or \
        ctx.ui.app.state.ctx.get("returns")
    if engine is None:
        return BLOCKED, "no returns engine is wired"

    class Nothing:
        @staticmethod
        def list():
            return []

    was, engine.registry = engine.registry, Nothing()
    try:
        body = engine.extract(next(iter(RETURNS)))
    finally:
        engine.registry = was
    if body.get("count") != 0:
        return FAIL, f"an empty population reports {body.get('count')} rows"
    if body.get("rows"):
        return FAIL, "an empty population produced rows"
    if body.get("complete"):
        return FAIL, ("a return over nothing reports itself complete, so an "
                      "empty extract reads as a clean one")
    detail = body.get("detail") or ""
    if "0 model" not in detail and "no model" not in detail.lower():
        return FAIL, f"the detail does not say the population is empty: {detail[:120]}"
    return PASS, "0 rows, not complete, and the detail says so"


@case("QA-AM-370", "A model with no purpose class at all")
def am_370(ctx: Ctx) -> Result:
    """Excluded, and the reason given. A model whose purpose nobody recorded
    is not out of scope — it is unassessable, and the two must not print the
    same, because only one of them is somebody's to fix."""
    _model(ctx)
    unknown = _baselined(ctx)
    if not unknown:
        return BLOCKED, "no purposeless model could be admitted"
    name = next((k for k in RETURNS if "ai" in k or "annex" in k),
                next(iter(RETURNS)))
    body = _extract(ctx, name)
    if "_status" in body:
        return BLOCKED, f"the extract answered {body['_status']}"
    excluded = body.get("excluded") or []
    mine = [e for e in excluded if unknown in f"{e}"]
    included = [r for r in (body.get("rows") or []) if unknown in f"{r}"]
    if included:
        return FAIL, ("a model with no purpose class was included in the "
                      "population, so an unassessed model is being reported "
                      "as assessed")
    if not mine:
        return FAIL, ("a model with no purpose class is neither included nor "
                      "listed as excluded, so it has vanished from the return")
    if not f"{mine[0]}".strip():
        return FAIL, "the exclusion carries no reason"
    reason = f"{mine[0]}".lower()
    if "purpose" not in reason:
        return FAIL, (f"the exclusion does not say the purpose is missing: "
                      f"{f'{mine[0]}'[:120]}")
    return PASS, f"excluded, with the reason: {f'{mine[0]}'[:80]}"


@case("QA-AM-4880", "Every excluded model carries a reason")
def am_4880(ctx: Ctx) -> Result:
    """A regulator's first question about a population of eleven is what
    happened to the twelfth. An exclusion list is only worth having if every
    row on it says why."""
    for purpose in ("credit_decision", "commercial", ""):
        _model(ctx, purpose=purpose)
    for name in RETURNS:
        body = _extract(ctx, name)
        if "_status" in body:
            continue
        for entry in body.get("excluded") or []:
            said = f"{entry}"
            if isinstance(entry, dict):
                if not (entry.get("reason") or entry.get("why") or "").strip():
                    return FAIL, (f"a model excluded from '{name}' carries no "
                                  f"reason: {said[:120]}")
                if not (entry.get("urn") or entry.get("model") or ""):
                    return FAIL, (f"an exclusion from '{name}' names no "
                                  f"model: {said[:120]}")
            elif len(said) < 20:
                return FAIL, (f"an exclusion from '{name}' is a bare "
                              f"identifier with no reason: {said}")
    return PASS, "every exclusion across every return names a model and a reason"


@case("QA-AM-4881", "An unknown return")
def am_4881(ctx: Ctx) -> Result:
    """The refusal names the returns the platform does extract, because a
    caller who guessed a name is one keystroke from the right one."""
    got = ctx.api.get(f"{R}/a-return-nobody-defined", auth=ctx.people["risk"])
    if got.status_code < 400:
        return FAIL, "an unknown return was extracted"
    if code_of(got) not in ("unknown_return", "not_found"):
        return FAIL, f"refused '{code_of(got)}'"
    if code_of(got) == "unknown_return":
        missing = [k for k in RETURNS if k not in got.text]
        if missing:
            return FAIL, f"the refusal does not name {missing}"
    return PASS, f"refused '{code_of(got)}', naming what it does extract"


@case("QA-AM-376", "An extract under a scoped reader")
def am_376(ctx: Ctx) -> Result:
    """The population is filtered to what the reader may see, and the count
    reflects that. A return whose population was silently widened past a
    reader's scope would hand somebody a list of models they are refused on
    every other screen."""
    import inspect
    engine = ctx.ui.app.state.ctx.get("regulatory_returns") or \
        ctx.ui.app.state.ctx.get("returns")
    if engine is None:
        return BLOCKED, "no returns engine is wired"
    source = inspect.getsource(type(engine).extract)
    if "scope" not in source:
        return FAIL, ("the extract takes no scope, so a restricted reader "
                      "receives the whole estate")
    if "unrestricted" not in source or "permits" not in source:
        return FAIL, ("the extract does not apply the scope the same way the "
                      "rest of the platform does")
    at_filter = source.find("scope.permits")
    at_population = source.find("_population")
    if at_filter < 0 or at_population < 0:
        return BLOCKED, "the filter or the population step is not reachable"
    if at_filter > at_population:
        return FAIL, ("the population is derived BEFORE the scope is applied, "
                      "so the exclusion list can name models the reader may "
                      "not see")
    return PASS, "scoped before the population is derived"


@case("QA-AM-4882", "Each field declares where its value comes from")
def am_4882(ctx: Ctx) -> Result:
    """`held`, `derived` or `not_held`, on every field of every return. A
    supervisor reading a value needs to know whether the firm asserted it,
    the platform computed it, or nobody has it — and the three carry very
    different weight."""
    for name, spec in RETURNS.items():
        for field in spec["fields"]:
            source = field.get("source")
            if source not in (HELD, DERIVED, NOT_HELD):
                return FAIL, (f"'{name}.{field.get('field')}' declares source "
                              f"{source!r}, which is not one of the three")
        body = _extract(ctx, name)
        if "_status" in body:
            continue
        declared = {f["field"] for f in spec["fields"]}
        published = {f["field"] for f in body.get("field_sources") or []}
        if published != declared:
            return FAIL, (f"'{name}' publishes sources for {sorted(published)} "
                          f"and declares {sorted(declared)}")
    total = sum(len(s["fields"]) for s in RETURNS.values())
    return PASS, (f"{total} fields across {len(RETURNS)} returns, each "
                  f"declaring held, derived or not_held")
