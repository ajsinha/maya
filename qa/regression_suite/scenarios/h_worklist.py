"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the list of work somebody can actually do.

**A list of work somebody cannot act on is a list they learn to ignore, and
ignoring the list is how the control stops operating.** So it is filtered by
permission AND by scope, and what is filtered out is counted rather than
hidden: `others` says how much is outstanding for other roles, because a short
list and an empty estate must not read the same.

Every item is DERIVED. Nothing here is a row somebody has to remember to
clear — an acknowledgement item disappears the moment the owner accepts the
finding, with nothing to tidy up.

And a subsystem that is absent or refusing must not blank the whole list. Nine
sources feed it; one raising skips its own items and leaves the other eight,
because a worklist that went empty because monitoring was down is one that
says the estate is clear.
"""
from __future__ import annotations

from core.estate.worklist import (_MATERIALITY, HORIZON_DAYS, ORDER,
                                  _urgency)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

DAY = 86400.0
M = "/api/v1/models"
F = "/api/v1/findings"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _worklist(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("worklist")


def _model(ctx: Ctx) -> tuple:
    name = ctx.unique("wl")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE},
                 auth=ctx.people["owner"])
    return name, urn


def _raise(ctx: Ctx, urn: str, **over) -> str:
    body = {"urn": urn, "severity": "High", "title": ctx.unique("finding"),
            "owner": "person/owner", "description": "qa",
            "category": "general", "source": "validation"}
    body.update(over)
    made = ctx.api.post(F, json=body, auth=ctx.people["risk"])
    return made.json().get("id", "") if made.status_code < 400 else ""


@case("QA-AM-319",
      "Worklist ordering with an overdue item, a due item and an open item")
def am_319(ctx: Ctx) -> Result:
    """Overdue, then due, then open — and within a band by date, then by
    model, so the order is stable across reads. A list that reshuffled
    between two page loads is one nobody can work down."""
    if ORDER != {"overdue": 0, "due": 1, "open": 2}:
        return FAIL, f"the ordering is {ORDER}"
    worklist = _worklist(ctx)
    if worklist is None:
        return BLOCKED, "no worklist is wired"
    import inspect
    source = inspect.getsource(type(worklist).across)
    if "ORDER[i.urgency]" not in source:
        return FAIL, "the sort does not key on urgency first"
    if "i.due_at" not in source or "i.urn" not in source:
        return FAIL, ("the sort does not break ties by date and model, so two "
                      "reads can order the same items differently")
    return PASS, "overdue, due, open — then by date, then by model"


@case("QA-AM-4950", "The urgency boundary")
def am_4950(ctx: Ctx) -> Result:
    """A date in the past is overdue, one inside the horizon is due, one
    beyond it is open, and one absent is open rather than overdue — an item
    with no date is not late, it is unscheduled, and treating the absence as
    lateness would fill the list with everything."""
    now = 1_700_000_000.0
    if _urgency(None, now) != "open":
        return FAIL, ("an item with no due date is not 'open', so an "
                      "unscheduled item reads as late")
    if _urgency(now - 1.0, now) != "overdue":
        return FAIL, "a date a second in the past is not overdue"
    if _urgency(now + 1.0, now) != "due":
        return FAIL, "a date a second away is not due"
    inside = _urgency(now + (HORIZON_DAYS * DAY) - 3600, now)
    if inside != "due":
        return FAIL, f"an hour inside the horizon reads '{inside}'"
    outside = _urgency(now + (HORIZON_DAYS * DAY) + 3600, now)
    if outside != "open":
        return FAIL, f"an hour beyond the horizon reads '{outside}'"
    at = _urgency(now + HORIZON_DAYS * DAY, now)
    if at != "open":
        return FAIL, (f"exactly {HORIZON_DAYS} days away reads '{at}'; the "
                      f"comparison is `<` so the boundary itself is not yet "
                      f"due")
    return PASS, (f"absent is open, past is overdue, inside {HORIZON_DAYS} "
                  f"days is due, the boundary itself is not")


@case("QA-AM-312", "A low-severity finding with months left")
def am_312(ctx: Ctx) -> Result:
    """Absent. A worklist carrying everything outstanding is a list nobody
    works down, and an item nobody needs to act on this month is exactly
    what makes it that."""
    worklist = _worklist(ctx)
    if worklist is None:
        return BLOCKED, "no worklist is wired"
    import inspect
    source = inspect.getsource(type(worklist)._findings)
    if 'urgency == "open"' not in source:
        return FAIL, "the findings source does not filter on urgency at all"
    if "not f[\"blocking\"]" not in source and "not f['blocking']" not in source:
        return FAIL, ("the filter does not exempt a blocking finding, so a "
                      "blocking item with months left disappears")
    if "continue" not in source:
        return FAIL, "nothing is skipped, so every open finding is listed"
    return PASS, "an open, non-blocking finding is skipped"


@case("QA-AM-313", "A Low finding that is blocking")
def am_313(ctx: Ctx) -> Result:
    """Present whatever its date, because blocking is not about severity —
    it refuses warrant resolution and alias promotion, so a Low finding that
    blocks is stopping a model from being served."""
    _, urn = _model(ctx)
    worklist = _worklist(ctx)
    findings = ctx.ui.app.state.ctx.get("findings")
    if worklist is None or findings is None:
        return BLOCKED, "the worklist or the findings register is not wired"
    fid = _raise(ctx, urn, severity="Low", blocking=True)
    if not fid:
        return BLOCKED, "the blocking finding could not be raised"
    row = findings.require(fid)
    findings.findings.set({"due_at": row["raised_at"] + 365 * DAY}, id=fid)
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    items = worklist.for_model(model)
    mine = [i for i in items if i.kind == "finding"]
    if not mine:
        return FAIL, ("a blocking Low finding a year out is absent from the "
                      "worklist, so a model being refused service has no row")
    if "blocking" not in mine[0].title.lower():
        return FAIL, f"the item does not say it blocks: {mine[0].title}"
    if "refuses warrant resolution" not in mine[0].detail:
        return FAIL, (f"the item does not say what blocking costs: "
                      f"{mine[0].detail[:110]}")
    return PASS, f"present with urgency '{mine[0].urgency}', naming the cost"


@case("QA-AM-315", "A subsystem that raises during a worklist build")
def am_315(ctx: Ctx) -> Result:
    """Its items are skipped and every other source still reports. A
    worklist that went empty because monitoring was down is one that says
    the estate is clear."""
    worklist = _worklist(ctx)
    if worklist is None:
        return BLOCKED, "no worklist is wired"
    _, urn = _model(ctx)
    _raise(ctx, urn, blocking=True)
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    before = worklist.for_model(model)
    if not before:
        return BLOCKED, "the model has no worklist items to lose"

    def explode(*_a, **_k):
        raise RuntimeError("the monitoring service is down")

    was = type(worklist)._monitors
    type(worklist)._monitors = explode
    try:
        after = worklist.for_model(model)
    finally:
        type(worklist)._monitors = was
    if not after:
        return FAIL, ("one failing source blanked the whole worklist, so the "
                      "estate reads as clear because monitoring is down")
    kinds = {i.kind for i in after}
    if "finding" not in kinds:
        return FAIL, f"the finding item was lost too: {kinds}"
    return PASS, f"{len(after)} item(s) survive one source raising: {sorted(kinds)}"


@case("QA-AM-314",
      "An unaccepted escalated finding, then the owner accepts it")
def am_314(ctx: Ctx) -> Result:
    """The item disappears with nothing to tidy up. Every item here is
    derived, so the reminder cycle clears itself the moment the owner
    accepts — a row somebody has to remember to close is a row that stays
    after the work is done."""
    worklist = _worklist(ctx)
    findings = ctx.ui.app.state.ctx.get("findings")
    if worklist is None or findings is None:
        return BLOCKED, "the worklist or the findings register is not wired"
    _, urn = _model(ctx)
    fid = _raise(ctx, urn)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    row = findings.require(fid)
    findings.findings.set({"raised_at": row["raised_at"] - 30 * DAY}, id=fid)
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    before = [i for i in worklist.for_model(model)
              if i.kind == "finding_acknowledgement"]
    if not before:
        return BLOCKED, "no acknowledgement item was derived"
    got = ctx.api.post(f"{F}/{fid}/acknowledge",
                       json={"days": 10.0, "plan": "repoint the feature"},
                       auth=ctx.people["owner"])
    if got.status_code >= 400:
        return BLOCKED, f"the acknowledgement failed: {got.text[:140]}"
    after = [i for i in worklist.for_model(model)
             if i.kind == "finding_acknowledgement"]
    if after:
        return FAIL, ("the acknowledgement item survives the owner accepting "
                      "the finding, so the reminder has to be tidied by hand")
    return PASS, "the item disappears the moment the owner accepts"


@case("QA-AM-316", "The `others` count under a scoped reader")
def am_316(ctx: Ctx) -> Result:
    """`others` counts what is outstanding for other ROLES, over the models
    the reader can see. Counting work on models they are refused would tell
    them how much exists elsewhere in the bank, which is a scope leak in a
    number."""
    worklist = _worklist(ctx)
    authz = ctx.ui.app.state.ctx.get("authz")
    registry = ctx.ui.app.state.ctx.get("registry")
    if not (worklist and authz and registry):
        return BLOCKED, "the worklist, authz or registry is not wired"
    import inspect
    source = inspect.getsource(type(worklist).mine)
    if "authz.visible" not in source:
        return FAIL, ("the worklist is not scoped, so a reader sees work on "
                      "models they are refused")
    at_visible = source.find("authz.visible")
    at_across = source.find("self.across")
    if at_visible > at_across:
        return FAIL, ("the list is built before the scope is applied, so "
                      "`others` counts work on models the reader cannot see")
    if "len(everything) - len(mine)" not in source:
        return FAIL, "`others` is not the difference over the visible set"
    return PASS, "scoped first, and `others` is counted over what is visible"


@case("QA-AM-311",
      "A model owner who owns a blocking finding sees it on their list")
def am_311(ctx: Ctx) -> Result:
    """Filtered by PERMISSION as well as scope: the item names
    `finding:close`, and an owner who cannot close a finding should not be
    handed one to close. The permission is on the item so the filter cannot
    drift from what the row asks for."""
    worklist = _worklist(ctx)
    registry = ctx.ui.app.state.ctx.get("registry")
    authz = ctx.ui.app.state.ctx.get("authz")
    if not (worklist and registry and authz):
        return BLOCKED, "the worklist, registry or authz is not wired"
    _, urn = _model(ctx)
    if not _raise(ctx, urn, blocking=True):
        return BLOCKED, "the finding could not be raised"
    model = registry.require(urn)
    items = [i for i in worklist.for_model(model) if i.kind == "finding"]
    if not items:
        return BLOCKED, "no finding item was derived"
    if items[0].permission != "finding:close":
        return FAIL, (f"the item asks for '{items[0].permission}' rather than "
                      f"the permission its action needs")
    people = ctx.ui.app.state.ctx.get("principals")
    if people is None:
        return BLOCKED, "no principal register is wired"
    owner = people.require("owner")
    validator = people.require("validator")
    if authz.permits(owner, "finding:close"):
        return FAIL, ("the model owner holds finding:close, so this run "
                      "cannot show the filter excluding anybody")
    if not authz.permits(validator, "finding:close"):
        return FAIL, "the validator does not hold finding:close either"
    mine = worklist.mine(owner, authz, [model])
    theirs = worklist.mine(validator, authz, [model])
    if any(i["kind"] == "finding" for i in mine["items"]):
        return FAIL, ("the owner is handed a finding to close that they "
                      "cannot close")
    if not any(i["kind"] == "finding" for i in theirs["items"]):
        return FAIL, "the validator who can close it is not offered it"
    if not mine.get("others"):
        return FAIL, ("the owner's list hides the finding and counts nothing "
                      "under `others`, so a short list reads as a clear estate")
    return PASS, (f"the owner sees {mine['others']} item(s) under others; the "
                  f"validator is offered the close")


@case("QA-AM-4951", "An item always names the permission its action needs")
def am_4951(ctx: Ctx) -> Result:
    """The filter reads the permission off the item, so a source that forgot
    one would produce a row nobody is offered — or, worse, one everybody is.
    Checked across every source by parsing the module rather than at one, so a
    tenth source added later is covered without anybody remembering to."""
    import ast
    import inspect

    from core.estate import worklist as module
    tree = ast.parse(inspect.getsource(module))
    built = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Item"):
            continue
        built += 1
        named = {k.arg for k in node.keywords}
        # Positionally: kind, urn, title, detail, permission.
        got = "permission" in named or len(node.args) >= 5
        if not got:
            return FAIL, (f"an Item built at line {node.lineno} names no "
                          f"permission, so the filter cannot tell who may act "
                          f"on it")
        value = None
        if "permission" in named:
            value = next(k.value for k in node.keywords
                         if k.arg == "permission")
        elif len(node.args) >= 5:
            value = node.args[4]
        if isinstance(value, ast.Constant) and ":" not in str(value.value):
            return FAIL, (f"the Item at line {node.lineno} names "
                          f"'{value.value}', which is not a permission")
    if built < 9:
        return BLOCKED, f"only {built} Item(s) are constructed in the module"
    return PASS, f"{built} Items constructed, every one naming a permission"


# ------------------------------------------------------- baseline debt on a list
B = "/api/v1/baseline"


def _imported(ctx: Ctx) -> str:
    """A model that arrived through the baseline import, so it carries a gap
    for every check in the baseline register."""
    name = ctx.unique("wlb")
    urn = f"maya://model/{name}"
    got = ctx.api.post(f"{B}/imports",
                       json={"source": "legacy-inventory", "note": "QA",
                             "models": [{"urn": urn, "name": name,
                                         "model_class": "logistic",
                                         "domain": "credit",
                                         "owner": "person/owner",
                                         "legal_entity": "LE-US-01",
                                         "purpose": "credit_decision",
                                         "tier": 3}]},
                       auth=ctx.people["risk"])
    return urn if got.status_code < 400 else ""


@case("QA-AM-317", "Baseline debt on a freshly imported model")
def am_317(ctx: Ctx) -> Result:
    """One item per model, not one per gap. A freshly baselined model has a
    gap for every check in the register, and listing them individually
    buries every other kind of work under a wall of rows that all say the
    same thing: this model arrived without its evidence."""
    from core.baseline.gaps import GAPS
    worklist = _worklist(ctx)
    debts = ctx.ui.app.state.ctx.get("debts")
    if worklist is None or debts is None:
        return BLOCKED, "the worklist or the debt register is not wired"
    urn = _imported(ctx)
    if not urn:
        return BLOCKED, "the baseline import failed"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    outstanding = debts.open_for(model["id"])
    if len(outstanding) < 2:
        return BLOCKED, f"the import raised {len(outstanding)} debt item(s)"
    items = [i for i in worklist.for_model(model) if i.kind == "debt"]
    if len(items) != 1:
        return FAIL, (f"{len(items)} debt rows on the worklist for "
                      f"{len(outstanding)} gaps — one model's arrival buries "
                      f"every other kind of work")
    row = items[0]
    if str(len(outstanding)) not in row.title:
        return FAIL, f"the row does not name the count: {row.title}"
    if str(len(outstanding)) not in row.detail:
        return FAIL, (f"the row does not say how many are without a plan: "
                      f"{row.detail[:140]}")
    worst = row.detail
    if not any(m in worst for m in _MATERIALITY):
        return FAIL, f"the row names no materiality: {worst[:140]}"
    if row.permission != "baseline:plan":
        return FAIL, f"the row asks for '{row.permission}'"
    return PASS, (f"one row for {len(outstanding)} of {len(GAPS)} gaps: "
                  f"{row.title}")


@case("QA-AM-318", "Debt where every gap has a dated plan and none is near expiry")
def am_318(ctx: Ctx) -> Result:
    """No debt item at all. Planned debt that is not approaching its expiry
    is not yet worth anyone's attention, and a list that keeps showing it is
    a list somebody learns to scroll past."""
    worklist = _worklist(ctx)
    debts = ctx.ui.app.state.ctx.get("debts")
    if worklist is None or debts is None:
        return BLOCKED, "the worklist or the debt register is not wired"
    urn = _imported(ctx)
    if not urn:
        return BLOCKED, "the baseline import failed"
    model = ctx.ui.app.state.ctx["registry"].require(urn)
    outstanding = debts.open_for(model["id"])
    if not outstanding:
        return BLOCKED, "the import raised no debt"
    before = [i for i in worklist.for_model(model) if i.kind == "debt"]
    if not before:
        return BLOCKED, "there was no debt item to clear"
    import time as _time
    horizon = _time.time() + HORIZON_DAYS * DAY
    soon = [d for d in outstanding if d["expires_at"] < horizon]
    if soon:
        return BLOCKED, (f"{len(soon)} gap(s) expire inside the "
                         f"{HORIZON_DAYS:g}-day horizon, so planning them "
                         f"would not clear the row")
    for item in outstanding:
        got = ctx.api.post(f"{B}/debt/{item['id']}/plan",
                           json={"plan": "closed by 2027-03-31 under REM-88"},
                           auth=ctx.people["risk"])
        if got.status_code >= 400:
            return BLOCKED, f"a gap could not be planned: {got.text[:150]}"
    after = [i for i in worklist.for_model(model) if i.kind == "debt"]
    if after:
        return FAIL, (f"the debt row survives every gap having a dated plan "
                      f"months from expiry: {after[0].title}")
    return PASS, (f"{len(outstanding)} gaps planned and the row clears; it "
                  f"returns when one is within {HORIZON_DAYS:g} days of expiry")
