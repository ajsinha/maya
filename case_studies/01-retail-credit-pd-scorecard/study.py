"""
What the steps of this case study share: the objects' names, the definitions, the
model, its specification document, and the people who act.

Nothing here talks to MAYA. It is the study's *declarations* — the things that would
sit in a repository under source control at a bank — kept in one place so that each
step script reads as the step it is, and so that two steps cannot disagree about what
the panel is called or what the model says.

Steps find each other's work by name rather than by passing identifiers in a file:
``probability_of_default_panel``, ``pd_fit_2025h1``, ``pd_scorecard_live``. That is deliberate. A step run
an hour later in a different process has to locate what the last one made exactly the
way a person or a scheduled job would — by asking MAYA.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NS = "retail_credit"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("servicing_monthly", "bureau_file", "default_outcome")

PANEL = "probability_of_default_panel"
PIN = "fit2025h1"
MODEL = "probability_of_default_scorecard"
WARRANT = "pd_fit_2025h1"
NAIVE_WARRANT = "pd_fit_naive"
LIVE = "pd_scorecard_live"

# The book runs 2023-01 to 2025-06 (make_data.py); the panel is pinned at the last month
# for which every twelve-month outcome is already known.
AS_OF = dt.date(2025, 6, 30)
KNOWN = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
MODEL_REF = f"{NS}/{MODEL}@v1"

# A second model manager, because the execution-warrant policy asks for a model manager's
# approval and the one who submitted it cannot also give it.
EXTRA_USERS = {"lara": ["model_manager"]}

# The scorecard. Every symbol is declared: the five weights are parameters to be fitted,
# the four drivers are features MAYA must find in the feature set. MAYA holds this as an
# expression tree, so it can be rendered in LaTeX for the document, lifted into reference
# code, and evaluated for blind scoring without executing anybody's Python.
#
# The centring of the bureau score is part of the model, not part of the fitting script:
# it is stated here, in the governed object, so a reader knows the units its coefficient
# is in and a second implementation cannot silently choose another centre.
FORMULA = """
b = (bureau - 680) / 60
z = intercept + wUtil*utilisation + wDti*dti + wDelinq*delinquencies + wBureau*b
pd12m = 1 / (1 + exp(-z))
"""
WEIGHTS = ("intercept", "wUtil", "wDti", "wDelinq", "wBureau")
DRIVERS = ("utilisation", "dti", "delinquencies", "bureau")
TARGET = "default_12m"
ROLES = {**{w: "parameter" for w in WEIGHTS}, **{d: "feature" for d in DRIVERS}}

# Why a forward-looking target is not leakage, written where a reviewer will read it.
# MAYA's leakage rule is "no row may use a value MAYA could not have known by its event
# date". A twelve-month default flag breaks that rule by construction, and the honest
# answer is not to widen the rule but to say why this row is an exception.
TARGET_JUSTIFICATION = (
    "The target default_12m is a forward-looking outcome: whether the account defaulted "
    "in the twelve months after the observation month. Its knowledge time is necessarily "
    "later than its event date, and it is never an input at scoring time — the scorecard "
    "takes the four drivers only, all of which are known at the observation month. The "
    "exception covers the target column alone; any driver known late would be leakage."
)

# ---------------------------------------------------------------------------------
# Feature definitions. Written out rather than inferred, because the definition is the
# governed object: the index, the types, where knowledge time comes from, how gaps are
# filled, and what must be true of the values.
# ---------------------------------------------------------------------------------
SERVICING_DEF = {
    "index": ["date", "account"],
    "index_types": {"date": "date", "account": "string"},
    "schema": [
        {"name": "utilisation", "type": "float64"},
        {"name": "dti", "type": "float64"},
        {"name": "delinquencies", "type": "int64"},
        {"name": "months_on_book", "type": "int64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "utilisation"},
        {"check": "range", "attr": "utilisation", "min": 0.0, "max": 1.0},
        {"check": "range", "attr": "dti", "min": 0.0, "max": 1.0},
    ],
}

BUREAU_DEF = {
    "index": ["date", "account"],
    "index_types": {"date": "date", "account": "string"},
    "schema": [{"name": "bureau_score", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "range", "attr": "bureau_score", "min": 300, "max": 850}],
}

OUTCOME_DEF = {
    "index": ["date", "account"],
    "index_types": {"date": "date", "account": "string"},
    "schema": [{"name": "default_12m", "type": "int64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "default_12m"}],
}

DEFINITIONS = {
    "servicing_monthly": SERVICING_DEF,
    "bureau_file": BUREAU_DEF,
    "default_outcome": OUTCOME_DEF,
}

# The panel: the monthly drivers, the quarterly bureau score carried as-of rather than
# resampled, and the outcome.
PANEL_DEF = {
    "index": ["date", "account"],
    "alignment": {"mode": "asof", "tolerance_days": 100},
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/{feature}@v1", "source_attr": source}
        for attr, feature, source in (
            ("utilisation", "servicing_monthly", "utilisation"),
            ("dti", "servicing_monthly", "dti"),
            ("delinquencies", "servicing_monthly", "delinquencies"),
            ("bureau", "bureau_file", "bureau_score"),
            ("default_12m", "default_outcome", "default_12m"),
        )
    ],
}

SECTIONS = {
    "Purpose": (
        "Estimate the probability that a revolving retail account defaults within the "
        "twelve months following an observation month, for IFRS 9 stage allocation and "
        "for portfolio-level expected credit loss."
    ),
    "Scope and Limitations": (
        "Revolving unsecured retail accounts with at least six months on book, in the "
        "domestic book only. The scorecard is not calibrated for accounts in forbearance, "
        "for the first six months after origination, or for secured lending. It is a "
        "ranking and calibration instrument, not a stress model: it carries no "
        "macroeconomic driver and must not be used to project defaults under a scenario."
    ),
    "Mathematical Formulation": (
        "A logistic link on four drivers. With $z = \\beta_0 + \\beta_u u + \\beta_d d + "
        "\\beta_n n + \\beta_b b$ for utilisation $u$, debt-to-income $d$, twelve-month "
        "delinquency count $n$ and centred bureau score $b = (\\mathrm{score} - 680)/60$, "
        "the estimate is $\\mathrm{PD}_{12} = (1 + e^{-z})^{-1}$. The coefficients are "
        "fitted by iteratively reweighted least squares on the Bernoulli log-likelihood; "
        "no penalty is applied, and the four drivers are retained on judgement rather than "
        "by selection. The centring constants of the bureau score are fixed by design and "
        "are not fitted; they are stated in the model itself so that the coefficient's "
        "units are unambiguous."
    ),
    "Assumptions": (
        "That the twelve-month default definition is stable across the fitting window; "
        "that the log-odds are linear in the four drivers, which the residual plots support "
        "over the central nine deciles and not in the extreme tails; that the bureau score "
        "carried as-of the last delivered file is a fair view of the borrower at the "
        "observation month; and that the book's composition at scoring time resembles the "
        "fitting window, which is what the execution warrant's covenants monitor."
    ),
    "Data and Features Used": (
        "Feature set retail_credit/probability_of_default_panel, pinned point-in-time. Drivers: utilisation, "
        "debt-to-income and the delinquency count from the monthly servicing extract, which "
        "is cut five days after month end; the bureau score from a quarterly file delivered "
        "a fortnight after the quarter it describes, carried forward as-of with a "
        "hundred-day tolerance. The target is the twelve-month default flag, whose "
        "knowledge time is a year after its event date by construction."
    ),
    "Calibration Methodology": (
        "Iteratively reweighted least squares to convergence at a relative log-likelihood "
        "change below $10^{-9}$, on the training partition only. The validation partition "
        "is used to check the fit did not diverge; the test partition is escrowed by MAYA "
        "and is scored blind, once per candidate parameter set, and every attempt is "
        "counted on the warrant."
    ),
    "Validation Evidence": (
        "Discrimination is reported as the area under the ROC curve on the training and "
        "validation partitions. Calibration is the quantity MAYA's blind scoring returns: "
        "on a zero-one target the root mean squared error is the square root of the Brier "
        "score, so the holdout figure is a calibration statement about unseen rows and not "
        "a discrimination one."
    ),
    "Known Weaknesses": (
        "No macroeconomic driver, so the scorecard cannot answer a scenario question. The "
        "bureau score is stale by up to a quarter, which flatters it in a fast "
        "deterioration. The linear log-odds assumption fails in the tails, where the model "
        "under-predicts. Accounts in forbearance are out of scope and are not detected by "
        "the model itself; the calling system must exclude them. Accounts whose first "
        "observation months precede the first bureau delivery have no bureau score at all; "
        "those rows are excluded from the fit rather than filled, and the model has nothing "
        "to say about them."
    ),
    "Change Log": (
        "Version 1: initial scorecard, fitted on the 2023-01 to 2025-06 window, drawn "
        "under training warrant retail\\_credit/pd\\_fit\\_2025h1."
    ),
}


def specification() -> str:
    """The model's specification document: §8.3's nine sections, said properly.

    MAYA refuses to submit a model version whose document is missing a section, so this
    is not decoration — it is the gate. What is written here is what a reviewer reads."""
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in SECTIONS.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        "\\title{Retail revolving PD scorecard}\\author{Model risk}\n"
        f"\\begin{{document}}\\maketitle\n{body}\n\\end{{document}}\n"
    )


def feed(name: str) -> bytes:
    """One of the three delivered files, exactly as it sits on disk."""
    path = DATA / f"{name}.csv"
    if not path.exists():
        raise SystemExit(
            f"{path} is missing. Write it with:\n"
            f"  .venv/bin/python {Path(__file__).parent.name}/make_data.py"
        )
    return path.read_bytes()


class Cast:
    """The people in the story, each an SDK client logged in with their own roles.

    Naming them is the point: MAYA has no single "the script" identity, and every refusal
    in this study happens because the person acting is the wrong person to act."""

    def __init__(self, maya: Any) -> None:
        self.dana = maya.client("dana")  # feature designer: writes definitions
        self.mick = maya.client("mick")  # feature manager: approves them, and pins
        self.mona = maya.client("mona")  # model designer: the model and its document
        self.devi = maya.client("devi")  # model developer: draws warrants and fits
        self.mgr = maya.client("mgr")  # model manager: approves models and parameters
        self.owen = maya.client("owen")  # model owner: accountable for it in production
        self.lara = maya.client("lara")  # a second model manager: independent validation
        self.admin = maya.client("admin")


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    """The training warrant this study drew, found the way anything finds it: by name."""
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet — run get_training_warrant.py")


def approved_parameters(warrant: dict[str, Any]) -> dict[str, Any]:
    """The approved parameter set on a warrant, or a clear complaint that there is none."""
    approved = [p for p in warrant.get("parameter_sets", []) if p["state"] == "approved"]
    if not approved:
        raise SystemExit(
            f"No approved parameter set on '{warrant['name']}' — run fit_parameters.py"
        )
    return dict(approved[0])


def find_execution_warrant(client: Any, name: str) -> dict[str, Any]:
    for row in client.execution.list():
        if row["name"] == name:
            return dict(client.execution.get(row["id"]))
    raise SystemExit(f"No execution warrant called '{name}' yet — run get_execution_warrant.py")


# ---------------------------------------------------------------------------------
# The fitting mathematics. Iteratively reweighted least squares and an ROC area, in
# numpy, so the study needs nothing beyond what MAYA already installs. What matters for
# the demonstration is not the optimiser but that the fit sees the training partition
# and nothing else.
# ---------------------------------------------------------------------------------
def design_matrix(frame: pd.DataFrame) -> np.ndarray:
    """The four drivers as the model reads them, including the bureau centring it declares.

    The script must scale the bureau score exactly as FORMULA does. Doing it here and
    nowhere else is the whole reason the centring is written into the model: the fit and
    the scoring agree because they are reading the same statement."""
    return np.column_stack(
        [
            np.ones(len(frame)),
            frame["utilisation"].astype(float).to_numpy(),
            frame["dti"].astype(float).to_numpy(),
            frame["delinquencies"].astype(float).to_numpy(),
            (frame["bureau"].astype(float).to_numpy() - 680.0) / 60.0,
        ]
    )


def fit_logistic(X: np.ndarray, y: np.ndarray, tol: float = 1e-9, limit: int = 60) -> np.ndarray:
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
        raise ValueError(
            "the fit did not converge to finite coefficients; check the conditioning of "
            "the design matrix before uploading anything to a warrant"
        )
    return beta


def auc(y: np.ndarray, score: np.ndarray) -> float:
    """Area under the ROC curve, by the rank identity (no scipy needed)."""
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), dtype=float)
    ranks[order] = np.arange(1, len(score) + 1)
    positives, negatives = float(y.sum()), float((1 - y).sum())
    if not positives or not negatives:
        return float("nan")
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


# One line each, shown under the name in MAYA's lists: what the object is, in words.
DESCRIPTIONS = {
    "bureau_file": "Each account's credit bureau score, as the bureau delivered it each month",
    "servicing_monthly": "Monthly servicing data per account: utilisation, debt-to-income, delinquencies, months on book",
    "default_outcome": "Whether each account defaulted within the following 12 months",
    "probability_of_default_panel": "One row per account and month: the scorecard's drivers and the 12-month default flag",
    "probability_of_default_scorecard": "12-month probability of default for retail credit accounts, a logistic scorecard",
}
