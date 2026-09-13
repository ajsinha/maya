"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the reference estimator, and what it refuses to fit.

A fit that "succeeds" on data that cannot support it produces coefficients
somebody will approve. Every refusal here is a number the platform declines to
produce — and the sharpest is the target appearing among its own regressors,
which fits perfectly and means nothing.
"""
from __future__ import annotations

from core.execution.runtimes.estimator import MIN_ROWS, EstimatorRuntime
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)


def _rows(n: int, **columns):
    return [{key: values[i] for key, values in columns.items()}
            for i in range(n)]


def _linear(n: int, noise=0.0):
    x = [float(i) for i in range(n)]
    y = [2.0 * v + 1.0 + (noise if i % 2 else -noise)
         for i, v in enumerate(x)]
    return x, y


def _fit(ctx: Ctx, rows, target="y", regressors=("x",)):
    """Call the estimator's own least squares directly."""
    from core.execution.errors import WarrantError
    runtime = EstimatorRuntime()
    entry = {"target": target, "regressors": list(regressors)}
    try:
        return runtime._ols(list(rows), entry), None
    except WarrantError as exc:
        return None, exc


@case("QA-FX-260", "Exactly one row below the minimum, then the minimum")
def fx_260(ctx: Ctx) -> Result:
    """"A fit this small is not an estimate." The boundary must bite on one
    side only, or the limit excludes the first size it admits."""
    # The row-count guard lives in `_rows`, which turns the warrant's
    # inputs into a frame — not in `_ols`, which is handed one. Calling the
    # solver directly walks past the check entirely.
    from core.execution.errors import WarrantError
    runtime = EstimatorRuntime()
    x, y = _linear(MIN_ROWS)

    def frame(n):
        return {"rows": _rows(n, x=x, y=y)}

    try:
        runtime._rows(frame(MIN_ROWS - 1))
    except WarrantError as exc:
        if exc.code != "too_few_rows":
            return FAIL, f"refused '{exc.code}', not too_few_rows"
        if str(MIN_ROWS) not in str(exc):
            return FAIL, f"the refusal does not state the minimum: {exc}"
    else:
        return FAIL, f"{MIN_ROWS - 1} rows was accepted as a frame to fit"
    try:
        runtime._rows(frame(MIN_ROWS))
    except WarrantError as exc:
        return FAIL, (f"exactly {MIN_ROWS} rows was refused '{exc.code}'; "
                      f"the minimum excludes itself")
    return PASS, f"{MIN_ROWS - 1} refused naming the minimum, {MIN_ROWS} accepted"


@case("QA-FX-263", "The target appearing as a regressor")
def fx_263(ctx: Ctx) -> Result:
    """Fits perfectly, means nothing, and every diagnostic a validator reads
    says the model is excellent."""
    x, y = _linear(40)
    fitted, exc = _fit(ctx, _rows(40, x=x, y=y), regressors=("x", "y"))
    if fitted is not None:
        return FAIL, ("a regression was fitted with its own target among the "
                      "regressors; it fits perfectly and means nothing")
    if exc.code != "target_is_a_regressor":
        return FAIL, f"refused '{exc.code}', not target_is_a_regressor"
    return PASS, f"refused '{exc.code}'"


@case("QA-FX-261", "Two perfectly collinear regressors")
def fx_261(ctx: Ctx) -> Result:
    """The coefficients are not identified: any split between the two fits
    equally well, and the numbers a validator reads are one arbitrary
    choice."""
    x, y = _linear(40)
    doubled = [2.0 * v for v in x]
    fitted, exc = _fit(ctx, _rows(40, x=x, x2=doubled, y=y),
                       regressors=("x", "x2"))
    if fitted is not None:
        return FAIL, ("two perfectly collinear regressors were fitted, so the "
                      "coefficients are one arbitrary split of many")
    if exc.code != "collinear_regressors":
        return FAIL, f"refused '{exc.code}', not collinear_regressors"
    return PASS, f"refused '{exc.code}'"


@case("QA-FX-262", "Two nearly collinear regressors")
def fx_262(ctx: Ctx) -> Result:
    """Accepted, because refusing every correlated pair would refuse most
    real scorecards — and reported, because the condition number is what
    tells a validator the coefficients are unstable."""
    x, y = _linear(60)
    nearly = [2.0 * v + (0.001 if i % 2 else -0.001)
              for i, v in enumerate(x)]
    fitted, exc = _fit(ctx, _rows(60, x=x, x2=nearly, y=y),
                       regressors=("x", "x2"))
    if fitted is None:
        return PASS, f"refused '{exc.code}' — near collinearity is refused too"
    diagnostics = str(fitted)
    if "condition" not in diagnostics:
        return FAIL, ("nearly collinear regressors were fitted and no "
                      "condition number is reported, so nothing tells a "
                      "validator the coefficients are unstable")
    return PASS, "fitted, with a condition number reported"


@case("QA-FX-264", "A constant series")
def fx_264(ctx: Ctx) -> Result:
    """A regressor that never varies explains nothing and makes the design
    matrix singular."""
    _, y = _linear(40)
    flat = [1.0] * 40
    fitted, exc = _fit(ctx, _rows(40, x=flat, y=y))
    if fitted is not None:
        return FAIL, "a constant regressor was fitted"
    if exc.code not in ("series_is_constant", "collinear_regressors"):
        return FAIL, f"refused '{exc.code}'"
    return PASS, f"refused '{exc.code}'"


@case("QA-FX-265", "A non-numeric value in a regressor")
def fx_265(ctx: Ctx) -> Result:
    """Coercing it would put a silent zero in a coefficient nobody can
    trace."""
    x, y = _linear(40)
    rows = _rows(40, x=x, y=y)
    rows[17]["x"] = "n/a"
    fitted, exc = _fit(ctx, rows)
    if fitted is not None:
        return FAIL, "a non-numeric value was coerced into a fit"
    if exc.code != "value_not_numeric":
        return FAIL, f"refused '{exc.code}', not value_not_numeric"
    return PASS, f"refused '{exc.code}'"


@case("QA-FX-4900", "A boolean is not a number")
def fx_4900(ctx: Ctx) -> Result:
    """`isinstance(True, int)` is True in Python. A regressor of booleans
    that slipped through would fit as ones and zeros with nothing saying the
    column was never numeric."""
    x, y = _linear(40)
    rows = _rows(40, x=x, y=y)
    rows[9]["x"] = True
    fitted, exc = _fit(ctx, rows)
    if fitted is not None:
        return FAIL, ("a boolean was accepted as a numeric regressor; "
                      "isinstance(True, int) is True and the check did not "
                      "exclude it")
    return PASS, f"refused '{exc.code}'"


@case("QA-FX-4901", "A column the rows do not have")
def fx_4901(ctx: Ctx) -> Result:
    """Naming it matters: a fit against a column that is absent is a typo in
    a warrant, and discovering it as a KeyError tells nobody which."""
    x, y = _linear(40)
    fitted, exc = _fit(ctx, _rows(40, x=x, y=y), regressors=("moon_phase",))
    if fitted is not None:
        return FAIL, "a fit ran against a column the rows do not have"
    if exc.code != "column_missing":
        return FAIL, f"refused '{exc.code}', not column_missing"
    if "moon_phase" not in str(exc):
        return FAIL, f"the refusal does not name the column: {exc}"
    return PASS, f"refused '{exc.code}', naming the column"


@case("QA-FX-4902", "A fit with no target or no regressors")
def fx_4902(ctx: Ctx) -> Result:
    """Underspecified rather than empty: there is nothing to estimate, and
    returning an empty coefficient set would be a parameter object that
    inhabits nothing."""
    x, y = _linear(40)
    rows = _rows(40, x=x, y=y)
    for target, regressors in (("", ("x",)), ("y", ())):
        fitted, exc = _fit(ctx, rows, target=target, regressors=regressors)
        if fitted is not None:
            return FAIL, (f"a fit with target={target!r} and "
                          f"regressors={regressors} produced coefficients")
        if exc.code != "fit_underspecified":
            return FAIL, f"refused '{exc.code}', not fit_underspecified"
    return PASS, "both underspecified forms refused"


@case("QA-FX-268", "The same fit run twice")
def fx_268(ctx: Ctx) -> Result:
    """Bit-identical, or a parameter set's digest changes without the data
    changing and every replay reports a mismatch."""
    x, y = _linear(50, noise=0.3)
    rows = _rows(50, x=x, y=y)
    first, _ = _fit(ctx, rows)
    second, _ = _fit(ctx, rows)
    if first is None or second is None:
        return BLOCKED, "the fit did not run"
    if first != second:
        differing = [k for k in first if first.get(k) != second.get(k)]
        return FAIL, (f"two runs over identical rows differ in {differing}; "
                      f"a parameter set's digest would change without the "
                      f"data changing")
    return PASS, "bit-identical across two runs"


@case("QA-FX-271", "Diagnostics travel with the coefficients")
def fx_271(ctx: Ctx) -> Result:
    """A coefficient with no diagnostics is a number a validator cannot
    challenge. The row count, the regressor count and a goodness measure are
    the minimum a review asks for."""
    x, y = _linear(50, noise=0.4)
    fitted, exc = _fit(ctx, _rows(50, x=x, y=y))
    if fitted is None:
        return BLOCKED, f"the fit was refused '{exc.code}'"
    # `values`, `diagnostics` and `family` — the coefficients are the
    # values, and the diagnostics travel beside them rather than among them.
    if not fitted.get("values"):
        return FAIL, f"the fit reports no coefficients: {sorted(fitted)}"
    diagnostics = fitted.get("diagnostics") or {}
    if not diagnostics:
        return FAIL, ("coefficients came back with no diagnostics at all, so "
                      "a validator has nothing to challenge")
    text = str(diagnostics)
    if not any(k in text for k in ("r_squared", "r2", "condition",
                                   "standard_error", "std_error", "n")):
        return FAIL, (f"the diagnostics carry no goodness or stability "
                      f"measure: {sorted(diagnostics)}")
    return PASS, f"{len(fitted['values'])} coefficient(s), diagnostics {sorted(diagnostics)[:5]}"
