"""
What the steps of this case study share: the objects' names, the three feed definitions, the
curve in LaTeX, the desk's two implementations of it, the specification document, the
calibration mathematics, and the people.

Nothing here talks to MAYA. It is the study's declarations — the things that would sit under
source control on a rates desk — in one place, so each step script reads as the step it is,
and so two steps cannot disagree about what the curve is called or what the model says.

It does import ``maya.formula.evaluate``, which is a library and not a client. The
calibrator must not contain a *second* Nelson–Siegel: the three columns of its linear
problem are read out of MAYA's own evaluation of the approved expression tree by
superposition (``design`` below), so the curve the calibration fits is the curve MAYA's
blind holdout score will reprice with, and a disagreement between the two is impossible
rather than merely unlikely.

Steps find each other's work by name: ``gbp_zero_curve``, ``gbp_curve_2606``,
``nelson_siegel_gbp_live``. A step run an hour later in a different process locates what
the last one made exactly the way a person or a scheduled job would — by asking MAYA.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np

NS = "rates"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("ois_par_quotes", "zero_yields", "curve_build")
AS_OF = dt.date(2026, 6, 30)
# A curve is knowable the evening it is built, so the pin is taken at seven the next
# morning and already holds everything. Compare case study 1, which had to wait a year.
KNOWN = dt.datetime(2026, 7, 1, 7, 0, tzinfo=dt.timezone.utc)
NEWLINE = b"\n"
CURRENCY = "GBP"

# The model, as the curve quant wrote it: Nelson–Siegel (1987) for a continuously
# compounded zero yield at maturity tau.
#
#   z          the maturity in units of the decay parameter
#   L_slope    the slope loading: 1 at the short end, falling to 0 at the long end
#   L_curve    the curvature loading: 0 at both ends, humped at tau = 1.79 lambda
#   y          the zero yield
#
# Writing the two loadings as their own lines is not decoration. They are what a reader of
# the specification has to recognise, they are the columns of the linear problem the
# calibration solves, and naming them is what lets the study ask MAYA for them rather than
# writing them out a second time.
FORMULA = r"""
z = \frac{\tau}{\lambda}
L_{slope} = \frac{1 - e^{-z}}{z}
L_{curve} = L_{slope} - e^{-z}
y = \beta_{0} + \beta_{1} L_{slope} + \beta_{2} L_{curve}
"""
FACTORS = ("beta0", "beta1", "beta2")
PARAMS = (*FACTORS, "lambda")
# Declared the way a quant writes them. MAYA normalises a subscripted Greek command the
# same way in the formula text and in the roles, so `\beta_{0}` is one symbol in both —
# and `\tau` has to be declared too, or LaTeX's own convention reads it as t times a times u.
ROLES = {
    "\\tau": "feature",
    "\\beta_{0}": "parameter",
    "\\beta_{1}": "parameter",
    "\\beta_{2}": "parameter",
    "\\lambda": "parameter",
}
# What each parameter may be, enforced by MAYA on every upload for the life of the version.
#
# beta0 is a long-run rate: not negative, not 25%. beta1 is a spread and may be either
# sign. beta2 is a curvature and may be large. lambda is where the hump sits: the bounds
# put it between 0.45 and 10.7 years, which covers every curve anybody quotes.
#
# What cannot be said here is the constraint that matters: beta0 + beta1 is the
# instantaneous short rate, and it should also be non-negative. That is a statement about
# two parameters at once, and MAYA's bounds are per parameter. Step 5 uploads a set that
# satisfies every bound in this table and implies a short rate of -6.7%.
BOUNDS = {
    "beta0": [0.0, 0.25],
    "beta1": [-0.25, 0.25],
    "beta2": [-0.5, 0.5],
    "lambda": [0.25, 6.0],
}

# The desk's implementation, written to MAYA's model interface (§8.3): a class named Model
# with fit(X, y, ctx) and predict(X, params, ctx). Its own variable names, its own order of
# operations. MAYA does not ask it to look like the formula; it asks whether it *computes*
# the formula, which is a different and much better question.
#
# fit() has nothing to learn and says so: the factors are calibrated under a warrant and
# arrive as an approved parameter set.
DESK_CODE = '''
"""GBP OIS zero curve, Nelson–Siegel. Rates desk implementation."""

import numpy as np


class Model:
    def fit(self, X, y, ctx):
        """Nothing is fitted here: the factors are calibrated under a warrant, then approved."""
        return {}

    def predict(self, X, params, ctx):
        maturity = np.asarray(X["tau"], dtype=float)
        decay_time = float(params["lambda"])
        scaled = maturity / decay_time
        decay = np.exp(-scaled)
        slope_loading = (1.0 - decay) / scaled
        curve_loading = slope_loading - decay
        return (
            params["beta0"]
            + params["beta1"] * slope_loading
            + params["beta2"] * curve_loading
        )
'''

# The same pricer with the commonest Nelson–Siegel mistake in it: the slope loading divided
# by the maturity instead of by the maturity over lambda. It is exactly right when
# lambda = 1 and wrong at every other lambda — and, because it rescales the loadings without
# leaving the space they span, a recalibration absorbs it completely. Step 4 and step 5
# between them show that the differential test is the only thing in the building that
# notices.
BUGGY_CODE = DESK_CODE.replace(
    "        slope_loading = (1.0 - decay) / scaled\n",
    "        slope_loading = (1.0 - decay) / maturity  # BUG: tau, not tau / lambda\n",
)

QUOTE_DEF = {
    "index": ["date", "tenor"],
    "index_types": {"date": "date", "tenor": "string"},
    "schema": [
        {"name": "parYield", "type": "float64"},
        {"name": "bidYield", "type": "float64"},
        {"name": "askYield", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "parYield"},
        {"check": "unique_on_index"},
        {"check": "range", "attr": "parYield", "min": -0.01, "max": 0.25},
    ],
}
ZERO_DEF = {
    "index": ["date", "tenor"],
    "index_types": {"date": "date", "tenor": "string"},
    "schema": [
        {"name": "tau", "type": "float64"},
        {"name": "zeroYield", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "zeroYield"},
        {"check": "unique_on_index"},
        {"check": "range", "attr": "zeroYield", "min": -0.01, "max": 0.25},
        # A tenor nobody publishes is a bad row rather than a long bond.
        {"check": "range", "attr": "tau", "min": 0.02, "max": 40.0},
        # Loose on purpose, and the looseness is the point: a relative limit on a
        # one-month rate of 1.4% is a blunt instrument, because a 25 basis point move is
        # 18% of it. It catches a decimal point, not a bad print.
        {"check": "max_daily_change", "attr": "zeroYield", "max": 0.40},
    ],
}
# The one method the curve team runs, stated once so the definition and the data cannot
# disagree about it.
METHOD = "log-linear DF bootstrap, OIS discounting"
BUILD_DEF = {
    "index": ["date"],
    "index_types": {"date": "date"},
    "schema": [
        {"name": "instruments", "type": "int64"},
        {"name": "maxResidualBp", "type": "float64"},
        {"name": "method", "type": "string"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "range", "attr": "instruments", "min": 18, "max": 30},
        # The only handle MAYA has on the quality of the bootstrap that produced this
        # study's target: a range check on the number the curve team reports about itself.
        {"check": "range", "attr": "maxResidualBp", "min": 0.0, "max": 1.5},
        {"check": "allowed_values", "attr": "method", "values": [METHOD]},
    ],
}
DEFINITIONS = {"ois_par_quotes": QUOTE_DEF, "zero_yields": ZERO_DEF, "curve_build": BUILD_DEF}

PANEL = "gbp_zero_curve"
PIN = "ns2606"
MODEL = "nelson_siegel"
WARRANT = "gbp_curve_2606"
LIVE = "nelson_siegel_gbp_live"
CURVE_FEATURE = "gbp_ns_curve"
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
MODEL_REF = f"{NS}/{MODEL}@v1"
CONTACT = "rates.curve.quant@example.com"
EXTRA_USERS = {"lara": ["model_manager"]}

# The curve, on the index the published pillars arrive on. The build report is per (date)
# and MAYA broadcasts it onto (date, tenor) rather than making anybody write a join. The
# model's notation and the curve team's column names meet here, which is the feature set's
# job: `tau` is the maturity in years, `y` is the published zero yield.
#
# `par` and `buildResidual` are members and not inputs of the model: the quoted par rate is
# what the curve was built from and the residual is how well that build went. Both belong
# beside the curve, and neither is something the model may see.
PANEL_DEF = {
    "index": ["date", "tenor"],
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/{feature}@v1", "source_attr": source}
        for attr, feature, source in (
            ("tau", "zero_yields", "tau"),
            ("y", "zero_yields", "zeroYield"),
            ("par", "ois_par_quotes", "parYield"),
            ("buildResidual", "curve_build", "maxResidualBp"),
        )
    ],
}

# The smoke run and the upload-time differential test need a value for every input the
# contract names, in the units of the problem: five points across the curve rather than
# five numbers near one.
SAMPLE = {"tau": [0.0833333, 0.5, 2.0, 10.0, 30.0]}

LEAKAGE_NOTE = (
    "Every row's inputs and target are published the same evening, so the certificate is "
    "expected to be clean. It is clean about time, and time is not what is wrong here: the "
    "target is itself the output of a bootstrap, and a curve fitted to it inherits every "
    "judgement in that build. No bitemporal rule can see that."
)

# The grid the non-linear parameter is searched on: 45 points, log-spaced, spanning the
# bounds the model declares. Log-spaced because lambda enters as tau/lambda, so what
# matters is its ratio to a maturity, not its distance from one.
LAMBDA_GRID = np.exp(np.linspace(np.log(BOUNDS["lambda"][0]), np.log(BOUNDS["lambda"][1]), 45))


# -- the calibration mathematics ----------------------------------------------------------
def rmse_bp(error: np.ndarray) -> float:
    """Root mean squared error in basis points, which is the unit a curve is argued in."""
    return float(1e4 * np.sqrt(np.nanmean(np.asarray(error, dtype=float) ** 2)))


def evaluate_curve(ir: dict[str, Any], tau: np.ndarray, values: dict[str, float]) -> np.ndarray:
    """MAYA's own evaluation of the approved expression tree. Not a second Nelson–Siegel."""
    from maya.formula.evaluate import evaluate

    return np.asarray(next(iter(evaluate(ir, {"tau": tau}, values).values())), dtype=float)


def design(ir: dict[str, Any], tau: np.ndarray, lam: float) -> np.ndarray:
    """The three columns of the linear problem, read out of the model by superposition.

    The curve is linear in beta0, beta1 and beta2, so evaluating the tree with one factor
    set to 1 and the others to 0 *is* that factor's loading. The calibrator therefore never
    writes the loadings down: it asks the approved mathematics for them, at the lambda in
    question, which is why it cannot drift from the specification.
    """
    zero = {name: 0.0 for name in FACTORS} | {"lambda": float(lam)}
    return np.column_stack(
        [evaluate_curve(ir, tau, {**zero, name: 1.0}) for name in FACTORS],
    )


def desk_design(ir: dict[str, Any], tau: np.ndarray, lam: float) -> np.ndarray:
    """The loadings the desk's *buggy* implementation uses, as algebra over MAYA's own.

    The wrong slope loading is the right one divided by lambda, and the wrong curvature
    loading is that divided loading minus the same exponential. Both are combinations of the
    three columns MAYA hands back — ``e^{-z}`` is the slope loading minus the curvature one —
    so the study can calibrate against the desk's mistake without containing a third
    implementation of Nelson–Siegel to be wrong in a fourth way.
    """
    right = design(ir, tau, lam)
    decay = right[:, 1] - right[:, 2]
    slope = right[:, 1] / float(lam)
    return np.column_stack([right[:, 0], slope, slope - decay])


def pooled_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """One curve for the whole window: ordinary least squares over every row at once."""
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return np.asarray(beta, dtype=float)


def daily_fit(x: np.ndarray, y: np.ndarray, day: np.ndarray, days: int) -> np.ndarray:
    """One curve per day, all of them at once: the normal equations, accumulated per day.

    Three by three per day, so the solve is exact and there is nothing to iterate. Done as
    a Python loop over five hundred days inside a grid of forty-five lambdas it would be
    twenty thousand tiny least-squares problems; done like this it is twelve bincounts.
    """
    gram = np.empty((days, 3, 3))
    moment = np.empty((days, 3))
    for i in range(3):
        moment[:, i] = np.bincount(day, x[:, i] * y, days)
        for j in range(3):
            gram[:, i, j] = np.bincount(day, x[:, i] * x[:, j], days)
    return np.linalg.solve(gram, moment[:, :, None])[:, :, 0]


def lambda_profile(
    ir: dict[str, Any], tau: np.ndarray, y: np.ndarray, day: np.ndarray, days: int
) -> tuple[np.ndarray, np.ndarray]:
    """The objective as a function of lambda, and each day's own best lambda.

    This is the honest shape of the calibration: for every lambda on the grid, refit the
    three linear factors *per day* — which is what a desk does every evening — and report
    the residual. What comes back is both the panel's profile and, day by day, where each
    day's minimum sits.
    """
    profile = np.empty(len(LAMBDA_GRID))
    per_day = np.empty((len(LAMBDA_GRID), days))
    for k, lam in enumerate(LAMBDA_GRID):
        x = design(ir, tau, lam)
        residual = (x * daily_fit(x, y, day, days)[day]).sum(axis=1) - y
        profile[k] = rmse_bp(residual)
        per_day[k] = np.bincount(day, residual**2, days)
    return profile, LAMBDA_GRID[per_day.argmin(axis=0)]


def curve_expression(values: dict[str, float]) -> str:
    """The same mathematics as a feature transform: the factors inlined as literals.

    This is the whole feature-or-model question in one string. MAYA's restricted expression
    language has arithmetic and ``exp``, which is everything Nelson–Siegel needs, so the
    curve can be a *derived feature* — and then the four numbers below are literals in a
    definition, with no bounds, no parameter set, no approval of their own and nothing to
    recalibrate against. Step 7 builds it and checks that it produces the same numbers as
    the governed model, to the last bit.
    """
    b0, b1, b2 = (float(values[name]) for name in FACTORS)
    z = f"(tau / {float(values['lambda']):.9g})"
    slope = f"((1 - exp(-{z})) / {z})"
    return (
        f"{b0:.9g}"
        f" {'-' if b1 < 0 else '+'} {abs(b1):.9g} * {slope}"
        f" {'-' if b2 < 0 else '+'} {abs(b2):.9g} * ({slope} - exp(-{z}))"
    )


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    """The training warrant this study drew, found the way anything finds it: by name."""
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet — run get_training_warrant.py")


def parameter_set(warrant: dict[str, Any], name: str) -> dict[str, Any]:
    for ps in warrant.get("parameter_sets", []):
        if ps["name"] == name and ps["state"] == "approved":
            return dict(ps)
    raise SystemExit(f"No approved parameter set '{name}' — run get_training_warrant.py")


SECTIONS = {
    "Purpose": (
        "Give the sterling rates desk a continuously compounded zero yield at any maturity "
        "between one month and thirty years, so that a cash flow falling between two "
        "published pillars can be discounted, a swap can be revalued off a smooth curve "
        "rather than off a polyline, and the front office and the risk engine use the same "
        "curve. The model interpolates and mildly extrapolates a curve that has already "
        "been built; it does not forecast rates and says nothing about where they go."
    ),
    "Scope and Limitations": (
        "GBP OIS zero yields, maturities from one month to thirty years, which is the span "
        "the published pillars cover. One parameter set is one curve: the three factors "
        "describe the shape of a single calibration window and are not a time series, so a "
        "parameter set approved for one window must not be used to reprice another. "
        "Nelson--Siegel has three factors and therefore at most one hump; a curve with two "
        "turning points, or with a kink at the point where the market thinks the policy "
        "path turns, is outside what this functional form can represent. The model is not "
        "arbitrage-free by construction: it fits yields, and nothing in it forbids an "
        "implied forward from going negative. Beyond thirty years it flattens towards "
        "$\\beta_0$, confidently and without evidence, which is why the execution warrant "
        "bounds the maturity rather than trusting the caller."
    ),
    "Mathematical Formulation": (
        "For a maturity $\\tau$ in years, with $z = \\tau / \\lambda$, the continuously "
        "compounded zero yield is "
        "$y(\\tau) = \\beta_0 + \\beta_1 \\frac{1 - e^{-z}}{z} + \\beta_2 "
        "\\left(\\frac{1 - e^{-z}}{z} - e^{-z}\\right)$. The two factor loadings are "
        "named in the expression tree: $L_{slope} = (1 - e^{-z})/z$ falls monotonically "
        "from 1 at the short end to 0 at the long end, and $L_{curve} = L_{slope} - e^{-z}$ "
        "is 0 at both ends and humped in between, with its maximum at $\\tau \\approx 1.79 "
        "\\lambda$. So $\\beta_0$ is the long rate, the limit of $y$ as $\\tau$ grows; "
        "$\\beta_0 + \\beta_1$ is the instantaneous short rate, the limit as $\\tau$ goes "
        "to zero; $\\beta_2$ scales the hump; and $\\lambda$ decides where that hump sits. "
        "The model is linear in the three $\\beta$ and non-linear in $\\lambda$ alone, "
        "which is what dictates how it is calibrated."
    ),
    "Assumptions": (
        "Five, stated rather than implied. First, that a zero yield exists at every "
        "maturity, which is an assumption about the market's completeness and not about "
        "the mathematics. Second, that the published pillar curve is the thing worth "
        "fitting: it is itself the output of a bootstrap with its own method and its own "
        "residual, so every judgement in that build is inherited here without appearing in "
        "this document. Third, that the curve has at most one hump, which is what three "
        "factors can express. Fourth, that $\\lambda$ is the same at every maturity and on "
        "every day of the calibration window — a modelling choice that makes the problem "
        "solvable and is not a fact about the market. Fifth, that the pillar errors are "
        "independent and of equal size, which unweighted least squares requires and which "
        "is false: the front of the curve is several times noisier than the long end, so "
        "the fit is pulled towards the noisy pillars. A weighted calibration is the obvious "
        "improvement and is not in this version."
    ),
    "Data and Features Used": (
        "Feature set rates/gbp_zero_curve, pinned point-in-time: the zero yield and its "
        "maturity for each benchmark tenor of the GBP OIS curve, the par rate the pillar "
        "was built from, and the curve team's own build report. The model's input contract "
        "names one attribute, $\\tau$; the published zero yield is the calibration target "
        "and is never an input, and the par quote and the build residual are members of the "
        "feature set rather than inputs of the model. Everything is knowable the evening of "
        "the trade date."
    ),
    "Calibration Methodology": (
        "Calibration, not estimation. The three factors are not observed and are not "
        "fitted to realised outcomes: they are chosen so that the curve reproduces zero "
        "yields the curve team has already published. The problem is nested, because the "
        "model is linear in $\\beta_0, \\beta_1, \\beta_2$ given $\\lambda$ and non-linear "
        "in $\\lambda$. So the honest method is a search over $\\lambda$ with ordinary "
        "least squares inside it: at each $\\lambda$ on a log-spaced grid across the "
        "declared bounds, the loadings are evaluated, the linear factors are solved exactly, "
        "and the residual is recorded; the reported objective is that residual as a "
        "function of $\\lambda$, so a reader can see for himself whether the minimum is "
        "sharp or flat. It is flat. Doubling $\\lambda$ from its best value costs a "
        "fraction of a basis point of fit, and the same grid run one day at a time puts the "
        "minimum anywhere between roughly 1.0 and 3.1 while the curve it was generated from "
        "used one value throughout. $\\lambda$ is therefore treated as a modelling "
        "constant to be approved once and revisited annually, not as a quantity to be "
        "compared across days, desks or vendors. Recalibration of the factors is daily in "
        "production: every recalibration is a new parameter set against a new warrant, "
        "approved, and never an edit of an existing one."
    ),
    "Validation Evidence": (
        "Four things, and the fourth is a warning. First, conformance: the desk's "
        "implementation is differentially tested against this specification over maturities "
        "resampled from the pinned curve, and a disagreement anywhere in the sampled domain "
        "fails the model version — which matters more here than usual, because the "
        "commonest error in this formula rescales the loadings without leaving the space "
        "they span, so a recalibration absorbs it exactly and no measure of fit, in sample "
        "or out, can see it. Second, the $\\lambda$ profile above, which is the evidence "
        "for the one parameter that is held constant. Third, the escrowed holdout: pillars "
        "withheld from the calibration and scored by MAYA in basis points, against a flat "
        "curve at the mean yield fitted on the same rows, which is the same model with its "
        "two shape factors set to zero. Fourth, the warning: a parameter set is one curve, "
        "and the holdout rows come from every day of the window, so the score measures how "
        "well a single curve describes two years of curves. It is the right number for the "
        "object MAYA licenses and it is not the number a desk cares about; the same model "
        "refit each evening, which is how it runs in production, fits several times better "
        "and cannot be one parameter set. Both numbers are in the case study."
    ),
    "Known Weaknesses": (
        "The first is structural, not statistical: the governed object is a single curve, "
        "and a curve is a thing that changes every evening. A parameter set that is right "
        "for one day is wrong for the next by roughly the amount the market moved, so "
        "either the model is recalibrated and re-approved daily — several hundred parameter "
        "sets a year, each needing a human approval nobody has time to give — or the "
        "approved set describes an average curve nobody trades on. Second, $\\lambda$ is "
        "barely identified: the objective is flat around its minimum, so the value in the "
        "approved parameter set should be read as a convention and never compared with "
        "another desk's. Third, the platform cannot express the constraint that matters "
        "most: $\\beta_0 > 0$ and $\\beta_0 + \\beta_1 > 0$ together say that both the long "
        "and the instantaneous rate are non-negative, the second is a statement about two "
        "parameters at once, and per-parameter bounds accept a set that satisfies each of "
        "them and implies a short rate of minus six per cent. Fourth, unweighted least "
        "squares over pillars whose noise differs by a factor of six pulls the fit towards "
        "the front of the curve. Fifth, three factors cannot reproduce a kinked curve: the "
        "residual at the two-year point is biased by a couple of basis points in the same "
        "direction every day, which is misspecification and not noise. Sixth, the target is "
        "itself a model output, and nothing in the platform records that the curve this "
        "model fits was built by another piece of mathematics with its own error."
    ),
    "Change Log": (
        "Version 1: Nelson--Siegel (1987) three-factor form for the GBP OIS zero curve, "
        "with $\\lambda$ as a fourth, non-linearly calibrated parameter, calibrated to the "
        "published pillar curve of 2024-07-01 to 2026-06-30. Svensson's fourth factor and "
        "second decay, a weighted objective, and any constraint spanning two parameters are "
        "deliberately out of this version; see the case study for why the third of those is "
        "not simply a matter of writing it down."
    ),
}


def specification() -> str:
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in SECTIONS.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        "\\title{The GBP OIS zero curve under Nelson--Siegel}"
        "\\author{Rates curve quant team and model risk}\n"
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
    """The people, each with their own roles and their own SDK client."""

    def __init__(self, maya: Any) -> None:
        self.dana = maya.client("dana")
        self.mick = maya.client("mick")
        self.mona = maya.client("mona")
        self.devi = maya.client("devi")
        self.mgr = maya.client("mgr")
        self.lara = maya.client("lara")
        self.admin = maya.client("admin")
