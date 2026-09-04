"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The captive estimator: the runtime that inhabits a parameter object.

Every other runtime here answers the question "what does this model say about
this input". This one answers a different question -- "what parameters does this
data imply" -- and it is the one the platform was missing. Until now MAYA could
issue a fit warrant, refuse a parameter set that no warrant authorised, and
require a second person to approve it, but nothing anywhere could actually
produce the numbers. The documentation said so plainly: parameters were stored,
not computed. A governed path with a hole in the middle is a path nobody can
walk end to end, and a control nobody has walked is a control nobody has tested.

**Two families, chosen because they are the two the worked example uses.**

  * ``ols`` -- ordinary least squares, the multiple linear regression behind
    most scorecards and most of the "simple challenger" estate.
  * ``garch11`` -- a GARCH(1,1) volatility model, which is not linear, has no
    closed form, and therefore exercises the part of the design that a
    closed-form fit would leave untested: an iterative fit can fail to
    converge, and a platform that reports an unconverged fit as a fit is worse
    than one that cannot fit at all.

**What this runtime is not.** It is not a modelling library and does not want to
become one. It is enough to demonstrate the governed path against real
arithmetic and to refuse everything else by name.

**Determinism is a governance requirement, not a nicety.** A fit that cannot be
reproduced cannot be replayed, and a parameter set nobody can reproduce is a
number in a register with no provenance. So there is no randomness anywhere
here: the optimiser starts from a fixed simplex, iterates a fixed number of
times, and stops on a fixed tolerance. Run it twice on the same rows and it
returns the same digits.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.execution.errors import WarrantError
from core.execution.runtimes.base import Invocation
from core.log import get_logger, swallowed

logger = get_logger(__name__)

OLS, GARCH11 = "ols", "garch11"
FAMILIES: Tuple[str, ...] = (OLS, GARCH11)

FAMILY_MEANING: Dict[str, str] = {
    OLS: "ordinary least squares: a linear kernel fitted by minimising squared "
         "residuals, with the closed-form solution and its usual diagnostics",
    GARCH11: "GARCH(1,1): conditional variance following "
             "h_t = omega + alpha*e^2_{t-1} + beta*h_{t-1}, fitted by "
             "maximising the Gaussian log-likelihood",
}

# Below this there is not enough data for a fit to mean anything, and a fit on
# four rows that reports an R-squared of 1.0 is worse than a refusal: it is a
# refusal that looks like a result.
MIN_ROWS = 30
# A GARCH fit that has not settled by here has not settled. Reported rather than
# returned quietly, because an unconverged fit still produces three numbers that
# look exactly like a converged one.
MAX_ITERATIONS = 2000
TOLERANCE = 1e-10
# Stationarity: alpha + beta < 1, or the conditional variance has no unconditional
# mean and the model forecasts an exploding one.
STATIONARITY_CEILING = 0.9999


class EstimatorRuntime:
    """Fits a parameter object from rows the caller supplies."""

    key = "estimator"

    def available(self) -> Optional[str]:
        try:
            import numpy  # noqa: F401
        except ImportError as exc:
            swallowed(logger, exc, "checked whether the estimator can run",
                      detail="numpy is absent, so the runtime reports itself "
                             "unavailable rather than failing at invocation",
                      level=logging.DEBUG)
            return "numpy is not installed, and the estimator is arithmetic on arrays"
        return None

    # ------------------------------------------------------------------ entry
    def invoke(self, call: Invocation) -> Any:
        if why := self.available():
            raise WarrantError("runtime_unavailable", why,
                               "install numpy, or fit elsewhere and record the "
                               "parameters against the warrant")
        verb = (call.warrant.get("operation") or {}).get("verb")
        if verb != "fit":
            raise WarrantError(
                "wrong_verb",
                f"the estimator runtime inhabits a parameter object and the "
                f"warrant's verb is '{verb}'",
                "issue a warrant whose verb is 'fit', or use a runtime that scores")

        entry = call.entry
        family = entry.get("family")
        if family not in FAMILIES:
            raise WarrantError(
                "unknown_family",
                f"'{family}' is not an estimator this engine implements",
                f"use one of {', '.join(FAMILIES)}, or fit it in your own engine "
                f"and record the parameters under this warrant")

        rows = self._rows(call.inputs)
        if family == OLS:
            return self._ols(rows, entry)
        return self._garch11(rows, entry)

    # ------------------------------------------------------------------- data
    @staticmethod
    def _rows(inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = (inputs or {}).get("rows")
        if not isinstance(rows, list):
            raise WarrantError(
                "no_rows",
                "the estimator was given no rows to fit; it expects inputs.rows "
                "to be a list of records",
                "assemble a training set from the featureset version the warrant "
                "names and pass its rows")
        if len(rows) < MIN_ROWS:
            raise WarrantError(
                "too_few_rows",
                f"{len(rows)} rows is below the minimum of {MIN_ROWS}; a fit this "
                f"small reports diagnostics that look like results",
                "widen the window, or accept that this population cannot support "
                "a fitted parameter set")
        return rows

    @staticmethod
    def _column(rows: Sequence[Dict[str, Any]], name: str) -> List[float]:
        """One column as floats, refusing anything that is not a number.

        A missing value is refused here rather than dropped or zeroed. Dropping
        changes the population the fit speaks for without saying so, and the
        featureset's own fill policy is the place that decision belongs -- where
        somebody chose it and it is on the record.
        """
        out = []
        for i, row in enumerate(rows):
            if name not in row:
                raise WarrantError(
                    "column_missing",
                    f"row {i} has no column '{name}'",
                    "check the featureset version the warrant pins actually "
                    "supplies this slot")
            value = row[name]
            if value is None or isinstance(value, bool) or not isinstance(
                    value, (int, float)) or not math.isfinite(float(value)):
                raise WarrantError(
                    "value_not_numeric",
                    f"column '{name}' holds {value!r} at row {i}, which is not a "
                    f"finite number",
                    "apply a fill policy on the featureset so the decision about "
                    "missing values is recorded rather than made here")
            out.append(float(value))
        return out

    # -------------------------------------------------------------------- ols
    def _ols(self, rows: List[Dict[str, Any]], entry: Dict[str, Any]) -> Dict[str, Any]:
        """Least squares by QR, with the diagnostics a validator asks for.

        Solved by ``lstsq`` rather than by inverting X'X: the normal equations
        square the condition number, and a scorecard with two correlated
        regressors is exactly where that stops being a textbook remark.
        """
        import numpy as np

        target = entry.get("target")
        regressors = list(entry.get("regressors") or [])
        if not target or not regressors:
            raise WarrantError(
                "fit_underspecified",
                "an ols fit must name a target and at least one regressor",
                "put 'target' and 'regressors' in the warrant's realisation entry")
        if target in regressors:
            raise WarrantError(
                "target_is_a_regressor",
                f"'{target}' is both the target and a regressor, so the fit would "
                f"predict the answer from the answer",
                "remove it from the regressors")

        y = np.asarray(self._column(rows, target), dtype=float)
        intercept = bool(entry.get("intercept", True))
        columns = [self._column(rows, name) for name in regressors]
        X = np.column_stack(([np.ones(len(y))] if intercept else []) + columns)
        names = (["intercept"] if intercept else []) + regressors

        n, k = X.shape
        if n <= k:
            raise WarrantError(
                "not_identified",
                f"{n} rows cannot identify {k} coefficients; the system is "
                f"underdetermined and any answer would be one of infinitely many",
                "add rows or remove regressors")
        rank = int(np.linalg.matrix_rank(X))
        if rank < k:
            raise WarrantError(
                "collinear_regressors",
                f"the design matrix has rank {rank} for {k} coefficients, so at "
                f"least one regressor is an exact combination of the others and "
                f"its coefficient is not identified",
                "drop the redundant regressor rather than letting the solver "
                "pick one of the infinitely many answers")

        beta, _, _, singular = np.linalg.lstsq(X, y, rcond=None)
        fitted = X @ beta
        residual = y - fitted
        rss = float(residual @ residual)
        tss = float(((y - y.mean()) ** 2).sum())
        dof = n - k
        sigma2 = rss / dof
        # Standard errors from the pseudo-inverse of X'X, which exists because
        # rank was checked above.
        covariance = sigma2 * np.linalg.pinv(X.T @ X)
        stderr = np.sqrt(np.clip(np.diag(covariance), 0.0, None))
        with np.errstate(divide="ignore", invalid="ignore"):
            t_stat = np.where(stderr > 0, beta / stderr, np.nan)

        r2 = 1.0 - rss / tss if tss > 0 else float("nan")
        adjusted = (1.0 - (1.0 - r2) * (n - 1) / dof) if tss > 0 and dof > 0 else float("nan")
        condition = (float(singular.max() / singular.min())
                     if singular.size and singular.min() > 0 else float("inf"))

        return {
            "family": OLS,
            "values": {name: float(b) for name, b in zip(names, beta)},
            "diagnostics": {
                "n": n, "k": k, "degrees_of_freedom": dof,
                "r_squared": self._finite(r2),
                "adjusted_r_squared": self._finite(adjusted),
                "residual_std_error": self._finite(math.sqrt(sigma2)),
                "standard_errors": {nm: float(s) for nm, s in zip(names, stderr)},
                "t_statistics": {nm: self._finite(t) for nm, t in zip(names, t_stat)},
                # The number a validator should look at before any of the others.
                # A condition number in the thousands means the coefficients are
                # a solution to this sample rather than a property of the world.
                "condition_number": self._finite(condition),
                "target": target, "regressors": regressors,
                "intercept": intercept,
            },
        }

    # ---------------------------------------------------------------- garch11
    def _garch11(self, rows: List[Dict[str, Any]], entry: Dict[str, Any]) -> Dict[str, Any]:
        """GARCH(1,1) by maximum likelihood, on a fixed deterministic simplex.

        The mean is removed first and the variance recursion is seeded with the
        sample variance, which is the standard choice and, more to the point, a
        *stated* one: seeding it with the first squared residual makes the fit
        depend on which row happened to be first.
        """
        import numpy as np

        series = entry.get("series")
        if not series:
            raise WarrantError(
                "fit_underspecified",
                "a garch11 fit must name the series whose volatility it models",
                "put 'series' in the warrant's realisation entry")
        x = np.asarray(self._column(rows, series), dtype=float)
        e = x - x.mean()
        var = float(e @ e / len(e))
        if var <= 0:
            raise WarrantError(
                "series_is_constant",
                f"'{series}' does not vary, so it has no volatility to model",
                "check the featureset version supplies the series you meant")

        def negative_log_likelihood(theta) -> float:
            omega, alpha, beta = theta
            if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= STATIONARITY_CEILING:
                return float("inf")
            h = var
            total = 0.0
            for value in e:
                total += math.log(h) + (value * value) / h
                h = omega + alpha * value * value + beta * h
            return 0.5 * total

        start = np.array([var * 0.05, 0.10, 0.85])
        theta, iterations, converged = self._nelder_mead(
            negative_log_likelihood, start)
        omega, alpha, beta = (float(v) for v in theta)
        if not converged:
            raise WarrantError(
                "fit_did_not_converge",
                f"the likelihood had not settled after {iterations} iterations, "
                f"so these three numbers are where the search happened to stop "
                f"rather than where it belongs",
                "a longer or cleaner series usually settles; recording an "
                "unconverged fit as a parameter set would put a number in the "
                "register that nobody could reproduce or defend")

        persistence = alpha + beta
        return {
            "family": GARCH11,
            "values": {"omega": omega, "alpha": alpha, "beta": beta},
            "diagnostics": {
                "n": int(len(e)), "series": series,
                "log_likelihood": self._finite(-negative_log_likelihood(theta)),
                "iterations": iterations, "converged": True,
                "persistence": self._finite(persistence),
                # Long-run variance exists only under stationarity, which the
                # optimiser was constrained to respect; reported so a reviewer
                # can compare it against the sample variance beside it.
                "long_run_variance": self._finite(omega / (1.0 - persistence)),
                "sample_variance": self._finite(var),
                "mean_removed": self._finite(float(x.mean())),
            },
        }

    # -------------------------------------------------------------- optimiser
    @staticmethod
    def _nelder_mead(f, start, max_iterations: int = MAX_ITERATIONS,
                     tolerance: float = TOLERANCE) -> Tuple[Any, int, bool]:
        """Nelder--Mead on a fixed initial simplex.

        Written out rather than imported because scipy is not a dependency here
        and adding one for forty lines of arithmetic would be the wrong trade in
        a platform that vendors everything. Fixed simplex, fixed coefficients,
        no randomness: two runs on the same rows give the same parameters.
        """
        import numpy as np

        n = len(start)
        simplex = np.array([start] + [start + np.eye(n)[i] * (0.05 * abs(start[i]) + 1e-4)
                                      for i in range(n)], dtype=float)
        values = np.array([f(p) for p in simplex])
        for iteration in range(1, max_iterations + 1):
            order = np.argsort(values)
            simplex, values = simplex[order], values[order]
            if abs(values[-1] - values[0]) <= tolerance * (abs(values[0]) + tolerance):
                return simplex[0], iteration, True
            centroid = simplex[:-1].mean(axis=0)
            reflected = centroid + (centroid - simplex[-1])
            fr = f(reflected)
            if fr < values[0]:
                expanded = centroid + 2.0 * (centroid - simplex[-1])
                fe = f(expanded)
                simplex[-1], values[-1] = ((expanded, fe) if fe < fr
                                           else (reflected, fr))
            elif fr < values[-2]:
                simplex[-1], values[-1] = reflected, fr
            else:
                contracted = centroid + 0.5 * (simplex[-1] - centroid)
                fc = f(contracted)
                if fc < values[-1]:
                    simplex[-1], values[-1] = contracted, fc
                else:
                    simplex[1:] = simplex[0] + 0.5 * (simplex[1:] - simplex[0])
                    values[1:] = [f(p) for p in simplex[1:]]
        return simplex[int(np.argmin(values))], max_iterations, False

    @staticmethod
    def _finite(value: float) -> Optional[float]:
        """JSON has no NaN. A diagnostic that cannot be computed says so as null
        rather than as a token that decodes differently in every language."""
        value = float(value)
        return value if math.isfinite(value) else None
