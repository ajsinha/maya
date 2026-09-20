"""
What the steps of this case study share: names, feature definitions, the hazard model,
its specification document, the proposed change, and the people.

Nothing here talks to MAYA. Steps find each other's work by name — ``prepay_panel``,
``smm_fit_2025``, ``prepay_live`` — because a step run later in a different process has
to locate what the last one made the way a person or a scheduled job would.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NS = "mortgage_prepay"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("loan_month", "mortgage_rate", "seasonality", "prepaid")
NEWLINE = b"\n"

PANEL = "prepay_panel"
PIN = "fit2512"
MODEL = "smm_hazard"
WARRANT = "smm_fit_2025"
LIVE = "prepay_live"
WORKSPACE = "smoother-rate-2026q1"

AS_OF = dt.date(2025, 12, 31)
KNOWN = dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
MODEL_REF = f"{NS}/{MODEL}@v1"
CONTACT = "mortgage.analytics@example.com"
EXTRA_USERS = {"lara": ["model_manager"]}

# The hazard. Every symbol is declared, and the two scalings are part of the model rather
# than of the fitting script: incentive in percentage points and seasoning in years, so a
# coefficient reads as "per point of incentive" and "per year on book" and the design
# matrix is not a mix of 0.02 and 180.
FORMULA = """
inc = 100 * (wac - mktRate)
s = min(age, 36) / 12
eq = 1 - ltv
z = a0 + aInc*inc + aAge*s + aEq*eq + aSum*movingSeason
smm = 1 / (1 + exp(-z))
"""
WEIGHTS = ("a0", "aInc", "aAge", "aEq", "aSum")
DRIVERS = ("wac", "mktRate", "age", "ltv", "movingSeason")
TARGET = "prepaid"
ROLES = {**{w: "parameter" for w in WEIGHTS}, **{d: "feature" for d in DRIVERS}}

# What this model calls a material shift, declared on the model rather than left to a
# platform default. Only the model knows what its output is: a shift of ten basis points of
# *monthly* hazard is about 1.2 percentage points of annualised CPR, which is the
# granularity at which the ALM committee's hedge ratios actually change. A default of one
# basis point would report every rounding difference as material and teach a reviewer to
# ignore the report.
MATERIALITY = 0.001
MATERIALITY_WHY = (
    "0.001 of monthly hazard, which is about 1.2 percentage points of annualised CPR: the "
    "granularity at which the hedge ratio changes."
)

# The recipe that generated the book (make_data.py), so the fit can be compared against it.
TRUE = {"a0": -6.10, "aInc": 0.62, "aAge": 0.34, "aEq": 1.45, "aSum": 0.38}

TARGET_JUSTIFICATION = (
    "The target 'prepaid' says whether the loan paid off in full during the observation "
    "month, and it is known when the next remittance settles a month later, so its "
    "knowledge time is later than its event date by construction. It is never an input: "
    "the model's contract names the coupon, the market rate, the age, the loan-to-value "
    "and the moving-season flag, all of which are known within two business days of month "
    "end. The exception covers the target column alone."
)

# ---------------------------------------------------------------------------------
# Feature definitions. Two are indexed on (date, loan) and two on date alone, because
# the mortgage rate and the calendar are not properties of any loan. MAYA joins them onto
# the panel on the index they share, which is the honest way to carry a market variable:
# putting one number a month into every loan's row would be a copy, and a copy can be
# wrong in one row and right in the next.
# ---------------------------------------------------------------------------------
TAPE_DEF = {
    "index": ["date", "loan"],
    "index_types": {"date": "date", "loan": "string"},
    "schema": [
        {"name": "wac", "type": "float64"},
        {"name": "age", "type": "int64"},
        {"name": "ltv", "type": "float64"},
        {"name": "balance", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "wac"},
        {"check": "range", "attr": "wac", "min": 0.0, "max": 0.25},
        {"check": "range", "attr": "ltv", "min": 0.0, "max": 1.5},
    ],
}

RATE_DEF = {
    "index": ["date"],
    "index_types": {"date": "date"},
    "schema": [{"name": "mkt_rate", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "range", "attr": "mkt_rate", "min": 0.0, "max": 0.25}],
}

SEASON_DEF = {
    "index": ["date"],
    "index_types": {"date": "date"},
    "schema": [{"name": "moving_season", "type": "int64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "moving_season"}],
}

OUTCOME_DEF = {
    "index": ["date", "loan"],
    "index_types": {"date": "date", "loan": "string"},
    "schema": [{"name": "prepaid", "type": "int64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "prepaid"}],
}

DEFINITIONS = {
    "loan_month": TAPE_DEF,
    "mortgage_rate": RATE_DEF,
    "seasonality": SEASON_DEF,
    "prepaid": OUTCOME_DEF,
}

PANEL_DEF = {
    "index": ["date", "loan"],
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/{feature}@v1", "source_attr": source}
        for attr, feature, source in (
            ("wac", "loan_month", "wac"),
            ("age", "loan_month", "age"),
            ("ltv", "loan_month", "ltv"),
            ("mktRate", "mortgage_rate", "mkt_rate"),
            ("movingSeason", "seasonality", "moving_season"),
            ("prepaid", "prepaid", "prepaid"),
        )
    ],
}

# The change the desk proposes, staged on a workspace in step 7. The survey rate is
# noisy month to month, and the argument for smoothing it is a reasonable one. It is also
# a change to a number that sits inside an approved, live model's incentive term, which is
# exactly the situation shadow replay exists for: the question is not whether smoothing is
# defensible in the abstract but how far it moves this book's forecast.
SMOOTHED_RATE_DEF = {
    **RATE_DEF,
    "transform": [
        {"op": "window", "attr": "mkt_rate", "fn": "mean", "size": 3, "name": "mkt_rate"}
    ],
}
CHANGE_NOTE = (
    "The published survey rate moves several basis points a month on nothing, and the "
    "incentive term inherits that noise. A three-month trailing mean is the desk's "
    "standard smoothing elsewhere. Proposed for the 2026 Q1 refresh."
)

SECTIONS = {
    "Purpose": (
        "Estimate the probability that a fixed-rate mortgage pays off in full in a given "
        "month — the single monthly mortality, from which the annualised constant "
        "prepayment rate follows — for valuation, hedging and the projection of pool "
        "cashflows."
    ),
    "Scope and Limitations": (
        "Fixed-rate, fully amortising first-lien mortgages in the domestic book, at least "
        "one month seasoned. It models \\emph{voluntary} prepayment: a loan that leaves the pool "
        "through default and liquidation is not the same event and is not in scope. There "
        "is no state-level, servicer-level or credit-score dimension, so it cannot answer "
        "a question about regional dispersion. It is a monthly hazard, not a term structure "
        "of prepayment: projecting it forward requires re-evaluating the incentive at each "
        "future month against a rate path, which is the caller's choice and not the model's."
    ),
    "Mathematical Formulation": (
        "A logistic hazard on four drivers. With coupon $c$, market rate $r$, age $a$ "
        "months and loan-to-value $\\ell$, let the incentive be $I = 100(c - r)$ in "
        "percentage points, the seasoning $S = \\min(a, 36)/12$ in years, and the equity "
        "$E = 1 - \\ell$. Then $z = \\alpha_0 + \\alpha_I I + \\alpha_S S + \\alpha_E E + "
        "\\alpha_M M$ for the moving-season indicator $M$, and the monthly hazard is "
        "$\\mathrm{SMM} = (1 + e^{-z})^{-1}$. The annualised rate is "
        "$\\mathrm{CPR} = 1 - (1 - \\mathrm{SMM})^{12}$, computed by the caller: it is a "
        "presentation of this model's output, not a second model. The seasoning ramp is "
        "capped at thirty-six months because the data cannot distinguish a ramp from a "
        "level beyond that, and the two scalings are stated here so a coefficient reads as "
        '"per percentage point of incentive" and "per year on book".'
    ),
    "Assumptions": (
        "That the published survey rate is a fair proxy for the rate the borrower could "
        "actually refinance into — it is not, for a borrower with impaired credit, and the "
        "model has no way to tell. That loan-to-value tracks refinanceability, which fails "
        "where a second lien exists. That the hazard is conditionally independent across "
        "loans given the drivers, which understates the variance of a pool-level forecast "
        "in a refinancing wave, when servicer capacity and media attention make prepayments "
        "correlated. And that the relationship between incentive and hazard is stable: it "
        "is estimated over one down-and-up rate cycle and no more."
    ),
    "Data and Features Used": (
        "Feature set mortgage_prepay/prepay_panel, pinned point-in-time. Loan-level: "
        "coupon, age and loan-to-value from the monthly tape, cut two business days after "
        "month end. Date-level, joined on the shared index: the thirty-year survey rate, "
        "published the first business day after the month it describes, and a moving-season "
        "indicator. The target is the full-payoff flag, known a month later when the "
        "remittance settles."
    ),
    "Calibration Methodology": (
        "Iteratively reweighted least squares on the Bernoulli log-likelihood, on the "
        "training partition only, to a relative log-likelihood change below $10^{-9}$. No "
        "penalty; the four drivers are chosen on judgement. The prepayment rate is around "
        "two per cent a month, so the fit is on a rare event: the intercept carries most of "
        "the base rate and the standard errors on the slopes are what a reviewer should ask "
        "about. The test partition is escrowed by MAYA and scored blind."
    ),
    "Validation Evidence": (
        "Discrimination as the area under the ROC curve on the training and validation "
        "partitions, and the fitted coefficients compared against the generating process, "
        "which for this synthetic book is known. Calibration is what MAYA's blind scoring "
        "returns: on a zero-one target the root mean squared error is the root Brier score, "
        "and on a two-per-cent event a model predicting zero everywhere scores about 0.133, "
        "so that figure is the number to beat and is quoted beside the model's."
    ),
    "Known Weaknesses": (
        "The incentive coefficient is identified only by the rate cycle in the fitting "
        "window; a flatter window would leave it unidentified and the fit would report a "
        "number anyway. The hazard is independent across loans, so a pool-level forecast in "
        "a refinancing wave is too confident. Burnout is absent: a pool that has already "
        "refinanced once is less responsive the second time, and this model will over-"
        "predict it. There is no term structure and no capacity constraint, so the model "
        "cannot represent the queue at a servicer that is the real limit in a wave."
    ),
    "Change Log": (
        "Version 1: initial monthly hazard, fitted on the 2023-07 to 2025-12 window under "
        "training warrant mortgage\\_prepay/smm\\_fit\\_2025."
    ),
}


def specification() -> str:
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in SECTIONS.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        "\\title{Monthly voluntary prepayment hazard}\\author{Mortgage analytics}\n"
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
    """The people, each an SDK client logged in with their own roles."""

    def __init__(self, maya: Any) -> None:
        self.dana = maya.client("dana")  # feature designer
        self.mick = maya.client("mick")  # feature manager: approves features, pins
        self.mona = maya.client("mona")  # model designer
        self.devi = maya.client("devi")  # model developer: warrants, fits, workspaces
        self.mgr = maya.client("mgr")  # model manager
        self.lara = maya.client("lara")  # a second model manager
        self.owen = maya.client("owen")  # model owner
        self.admin = maya.client("admin")


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet — run get_training_warrant.py")


def approved_parameters(warrant: dict[str, Any]) -> dict[str, Any]:
    approved = [p for p in warrant.get("parameter_sets", []) if p["state"] == "approved"]
    if not approved:
        raise SystemExit(
            f"No approved parameter set on '{warrant['name']}' — run fit_parameters.py"
        )
    return dict(approved[0])


def find_workspace(client: Any, name: str) -> dict[str, Any] | None:
    for row in client.workspaces.list():
        if row["name"] == name:
            return dict(client.workspaces.get(row["id"]))
    return None


# ---------------------------------------------------------------------------------
# The fitting mathematics: the same design matrix the formula declares, and IRLS.
# ---------------------------------------------------------------------------------
def design_matrix(frame: pd.DataFrame) -> np.ndarray:
    """The four drivers as the model reads them, with the scalings the formula declares.

    Reading the scalings off the model rather than choosing them here is what keeps the
    fit and MAYA's own evaluation of the formula in agreement."""
    incentive = 100.0 * (frame["wac"].astype(float) - frame["mktRate"].astype(float))
    seasoning = np.minimum(frame["age"].astype(float), 36.0) / 12.0
    equity = 1.0 - frame["ltv"].astype(float)
    return np.column_stack(
        [
            np.ones(len(frame)),
            incentive.to_numpy(),
            seasoning.to_numpy(),
            equity.to_numpy(),
            frame["movingSeason"].astype(float).to_numpy(),
        ]
    )


def fit_logistic(X: np.ndarray, y: np.ndarray, tol: float = 1e-9, limit: int = 80) -> np.ndarray:
    beta = np.zeros(X.shape[1])
    previous = -np.inf
    for _ in range(limit):
        eta = X @ beta
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(mu * (1 - mu), 1e-9, None)
        z = eta + (y - mu) / w
        beta = np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (w * z))
        loglik = float(np.sum(y * eta - np.logaddexp(0.0, eta)))
        if abs(loglik - previous) < tol * max(1.0, abs(loglik)):
            break
        previous = loglik
    if not np.all(np.isfinite(beta)):
        raise ValueError("the fit did not converge to finite coefficients")
    return beta


def auc(y: np.ndarray, score: np.ndarray) -> float:
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), dtype=float)
    ranks[order] = np.arange(1, len(score) + 1)
    positives, negatives = float(y.sum()), float((1 - y).sum())
    if not positives or not negatives:
        return float("nan")
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def cpr(smm: float) -> float:
    """The annualised constant prepayment rate a monthly hazard implies."""
    return 1.0 - (1.0 - smm) ** 12
