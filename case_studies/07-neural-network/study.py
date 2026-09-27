"""
What the steps of this case study share: the objects' names, the definitions, the
declared black box, its specification document, the challenger, and the people.

Nothing here talks to MAYA. It is the study's *declarations* — the things that would sit
in a repository under source control at a bank — kept in one place so that each step
script reads as the step it is, and so that two steps cannot disagree about what the
panel is called or what the network is.

Steps find each other's work by name: ``fraud_panel``, ``fraud_mlp``,
``fraud_mlp_fit_2025q2``, ``fraud_mlp_live``. A step run an hour later in a different
process locates what the last one made exactly the way a person or a scheduled job would —
by asking MAYA.

The one thing that is *not* declared here is the mathematics, because there is none to
declare. The network is ``network.py`` beside this file, and the closest MAYA can come to
holding it is the black-box node in ``model_ir()``: the architecture, the
hyperparameters, the seed, and a prose statement of what the thing estimates. That
substitution is the subject of the study.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import network

NS = "card_fraud"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("card_day_activity", "card_profile", "fraud_confirmed")

PANEL = "fraud_panel"
PIN = "fit2025q2"
MODEL = "fraud_mlp"
WARRANT = "fraud_mlp_fit_2025q2"
NAIVE_WARRANT = "fraud_mlp_fit_naive"
LIVE = "fraud_mlp_live"
CONTACT = "card.fraud.analytics@example.com"

# The book runs 2025-03-01 to 2025-04-14 (make_data.py); the panel is pinned at the last
# day whose 45-day dispute window has closed.
AS_OF = dt.date(2025, 4, 14)
KNOWN = dt.datetime(2025, 7, 1, tzinfo=dt.timezone.utc)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
MODEL_REF = f"{NS}/{MODEL}@v1"

# A second model manager, because the execution-warrant policy asks for a model manager's
# approval and the one who submitted it cannot also give it.
EXTRA_USERS = {"lara": ["model_manager"]}

# The one number the whole fit hangs on. It is declared in the black-box node, in the
# warrant spec and in the specification document, and it is the same number in all three:
# a network's parameters are reproducible from the seed and from nothing else.
SEED = 7
DRIVERS = network.COLUMNS
TARGET = "fraud_confirmed"

# What the black-box node carries in place of a formula. Every one of these is a decision
# a reviewer can challenge without being able to read a single weight.
HYPERPARAMETERS = {
    "layers": [len(DRIVERS), *network.HIDDEN, 1],
    "activation": "tanh on both hidden layers, logistic on the output",
    "loss": "Bernoulli negative log-likelihood, unweighted",
    "optimiser": "mini-batch gradient descent, no momentum, no penalty",
    "learning_rate": network.LEARNING_RATE,
    "batch_size": network.BATCH,
    "epochs": network.EPOCHS,
    "stopping_rule": (
        f"a fixed {network.EPOCHS} epochs; no early stopping, so nothing in the fit "
        "depends on the validation partition"
    ),
    "initialisation": "He-normal from the declared seed; biases zero",
    "standardisation": (
        "each driver centred and scaled by the training partition's own mean and standard "
        "deviation, which are carried in the parameter set as x_mean and x_scale"
    ),
    "seed": SEED,
    "fitted_values": sum(
        int(np.asarray(v).size) for v in network.initial_parameters(SEED).values()
    ),
}
ESTIMATES = (
    "The probability that a card-day is later confirmed as fraud by the disputes team, "
    "given the day's authorisation pattern and the card's profile. It is a ranking "
    "instrument for a review queue, not a calibrated loss estimate, and it explains "
    "nothing: there is no coefficient to read and no reason code to give a customer."
)
ARCHITECTURE = (
    f"Feed-forward neural network (multi-layer perceptron), {len(DRIVERS)} inputs -> "
    f"{network.HIDDEN[0]} tanh -> {network.HIDDEN[1]} tanh -> 1 logistic; "
    f"{HYPERPARAMETERS['fitted_values']} fitted values in eight arrays. There is no closed "
    "form: the mapping from inputs to score cannot be written as an expression anybody "
    "would read, which is why this model is declared opaque rather than parsed."
)


def model_ir(estimates: str = ESTIMATES) -> dict[str, Any]:
    """The model as MAYA can hold it: a declared black box with an exact input contract.

    The six drivers are ``feature`` inputs, so MAYA checks a feature set against them
    before a warrant can be drawn. The eight weight arrays are ``parameter`` inputs, so
    MAYA requires an approved parameter set before the model may run anywhere. Neither
    fact needs MAYA to understand the network.
    """
    return {
        "outputs": [{"name": "fraud_score", "type": "float64"}],
        "inputs": [
            *[{"name": name, "type": "float64", "role": "feature"} for name in DRIVERS],
            *[
                {"name": name, "type": "float64", "role": "parameter"}
                for name in network.initial_parameters(SEED)
            ],
        ],
        "black_box": {
            "estimates": estimates,
            "architecture": ARCHITECTURE,
            "hyperparameters": HYPERPARAMETERS,
        },
    }


# Eight card-days, in realistic units, for the ladder's smoke run and its determinism
# probe. They are written out rather than sampled so that a reviewer can see what the
# sandbox was asked: four innocent days, two that look like half of a fraud, and the two
# fraud signatures the network is for.
SAMPLE = {
    #              quiet  quiet  big-ticket  abroad-coffee  busy  cash-out  testing  dormant-burst
    "amount_ratio": [0.82, 1.05, 4.30, 0.40, 1.10, 4.85, 0.17, 0.21],
    "foreign_share": [0.00, 0.03, 0.00, 0.78, 0.00, 0.81, 0.00, 0.02],
    "night_share": [0.10, 0.00, 0.05, 0.12, 0.08, 0.06, 0.74, 0.69],
    "velocity_ratio": [0.95, 1.12, 1.05, 0.90, 4.10, 0.70, 4.60, 5.20],
    "tenure_months": [36.0, 84.0, 61.0, 29.0, 47.0, 5.0, 132.0, 140.0],
    "prior_disputes": [0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 2.0],
}

# Why a label that is 45 days late is not leakage, written where a reviewer will read it.
TARGET_JUSTIFICATION = (
    "The target fraud_confirmed is a forward-looking outcome: whether the disputes team "
    "later confirmed fraud on that card-day, which cannot be known until the chargeback "
    "window has closed 45 days afterwards. Its knowledge time is necessarily later than "
    "its event date, and it is never an input at scoring time — the network takes the four "
    "activity drivers, known the next morning, and the two profile drivers, carried as-of "
    "from the last delivered month-end file. The exception covers the target column alone; "
    "any driver known late would be leakage, and for a model nobody can read, a leaked "
    "driver would never be found by inspection."
)

# ---------------------------------------------------------------------------------
# Feature definitions. Written out rather than inferred, because the definition is the
# governed object: the index, the types, where knowledge time comes from, and what must
# be true of the values. For an unreadable model these checks matter more, not less:
# they are the only place anybody states what the numbers going in are allowed to be.
# ---------------------------------------------------------------------------------
ACTIVITY_DEF = {
    "index": ["date", "card"],
    "index_types": {"date": "date", "card": "string"},
    "schema": [
        {"name": "amount_ratio", "type": "float64"},
        {"name": "foreign_share", "type": "float64"},
        {"name": "night_share", "type": "float64"},
        {"name": "velocity_ratio", "type": "float64"},
        {"name": "auth_count", "type": "int64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "amount_ratio"},
        {"check": "range", "attr": "amount_ratio", "min": 0.0, "max": 100.0},
        {"check": "range", "attr": "foreign_share", "min": 0.0, "max": 1.0},
        {"check": "range", "attr": "night_share", "min": 0.0, "max": 1.0},
        {"check": "range", "attr": "velocity_ratio", "min": 0.0, "max": 50.0},
    ],
}

PROFILE_DEF = {
    "index": ["date", "card"],
    "index_types": {"date": "date", "card": "string"},
    "schema": [
        {"name": "tenure_months", "type": "int64"},
        {"name": "prior_disputes", "type": "int64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "tenure_months"},
        {"check": "range", "attr": "tenure_months", "min": 0, "max": 600},
    ],
}

OUTCOME_DEF = {
    "index": ["date", "card"],
    "index_types": {"date": "date", "card": "string"},
    "schema": [{"name": "fraud_confirmed", "type": "int64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "fraud_confirmed"}],
}

DEFINITIONS = {
    "card_day_activity": ACTIVITY_DEF,
    "card_profile": PROFILE_DEF,
    "fraud_confirmed": OUTCOME_DEF,
}

# The panel: the daily activity drivers, the month-end profile carried as-of rather than
# resampled, and the outcome. ``auth_count`` is deliberately not a member: the model's
# contract does not name it, and a panel that carries what the model does not use invites
# somebody to start using it.
PANEL_DEF = {
    "index": ["date", "card"],
    "alignment": {"mode": "asof", "tolerance_days": 45},
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/{feature}@v1", "source_attr": attr}
        for attr, feature in (
            ("amount_ratio", "card_day_activity"),
            ("foreign_share", "card_day_activity"),
            ("night_share", "card_day_activity"),
            ("velocity_ratio", "card_day_activity"),
            ("tenure_months", "card_profile"),
            ("prior_disputes", "card_profile"),
            ("fraud_confirmed", "fraud_confirmed"),
        )
    ],
}

SECTIONS = {
    "Purpose": (
        "Rank card-days by the probability that the disputes team will later confirm fraud "
        "on them, so that a fixed-capacity review queue looks at the right ones first. The "
        "score is used for triage only: no account is blocked, closed or repriced on it."
    ),
    "Scope and Limitations": (
        "Card-not-present and card-present authorisation activity on active personal debit "
        "and credit cards, domestic issuance, scored daily on the previous day's activity. "
        "Out of scope: commercial cards, cards under 30 days old whose profile file has not "
        "yet arrived, and any account already in a fraud investigation. The model is not a "
        "loss model and its output is not a calibrated probability for accounting purposes. "
        "It gives no reason codes, so it must not be the sole basis of a decision "
        "communicated to a customer."
    ),
    "Mathematical Formulation": (
        "There is none to state, and that is the point of this section. The model is a "
        "declared black box: a feed-forward neural network with layer widths "
        "$6 \\to 12 \\to 8 \\to 1$, $\\tanh$ on both hidden layers and a logistic output, "
        "209 fitted values. Writing the composed map out as an expression would produce "
        "something no reviewer could check, so what is declared instead is everything that "
        "determines it: the architecture above; the loss (Bernoulli negative "
        "log-likelihood, unweighted); the optimiser (mini-batch gradient descent, no "
        "momentum, no penalty) with learning rate 0.15 and batch size 256; He-normal "
        "initialisation with zero biases; a fixed 80 epochs and no early stopping; the "
        "standardisation of each driver by the training partition's own mean and standard "
        "deviation, carried in the parameter set as x\\_mean and x\\_scale; and the seed, "
        "7, from which the initialisation and the batch order are both drawn. Those are "
        "the reviewable facts. The weights themselves are reviewable only as a "
        "content-hashed, approved parameter set."
    ),
    "Assumptions": (
        "That a card's own recent history is a fair baseline for what is unusual on it, "
        "since every activity driver is a ratio to that baseline; that the confirmed-fraud "
        "label is a decision of the disputes team and not ground truth, so the model learns "
        "what that team confirms; that the two fraud patterns present in the fitting window "
        "(a large authorisation abroad, and a burst of micro-authorisations) are the ones "
        "that will still be present when it runs; and that the month-end profile file "
        "carried as-of is a fair view of tenure and dispute history on the day scored."
    ),
    "Data and Features Used": (
        "Feature set card_fraud/fraud_panel, pinned point-in-time. Four drivers from the "
        "daily authorisation summary, cut one day after the day they describe: the largest "
        "authorisation as a ratio to the card's own usual largest, the foreign share, the "
        "night share and the authorisation-count ratio. Two drivers from the month-end "
        "customer profile, delivered ten days after the month and carried forward as-of "
        "with a 45-day tolerance: tenure in months and disputes in the previous twelve "
        "months. The target is the confirmed-fraud flag, whose knowledge time is 45 days "
        "after its event date by construction."
    ),
    "Calibration Methodology": (
        "Mini-batch gradient descent on the training partition only, for the declared fixed "
        "number of epochs, from the declared seed. No hyperparameter was tuned on the "
        "validation partition and no epoch count was chosen by watching it, which is why "
        "the validation figure below is worth quoting at all. The test partition is "
        "escrowed by MAYA and, because the model is a declared black box, MAYA will not "
        "score it — see Validation Evidence."
    ),
    "Validation Evidence": (
        "Discrimination is reported as the area under the ROC curve on the training and "
        "validation partitions, computed by the desk and uploaded with the parameter set "
        "against the checksum of the exact rows MAYA issued. A logistic regression on the "
        "same six drivers, fitted on the same rows, is reported beside it as the challenger; "
        "accepting an unreadable model is only defensible while that gap is real, and the "
        "gap is the justification of record. The escrowed holdout is scored blind by MAYA: "
        "the approved artifact is run in MAYA's sandbox on the holdout's inputs only, never "
        "the target, and MAYA computes the metric on rows the desk never sees -- the same "
        "claim a formula's blind score makes."
    ),
    "Known Weaknesses": (
        "Nobody can read the model. There is no coefficient to sanity-check, no monotonicity "
        "to assert, and no way to tell by inspection whether a driver has leaked; the input "
        "contract, the leakage certificate and the covenants are the whole of the defence. "
        "The parameters are reproducible from the seed and are not otherwise identified: a "
        "different seed gives materially different weights with indistinguishable "
        "performance, so 'the weights' are one arbitrary member of a family. The network "
        "learned two fraud patterns and will not recognise a third; because it cannot "
        "explain itself, that failure will look like silence rather than like an error. The "
        "profile drivers are stale by up to a month, and a card whose first profile file has "
        "not arrived cannot be scored at all."
    ),
    "Change Log": (
        "Version 1: initial network, six drivers, fitted on the 2025-03-01 to 2025-04-14 "
        "window under training warrant card\\_fraud/fraud\\_mlp\\_fit\\_2025q2."
    ),
}


def specification() -> str:
    """The model's specification document: §8.3's nine sections, said properly.

    MAYA refuses to submit a model version whose document is missing a section, so this is
    not decoration — it is the gate. For a black box it is also the only place the model's
    mathematics is stated at all, which is why *Mathematical Formulation* here is a list of
    declarations rather than a formula."""
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in SECTIONS.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        "\\title{Card-day fraud network}\\author{Fraud analytics and model risk}\n"
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


def artifact_source() -> str:
    """``network.py``, as bytes MAYA will hash — the same file the desk imports to fit."""
    return Path(network.__file__).read_text(encoding="utf-8")


LOADS_FROM_DISK = '''
"""The forward pass, with the weights loaded from disk. The usual way, and refused."""

import numpy as np


class Model:
    def fit(self, X, y, ctx):
        return {}

    def predict(self, X, params, ctx):
        weights = np.load(open("/models/fraud_mlp/weights.npz", "rb"))
        matrix = np.column_stack([np.asarray(v, dtype=float) for v in X.values()])
        hidden = np.tanh(matrix @ weights["W1"] + weights["b1"])
        return 1.0 / (1.0 + np.exp(-(hidden @ weights["W3"] + weights["b3"]))).ravel()
'''


class Context:
    """What the desk passes where MAYA's sandbox passes its own run context: a seed.

    MAYA's sandbox constructs this itself (``maya/security/sandbox_runner.py``). The desk
    needs an equivalent to call the same ``fit`` outside MAYA, which is where every fit in
    this study happens (ADR-007)."""

    def __init__(self, seed: int) -> None:
        self.seed = seed


def as_npz(values: dict[str, Any]) -> bytes:
    """The fitted parameters as the ``.npz`` a training run actually leaves behind.

    ``allow_pickle`` is not needed and not used: every value is a float array. This is the
    file the desk would keep, and its sha256 is what the parameter set's notes quote."""
    buffer = io.BytesIO()
    np.savez(buffer, **{name: np.asarray(value, dtype=float) for name, value in values.items()})
    return buffer.getvalue()


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


class Cast:
    """The people in the story, each an SDK client logged in with their own roles.

    Naming them is the point: MAYA has no single "the script" identity, and every refusal
    in this study happens because the person acting is the wrong person to act."""

    def __init__(self, maya: Any) -> None:
        self.dana = maya.client("dana")  # feature designer: writes definitions
        self.mick = maya.client("mick")  # feature manager: approves them, and pins
        self.mona = maya.client("mona")  # model designer: the network and its document
        self.devi = maya.client("devi")  # model developer: draws warrants and fits
        self.mgr = maya.client("mgr")  # model manager: approves models and parameters
        self.owen = maya.client("owen")  # model owner: accountable for it in production
        self.lara = maya.client("lara")  # a second model manager: independent validation
        self.admin = maya.client("admin")


# ---------------------------------------------------------------------------------
# The challenger, and the metric. A logistic regression by iteratively reweighted least
# squares on the same six drivers and the same rows: the only honest justification for
# accepting a model nobody can read is that a model somebody *can* read does worse.
# ---------------------------------------------------------------------------------
def logistic_design(frame: pd.DataFrame) -> np.ndarray:
    """The six drivers plus an intercept, standardised so IRLS is well conditioned."""
    matrix = np.column_stack([frame[name].astype(float).to_numpy() for name in DRIVERS])
    matrix = (matrix - matrix.mean(axis=0)) / matrix.std(axis=0)
    return np.column_stack([np.ones(len(frame)), matrix])


def crafted_design(frame: pd.DataFrame) -> np.ndarray:
    """The same six drivers plus the three conjunctions a fraud analyst would write.

    A large authorisation *and* a foreign acquirer; a night *and* a burst; and the ratio
    that says "many, and tiny". These are the interactions the data was built with, so this
    is the strongest readable challenger there is — and reporting it is the honest way to
    ask what the network is really buying. Nobody knows the true conjunctions in a real
    book; here, someone does."""
    matrix = np.column_stack(
        [
            *[frame[name].astype(float).to_numpy() for name in DRIVERS],
            frame["amount_ratio"].astype(float).to_numpy()
            * frame["foreign_share"].astype(float).to_numpy(),
            frame["night_share"].astype(float).to_numpy()
            * frame["velocity_ratio"].astype(float).to_numpy(),
            frame["velocity_ratio"].astype(float).to_numpy()
            / np.maximum(frame["amount_ratio"].astype(float).to_numpy(), 0.01),
        ]
    )
    matrix = (matrix - matrix.mean(axis=0)) / matrix.std(axis=0)
    return np.column_stack([np.ones(len(frame)), matrix])


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
        raise ValueError("the challenger did not converge to finite coefficients")
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
