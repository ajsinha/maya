"""
What the steps of this case study share: names, feature definitions, three member models,
the composite that multiplies them, four specification documents, and the people.

Nothing here talks to MAYA. Steps find each other's work by name.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NS = "impairment"
DATA = Path(__file__).resolve().parent / "data"
FEEDS = ("exposures", "outcomes")
NEWLINE = b"\n"

PANEL = "ecl_panel"
PIN = "ecl2506"
PD_MODEL = "pd_12m"
LGD_MODEL = "lgd_secured"
EAD_MODEL = "ead_ccf"
COMPOSITE = "ecl_stage_aware"
WARRANT = "ecl_fit_2025h1"
LIVE = "ecl_live"

AS_OF = dt.date(2025, 6, 30)
KNOWN = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
COMPOSITE_REF = f"{NS}/{COMPOSITE}@v1"
CONTACT = "impairment.committee@example.com"
EXTRA_USERS = {"lara": ["model_manager"]}

TARGET = "realisedLoss12"

# ---------------------------------------------------------------------------------
# The three members. Each estimates one factor of the product, each has a shape chosen
# for what its quantity *is*, and each is a model in its own right.
# ---------------------------------------------------------------------------------
PD_FORMULA = """
util = min(drawn / commitment, 1)
ltv = min(drawn / collateral, 2)
z = p0 + pArr*arrears + pUtil*util + pLtv*ltv
pd12 = 1 / (1 + exp(-z))
"""
PD_WEIGHTS = ("p0", "pArr", "pUtil", "pLtv")
PD_ROLES = {
    **{w: "parameter" for w in PD_WEIGHTS},
    **{f: "feature" for f in ("drawn", "commitment", "collateral", "arrears")},
}

LGD_FORMULA = """
cov = min(collateral / max(drawn, 1), 3)
lz = l0 + lCov*cov
lgd = 1 / (1 + exp(-lz))
"""
LGD_WEIGHTS = ("l0", "lCov")
LGD_ROLES = {
    **{w: "parameter" for w in LGD_WEIGHTS},
    **{f: "feature" for f in ("collateral", "drawn")},
}

# The credit conversion factor: the share of the undrawn limit a defaulting borrower is
# assumed to take first. One parameter, and one of the most argued-over numbers in
# impairment, which is exactly why it should be a named approved figure and not a constant
# in somebody's code.
EAD_FORMULA = """
ead = drawn + ccf*(commitment - drawn)
"""
EAD_WEIGHTS = ("ccf",)
EAD_ROLES = {"ccf": "parameter", "drawn": "feature", "commitment": "feature"}

# ---------------------------------------------------------------------------------
# The composite, and the two parameters that belong to the *combiner* rather than to any
# member. This is what makes IFRS 9 different from a plain product of three models: the
# standard's judgement calls — when has credit risk increased significantly, and how much
# more loss does a lifetime horizon imply — live in the combination, and they are the
# numbers an impairment committee actually argues about.
#
#     sicr        = pd12 / pd_at_origination
#     stage       = 2 if sicr > sicrThreshold else 1
#     ecl         = (lifetimeFactor if stage 2 else 1) * pd12 * lgd * ead
#
# Written as an IR node because it refers to member outputs by alias.
# ---------------------------------------------------------------------------------
COMBINE = {
    "op": "mul",
    "args": [
        {
            "op": "where",
            "args": [
                {
                    "op": "gt",
                    "args": [
                        {"op": "div", "args": [{"ref": "pd.pd12"}, {"ref": "pdOrigination"}]},
                        {"param": "sicrThreshold"},
                    ],
                },
                {"param": "lifetimeFactor"},
                {"const": 1},
            ],
        },
        {"ref": "pd.pd12"},
        {"ref": "lgd.lgd"},
        {"ref": "ead.ead"},
    ],
}
COMBINER_WEIGHTS = ("sicrThreshold", "lifetimeFactor")

# What the committee decided, and what each figure means. These are judgements, not fits:
# they are registered as an approved parameter set so that the figures in the accounts are
# figures somebody signed for.
COMMITTEE = {"sicrThreshold": 3.0, "lifetimeFactor": 2.8}
# What the committee settles on after step 7's evidence. Chosen for being a defensible reading
# of "significant", not for making the total come out right — see step 7, which declines to
# pick the threshold that flatters the allowance and says why.
CHOSEN_THRESHOLD = 12.0
COMMITTEE_WHY = (
    "sicrThreshold 3.0: a twelve-month probability of default three times its value at "
    "origination is the committee's threshold for a significant increase in credit risk. "
    "lifetimeFactor 2.8: the ratio of lifetime to twelve-month expected loss on this book's "
    "average remaining life, from the December 2025 lifetime study. Both are judgements of "
    "the impairment committee, minuted, and neither is fitted to anything."
)


def composite_ir() -> dict[str, Any]:
    return {
        "outputs": [{"name": "ecl", "type": "float64"}],
        "inputs": [],  # the union of the members' contracts plus what the combiner reads
        "composite": {
            "kind": "ensemble",
            "members": [
                {"alias": "pd", "ref": f"maya://model/{NS}/{PD_MODEL}@v1"},
                {"alias": "lgd", "ref": f"maya://model/{NS}/{LGD_MODEL}@v1"},
                {"alias": "ead", "ref": f"maya://model/{NS}/{EAD_MODEL}@v1"},
            ],
            "combine": COMBINE,
            "train": {"mode": "parallel", "order": ["pd", "lgd", "ead"]},
        },
    }


TRUE_PD = {"p0": -4.35, "pArr": 0.92, "pUtil": 1.55, "pLtv": 1.10}
TRUE_LGD = {"l0": 0.95, "lCov": -2.60}
TRUE_CCF = 0.55

TARGET_JUSTIFICATION = (
    "The target realisedLoss12 is the money actually lost on the account over the twelve "
    "months following the observation month, so it cannot be known until those twelve months "
    "have passed and its knowledge time is later than its event date by construction. It is "
    "never an input: the composite's contract names the balance, the limit, the collateral, "
    "the arrears and the probability of default at origination, all known three business days "
    "after month end. The exception covers the target column alone."
)

# ---------------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------------
EXPOSURE_DEF = {
    "index": ["date", "account"],
    "index_types": {"date": "date", "account": "string"},
    "schema": [
        {"name": "drawn", "type": "float64"},
        {"name": "commitment", "type": "float64"},
        {"name": "collateral", "type": "float64"},
        {"name": "arrears", "type": "int64"},
        {"name": "pd_origination", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "drawn"},
        {"check": "range", "attr": "arrears", "min": 0, "max": 12},
        # A probability of default at origination outside (0, 1) is not a risky loan, it is a
        # broken record, and the whole stage-allocation test divides by it.
        {"check": "range", "attr": "pd_origination", "min": 0.0001, "max": 1.0},
    ],
}

OUTCOME_DEF = {
    "index": ["date", "account"],
    "index_types": {"date": "date", "account": "string"},
    "schema": [
        {"name": "defaulted12", "type": "int64"},
        {"name": "loss_rate", "type": "float64"},
        {"name": "realised_loss12", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "defaulted12"},
        {"check": "range", "attr": "loss_rate", "min": 0.0, "max": 1.0},
    ],
}

DEFINITIONS = {"exposures": EXPOSURE_DEF, "outcomes": OUTCOME_DEF}

PANEL_DEF = {
    "index": ["date", "account"],
    "members": [
        {"attr": attr, "ref": f"maya://feature/{NS}/{feature}@v1", "source_attr": source}
        for attr, feature, source in (
            ("drawn", "exposures", "drawn"),
            ("commitment", "exposures", "commitment"),
            ("collateral", "exposures", "collateral"),
            ("arrears", "exposures", "arrears"),
            ("pdOrigination", "exposures", "pd_origination"),
            ("defaulted12", "outcomes", "defaulted12"),
            ("lossRate", "outcomes", "loss_rate"),
            ("realisedLoss12", "outcomes", "realised_loss12"),
        )
    ],
}

# ---------------------------------------------------------------------------------
# Four specification documents: one per member and one for the composite. A reviewer
# reading the composite should not have to open three others to learn what it does.
# ---------------------------------------------------------------------------------
PD_SECTIONS = {
    "Purpose": (
        "Estimate the probability that a secured revolving facility defaults within twelve "
        "months of an observation month. It is the first factor of the impairment model "
        "impairment/ecl_stage_aware and is not used on its own."
    ),
    "Scope and Limitations": (
        "Secured revolving facilities in the domestic book, excluding accounts already in "
        "default and accounts in forbearance. It is a point-in-time twelve-month probability, "
        "not a through-the-cycle rating, and it carries no macroeconomic driver, so it cannot "
        "be used to produce the forward-looking scenarios IFRS 9 also requires — those are a "
        "separate overlay with their own governance."
    ),
    "Mathematical Formulation": (
        "A logistic on three drivers. With drawn balance $D$, limit $C$, collateral $V$ and "
        "arrears $a$ in months, let $u = \\min(D/C, 1)$ and $\\ell = \\min(D/V, 2)$. Then "
        "$z = \\pi_0 + \\pi_a a + \\pi_u u + \\pi_\\ell \\ell$ and "
        "$\\mathrm{PD}_{12} = (1 + e^{-z})^{-1}$. Both ratios are capped because beyond the "
        "cap the data contains almost nothing and an uncapped linear term would extrapolate "
        "confidently into it."
    ),
    "Assumptions": (
        "That arrears are reported consistently across servicing systems, which is the "
        "assumption most often false in practice and the one that would move this model most. "
        "That the collateral valuation is current. And that default is conditionally "
        "independent across accounts given the drivers, which understates the variance of a "
        "portfolio loss in a downturn."
    ),
    "Data and Features Used": (
        "Feature set impairment/ecl_panel, pinned point-in-time: drawn balance, limit, "
        "collateral and arrears from the monthly book, cut three business days after month "
        "end. Fitted on the twelve-month default flag, known a year and a day later."
    ),
    "Calibration Methodology": (
        "Iteratively reweighted least squares on the Bernoulli log-likelihood, on the "
        "training partition of the composite's warrant only."
    ),
    "Validation Evidence": (
        "Fitted coefficients against the process that generated this synthetic book, the area "
        "under the ROC curve on training and validation, and — the figure that matters — the "
        "composite's blind score against realised loss, since a probability that ranks well "
        "and is scaled wrongly still produces a wrong provision."
    ),
    "Known Weaknesses": (
        "No macroeconomic driver, so no scenario. The arrears counter saturates at six "
        "months, and an account twelve months in arrears is not twice as risky as one six "
        "months in arrears — it is a different kind of account, and this model cannot say so. "
        "Collateral enters only through the loan-to-value ratio, so a fall in value and a rise "
        "in balance are indistinguishable to it."
    ),
    "Change Log": "Version 1: initial twelve-month probability of default member.",
}

LGD_SECTIONS = {
    "Purpose": (
        "Estimate the share of exposure lost on a secured facility that defaults — the loss "
        "given default. Second factor of impairment/ecl_stage_aware; not used on its own."
    ),
    "Scope and Limitations": (
        "Secured facilities only, and only the economic loss net of recoveries on the "
        "collateral. It says nothing about unsecured exposure, nothing about the time to "
        "recovery, and nothing about the cost of collection, which for a small balance can "
        "exceed the recovery itself."
    ),
    "Mathematical Formulation": (
        "A logistic in collateral coverage. With collateral $V$ and drawn balance $D$, let "
        "$c = \\min(V / \\max(D, 1), 3)$. Then $\\mathrm{LGD} = (1 + e^{-(\\lambda_0 + "
        "\\lambda_c c)})^{-1}$. A logistic because a loss rate is a share and belongs in "
        "$[0, 1]$: a linear form would predict a negative loss on a well-secured account and "
        "a loss above par on a badly secured one, and both are impossible rather than merely "
        "unlikely."
    ),
    "Assumptions": (
        "That coverage measured on the \\emph{current} balance is a fair proxy for coverage at the "
        "moment of default. It is not, and the weakness section says what that costs."
    ),
    "Data and Features Used": (
        "Feature set impairment/ecl_panel, pinned point-in-time: collateral and drawn balance. "
        "Fitted on the realised loss rate of the accounts that actually defaulted, which is a "
        "small fraction of the panel — the sample size is the first thing a reviewer should "
        "ask about."
    ),
    "Calibration Methodology": (
        "Iteratively reweighted least squares on the realised loss rate, treated as a "
        "proportion rather than an event, over the defaulted rows of the training partition."
    ),
    "Validation Evidence": (
        "Fitted coefficients against the generating process, and the composite's blind score."
    ),
    "Known Weaknesses": (
        "Coverage is measured on the balance drawn today, while the loss is realised on the "
        "exposure at default — which the third member says is larger. So this member "
        "\\emph{overstates} coverage, and therefore understates loss, by most on exactly the "
        "accounts with the largest undrawn limits. The honest fix is a coverage input computed "
        "from the exposure-at-default member's output, which would make this a pipeline rather "
        "than a product; it is not done here, and the bias is documented instead of hidden."
    ),
    "Change Log": "Version 1: initial secured loss-given-default member.",
}

EAD_SECTIONS = {
    "Purpose": (
        "Estimate the exposure at default of a revolving facility: the balance drawn today "
        "plus the share of the remaining limit a defaulting borrower is expected to take "
        "first. Third factor of impairment/ecl_stage_aware."
    ),
    "Scope and Limitations": (
        "Revolving facilities with an undrawn limit. For a fully drawn facility it returns "
        "the balance, correctly and trivially. It does not model limit reductions, which a "
        "lender often makes precisely when a borrower is deteriorating, and which would make "
        "this member conservative."
    ),
    "Mathematical Formulation": (
        "$\\mathrm{EAD} = D + \\kappa (C - D)$ for drawn balance $D$, limit $C$ and a credit "
        "conversion factor $\\kappa$. One parameter, and one of the most argued-over numbers "
        "in impairment: it is registered as a named, approved figure rather than living as a "
        "constant in somebody's code."
    ),
    "Assumptions": (
        "That the conversion factor is the same across the book. It is not — it varies with "
        "product, with utilisation and with how close the borrower is to default — and a "
        "single figure is a deliberate simplification whose direction of error is unknown."
    ),
    "Data and Features Used": ("Feature set impairment/ecl_panel: drawn balance and limit."),
    "Calibration Methodology": (
        "Estimated by least squares on the realised exposure of the accounts that defaulted, "
        "over the training partition, and bounded to $[0, 1]$ because a conversion factor "
        "outside that range is not a calibration but an error."
    ),
    "Validation Evidence": (
        "The fitted factor against the one that generated the book, and the composite's blind "
        "score against realised loss."
    ),
    "Known Weaknesses": (
        "One factor for the whole book. No behavioural distinction between a borrower who "
        "draws down deliberately before defaulting and one whose balance grows through "
        "capitalised interest, though the two have very different implications for recovery."
    ),
    "Change Log": "Version 1: initial credit-conversion-factor member.",
}

COMPOSITE_SECTIONS = {
    "Purpose": (
        "Compute the expected credit loss allowance on a book of secured revolving facilities "
        "under IFRS 9: the twelve-month expectation for accounts whose credit risk has not "
        "increased significantly since origination, and the lifetime expectation for those "
        "where it has. The output is an accounting figure that appears in the financial "
        "statements, which is why every judgement in it is a named, approved number."
    ),
    "Scope and Limitations": (
        "Stage 1 and stage 2 only. An account already in default is stage 3 and is measured "
        "individually, not by this model. The forward-looking macroeconomic scenarios IFRS 9 "
        "also requires are a separate overlay with their own governance and are not applied "
        "here. The lifetime measurement is approximated by a multiple of the twelve-month "
        "figure rather than by a term structure of default, which is a simplification the "
        "committee accepted and which the multiple's own study quantifies."
    ),
    "Mathematical Formulation": (
        "The product of three estimates, with a stage-dependent horizon. With "
        "$\\mathrm{PD}_{12}$ from the first member, $\\mathrm{LGD}$ from the second, "
        "$\\mathrm{EAD}$ from the third, and the probability of default at origination "
        "$\\mathrm{PD}_0$, let the significant-increase ratio be "
        "$s = \\mathrm{PD}_{12} / \\mathrm{PD}_0$. Then "
        "$\\mathrm{ECL} = h \\cdot \\mathrm{PD}_{12} \\cdot \\mathrm{LGD} \\cdot "
        "\\mathrm{EAD}$ where $h = \\phi$ if $s > \\theta$ and $h = 1$ otherwise. The "
        "threshold $\\theta$ and the lifetime multiple $\\phi$ are parameters \\textbf{of the "
        "combination}, not of any member: they are the standard's judgement calls and belong "
        "to the impairment committee rather than to a modeller."
    ),
    "Assumptions": (
        "That the three factors are independent enough to multiply. They are not: an account "
        "deteriorating towards default also draws down its limit and is often secured on an "
        "asset falling in value, so the product understates the correlation and therefore the "
        "loss in exactly the conditions where the allowance matters. That the origination "
        "probability on the record is the one that was actually assessed. And that a ratio "
        "test is a sufficient test of significant increase, which is the interpretation this "
        "institution has adopted and disclosed."
    ),
    "Data and Features Used": (
        "Feature set impairment/ecl_panel, pinned point-in-time. The composite's input "
        "contract is the union of its three members' contracts plus the origination "
        "probability its own combiner reads."
    ),
    "Calibration Methodology": (
        "The three members are fitted independently, in parallel, under one training warrant "
        "against one pinned feature set; the warrant will not seal until all three have an "
        "approved parameter set. The combiner's two parameters are not fitted at all: they "
        "are the committee's judgements, registered as an approved parameter set with their "
        "provenance recorded, so a change to either is a new approval rather than an edit."
    ),
    "Validation Evidence": (
        "MAYA scores the composite blind against realised loss on the escrowed partition, in "
        "currency. \\textbf{Read that figure carefully.} Realised loss is zero on more than nine "
        "rows in ten and large on the rest, so a per-account error statistic is dominated by "
        "the variance of a Bernoulli outcome and not by the quality of the expectation. The "
        "meaningful test of an expected-loss model is at portfolio level — does the sum of the "
        "allowance match the sum of the loss — and the study reports that alongside, with the "
        "per-account figure quoted against the naive alternatives so it is read as a "
        "comparison rather than as an accuracy."
    ),
    "Known Weaknesses": (
        "The three factors multiply as if independent when they are positively correlated in "
        "stress, so the allowance is understated in a downturn. The lifetime measurement is a "
        "multiple rather than a term structure. The loss-given-default member measures "
        "coverage on the current balance while loss is realised on the exposure at default, a "
        "bias inherited from that member and largest on the least-drawn accounts. And the "
        "composite is capped at the maturity of its least mature member, so a member's "
        "deprecation is the allowance's problem too."
    ),
    "Change Log": (
        "Version 1: stage-aware product of the twelve-month probability of default, secured "
        "loss given default and credit-conversion-factor exposure members, drawn under "
        "impairment/ecl\\_fit\\_2025h1."
    ),
}


def document(title: str, sections: dict[str, str]) -> str:
    body = "\n".join(f"\\section{{{name}}}\n{text}\n" for name, text in sections.items())
    return (
        "\\documentclass[11pt]{article}\n\\usepackage{amsmath,amssymb}\n"
        f"\\title{{{title}}}\\author{{Impairment and model risk}}\n"
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


def parameter_sets(warrant: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Approved parameter sets by member alias; the combiner's own sit under ''."""
    return {
        (ps.get("member_alias") or ""): dict(ps)
        for ps in warrant.get("parameter_sets", [])
        if ps["state"] == "approved"
    }


# ---------------------------------------------------------------------------------
# The fitting mathematics, one per member.
# ---------------------------------------------------------------------------------
def pd_design(frame: pd.DataFrame) -> np.ndarray:
    drawn = frame["drawn"].astype(float).to_numpy()
    commitment = frame["commitment"].astype(float).to_numpy()
    collateral = frame["collateral"].astype(float).to_numpy()
    return np.column_stack(
        [
            np.ones(len(frame)),
            frame["arrears"].astype(float).to_numpy(),
            np.minimum(drawn / commitment, 1.0),
            np.minimum(drawn / np.maximum(collateral, 1.0), 2.0),
        ]
    )


def lgd_design(frame: pd.DataFrame) -> np.ndarray:
    coverage = frame["collateral"].astype(float).to_numpy() / np.maximum(
        frame["drawn"].astype(float).to_numpy(), 1.0
    )
    return np.column_stack([np.ones(len(frame)), np.minimum(coverage, 3.0)])


def fit_logistic(X: np.ndarray, y: np.ndarray, tol: float = 1e-10, limit: int = 100) -> np.ndarray:
    """IRLS on a Bernoulli mean, which also serves for a proportion in [0, 1]."""
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
        raise ValueError("a member's fit did not converge to finite coefficients")
    return beta


def auc(y: np.ndarray, score: np.ndarray) -> float:
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), dtype=float)
    ranks[order] = np.arange(1, len(score) + 1)
    positives, negatives = float(y.sum()), float((1 - y).sum())
    if not positives or not negatives:
        return float("nan")
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))
