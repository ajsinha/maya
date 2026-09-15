"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the findings register itself, rather than the workflow over it.

Two things about it are load-bearing and easy to miss. **`blocking` is a
column, not a severity**: an Observation can block and a Critical need not, so
every guard downstream reads the column. And **`status` is a summary of the
acts, never a substitute for them** — the acknowledgement, the plan and the
extensions are all derived from the act log, so moving the status cannot
launder any of them.

What the register refuses is as narrow as it looks: severity, source, owner and
title are checked; the status vocabulary is not, and `due_at` is derived from
severity on every path a caller can reach.
"""
from __future__ import annotations

from core.validation.common import (REMEDIATION_DAYS, SOURCES,
                                    ValidationError)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_refused)
from qa.regression_suite.scenarios.g_execution import governed

DAY = 86400.0
F = "/api/v1/findings"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("fr")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER}, auth=ctx.people["owner"])
    return f"maya://model/{name}"


def _raise(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "severity": "High", "title": "A QA finding",
            "owner": "person/owner", "description": "qa",
            "category": "general", "source": "validation"}
    body.update(over)
    return ctx.api.post(F, json=body, auth=ctx.people["risk"])


def _register(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("findings")


@case("QA-AM-069", "Raise a Low finding with `blocking: true`")
def am_069(ctx: Ctx) -> Result:
    """`blocking` is the column, not the severity. A Low finding that blocks
    must withhold service exactly as a Critical one does — otherwise the
    column is decoration and the severity is the real control, which is not
    what any of the guards read."""
    made = governed(ctx)
    urn = made["urn"]
    raised = _raise(ctx, urn, severity="Low", blocking=True,
                    title="A Low finding that blocks")
    if raised.status_code >= 400:
        return FAIL, f"a Low blocking finding was refused: {raised.text[:150]}"
    row = raised.json() or {}
    if not row.get("blocking"):
        return FAIL, ("accepted, but the finding is not blocking — the column "
                      "was overridden by the severity")
    ctx.api.post("/api/v1/warrants",
                 json={"urn": urn, "principal": "svc-pricing",
                       "environment": "prod",
                       "declared_use": "credit_decision"})
    got = ctx.api.post("/api/v1/resolve",
                       json={"urn": urn, "principal": "svc-pricing",
                             "environment": "prod",
                             "declared_use": "credit_decision"})
    if got.status_code < 400:
        return FAIL, ("a warrant resolved with a blocking Low finding open, "
                      "so `blocking` is only honoured at high severities")
    if code_of(got) != "blocked":
        return FAIL, f"refused '{code_of(got)}' rather than 'blocked'"
    said = got.text
    if "A Low finding that blocks" not in said:
        return FAIL, (f"the refusal does not name the finding, so the caller "
                      f"cannot tell what to chase: {said[:200]}")
    return PASS, f"refused 'blocked' at HTTP {got.status_code}, naming the finding"


@case("QA-AM-070", "A caller-supplied `due_at` two years out")
def am_070(ctx: Ctx) -> Result:
    """Remediation dates are derived from severity rather than negotiated.
    `raise_finding` takes a `due_at` for the importers that carry a real
    historical date; the question is whether anything a caller can reach
    exposes it, because a negotiable date is a date that means nothing in
    the pack it is reported in."""
    urn = _model(ctx)
    got = _raise(ctx, urn, severity="Critical", due_at=99_999_999_999.0)
    if got.status_code < 400:
        row = got.json() or {}
        window = (row["due_at"] - row["raised_at"]) / DAY
        expected = REMEDIATION_DAYS["Critical"]
        if abs(window - expected) > 1.0:
            return FAIL, (f"the route accepted the caller's date: the window "
                          f"is {window:.0f} days rather than the derived "
                          f"{expected:g}, so a remediation date is negotiable")
        return PASS, (f"the field was accepted and ignored; the window is the "
                      f"derived {window:.0f} days")
    from routes.validation_routes import FindingIn
    if "due_at" in FindingIn.model_fields:
        return FAIL, ("the request model carries `due_at`, so the derived "
                      "window can be bypassed from the API")
    if "extra_forbidden" not in got.text:
        return FAIL, (f"refused, but not as an unknown field: {got.text[:180]}")
    clean = _raise(ctx, urn, severity="Critical")
    if clean.status_code >= 400:
        return BLOCKED, f"the same finding without the field failed: {clean.text[:150]}"
    row = clean.json() or {}
    window = (row["due_at"] - row["raised_at"]) / DAY
    expected = REMEDIATION_DAYS["Critical"]
    if abs(window - expected) > 1.0:
        return FAIL, (f"the derived window is {window:.0f} days rather than "
                      f"{expected:g}")
    return PASS, (f"refused outright — the body model forbids unknown fields "
                  f"and carries no `due_at`, so the {expected:g}-day Critical "
                  f"window cannot be negotiated from any route")


@case("QA-AM-072", "Raise with an unknown source")
def am_072(ctx: Ctx) -> Result:
    """A regulator-raised finding and a self-identified one carry very
    different weight in every pack the register feeds, and free text loses
    that distinction permanently."""
    got = _raise(ctx, _model(ctx), source="hearsay")
    outcome = expect_refused(got, "validation_refused")
    if outcome[0] is not PASS:
        return outcome
    if "hearsay" not in got.text:
        return FAIL, "the refusal does not name the value it rejected"
    if not any(s in got.text for s in SOURCES):
        return FAIL, (f"the refusal does not say what is allowed, so the "
                      f"caller has to guess: {got.text[:180]}")
    return PASS, f"refused 'validation_refused', naming the {len(SOURCES)} sources"


@case("QA-AM-074", "Raise the identical finding twice by hand")
def am_074(ctx: Ctx) -> Result:
    """Both accepted, and that is a limitation worth stating rather than a
    defect to assert: the register cannot tell a duplicate from two genuine
    instances of the same problem, so the ageing profile counts one problem
    as two. Reported here so the number is read with that in mind."""
    urn = _model(ctx)
    body = {"severity": "High", "title": "Drift on the income feature",
            "owner": "person/owner", "description": "the same text twice"}
    first, second = _raise(ctx, urn, **body), _raise(ctx, urn, **body)
    if first.status_code >= 400 or second.status_code >= 400:
        return FAIL, (f"one of the two was refused: "
                      f"{first.status_code}/{second.status_code}")
    if (first.json() or {}).get("id") == (second.json() or {}).get("id"):
        return FAIL, "the second raise returned the first finding's id"
    seen = ctx.api.get(f"{F}?urn={urn}", auth=ctx.people["risk"])
    summary = (seen.json() or {}).get("summary") or {}
    if summary.get("open") != 2:
        return FAIL, (f"the register reports {summary.get('open')} open rather "
                      f"than 2")
    return PASS, ("both accepted and both counted: nothing dedupes a "
                  "human-raised finding, so one problem raised twice is two "
                  "rows in the ageing profile")


@case("QA-AM-075", "`set_status` to `closed`")
def am_075(ctx: Ctx) -> Result:
    """Closure needs a verifier and evidence, and this is the back door to
    the status column without either. Checked at the register because no
    route reaches `set_status` — and that is the stronger of the two facts."""
    register = _register(ctx)
    if register is None:
        return BLOCKED, "no findings register is wired"
    raised = _raise(ctx, _model(ctx))
    fid = (raised.json() or {}).get("id")
    if not fid:
        return BLOCKED, f"the finding could not be raised: {raised.text[:150]}"
    try:
        register.set_status(fid, "closed")
    except ValidationError as exc:
        if "close()" not in str(exc):
            return FAIL, f"refused, but not as the closure back door: {exc}"
        row = register.require(fid)
        if row["status"] == "closed":
            return FAIL, "refused and the status moved anyway"
        return PASS, f"refused: {str(exc)[:110]}"
    return FAIL, ("`set_status` closed a finding with no verifier and no "
                  "evidence, so the closure guard has a back door")


@case("QA-AM-076", "`set_status` to an unknown value")
def am_076(ctx: Ctx) -> Result:
    """A limitation, recorded rather than asserted as a defect: the register
    checks the severity and the source vocabularies and not the status one.
    It matters because the status is what every list filters on, so a value
    outside the vocabulary is a finding that is open and appears nowhere."""
    register = _register(ctx)
    if register is None:
        return BLOCKED, "no findings register is wired"
    raised = _raise(ctx, _model(ctx))
    fid = (raised.json() or {}).get("id")
    if not fid:
        return BLOCKED, f"the finding could not be raised: {raised.text[:150]}"
    try:
        register.set_status(fid, "banana")
    except ValidationError as exc:
        return PASS, f"the status vocabulary is checked after all: {str(exc)[:110]}"
    row = register.require(fid)
    if row["status"] != "banana":
        return FAIL, (f"accepted without refusing, but the status reads "
                      f"'{row['status']}'")
    model_id = row["model_id"]
    still_open = [f["id"] for f in register.open_for(model_id)]
    return PASS, ("no status vocabulary is checked: the finding now reads "
                  "'banana' and is "
                  + ("still counted open, so the column can disagree with the "
                     "acts" if fid in still_open else
                     "no longer counted open, so it is outstanding and "
                     "invisible to every list"))


@case("QA-AM-077", "`set_status` back to `open` after an acknowledgement")
def am_077(ctx: Ctx) -> Result:
    """The status is a summary of the acts, so moving it back must not move
    the acknowledgement with it. An acknowledgement that could be undone by
    a status write would be a date somebody committed to and nothing holds."""
    register = _register(ctx)
    workflow = ctx.ui.app.state.ctx.get("finding_workflow")
    if register is None or workflow is None:
        return BLOCKED, "the register or the finding workflow is not wired"
    raised = _raise(ctx, _model(ctx), owner="person/owner")
    fid = (raised.json() or {}).get("id")
    if not fid:
        return BLOCKED, f"the finding could not be raised: {raised.text[:150]}"
    said = ctx.api.post(f"{F}/{fid}/acknowledge",
                        json={"days": 20.0, "plan": "repoint the feature"},
                        auth=ctx.people["owner"])
    if said.status_code >= 400:
        return BLOCKED, f"the acknowledgement failed: {said.text[:150]}"
    moved = register.require(fid)["status"]
    if moved == "open":
        return FAIL, ("the acknowledgement did not move the status, so this "
                      "case cannot show it surviving a move back")
    register.set_status(fid, "open")
    after = workflow.reading(fid)
    if not after["acknowledgement"]["acknowledged"]:
        return FAIL, ("writing the status back to open erased the "
                      "acknowledgement, so a committed date can be undone by "
                      "a summary column")
    if register.require(fid)["status"] != "open":
        return FAIL, "the status did not move"
    return PASS, (f"the status moved {moved} → open and the acknowledgement "
                  f"stands, because it is derived from the acts")


@case("QA-AM-078", "Summary over a model with no findings")
def am_078(ctx: Ctx) -> Result:
    """`worst()` answers `Observation` for an empty collection — the lowest
    of a vocabulary, which is the right answer to *which of these is worst*
    and the wrong answer to *what is the worst open finding*. The summary
    must say null, or every clean model in the inventory carries a severity."""
    urn = _model(ctx)
    got = ctx.api.get(f"{F}?urn={urn}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the register could not be read: {got.text[:150]}"
    summary = (got.json() or {}).get("summary") or {}
    if summary.get("open") != 0:
        return BLOCKED, f"the fresh model has {summary.get('open')} findings"
    if summary.get("worst_severity") is not None:
        return FAIL, (f"a model with no findings reports worst_severity "
                      f"'{summary['worst_severity']}', so a clean model reads "
                      f"as carrying one")
    if summary.get("by_severity"):
        return FAIL, f"by_severity is not empty: {summary['by_severity']}"
    return PASS, "open 0, worst_severity null, by_severity empty"


@case("QA-AM-079", "Estate-wide open findings under a scoped reader")
def am_079(ctx: Ctx) -> Result:
    """The list is correctly short. The question is whether the ANSWER says
    so: a total that is silently short gets reconciled against somebody
    else's, and the difference is blamed on a bug in the register rather
    than read as the scope doing its job. The worklist answers this with an
    `others` count; this route does not."""
    urn = _model(ctx)
    if _raise(ctx, urn, blocking=True).status_code >= 400:
        return BLOCKED, "the finding could not be raised"
    who = ctx.unique("scoped")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_risk_manager"],
                              "password": f"{who}-pw",
                              "legal_entities": ["LE-XX-99"], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, f"the scoped reader could not be created: {made.text[:150]}"
    wide = ctx.api.get("/api/v1/open-findings", auth=ctx.people["risk"])
    narrow = ctx.api.get("/api/v1/open-findings", auth=(who, f"{who}-pw"))
    if narrow.status_code >= 400:
        return BLOCKED, f"the scoped read was refused: {narrow.text[:150]}"
    seen = narrow.json() or {}
    everything = wide.json() or {}
    if seen.get("open", 0) >= everything.get("open", 0):
        return FAIL, (f"the scoped reader sees {seen.get('open')} of "
                      f"{everything.get('open')} open findings, so the scope "
                      f"removed nothing")
    if any(f["urn"] == urn for f in seen.get("findings") or []):
        return FAIL, "the scoped reader sees a finding on another entity's model"
    hidden = everything.get("open", 0) - seen.get("open", 0)
    # A key whose NAME carries the idea, rather than one exact spelling: what
    # the case is for is whether the answer says it is partial, not what the
    # field is called.
    counted = [k for k in seen
               if any(word in k for word in
                      ("hidden", "out_of_scope", "others", "withheld"))]
    said = (seen.get("detail") or "").lower()
    admits = any(word in said for word in
                 ("outside your scope", "not the estate", "not counted here"))
    if not counted and not admits:
        return FAIL, (f"the answer is short by {hidden} and says nothing about "
                      f"it: no count of what scope removed, and no `detail` "
                      f"saying the total is partial — so a reader reconciling "
                      f"against an estate-wide pack sees a discrepancy and "
                      f"reads it as a defect in the register")
    if not admits:
        return FAIL, (f"the answer carries {counted} and the detail does not "
                      f"say the total is partial: {said[:140]}")
    wide_body = everything
    if wide_body.get("detail") and "every model" not in \
            (wide_body["detail"] or "").lower():
        return FAIL, ("an unscoped reader is not told their total IS the "
                      "estate's, so the two answers cannot be told apart")
    return PASS, (f"short by {hidden}; the answer carries {counted} and says "
                  f"so: {said[:90]}")


@case("QA-AM-080", "Read a finding by id that belongs to a model out of scope")
def am_080(ctx: Ctx) -> Result:
    """`/findings?urn=` passes the model to the authoriser; `/findings/{id}`
    does not. If the id path is unscoped it is a leak with a stable
    identifier — and finding ids travel in notifications, worklists and
    board packs, so a reader restricted to one entity is handed them."""
    urn = _model(ctx)
    raised = _raise(ctx, urn, blocking=True,
                    title="The other entity's model failed challenge")
    fid = (raised.json() or {}).get("id")
    if not fid:
        return BLOCKED, f"the finding could not be raised: {raised.text[:150]}"
    who = ctx.unique("scoped")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_risk_manager"],
                              "password": f"{who}-pw",
                              "legal_entities": ["LE-XX-99"], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, f"the scoped reader could not be created: {made.text[:150]}"
    auth = (who, f"{who}-pw")
    by_urn = ctx.api.get(f"{F}?urn={urn}", auth=auth)
    if by_urn.status_code < 400:
        return BLOCKED, ("the urn path is not scoped either, so this case "
                         "cannot contrast the two")
    by_id = ctx.api.get(f"{F}/{fid}", auth=auth)
    if by_id.status_code >= 400:
        return PASS, (f"the id path is scoped too: refused "
                      f"'{code_of(by_id) or by_id.status_code}'")
    leaked = by_id.json() or {}
    return FAIL, (f"the urn path refused '{code_of(by_urn)}' and the id path "
                  f"answered {by_id.status_code} with the finding — severity "
                  f"'{leaked.get('severity')}', owner '{leaked.get('owner')}', "
                  f"'{leaked.get('title')}'. The route authorises "
                  f"`finding:read` with no model, so any finding id reads "
                  f"across every entity")
