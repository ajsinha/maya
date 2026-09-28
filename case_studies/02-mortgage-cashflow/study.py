"""
What the steps of this case study share: the objects' names, the definitions, the model
in LaTeX, the two implementations of it, the specification document, and the people.

Nothing here talks to MAYA. It is the study's declarations — the things that would sit
under source control at a bank — in one place, so each step script reads as the step it
is, and so two steps cannot disagree about what the panel is called or what the model
says.

Steps find each other's work by name: ``mortgage_loan_month_panel``, ``cashflow_recon_2509``,
``scheduled_cashflow_live``. A step run an hour later in a different process locates what
the last one made exactly the way a person or a scheduled job would — by asking MAYA.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

NS = "mortgage_alm"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("loan_tape", "servicer_report")
AS_OF = dt.date(2025, 9, 30)
KNOWN = dt.datetime(2025, 10, 20, tzinfo=dt.timezone.utc)
SERVICING_FEE = 0.0025  # 25bp a year, from the servicing agreement
NEWLINE = b"\n"

# The model, as the analyst wrote it. MAYA reads LaTeX and Python into the same tree;
# this is the LaTeX, because for a formula this shape the LaTeX *is* the documentation.
#
#   i         the monthly rate
#   n         payments remaining — the term less the age, and not the term
#   annuity   the present value of n payments of 1, at i
#   payment   the level payment that amortises the balance over those n months
#   netCash   what reaches the investor: the payment less the servicer's monthly fee
FORMULA = r"""
i = \frac{rate}{12}
n = term - age
annuity = \frac{1 - (1 + i)^{-n}}{i}
payment = \frac{balance}{annuity}
netCash = payment - balance \cdot \frac{fee}{12}
"""
ROLES = {
    "rate": "feature",
    "term": "feature",
    "age": "feature",
    "balance": "feature",
    "fee": "parameter",
}

# The desk's implementation, written to MAYA's model interface (§8.3): a class named
# Model with fit(X, y, ctx) and predict(X, params, ctx). It is vectorised numpy with its
# own variable names and its own order of operations. MAYA does not ask it to look like
# the formula — it asks whether it *computes* the formula, which is a different and much
# better question.
#
# fit() has nothing to learn, and says so rather than pretending: a contractual cashflow
# has no parameters to estimate, and the one constant comes from the servicing agreement.
DESK_CODE = '''
"""Monthly net cashflow of a level-payment mortgage. Desk implementation."""

import numpy as np


class Model:
    def fit(self, X, y, ctx):
        """Nothing is estimated: every quantity in this model is contractual."""
        return {}

    def predict(self, X, params, ctx):
        balance = np.asarray(X["balance"], dtype=float)
        monthly = np.asarray(X["rate"], dtype=float) / 12.0
        remaining = np.asarray(X["term"], dtype=float) - np.asarray(X["age"], dtype=float)
        growth = (1.0 + monthly) ** remaining
        payment = balance * monthly * growth / (growth - 1.0)
        servicing = balance * params["fee"] / 12.0
        return payment - servicing
'''

# The same, with the mistake every mortgage system makes once: amortising over the
# original term rather than the term remaining. It is one expression, it is never caught
# by a unit test written from the same misunderstanding, and it understates the payment
# on every seasoned loan in the book.
BUGGY_CODE = DESK_CODE.replace(
    'remaining = np.asarray(X["term"], dtype=float) - np.asarray(X["age"], dtype=float)',
    'remaining = np.asarray(X["term"], dtype=float)  # BUG: ignores how seasoned the loan is',
)

TAPE_DEF = {
    "index": ["date", "loan"],
    "index_types": {"date": "date", "loan": "string"},
    "schema": [
        {"name": "balance", "type": "float64"},
        {"name": "rate", "type": "float64"},
        {"name": "term", "type": "int64"},
        {"name": "age", "type": "int64"},
        {"name": "original_balance", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "balance"},
        {"check": "range", "attr": "rate", "min": 0.0, "max": 0.25},
        # A loan cannot be older than its term. This check is the data-side counterpart of
        # the bug the conformance test catches on the code side.
        {"check": "range", "attr": "age", "min": 0, "max": 480},
    ],
}

REPORT_DEF = {
    "index": ["date", "loan"],
    "index_types": {"date": "date", "loan": "string"},
    "schema": [{"name": "remitted", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "remitted"}],
}


PANEL = "mortgage_loan_month_panel"
PIN = "recon2509"
MODEL = "mortgage_scheduled_cashflow"
WARRANT = "cashflow_recon_2509"
LIVE = "scheduled_cashflow_live"
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
MODEL_REF = f"{NS}/{MODEL}@v1"
CONTACT = "alm.analytics@example.com"

# A second model manager: the execution-warrant policy asks for a model manager's
# approval, and the one who submitted it cannot also give it.
EXTRA_USERS = {"lara": ["model_manager"]}

# The panel. The servicer's remittance is carried beside the four tape columns as the
# benchmark the output is measured against; it is not an input, and the model's input
# contract does not name it.
PANEL_DEF = {
    "index": ["date", "loan"],
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/{feature}@v1", "source_attr": attr}
        for attr, feature in (
            ("balance", "loan_tape"),
            ("rate", "loan_tape"),
            ("term", "loan_tape"),
            ("age", "loan_tape"),
            ("remitted", "servicer_report"),
        )
    ],
}
DEFINITIONS = {"loan_tape": TAPE_DEF, "servicer_report": REPORT_DEF}

# The smoke run and the differential test need a value for every input the contract
# names, in realistic units: two loans, one new and one seasoned.
SAMPLE = {
    "balance": [250_000.0, 75_000.0],
    "rate": [0.0325, 0.0615],
    "term": [360.0, 180.0],
    "age": [1.0, 149.0],
}

TARGET_JUSTIFICATION = (
    "The benchmark 'remitted' is the servicer's report, which arrives a fortnight after "
    "the month it covers, so its knowledge time is later than its event date by "
    "construction. It is a benchmark and never an input: the model's input contract names "
    "only the four tape columns, all of which are known two business days after month end."
)


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    """The training warrant this study drew, found the way anything finds it: by name."""
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet — run get_training_warrant.py")


def approved_parameters(warrant: dict[str, Any]) -> dict[str, Any]:
    approved = [p for p in warrant.get("parameter_sets", []) if p["state"] == "approved"]
    if not approved:
        raise SystemExit(
            f"No approved parameter set on '{warrant['name']}' — run get_training_warrant.py"
        )
    return dict(approved[0])


SECTIONS = {
    "Purpose": (
        "Project the monthly cash a pool of fixed-rate, level-payment mortgages remits to "
        "the investor, for asset-liability management, liquidity planning and the monthly "
        "reconciliation against the servicer's report."
    ),
    "Scope and Limitations": (
        "Fixed-rate, fully amortising, level-payment loans with at least two payments "
        "remaining. It is a \\emph{scheduled} cashflow model: it says what the contract requires "
        "this month. It does not forecast prepayment, default, delinquency or recovery, and "
        "must not be used as a valuation model on its own — a price needs a prepayment "
        "model and a discount curve, which are separate models with their own warrants. "
        "Interest-only periods, rate resets, payment holidays and capitalised arrears are "
        "out of scope and are not detected by the model."
    ),
    "Mathematical Formulation": (
        "With balance $B$, annual coupon $r$, original term $m$ months and age $a$ months, "
        "let $i = r/12$ and $n = m - a$. The present value of $n$ unit payments is "
        "$\\alpha = (1 - (1+i)^{-n})/i$, the level payment is $P = B/\\alpha$, and the cash "
        "reaching the investor is $P - Bf/12$ where $f$ is the annual servicing fee. The "
        "interest and principal components, $Bi$ and $P - Bi$, follow from the same "
        "quantities and are reported by the reference implementation."
    ),
    "Assumptions": (
        "That the tape's balance is the balance on which interest accrues this month; that "
        "the coupon is fixed for the remaining life; that payments are monthly, in arrears "
        "and of equal size; that the age on the tape counts payments actually made, so that "
        "$m - a$ is the number remaining; and that the servicing fee accrues on the "
        "outstanding balance at a rate fixed by the servicing agreement."
    ),
    "Data and Features Used": (
        "Feature set mortgage_alm/mortgage_loan_month_panel, pinned point-in-time. Inputs: balance, "
        "coupon, original term and age from the monthly loan tape, cut two business days "
        "after month end. The servicer's remittance is carried in the same feature set as "
        "the benchmark the output is measured against; it is not an input, and the model's "
        "input contract does not name it."
    ),
    "Calibration Methodology": (
        "None. There is nothing to fit: every quantity is contractual. The one parameter, "
        "the servicing fee, is taken from the servicing agreement at 25 basis points a year "
        "and is registered as an approved parameter set so that the figure in production is "
        "a figure somebody signed for. A change to the agreement is a new parameter set and "
        "a new approval, not an edit."
    ),
    "Validation Evidence": (
        "Two independent checks. First, conformance: the desk's implementation is "
        "differentially tested against this specification over sampled inputs, and a "
        "disagreement anywhere in the sampled domain fails the model version rather than "
        "being noted. Second, reconciliation: the model's output is scored blind against "
        "what the servicer actually remitted, in pounds per loan-month. The residual is not "
        "expected to be zero — partial prepayments and late payments are real and are not "
        "in scope — and its size is the statement of accuracy."
    ),
    "Known Weaknesses": (
        "The model is exactly as right as the tape. A stale age column, a capitalised "
        "arrears balance or a loan that has silently converted to interest-only all produce "
        "a confident and wrong number, and the model cannot tell. It says nothing about "
        "\\emph{whether} the cash will arrive, only what the contract requires: for a book with "
        "meaningful arrears the reconciliation residual will be dominated by collection, "
        "not by arithmetic."
    ),
    "Change Log": (
        "Version 1: initial scheduled-cashflow model, servicing fee 25 basis points, "
        "reconciled against the servicer's report for the 2024-01 to 2025-09 window."
    ),
}


def specification() -> str:
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in SECTIONS.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        "\\title{Scheduled mortgage cashflow}\\author{ALM and model risk}\n"
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


# One line each, shown under the name in MAYA's lists: what the object is, in words.
DESCRIPTIONS = {
    "loan_tape": "Monthly loan tape: balance, rate, term and age of each mortgage",
    "servicer_report": "The cash each mortgage remitted to the servicer that month",
    "mortgage_loan_month_panel": "One row per mortgage and month: the loan's terms and the cash it remitted",
    "mortgage_scheduled_cashflow": "Scheduled monthly cash from a level-payment mortgage net of the servicing fee; nothing to fit",
}
