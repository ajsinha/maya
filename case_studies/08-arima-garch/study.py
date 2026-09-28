"""
What the steps of this case study share: names, feature definitions with their lags, the
two models, the GARCH implementation, the documents, and the people.

Nothing here talks to MAYA. Steps find each other's work by name.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np

NS = "market_risk"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("index_daily",)
NEWLINE = b"\n"

PANEL = "return_panel"
PIN = "ts2025"
MEAN_MODEL = "ar2_mean"
VOL_MODEL = "garch11_vol"
MEAN_WARRANT = "ar2_fit_2025"
VOL_WARRANT = "garch_fit_2025"
LIVE = "garch_vol_live"

AS_OF = dt.date(2025, 6, 30)
KNOWN = dt.datetime(2025, 7, 15, tzinfo=dt.timezone.utc)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
CONTACT = "market.risk.quant@example.com"
EXTRA_USERS = {"lara": ["model_manager"]}

# The generating process (make_data.py), for the README's comparison.
TRUE_AR = {"c": 0.00028, "phi1": 0.062, "phi2": -0.041}
TRUE_GARCH = {"omega": 3.39e-6, "alpha": 0.092, "beta": 0.880}

# ---------------------------------------------------------------------------------
# The conditional mean: an AR(2), which *is* a row-wise formula once the lags are
# features. That is the whole trick of this half of the study — the lag structure stops
# being a line of pandas inside somebody's fitting script and becomes a declared
# transform on a governed feature, so a reviewer can see that the model is AR(2) without
# reading any Python.
# ---------------------------------------------------------------------------------
MEAN_FORMULA = """
rHat = c + phi1*retLag1 + phi2*retLag2
"""
MEAN_WEIGHTS = ("c", "phi1", "phi2")
MEAN_ROLES = {
    **{w: "parameter" for w in MEAN_WEIGHTS},
    "retLag1": "feature",
    "retLag2": "feature",
}

# AR(2) is stationary only inside a triangle in (phi1, phi2):
#
#     phi1 + phi2 < 1,    phi2 - phi1 < 1,    |phi2| < 1
#
# The third is a bound on one parameter and MAYA has always been able to say it. The first
# two are *joint*: each coefficient can sit anywhere in (-1, 1) and the pair still describe a
# process that explodes. They are properties of the model, so they are declared in the model.
MEAN_CONSTRAINTS = [
    {
        "expr": {"op": "add", "args": [{"param": "phi1"}, {"param": "phi2"}]},
        "op": "lt",
        "rhs": 1.0,
        "why": (
            "phi1 + phi2 < 1 is half of AR(2) stationarity: at or above one the process has a "
            "unit root or worse, the long-run mean does not exist, and a forecast at any "
            "horizon diverges"
        ),
    },
    {
        "expr": {"op": "sub", "args": [{"param": "phi2"}, {"param": "phi1"}]},
        "op": "lt",
        "rhs": 1.0,
        "why": (
            "phi2 - phi1 < 1 is the other half: it rules out the explosive oscillating root, "
            "which a fit can reach while both coefficients still look individually modest"
        ),
    },
]

# ---------------------------------------------------------------------------------
# The conditional variance: GARCH(1,1), which is *not* a row-wise formula.
#
#     sigma2_t = omega + alpha * shock_{t-1}^2 + beta * sigma2_{t-1}
#
# The variance on the right is yesterday's variance, which is not an observable column: it is
# a state the model carries from row to row, and there is no lag transform that can produce
# it because it depends on the parameters. MAYA's formula language evaluates one row at a
# time, so this cannot be expressed in it, and pretending otherwise would be worse than
# admitting it. The model is registered as a declared black box with a code artifact.
# ---------------------------------------------------------------------------------
VOL_IR: dict[str, Any] = {
    "outputs": [{"name": "sigma2", "type": "float64"}],
    "inputs": [
        {"name": "ret", "type": "float64", "role": "feature"},
        {"name": "index", "type": "string", "role": "feature"},
        {"name": "omega", "type": "float64", "role": "parameter", "bounds": [1e-12, 1e-2]},
        {"name": "alpha", "type": "float64", "role": "parameter", "bounds": [0.0, 1.0]},
        {"name": "beta", "type": "float64", "role": "parameter", "bounds": [0.0, 1.0]},
    ],
    "black_box": {
        "estimates": (
            "the conditional variance of each day's log return, given every return before it"
        ),
        "architecture": (
            "GARCH(1,1): sigma2_t = omega + alpha*shock_{t-1}^2 + beta*sigma2_{t-1}, recursed "
            "separately for each index from the unconditional variance omega/(1-alpha-beta), "
            "the shock measured against the mean of the returns before it, fitted by maximum "
            "likelihood under a Gaussian conditional density with variance targeting. "
            "Recursive by construction: the variance is a state carried between rows, which is "
            "why this is a black box and not a formula"
        ),
    },
    "constraints": [
        {
            "expr": {"op": "add", "args": [{"param": "alpha"}, {"param": "beta"}]},
            "op": "lt",
            "rhs": 1.0,
            "why": (
                "alpha + beta < 1 is stationarity: at or above one the conditional variance "
                "has no finite long-run mean, the term structure of volatility rises without "
                "limit, and every value-at-risk number computed from it is meaningless. Each "
                "coefficient can sit well inside [0, 1] while the pair cannot"
            ),
        }
    ],
}
VOL_WEIGHTS = ("omega", "alpha", "beta")

# The desk's implementation, written to MAYA's model interface. The recursion is the reason
# the model is a black box, and it is right here in eight lines: MAYA cannot express it, but
# it can still run it in a sandbox, hash it, and refuse to let it be submitted if it does not
# parse, imports something forbidden, touches the filesystem or is non-deterministic.
VOL_CODE = '''
"""GARCH(1,1) conditional variance, one recursion per index. Desk implementation."""
import numpy as np


class Model:
    def fit(self, X, y, ctx):
        """Fitting happens in the research environment: this artifact only recurses."""
        return {}

    def predict(self, X, params, ctx):
        ret = np.asarray(X["ret"], dtype=float)
        names = np.asarray(X["index"]).astype(str)
        omega, alpha, beta = params["omega"], params["alpha"], params["beta"]
        variance = np.empty(len(ret))
        for name in np.unique(names):
            rows = np.flatnonzero(names == name)  # already in date order
            state = omega / max(1.0 - alpha - beta, 1e-9)  # the unconditional variance
            total, seen = 0.0, 0
            for t in rows:
                variance[t] = state  # known before day t's return
                mean = total / seen if seen else 0.0  # only the returns before day t
                shock = ret[t] - mean
                state = omega + alpha * shock * shock + beta * state
                total, seen = total + ret[t], seen + 1
        return variance
'''

# ---------------------------------------------------------------------------------
# Features. The lag structure and the squared return are declared transforms on the feed,
# not lines in a fitting script.
# ---------------------------------------------------------------------------------
DAILY_DEF = {
    "index": ["date", "index"],
    "index_types": {"date": "date", "index": "string"},
    "schema": [{"name": "close", "type": "float64"}, {"name": "ret", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [
        # A lag is grouped by everything after the first index column, so each index gets its
        # own history and never borrows another's. That is the sort of mistake that is easy to
        # make in five lines of pandas and impossible to see in a review of them.
        {"op": "lag", "attr": "ret", "n": 1, "name": "retLag1"},
        {"op": "lag", "attr": "ret", "n": 2, "name": "retLag2"},
        {"op": "derive", "name": "retSq", "expr": "ret * ret"},
    ],
    "quality": [
        {"check": "not_null", "attr": "ret"},
        # A daily log return outside ±40% is not a crash, it is a corporate action nobody
        # adjusted for.
        {"check": "range", "attr": "ret", "min": -0.4, "max": 0.4},
    ],
}

DEFINITIONS = {"index_daily": DAILY_DEF}

PANEL_DEF = {
    "index": ["date", "index"],
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/index_daily@v1", "source_attr": attr}
        for attr in ("ret", "retLag1", "retLag2", "retSq")
    ],
}

TARGET_JUSTIFICATION_MEAN = (
    "The target 'ret' is today's log return and the drivers are its own first two lags, so "
    "every row is built from values known strictly before the one it predicts. The knowledge "
    "time on the panel is the close of the day the return is about, which is later than the "
    "start of that day by the length of a trading session: the exception covers that, and "
    "nothing else. No driver here is known after its own row."
)
TARGET_JUSTIFICATION_VOL = (
    "The target 'retSq' is the squared return of the day whose volatility is being forecast, "
    "so it is known at that day's close and not before. It is a noisy proxy for a quantity "
    "nobody observes — realised variance on a single day is a one-observation estimate of it — "
    "and it is never an input: the model reads the return history only. The exception covers "
    "the target column alone."
)

SECTIONS_MEAN = {
    "Purpose": (
        "Forecast the conditional mean of tomorrow's daily log return on a broad equity index "
        "from its own recent history, as the mean component of a two-part model whose other "
        "half is the conditional variance."
    ),
    "Scope and Limitations": (
        "Daily log returns on liquid broad indices. The predictable component of a daily "
        "equity return is very small — an R-squared of a few tenths of a per cent is the "
        "honest expectation — and this model must not be read as a trading signal: transaction "
        "costs exceed the forecast at any realistic size. Its purpose is to remove the little "
        "structure there is from the residual, so that the variance model is fitted to "
        "something closer to a shock."
    ),
    "Mathematical Formulation": (
        "An AR(2) on the log return: $\\hat r_t = c + \\phi_1 r_{t-1} + \\phi_2 r_{t-2}$. The "
        "two lags are \\emph{features}, produced by declared lag transforms on the return feed and "
        "grouped by index so no series borrows another's history. Stationarity requires "
        "$\\phi_1 + \\phi_2 < 1$, $\\phi_2 - \\phi_1 < 1$ and $|\\phi_2| < 1$: the third is a "
        "bound on one coefficient, the first two are joint conditions that no per-parameter "
        "bound can express, and all three are declared on the model."
    ),
    "Assumptions": (
        "That two lags are enough, which the partial autocorrelation supports on this data and "
        "which a longer sample might not. That the coefficients are constant over the fitting "
        "window — a regime change in market microstructure would break that, and the model has "
        "no way to notice. And that the residual is what the variance model should be fitted "
        "to, which is only true to the extent this mean model is right."
    ),
    "Data and Features Used": (
        "Feature set market_risk/return_panel, pinned point-in-time: the log return and its "
        "first two lags, from the daily index feed, known at that day's close."
    ),
    "Calibration Methodology": (
        "Ordinary least squares on the training partition, which for an AR model with fixed "
        "lags is the conditional maximum likelihood estimator under a Gaussian shock. The "
        "first two rows of each index have no lags and are excluded rather than filled: a "
        "zero there is not a missing return, it is an invented one."
    ),
    "Validation Evidence": (
        "Fitted coefficients against the process that generated this synthetic series, the "
        "R-squared on training and validation, and MAYA's blind score against the realised "
        "return on the escrowed partition — quoted beside the score of forecasting the sample "
        "mean, because on a daily return series those two are very close and saying so is the "
        "point."
    ),
    "Known Weaknesses": (
        "The predictable part of a daily return is a rounding error next to its variance, so "
        "almost any error statistic will look the same for this model and for a constant. It "
        "carries no exogenous driver, no day-of-week effect and no asymmetry. And it is fitted "
        "by least squares under an assumption of constant variance that the companion "
        "volatility model exists precisely because it is false — the coefficients are "
        "consistent but their standard errors are understated."
    ),
    "Change Log": "Version 1: initial AR(2) conditional mean.",
}

SECTIONS_VOL = {
    "Purpose": (
        "Forecast the conditional variance of tomorrow's daily log return, for "
        "value-at-risk, for option pricing inputs and for limit monitoring. The companion to "
        "market_risk/ar2_mean, which forecasts the conditional mean."
    ),
    "Scope and Limitations": (
        "Daily log returns on liquid broad indices, each recursed on its own with one pooled "
        "parameter set. It is a symmetric "
        "model: it treats a fall and a rise of equal size as equally informative about "
        "tomorrow's variance, which is false for equities — the leverage effect is real and a "
        "GJR or EGARCH extension is the usual answer. It forecasts one day ahead; the "
        "multi-day term structure follows from the same parameters and is only as good as the "
        "stationarity assumption. It says nothing about the shape of the tail beyond its scale."
    ),
    "Mathematical Formulation": (
        "GARCH(1,1): $\\sigma_t^2 = \\omega + \\alpha \\varepsilon_{t-1}^2 + \\beta "
        "\\sigma_{t-1}^2$, where $\\varepsilon$ is the return less the mean of the returns before "
        "it, recursed for each index from the unconditional variance $\\omega/(1-\\alpha-\\beta)$, "
        "with the forecast being $\\sigma_t^2$. Nothing after day $t-1$ enters the forecast for "
        "day $t$. \\textbf{This is not a row-wise expression.} The "
        "variance on the right is yesterday's variance, which is not an observable column but "
        "a state carried from row to row and dependent on the parameters, so no lag transform "
        "can produce it. MAYA's formula language evaluates one row at a time, so the model is "
        "registered as a declared black box with a code artifact rather than written as a "
        "formula that would be a lie. Stationarity requires $\\alpha + \\beta < 1$ and is "
        "declared as a constraint on the model."
    ),
    "Assumptions": (
        "That the conditional density is Gaussian, which understates the tails — the fitted "
        "parameters are still consistent under quasi-maximum likelihood, but any quantile read "
        "off a normal distribution at this volatility will be too small. That one lag of each "
        "term is enough. That $\\omega$ is identified, which under variance targeting it is "
        "not: it is pinned to the sample variance and the persistence, so a change in the "
        "sample changes it whether or not the process changed."
    ),
    "Data and Features Used": (
        "Feature set market_risk/return_panel, pinned point-in-time: the log return series, "
        "and the squared return as the benchmark the forecast is measured against."
    ),
    "Calibration Methodology": (
        "Quasi-maximum likelihood under a Gaussian conditional density, with variance "
        "targeting: $\\omega$ is set to $s^2(1 - \\alpha - \\beta)$ for the sample variance "
        "$s^2$, and the likelihood is maximised over $(\\alpha, \\beta)$ on a grid refined "
        "twice. A grid rather than a gradient method because the surface is flat along "
        "$\\alpha + \\beta$ and a naive optimiser walks up to the stationarity boundary and "
        "stops there, which is the single most common way a GARCH fit goes wrong."
    ),
    "Validation Evidence": (
        "Fitted parameters against the generating process, the log-likelihood against a "
        "constant-variance model, and the forecast compared with the realised squared return. "
        "MAYA \\textbf{refuses to score a declared black box} and the desk scores it instead, which "
        "is a weaker claim than a blind one; case study 7 quantifies how much weaker, and the "
        "same reasoning applies here."
    ),
    "Known Weaknesses": (
        "Symmetric, so it misses the leverage effect. Gaussian, so it understates tail "
        "quantiles. Variance targeting makes $\\omega$ an artefact of the sample. And the "
        "persistence is high — $\\alpha + \\beta$ near one — which means the model is close to "
        "the boundary where its long-run variance stops existing: it is stationary, the "
        "constraint proves it, and it is not comfortably so."
    ),
    "Change Log": "Version 1: initial GARCH(1,1) conditional volatility.",
}


def document(title: str, sections: dict[str, str]) -> str:
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in sections.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        f"\\title{{{title}}}\\author{{Market risk analytics}}\n"
        f"\\begin{{document}}\\maketitle\n{body}\n\\end{{document}}\n"
    )


def feed(name: str) -> bytes:
    path = DATA / f"{name}.csv"
    if not path.exists():
        raise SystemExit(
            f"{path} is missing. Write it with:\n"
            f"  .venv/bin/python {Path(__file__).parent.name}/make_data.py"
        )
    return path.read_bytes()


class Cast:
    def __init__(self, maya: Any) -> None:
        self.dana = maya.client("dana")
        self.mick = maya.client("mick")
        self.mona = maya.client("mona")
        self.devi = maya.client("devi")
        self.mgr = maya.client("mgr")
        self.lara = maya.client("lara")
        self.admin = maya.client("admin")


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet — run get_training_warrants.py")


# ---------------------------------------------------------------------------------
# The fitting mathematics.
# ---------------------------------------------------------------------------------
def fit_ar2(lag1: np.ndarray, lag2: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """Least squares on the two lags, and the R-squared it achieves."""
    design = np.column_stack([np.ones(len(y)), lag1, lag2])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ beta
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return beta, 1.0 - ss_res / ss_tot


def garch_loglik(
    shock: np.ndarray, alpha: np.ndarray, beta: np.ndarray, sample: float | None = None
) -> np.ndarray:
    """Gaussian quasi-log-likelihood for every (alpha, beta) pair at once.

    The recursion is sequential in time and independent across pairs, so it vectorises across
    the grid: one pass over the series, updating a vector of variances. Written this way it is
    a few hundredths of a second instead of minutes.

    Variance targeting pins omega to the sample variance and the persistence, which is what
    makes the surface a function of two parameters rather than three."""
    sample = float(np.var(shock)) if sample is None else sample
    omega = sample * (1.0 - alpha - beta)
    variance = np.full(alpha.shape, sample)
    total = np.zeros(alpha.shape)
    squared = shock**2
    for t in range(len(shock)):
        total -= 0.5 * (np.log(variance) + squared[t] / variance)
        variance = omega + alpha * squared[t] + beta * variance
    return total


def fit_garch(shock: np.ndarray | list[np.ndarray]) -> tuple[dict[str, float], float]:
    """Grid, then refine twice. Returns the parameters and the log-likelihood.

    A grid rather than a gradient method on purpose: the likelihood is nearly flat along
    ``alpha + beta``, and an optimiser started carelessly walks up to the stationarity
    boundary and reports a persistence of one, which is the commonest way a GARCH fit goes
    wrong and the reason the constraint on this model exists.

    Given several series (one per index, all from one process) it maximises their summed
    likelihood with one parameter set, each series recursed on its own."""
    series = shock if isinstance(shock, list) else [shock]
    sample = float(np.var(np.concatenate(series)))
    lo_a, hi_a, lo_b, hi_b = 0.005, 0.30, 0.50, 0.99
    best = {"alpha": 0.1, "beta": 0.85}
    loglik = -np.inf
    for _ in range(3):
        a = np.linspace(lo_a, hi_a, 24)
        b = np.linspace(lo_b, hi_b, 24)
        grid_a, grid_b = np.meshgrid(a, b, indexing="ij")
        allowed = grid_a + grid_b < 0.9995
        flat_a, flat_b = grid_a[allowed], grid_b[allowed]
        ll = sum(garch_loglik(x, flat_a, flat_b, sample) for x in series)
        k = int(np.argmax(ll))
        best = {"alpha": float(flat_a[k]), "beta": float(flat_b[k])}
        loglik = float(ll[k])
        span_a, span_b = (hi_a - lo_a) / 6, (hi_b - lo_b) / 6
        lo_a, hi_a = max(0.001, best["alpha"] - span_a), min(0.6, best["alpha"] + span_a)
        lo_b, hi_b = max(0.2, best["beta"] - span_b), min(0.998, best["beta"] + span_b)
    omega = sample * (1.0 - best["alpha"] - best["beta"])
    return {"omega": float(omega), **best}, loglik


def constant_variance_loglik(shock: np.ndarray | list[np.ndarray]) -> float:
    """The likelihood of the model GARCH has to beat: one variance for the whole sample."""
    x = np.concatenate(shock) if isinstance(shock, list) else shock
    sample = float(np.var(x))
    return float(-0.5 * np.sum(np.log(sample) + x**2 / sample))


# A few rows for the artifact ladder's smoke run: two indices, interleaved as a panel is.
SAMPLE = {
    "ret": [0.004, -0.006, 0.011, -0.002, -0.013, 0.007],
    "index": ["AZX", "BQI", "AZX", "BQI", "AZX", "BQI"],
}
