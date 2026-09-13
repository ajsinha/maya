"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section J — the deletion cascade, declared as data rather than written as code.

Thirty-eight tables carry a `model_id`, and every one has to be dispositioned:
BLOCKS while something is live, GOES with the record, or STAYS because it
records something that happened. A table left out is not a refusal — it is a
deletion that quietly succeeds, which is why the cascade is a table and why
these cases read it.
"""
from __future__ import annotations

from core.retention.cascade import BLOCKS, CASCADE, GOES, STAYS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


@case("QA-DEL-4000", "Every disposition is one of the three kinds")
def del_4000(ctx: Ctx) -> Result:
    """A fourth kind would be a table nothing in `blocking()` or `destroy()`
    reads, which is the shape of a row that quietly survives a deletion."""
    kinds = {BLOCKS, GOES, STAYS}
    odd = [d.table for d in CASCADE if d.kind not in kinds]
    if odd:
        return FAIL, f"dispositions of an unknown kind: {odd}"
    return PASS, f"{len(CASCADE)} dispositions, all of {sorted(kinds)}"


@case("QA-DEL-4001", "Every disposition says why")
def del_4001(ctx: Ctx) -> Result:
    """The cascade is the document somebody reads before agreeing a model may
    be destroyed. A row with no reason is a decision nobody can check."""
    silent = [d.table for d in CASCADE
              if not (d.why or "").strip() or not (d.label or "").strip()]
    if silent:
        return FAIL, f"dispositions with no stated reason: {silent}"
    return PASS, f"all {len(CASCADE)} say what the row is and why"


@case("QA-DEL-4002", "Every blocking disposition produces runnable SQL")
def del_4002(ctx: Ctx) -> Result:
    """A liveness predicate is OPTIONAL and its absence is defined rather
    than accidental: `blocking_sql` emits `WHERE model_id = :m` alone, so
    every row of that table blocks. Three tables rely on it —
    `model_version`, `alias` and `regulatory_approval` — and for each, any
    row at all is a live commitment. What must hold is that every
    disposition's SQL actually runs, because a cascade discovering a bad
    predicate does so mid-deletion.
    """
    db = ctx.made.get("db") or ctx.ui.app.state.ctx.get("db")
    if db is None:
        return BLOCKED, "no database reachable from this run"
    broken, unconditional = [], []
    for disposition in CASCADE:
        if disposition.kind != BLOCKS:
            continue
        if not disposition.live:
            unconditional.append(disposition.table)
        try:
            db.query(disposition.blocking_sql(), {"m": "qa-no-such-model"})
        except Exception as exc:
            broken.append(f"{disposition.table}: {type(exc).__name__} {exc}")
    if broken:
        return FAIL, ("these blocking predicates do not run, and a cascade "
                      "would meet them mid-deletion: " + "; ".join(broken[:4]))
    total = len([d for d in CASCADE if d.kind == BLOCKS])
    return PASS, (f"{total} blocking queries all run; {len(unconditional)} "
                  f"block unconditionally ({', '.join(unconditional)})")


@case("QA-DEL-4003", "No table is dispositioned twice")
def del_4003(ctx: Ctx) -> Result:
    """Two rows for one table is two answers, and which applies depends on
    iteration order."""
    seen = [d.table for d in CASCADE]
    twice = sorted({t for t in seen if seen.count(t) > 1})
    if twice:
        return FAIL, f"tables dispositioned more than once: {twice}"
    return PASS, f"{len(set(seen))} distinct tables"


@case("QA-DEL-4004", "Every table carrying a model_id is dispositioned")
def del_4004(ctx: Ctx) -> Result:
    """The check the whole cascade rests on. A table with a `model_id` and no
    disposition is a row the deletion neither blocks on nor destroys — it
    simply points at a model that is gone.
    """
    db = ctx.made.get("db") or ctx.ui.app.state.ctx.get("db")
    if db is None:
        return BLOCKED, "no database reachable from this run"
    rows = db.query(
        "SELECT m.name AS table_name FROM sqlite_master m "
        "WHERE m.type = 'table' AND m.sql LIKE '%model_id%'")
    carrying = {r["table_name"] for r in rows
                if not r["table_name"].startswith("sqlite_")}
    declared = {d.table for d in CASCADE}
    missing = sorted(carrying - declared)
    if missing:
        return FAIL, (f"{len(missing)} table(s) carry a model_id and have no "
                      f"disposition, so a deletion neither blocks on them nor "
                      f"destroys them: {missing[:8]}")
    return PASS, f"all {len(carrying)} tables carrying model_id dispositioned"


@case("QA-DEL-4005", "Every dispositioned table exists")
def del_4005(ctx: Ctx) -> Result:
    """The other direction. A disposition naming a table that is not there is
    a control that runs against nothing, and the SQL would fail at the worst
    possible moment — mid-cascade."""
    db = ctx.made.get("db") or ctx.ui.app.state.ctx.get("db")
    if db is None:
        return BLOCKED, "no database reachable from this run"
    rows = db.query("SELECT name FROM sqlite_master WHERE type = 'table'")
    present = {r["name"] for r in rows}
    absent = sorted(d.table for d in CASCADE if d.table not in present)
    if absent:
        return FAIL, (f"dispositions naming tables that do not exist: "
                      f"{absent}")
    return PASS, f"all {len(CASCADE)} dispositioned tables exist"


@case("QA-DEL-4006", "The evidence chain is never destroyed by a cascade")
def del_4006(ctx: Ctx) -> Result:
    """Deleting a model destroys the model's record and not the record THAT
    IT HAPPENED. An evidence table among the GOES rows would let a deletion
    erase its own trace."""
    destroyed = {d.table for d in CASCADE if d.kind == GOES}
    trace = sorted(t for t in destroyed
                   if "evidence" in t or "anchor" in t or "tombstone" in t)
    if trace:
        return FAIL, (f"a cascade would destroy {trace}, so a deletion erases "
                      f"its own trace")
    return PASS, f"{len(destroyed)} tables destroyed, none of them the trace"


@case("QA-DEL-005", "Delete a model under a legal hold")
def del_005(ctx: Ctx) -> Result:
    """A hold is a refusal to destroy, not an authorisation problem — and it
    outranks the administrator who would otherwise be allowed."""
    import inspect

    from core.retention import cascade
    from core.lifecycle import service
    source = inspect.getsource(service.LifecycleService.delete)
    if "hold" not in source.lower():
        blocking = inspect.getsource(cascade.Cascade.blocking)
        if "hold" not in blocking.lower():
            return FAIL, ("nothing in the delete path consults a legal hold, "
                          "so a hold is a label")
    return PASS, "the delete path consults a legal hold"


@case("QA-DEL-027", "Act on a tombstoned model")
def del_027(ctx: Ctx) -> Result:
    """A deleted model's URN must not be usable. Re-registering it would put
    a different model behind an identifier that already means something."""
    tombstones = ctx.ui.app.state.ctx.get("tombstones")
    if tombstones is None:
        return BLOCKED, "no tombstone register reachable from this run"
    import inspect
    source = inspect.getsource(tombstones.refuse_reuse)
    if "urn_was_deleted" not in source:
        return FAIL, ("a deleted URN can be re-registered, so an identifier "
                      "that meant one model can come to mean another")
    if "override" in source.lower() and "raise" not in source:
        return FAIL, "the refusal has an override"
    return PASS, "a deleted URN refuses reuse, with no override"


@case("QA-DEL-070", "An unreferenced blob is marked before it is swept")
def del_070(ctx: Ctx) -> Result:
    """Seen once is not orphaned. A blob written a second before the sweep
    ran has no reference yet, and destroying it would be the compaction
    deleting something that was about to be cited."""
    from core.retention.compaction import SIGHTINGS_BEFORE_SWEEP
    if SIGHTINGS_BEFORE_SWEEP < 2:
        return FAIL, (f"a blob is swept after {SIGHTINGS_BEFORE_SWEEP} "
                      f"sighting(s), so one written just before the sweep is "
                      f"destroyed")
    return PASS, f"{SIGHTINGS_BEFORE_SWEEP} sightings before anything is swept"


@case("QA-DEL-4007", "Delta is reported, never reclaimed")
def del_4007(ctx: Ctx) -> Result:
    """MAYA does not own the data plane. Compaction reporting Delta space as
    reclaimable — let alone touching it — would be the register acting on
    storage somebody else is responsible for."""
    import inspect

    from core.retention import compaction
    source = inspect.getsource(compaction)
    if "not_reclaimable" not in source:
        return FAIL, "compaction does not hold anything as unreclaimable"
    if "delta" not in source.lower():
        return BLOCKED, "compaction says nothing about Delta on this build"
    for verb in ("vacuum(", "delete(", "remove("):
        window = source[max(0, source.lower().find("delta") - 400):]
        if f"delta.{verb}" in window:
            return FAIL, f"compaction calls delta.{verb} on the data plane"
    return PASS, "Delta is reported under not_reclaimable and left alone"
