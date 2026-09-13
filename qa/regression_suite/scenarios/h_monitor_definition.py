"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — defining a monitor.

Two checks here do the same job from different directions, and the second one
is the interesting one. `test_key` against `kind` catches a definition error —
pairing input drift with a discrimination test. `kind` against the MODEL
catches something worse: a `performance` monitor on a T0 pricer has no
parameters and no fitted relationship to lose, and a `calibration` monitor on
a T5 generative assembly is asking for a Brier score over text. Both used to
be accepted, and both produce a monitor that runs for ever without ever
meaning anything — which reads on the estate screen as coverage. That is worse
than an absent monitor, because an absent one is visible in the worklist and a
meaningless one is not.

The answer comes from the fibre (L-15), which is the point of having one: the
class already knew what it could answer, in a table nothing could read.
"""
from __future__ import annotations

from core.monitoring.common import ADMISSIBLE_TESTS, LABEL_DEPENDENT
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

MON = "/api/v1/monitors"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
#: A kernel whose parameters are fitted, so the fibre admits a performance
#: monitor. A T0 model has nothing to lose and is refused `kind_not_answerable`.
FITTED = {"parameter_kind": "estimated_coefficients",
          "fit_procedure": "estimate", "runtime": "estimator",
          "input_schema": [{"name": "x", "dtype": "float"}],
          "output_schema": [{"name": "score", "dtype": "float"}]}


def _model(ctx: Ctx, kernel=None, *, version: bool = True) -> tuple:
    name = ctx.unique("md")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    if version:
        ctx.api.post(f"{M}/{name}/versions",
                     json={"semver": "1.0.0", "kernel": dict(kernel or FITTED)},
                     auth=ctx.people["developer"])
    return name, urn


def _define(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "name": ctx.unique("mon"), "kind": "input_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.2},
            "owner": "person/owner", "reference": {}, "slice": {},
            "cadence_days": 1.0, "label_delay_days": 0.0,
            "breach_severity": "Medium", "escalate_after": 3}
    body.update(over)
    return ctx.api.post(MON, json=body, auth=ctx.people["owner"])


@case("QA-AM-190", "Pair `input_drift` with `discrimination.gini`")
def am_190(ctx: Ctx) -> Result:
    """A definition error, not a runtime surprise, so it is refused when the
    monitor is defined rather than when it first runs."""
    _name, urn = _model(ctx)
    got = _define(ctx, urn, kind="input_drift",
                  test_key="discrimination.gini")
    outcome = refused_by_the_control(
        got, "input drift was paired with a discrimination test")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "test_not_admissible":
        return FAIL, f"refused '{code_of(got)}'"
    for admissible in ADMISSIBLE_TESTS["input_drift"]:
        if admissible not in got.text:
            return FAIL, (f"the refusal does not name '{admissible}', so the "
                          f"caller is told no with nothing to use instead")
    return PASS, "refused 'test_not_admissible', naming what does answer it"


@case("QA-AM-191", "Define a `performance` monitor with no `label_delay_days`")
def am_191(ctx: Ctx) -> Result:
    """A performance monitor compares predictions to outcomes, so it has to
    declare how long those outcomes take to arrive. Without it the monitor
    evaluates against labels that do not exist yet and reads clean."""
    _name, urn = _model(ctx)
    got = _define(ctx, urn, kind="performance", test_key="discrimination.auc",
                  threshold={"min": 0.6})
    outcome = refused_by_the_control(
        got, "a performance monitor with no label delay")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "label_delay_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'label_delay_required'"


@case("QA-AM-192", "Define a `performance` monitor with `label_delay_days: 0`")
def am_192(ctx: Ctx) -> Result:
    """Explicit zero and absent are the same answer here, and both are
    wrong — a label that arrives instantly is not a label, it is the score."""
    _name, urn = _model(ctx)
    got = _define(ctx, urn, kind="performance", test_key="discrimination.auc",
                  threshold={"min": 0.6}, label_delay_days=0.0)
    outcome = refused_by_the_control(
        got, "a performance monitor with a zero label delay")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "label_delay_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'label_delay_required' on an explicit zero"


@case("QA-AM-193", "Define a `calibration` monitor with a delay of 0.5 days")
def am_193(ctx: Ctx) -> Result:
    """EXPLORATORY. The bound is `> 0` rather than a minimum, and half a day
    is a real answer for a fraud model whose outcome is a chargeback the same
    afternoon. Refusing it would push a firm into declaring 1 and evaluating
    against labels it does not have."""
    _name, urn = _model(ctx)
    got = _define(ctx, urn, kind="calibration",
                  test_key="calibration.brier", threshold={"max": 0.25},
                  label_delay_days=0.5)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' at half a day, so a same-day "
                      f"outcome has to be declared as a longer one")
    body = got.json() or {}
    if float(body.get("label_delay_days") or 0) != 0.5:
        return FAIL, (f"stored as {body.get('label_delay_days')!r} rather "
                      f"than 0.5, so a sub-day delay is rounded away")
    return PASS, "half a day accepted and kept as half a day"


@case("QA-AM-194", "Define with no threshold")
def am_194(ctx: Ctx) -> Result:
    """A monitor with no threshold can never breach, so it monitors nothing
    — and it reads on the estate screen exactly like one that does."""
    _name, urn = _model(ctx)
    got = _define(ctx, urn, threshold={})
    outcome = refused_by_the_control(got, "a monitor with no threshold")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "threshold_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'threshold_required'"


@case("QA-AM-195", 'Define with `threshold: {"floor": 0.4}`')
def am_195(ctx: Ctx) -> Result:
    """A threshold in a vocabulary the judge does not have. `define` asks
    only whether the dict is non-empty, so this is accepted — and the failure
    lands at evaluation, on whoever is reading the monitor rather than
    whoever wrote it."""
    _name, urn = _model(ctx)
    # A reference on the definition, so the evaluation reaches the JUDGE
    # rather than stopping at `no_reference` — otherwise the refusal proves
    # nothing about the threshold.
    reference = {"sample": [float(n) for n in range(50)]}
    got = _define(ctx, urn, threshold={"floor": 0.4}, reference=reference)
    if got.status_code >= 400:
        return PASS, (f"refused at definition ('{code_of(got)}') — the "
                      f"vocabulary is checked where it is written")
    monitor_id = (got.json() or {}).get("id")
    ran = ctx.api.post(
        f"{MON}/{monitor_id}/evaluate",
        json={"rows": [{"scored_at": float(n), "score": float(n) + 10.0}
                       for n in range(50)]},
        auth=ctx.people["owner"])
    if ran.status_code < 400:
        return FAIL, ("a threshold declaring none of min, max or target was "
                      "accepted AND evaluated, so the monitor can never "
                      "breach and reads as covering the model")
    return FAIL, (f"accepted at definition and refused at evaluation "
                  f"('{code_of(ran)}'): `define` tests only that the "
                  f"threshold dict is non-empty, so a monitor written with "
                  f"the wrong vocabulary reads as active until somebody runs "
                  f"it — and the refusal lands on whoever is reading the "
                  f"monitor rather than whoever wrote it")


@case("QA-AM-196", "Define two monitors with the same name on one model")
def am_196(ctx: Ctx) -> Result:
    """The name is how a breach is reported and how a monitor is found. Two
    with one name make every later reference ambiguous."""
    _name, urn = _model(ctx)
    shared = ctx.unique("mon")
    if _define(ctx, urn, name=shared).status_code >= 400:
        return BLOCKED, "the first monitor could not be defined"
    got = _define(ctx, urn, name=shared)
    outcome = refused_by_the_control(
        got, "two monitors on one model share a name")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "duplicate_monitor":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'duplicate_monitor'"


@case("QA-AM-4700", "Define two monitors with the same name on two models")
def am_4700(ctx: Ctx) -> Result:
    """The other side of QA-AM-196. The uniqueness is per MODEL, and it has
    to be — `psi` is what everybody calls their drift monitor, and a register
    where the second model cannot use the name would push every firm into
    prefixing the model name into the monitor name."""
    _a, first = _model(ctx)
    _b, second = _model(ctx)
    shared = ctx.unique("mon")
    if _define(ctx, first, name=shared).status_code >= 400:
        return BLOCKED, "the first monitor could not be defined"
    got = _define(ctx, second, name=shared)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a monitor name is unique "
                      f"across the estate, so the second model to want a "
                      f"monitor called '{shared}' cannot have one")
    return PASS, "one name, two models, both defined"


@case("QA-AM-197", "Define with `escalate_after: 0`")
def am_197(ctx: Ctx) -> Result:
    """Zero means the severity never escalates: the monitor breaches at its
    declared severity and stays there. A firm that wants a Medium breach to
    stay Medium has to be able to say so."""
    _name, urn = _model(ctx)
    got = _define(ctx, urn, escalate_after=0)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — there is no way to say "
                      f"'this breach does not escalate'")
    if int((got.json() or {}).get("escalate_after", -1)) != 0:
        return FAIL, "escalate_after was not stored as 0"
    return PASS, "0 accepted and kept"


@case("QA-AM-198", "Define with `escalate_after: -1`")
def am_198(ctx: Ctx) -> Result:
    """EXPLORATORY. A negative escalation count is not a quantity. Whatever
    the escalation arithmetic does with it, a firm reading the monitor cannot
    tell what it means — and zero already says *never escalate*, so there is
    nothing a negative could mean that is not already sayable."""
    _name, urn = _model(ctx)
    got = _define(ctx, urn, escalate_after=-1)
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    return FAIL, ("`escalate_after: -1` was accepted and stored: nothing "
                  "validates the field, and 0 already means *never escalate*, "
                  "so a negative is a number with no reading that goes into "
                  "the escalation arithmetic")


@case("QA-AM-201",
      "Define a `performance` monitor against a class whose fibre cannot "
      "answer it")
def am_201(ctx: Ctx) -> Result:
    """The check that reads the fibre. A T0 model has no parameters and no
    fitted relationship to lose, so a performance monitor over it runs for
    ever without meaning anything — and reads as coverage."""
    _name, urn = _model(ctx, kernel={"parameter_kind": "none",
                                     "fit_procedure": "none",
                                     "runtime": "expression",
                                     "input_schema": [{"name": "x",
                                                       "dtype": "float"}],
                                     "output_schema": [{"name": "price",
                                                        "dtype": "float"}]})
    got = _define(ctx, urn, kind="performance",
                  test_key="discrimination.auc", threshold={"min": 0.6},
                  label_delay_days=30.0)
    outcome = refused_by_the_control(
        got, "a performance monitor over a class that cannot answer it")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "kind_not_answerable":
        return FAIL, f"refused '{code_of(got)}'"
    if "T0" not in got.text:
        return FAIL, "the refusal does not name the class it read"
    return PASS, "refused 'kind_not_answerable', naming the class"


@case("QA-AM-202", "Define a monitor on a model with no version yet")
def am_202(ctx: Ctx) -> Result:
    """No version means no derived class, so the fibre has no opinion — and
    a refusal here would be an opinion invented from the absence of one. The
    fit gate refuses later, where the fact exists."""
    _name, urn = _model(ctx, version=False)
    got = _define(ctx, urn, kind="performance",
                  test_key="discrimination.auc", threshold={"min": 0.6},
                  label_delay_days=30.0)
    if got.status_code >= 400:
        if code_of(got) == "kind_not_answerable":
            return FAIL, ("a model with no version was refused on the fibre's "
                          "opinion, which it cannot have — the class is "
                          "derived from a version that does not exist")
        return PASS, (f"refused '{code_of(got)}' for a reason other than the "
                      f"fibre")
    return PASS, "accepted: no version, so the fibre has no opinion to give"


@case("QA-AM-4701", "Every label-dependent kind demands a delay")
def am_4701(ctx: Ctx) -> Result:
    """A sweep rather than a case per kind. `LABEL_DEPENDENT` is a tuple and
    the check reads it, so a fifth kind added later is covered without
    anybody remembering to — but only if the tuple is what decides, and this
    is what pins that."""
    _name, urn = _model(ctx)
    slipped = []
    for kind in LABEL_DEPENDENT:
        got = _define(ctx, urn, kind=kind,
                      test_key=ADMISSIBLE_TESTS[kind][0],
                      threshold={"min": 0.1}, label_delay_days=0.0)
        if got.status_code < 400 or code_of(got) != "label_delay_required":
            slipped.append(f"{kind}:{code_of(got) or got.status_code}")
    if slipped:
        return FAIL, (f"a label-dependent kind does not demand a delay: "
                      f"{slipped}")
    others = [k for k in ADMISSIBLE_TESTS if k not in LABEL_DEPENDENT]
    for kind in others:
        got = _define(ctx, urn, kind=kind,
                      test_key=ADMISSIBLE_TESTS[kind][0],
                      threshold={"max": 0.2}, label_delay_days=0.0)
        if got.status_code >= 400 and code_of(got) == "label_delay_required":
            return FAIL, (f"'{kind}' compares nothing to an outcome and is "
                          f"still made to declare a label delay")
    return PASS, (f"{', '.join(LABEL_DEPENDENT)} demand a delay; "
                  f"{', '.join(others)} do not")
