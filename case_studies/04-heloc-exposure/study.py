"""
What the steps of this case study share: names, feature definitions, the two member
models, the composite that routes between them, the documents, and the people.

Nothing here talks to MAYA. Steps find each other's work by name.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NS = "heloc"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("heloc_month", "exposure_later")
NEWLINE = b"\n"

PANEL = "heloc_panel"
PIN = "ead2506"
DRAW_MODEL = "usage_draw_period"
REPAY_MODEL = "usage_repayment"
COMPOSITE = "ead_heloc"
WARRANT = "ead_fit_2025h1"
LIVE = "ead_heloc_live"

AS_OF = dt.date(2025, 6, 30)
KNOWN = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
COMPOSITE_REF = f"{NS}/{COMPOSITE}@v1"
CONTACT = "retail.secured.risk@example.com"
EXTRA_USERS = {"lara": ["model_manager"]}

# ---------------------------------------------------------------------------------
# The two members, and why they are shaped differently.
#
# In the draw period a borrower can take more of the line, and the fraction they take is
# bounded below by zero and above by one: a logistic is the right shape, and its bounds are
# a property of the problem rather than a convenience.
#
# In repayment the line is closed to new draws and the balance amortises, so the twelve-
# month change is *negative*. A logistic cannot produce a negative number, so forcing both
# regimes through one functional form would be wrong about at least one of them. This is
# the whole argument for a router: not that the coefficients differ, but that the
# mathematics does.
# ---------------------------------------------------------------------------------
DRAW_FORMULA = """
eq = 1 - cltv
room = (commitment - drawn) / commitment
z = d0 + dEq*eq + dRoom*room + dRate*(100*rate - 8)
leq = 1 / (1 + exp(-z))
"""
DRAW_WEIGHTS = ("d0", "dEq", "dRoom", "dRate")
DRAW_ROLES = {
    **{w: "parameter" for w in DRAW_WEIGHTS},
    **{f: "feature" for f in ("cltv", "commitment", "drawn", "rate")},
}

REPAY_FORMULA = """
eq = 1 - cltv
leq = r0 + rEq*eq
"""
REPAY_WEIGHTS = ("r0", "rEq")
REPAY_ROLES = {**{w: "parameter" for w in REPAY_WEIGHTS}, "cltv": "feature"}

# The composite. Its combiner is written as an IR node rather than a formula string because
# it refers to a member's output by alias — ``draw.leq`` — which is not something the
# formula syntax spells. Read it as:
#
#     ead = drawn + where(inDraw, draw.leq, repay.leq) * (commitment - drawn)
#
# The exposure at default is what is already drawn plus the part of the remaining line the
# borrower is expected to take, and which fraction applies depends on the regime.
COMBINE = {
    "op": "add",
    "args": [
        {"ref": "drawn"},
        {
            "op": "mul",
            "args": [
                {
                    "op": "where",
                    "args": [{"ref": "inDraw"}, {"ref": "draw.leq"}, {"ref": "repay.leq"}],
                },
                {"op": "sub", "args": [{"ref": "commitment"}, {"ref": "drawn"}]},
            ],
        },
    ],
}


def composite_ir() -> dict[str, Any]:
    return {
        "outputs": [{"name": "ead", "type": "float64"}],
        "inputs": [],  # the union of the members' contracts, which MAYA computes
        "composite": {
            "kind": "router",
            "members": [
                {"alias": "draw", "ref": f"maya://model/{NS}/{DRAW_MODEL}@v1"},
                {"alias": "repay", "ref": f"maya://model/{NS}/{REPAY_MODEL}@v1"},
            ],
            "combine": COMBINE,
            "train": {"mode": "parallel", "order": ["draw", "repay"]},
        },
    }


# The generating coefficients (make_data.py), for the README's comparison.
TRUE_DRAW = {"d0": -1.55, "dEq": 1.30, "dRoom": 0.95, "dRate": -0.11}
TRUE_REPAY = {"r0": -4.20, "rEq": 0.38}

TARGET = "exposure12"
TARGET_JUSTIFICATION = (
    "The target 'exposure12' is the drawn balance twelve months after the observation "
    "month, so it cannot be known until those twelve months have passed and its knowledge "
    "time is later than its event date by construction. It is never an input: the "
    "composite's contract names the commitment, the drawn balance, the combined "
    "loan-to-value, the rate, and the regime flag, all known three business days after "
    "month end. The exception covers the target column alone."
)

# ---------------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------------
TAPE_DEF = {
    "index": ["date", "account"],
    "index_types": {"date": "date", "account": "string"},
    "schema": [
        {"name": "commitment", "type": "float64"},
        {"name": "drawn", "type": "float64"},
        {"name": "cltv", "type": "float64"},
        {"name": "rate", "type": "float64"},
        {"name": "seasoning", "type": "int64"},
        {"name": "in_draw", "type": "int64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "commitment"},
        {"check": "range", "attr": "cltv", "min": 0.0, "max": 1.5},
        # A drawn balance above the commitment is not a large exposure, it is a broken feed.
        {"check": "range", "attr": "rate", "min": 0.0, "max": 0.3},
    ],
}

LATER_DEF = {
    "index": ["date", "account"],
    "index_types": {"date": "date", "account": "string"},
    "schema": [{"name": "exposure12", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "exposure12"}],
}

DEFINITIONS = {"heloc_month": TAPE_DEF, "exposure_later": LATER_DEF}

PANEL_DEF = {
    "index": ["date", "account"],
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/{feature}@v1", "source_attr": source}
        for attr, feature, source in (
            ("commitment", "heloc_month", "commitment"),
            ("drawn", "heloc_month", "drawn"),
            ("cltv", "heloc_month", "cltv"),
            ("rate", "heloc_month", "rate"),
            ("seasoning", "heloc_month", "seasoning"),
            ("inDraw", "heloc_month", "in_draw"),
            ("exposure12", "exposure_later", "exposure12"),
        )
    ],
}

# ---------------------------------------------------------------------------------
# The specification documents. Three of them: one per member, and one for the composite,
# because a composite is a model in every respect and a reviewer reading it should not have
# to open two other documents to find out what it does.
# ---------------------------------------------------------------------------------
DRAW_SECTIONS = {
    "Purpose": (
        "Estimate the fraction of the undrawn portion of a home equity line of credit that "
        "a borrower will draw over the next twelve months, while the account is still "
        "within its draw period. It is a member of the exposure model heloc/ead_heloc and "
        "is not used on its own."
    ),
    "Scope and Limitations": (
        "Accounts inside the draw period only. It says nothing about accounts in "
        "repayment, which are the other member's business, and nothing about accounts in "
        "default or forbearance. It is a twelve-month reduced form: the underlying "
        "behaviour is monthly, and aggregating it to a year is an approximation that "
        "understates the variance of the outcome."
    ),
    "Mathematical Formulation": (
        "A logistic function of three drivers. With combined loan-to-value $\\ell$, the "
        "equity available is $E = 1 - \\ell$; with commitment $C$ and drawn balance $D$, "
        "the room on the line is $R = (C - D)/C$; and the rate is centred at eight per "
        "cent, $\\rho = 100r - 8$. Then $z = \\delta_0 + \\delta_E E + \\delta_R R + "
        "\\delta_\\rho \\rho$ and the draw fraction is $(1 + e^{-z})^{-1}$. The logistic is "
        "chosen because the quantity is a fraction of a known amount: it cannot be negative "
        "and cannot exceed one, and those bounds are a property of the problem rather than "
        "a convenience."
    ),
    "Assumptions": (
        "That the combined loan-to-value on the tape reflects a current valuation, which it "
        "does not in a falling market — a stale valuation overstates equity and this model "
        "will then overstate draws. That the borrower's decision depends on the room left "
        "on the line rather than on its absolute size. And that behaviour is conditionally "
        "independent across accounts, which is false in a liquidity event, when everybody "
        "draws at once."
    ),
    "Data and Features Used": (
        "Feature set heloc/heloc_panel, pinned point-in-time: commitment, drawn balance, "
        "combined loan-to-value and rate from the monthly tape, cut three business days "
        "after month end. Fitted on the realised twelve-month draw fraction, derived from "
        "the drawn balance twelve months later."
    ),
    "Calibration Methodology": (
        "The realised draw fraction is computed as $(D_{t+12} - D_t)/(C_t - D_t)$ on rows "
        "with a meaningful undrawn balance, clipped to $[0, 1]$, and the logistic is fitted "
        "to it by iteratively reweighted least squares on the training partition of the "
        "composite's warrant. Rows with almost no undrawn balance are excluded: the "
        "fraction is undefined there, and including them would let a rounding difference "
        "divided by a few pounds dominate the fit."
    ),
    "Validation Evidence": (
        "The fitted coefficients are compared against the process that generated this "
        "synthetic book, and the member's contribution is measured through the composite: "
        "MAYA scores the composite blind against the realised exposure, in currency, which "
        "is the quantity anybody actually cares about."
    ),
    "Known Weaknesses": (
        "The twelve-month reduced form cannot represent a borrower who draws the whole line "
        "in one month and repays it in the next. Equity is measured with a stale valuation. "
        "And the model has no measure of the borrower's distress: the draws that matter most "
        "for exposure at default are the ones made by somebody about to default, and "
        "nothing here sees that."
    ),
    "Change Log": "Version 1: initial draw-period usage member.",
}

REPAY_SECTIONS = {
    "Purpose": (
        "Estimate the twelve-month change in the drawn balance of a home equity line of "
        "credit that has entered its repayment period, as a fraction of the undrawn line. "
        "It is a member of heloc/ead_heloc and is not used on its own."
    ),
    "Scope and Limitations": (
        "Accounts in repayment only. The line is closed to new draws, so the twelve-month "
        "change is an amortisation and is negative; the quantity is expressed as a fraction "
        "of the undrawn line only so that the composite can combine the two regimes with "
        "one arithmetic. Prepayment in full is not modelled."
    ),
    "Mathematical Formulation": (
        "Linear in the equity available: with $E = 1 - \\ell$, the fraction is "
        "$\\rho_0 + \\rho_E E$. It is deliberately **not** a logistic. The quantity is "
        "negative, and a logistic cannot produce a negative number — forcing both regimes "
        "through one functional form would be wrong about at least one of them, which is "
        "the argument for routing between two members rather than adding an interaction "
        "term to one."
    ),
    "Assumptions": (
        "That the repayment schedule is roughly proportional to the balance, so that the "
        "twelve-month change scales with it; and that no new draws occur, which the product "
        "terms forbid and the data supports."
    ),
    "Data and Features Used": (
        "Feature set heloc/heloc_panel, pinned point-in-time: the combined loan-to-value "
        "from the monthly tape. Fitted on the same realised twelve-month change as the "
        "other member, on the repayment-period rows."
    ),
    "Calibration Methodology": (
        "Ordinary least squares on the realised fraction, on the training partition of the "
        "composite's warrant, restricted to repayment-period rows with a meaningful undrawn "
        "balance."
    ),
    "Validation Evidence": (
        "Fitted coefficients against the generating process, and the composite's blind "
        "score against realised exposure in currency."
    ),
    "Known Weaknesses": (
        "A linear form is unbounded, so far outside the fitted range of equity it will "
        "predict a fraction below minus one, which is arithmetically impossible. The "
        "composite's output range covenant is what stops that reaching a balance sheet, and "
        "it is a guard rather than a fix."
    ),
    "Change Log": "Version 1: initial repayment-period member.",
}

COMPOSITE_SECTIONS = {
    "Purpose": (
        "Estimate the exposure at default of a home equity line of credit: the drawn "
        "balance the bank would be owed if the borrower defaulted, which is more than the "
        "balance drawn today because a committed line can still be taken down. Used for "
        "credit risk capital, for the exposure input to expected credit loss, and for "
        "liquidity planning on committed facilities."
    ),
    "Scope and Limitations": (
        "First-lien and second-lien home equity lines of credit in the domestic book. It "
        "is a *usage* model, not a regulatory loan-equivalent model: a Basel-compliant LEQ "
        "is estimated on accounts that actually defaulted, and this one is estimated on all "
        "accounts, which makes it the right instrument for stress and liquidity work and the "
        "wrong one for regulatory exposure at default without a separate conditional "
        "adjustment. That distinction is the single most important sentence in this "
        "document. Defaulted, forborne and frozen accounts are out of scope."
    ),
    "Mathematical Formulation": (
        "A router over two members. With commitment $C$, drawn balance $D$ and the "
        "regime indicator $\\mathbb{1}_{\\text{draw}}$, the estimate is "
        "$\\mathrm{EAD} = D + f \\cdot (C - D)$ where $f$ is the draw member's fraction "
        "inside the draw period and the repayment member's fraction outside it. The two "
        "members have different functional forms for a stated reason, given in each of "
        "their documents."
    ),
    "Assumptions": (
        "That the regime flag on the tape is correct — an account wrongly marked as still "
        "in its draw period is given a materially larger exposure, and neither member can "
        "detect that. That the commitment on the tape is the legal commitment rather than a "
        "shadow limit. And that the two regimes are exhaustive."
    ),
    "Data and Features Used": (
        "Feature set heloc/heloc_panel, pinned point-in-time. The composite's input "
        "contract is the union of its members' contracts plus the commitment, the drawn "
        "balance and the regime flag its own combiner reads."
    ),
    "Calibration Methodology": (
        "The two members are fitted independently — in parallel, since neither consumes the "
        "other's output — each on its own regime's rows, under one training warrant against "
        "one pinned feature set. The warrant will not seal until every trainable member has "
        "an approved parameter set, so a composite cannot go to production with one member "
        "fitted and the other left at whatever it had."
    ),
    "Validation Evidence": (
        "MAYA scores the composite blind against the realised drawn balance twelve months "
        "later, in currency, on the escrowed partition. The benchmark quoted beside it is "
        "the naive forecast that exposure does not change — today's drawn balance — because "
        "a currency error with nothing to compare it against says nothing about whether the "
        "model is worth running."
    ),
    "Known Weaknesses": (
        "The composite is capped at the maturity of its least mature member, which is the "
        "right behaviour and means a member's deprecation is the composite's problem too. "
        "It inherits both members' weaknesses: a stale valuation, no measure of borrower "
        "distress, an unbounded repayment member, and a twelve-month reduced form over "
        "monthly behaviour. In a liquidity event the independence assumption fails in the "
        "direction that matters, and the model will under-state exposure exactly when the "
        "number is needed."
    ),
    "Change Log": (
        "Version 1: router over the draw-period and repayment members, drawn under "
        "heloc/ead\\_fit\\_2025h1."
    ),
}


def document(title: str, sections: dict[str, str]) -> str:
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in sections.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath,amssymb}\n"
        f"\\title{{{title}}}\\author{{Retail secured risk}}\n"
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
        self.owen = maya.client("owen")
        self.admin = maya.client("admin")


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet — run get_training_warrant.py")


def member_parameters(warrant: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The approved parameter set per member alias."""
    out = {}
    for ps in warrant.get("parameter_sets", []):
        if ps["state"] == "approved":
            out[ps.get("member_alias") or ""] = dict(ps)
    return out


# ---------------------------------------------------------------------------------
# The fitting mathematics.
# ---------------------------------------------------------------------------------
MIN_UNDRAWN = 500.0  # below this the realised fraction is noise divided by nothing


def realised_fraction(frame: pd.DataFrame) -> pd.DataFrame:
    """The twelve-month draw fraction, and the rows on which it means anything.

    The denominator is the undrawn line. On an account with forty pounds of room a rounding
    difference becomes a fraction of one, so those rows are dropped rather than clipped —
    clipping would keep the row and hide that its value was never informative."""
    undrawn = frame["commitment"].astype(float) - frame["drawn"].astype(float)
    out = frame.loc[undrawn > MIN_UNDRAWN].copy()
    out["fraction"] = (out["exposure12"].astype(float) - out["drawn"].astype(float)) / (
        out["commitment"].astype(float) - out["drawn"].astype(float)
    )
    return out


def draw_design(frame: pd.DataFrame) -> np.ndarray:
    """The draw member's design matrix, with the scalings its formula declares."""
    commitment = frame["commitment"].astype(float).to_numpy()
    drawn = frame["drawn"].astype(float).to_numpy()
    return np.column_stack(
        [
            np.ones(len(frame)),
            1.0 - frame["cltv"].astype(float).to_numpy(),
            (commitment - drawn) / commitment,
            100.0 * frame["rate"].astype(float).to_numpy() - 8.0,
        ]
    )


def repay_design(frame: pd.DataFrame) -> np.ndarray:
    return np.column_stack([np.ones(len(frame)), 1.0 - frame["cltv"].astype(float).to_numpy()])


def fit_logistic_fraction(
    X: np.ndarray, y: np.ndarray, tol: float = 1e-10, limit: int = 100
) -> np.ndarray:
    """IRLS for a logistic mean on a *fraction* in [0, 1], not a zero-one label.

    The weights are the same Bernoulli variance; the target is a proportion. This is the
    standard quasi-likelihood fit, and it is what a draw fraction wants: the outcome is a
    share of a known amount rather than an event."""
    y = np.clip(y, 1e-6, 1 - 1e-6)
    beta = np.zeros(X.shape[1])
    previous = np.inf
    for _ in range(limit):
        eta = X @ beta
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(mu * (1 - mu), 1e-9, None)
        z = eta + (y - mu) / w
        beta = np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (w * z))
        deviance = float(np.sum(w * (z - X @ beta) ** 2))
        if abs(previous - deviance) < tol * max(1.0, abs(deviance)):
            break
        previous = deviance
    if not np.all(np.isfinite(beta)):
        raise ValueError("the draw member's fit did not converge")
    return beta


def fit_least_squares(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta
