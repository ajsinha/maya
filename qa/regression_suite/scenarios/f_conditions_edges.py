"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the edges of a conditional approval.

SR 26-2 V permits use before validation with compensating controls, and this
module is what makes those controls enforced rather than promised. The
distinction it turns on is `enforced` against `attested`: an exposure cap is
something MAYA cannot see behind a call, so a named person confirms it and an
unconfirmed one goes stale — a real control, and not the same thing as one the
platform checks. A firm told the attested ones were machine-enforced would
have stopped checking.

The window is mandatory and bounded at 183 days, because a conditional
approval with no end date is an unconditional approval that has not noticed
yet.

**Every case that successfully imposes a condition is `isolated`.** Not for
tidiness: QA-GOV-4620 below establishes that the second condition in an estate
cannot be stored at all, so two cases sharing an instance would mean the first
one to impose decides the verdict of every case after it.
"""
from __future__ import annotations

from core.lifecycle.conditions import MAX_DAYS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)
from qa.regression_suite.scenarios.g_execution import governed

C = "/api/v1/approval-conditions"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ASSESSMENT = {"exposure": 1_000.0, "purpose_class": "commercial",
              "feature_count": 3, "interpretable": True,
              "uses_alternative_data": False}


def _model(ctx: Ctx) -> tuple:
    name = ctx.unique("cd")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess", json=dict(ASSESSMENT))
    return name, urn


def _impose(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "kind": "expires", "rationale": "pending validation",
            "days": 90.0, "parameters": {}, "semver": "",
            "confirm_every_days": 30.0}
    body.update(over)
    return ctx.api.post(C, json=body, auth=ctx.people["risk"])


def _reference(got) -> str:
    return (got.json() or {}).get("reference", "") if got.status_code < 400 \
        else ""


@case("QA-GOV-152", "Impose a condition running 0 days")
def gov_152(ctx: Ctx) -> Result:
    """Zero days is an approval that has already lapsed, recorded as though
    it were a control."""
    _name, urn = _model(ctx)
    got = _impose(ctx, urn, days=0.0)
    outcome = refused_by_the_control(got, "a condition running no days")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "window_out_of_range":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'window_out_of_range'"


@case("QA-GOV-153", "Impose a condition running exactly 183 days", isolated=True)
def gov_153(ctx: Ctx) -> Result:
    """Six months: long enough to finish a validation, short enough that
    nobody plans around it. The bound is inclusive and this is the side of it
    that has to work."""
    _name, urn = _model(ctx)
    got = _impose(ctx, urn, days=MAX_DAYS)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' at exactly {MAX_DAYS:.0f} "
                      f"days, so the documented bound is one day shorter")
    return PASS, f"{MAX_DAYS:.0f} days accepted"


@case("QA-GOV-154", "Impose a condition running 183.5 days")
def gov_154(ctx: Ctx) -> Result:
    """The other side. Half a day over is over, or the bound is advisory."""
    _name, urn = _model(ctx)
    got = _impose(ctx, urn, days=MAX_DAYS + 0.5)
    outcome = refused_by_the_control(
        got, f"a condition running longer than {MAX_DAYS:.0f} days")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "window_out_of_range":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'window_out_of_range' at half a day over"


@case("QA-GOV-155", "Impose an `exposure_cap` with an amount and no currency")
def gov_155(ctx: Ctx) -> Result:
    """An amount with no currency is a cap nobody can compare anything to —
    the same gap the delegation ceiling refuses on."""
    _name, urn = _model(ctx)
    got = _impose(ctx, urn, kind="exposure_cap",
                  parameters={"amount": 1_000_000.0})
    outcome = refused_by_the_control(got, "an exposure cap with no currency")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "condition_incomplete":
        return FAIL, f"refused '{code_of(got)}'"
    if "currency" not in got.text:
        return FAIL, "the refusal does not name the field that is missing"
    return PASS, "refused 'condition_incomplete', naming currency"


@case("QA-GOV-156", "Impose a `usage_cap` before any warrant exists", isolated=True)
def gov_156(ctx: Ctx) -> Result:
    """EXPECTED GAP. The cap is applied to every existing grant at the moment
    it is imposed, and nothing re-applies it to grants issued afterwards — so
    a cap imposed before the first warrant caps nothing."""
    made = governed(ctx)
    urn = made["urn"]
    got = _impose(ctx, urn, kind="usage_cap",
                  parameters={"calls": 10, "window_hours": 1.0})
    if got.status_code >= 400:
        return BLOCKED, f"the cap could not be imposed: {got.text[:140]}"
    issued = ctx.api.post("/api/v1/warrants",
                          json={"urn": urn, "principal": "svc-pricing",
                                "environment": "prod",
                                "declared_use": "credit_decision"})
    if issued.status_code >= 400:
        return BLOCKED, f"the warrant could not be issued: {issued.text[:140]}"
    quotas = ctx.ui.app.state.ctx.get("quotas")
    if quotas is None:
        return PASS, ("no quota register is wired, so the cap is recorded and "
                      "not enforced — which is QA-GOV-157")
    grants = ctx.ui.app.state.ctx["warrants"].grants.repo.many()
    mine = [g for g in grants if g.get("principal") == "svc-pricing"]
    capped = [g for g in mine if quotas.for_grant(g["id"])] if hasattr(
        quotas, "for_grant") else []
    if capped:
        return PASS, "the cap reached the warrant issued after it"
    return FAIL, ("a usage cap imposed before the first warrant caps nothing: "
                  "`_apply_usage_cap` walks the grants that exist when the "
                  "condition is imposed, and issuing a warrant afterwards "
                  "does not consult the conditions")


@case("QA-GOV-158", "Impose a condition naming a version that does not exist")
def gov_158(ctx: Ctx) -> Result:
    """A condition pinned to a version nobody created is a control attached
    to nothing, and it would read on the model page as attached to
    everything."""
    _name, urn = _model(ctx)
    got = _impose(ctx, urn, semver="9.9.9")
    outcome = refused_by_the_control(
        got, "a condition naming a version that does not exist")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "no_version":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'no_version'"


@case("QA-GOV-159", "Impose a condition with no `semver`", isolated=True)
def gov_159(ctx: Ctx) -> Result:
    """A condition on the MODEL rather than on one version. That is the
    common case — the term is about the approval, and the approval outlives
    any one version."""
    _name, urn = _model(ctx)
    got = _impose(ctx, urn, semver="")
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — every condition would have "
                      f"to be re-imposed on each new version")
    body = got.json() or {}
    if body.get("model_version_id") is not None:
        return FAIL, (f"no semver was given and the condition was pinned to "
                      f"version {body.get('model_version_id')}")
    return PASS, "accepted with model_version_id null"


@case("QA-GOV-160", "Confirm an *enforced* condition", isolated=True)
def gov_160(ctx: Ctx) -> Result:
    """Confirming something the platform already checks records an opinion
    about a fact, and it would make the two enforcement classes look alike on
    the screen where the difference matters most."""
    _name, urn = _model(ctx)
    ref = _reference(_impose(ctx, urn, kind="expires"))
    if not ref:
        return BLOCKED, "the condition could not be imposed"
    got = ctx.api.post(f"{C}/{ref}/confirm", json={"note": "qa"},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(got, "an enforced condition was confirmed")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "not_attested":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'not_attested'"


@case("QA-GOV-161", "Confirm an attested condition twice", isolated=True)
def gov_161(ctx: Ctx) -> Result:
    """Confirmation is a cadence, not an event. The second one is the whole
    point — it is what stops the condition going stale — so refusing it would
    make the control expire after its first exercise."""
    _name, urn = _model(ctx)
    ref = _reference(_impose(ctx, urn, kind="human_review",
                             parameters={"share": 0.1}))
    if not ref:
        return BLOCKED, "the condition could not be imposed"
    first = ctx.api.post(f"{C}/{ref}/confirm", json={"note": "qa"},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, f"the first confirmation failed: {first.text[:140]}"
    was = (first.json() or {}).get("confirmed_at")
    second = ctx.api.post(f"{C}/{ref}/confirm", json={"note": "qa again"},
                          auth=ctx.people["risk"])
    if second.status_code >= 400:
        return FAIL, (f"the second confirmation was refused "
                      f"'{code_of(second)}'; a cadence that may be exercised "
                      f"once is not a cadence")
    now = (second.json() or {}).get("confirmed_at")
    if now == was:
        return FAIL, "the second confirmation did not move confirmed_at"
    return PASS, "confirmed twice, and the clock moved both times"


@case("QA-GOV-162", "Confirm a discharged condition", isolated=True)
def gov_162(ctx: Ctx) -> Result:
    """A discharged condition needs no confirmation, and accepting one would
    put a fresh date on a control that has been lifted."""
    _name, urn = _model(ctx)
    ref = _reference(_impose(ctx, urn, kind="human_review",
                             parameters={"share": 0.1}))
    if not ref:
        return BLOCKED, "the condition could not be imposed"
    gone = ctx.api.post(f"{C}/{ref}/discharge",
                        json={"reason": "the validation completed"},
                        auth=ctx.people["risk"])
    if gone.status_code >= 400:
        return BLOCKED, f"the discharge failed: {gone.text[:140]}"
    got = ctx.api.post(f"{C}/{ref}/confirm", json={"note": "qa"},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(
        got, "a discharged condition was confirmed")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "not_active":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'not_active'"


@case("QA-GOV-163", "Discharge twice", isolated=True)
def gov_163(ctx: Ctx) -> Result:
    """A condition is discharged once. The second would rewrite who lifted it
    and why."""
    _name, urn = _model(ctx)
    ref = _reference(_impose(ctx, urn))
    if not ref:
        return BLOCKED, "the condition could not be imposed"
    first = ctx.api.post(f"{C}/{ref}/discharge",
                         json={"reason": "the validation completed"},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, f"the first discharge failed: {first.text[:140]}"
    got = ctx.api.post(f"{C}/{ref}/discharge",
                       json={"reason": "a different reason entirely"},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(got, "a condition was discharged twice")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "not_active":
        return FAIL, f"refused '{code_of(got)}'"
    held = ctx.api.get(f"{C}?urn={urn}", auth=ctx.people["risk"])
    rows = [r for r in ((held.json() or {}).get("conditions") or [])
            if r.get("reference") == ref]
    if rows and "different reason" in (rows[0].get("discharge_reason") or ""):
        return FAIL, "the refused second discharge overwrote the first reason"
    return PASS, "refused 'not_active', first reason intact"


@case("QA-GOV-164", "Discharge with no reason", isolated=True)
def gov_164(ctx: Ctx) -> Result:
    """Lifting a condition with no reason removes a control and records
    nothing about why it was safe to."""
    _name, urn = _model(ctx)
    ref = _reference(_impose(ctx, urn))
    if not ref:
        return BLOCKED, "the condition could not be imposed"
    got = ctx.api.post(f"{C}/{ref}/discharge", json={"reason": "   "},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(
        got, "a condition was discharged with no reason")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "reason_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'reason_required' on whitespace"


@case("QA-GOV-165",
      "Two `expires` conditions with different windows on one model", isolated=True)
def gov_165(ctx: Ctx) -> Result:
    """VERIFY. Every condition is evaluated and any broken one refuses, so
    the shorter window binds — which is right, and worth pinning because the
    alternative reading (the latest imposed wins) would let a second, longer
    condition extend an approval nobody re-granted."""
    _name, urn = _model(ctx)
    short = _reference(_impose(ctx, urn, days=1.0,
                               rationale="the short one"))
    long_ = _reference(_impose(ctx, urn, days=120.0,
                               rationale="the long one"))
    if not (short and long_):
        return BLOCKED, "both conditions could not be imposed"
    if short == long_:
        return FAIL, (f"two conditions on one model share the reference "
                      f"'{short}', so confirming or discharging one by "
                      f"reference addresses whichever the query returns first")
    got = ctx.api.get(f"{C}?urn={urn}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the reading answered {got.status_code}"
    body = got.json() or {}
    rows = body.get("conditions")
    if not isinstance(rows, list):
        return FAIL, (f"`conditions` reads {rows!r}, an integer. `for_model` "
                      f"builds `{{\"conditions\": rows, ...}}` and then "
                      f"spreads `**self.evaluate(urn)` over it, and `evaluate` "
                      f"answers `conditions: len(rows)` — so the spread "
                      f"overwrites the rows with a count, and the rationale, "
                      f"the imposer and the discharge reason never reach a "
                      f"caller of GET /approval-conditions?urn=")
    windows = sorted((r.get("expires_at") or 0) for r in rows
                     if r.get("reference") in (short, long_))
    if len(windows) != 2:
        return FAIL, f"both conditions are not on the model: {len(windows)}"
    return PASS, (f"two windows stand side by side "
                  f"({(windows[1] - windows[0]) / 86400:.0f} days apart); "
                  f"every condition is evaluated, so the shorter binds")


@case("QA-GOV-166", "Resolve after the condition's expiry", isolated=True)
def gov_166(ctx: Ctx) -> Result:
    """A conditional approval that outlives its conditions is an
    unconditional one nobody granted. Resolution is where that has to bite."""
    made = governed(ctx)
    urn = made["urn"]
    conditions = ctx.ui.app.state.ctx.get("approval_conditions")
    if conditions is None:
        return BLOCKED, "no conditions engine is wired"
    imposed = _impose(ctx, urn, days=1.0)
    if imposed.status_code >= 400:
        return BLOCKED, f"the condition could not be imposed: {imposed.text[:140]}"
    ref = _reference(imposed)
    # Wound back rather than waited out. There is no API for an expiry in the
    # past and there should not be one.
    row = conditions.require(ref)
    conditions.repo.set({"expires_at": row["imposed_at"] - 1.0}, id=row["id"])
    ctx.api.post("/api/v1/warrants",
                 json={"urn": urn, "principal": "svc-pricing",
                       "environment": "prod",
                       "declared_use": "credit_decision"})
    got = ctx.api.post("/api/v1/resolve",
                       json={"urn": urn, "principal": "svc-pricing",
                             "environment": "prod",
                             "declared_use": "credit_decision"})
    if got.status_code < 400:
        return FAIL, ("a model whose conditional approval expired still "
                      "resolves, so the condition is a note with a date on it")
    if code_of(got) != "approval_condition_broken":
        return FAIL, f"refused '{code_of(got)}'"
    if ref not in got.text:
        return FAIL, "the refusal does not name the condition that broke"
    return PASS, f"refused 'approval_condition_broken', naming {ref}"


@case("QA-GOV-167", "Resolve in an environment the condition excludes", isolated=True)
def gov_167(ctx: Ctx) -> Result:
    """An `environments` condition is the one a firm uses to let a model into
    UAT while validation finishes. If it does not refuse in prod it has done
    the opposite of its job."""
    made = governed(ctx)
    urn = made["urn"]
    imposed = _impose(ctx, urn, kind="environments",
                      parameters={"environments": ["uat"]},
                      rationale="uat only until validation completes")
    if imposed.status_code >= 400:
        return BLOCKED, f"the condition could not be imposed: {imposed.text[:140]}"
    ctx.api.post("/api/v1/warrants",
                 json={"urn": urn, "principal": "svc-pricing",
                       "environment": "prod",
                       "declared_use": "credit_decision"})
    got = ctx.api.post("/api/v1/resolve",
                       json={"urn": urn, "principal": "svc-pricing",
                             "environment": "prod",
                             "declared_use": "credit_decision"})
    if got.status_code < 400:
        return FAIL, ("a model approved for uat only resolved in prod, so an "
                      "environments condition permits every environment")
    if code_of(got) != "approval_condition_broken":
        return FAIL, f"refused '{code_of(got)}'"
    if "uat" not in got.text:
        return FAIL, "the refusal does not say which environments are approved"
    return PASS, "refused 'approval_condition_broken', naming uat"


@case("QA-GOV-4620",
      "A second model in the estate receives its first condition",
      isolated=True)
def gov_4620(ctx: Ctx) -> Result:
    """The reference is numbered from a PER-MODEL counter —
    ``COND-{len(repo.many(model_id=...)) + 1:04d}`` — and
    ``uq_approval_condition_reference`` is UNIQUE on ``reference`` across the
    whole table. So the first condition on every model is COND-0001, and the
    second model in an estate to be approved on terms cannot be.

    Written as its own case because QA-GOV-159 found it by accident, which is
    not where a reader will look for it.
    """
    _first, first_urn = _model(ctx)
    one = _impose(ctx, first_urn)
    if one.status_code >= 400:
        return BLOCKED, f"the first condition could not be imposed: {one.text[:140]}"
    if _reference(one) != "COND-0001":
        return BLOCKED, f"the first reference is {_reference(one)!r}"
    _second, second_urn = _model(ctx)
    two = _impose(ctx, second_urn)
    if two.status_code < 400:
        if _reference(two) == "COND-0001":
            return FAIL, ("two models both hold a condition referenced "
                          "COND-0001, so confirming or discharging one by "
                          "reference addresses whichever row the query "
                          "returns")
        return PASS, (f"the second model's condition is "
                      f"{_reference(two)!r}, distinct from the first")
    if two.status_code >= 500:
        return FAIL, (f"the second model in the estate to be approved on "
                      f"terms crashes with {two.status_code}: the reference "
                      f"is numbered per model and the unique index is over "
                      f"the whole table, so COND-0001 can exist once. "
                      f"Conditional approval works for exactly one model, "
                      f"and it fails as an unhandled error rather than a "
                      f"refusal")
    return FAIL, (f"the second model's condition is refused "
                  f"'{code_of(two)}' — a model cannot be approved on terms "
                  f"because another one already was")
