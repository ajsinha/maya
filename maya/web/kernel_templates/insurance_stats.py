"""
Kernel templates: Insurance, transforms and statistics.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.web.kernel_templates._base import _C, _P, _t

TEMPLATES: list[dict[str, Any]] = [
    # ---- insurance -----------------------------------------------------------------------
    _t(
        "pure_premium",
        "Insurance",
        "Pure premium from frequency and severity",
        "The product every general insurance pricing model reduces to, whatever fits the "
        "two halves.",
        r"""
premium = frequency \cdot severity
""",
        {"frequency": "feature", "severity": "feature"},
        "general insurance pricing burning cost expected claims",
    ),
    _t(
        "loss_ratio",
        "Insurance",
        "Loss ratio",
        "Incurred over earned. The definition of the denominator is where the reserving "
        "argument lives.",
        r"""
lr = incurred / earned
""",
        {"incurred": "feature", "earned": "feature"},
        "combined ratio underwriting reserving performance",
    ),
    _t(
        "credibility_weighted",
        "Insurance",
        "A credibility-weighted rate",
        "Bühlmann in its simplest form: your own experience weighted against the book's, by "
        "how much of it you have.",
        r"""
z = n / (n + k)
rate = z\,own + (1 - z) book
""",
        {"k": _P, "own": "feature", "book": "feature"},
        "buhlmann experience rating partial credibility",
    ),
    # ---- transforms and statistics -------------------------------------------------------
    _t(
        "zscore",
        "Transforms and statistics",
        "A z-score",
        "Centre and scale. Worth governing because the centre and the scale are decisions, "
        "and a model that standardises in its fitting script and not in its specification "
        "will be scored on the wrong units.",
        r"""
z = (x - \mu) / \sigma
""",
        {"mu": _C, "sigma": _C},
        "standardise normalise centring scaling",
    ),
    _t(
        "minmax_scale",
        "Transforms and statistics",
        "Min–max scaling to the unit interval",
        "The bounds are constants rather than features: taking them from the batch makes "
        "today's score depend on today's other rows.",
        r"""
s = (x - lo) / (hi - lo)
""",
        {"lo": _C, "hi": _C},
        "normalise rescale unit interval",
    ),
    _t(
        "winsorise",
        "Transforms and statistics",
        "Winsorising to declared bounds",
        "Clipping written as mathematics rather than as a preprocessing step, so that the "
        "bound is part of the governed object and shows up in the specification.",
        r"""
w = \min(\max(x, lo), hi)
""",
        {"lo": _C, "hi": _C},
        "clip outlier trimming cap floor",
    ),
    _t(
        "log_return",
        "Transforms and statistics",
        "A log return",
        "Additive across time, which is why risk models use it and reporting does not.",
        r"""
r = \log(p / p_{prev})
""",
        {"p_prev": "feature"},
        "continuously compounded price relative",
    ),
    _t(
        "logit_link",
        "Transforms and statistics",
        "The logit link, both ways",
        "From a probability to a score and back. Two lines that a great many models are made of.",
        r"""
odds = p / (1 - p)
score = \log(odds)
""",
        None,
        "log odds inverse sigmoid link function",
    ),
    _t(
        "probit",
        "Transforms and statistics",
        "A probit model",
        "The other link. Indistinguishable from a logit in fit and different in the tails, "
        "which is where the capital is.",
        r"""
z = \beta_0 + \beta_1 x_1 + \beta_2 x_2
p = ncdf(z)
""",
        {"beta_0": _P, "beta_1": _P, "beta_2": _P, "x_1": "feature", "x_2": "feature"},
        "normal cdf link binary classification",
    ),
    _t(
        "exponential_decay",
        "Transforms and statistics",
        "An exponential decay weight",
        "The weight itself, not the weighted average: the average is an aggregation and "
        "belongs upstream of the kernel.",
        r"""
w = \lambda^{age}
""",
        {"lambda": _P, "age": "feature"},
        "ewma half life recency weighting",
    ),
    _t(
        "piecewise_linear",
        "Transforms and statistics",
        "A piecewise-linear response with a knee",
        "One knot, written with `where`. The knot is a parameter because somebody chose it.",
        r"""
y = where(x < knot, a x, a\,knot + b (x - knot))
""",
        {"a": _P, "b": _P, "knot": _P},
        "spline hinge segmented broken stick kink",
    ),
    # ---- insurance, continued -------------------------------------------------------------
    _t(
        "chain_ladder",
        "Insurance",
        "Ultimate loss from a development factor",
        "The workhorse of reserving. The factor comes from a triangle, which is an aggregation, "
        "so it arrives here as an input.",
        r"""
ultimate = paid \cdot ldf
""",
        {"paid": "feature", "ldf": "feature"},
        "reserving triangle development claims ibnr actuarial",
    ),
    _t(
        "bornhuetter_ferguson",
        "Insurance",
        "Bornhuetter–Ferguson reserve",
        "Credibility between the experience and the plan: the unreported share of an a-priori "
        "loss. Steadier than chain ladder on immature years, which is exactly when it is used.",
        r"""
ibnr = premium \cdot lr \cdot (1 - 1/ldf)
""",
        {"lr": _P, "premium": "feature", "ldf": "feature"},
        "reserving a priori expected loss ratio immature",
    ),
    _t(
        "reinsurance_layer",
        "Insurance",
        "Recovery from an excess-of-loss layer",
        "Attachment and limit, written as arithmetic. The whole contract is in the two "
        "constants, which is why they belong in the governed object.",
        r"""
recovery = \min(\max(loss - attachment, 0), limit)
""",
        {"attachment": _P, "limit": _P, "loss": "feature"},
        "excess of loss xol treaty cession attachment",
    ),
    _t(
        "scr_two_risks",
        "Insurance",
        "Aggregating two risk modules with a correlation",
        "Solvency II's square-root formula for two modules. The correlation is set by the "
        "standard, so it is a constant a firm may not choose.",
        r"""
scr = \sqrt{a^2 + b^2 + 2\rho a b}
""",
        {"rho": _C, "a": "feature", "b": "feature"},
        "solvency ii standard formula correlation matrix diversification",
    ),
    _t(
        "expense_ratio",
        "Insurance",
        "Expense ratio",
        "Expenses over earned premium; with the loss ratio it makes the combined ratio, and "
        "over a hundred means the underwriting lost money.",
        r"""
er = expenses / earned
""",
        {"expenses": "feature", "earned": "feature"},
        "combined ratio underwriting result acquisition cost",
    ),
    # ---- statistics, continued ------------------------------------------------------------
    _t(
        "log_loss",
        "Transforms and statistics",
        "Log loss for one row",
        "The loss a logistic regression minimises. Per row, because the mean over rows is an "
        "aggregation -- but the row is the thing worth governing.",
        r"""
loss = -(y \log(p) + (1 - y) \log(1 - p))
""",
        {"y": "feature", "p": "feature"},
        "cross entropy deviance binary classification scoring rule",
    ),
    _t(
        "brier_row",
        "Transforms and statistics",
        "Brier score contribution",
        "Squared error on a probability, which makes it a calibration statement rather than a "
        "discrimination one -- the distinction case study 01 insists on.",
        r"""
brier = (p - y)^2
""",
        {"y": "feature", "p": "feature"},
        "calibration scoring rule probability accuracy",
    ),
    _t(
        "gini_from_auc",
        "Transforms and statistics",
        "Gini from AUC",
        "The conversion every credit paper assumes you know. Both measure the same ordering; "
        "only the scale differs.",
        r"""
gini = 2 auc - 1
""",
        {"auc": "feature"},
        "discrimination power somers d accuracy ratio",
    ),
    _t(
        "platt_scaling",
        "Transforms and statistics",
        "Platt scaling of a score to a probability",
        "A logistic fitted on top of a model's score, which is how an uncalibrated ranker "
        "becomes a probability -- and why the ranking can be good while the level is wrong.",
        r"""
p = 1 / (1 + \exp(a \cdot score + b))
""",
        {"a": _P, "b": _P, "score": "feature"},
        "calibration sigmoid post processing probability mapping",
    ),
    _t(
        "softmax_two",
        "Transforms and statistics",
        "Softmax over two scores",
        "The two-class case, which is a logistic in disguise -- worth seeing written out, "
        "because it makes the multi-class generalisation obvious.",
        r"""
p = \exp(a) / (\exp(a) + \exp(b))
""",
        {"a": "feature", "b": "feature"},
        "multinomial normalisation logit neural network output",
    ),
    _t(
        "relu",
        "Transforms and statistics",
        "A rectified linear unit",
        "One line, and the whole of modern deep learning leans on it. Written with max rather "
        "than a condition, which is the same thing and differentiates better.",
        r"""
y = \max(x, 0)
""",
        None,
        "activation neural network hinge piecewise",
    ),
    _t(
        "tanh_activation",
        "Transforms and statistics",
        "A hyperbolic tangent, from exponentials",
        "MAYA's IR has no tanh, and it does not need one: this is the definition, and writing "
        "it out is what makes the model evaluable by the platform rather than by a library.",
        r"""
e = \exp(2 x)
y = (e - 1) / (e + 1)
""",
        None,
        "activation neural network sigmoid squashing",
    ),
    _t(
        "box_cox",
        "Transforms and statistics",
        "A Box–Cox transform",
        "Two cases in one expression, with the logarithm as the limit at zero. The condition "
        "is in the governed object rather than in a preprocessing script.",
        r"""
y = where(\lambda == 0, \log(x), (x^{\lambda} - 1)/\lambda)
""",
        {"lambda": _P},
        "power transform normality variance stabilising skew",
    ),
    _t(
        "interaction_term",
        "Transforms and statistics",
        "A linear model with an interaction",
        "The term that says two drivers matter more together than apart -- which is what "
        "case study 07's network discovers and a logistic has to be told.",
        r"""
y = \beta_0 + \beta_1 x_1 + \beta_2 x_2 + \beta_{12} x_1 x_2
""",
        {
            "beta_0": _P,
            "beta_1": _P,
            "beta_2": _P,
            "beta_12": _P,
            "x_1": "feature",
            "x_2": "feature",
        },
        "crossed feature engineering conjunction moderation",
    ),
]
