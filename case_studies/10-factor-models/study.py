"""
What the steps of this case study share: names, the two feature definitions, the two
panels, **both versions of the model**, a specification document for each, the fitting
mathematics and the people.

Nothing here talks to MAYA. Steps find each other's work by name — ``factor_panel``,
``capm_fit_2324``, ``ff5_fit_2324`` — because a step run an hour later in a different
process has to locate what the last one made the way a person or a scheduled job would.

The two formulas are the point of the study. They are the two simplest regressions in
finance, and they are deliberately simple: what is being demonstrated is not the
statistics but MAYA's **model versioning** — one model, two versions, a semantic diff
between them, a parameter set that belongs to one and cannot be lent to the other, and a
maturity ladder that takes the first one out of service without pretending the warrants
drawn on it never existed.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NS = "factor_models"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("equity_daily", "factor_daily")

PANEL = "factor_panel"  # the wide panel: the market factor and the four others
NARROW = "capm_panel"  # what version 1's contract was enough for
PIN = "y2023_24"
MODEL = "equity_factor_model"
WARRANT_V1 = "capm_fit_2324"
NAIVE_WARRANT = "capm_fit_naive"
WARRANT_V2 = "ff5_fit_2324"
CONTRACT_CHECK_V1 = "capm_contract_check"
LIVE_V1 = "capm_attribution"
LIVE_V2 = "ff5_attribution"

# The panel is pinned at the end of the window, and known from the first factor
# publication after it: the library that describes December is out on 4 January.
AS_OF = dt.date(2024, 12, 31)
KNOWN = dt.datetime(2025, 2, 1, tzinfo=dt.timezone.utc)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
NARROW_REF = f"maya://featureset/{NS}/{NARROW}@v1"
MODEL_V1 = f"{NS}/{MODEL}@v1"
MODEL_V2 = f"{NS}/{MODEL}@v2"
SUCCESSOR = f"maya://model/{NS}/{MODEL}@v2"
CONTACT = "equity.research.attribution@example.com"

# Both warrants are drawn with the same split and the same seed on the same pin, which is
# how they come to escrow the *same* holdout rows. MAYA assigns splits by hashing
# (seed, index key), so this is not a hope — the two warrants report the same holdout
# content hash, and the study prints both.
SEED = 7
SPLIT = {"train": 0.70, "validation": 0.15, "test": 0.15}

# A second model manager, because whoever submits an execution warrant may not approve it.
EXTRA_USERS = {"lara": ["model_manager"]}

# ---------------------------------------------------------------------------------
# Version 1: the simple linear regression. One slope, one intercept.
# ---------------------------------------------------------------------------------
FORMULA_V1 = "exRet = alpha + beta*mktExcess"
DRIVERS_V1 = ("mktExcess",)
WEIGHTS_V1 = ("alpha", "beta")

# Version 2: the multiple linear regression, on the same panel. Five slopes, one
# intercept, and the *same* symbol 'beta' on the market — which is what makes the semantic
# diff worth reading. A text diff would report a longer line. MAYA reports that the
# equation beta now sits in has four more terms in it, so beta's meaning has changed even
# though its name, type and bounds have not.
FORMULA_V2 = "exRet = alpha + beta*mktExcess + bSmb*smb + bHml*hml + bRmw*rmw + bCma*cma"
DRIVERS_V2 = ("mktExcess", "smb", "hml", "rmw", "cma")
WEIGHTS_V2 = ("alpha", "beta", "bSmb", "bHml", "bRmw", "bCma")

TARGET = "stockExcess"


def roles(weights: tuple[str, ...], drivers: tuple[str, ...]) -> dict[str, str]:
    """Every symbol declared, because a name MAYA has not been told about is read as a
    product of single letters — ``mktExcess`` would become nine features nobody has."""
    return {**{w: "parameter" for w in weights}, **{d: "feature" for d in drivers}}


ROLES_V1 = roles(WEIGHTS_V1, DRIVERS_V1)
ROLES_V2 = roles(WEIGHTS_V2, DRIVERS_V2)

# The universe's mean loadings, exactly as make_data.py sets them, so the fits can be
# compared against the process that generated the returns. A pooled regression over the
# whole panel estimates the equal-weighted universe's exposure, and make_data.py recentres
# the thirty drawn loadings so that mean is these numbers to the last decimal place.
# Every stock's true alpha is zero.
TRUE = {"alpha": 0.0, "beta": 1.00, "bSmb": 0.60, "bHml": 0.40, "bRmw": 0.05, "bCma": 0.00}
# The realised premia that turn the universe's tilt into a CAPM alpha are not stated here:
# step 1 measures them off the delivered file, which is the only place they should come from.
TRADING_DAYS = 252

# Why a factor model's own drivers are known after the returns they explain. This is a
# harder exception than case study 1's — there, the *target* was forward-looking and the
# drivers were all known at the observation date. Here the drivers themselves are
# published a month late, and the only honest defence is that the model is an attribution
# and never a forecast. That claim is enforced twice over: in the specification's scope,
# and in the execution warrant, which does not permit a production environment.
LEAKAGE_JUSTIFICATION = (
    "This is an attribution model, not a forecast, and both sides of the regression "
    "describe the same day. The factor library assembles a month's factor returns from "
    "the cross-section after that month has closed and publishes them on the fourth of "
    "the following month, so every row of this panel carries a knowledge time up to "
    "thirty-four days after its event date. The exception therefore covers the drivers "
    "as well as the target, which is only sound because the model's output is never used "
    "to take a position: it decomposes a return that has already happened. The execution "
    "warrant permits dev and uat only, the specification's Scope and Limitations section "
    "forbids forecasting use, and any use of this model to predict a return not yet "
    "realised would be leakage of exactly the kind this certificate exists to find."
)

# ---------------------------------------------------------------------------------
# Feature definitions. One is indexed on (date, stock) and one on date alone: a factor
# return is a property of the market, not of any stock, so it is stored once a day and
# MAYA broadcasts it across the cross-section on the index the two share (case study 3
# does the same with a mortgage rate). Every feed declares where its knowledge time comes
# from, and the two lags here are very different: a close is known that evening, a factor
# library a month later.
# ---------------------------------------------------------------------------------
EQUITY_DEF = {
    "index": ["date", "stock"],
    "index_types": {"date": "date", "stock": "string"},
    "schema": [
        {"name": "total_return", "type": "float64"},
        {"name": "excess_return", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "excess_return"},
        # A daily equity return outside ±50% is a corporate action nobody adjusted for,
        # not a return, and it would move a pooled slope on its own.
        {"check": "range", "attr": "excess_return", "min": -0.5, "max": 0.5},
        {"check": "range", "attr": "total_return", "min": -0.5, "max": 0.5},
    ],
}

FACTOR_DEF = {
    "index": ["date"],
    "index_types": {"date": "date"},
    "schema": [
        {"name": "mkt_rf", "type": "float64"},
        {"name": "smb", "type": "float64"},
        {"name": "hml", "type": "float64"},
        {"name": "rmw", "type": "float64"},
        {"name": "cma", "type": "float64"},
        {"name": "rf", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "mkt_rf"},
        {"check": "range", "attr": "mkt_rf", "min": -0.25, "max": 0.25},
        {"check": "range", "attr": "rf", "min": 0.0, "max": 0.01},
    ],
}

DEFINITIONS = {"equity_daily": EQUITY_DEF, "factor_daily": FACTOR_DEF}

# The panels. ``factor_panel`` carries all five factors and is what both versions are
# fitted on, so that the holdout is literally the same rows. ``capm_panel`` carries only
# what version 1 declared it needed — and is therefore what step 7 uses to show that a
# feature set which satisfied version 1's contract does not satisfy version 2's.
MEMBERS = {
    "stockExcess": ("equity_daily", "excess_return"),
    "mktExcess": ("factor_daily", "mkt_rf"),
    "smb": ("factor_daily", "smb"),
    "hml": ("factor_daily", "hml"),
    "rmw": ("factor_daily", "rmw"),
    "cma": ("factor_daily", "cma"),
}


def panel_def(attrs: tuple[str, ...]) -> dict[str, Any]:
    return {
        "index": ["date", "stock"],
        "members": [
            {
                "attr": attr,
                "ref": f"maya://feature/{NS}/{MEMBERS[attr][0]}@v1",
                "source_attr": MEMBERS[attr][1],
            }
            for attr in attrs
        ],
    }


PANEL_DEF = panel_def(("stockExcess", "mktExcess", "smb", "hml", "rmw", "cma"))
NARROW_DEF = panel_def(("stockExcess", "mktExcess"))

# ---------------------------------------------------------------------------------
# The specification documents. Two of them, because a model version's document is bound
# to that version's mathematics: MAYA marks a document for re-review the moment the
# formula IR moves under it, and refuses to submit the version until somebody has written
# the document again. Step 7 shows that refusal. What differs between these two is not
# decoration — it is the formulation, what the validation evidence can claim, and the
# weaknesses that version 2 fixes and the ones it does not.
# ---------------------------------------------------------------------------------
_SHARED = {
    "Purpose": (
        "Decompose the realised daily excess return of each stock in the research "
        "universe into the part explained by common factor exposures and the part that is "
        "not, for performance attribution and for the risk report the investment "
        "committee reads monthly."
    ),
    "Data and Features Used": (
        "Feature set factor\\_models/factor\\_panel, pinned point-in-time at 2024-12-31. "
        "The dependent variable is the stock's daily excess return over the risk-free "
        "rate, from the equity tape, whose knowledge time is the evening of the same day. "
        "The factors come from a published factor library indexed on date alone and "
        "broadcast across the cross-section: one row a day, not one row a stock-day. The "
        "library republishes each month's factors on the fourth day of the following "
        "month, so the drivers are known up to thirty-four days after the returns they "
        "explain. That is recorded as an exception on the training warrant's leakage "
        "certificate, with the reason, and it is the single most important thing to read "
        "before using this model for anything."
    ),
    "Calibration Methodology": (
        "Ordinary least squares on the pooled panel, over the training partition only, "
        "solved by the normal equations. The validation partition is used to confirm the "
        "fit did not overfit; the test partition is escrowed by MAYA and scored blind, "
        "and every attempt is counted on the warrant. Standard errors are reported twice: "
        "the classical ones, and ones clustered by date. The two differ because thirty "
        "stocks share one day's factor realisation, so the residuals of a given day are "
        "not independent, and a classical standard error on the intercept understates its "
        "uncertainty whenever the model omits a common factor. The gap between the two is "
        "itself a diagnostic and is reported as one."
    ),
    "Assumptions": (
        "That factor exposures are constant over the two-year window, which is why the "
        "window is two years and not ten. That the pooled specification is the right one: "
        "one intercept and one slope per factor for the whole universe, so what is "
        "estimated is the equal-weighted universe's exposure and not any single stock's. "
        "That the residuals are homoscedastic, which the classical standard errors assume "
        "and the clustered ones do not. And that the published factor library is itself "
        "correct; it is a vendor input and is not revalidated here."
    ),
}

SECTIONS_V1 = {
    **_SHARED,
    "Scope and Limitations": (
        "The thirty stocks of the domestic research universe, over the two-year window "
        "2023-01 to 2024-12, at daily frequency. The model is an attribution instrument "
        "and must not be used to forecast: its own drivers are published up to a month "
        "after the returns they explain, so a prediction made from it would use "
        "information nobody had. It is a single-factor model and attributes everything "
        "not explained by the market to alpha, which is the strongest of its limitations "
        "and is quantified in Known Weaknesses."
    ),
    "Mathematical Formulation": (
        "The single-index market model. For stock $i$ on day $t$, with $R^e_{it}$ the "
        "excess return over the risk-free rate and $M_t$ the market's excess return, "
        "$R^e_{it} = \\alpha + \\beta M_t + \\varepsilon_{it}$. The two coefficients are "
        "estimated by ordinary least squares on the pooled panel, so $\\beta$ is the "
        "equal-weighted universe's market exposure and $\\alpha$ is its average daily "
        "return in excess of what that exposure explains. Annualisation of $\\alpha$ at "
        "252 trading days is a presentation of the output, performed by the caller, and "
        "is not a second model."
    ),
    "Validation Evidence": (
        "Reported as the coefficient of determination on the training and validation "
        "partitions, the two coefficients with classical and date-clustered standard "
        "errors, and MAYA's blind root mean squared error on the escrowed test partition. "
        "The holdout figure is quoted against a benchmark that predicts zero excess "
        "return for every stock on every day, which is the only honest thing to compare a "
        "return model's error against: an error of one and a half per cent a day is "
        "meaningless until it is set beside the one and eight tenths per cent of a model "
        "that says nothing."
    ),
    "Known Weaknesses": (
        "One factor. Every exposure the universe has to size, value, profitability or "
        "investment is absorbed into $\\alpha$, and this universe is deliberately tilted "
        "small and value, so $\\alpha$ here is a measurement of the model's omissions "
        "rather than of skill. Reading it as skill is the error this model most invites. "
        "The market slope is affected too: an omitted factor correlated in sample with "
        "the market biases $\\beta$, and the study quantifies that bias against the "
        "generating process. There is no time variation in the exposures, no industry "
        "control, no currency dimension and no allowance for a stale factor publication."
    ),
    "Change Log": (
        "Version 1: initial single-factor market model, fitted on the 2023-01 to 2024-12 "
        "window under training warrant factor\\_models/capm\\_fit\\_2324."
    ),
}

SECTIONS_V2 = {
    **SECTIONS_V1,
    "Scope and Limitations": (
        "The thirty stocks of the domestic research universe, over the two-year window "
        "2023-01 to 2024-12, at daily frequency. The model is an attribution instrument "
        "and must not be used to forecast: its own drivers are published up to a month "
        "after the returns they explain. It attributes to five common factors and to "
        "nothing else; any exposure outside those five — industry, momentum, currency, "
        "liquidity — is still absorbed into $\\alpha$, and the fact that $\\alpha$ is now "
        "indistinguishable from zero on this universe is evidence about this universe and "
        "not a general claim."
    ),
    "Mathematical Formulation": (
        "The five-factor model. For stock $i$ on day $t$, "
        "$R^e_{it} = \\alpha + \\beta M_t + b_s \\mathrm{SMB}_t + b_h \\mathrm{HML}_t + "
        "b_r \\mathrm{RMW}_t + b_c \\mathrm{CMA}_t + \\varepsilon_{it}$, where the four "
        "additional factors are the published size, value, profitability and investment "
        "return series. The six coefficients are estimated by ordinary least squares on "
        "the pooled panel. The symbol $\\beta$ is carried over from version 1 and its "
        "interpretation is not: it is now the market exposure \\emph{holding the four other "
        "exposures fixed}, which is a different quantity that happens to have the same "
        "name. Version 1's estimate of it is not an estimate of this."
    ),
    "Validation Evidence": (
        "The same three instruments as version 1 — coefficients with classical and "
        "date-clustered standard errors, $R^2$ on training and validation, and MAYA's "
        "blind score on the escrowed test partition — and one more that matters more than "
        "any of them: the two versions are scored on the \\emph{same} escrowed rows, because "
        "both warrants were drawn on the same pin with the same split and the same seed "
        "and MAYA reports the same holdout content hash for both. The improvement is "
        "therefore measured on rows neither fit saw, and is a difference rather than an "
        "assertion. The intercept falling from significant to indistinguishable from zero "
        "is the substantive finding; the reduction in holdout error is smaller than that "
        "fall suggests, and the study says so."
    ),
    "Known Weaknesses": (
        "Five factors are not all factors. There is no momentum, no industry and no "
        "liquidity term, and the residual still carries whatever this universe is exposed "
        "to outside the five. The exposures are constant over the window. The "
        "profitability loading is not significantly different from zero on this universe, "
        "and the investment loading comes back significantly negative when the process "
        "that generated the data has no average investment tilt at all: with five "
        "coefficients and a five per cent test, about one such false positive is what "
        "should be expected, and a reviewer who reads it as a real exposure has been "
        "misled by arithmetic rather than by the model. Multicollinearity among the "
        "published factors is not diagnosed here. And the leakage exception version 1 "
        "carried is carried unchanged: this is still an attribution, never a forecast."
    ),
    "Change Log": (
        "Version 1: single-factor market model, fitted under training warrant "
        "factor\\_models/capm\\_fit\\_2324. Version 2: four further published factors "
        "added — size, value, profitability and investment — on the same pinned panel, "
        "fitted under factor\\_models/ff5\\_fit\\_2324. The input contract gains four "
        "attributes, so a feature set that satisfied version 1 need not satisfy version "
        "2, and version 1's parameter set is not a parameter set for version 2. Version 1 "
        "is deprecated with this version as its successor."
    ),
}


def specification(title: str, sections: dict[str, str]) -> str:
    """§8.3's nine sections, said properly. MAYA refuses to submit a version whose
    document is missing one, and refuses again if the formula moved after it was written."""
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in sections.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        f"\\title{{{title}}}\\author{{Equity research, model risk}}\n"
        f"\\begin{{document}}\\maketitle\n{body}\n\\end{{document}}\n"
    )


def spec_v1() -> str:
    return specification("Equity factor model, version 1: the market model", SECTIONS_V1)


def spec_v2() -> str:
    return specification("Equity factor model, version 2: five factors", SECTIONS_V2)


def feed(name: str) -> bytes:
    """One of the two delivered files, exactly as it sits on disk."""
    path = DATA / f"{name}.csv"
    if not path.exists():
        raise SystemExit(
            f"{path} is missing. Write it with:\n"
            f"  .venv/bin/python {Path(__file__).parent.name}/make_data.py"
        )
    return path.read_bytes()


class Cast:
    """The people in the story, each an SDK client logged in with their own roles."""

    def __init__(self, maya: Any) -> None:
        self.dana = maya.client("dana")  # feature designer: writes the definitions
        self.mick = maya.client("mick")  # feature manager: approves them, and pins
        self.mona = maya.client("mona")  # model designer: both versions and both documents
        self.devi = maya.client("devi")  # model developer: draws warrants and fits
        self.mgr = maya.client("mgr")  # model manager: approves models and parameters
        self.owen = maya.client("owen")  # model owner: accountable in production
        self.lara = maya.client("lara")  # a second model manager
        self.admin = maya.client("admin")


# ---------------------------------------------------------------------------------
# Lookups. Steps find each other's work by name through the SDK, never through a file.
# ---------------------------------------------------------------------------------
def version(client: Any, ref: str, version_no: int) -> dict[str, Any]:
    """One version of a model, by number. ``models.get`` returns them newest first."""
    for v in client.models.get(ref)["versions"]:
        if v["version_no"] == version_no:
            return dict(v)
    raise SystemExit(f"{ref} has no version {version_no} yet")


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet — run the step that draws it")


def find_execution_warrant(client: Any, name: str) -> dict[str, Any]:
    for row in client.execution.list():
        if row["name"] == name:
            return dict(client.execution.get(row["id"]))
    raise SystemExit(f"No execution warrant called '{name}' yet")


def approved_parameters(warrant: dict[str, Any]) -> dict[str, Any]:
    approved = [p for p in warrant.get("parameter_sets", []) if p["state"] == "approved"]
    if not approved:
        raise SystemExit(f"No approved parameter set on '{warrant['name']}' — fit it first")
    return dict(approved[0])


# ---------------------------------------------------------------------------------
# The fitting mathematics: ordinary least squares by the normal equations, classical and
# date-clustered standard errors, and R². In numpy, because scipy and sklearn are not
# installed and a two-hundred-line fit would not make the governance any clearer.
# ---------------------------------------------------------------------------------
def design_matrix(frame: pd.DataFrame, drivers: tuple[str, ...]) -> np.ndarray:
    """The intercept and the drivers, in the order the model declares its parameters."""
    return np.column_stack(
        [np.ones(len(frame))] + [frame[d].astype(float).to_numpy() for d in drivers]
    )


def fit_ols(X: np.ndarray, y: np.ndarray, clusters: Any) -> dict[str, Any]:
    """Coefficients, two sets of standard errors, R² and the residual standard deviation.

    The clustered standard errors are the reason this function is eight lines longer than
    ``lstsq``. Thirty stocks share one day's factor realisation, so the residuals within a
    day are correlated, and a classical standard error on the intercept understates its
    uncertainty by exactly as much as the model has omitted a common factor. Quoting both
    turns that understatement into a number a reviewer can read."""
    n, k = X.shape
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    resid = y - X @ beta
    rss = float(resid @ resid)
    classical = np.sqrt(np.diag(rss / (n - k) * xtx_inv))
    meat = np.zeros((k, k))
    for _, rows in pd.Series(np.arange(n)).groupby(np.asarray(clusters)):
        idx = rows.to_numpy()
        g = X[idx].T @ resid[idx]
        meat += np.outer(g, g)
    clustered = np.sqrt(np.diag(xtx_inv @ meat @ xtx_inv))
    centred = y - y.mean()
    return {
        "beta": beta,
        "se": classical,
        "se_clustered": clustered,
        "r2": float(1.0 - rss / float(centred @ centred)),
        "resid_sd": float(np.sqrt(rss / (n - k))),
        "n": n,
        "clusters": int(pd.Series(np.asarray(clusters)).nunique()),
    }


def r_squared(y: np.ndarray, pred: np.ndarray) -> float:
    """Out-of-sample R², for the validation partition the fit did not use."""
    resid = y - pred
    centred = y - y.mean()
    return float(1.0 - (resid @ resid) / float(centred @ centred))


def coefficient_table(
    names: tuple[str, ...], fit: dict[str, Any], truth: dict[str, float]
) -> list[str]:
    """One line per coefficient: the estimate, both standard errors, both t statistics,
    and what the process that generated the returns actually used."""
    out = ["name     estimate         se   clustered se      t   clustered t    generated"]
    for i, name in enumerate(names):
        b = float(fit["beta"][i])
        se, cl = float(fit["se"][i]), float(fit["se_clustered"][i])
        out.append(
            f"{name:<6} {b:+11.6f} {se:10.6f} {cl:14.6f} {b / se:+7.2f} "
            f"{b / cl:+13.2f} {truth[name]:+12.4f}"
        )
    return out
