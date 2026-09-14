"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section J — what stops a deletion, and what the refusal can see.

There are no foreign keys, on purpose. The reference index is the whole
control: `refuse_if_referenced` asks what points at a model and refuses if
anything would be left pointing at nothing. The cascade then destroys what goes
and keeps what stays, and **never touches a blocking row** — because a cascade
that could destroy one would make the refusal decorative.

Which means the two lists have to agree. `CASCADE` declares twenty-four tables
BLOCKS; `ReferenceIndex._to_model` decides whether a deletion is refused. A
table in the first list and not the second is the sharpest version of this
codebase's recurring defect: **a reference check that misses a table does not
fail, it approves.**
"""
from __future__ import annotations


from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
B = "/api/v1/baseline"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("del")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **SHAPE}, auth=ctx.people["owner"])
    return name


def _delete(ctx: Ctx, name: str):
    return ctx.api.delete(f"{M}/maya://model/{name}?reason=qa%20deletion")


def _rows(ctx: Ctx, table: str, name: str) -> int:
    db = ctx.ui.app.state.ctx["db"]
    model = ctx.ui.app.state.ctx["registry"].get(f"maya://model/{name}")
    if model is None:
        return -1
    got = db.query(f"SELECT COUNT(*) AS n FROM {table} WHERE model_id = :m",
                   {"m": model["id"]})
    return got[0]["n"] if got else 0


@case("QA-PLT-5201",
      "Every table the cascade calls BLOCKS is one the refusal can see")
def plt_5201(ctx: Ctx) -> Result:
    """The two lists are one control in two halves. A blocking row is never
    destroyed, so the only thing standing between it and an orphan is the
    reference index having looked.

    Asserted on the CONSTRUCT and then executed, not on the token. A first
    version of this case grepped `FROM (\\w+)` out of `_to_model` and reported
    six tables missing — they are reached by `_declared`, which builds its SQL
    from the dispositions themselves. That is the same mistake the guard test
    docs/11 §7 records made, arriving from the other side: a check that reads
    source for a word instead of asking what the code does."""
    from core.references.index import ReferenceIndex
    from core.retention.cascade import BLOCKS, CASCADE
    db = ctx.ui.app.state.ctx.get("db")
    if db is None:
        return BLOCKED, "no database is wired"
    blocks = [d for d in CASCADE if d.kind == BLOCKS]
    by_hand = set(ReferenceIndex.ASKED_BY_HAND)
    declared = [d for d in blocks if d.table not in by_hand]
    uncovered = [d.table for d in blocks
                 if d.table not in by_hand and not hasattr(d, "blocking_sql")]
    if uncovered:
        return FAIL, (f"{len(uncovered)} blocking table(s) are neither asked "
                      f"by hand nor answerable from the declaration: "
                      f"{uncovered}")
    ran = 0
    for disposition in declared:
        try:
            db.query(disposition.blocking_sql(), {"m": "no-such-model"})
        except Exception as exc:
            return FAIL, (f"the declared query for '{disposition.table}' does "
                          f"not run against the schema: "
                          f"{type(exc).__name__}: {str(exc)[:120]}")
        ran += 1
    name = _model(ctx)
    urn = f"maya://model/{name}"
    empty = ctx.api.get(f"/api/v1/references?kind=model&identifier={urn}",
                        auth=ctx.people["risk"])
    if empty.status_code >= 400:
        return PASS, (f"{len(blocks)} blocking table(s): "
                      f"{len(blocks) - len(declared)} asked by hand, "
                      f"{ran} answered from the declaration, every query valid "
                      f"against the schema")
    return PASS, (f"{len(blocks)} blocking table(s): "
                  f"{len(blocks) - len(declared)} asked by hand, {ran} "
                  f"answered from the declaration and every one of those "
                  f"queries runs against the real schema; a fresh model "
                  f"reports {len((empty.json() or {}).get('references') or [])} "
                  f"reference(s)")


@case("QA-DEL-042", "Delete a model with an unfinished validation",
      isolated=True)
def del_042(ctx: Ctx) -> Result:
    """A validation in progress is the clearest case: somebody is actively
    working on this model, and the register is about to forget it exists."""
    name = _model(ctx)
    made = ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        return BLOCKED, f"the version could not be created: {made.text[:150]}"
    opened = ctx.api.post("/api/v1/validations",
                          json={"urn": f"maya://model/{name}", "semver": "1.0.0",
                                "validators": ["person/validator"],
                                "kind": "initial", "scope": ["fit"]},
                          auth=ctx.people["validator"])
    if opened.status_code >= 400:
        return BLOCKED, f"the validation could not be opened: {opened.text[:170]}"
    before = _rows(ctx, "validation", name)
    got = _delete(ctx, name)
    if got.status_code >= 400:
        if code_of(got) != "still_referenced":
            return FAIL, f"refused '{code_of(got)}' rather than still_referenced"
        if "validation" not in got.text:
            return FAIL, (f"refused, and the refusal does not name the "
                          f"validation: {got.text[:170]}")
        return PASS, "refused 'still_referenced', naming the validation"
    left = ctx.ui.app.state.ctx["db"].query(
        "SELECT COUNT(*) AS n FROM validation WHERE model_id NOT IN "
        "(SELECT id FROM model)")
    return FAIL, (
        f"a model with an unfinished validation was deleted "
        f"({got.status_code}). It carried {before} validation row(s), the "
        f"cascade declares `validation` BLOCKS so it destroyed none of them, "
        f"and `_to_model` never reads that table — so nothing refused and "
        f"nothing cleaned up. {left[0]['n'] if left else '?'} validation "
        f"row(s) in this database now name a model that does not resolve, and "
        f"the validator working on it has a record of an episode about nothing")


@case("QA-DEL-045", "Delete a model with an undischarged approval condition",
      isolated=True)
def del_045(ctx: Ctx) -> Result:
    """`approval_condition` IS read by the index, so this is the control
    working — and it is here to sit beside QA-DEL-042 as the contrast: the
    same disposition, one table read and one not."""
    from core.retention.cascade import CASCADE
    blocks = {d.table for d in CASCADE if d.kind == "blocks"}
    if "approval_condition" not in blocks:
        return BLOCKED, "approval_condition is no longer a blocking table"
    name = _model(ctx)
    made = ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        return BLOCKED, f"the version could not be created: {made.text[:150]}"
    imposed = ctx.api.post(
        "/api/v1/approval-conditions",
        json={"urn": f"maya://model/{name}", "semver": "1.0.0",
              "kind": "expires", "days": 90.0,
              "rationale": "re-validate before September"},
        auth=ctx.people["risk"])
    if imposed.status_code >= 400:
        return BLOCKED, f"the condition could not be imposed: {imposed.text[:170]}"
    got = _delete(ctx, name)
    if got.status_code < 400:
        return FAIL, ("a model carrying an undischarged approval condition was "
                      "deleted, and the condition now names nothing")
    if code_of(got) != "still_referenced":
        return FAIL, f"refused '{code_of(got)}' rather than still_referenced"
    if "condition" not in got.text.lower():
        return FAIL, f"the refusal does not name the condition: {got.text[:170]}"
    return PASS, "refused 'still_referenced', naming the condition"


@case("QA-DEL-090", "Delete a model carrying outstanding baseline debt",
      isolated=True)
def del_090(ctx: Ctx) -> Result:
    """`compliance_debt` is the second half of QA-DEL-042, reached through
    the one operation that produces it in bulk: a baseline import raises a
    gap for every check in the register."""
    urn = f"maya://model/{ctx.unique('delb')}"
    name = urn.split("/")[-1]
    imported = ctx.api.post(
        f"{B}/imports",
        json={"source": "legacy-inventory", "note": "QA",
              "models": [{"urn": urn, "name": name, "model_class": "logistic",
                          "domain": "credit", "owner": "person/owner",
                          "legal_entity": "LE-US-01",
                          "purpose": "credit_decision", "tier": 3}]},
        auth=ctx.people["risk"])
    if imported.status_code >= 400:
        return BLOCKED, f"the import failed: {imported.text[:170]}"
    outstanding = _rows(ctx, "compliance_debt", name)
    if outstanding < 1:
        return BLOCKED, "the import raised no debt"
    got = _delete(ctx, name)
    if got.status_code >= 400:
        if code_of(got) != "still_referenced":
            return FAIL, f"refused '{code_of(got)}' rather than still_referenced"
        if "debt" not in got.text.lower():
            return FAIL, f"the refusal does not name the debt: {got.text[:170]}"
        return PASS, f"refused 'still_referenced', naming {outstanding} debt item(s)"
    orphans = ctx.ui.app.state.ctx["db"].query(
        "SELECT COUNT(*) AS n FROM compliance_debt WHERE model_id NOT IN "
        "(SELECT id FROM model)")
    return FAIL, (
        f"a model carrying {outstanding} outstanding compliance debt item(s) "
        f"was deleted ({got.status_code}). `compliance_debt` is declared BLOCKS "
        f"— so the cascade left every row — and `_to_model` never reads it, so "
        f"nothing refused. {orphans[0]['n'] if orphans else '?'} debt row(s) "
        f"now name no model, and the baseline burn-down counts gaps against a "
        f"model nobody can look up")


@case("QA-DEL-054", "Delete a model with limitations and assumptions attached",
      isolated=True)
def del_054(ctx: Ctx) -> Result:
    """Both are declared GOES — destroyed with the model and counted. The
    question this case turns out to ask is whether that disposition can ever
    fire: a limitation hangs off a VERSION, and a version blocks a
    deletion."""
    from db.schema.tables import METADATA
    name = _model(ctx)
    urn = f"maya://model/{name}"
    made = ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        return BLOCKED, f"the version could not be created: {made.text[:150]}"
    limitation = ctx.api.post(
        "/api/v1/limitations",
        json={"urn": urn, "semver": "1.0.0", "kind": "scope",
              "statement": "not calibrated below a 500 score"},
        auth=ctx.people["validator"])
    assumption = ctx.api.post(
        "/api/v1/assumptions",
        json={"urn": urn, "semver": "1.0.0", "kind": "data",
              "statement": "the bureau file is refreshed monthly"},
        auth=ctx.people["owner"])
    if limitation.status_code >= 400 and assumption.status_code >= 400:
        return BLOCKED, (f"neither could be attached: "
                         f"{limitation.text[:90]} / {assumption.text[:90]}")
    counts = {t: _rows(ctx, t, name)
              for t in ("model_limitation", "model_assumption")}
    if not any(v > 0 for v in counts.values()):
        return BLOCKED, f"nothing was attached: {counts}"
    got = _delete(ctx, name)
    if got.status_code < 400:
        db = ctx.ui.app.state.ctx["db"]
        left = {t: db.query(f"SELECT COUNT(*) AS n FROM {t} WHERE model_id "
                            f"NOT IN (SELECT id FROM model)")[0]["n"]
                for t in counts}
        if any(left.values()):
            return FAIL, (f"after the deletion {left} row(s) name no model, "
                          f"though both tables are declared GOES")
        destroyed = (got.json() or {}).get("destroyed") or {}
        for table, had in counts.items():
            if had and not destroyed.get(table):
                return FAIL, (f"{had} {table} row(s) went and the tombstone "
                              f"counts none: {destroyed}")
        return PASS, f"both destroyed and counted: {destroyed}"
    if code_of(got) != "still_referenced":
        return FAIL, f"refused '{code_of(got)}' rather than still_referenced"
    nullable = {t: METADATA.tables[t].c["model_version_id"].nullable
                for t in counts}
    if any(nullable.values()):
        return BLOCKED, (f"a model-level limitation is possible "
                         f"({nullable}); this case did not build one")
    return FAIL, (
        f"the GOES disposition on `model_limitation` and `model_assumption` "
        f"cannot fire through the delete route. Both rows carry a NOT NULL "
        f"`model_version_id` ({nullable}), so neither can exist without a "
        f"version — and `model_version` blocks a deletion unconditionally, so "
        f"a model that has either is always refused: '{code_of(got)}', "
        f"{got.text[:110]}. Two dispositions declared, counted in the "
        f"tombstone's shape, and unreachable by the only path that runs the "
        f"cascade. The rows go when the VERSION is removed, which is a "
        f"different act with a different record")


@case("QA-DEL-056", "Warrant invocations survive a deletion and are counted",
      isolated=True)
def del_056(ctx: Ctx) -> Result:
    """`warrant_invocation` is declared STAYS: a record of something that
    happened reads correctly after the model is gone. Counted as `(kept)`
    rather than dropped, because "nothing was destroyed" and "nothing was
    there" are different facts and the tombstone is the only place either is
    recorded."""
    from core.retention.cascade import CASCADE
    stays = {d.table for d in CASCADE if d.kind == "stays"}
    if "warrant_invocation" not in stays:
        return BLOCKED, "warrant_invocation is no longer a STAYS table"
    name = _model(ctx)
    db = ctx.ui.app.state.ctx["db"]
    model = ctx.ui.app.state.ctx["registry"].require(f"maya://model/{name}")
    db.execute(
        "INSERT INTO warrant_invocation (id, model_id, warrant_id, verb, "
        "environment, principal, declared_use, at, outcome) VALUES "
        "(:i, :m, 'w-qa', 'score', 'prod', 'svc-qa', 'credit_decision', "
        "0.0, 'served')",
        {"i": f"inv-{name}", "m": model["id"]})
    got = _delete(ctx, name)
    if got.status_code >= 400:
        return BLOCKED, (f"the deletion was refused: '{code_of(got)}' "
                         f"{got.text[:150]}")
    destroyed = (got.json() or {}).get("destroyed") or {}
    survivors = db.query(
        "SELECT COUNT(*) AS n FROM warrant_invocation WHERE id = :i",
        {"i": f"inv-{name}"})
    if not survivors or not survivors[0]["n"]:
        return FAIL, ("the invocation was destroyed with the model, so the "
                      "record of what this model actually served is gone")
    kept = [k for k in destroyed if "(kept)" in k]
    if "warrant_invocation (kept)" not in destroyed:
        return FAIL, (f"the invocation survived and the tombstone does not "
                      f"count it as kept: {destroyed} (kept keys: {kept})")
    return PASS, (f"the invocation survives and is counted: "
                  f"warrant_invocation (kept) = "
                  f"{destroyed['warrant_invocation (kept)']}")


@case("QA-DEL-059", "A blocking row is never destroyed by the cascade",
      isolated=True)
def del_059(ctx: Ctx) -> Result:
    """The cascade is called after the refusal, so it trusts that nothing
    blocking is left. Driving it directly with a blocking row present is
    what proves the trust is not load-bearing: a cascade that could destroy
    one would make the refusal decorative."""
    from core.retention.cascade import CASCADE
    name = _model(ctx)
    urn = f"maya://model/{name}"
    made = ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        return BLOCKED, f"the version could not be created: {made.text[:150]}"
    # A GOES row, so the cascade has something to count. `risk_assessment` is
    # declared GOES and an assessment is the cheapest one to produce.
    assessed = ctx.api.post(f"{M}/{name}/assess",
                            json={"exposure": 1_000.0,
                                  "purpose_class": "commercial",
                                  "feature_count": 3, "interpretable": True,
                                  "uses_alternative_data": False},
                            auth=ctx.people["risk"])
    if assessed.status_code >= 400:
        return BLOCKED, f"the model could not be assessed: {assessed.text[:150]}"
    raised = ctx.api.post(
        "/api/v1/findings",
        json={"urn": urn, "severity": "High", "title": "a blocking finding",
              "owner": "person/owner", "description": "qa",
              "category": "general", "source": "validation", "blocking": True},
        auth=ctx.people["risk"])
    if raised.status_code >= 400:
        return BLOCKED, f"the finding could not be raised: {raised.text[:150]}"
    cascade = ctx.ui.app.state.ctx.get("cascade")
    if cascade is None:
        from core.retention.cascade import Cascade
        cascade = Cascade(ctx.ui.app.state.ctx["db"])
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    counts = cascade.destroy(model["id"])
    db = ctx.ui.app.state.ctx["db"]
    blocking = [d.table for d in CASCADE if d.kind == "blocks"]
    destroyed = [t for t in blocking if t in counts]
    if destroyed:
        return FAIL, (f"the cascade destroyed rows in blocking table(s) "
                      f"{destroyed}: {counts}")
    survived = db.query("SELECT COUNT(*) AS n FROM finding WHERE model_id = :m",
                        {"m": model["id"]})
    if not survived or not survived[0]["n"]:
        return FAIL, ("the blocking finding is gone after a direct cascade, so "
                      "the refusal above it is the only thing protecting it")
    if not counts:
        return BLOCKED, "the cascade destroyed nothing at all"
    return PASS, (f"{len(blocking)} blocking table(s) untouched, "
                  f"{len(counts)} table(s) counted: "
                  f"{sorted(counts)[:5]}{'…' if len(counts) > 5 else ''}")
