"""
Case study 1 — a retail credit PD scorecard, governed end to end.

Run it:  .venv/bin/python case_studies/01-retail-credit-pd-scorecard/run.py [--keep]

The three feeds it ingests are the CSV files in ``data/``, which are committed beside
this script and were written by ``make_data.py``. MAYA reads them as a source driver
would, materialises them into its Delta lake, and everything after that is MAYA's.

What it demonstrates, in the order the script does it: a feature whose values arrive
late and are therefore *known* after the dates they are about; a bureau file on a
different frequency, aligned as-of rather than resampled; an outcome that by
construction can only be known a year after the month it describes; a point-in-time
pin; a logistic model whose mathematics MAYA holds as an expression rather than as
code; a training warrant that refuses to be approved until the forward-looking target
is justified in writing; a fit whose parameters are tied to the exact rows they were
fitted on by checksum; blind scoring against an escrowed holdout; and an execution
warrant with a covenant that suspends the model when its inputs drift.

Everything goes through ``maya.sdk.Client`` as a named user with that user's roles.
Nothing here is a special demo path: it is the SDK, and the refusals are real.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import io
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maya_demo import Narrator, arguments, browse_hint, start  # noqa: E402

NS = "retail_credit"
# The book runs 2023-01 to 2025-06 (make_data.py); the panel is pinned at the last month
# for which every twelve-month outcome is already known.
AS_OF = dt.date(2025, 6, 30)
KNOWN = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)

# The scorecard. Every symbol is declared: the five weights are parameters to be
# fitted, the four drivers are features MAYA must find in the feature set. MAYA holds
# this as an expression tree, so it can be rendered in LaTeX for the document, lifted
# into reference code, and evaluated for blind scoring without executing anybody's
# Python.
# The centring of the bureau score is part of the model, not part of the fitting script:
# it is stated here, in the governed object, so a reader of the model knows the units its
# coefficient is in, and a second implementation cannot silently choose another centre.
FORMULA = """
b = (bureau - 680) / 60
z = intercept + wUtil*utilisation + wDti*dti + wDelinq*delinquencies + wBureau*b
pd12m = 1 / (1 + exp(-z))
"""
WEIGHTS = ("intercept", "wUtil", "wDti", "wDelinq", "wBureau")
DRIVERS = ("utilisation", "dti", "delinquencies", "bureau")
ROLES = {**{w: "parameter" for w in WEIGHTS}, **{d: "feature" for d in DRIVERS}}

# Why a forward-looking target is not leakage, written where a reviewer will read it.
# MAYA's leakage rule is "no row may use a value MAYA could not have known by its event
# date". A 12-month default flag breaks that rule by construction, and the honest answer
# is not to widen the rule but to say why this row is an exception.
TARGET_JUSTIFICATION = (
    "The target default_12m is a forward-looking outcome: whether the account defaulted "
    "in the twelve months after the observation month. Its knowledge time is necessarily "
    "later than its event date, and it is never an input at scoring time — the scorecard "
    "takes the four drivers only, all of which are known at the observation month. The "
    "exception covers the target column alone; any driver known late would be leakage."
)


# ---------------------------------------------------------------------------------
# The feeds, as they sit on disk. Committed CSV, not generated at run time, so a reader
# can open them and see precisely what MAYA was given; make_data.py holds the recipe.
# ---------------------------------------------------------------------------------
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("servicing_monthly", "bureau_file", "default_outcome")


def feed(name: str) -> bytes:
    path = DATA / f"{name}.csv"
    if not path.exists():
        raise SystemExit(
            f"{path} is missing. Write it with:\n"
            f"  .venv/bin/python {Path(__file__).parent.name}/make_data.py"
        )
    return path.read_bytes()


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


def specification() -> str:
    """The model's specification document: §8.3's nine sections, said properly.

    MAYA refuses to submit a model version whose document is missing a section, so this
    is not decoration — it is the gate. What is written here is what a reviewer reads."""
    sections = {
        "Purpose": (
            "Estimate the probability that a revolving retail account defaults within the "
            "twelve months following an observation month, for IFRS 9 stage allocation and "
            "for portfolio-level expected credit loss."
        ),
        "Scope and Limitations": (
            "Revolving unsecured retail accounts with at least six months on book, in the "
            "domestic book only. The scorecard is not calibrated for accounts in "
            "forbearance, for the first six months after origination, or for secured "
            "lending. It is a ranking and calibration instrument, not a stress model: it "
            "carries no macroeconomic driver and must not be used to project defaults "
            "under a scenario."
        ),
        "Mathematical Formulation": (
            "A logistic link on four drivers. With $z = \\beta_0 + \\beta_u u + \\beta_d d + "
            "\\beta_n n + \\beta_b b$ for utilisation $u$, debt-to-income $d$, "
            "twelve-month delinquency count $n$ and centred bureau score "
            "$b = (\\mathrm{score} - 680)/60$, the "
            "estimate is $\\mathrm{PD}_{12} = (1 + e^{-z})^{-1}$. The coefficients are "
            "fitted by iteratively reweighted least squares on the Bernoulli "
            "log-likelihood; no penalty is applied, and the four drivers are retained on "
            "judgement rather than by selection. The centring constants of the bureau score "
            "are fixed by design and are not fitted; they are stated in the model itself so "
            "that the coefficient's units are unambiguous."
        ),
        "Assumptions": (
            "That the twelve-month default definition is stable across the fitting window; "
            "that the log-odds are linear in the four drivers, which the residual plots "
            "support over the central nine deciles and not in the extreme tails; that the "
            "bureau score carried as-of the last delivered file is a fair view of the "
            "borrower at the observation month; and that the book's composition at "
            "scoring time resembles the fitting window, which is what the execution "
            "warrant's covenants monitor."
        ),
        "Data and Features Used": (
            "Feature set retail_credit/pd_panel, pinned point-in-time. Drivers: "
            "utilisation, debt-to-income and the delinquency count from the monthly "
            "servicing extract, which is cut five days after month end; the bureau score "
            "from a quarterly file delivered a fortnight after the quarter it describes, "
            "carried forward as-of with a hundred-day tolerance. The target is the "
            "twelve-month default flag, whose knowledge time is a year after its event "
            "date by construction."
        ),
        "Calibration Methodology": (
            "Iteratively reweighted least squares to convergence at a relative "
            "log-likelihood change below $10^{-9}$, on the training partition only. The "
            "validation partition is used to check the fit did not diverge; the test "
            "partition is escrowed by MAYA and is scored blind, once per candidate "
            "parameter set, and every attempt is counted on the warrant."
        ),
        "Validation Evidence": (
            "Discrimination is reported as the area under the ROC curve on the training "
            "and validation partitions. Calibration is the quantity MAYA's blind scoring "
            "returns: on a zero-one target the root mean squared error is the square root "
            "of the Brier score, so the holdout figure is a calibration statement about "
            "unseen rows and not a discrimination one."
        ),
        "Known Weaknesses": (
            "No macroeconomic driver, so the scorecard cannot answer a scenario question. "
            "The bureau score is stale by up to a quarter, which flatters it in a fast "
            "deterioration. The linear log-odds assumption fails in the tails, where the "
            "model under-predicts. Accounts in forbearance are out of scope and are not "
            "detected by the model itself; the calling system must exclude them. Accounts "
            "whose first observation months precede the first bureau delivery have no "
            "bureau score at all; those rows are excluded from the fit rather than filled, "
            "and the model has nothing to say about them."
        ),
        "Change Log": (
            "Version 1: initial scorecard, fitted on the 2023-01 to 2025-06 window, "
            "drawn under training warrant retail\\_credit/pd\\_fit\\_2025h1."
        ),
    }
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in sections.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath}\n"
        "\\title{Retail revolving PD scorecard}\\author{Model risk}\n"
        f"\\begin{{document}}\\maketitle\n{body}\n\\end{{document}}\n"
    )


# ---------------------------------------------------------------------------------
# The fit. Iteratively reweighted least squares, in numpy, so the study needs nothing
# beyond what MAYA already installs. What matters for the demonstration is not the
# optimiser but that the fit sees the training partition and nothing else.
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


class Cast:
    """The people in the story, each an SDK client logged in with their own roles.

    Naming them is the point: MAYA has no single "the script" identity, and every
    refusal below happens because the person acting is the wrong person to act."""

    def __init__(self, maya: Any) -> None:
        self.dana = maya.client("dana")  # feature designer: writes definitions
        self.mick = maya.client("mick")  # feature manager: approves them, and pins
        self.mona = maya.client("mona")  # model designer: the model and its document
        self.devi = maya.client("devi")  # model developer: draws warrants and fits
        self.mgr = maya.client("mgr")  # model manager: approves models and parameters
        self.owen = maya.client("owen")  # model owner: accountable for it in production
        self.lara = maya.client("lara")  # a second model manager: independent validation
        self.admin = maya.client("admin")


def ingest(cast: Cast, n: Narrator) -> None:
    """Read the three feeds from data/, define them, and have someone else approve them."""
    from maya.core.errors import NotApproved, PermissionDenied

    n.step("Reading the three feeds from data/, as they were delivered")
    raw = {name: feed(name) for name in FEEDS}
    for name, body in raw.items():
        n.fact(name, f"{body.count(b'\n') - 1:,} rows, {len(body) / 1e6:.1f} MB")
    outcome = pd.read_csv(io.BytesIO(raw["default_outcome"]))
    n.fact("default rate in the book", f"{outcome['default_12m'].mean():.2%}")

    n.step("Three features, defined then approved by someone other than their author")
    for name, definition in (
        ("servicing_monthly", SERVICING_DEF),
        ("bureau_file", BUREAU_DEF),
        ("default_outcome", OUTCOME_DEF),
    ):
        cast.dana.features.create(NS, name, definition)
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        n.say(f"{name}: defined and submitted by dana, and now in MAYA's lake")
    try:
        cast.dana.features.transition(f"{NS}/servicing_monthly", 1, "approve")
    except (PermissionDenied, NotApproved) as exc:
        n.refused("dana approving her own feature", exc)
    for name in FEEDS:
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
    n.say("all three approved by mick, the feature manager")


def panel(maya: Any, cast: Cast, n: Narrator) -> str:
    """Compose the three features into one panel and pin it point-in-time."""
    from maya.core.errors import MayaError

    n.step("A panel: monthly drivers, a quarterly bureau score carried as-of, the outcome")
    definition = {
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
    cast.devi.featuresets.create(NS, "pd_panel", definition)
    cast.devi.featuresets.transition(f"{NS}/pd_panel", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/pd_panel", 1, "approve")
    n.say("pd_panel approved; the bureau score is aligned as-of, never resampled")

    n.step("Pinning it point-in-time: one immutable, content-hashed set of rows")
    pinned = cast.mick.featuresets.pin(
        f"{NS}/pd_panel", 1, "fit2025h1", str(AS_OF), cascade=True, as_of_known=KNOWN.isoformat()
    )
    maya.drain()
    job = cast.mick.jobs.get(pinned["job"]["id"])
    if job["state"] != "succeeded":
        raise MayaError(f"pinning {job['state']}: {job.get('error')}")
    ref = f"maya://featureset/{NS}/pd_panel#fit2025h1/{AS_OF}"
    n.fact("pin", ref)
    n.fact("knowledge time", KNOWN.date())
    return ref


def register_model(cast: Cast, n: Narrator) -> None:
    """The scorecard as an expression, with the document MAYA will not let it skip."""
    from maya.core.errors import NotApproved

    n.step("The scorecard as mathematics, with a document a reviewer can hold")
    cast.mona.models.create(NS, "pd_scorecard", formula=FORMULA, roles=ROLES)
    try:
        cast.mona.models.transition(f"{NS}/pd_scorecard", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting the model before its document is complete", exc)
    cast.mona.models.update_draft(f"{NS}/pd_scorecard", spec_latex=specification())
    cast.mona.models.transition(f"{NS}/pd_scorecard", 1, "submit")
    cast.mgr.models.transition(f"{NS}/pd_scorecard", 1, "approve")
    version = cast.mgr.models.get(f"{NS}/pd_scorecard")["versions"][0]
    n.fact("model", f"{NS}/pd_scorecard v1, {version['state']}")
    n.fact("input contract", ", ".join(c["name"] for c in version["input_contract"]))


def draw_warrant(cast: Cast, pin_ref: str, n: Narrator) -> Any:
    """Two warrants: one refused for unexplained leakage, one that states the reason."""
    from maya.core.errors import NotApproved

    n.step("A training warrant, refused until the forward-looking target is justified")
    naive = cast.devi.training.create(
        NS,
        "pd_fit_naive",
        f"{NS}/pd_scorecard@v1",
        pin_ref,
        spec={"target": "default_12m"},
    )
    n.fact("certificate without a reason", naive["leakage_certificate"]["status"])
    n.fact("violating rows", f"{naive['leakage_certificate']['violations']:,}")
    try:
        cast.devi.training.transition(naive["id"], "submit")
    except NotApproved as exc:
        n.refused("submitting a warrant whose leakage certificate was refused", exc)

    drawn = cast.devi.training.create(
        NS,
        "pd_fit_2025h1",
        f"{NS}/pd_scorecard@v1",
        pin_ref,
        spec={
            "target": "default_12m",
            "objective": "twelve-month PD for IFRS 9 stage allocation",
            "metrics": ["rmse", "mae"],
            "seed": 11,
            "leakage_justification": TARGET_JUSTIFICATION,
        },
    )
    n.fact("certificate with the reason", drawn["leakage_certificate"]["status"])
    report = drawn["contract_report"]
    n.fact("contract satisfied", f"{report['ok']}; {report['mapping']}")
    return drawn


def fit(cast: Cast, drawn: Any, n: Narrator) -> tuple[dict[str, float], str, dict[str, float]]:
    """Fit on the training partition, and report what the developer could see."""
    n.step("Fitting on the training partition, which is the only partition handed over")
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        frame = ds.frame
        checksum = ds.checksum
        n.fact("rows handed to the developer", f"{len(frame):,}")
        n.fact("partitions present", ", ".join(sorted(frame["_split"].unique())))
        n.fact("target among the inputs", ds.target in ds.X.columns)
        # The bureau file is quarterly and delivered late, so the earliest observation
        # months of the panel have no bureau score to carry forward yet. MAYA leaves that
        # gap visible rather than inventing a value, which is the right behaviour and puts
        # the decision here, in the open: this fit uses complete cases and says how many
        # rows that cost.
        needed = [*DRIVERS, "default_12m"]
        complete = frame.dropna(subset=needed)
        n.fact(
            "rows with no bureau score yet",
            f"{len(frame) - len(complete):,} of {len(frame):,}, excluded from the fit",
        )
        train = complete[complete["_split"] == "train"]
        validation = complete[complete["_split"] == "validation"]
        design = design_matrix(train)
        beta = fit_logistic(design, train["default_12m"].astype(float).to_numpy())
        values = dict(zip(WEIGHTS, (round(float(b), 6) for b in beta)))
        vdesign = design_matrix(validation)
        metrics = {
            "auc_train": round(auc(train["default_12m"].to_numpy(), design @ beta), 4),
            "auc_validation": round(auc(validation["default_12m"].to_numpy(), vdesign @ beta), 4),
        }
    n.fact("coefficients", ", ".join(f"{k}={v:+.3f}" for k, v in values.items()))
    n.fact("AUC (train / validation)", f"{metrics['auc_train']} / {metrics['auc_validation']}")
    return values, checksum, metrics


def approve_parameters(
    cast: Cast,
    drawn: Any,
    values: dict[str, float],
    checksum: str,
    metrics: dict[str, float],
    n: Narrator,
) -> str:
    """Upload the fit twice: once untied to the data, once tied, and see the difference."""
    from maya.core.errors import NotApproved

    n.step("Uploading the parameters, tied to the rows they were fitted on")
    warrant = cast.devi.warrant(drawn["id"])
    untied = warrant.upload_parameters(values, data_checksum="0" * 64)
    n.fact("a set quoting the wrong checksum", untied["flag"])
    cast.devi.training.parameter_transition(untied["id"], "submit")
    try:
        cast.mgr.training.parameter_transition(untied["id"], "approve")
    except NotApproved as exc:
        n.refused("approving parameters not tied to the warrant's data", exc)
    tied = warrant.upload_parameters(values, data_checksum=checksum, metrics=metrics)
    n.fact("the set quoting the right one", f"verified_data={tied['verified_data']}")
    cast.devi.training.parameter_transition(tied["id"], "submit")
    cast.mgr.training.parameter_transition(tied["id"], "approve")

    n.step("Blind scoring against the escrowed holdout, counted on the warrant")
    scored = warrant.score_holdout(parameter_set_id=tied["id"])
    n.fact("holdout rows", f"{scored['metrics']['rows']:,}")
    n.fact("RMSE (= root Brier score)", f"{scored['metrics']['rmse']:.4f}")
    n.fact("attempt", scored["attempt"])
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    n.fact("warrant sealed at", cast.mgr.training.seal(drawn["id"])["sealed_at"])
    return str(tied["id"])


def go_live(cast: Cast, drawn: Any, parameter_set: str, n: Narrator) -> None:
    """An execution warrant, a covenant breach, a suspension, and a reinstatement."""
    from maya.core.errors import MayaError

    n.step("An execution warrant: where it may run, who owns it, what suspends it")
    ew = cast.mgr.execution.create(
        NS,
        "pd_scorecard_live",
        training_warrant_id=drawn["id"],
        parameter_set_id=parameter_set,
        spec={
            "environments": ["dev", "prod"],
            "contact": "retail.credit.risk@example.com",
            "covenants": [
                {"kind": "input_null_rate", "attr": "bureau", "max": 0.05},
                # No baseline is given: MAYA takes it from this warrant's own training
                # data and fixes it at creation, so "drift" is measured against the
                # distribution the model was actually fitted on.
                {"kind": "input_psi", "attr": "utilisation", "max": 0.25},
            ],
        },
    )
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")  # not mgr: she submitted it
    cast.mgr.execution.seal(ew["id"])
    live = cast.devi.execution.bundle(ew["id"], "prod")
    n.fact("bundle", f"{live['status']}, {live['attestation']}")

    n.step("A covenant breach suspends it, and says who to call")
    breach = cast.devi.execution.report(
        ew["id"], environment="prod", rows=25_000, input_stats={"bureau": {"null_rate": 0.31}}
    )
    n.fact("after a 31% null bureau score", breach["status"])
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("serving the model while it is suspended", exc)
    cast.admin.execution.reinstate(
        ew["id"], "bureau file arrived late; the feed is confirmed restored"
    )
    n.fact("after reinstatement", cast.devi.execution.bundle(ew["id"], "prod")["status"])


def main() -> int:
    args = arguments(__doc__ or "")
    n = Narrator("Case study 1 — retail credit PD scorecard (banking, fitted)", args.quiet)
    # A second model manager, because the execution-warrant policy asks for a model
    # manager's approval and the one who submitted it cannot also give it.
    maya = start(NS, keep=args.keep, extra_users={"lara": ["model_manager"]})
    try:
        cast = Cast(maya)
        ingest(cast, n)
        pin_ref = panel(maya, cast, n)
        register_model(cast, n)
        drawn = draw_warrant(cast, pin_ref, n)
        values, checksum, metrics = fit(cast, drawn, n)
        parameter_set = approve_parameters(cast, drawn, values, checksum, metrics, n)
        go_live(cast, drawn, parameter_set, n)

        n.step("What the estate now holds, and what an auditor can read")
        for kind in ("feature", "featureset", "model"):
            n.fact(f"{kind}s in the catalog", len(cast.mick.catalog.browse(type=kind)))
        chain = cast.admin.admin.verify_audit()
        n.fact("audit chain", f"{chain['checked']:,} entries, unbroken={chain['ok']}")
        n.fact("custody events on the warrant", len(cast.mgr.training.get(drawn["id"])["custody"]))
        # Lineage edges name the *version*: "the panel" is not a thing data flowed into,
        # version 1 of it is.
        graph = cast.mgr.access.lineage(f"maya://featureset/{NS}/pd_panel@v1")
        n.fact(
            "lineage around the panel",
            f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges",
        )
        browse_hint(maya, n)
        n.done()
        return 0
    finally:
        maya.close()


if __name__ == "__main__":
    sys.exit(main())
