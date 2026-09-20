"""
What the steps of this case study share: the objects' names, the four feed definitions, the
model in LaTeX, the desk's two implementations of it, the specification document, the
calibration mathematics, and the people.

Nothing here talks to MAYA. It is the study's declarations — the things that would sit
under source control on a derivatives desk — in one place, so each step script reads as the
step it is, and so two steps cannot disagree about what the chain is called or what the
model says.

It does import ``maya.formula.evaluate``, which is a library and not a client: the
calibrator must not contain a *second* Black–Scholes. It prices with MAYA's own evaluation
of the expression tree the SDK handed back, so the volatility it finds is the volatility
MAYA's blind holdout score will reprice with, and a disagreement between the calibrator and
the specification is impossible rather than merely unlikely.

Steps find each other's work by name: ``acme_chain``, ``acme_surface_2509``,
``bsm_call_acme_live``. A step run an hour later in a different process locates what the
last one made exactly the way a person or a scheduled job would — by asking MAYA.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any

import numpy as np

NS = "equity_derivatives"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("option_quotes", "underlying_spot", "dividend_forecast", "discount_curve")
AS_OF = dt.date(2025, 9, 30)
# The chain is knowable the evening it trades, so the pin is taken at six the next morning
# and already holds everything. Compare case study 1, which had to wait a year.
KNOWN = dt.datetime(2025, 10, 1, 6, 0, tzinfo=dt.timezone.utc)
NEWLINE = b"\n"
UNDERLYING = "ACME"

# The model, as the quant wrote it: Black–Scholes–Merton for a European call with a
# continuous dividend yield, over a volatility that is piecewise constant in nine buckets.
#
#   m         moneyness, strike over spot
#   volShort  the three volatilities of the short maturity band, selected by strike band
#   sigma     the surface: the maturity band first, then the strike band
#   d1, d2    the usual arguments
#   C         the call premium
#
# sigma_ij is the volatility of maturity band i and strike band j, and the *bands are part
# of the model*: their edges are in the governed expression tree, not in a calibration
# script, so a calibrator cannot quietly choose different ones. `bucket_masks` below asks
# the model which quotes each one prices rather than reading the numbers off this text.
FORMULA = r"""
m = \frac{K}{S}
volShort = where(m < 0.95, sigma11, where(m > 1.05, sigma13, sigma12))
volMid = where(m < 0.95, sigma21, where(m > 1.05, sigma23, sigma22))
volLong = where(m < 0.95, sigma31, where(m > 1.05, sigma33, sigma32))
\sigma = where(T < 0.25, volShort, where(T < 0.75, volMid, volLong))
d_1 = \frac{\ln(S/K) + (r - q + \sigma^2/2) T}{\sigma \sqrt{T}}
d_2 = d_1 - \sigma \sqrt{T}
C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)
"""
SIGMAS = tuple(f"sigma{i}{j}" for i in (1, 2, 3) for j in (1, 2, 3))
BANDS = {1: "K/S < 0.95", 2: "at the money", 3: "K/S > 1.05"}
MATURITIES = {1: "T < 0.25 (1M)", 2: "0.25 <= T < 0.75 (3M, 6M)", 3: "T >= 0.75 (1Y)"}
ROLES = {
    **{name: "feature" for name in ("S", "K", "r", "q", "T")},
    **{name: "parameter" for name in SIGMAS},
}
# A volatility is a positive number and it is not 400%. Both ends are enforced by MAYA on
# every parameter upload, so an optimiser that wandered cannot be signed for.
VOL_BOUNDS = [0.01, 3.0]

# The desk's implementation, written to MAYA's model interface (§8.3): a class named Model
# with fit(X, y, ctx) and predict(X, params, ctx). Its own variable names, its own selection
# of the bucket, its own order of operations. MAYA does not ask it to look like the formula;
# it asks whether it *computes* the formula, which is a different and much better question.
#
# fit() has nothing to learn and says so: a pricing model is calibrated to quotes, not
# fitted to outcomes, and the calibration arrives as an approved parameter set.
DESK_CODE = '''
"""European call, Black–Scholes–Merton on a bucketed volatility surface. Desk pricer."""

import math

import numpy as np

_erfc = np.vectorize(math.erfc, otypes=[float])
ATM_LOW, ATM_HIGH = 0.95, 1.05
SHORT, LONG = 0.25, 0.75


def _ncdf(x):
    return 0.5 * _erfc(-np.asarray(x, dtype=float) / math.sqrt(2.0))


class Model:
    def fit(self, X, y, ctx):
        """Nothing is fitted: the surface is calibrated to quotes and approved as parameters."""
        return {}

    def _surface(self, moneyness, tte, params):
        band = np.where(moneyness < ATM_LOW, 1, np.where(moneyness > ATM_HIGH, 3, 2))
        maturity = np.where(tte < SHORT, 1, np.where(tte < LONG, 2, 3))
        vol = np.zeros(np.broadcast(moneyness, tte).shape, dtype=float)
        for i in (1, 2, 3):
            for j in (1, 2, 3):
                vol = np.where((maturity == i) & (band == j), params[f"sigma{i}{j}"], vol)
        return vol

    def predict(self, X, params, ctx):
        spot = np.asarray(X["S"], dtype=float)
        strike = np.asarray(X["K"], dtype=float)
        rate = np.asarray(X["r"], dtype=float)
        yield_ = np.asarray(X["q"], dtype=float)
        tte = np.asarray(X["T"], dtype=float)
        vol = self._surface(strike / spot, tte, params)
        root = vol * np.sqrt(tte)
        d1 = (np.log(spot / strike) + (rate - yield_ + 0.5 * vol * vol) * tte) / root
        d2 = d1 - root
        return spot * np.exp(-yield_ * tte) * _ncdf(d1) - strike * np.exp(-rate * tte) * _ncdf(d2)
'''

# The same pricer with one character's worth of mistake: sigma*T where the mathematics says
# sigma*sqrt(T). It is exactly right at one year and wrong at every other maturity, so a
# unit test written on the 1Y pillar — the pillar a desk quotes first — passes.
BUGGY_CODE = DESK_CODE.replace(
    "        d2 = d1 - root\n",
    "        d2 = d1 - vol * tte  # BUG: sigma*T, not sigma*sqrt(T)\n",
)

QUOTE_DEF = {
    "index": ["date", "underlying", "tenor", "contract"],
    "index_types": {
        "date": "date",
        "underlying": "string",
        "tenor": "string",
        "contract": "string",
    },
    "schema": [
        {"name": "strike", "type": "float64"},
        {"name": "tte", "type": "float64"},
        {"name": "mid", "type": "float64"},
        {"name": "moneyness", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "mid"},
        {"check": "unique_on_index"},
        # A quote on a tenor nobody quotes, or a price below a penny, is a bad row rather
        # than a cheap option.
        {"check": "range", "attr": "tte", "min": 0.02, "max": 1.5},
        {"check": "range", "attr": "mid", "min": 0.01, "max": 100_000.0},
    ],
}
SPOT_DEF = {
    "index": ["date", "underlying"],
    "index_types": {"date": "date", "underlying": "string"},
    "schema": [{"name": "spot", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "spot"},
        {"check": "range", "attr": "spot", "min": 0.01, "max": 100_000.0},
    ],
}
DIVIDEND_DEF = {
    "index": ["date", "underlying"],
    "index_types": {"date": "date", "underlying": "string"},
    "schema": [{"name": "divYield", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "range", "attr": "divYield", "min": 0.0, "max": 0.15}],
}
CURVE_DEF = {
    "index": ["date", "tenor"],
    "index_types": {"date": "date", "tenor": "string"},
    "schema": [{"name": "rate", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "range", "attr": "rate", "min": -0.01, "max": 0.25}],
}
DEFINITIONS = {
    "option_quotes": QUOTE_DEF,
    "underlying_spot": SPOT_DEF,
    "dividend_forecast": DIVIDEND_DEF,
    "discount_curve": CURVE_DEF,
}

PANEL = "acme_chain"
PILLAR = "acme_1y"
PIN = "surf2509"
MODEL = "bsm_call"
WARRANT = "acme_surface_2509"
LIVE = "bsm_call_acme_live"
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
PILLAR_REF = f"maya://featureset/{NS}/{PILLAR}@v1"
MODEL_REF = f"{NS}/{MODEL}@v1"
CONTACT = "equity.derivatives.quant@example.com"
EXTRA_USERS = {"lara": ["model_manager"]}

# The chain, on the index the quotes arrive on. Three of the four members carry a coarser
# index than the set — spot and the dividend forecast are per (date, underlying), the curve
# is per (date, tenor) — and MAYA broadcasts each onto the chain rather than making anybody
# write a join. The model's notation and the vendors' column names meet here, which is the
# feature set's job: `S` is the spot feed's `spot`, `q` is the forecast's `divYield`.
#
# A volatility surface belongs to one underlying, so the set is filtered to ACME. The other
# three names are in the features and would each get their own chain, warrant and calibration.
PANEL_DEF = {
    "index": ["date", "underlying", "tenor", "contract"],
    "filters": {"universe": {"attr": "underlying", "values": [UNDERLYING]}},
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/{feature}@v1", "source_attr": source}
        for attr, feature, source in (
            ("S", "underlying_spot", "spot"),
            ("K", "option_quotes", "strike"),
            ("T", "option_quotes", "tte"),
            ("r", "discount_curve", "rate"),
            ("q", "dividend_forecast", "divYield"),
            ("mid", "option_quotes", "mid"),
            ("moneyness", "option_quotes", "moneyness"),
        )
    ],
}

# The 1Y pillar: the same chain, restricted, written as set algebra (§6.8) rather than as a
# second definition to keep in step. It exists to be a *test domain*: the maturity bug step
# 4 plants is invisible at one year, and the only honest way to show that is to run the
# comparison there and watch it pass.
PILLAR_DEF = {
    "derivation": {
        "operator": "override",
        "operands": [f"maya://featureset/{NS}/{PANEL}@v1"],
        "options": {
            "filters": {
                "universe": {"attr": "underlying", "values": [UNDERLYING]},
                "where": "T > 0.9",
            }
        },
    }
}

# The smoke run and the upload-time differential test need a value for every input the
# contract names, in the units of the problem: one at-the-money 1M call and one 1Y wing.
SAMPLE = {
    "S": [100.0, 100.0],
    "K": [100.0, 120.0],
    "r": [0.0425, 0.0475],
    "q": [0.021, 0.021],
    "T": [0.08333333, 1.0],
}

LEAKAGE_NOTE = (
    "Nothing in this panel is a forecast. Every input and the target are published the "
    "evening of the trade date, so the certificate is expected to be clean — and a clean "
    "certificate here says less than it does elsewhere, because the target is a price the "
    "market had already quoted."
)


# -- the calibration mathematics ----------------------------------------------------------
def columns(frame: Any) -> dict[str, np.ndarray]:
    """The five inputs the model's contract names, as float arrays."""
    return {name: frame[name].astype(float).to_numpy() for name in ("S", "K", "r", "q", "T")}


def price(ir: dict[str, Any], cols: dict[str, np.ndarray], vols: dict[str, float]) -> np.ndarray:
    """MAYA's own evaluation of the approved expression tree. Not a second Black–Scholes."""
    from maya.formula.evaluate import evaluate

    return np.asarray(next(iter(evaluate(ir, cols, vols).values())), dtype=float)


def flat(value: float) -> dict[str, float]:
    """One volatility in all nine buckets — a flat surface, which is what BSM assumes."""
    return {name: float(value) for name in SIGMAS}


def bucket_masks(ir: dict[str, Any], cols: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Which quotes each bucket's volatility prices — asked of the model, not of the analyst.

    Perturb one sigma and see which rows move. The bucket edges are in the expression tree,
    so this cannot drift from them, and a quote no bucket claims would show up as a gap
    rather than being silently swept into a neighbour.
    """
    base = price(ir, cols, flat(0.2))
    out = {}
    for name in SIGMAS:
        moved = price(ir, cols, {**flat(0.2), name: 0.3})
        out[name] = (moved != base) & ~(np.isnan(moved) & np.isnan(base))
    return out


def golden(objective: Any, lo: float, hi: float, iterations: int = 90) -> float:
    """Golden-section minimisation of a one-dimensional objective. No dependencies."""
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = objective(c), objective(d)
    for _ in range(iterations):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = objective(c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = objective(d)
    return (a + b) / 2.0


def calibrate(
    ir: dict[str, Any], cols: dict[str, np.ndarray], mid: np.ndarray, mask: np.ndarray
) -> dict[str, float]:
    """The volatility that best reprices ``mask``'s quotes, and how well it does.

    Least squares in price, which is what a desk minimises when it marks a surface: the
    objective is the sum of squared differences between the model's premium and the quoted
    mid, over the quotes in one bucket.
    """
    here = {k: v[mask] for k, v in cols.items()}
    target = mid[mask]

    def sse(vol: float) -> float:
        return float(np.nansum((price(ir, here, flat(vol)) - target) ** 2))

    vol = golden(sse, VOL_BOUNDS[0], 1.5)
    residual = price(ir, here, flat(vol)) - target
    return {
        "sigma": round(vol, 6),
        "quotes": int(mask.sum()),
        "rmse": float(np.sqrt(np.nanmean(residual**2))),
        "mae": float(np.nanmean(np.abs(residual))),
    }


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
        "Price European calls on ACME for the equity derivatives desk: to mark the book "
        "daily, to interpolate a premium for a strike or maturity nobody quoted, and to "
        "produce the risk the desk hedges on. It is the pricing leg of the desk's "
        "mark-to-model process, not a view on where volatility is going."
    ),
    "Scope and Limitations": (
        "European calls on a single underlying, with a continuous dividend yield, at "
        "maturities between one month and one year and strikes within roughly 20 per cent "
        "of spot — the region the calibrating quotes cover. American exercise, discrete "
        "dividends, barriers, anything on another underlying and anything beyond one year "
        "are out of scope: outside the calibrated region the model extrapolates a "
        "piecewise-constant surface, which is why the execution warrant bounds the time to "
        "expiry rather than trusting the caller. The model prices; it does not forecast. "
        "Nothing here says what the premium will be tomorrow."
    ),
    "Mathematical Formulation": (
        "With spot $S$, strike $K$, continuously compounded rate $r$, continuous dividend "
        "yield $q$ and time to expiry $T$, the premium of a European call is "
        "$C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)$ with "
        "$d_1 = (\\ln(S/K) + (r - q + \\sigma^2/2)T) / (\\sigma\\sqrt{T})$ and "
        "$d_2 = d_1 - \\sigma\\sqrt{T}$. The volatility $\\sigma$ is piecewise constant in "
        "nine buckets: three maturity bands ($T < 0.25$, $0.25 \\le T < 0.75$, "
        "$T \\ge 0.75$) crossed with three strike bands ($K/S < 0.95$, at the money, "
        "$K/S > 1.05$), giving $\\sigma_{ij}$ for maturity band $i$ and strike band $j$. "
        "The band edges are part of the model and are held in the expression tree."
    ),
    "Assumptions": (
        "The Black–Scholes assumptions, stated rather than implied: the underlying follows "
        "a geometric Brownian motion with constant volatility within each bucket, the "
        "dividend yield is continuous and known, the rate is the continuously compounded "
        "rate for the option's own maturity, there are no transaction costs and no early "
        "exercise. Two of those are false and matter. Volatility is not constant across "
        "strike — that is why there are nine buckets rather than one — and it is not "
        "constant within a bucket either, which is the residual measured below. The quoted "
        "mid is assumed to be a fair two-way price, so a stale or one-sided quote enters "
        "the calibration as if it were information."
    ),
    "Data and Features Used": (
        "Feature set equity_derivatives/acme_chain, pinned point-in-time: the closing mid "
        "of every listed ACME call on four tenors and a fixed strike ladder, with the "
        "official close of the underlying, the research desk's continuous dividend yield "
        "and the risk-free rate for each tenor. All four feeds are knowable the evening of "
        "the trade date. The quoted mid is the calibration target and is never an input; "
        "the model's input contract names S, K, T, q and r only."
    ),
    "Calibration Methodology": (
        "Calibration, not estimation, and the distinction is the point. The volatility is "
        "not observed and is not fitted to realised outcomes: each $\\sigma_{ij}$ is chosen "
        "to minimise the sum of squared differences between the model's premium and the "
        "quoted mid, over the quotes of that bucket in the training partition of the "
        "warrant's data. So the parameter is a restatement of today's market prices in the "
        "model's own units, and the model's job afterwards is to interpolate between them. "
        "It follows that the calibration says nothing about whether the model predicts "
        "anything, and that a holdout drawn from the same day's chain measures "
        "interpolation, not forecasting. Recalibration is daily in production; every "
        "recalibration is a new parameter set against a new warrant, approved, and never "
        "an edit of an existing one."
    ),
    "Validation Evidence": (
        "Three things, none of which is an accuracy claim about the future. First, "
        "conformance: the desk's pricer is differentially tested against this "
        "specification over quotes resampled from the pinned chain, and a disagreement "
        "anywhere in the sampled domain fails the model version. Second, the calibration "
        "residual per bucket, in pence per contract, which is how far the best "
        "piecewise-constant surface is from the quotes it was fitted to. Third, the "
        "escrowed holdout: quotes withheld from the calibration and scored by MAYA, which "
        "measures whether the surface reprices contracts it was not shown on the same "
        "dates. A flat surface — one volatility in all nine buckets — is scored on the same "
        "holdout for comparison, and the gap between the two is the evidence for the nine."
    ),
    "Known Weaknesses": (
        "A Black–Scholes model with one volatility cannot price this market, and the "
        "evidence is in this document: on the escrowed holdout the best single volatility "
        "misprices the chain about twice as badly as the nine-bucket surface, and its error "
        "is not noise but a pattern — it is around seventy pence a contract too cheap on "
        "the long-dated low-strike wing, where the market charges the most volatility, "
        "while overpaying the shorter-dated at-the-money and high-strike contracts. Nine "
        "buckets are an improvement and still an approximation: the surface is a step "
        "function where the market is smooth, so a quote that crosses a band edge as spot "
        "moves changes volatility discontinuously, and the surface's own residual is worst "
        "in the widest and most expensive bucket, one year and $K/S < 0.95$. The model has "
        "no term structure and no skew \\emph{within} a band. It is calibrated to mids and "
        "therefore inherits every stale quote in the chain. Outside the calibrated maturity "
        "and strike region it extrapolates flat, which is why that region is bounded by "
        "covenant. Nothing in the calibration constitutes evidence of predictive power, "
        "because the target was already public."
    ),
    "Change Log": (
        "Version 1: European call under Black–Scholes–Merton with a continuous dividend "
        "yield and a nine-bucket piecewise-constant volatility surface, calibrated to the "
        "ACME chain of 2025-04-01 to 2025-09-30. Delta and vega are deliberately not part "
        "of this version; see the case study's README for why they would be separate "
        "governed objects."
    ),
}


def specification() -> str:
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in SECTIONS.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        "\\title{European call on ACME under Black--Scholes--Merton}"
        "\\author{Equity derivatives quant team and model risk}\n"
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
