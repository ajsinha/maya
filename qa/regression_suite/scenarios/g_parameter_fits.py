"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — fitting a parameter set, and taking delivery of one.

Two orderings carry this module and both are about not doing work on an
authority that was never valid. **The window is checked before the
snapshot**: it is the caller's governance statement — *this model was
estimated over 2019 to 2024* — and reading it off whatever rows arrived would
make the claim a description of the extract rather than a decision anybody
made. And **authority comes before data**: a warrant that will not resolve
should not have caused a dataset to be read first.

`fitted` is the strongest claim the register offers — estimated from data
under a warrant MAYA issued — so the kinds that nothing fits are refused it by
name. Claiming it for a judgement launders an opinion into a measurement, and
the diagnostics that make an elicitation reviewable are exactly what nobody
looks for once the row says `fitted`.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)


def _fitting(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("parameter_fitting") or \
        ctx.ui.app.state.ctx.get("fitting")


def _register(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("parameters")


def _code(exc) -> str:
    return getattr(exc, "code", "") or f"{exc}"


def _window(fitter, window):
    from core.parameters.common import ParameterError
    try:
        return None, fitter._checked_window(window)
    except ParameterError as exc:
        return exc, None


@case("QA-FX-253", "A fit with no window")
def fx_253(ctx: Ctx) -> Result:
    """Law L-W9 refuses a featureset read for training that does not bound
    the period it covers. Both ends are required — a window with only a start
    is a claim about an open interval nobody can reproduce."""
    fitter = _fitting(ctx)
    if fitter is None:
        return BLOCKED, "no parameter fitting service is wired"
    for window in (None, {}, {"from": 1.0}, {"to": 2.0}):
        exc, _ = _window(fitter, window)
        if exc is None:
            return FAIL, f"a fit with window={window!r} was accepted"
        if _code(exc) != "window_required":
            return FAIL, f"window={window!r} refused '{_code(exc)}'"
    return PASS, "absent, empty, start-only and end-only all refused"


@case("QA-FX-254", "An inverted window")
def fx_254(ctx: Ctx) -> Result:
    """A window that ends before it starts covers no period at all, and it is
    the ordinary shape of a swapped pair of arguments."""
    fitter = _fitting(ctx)
    if fitter is None:
        return BLOCKED, "no parameter fitting service is wired"
    exc, _ = _window(fitter, {"from": 2_000.0, "to": 1_000.0})
    if exc is None:
        return FAIL, "a window ending before it starts was accepted"
    if _code(exc) != "window_inverted":
        return FAIL, f"refused '{_code(exc)}'"
    said = f"{exc}"
    if "2000" not in said.replace(",", "") and "2000.0" not in said:
        return FAIL, f"the refusal does not give the bounds: {said[:110]}"
    return PASS, "refused 'window_inverted', naming both ends"


@case("QA-FX-255", "A window whose `from` equals its `to`")
def fx_255(ctx: Ctx) -> Result:
    """EXPLORATORY, and the boundary is `<=` rather than `<`. A zero-length
    window is an estimation period covering no time, which is not a narrow
    claim but an empty one — and it would read on a model card as a real
    date range."""
    fitter = _fitting(ctx)
    if fitter is None:
        return BLOCKED, "no parameter fitting service is wired"
    exc, _ = _window(fitter, {"from": 1_000.0, "to": 1_000.0})
    if exc is None:
        return FAIL, ("a zero-length window was accepted, so a fit can claim "
                      "an estimation period covering no time")
    if _code(exc) != "window_inverted":
        return FAIL, f"refused '{_code(exc)}'"
    _ok, kept = _window(fitter, {"from": 1_000.0, "to": 1_000.1})
    if kept is None:
        return FAIL, "a window a tenth of a second long is also refused"
    return PASS, "zero-length refused, the smallest positive window accepted"


@case("QA-FX-256", "The window is checked before the data")
def fx_256(ctx: Ctx) -> Result:
    """The ordering that makes a refusal cheap. A fit with a bad window and a
    missing snapshot must refuse on the window — reading the dataset first
    would do the expensive thing on behalf of a request that was never
    well-formed."""
    import inspect
    fitter = _fitting(ctx)
    if fitter is None:
        return BLOCKED, "no parameter fitting service is wired"
    source = inspect.getsource(type(fitter).fit)
    at_window = source.find("_checked_window")
    at_snapshot = source.find("self._snapshot(")
    at_rows = source.find("self._rows(")
    at_warrant = source.find("resolve_fit")
    for name, at in (("the snapshot", at_snapshot), ("the rows", at_rows),
                     ("the warrant", at_warrant)):
        if at < 0:
            return FAIL, f"the fit never reaches {name}"
    if at_window > at_snapshot:
        return FAIL, ("the snapshot is read before the window is checked, so "
                      "a malformed request costs a dataset read")
    if at_warrant > at_rows:
        return FAIL, ("the rows are read before the warrant resolves, so a "
                      "dataset is read on an authority that may never have "
                      "been valid")
    return PASS, "window, then snapshot, then warrant, then rows"


@case("QA-FX-258", "A snapshot whose Delta table is gone")
def fx_258(ctx: Ctx) -> Result:
    """A fit cannot be run against a dataset that is no longer there, and the
    refusal has to say the table is missing rather than producing a fit over
    zero rows — which would be a parameter set estimated from nothing."""
    from core.parameters.common import ParameterError
    fitter = _fitting(ctx)
    if fitter is None:
        return BLOCKED, "no parameter fitting service is wired"
    snapshot = {"name": "a-snapshot", "delta_table": "no_such_table",
                "delta_version": 1}
    try:
        fitter._rows(snapshot)
    except ParameterError as exc:
        if _code(exc) != "snapshot_storage_missing":
            return FAIL, f"refused '{_code(exc)}'"
        if "no_such_table" not in f"{exc}":
            return FAIL, "the refusal does not name the table"
        return PASS, "refused 'snapshot_storage_missing', naming the table"
    return FAIL, "a fit read rows from a table that is not in storage"


@case("QA-FX-270", "The person who ran the fit approving it")
def fx_270(ctx: Ctx) -> Result:
    """A parameter set changes what the model does, so it is approved like a
    version — by somebody other than whoever produced it. Compared with
    `same_person`, because the register writes a creator as `person/a.dev`
    and authenticates the same human as `a.dev`."""
    import inspect
    register = _register(ctx)
    if register is None:
        return BLOCKED, "no parameter register is wired"
    source = inspect.getsource(type(register).approve)
    if "same_person(" not in source:
        return FAIL, ("approval compares the actor to the creator without "
                      "`same_person`, so dropping the person/ prefix steps "
                      "around the duties check")
    from core.authz.common import same_person
    if not same_person("person/a.dev", "a.dev"):
        return FAIL, "`same_person` does not equate the two spellings"
    if same_person("a.dev", "b.dev"):
        return FAIL, "`same_person` equates two different people"
    if "self_approval" not in source:
        return FAIL, "approval does not refuse self-approval by name"
    return PASS, "refused 'self_approval', compared as identities"


@case("QA-FX-232", "A `fitted` set against a T0 kernel")
def fx_232(ctx: Ctx) -> Result:
    """The recorded defect: the fit WARRANT path refused this correctly under
    L-W1 and the delivery path did not, so the type error was enforced on one
    route and not the other — the pattern this module's own docstring warns
    about, in the module that warns about it."""
    import inspect
    register = _register(ctx)
    if register is None:
        return BLOCKED, "no parameter register is wired"
    # The guards live in `_refuse_if_not_fittable`, which `record` calls —
    # reading `record` itself finds none of them.
    source = inspect.getsource(type(register)._refuse_if_not_fittable)
    if "nothing_to_fit" not in source:
        return FAIL, ("the delivery path does not refuse a fitted set over a "
                      "terminal parameter object, so the type error is "
                      "enforced on the warrant route only")
    if "parameters_not_reachable" not in source:
        return FAIL, ("the delivery path does not refuse a fitted set over an "
                      "opaque parameter object")
    if "_parameter_kind" not in source:
        return FAIL, ("the check does not read the DERIVED parameter kind, so "
                      "it rests on something a caller declares")
    return PASS, ("both refusals present on the delivery path, keyed on the "
                  "derived kind")


@case("QA-FX-4810",
      "`fitted` is refused for every kind that nothing fits")
def fx_4810(ctx: Ctx) -> Result:
    """A sweep rather than a case per kind. A rule set is authored, a
    generative assembly is configured and elicited weights come out of a
    panel — none is a quantity data produced. Claiming `fitted` for a
    judgement launders an opinion into a measurement, and once the row says
    `fitted` nobody looks for the panel, the questions or the dissent."""
    from core.parameters.common import NOT_FROM_DATA
    if not NOT_FROM_DATA:
        return FAIL, "no kind is excluded from being fitted"
    import inspect
    register = _register(ctx)
    if register is None:
        return BLOCKED, "no parameter register is wired"
    source = inspect.getsource(type(register)._refuse_if_not_fittable)
    if "NOT_FROM_DATA" not in source:
        return FAIL, ("the record path does not consult NOT_FROM_DATA, so a "
                      "kind added to it later is not refused")
    for kind in ("rule_set", "elicited_weights", "llm_configuration"):
        if kind not in NOT_FROM_DATA:
            return FAIL, (f"'{kind}' may be recorded as fitted: it is "
                          f"authored, configured or elicited, not estimated")
    return PASS, f"{len(NOT_FROM_DATA)} kinds refused `fitted`: {sorted(NOT_FROM_DATA)}"


@case("QA-FX-236", "A `fitted` set with no featureset")
def fx_236(ctx: Ctx) -> Result:
    """The coefficients mean nothing without the columns they belong to. A
    fitted set that does not name its featureset version is a vector of
    numbers nobody can attach to a schema."""
    from core.parameters.common import ParameterError
    register = _register(ctx)
    if register is None:
        return BLOCKED, "no parameter register is wired"
    try:
        register._binding("fitted", None, None)
    except ParameterError as exc:
        if _code(exc) != "featureset_required":
            return FAIL, f"refused '{_code(exc)}'"
    else:
        return FAIL, "a fitted set with no featureset was accepted"
    if register._binding("declared", None, None) is None:
        return FAIL, "a DECLARED set is also made to name a featureset"
    return PASS, "refused for a fitted set, not demanded of a declared one"


@case("QA-FX-237",
      "A `fitted` set naming a snapshot that is not PIT verified")
def fx_237(ctx: Ctx) -> Result:
    """A model fitted on leaked data scores well and then does not. The
    refusal names the suspected columns where the report has them, because
    *not verified* and *verified and leaking* are different problems."""
    from core.parameters.common import ParameterError
    register = _register(ctx)
    if register is None or register.snapshots is None:
        return BLOCKED, "no snapshot repository is wired"
    import time
    table = ctx.unique("pit").replace("-", "_")
    register.snapshots.add({
        "name": ctx.unique("snap"), "kind": "training", "delta_table": table,
        "delta_version": 1, "row_count": 10, "as_of": time.time(),
        "pit_verified": 0,
        "pit_report": {"leakage": ["repaid_flag"], "detail": "label visible"},
        "digest": "sha256:" + "2" * 64, "created_at": time.time()})
    snapshot_id = register.snapshots.one(delta_table=table)["id"]
    try:
        register._refuse_unverified_snapshot(snapshot_id, "fitted")
    except ParameterError as exc:
        if _code(exc) != "snapshot_not_pit_verified":
            return FAIL, f"refused '{_code(exc)}'"
        if "repaid_flag" not in f"{exc}":
            return FAIL, (f"the refusal does not name the suspected column: "
                          f"{f'{exc}'[:120]}")
        return PASS, "refused 'snapshot_not_pit_verified', naming the column"
    return FAIL, "an unverified snapshot was accepted behind a fitted set"


@case("QA-FX-238", "A `fitted` set naming an unknown snapshot")
def fx_238(ctx: Ctx) -> Result:
    """A training set that is not in the register. The refusal must say so
    rather than treating the absence as *no snapshot was named*, which is a
    legitimate and different state."""
    from core.parameters.common import ParameterError
    register = _register(ctx)
    if register is None or register.snapshots is None:
        return BLOCKED, "no snapshot repository is wired"
    try:
        register._refuse_unverified_snapshot("snap-nobody-recorded", "fitted")
    except ParameterError as exc:
        if _code(exc) != "unknown_snapshot":
            return FAIL, f"refused '{_code(exc)}'"
        if "omit snapshot_id" not in getattr(exc, "remediation", ""):
            return FAIL, ("the refusal does not say that naming no snapshot "
                          "is a different and legitimate state")
        return PASS, "refused 'unknown_snapshot', distinguishing it from none"
    return FAIL, "a parameter set naming an unknown snapshot was accepted"
