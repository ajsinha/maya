"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the estate fold.

A dashboard asks nine sources the same question about every model in the
estate, and each source goes to the database. The fold builds one in-memory
index per folded table per column-set, serves equality reads from it, and drops
it at the end of the scope.

Every part of that is a chance to answer a governance question from a state
that never existed. So the fold is deliberately narrow: **fourteen named
tables, equality filters only, no ordering, no limit** — anything else falls
through to SQL, because a read this cannot answer correctly is one it must not
answer at all. Writes to a folded table are refused outright rather than
invalidating the index, and nesting is a no-op rather than a scope whose exit
drops the outer index.

The gap this section is looking for is the write the fold cannot see: the
refusal is on `Repository`, so anything reaching the database another way
leaves the fold answering from before it with nothing said.
"""
from __future__ import annotations

import time

from core.estate.worklist import FOLDED
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

M = "/api/v1/models"
P = "/api/v1/portfolio"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _db(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("db")


def _model(ctx: Ctx, **over) -> str:
    name = ctx.unique("fold")
    body = {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **SHAPE}
    body.update(over)
    ctx.api.post(M, json=body, auth=ctx.people["owner"])
    return body["urn"]


@case("QA-PLT-092", "A write through a repository during a fold")
def plt_092(ctx: Ctx) -> Result:
    """Refused — and the question is whether it is refused with a code. A
    fold that let a write land would make every read after it answer from
    before it, so refusing is right; a bare `RuntimeError` is how that
    refusal reaches a caller as a 500 rather than as a governance answer."""
    db = _db(ctx)
    if db is None or not hasattr(db, "folding"):
        return BLOCKED, "no folding database is wired"
    urn = _model(ctx)
    registry = ctx.ui.app.state.ctx["registry"]
    model = registry.require(urn)
    with db.folding(FOLDED):
        try:
            registry.catalogue.models.set({"name": "renamed inside a fold"},
                                id=model["id"])
        except Exception as exc:
            code = getattr(exc, "code", None)
            after = registry.require(urn)
            if after["name"] == "renamed inside a fold":
                return FAIL, "refused and the write landed anyway"
            if code:
                return PASS, f"refused '{code}': {str(exc)[:110]}"
            return FAIL, (
                f"refused with a bare {type(exc).__name__} carrying no code, "
                f"no detail and no remediation, so `Routes.guard` cannot map "
                f"it and a route reaching it answers 500. Latent rather than "
                f"live: the folded tables are read by `WorkList.across` and "
                f"the portfolio cuts, which write nothing, and the digest's "
                f"`notification` writes land after the fold has closed — so "
                f"no route reaches it today and the first one that does finds "
                f"an unmapped 500: {str(exc)[:130]}")
    return FAIL, ("a folded table was written during a fold, so every read "
                  "after it in the same scope answers from before the write")


@case("QA-PLT-093", "A write during a fold that does not go through a repository")
def plt_093(ctx: Ctx) -> Result:
    """The refusal lives on `Repository.set`, so a write that reaches the
    database another way — a raw statement, a trigger, a second process —
    is invisible to it. The fold then answers from before the write with
    nothing said, which is the failure the refusal exists to prevent,
    arriving by the door it does not cover."""
    db = _db(ctx)
    if db is None or not hasattr(db, "folding"):
        return BLOCKED, "no folding database is wired"
    urn = _model(ctx)
    registry = ctx.ui.app.state.ctx["registry"]
    model = registry.require(urn)
    renamed = "renamed by a raw statement"
    with db.folding(FOLDED):
        registry.catalogue.models.one(id=model["id"])          # builds the index
        db.execute("UPDATE model SET name = :n WHERE id = :i",
                   {"n": renamed, "i": model["id"]})
        inside = registry.catalogue.models.one(id=model["id"]) or {}
    outside = registry.require(urn)
    if outside["name"] != renamed:
        return BLOCKED, "the raw write did not land"
    if inside.get("name") == renamed:
        return PASS, ("the fold saw the raw write, so the index is not a "
                      "snapshot after all")
    return FAIL, (f"a raw UPDATE landed during a fold and the fold went on "
                  f"answering '{inside.get('name')}' while the table said "
                  f"'{renamed}'. `_refuse_write_while_folding` is called from "
                  f"`Repository.add/set/remove` only, so any write reaching "
                  f"the database another way is invisible to it and nothing "
                  f"is said")


@case("QA-PLT-094", "A fold, an inner fold, and the outer index")
def plt_094(ctx: Ctx) -> Result:
    """Nesting is a no-op rather than a scope of its own, because the inner
    scope's exit would drop the outer scope's index — and the bug that
    produces is a read that is correct on Tuesday."""
    db = _db(ctx)
    if db is None or not hasattr(db, "folding"):
        return BLOCKED, "no folding database is wired"
    urn = _model(ctx)
    registry = ctx.ui.app.state.ctx["registry"]
    model = registry.require(urn)
    with db.folding(FOLDED):
        registry.catalogue.models.one(id=model["id"])
        if db._fold is None:
            return FAIL, "the outer fold built no index"
        with db.folding(FOLDED):
            if db._fold is None:
                return FAIL, "entering an inner fold dropped the outer index"
        if db._fold is None:
            return FAIL, ("leaving the inner fold dropped the outer index, so "
                          "every read after it in the outer scope goes to the "
                          "database while the caller believes it is folded")
        served = db.folded("model", ["id"], [model["id"]])
        if not served:
            return FAIL, "the outer index no longer answers"
    if db._fold is not None:
        return FAIL, "the fold survived its own scope"
    return PASS, "the inner fold is a no-op and the outer index survives it"


@case("QA-PLT-095", "A folded read with an `order` or a `limit`")
def plt_095(ctx: Ctx) -> Result:
    """Falls through to the database. The index is built on equality alone,
    so an ordered or limited read it tried to answer would be answering a
    different question from the SQL it replaced."""
    db = _db(ctx)
    if db is None or not hasattr(db, "folding"):
        return BLOCKED, "no folding database is wired"
    registry = ctx.ui.app.state.ctx["registry"]
    for _ in range(3):
        _model(ctx)
    plain = registry.catalogue.models.many(legal_entity="LE-US-01")
    ordered = registry.catalogue.models.many(order="urn", desc=True,
                                   legal_entity="LE-US-01")
    limited = registry.catalogue.models.many(order="urn", limit=2,
                                   legal_entity="LE-US-01")
    with db.folding(FOLDED):
        folded_plain = registry.catalogue.models.many(legal_entity="LE-US-01")
        folded_ordered = registry.catalogue.models.many(order="urn", desc=True,
                                              legal_entity="LE-US-01")
        folded_limited = registry.catalogue.models.many(order="urn", limit=2,
                                              legal_entity="LE-US-01")
    if [r["id"] for r in folded_plain] != [r["id"] for r in plain]:
        return FAIL, "the folded equality read disagrees with the database"
    if [r["id"] for r in folded_ordered] != [r["id"] for r in ordered]:
        return FAIL, ("an ordered read was answered from the index and came "
                      "back in a different order from the SQL")
    if [r["id"] for r in folded_limited] != [r["id"] for r in limited]:
        return FAIL, (f"a limited read answered {len(folded_limited)} rows "
                      f"inside the fold and {len(limited)} outside it")
    return PASS, (f"{len(plain)} rows either way; ordered and limited reads "
                  f"fall through to SQL unchanged")


@case("QA-PLT-096", "A table outside the folded fourteen read during a fold")
def plt_096(ctx: Ctx) -> Result:
    """Fresh from the database. The list is named rather than derived so a
    dashboard cannot pull telemetry or the evidence chain into memory, and
    the price of that is that an unfolded table must still read correctly
    from inside a fold."""
    db = _db(ctx)
    if db is None or not hasattr(db, "folding"):
        return BLOCKED, "no folding database is wired"
    evidence = ctx.ui.app.state.ctx.get("evidence")
    if evidence is None:
        return BLOCKED, "no evidence chain is wired"
    if "evidence_node" in FOLDED:
        return BLOCKED, "the evidence chain is folded after all"
    before = db.query("SELECT COUNT(*) AS n FROM evidence_node")[0]["n"]
    with db.folding(FOLDED):
        inside = db.query("SELECT COUNT(*) AS n FROM evidence_node")[0]["n"]
        if db.folded("evidence_node", ["id"], ["anything"]) is not None:
            return FAIL, "an unfolded table was served from the index"
        # Appended, not registered: `model` is folded, so a registration
        # inside a fold is refused before it reaches the chain.
        evidence.append("qa_probe", "model", "mid-fold",
                        {"why": "an unfolded table must still read fresh"},
                        actor="qa")
        after = db.query("SELECT COUNT(*) AS n FROM evidence_node")[0]["n"]
    if inside != before:
        return BLOCKED, f"the count moved before the write: {before} → {inside}"
    if after <= before:
        return FAIL, (f"a registration inside a fold appended nothing to the "
                      f"chain, or the read is stale: {before} → {after}")
    return PASS, (f"evidence_node is outside the fourteen and reads fresh: "
                  f"{before} → {after} during the fold")


@case("QA-PLT-078", "A write landing during an estate fold")
def plt_078(ctx: Ctx) -> Result:
    """The fold's answer has to be internally consistent — one moment, not a
    blend of before and after. A cut of the estate that counted a model in
    one aggregate and not in another would be reconciled against itself and
    read as a defect in whichever number somebody trusted less."""
    db = _db(ctx)
    portfolio = ctx.ui.app.state.ctx.get("portfolio")
    if db is None or portfolio is None:
        return BLOCKED, "no folding database or portfolio is wired"
    for _ in range(3):
        _model(ctx)
    landed = {"n": 0}

    real = type(db).folded

    def watching(self, table, columns, values):
        rows = real(self, table, columns, values)
        if table == "model" and landed["n"] == 0:
            landed["n"] = 1
            # A model registered mid-fold, through the repository the fold
            # refuses — so it lands outside the scope, exactly as a second
            # process would.
            self.execute(
                "INSERT INTO model (id, urn, name, owner, model_class, domain, "
                "legal_entity, purpose, tier, status, registered_at) VALUES "
                "(:i, :u, :n, 'owner', 'logistic', 'credit', 'LE-US-01', "
                "'credit_decision', 3, 'registered', :t)",
                {"i": "mid-fold-0001", "u": "maya://model/mid-fold",
                 "n": "mid-fold", "t": time.time()})
        return rows

    type(db).folded = watching
    try:
        cut = portfolio.aggregate()
        heat = portfolio.by("domain")
    finally:
        type(db).folded = real
    if not landed["n"]:
        return BLOCKED, "the fold never consulted the index"
    counted = sum(c.get("models", 0) for c in (heat.get("cells") or []))
    if cut["models"] != counted:
        return FAIL, (f"the aggregate counted {cut['models']} models and the "
                      f"cut by domain counted {counted}: one read the estate "
                      f"before the mid-fold write and the other after it")
    return PASS, (f"a model landed mid-fold and both aggregates agree on "
                  f"{cut['models']}")


@case("QA-PLT-079", "The estate-fold cache after a mutation")
def plt_079(ctx: Ctx) -> Result:
    """The index is per-scope, not a cache with a lifetime. A dashboard read
    after a change must reflect the change — a fold that outlived its
    request would be a governance number that is right until somebody
    refreshes."""
    db = _db(ctx)
    portfolio = ctx.ui.app.state.ctx.get("portfolio")
    if db is None or portfolio is None:
        return BLOCKED, "no folding database or portfolio is wired"
    _model(ctx, domain="credit")
    before = portfolio.by("domain")
    if db._fold is not None:
        return FAIL, "the fold outlived the read that opened it"
    _model(ctx, domain="markets")
    after = portfolio.by("domain")
    domains = {c["value"] for c in (after.get("cells") or [])}
    if "markets" not in domains:
        return FAIL, (f"a model registered between two reads is absent from "
                      f"the second: {sorted(domains)} — the fold index "
                      f"survived its scope")
    total_before = sum(c["models"] for c in (before.get("cells") or []))
    total_after = sum(c["models"] for c in (after.get("cells") or []))
    if total_after != total_before + 1:
        return FAIL, (f"the second read counts {total_after} against "
                      f"{total_before} before one registration")
    return PASS, (f"{total_before} → {total_after}; the index is built and "
                  f"dropped inside each read")


@case("QA-PLT-080", "The estate fold on an estate of exactly zero models",
      isolated=True)
def plt_080(ctx: Ctx) -> Result:
    """Zeroes, and a detail saying the estate is empty. A zero that does not
    say why is the same number as a zero produced by a broken read, and the
    two get treated the same way — which is to say, not at all."""
    portfolio = ctx.ui.app.state.ctx.get("portfolio")
    registry = ctx.ui.app.state.ctx.get("registry")
    if portfolio is None or registry is None:
        return BLOCKED, "no portfolio is wired"
    if registry.list():
        return BLOCKED, f"the fresh instance has {len(registry.list())} models"
    cut = portfolio.aggregate()
    if cut["models"] or cut["with_something_owed"]:
        return FAIL, f"an empty estate counts models: {cut}"
    if cut["exposure_coverage"] != 0.0 or cut["exposure_total"]:
        return FAIL, f"an empty estate carries exposure: {cut}"
    if cut["share_of_exposure_owing"] is not None:
        return FAIL, ("an empty estate reports a share of exposure owing "
                      "rather than null, so nothing over zero was divided")
    if "empty" not in (cut.get("detail") or ""):
        return FAIL, (f"the zero does not say the estate is empty: "
                      f"{cut.get('detail')!r}")
    by = portfolio.by("domain")
    if by.get("cells"):
        return FAIL, f"an empty estate has cells: {by['cells']}"
    if not (by.get("detail") or ""):
        return FAIL, "the empty cut says nothing"
    return PASS, f"zeroes and a detail: {cut['detail']!r}"


@case("QA-PLT-081", "The estate fold on an estate of exactly one model",
      isolated=True)
def plt_081(ctx: Ctx) -> Result:
    """One is the arithmetic edge every aggregate hits first: a coverage of
    one over one, a distribution with a single cell, a share that divides by
    the only exposure there is."""
    portfolio = ctx.ui.app.state.ctx.get("portfolio")
    registry = ctx.ui.app.state.ctx.get("registry")
    if portfolio is None or registry is None:
        return BLOCKED, "no portfolio is wired"
    if registry.list():
        return BLOCKED, f"the fresh instance has {len(registry.list())} models"
    _model(ctx)
    cut = portfolio.aggregate()
    if cut["models"] != 1:
        return FAIL, f"one model, and the aggregate counts {cut['models']}"
    if not (0.0 <= cut["exposure_coverage"] <= 1.0):
        return FAIL, f"coverage outside [0,1]: {cut['exposure_coverage']}"
    if cut["exposure_known_for"] == 0 and cut["share_of_exposure_owing"] is not None:
        return FAIL, ("no exposure is known and a share of it is still "
                      "reported")
    if not (cut.get("detail") or ""):
        return FAIL, "the aggregate says nothing"
    for dimension in ("domain", "tier", "legal_entity"):
        by = portfolio.by(dimension)
        cells = by.get("cells") or []
        if len(cells) != 1:
            return FAIL, (f"one model cuts into {len(cells)} cells by "
                          f"{dimension}")
        if cells[0]["models"] != 1:
            return FAIL, f"the single {dimension} cell counts {cells[0]}"
    heat = portfolio.heatmap("domain", "tier")
    if not heat:
        return FAIL, "the heatmap is empty for a single model"
    return PASS, ("one model: one cell in each of three dimensions, coverage "
                  f"{cut['exposure_coverage']}, and a detail")


@case("QA-PLT-097", "An append-only repository `set()` reaching HTTP")
def plt_097(ctx: Ctx) -> Result:
    """`AppendOnlyViolation` carries a code, a detail and a remediation — the
    three fields the refusal taxonomy is built from. It is a bare
    `RuntimeError`, `append_only` is not in `STATUS`, and `Routes.guard`
    does not catch it, so anything that reached HTTP through it would arrive
    as an unmapped 500 rather than as the refusal it was written to be."""
    from db.repositories import AppendOnlyViolation
    from routes.base import STATUS, Routes
    evidence = ctx.ui.app.state.ctx.get("evidence")
    if evidence is None:
        return BLOCKED, "no evidence chain is wired"
    try:
        evidence.repo.set({"payload": {}}, id="anything")
    except AppendOnlyViolation as exc:
        problem = exc.as_problem()
        if set(problem) != {"error", "detail", "remediation"}:
            return FAIL, f"the refusal is not shaped like one: {problem}"
        mapped = problem["error"] in STATUS
        import inspect
        caught = "AppendOnlyViolation" in inspect.getsource(Routes.guard)
        if mapped and caught:
            return PASS, (f"refused '{problem['error']}' → "
                          f"{STATUS[problem['error']]}, and the guard catches it")
        return FAIL, (
            f"the repository refuses '{problem['error']}' with a detail and a "
            f"remediation, and neither half of the taxonomy receives it: "
            f"{'in' if mapped else 'NOT in'} STATUS, "
            f"{'caught' if caught else 'NOT caught'} by Routes.guard. It is a "
            f"bare RuntimeError, so a route reaching it answers 500 with no "
            f"code — the refusal was written for a mapping it was never added "
            f"to. Latent: `EvidenceRepository` is the only AppendOnly "
            f"subclass and nothing outside the tests calls its set() or "
            f"remove(), so this is the shape of the refusal rather than a "
            f"live 500")
    except Exception as exc:
        return FAIL, f"refused with {type(exc).__name__} instead: {exc}"
    return FAIL, "an append-only table accepted an UPDATE through its repository"
