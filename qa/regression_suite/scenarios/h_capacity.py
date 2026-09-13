"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — how much validation a firm can actually do.

Two halves of one answer, and they live apart on purpose. What falls DUE is
computed from triggers the platform already evaluates; what a validator can
TAKE ON is declared and never inferred, because inferring it from how much
somebody happened to complete last quarter would make working late into a
higher capacity.

**The forecast states its own assumption.** Dividing work by capacity assumes
effort is comparable across tiers, and it is weighted from a published table
rather than counted — a forecast that hid that assumption is one people act
on.

**The inverted queue is computed rather than noticed.** A list sorted by due
date puts a Tier 4 model in front of a Tier 1 whenever its date came first,
and that is invisible in exactly the ordering every backlog is kept in.
"""
from __future__ import annotations

from core.validation.capacity import _inversion
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

C = "/api/v1/validator-capacity"


def _engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("validation_capacity")


def _code(exc) -> str:
    return getattr(exc, "code", "") or f"{exc}"


@case("QA-AM-163", "Declare a capacity of zero")
def am_163(ctx: Ctx) -> Result:
    """A zero divides into an infinite forecast. And it is better expressed
    by not declaring one at all — *this person does no validation* and *this
    person can take on no more* are different facts."""
    from core.validation.common import ValidationError
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no validation capacity service is wired"
    for value in (0.0, -3.0):
        try:
            engine.declare("person/v", value, actor="qa")
        except ValidationError as exc:
            if "infinite" not in f"{exc}" and "zero" not in f"{exc}":
                return FAIL, f"a capacity of {value} refused: {f'{exc}'[:110]}"
            continue
        return FAIL, f"a capacity of {value} was declared"
    try:
        engine.declare("   ", 5.0, actor="qa")
    except ValidationError:
        return PASS, "zero, negative and an unowned capacity all refused"
    return FAIL, "a capacity belonging to nobody was declared"


@case("QA-AM-164", "Declare a capacity twice for one person")
def am_164(ctx: Ctx) -> Result:
    """The row is REPLACED rather than appended, so a person has one capacity
    and not a history the forecast has to choose between — and the evidence
    node carries what it was, so the change is still findable."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no validation capacity service is wired"
    who = ctx.unique("person/v")
    engine.declare(who, 4.0, actor="qa")
    engine.declare(who, 9.0, actor="qa")
    rows = [r for r in engine.declared() if r["validator"] == who]
    if len(rows) != 1:
        return FAIL, (f"declaring twice left {len(rows)} rows, so the forecast "
                      f"has to choose which capacity is current")
    if rows[0]["episodes_per_quarter"] != 9.0:
        return FAIL, f"the current capacity reads {rows[0]['episodes_per_quarter']}"
    evidence = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    if evidence is None:
        return BLOCKED, "no evidence engine is wired"
    nodes = [n for n in evidence.repo.many()
             if n.get("kind") == "validator_capacity_declared"
             and who in f"{n.get('payload') or {}}"]
    if len(nodes) < 2:
        return FAIL, f"two declarations wrote {len(nodes)} evidence node(s)"
    if (nodes[-1].get("payload") or {}).get("was") != 4.0:
        return FAIL, ("the second declaration does not record what the "
                      "capacity was, so the change is not findable")
    return PASS, "one row at 9.0, and the chain records it was 4.0"


@case("QA-AM-165",
      "Workload where a validator carries episodes and has declared none")
def am_165(ctx: Ctx) -> Result:
    """`utilisation` is null rather than zero, and the validator is NAMED
    under `capacity_not_declared`. A zero would sort them to the bottom of a
    list ordered by utilisation, which is where somebody carrying work they
    never sized would be least visible."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no validation capacity service is wired"
    report = engine.by_validator()
    undeclared = report.get("capacity_not_declared")
    if undeclared is None:
        return FAIL, "the workload does not report who has declared nothing"
    for row in report.get("validators") or []:
        if not row.get("capacity_declared"):
            if row.get("utilisation") is not None:
                return FAIL, (f"'{row['validator']}' declared no capacity and "
                              f"reports a utilisation of "
                              f"{row['utilisation']} — a number computed from "
                              f"a denominator nobody gave")
            if row.get("overloaded"):
                return FAIL, ("somebody who declared no capacity is reported "
                              "overloaded against it")
            if row["validator"] not in undeclared:
                return FAIL, (f"'{row['validator']}' has no capacity and is "
                              f"not named under capacity_not_declared")
    return PASS, (f"{len(undeclared)} validator(s) with no declared capacity, "
                  f"utilisation null and each named")


@case("QA-AM-168", "Queue where a Tier 4 model is due before a Tier 1")
def am_168(ctx: Ctx) -> Result:
    """The inversion is computed. A list sorted by due date is how every
    backlog is kept, and in that ordering lower-risk work sitting in front of
    higher-risk work is invisible — so it is reported with the models on both
    sides of it."""
    rows = [{"urn": "maya://model/low", "tier": 4, "last_validated": 100.0},
            {"urn": "maya://model/high", "tier": 1, "last_validated": 200.0}]
    got = _inversion(rows)
    if not got or not got.get("inverted"):
        return FAIL, (f"a tier 4 model dated before a tier 1 is not reported "
                      f"as an inversion: {got}")
    ahead = got.get("ahead") or got.get("rows") or []
    said = f"{got}"
    if "maya://model/low" not in said:
        return FAIL, "the inversion does not name the model in front"
    if "maya://model/high" not in said:
        return FAIL, "the inversion does not name what it is in front of"
    ordered = [{"urn": "maya://model/high", "tier": 1, "last_validated": 100.0},
               {"urn": "maya://model/low", "tier": 4, "last_validated": 200.0}]
    if (_inversion(ordered) or {}).get("inverted"):
        return FAIL, "a correctly ordered queue is reported as inverted"
    del ahead
    return PASS, "inverted, naming the model in front and what it precedes"


@case("QA-AM-4900", "A queue where every model is the same tier")
def am_4900(ctx: Ctx) -> Result:
    """No inversion is possible, and reporting one would make the warning
    meaningless on the estate that most needs it — a book of one tier is
    exactly where a due-date ordering is the right ordering."""
    rows = [{"urn": f"maya://model/m{i}", "tier": 2,
             "last_validated": 100.0 + i} for i in range(5)]
    got = _inversion(rows)
    if got and got.get("inverted"):
        return FAIL, f"five models of one tier are reported as inverted: {got}"
    if _inversion([]) and _inversion([]).get("inverted"):
        return FAIL, "an empty queue is reported as inverted"
    one = [{"urn": "maya://model/only", "tier": 1, "last_validated": 1.0}]
    if _inversion(one) and _inversion(one).get("inverted"):
        return FAIL, "a queue of one is reported as inverted"
    return PASS, "one tier, empty and single-model queues are never inverted"


@case("QA-AM-4901", "A model with no tier in the queue")
def am_4901(ctx: Ctx) -> Result:
    """An untiered model sorts as tier 9 — behind everything — because a
    model whose depth of control nobody has decided is not one to put in
    front of a Tier 1. Treating the absence as tier 1 would let an
    unassessed model jump the queue."""
    rows = [{"urn": "maya://model/untiered", "tier": None,
             "last_validated": 100.0},
            {"urn": "maya://model/high", "tier": 1, "last_validated": 200.0}]
    got = _inversion(rows)
    if not (got or {}).get("inverted"):
        return FAIL, ("an untiered model dated before a tier 1 is not an "
                      "inversion, so an unassessed model sits in front "
                      "unremarked")
    reversed_rows = [{"urn": "maya://model/high", "tier": 1,
                      "last_validated": 100.0},
                     {"urn": "maya://model/untiered", "tier": None,
                      "last_validated": 200.0}]
    if (_inversion(reversed_rows) or {}).get("inverted"):
        return FAIL, ("a tier 1 in front of an untiered model is reported as "
                      "an inversion, so the absence is ranking as high risk")
    return PASS, "an untiered model ranks behind, never in front"


@case("QA-AM-167", "Forecast with work due and no capacity declared anywhere")
def am_167(ctx: Ctx) -> Result:
    """The detail says this is a statement about what nobody has declared
    rather than about a shortfall. Dividing by nothing and reporting an
    infinite gap would be the arithmetic answering a question nobody asked."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no validation capacity service is wired"

    class Nothing:
        @staticmethod
        def many(**_where):
            return []

        @staticmethod
        def one(**_where):
            return None

    was, engine.capacities = engine.capacities, Nothing()
    try:
        report = engine.forecast()
    except ZeroDivisionError:
        return FAIL, ("the forecast divides by zero when nobody has declared "
                      "a capacity")
    finally:
        engine.capacities = was
    if report.get("capacity") not in (0, 0.0, None):
        return FAIL, f"capacity reads {report.get('capacity')} with none declared"
    detail = report.get("detail") or ""
    if "declar" not in detail:
        return FAIL, (f"the forecast does not say the gap is undeclared "
                      f"capacity rather than a shortfall: {detail[:130]}")
    return PASS, f"no division by zero, and the detail says why: {detail[:80]}"


@case("QA-AM-4902", "The forecast states its own assumption")
def am_4902(ctx: Ctx) -> Result:
    """Dividing work by capacity assumes effort is comparable across tiers.
    It is weighted from a published table rather than counted, and a
    forecast that hid that assumption is one people act on."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no validation capacity service is wired"
    report = engine.forecast()
    assumes = report.get("assumes")
    if not assumes:
        return FAIL, ("the forecast states no assumption, so a number resting "
                      "on a weighting reads like a count")
    if "weight" not in assumes and "effort" not in assumes:
        return FAIL, f"the assumption does not name the weighting: {assumes}"
    for field in ("shortfall", "inverted_queue"):
        if field not in report:
            return FAIL, f"the forecast carries no '{field}'"
    if (report.get("shortfall") or 0) < 0:
        return FAIL, (f"the shortfall is {report['shortfall']}: a surplus is "
                      f"not a negative shortfall, and it sums wrongly")
    return PASS, f"assumption stated: {assumes[:80]}"


@case("QA-AM-169", "Queue with `horizon_days=0`")
def am_169(ctx: Ctx) -> Result:
    """Only what is already due. A zero horizon read as *everything* would
    make the narrowest possible ask return the widest possible answer."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no validation capacity service is wired"
    narrow = engine.due_within(horizon_days=0.0)
    wide = engine.due_within(horizon_days=3650.0)
    if narrow.get("count") is None or wide.get("count") is None:
        return FAIL, "the queue reports no count"
    if narrow["count"] > wide["count"]:
        return FAIL, (f"a zero horizon returned {narrow['count']} models and a "
                      f"ten-year one {wide['count']}: zero is being read as "
                      f"unbounded")
    if narrow.get("horizon_days") not in (0, 0.0, None):
        return FAIL, f"the horizon is echoed as {narrow.get('horizon_days')}"
    return PASS, (f"zero horizon -> {narrow['count']}, ten years -> "
                  f"{wide['count']}")


@case("QA-AM-171",
      "Queue on an instance built without the validation plans")
def am_171(ctx: Ctx) -> Result:
    """The queue is computed from re-validation triggers, and without the
    plans there are none. It has to say so rather than answering an empty
    queue, because an empty queue reads as an estate with nothing due."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no validation capacity service is wired"
    was, engine.plans = engine.plans, None
    try:
        report = engine.due_within()
    except Exception as exc:
        code = getattr(exc, "code", "") or type(exc).__name__
        if "plan" not in f"{exc}".lower():
            return FAIL, f"refused '{code}' without naming the plans: {exc}"
        return PASS, f"refused, naming the missing plans: {f'{exc}'[:80]}"
    finally:
        engine.plans = was
    if report.get("count"):
        return FAIL, f"with no plans wired the queue holds {report['count']}"
    detail = report.get("detail") or ""
    if "plan" not in detail.lower():
        return FAIL, (f"an instance with no plans answers an empty queue with "
                      f"no explanation, which reads as nothing being due: "
                      f"{detail[:120]}")
    return PASS, f"empty and says why: {detail[:80]}"
