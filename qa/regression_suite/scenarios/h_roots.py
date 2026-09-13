"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — one cause, many findings.

Three refusals define this module and each is a thing it deliberately does not
do. It **merges nothing**: a model whose feature stopped landing has a real
problem whatever caused it. It **infers nothing**: candidates are a suggestion
and a person asserts the grouping, because a platform that grouped on a weak
signal would eventually hide one finding behind another's closure. And
**addressing a root closes no finding**, because the point of a finding is
that somebody checked THIS MODEL is all right again — a root that closed its
children would be one act discharging obligations several different people
owe.
"""
from __future__ import annotations


from core.validation.correlation import KINDS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

R = "/api/v1/finding-roots"
F = "/api/v1/findings"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> tuple:
    name = ctx.unique("rt")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    return name, urn


def _raise(ctx: Ctx, urn: str, **over) -> str:
    body = {"urn": urn, "severity": "High", "title": ctx.unique("finding"),
            "owner": "person/owner", "description": "qa",
            "category": "general", "source": "validation"}
    body.update(over)
    made = ctx.api.post(F, json=body, auth=ctx.people["risk"])
    return made.json().get("id", "") if made.status_code < 400 else ""


def _root(ctx: Ctx, findings=(), **over):
    body = {"title": ctx.unique("root"), "kind": KINDS[0][0],
            "detail": "the upstream view stopped landing on Tuesday",
            "findings": list(findings)}
    body.update(over)
    return ctx.api.post(R, json=body, auth=ctx.people["risk"])


def _id(made) -> str:
    if made.status_code >= 400:
        return ""
    body = made.json() or {}
    return (body.get("root") or body).get("id") or body.get("root_id") or ""


@case("QA-AM-136", "Attach a list containing one unknown finding id")
def am_136(ctx: Ctx) -> Result:
    """The whole call is refused rather than part of it. A root that silently
    covers fewer findings than somebody listed is a root somebody will rely
    on — and the ones that were real must not be attached either, or a retry
    reports them as `already_attached` and the caller believes the first call
    half worked by design."""
    _name, urn = _model(ctx)
    good = _raise(ctx, urn)
    root_id = _id(_root(ctx))
    if not (good and root_id):
        return BLOCKED, "the fixture could not be built"
    got = ctx.api.post(f"{R}/{root_id}/attach",
                       json={"findings": [good, "fnd-does-not-exist"]},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(
        got, "a root was attached to a finding that does not exist")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "unknown_finding":
        return FAIL, f"refused '{code_of(got)}'"
    again = ctx.api.post(f"{R}/{root_id}/attach", json={"findings": [good]},
                         auth=ctx.people["risk"])
    if again.status_code >= 400:
        return BLOCKED, f"the retry failed: {again.text[:140]}"
    if (again.json() or {}).get("already_attached"):
        return FAIL, ("the refused call attached the good finding anyway, so "
                      "part of a refused call was written")
    return PASS, "refused 'unknown_finding', and nothing was attached"


@case("QA-AM-137", "Attach the same finding to the same root twice")
def am_137(ctx: Ctx) -> Result:
    """Reported under `already_attached` rather than refused. Re-running a
    correlation script is the ordinary case, and a refusal would make the
    second run look like a failure."""
    _name, urn = _model(ctx)
    fid = _raise(ctx, urn)
    root_id = _id(_root(ctx))
    if not (fid and root_id):
        return BLOCKED, "the fixture could not be built"
    first = ctx.api.post(f"{R}/{root_id}/attach", json={"findings": [fid]},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, f"the first attach failed: {first.text[:140]}"
    got = ctx.api.post(f"{R}/{root_id}/attach", json={"findings": [fid]},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"the second attach was refused '{code_of(got)}', so "
                      f"re-running a correlation reads as a failure")
    body = got.json() or {}
    if fid not in (body.get("already_attached") or []):
        return FAIL, (f"the repeat is not reported under already_attached: "
                      f"{body}")
    if body.get("attached"):
        return FAIL, "the repeat is also counted as newly attached"
    return PASS, "reported under already_attached, attached nothing"


@case("QA-AM-138",
      "Attach a finding that is already attached to a *different* root")
def am_138(ctx: Ctx) -> Result:
    """The finding silently moves. `attach` writes `root_id` without asking
    whether one is already set, so the first root quietly stops covering it
    — and the first root's reading gets smaller with nothing recorded about
    why. A cause somebody asserted should not be un-asserted by a later call
    that never mentions it."""
    _name, urn = _model(ctx)
    fid = _raise(ctx, urn)
    first = _id(_root(ctx))
    second = _id(_root(ctx))
    if not (fid and first and second):
        return BLOCKED, "the fixture could not be built"
    if ctx.api.post(f"{R}/{first}/attach", json={"findings": [fid]},
                    auth=ctx.people["risk"]).status_code >= 400:
        return BLOCKED, "the first attach failed"
    got = ctx.api.post(f"{R}/{second}/attach", json={"findings": [fid]},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a finding already under a "
                      f"cause is not silently moved")
    body = got.json() or {}
    if fid in (body.get("attached") or []):
        return FAIL, (f"a finding under root {first} was moved to root "
                      f"{second} by a call that never mentioned the first: "
                      f"`attach` writes `root_id` without asking whether one "
                      f"is set, so the first cause silently stops covering it "
                      f"and its reading shrinks with nothing recorded about "
                      f"why")
    return PASS, f"not moved: {body}"


@case("QA-AM-139", "Attach a finding that is already closed")
def am_139(ctx: Ctx) -> Result:
    """EXPLORATORY, and the answer should be yes. A cause is usually named
    AFTER the findings have been dealt with — the point of naming it is to
    say the six things that happened last month were one thing — and refusing
    a closed finding would make a root only assertable while the mess is
    still live."""
    _name, urn = _model(ctx)
    fid = _raise(ctx, urn)
    root_id = _id(_root(ctx))
    if not (fid and root_id):
        return BLOCKED, "the fixture could not be built"
    closed = ctx.api.post(f"{F}/{fid}/close",
                          json={"evidence": {"note": "fixed and verified"}},
                          auth=ctx.people["validator"])
    if closed.status_code >= 400:
        return BLOCKED, f"the finding could not be closed: {closed.text[:140]}"
    got = ctx.api.post(f"{R}/{root_id}/attach", json={"findings": [fid]},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a cause can only be named "
                      f"while its findings are still open, so the retrospective "
                      f"case the feature exists for cannot be recorded")
    if fid not in ((got.json() or {}).get("attached") or []):
        return FAIL, f"accepted and attached nothing: {got.json()}"
    return PASS, "a closed finding can be attached to a cause named later"


@case("QA-AM-140", "Address a root while its children are open")
def am_140(ctx: Ctx) -> Result:
    """Accepted, and `findings_closed` is zero — stated rather than implied.
    Each finding needs its own closure with its own verifier, because a root
    that closed its children would be one act discharging obligations several
    different people owe."""
    _name, urn = _model(ctx)
    a, b = _raise(ctx, urn), _raise(ctx, urn)
    root_id = _id(_root(ctx, findings=[a, b]))
    if not (a and b and root_id):
        return BLOCKED, "the fixture could not be built"
    got = ctx.api.post(f"{R}/{root_id}/address?note=the+view+was+repointed",
                       auth=ctx.people["validator"])
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a cause cannot be recorded "
                      f"as dealt with until every finding under it is closed, "
                      f"which inverts the order these things happen in")
    body = got.json() or {}
    if body.get("findings_closed") != 0:
        return FAIL, (f"addressing the root closed "
                      f"{body.get('findings_closed')} finding(s)")
    still = body.get("still_open") or []
    if sorted(still) != sorted([a, b]):
        return FAIL, f"the open children are not named: {still}"
    open_now = ctx.api.get(f"{F}?urn={urn}", auth=ctx.people["risk"])
    rows = (open_now.json() or {}).get("open") or []
    if len({f["id"] for f in rows} & {a, b}) != 2:
        return FAIL, "a child finding was closed by addressing the root"
    return PASS, f"addressed, 0 closed, {len(still)} named as still open"


@case("QA-AM-141", "Address the same root twice")
def am_141(ctx: Ctx) -> Result:
    """The second would rewrite who dealt with the cause and how."""
    root_id = _id(_root(ctx))
    if not root_id:
        return BLOCKED, "the root could not be opened"
    first = ctx.api.post(f"{R}/{root_id}/address?note=repointed",
                         auth=ctx.people["validator"])
    if first.status_code >= 400:
        return BLOCKED, f"the first address failed: {first.text[:140]}"
    got = ctx.api.post(f"{R}/{root_id}/address?note=something+else",
                       auth=ctx.people["validator"])
    outcome = refused_by_the_control(got, "a root was addressed twice")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "root_already_addressed":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'root_already_addressed'"


@case("QA-AM-142", "Address with an empty note")
def am_142(ctx: Ctx) -> Result:
    """A cause marked addressed with no account of how is a row that will be
    read as an all-clear."""
    root_id = _id(_root(ctx))
    if not root_id:
        return BLOCKED, "the root could not be opened"
    got = ctx.api.post(f"{R}/{root_id}/address?note=%20%20",
                       auth=ctx.people["validator"])
    outcome = refused_by_the_control(got, "a root addressed with no account")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "root_note_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'root_note_required' on whitespace"


@case("QA-AM-144",
      "Candidates where twelve findings share a source and category on one "
      "model")
def am_144(ctx: Ctx) -> Result:
    """No suggestion. Twelve findings on ONE model sharing a source and a
    category is a busy model, not a shared cause — the signal needs more than
    one model or it proposes a grouping of a thing with itself."""
    _name, urn = _model(ctx)
    for _ in range(12):
        if not _raise(ctx, urn, source="monitoring", category="drift"):
            return BLOCKED, "a finding could not be raised"
    got = ctx.api.get(f"{R}/candidates?window_hours=24", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the candidates read answered {got.status_code}"
    mine = [s for s in ((got.json() or {}).get("suggestions") or [])
            if s.get("source") == "monitoring" and s.get("category") == "drift"]
    if mine:
        return FAIL, (f"twelve findings on one model were suggested as a "
                      f"shared cause across {mine[0].get('models')} model(s)")
    return PASS, "one model, twelve findings, and no suggestion"


@case("QA-AM-145", "Candidates where the findings were acknowledged first")
def am_145(ctx: Ctx) -> Result:
    """The recorded fix. Querying only `open` meant an acknowledged finding
    could never be suggested as part of a group — and a shared upstream
    failure is usually noticed BECAUSE several owners have just acknowledged
    the same thing."""
    findings = ctx.ui.app.state.ctx.get("findings")
    workflow = ctx.ui.app.state.ctx.get("finding_workflow")
    if not (findings and workflow):
        return BLOCKED, "the findings workflow is not wired"
    ids = []
    for _ in range(2):
        _name, urn = _model(ctx)
        fid = _raise(ctx, urn, source="monitoring", category="upstream")
        if not fid:
            return BLOCKED, "a finding could not be raised"
        ids.append(fid)
        findings.set_status(fid, "in_remediation", actor="qa")
    got = ctx.api.get(f"{R}/candidates?window_hours=24", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the candidates read answered {got.status_code}"
    mine = [s for s in ((got.json() or {}).get("suggestions") or [])
            if s.get("category") == "upstream"]
    if not mine:
        return FAIL, ("two acknowledged findings across two models sharing a "
                      "source and category are not suggested, so a shared "
                      "upstream failure is invisible at exactly the moment "
                      "several owners have just accepted it")
    return PASS, f"suggested across {mine[0].get('models')} models"


@case("QA-AM-146", "Candidates with `window_hours=0`")
def am_146(ctx: Ctx) -> Result:
    """A window of zero is `raised_at >= now`, so nothing qualifies — and it
    must return no suggestions rather than every finding ever raised, which
    is what a window read as *unbounded* would do."""
    for _ in range(2):
        _name, urn = _model(ctx)
        if not _raise(ctx, urn, source="monitoring", category="zero_window"):
            return BLOCKED, "a finding could not be raised"
    got = ctx.api.get(f"{R}/candidates?window_hours=0", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' — a window of zero is not one"
    body = got.json() or {}
    mine = [s for s in (body.get("suggestions") or [])
            if s.get("category") == "zero_window"]
    if mine:
        return FAIL, (f"a zero-hour window suggested {mine[0].get('count')} "
                      f"finding(s), so zero is being read as unbounded")
    if body.get("window_hours") != 0:
        return FAIL, f"the window reads back as {body.get('window_hours')}"
    return PASS, "zero hours, no suggestions, and the window is echoed"


@case("QA-AM-143", "Open a root with an unknown kind")
def am_143(ctx: Ctx) -> Result:
    """The kinds are a closed vocabulary because each one implies a different
    person to go and talk to. A free-text kind is a cause nobody can route."""
    got = _root(ctx, kind="something_went_wrong")
    outcome = refused_by_the_control(got, "a root of a kind that is not one")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "unknown_root_kind":
        return FAIL, f"refused '{code_of(got)}'"
    missing = [k for k, _why in KINDS if k not in got.text]
    if missing:
        return FAIL, f"the refusal does not name the kinds {missing}"
    return PASS, f"refused 'unknown_root_kind', naming all {len(KINDS)}"
