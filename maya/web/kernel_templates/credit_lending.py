"""
Kernel templates: Credit risk, retail lending, counterparty risk, capital and treasury.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.web.kernel_templates._base import _C, _P, _t

TEMPLATES: list[dict[str, Any]] = [
    # ---- credit risk --------------------------------------------------------------------
    _t(
        "logistic_pd",
        "Credit risk",
        "A logistic probability of default",
        "The link function every scorecard ends in. Everything before it is feature "
        "engineering; everything after it is calibration.",
        r"""
z = \beta_0 + \beta_1 utilisation + \beta_2 arrears + \beta_3 ltv
pd = 1 / (1 + \exp(-z))
""",
        {
            "beta_0": _P,
            "beta_1": _P,
            "beta_2": _P,
            "beta_3": _P,
            "utilisation": "feature",
            "arrears": "feature",
            "ltv": "feature",
        },
        "scorecard logit probability of default retail",
    ),
    _t(
        "score_to_pd",
        "Credit risk",
        "A bureau score converted to a probability",
        "Points-to-double-the-odds, the scaling every bureau ships and every model has to "
        "undo before it can use the number.",
        r"""
odds = odds_{ref} 2^{(score - score_{ref})/pdo}
pd = 1 / (1 + odds)
""",
        {"odds_ref": _C, "score_ref": _C, "pdo": _C, "score": "feature", "odds": "feature"},
        "scaling points to double odds fico bureau",
    ),
    _t(
        "expected_loss",
        "Credit risk",
        "Expected loss, the product of three estimates",
        "Three models in one line. The assumption that they multiply is an independence "
        "assumption, and it is the one that fails when it matters.",
        r"""
el = pd \cdot lgd \cdot ead
""",
        {"pd": "feature", "lgd": "feature", "ead": "feature"},
        "ifrs9 provision impairment allowance ecl",
    ),
    _t(
        "ifrs9_ecl_stage",
        "Credit risk",
        "IFRS 9 expected credit loss with a stage test",
        "The twelve-month figure, lifted to a lifetime multiple when the ratio of current "
        "to origination default probability crosses the threshold. The threshold and the "
        "multiple are committee decisions, so they are parameters.",
        r"""
s = pd_{12} / pd_{0}
h = where(s > \theta, \phi, 1)
ecl = h \cdot pd_{12} \cdot lgd \cdot ead
""",
        {
            "theta": _P,
            "phi": _P,
            "pd_12": "feature",
            "pd_0": "feature",
            "lgd": "feature",
            "ead": "feature",
        },
        "significant increase sicr lifetime stage 2 impairment",
    ),
    _t(
        "basel_irb_corporate",
        "Credit risk",
        "Basel IRB capital for a corporate exposure",
        "Prescribed by regulation rather than fitted, so it is a model with no dials at all: "
        "what has to be evidenced is that the implementation computes what the text says. "
        "N^{-1} is the normal quantile, not a reciprocal: the parser reads the superscript "
        "as the inverse function, and 0.999 is the confidence the rule fixes.",
        r"""
R = 0.12 \frac{1 - \exp(-50 pd)}{1 - \exp(-50)} + 0.24 \left(1 - \frac{1 - \exp(-50 pd)}{1 - \exp(-50)}\right)
b = (0.11852 - 0.05478 \log(pd))^2
mat = (1 + (M - 2.5) b) / (1 - 1.5 b)
cond = ncdf((N^{-1}(pd) + \sqrt{R} N^{-1}(0.999)) / \sqrt{1 - R})
k = (lgd \cdot cond - pd \cdot lgd) \cdot mat
""",
        {"pd": "feature", "lgd": "feature", "M": "feature"},
        "regulatory capital rwa asset correlation maturity adjustment",
    ),
    _t(
        "merton_dd",
        "Credit risk",
        "Merton distance to default",
        "Equity as a call on the firm's assets. The distance is in standard deviations, and "
        "the probability is the tail beyond it.",
        r"""
dd = (\log(V/D) + (\mu - \sigma^2/2)T) / (\sigma\sqrt{T})
pd = ncdf(-dd)
""",
        {"sigma": _P, "mu": _P},
        "structural model firm value kmv equity",
    ),
    _t(
        "hazard_from_spread",
        "Credit risk",
        "A hazard rate implied by a credit spread",
        "The credit triangle: spread over one minus recovery. Approximate, universally "
        "used, and worth stating as an approximation.",
        r"""
h = s / (1 - R)
""",
        {"R": _P},
        "cds default intensity recovery credit triangle",
    ),
    _t(
        "survival_probability",
        "Credit risk",
        "Survival probability from a constant hazard",
        "The other half of the credit triangle, and the reason a flat hazard curve gives an "
        "exponentially decaying survival.",
        r"""
q = \exp(-h t)
""",
        None,
        "default probability term structure intensity",
    ),
    _t(
        "altman_z",
        "Credit risk",
        "Altman Z-score",
        "Five ratios and five weights from 1968, still quoted. A worked example of an "
        "authored model: the weights were published, not fitted here.",
        r"""
z = 1.2 wc + 1.4 re + 3.3 ebit + 0.6 mve + 1.0 sales
""",
        {
            "wc": "feature",
            "re": "feature",
            "ebit": "feature",
            "mve": "feature",
            "sales": "feature",
        },
        "bankruptcy corporate distress discriminant",
    ),
    _t(
        "ccf_ead",
        "Credit risk",
        "Exposure at default from a conversion factor",
        "Drawn balance plus a fraction of the undrawn commitment. The fraction is the model.",
        r"""
ead = drawn + ccf (commitment - drawn)
""",
        {"ccf": _P, "drawn": "feature", "commitment": "feature"},
        "undrawn limit revolving credit conversion factor",
    ),
    _t(
        "lgd_collateral",
        "Credit risk",
        "Loss given default from collateral coverage",
        "A logistic in coverage, capped. Note the cap is inside the model rather than "
        "applied afterwards, so the scoring and the fit read the same statement.",
        r"""
cov = \min(collateral / \max(drawn, 1), 3)
z = l_0 + l_{cov} cov
lgd = 1 / (1 + \exp(-z))
""",
        {"l_0": _P, "l_cov": _P, "collateral": "feature", "drawn": "feature"},
        "recovery secured haircut coverage",
    ),
    # ---- mortgages and retail lending ----------------------------------------------------
    _t(
        "level_payment",
        "Mortgages and retail",
        "A level mortgage payment",
        "One line, and the whole of it is the order of operations.",
        r"""
payment = balance \cdot r / (1 - (1 + r)^{-n})
""",
        {"r": _P, "balance": "feature", "n": "feature"},
        "amortisation annuity repayment instalment",
    ),
    _t(
        "remaining_balance",
        "Mortgages and retail",
        "The balance remaining after k payments",
        "Derived from the same annuity. A servicing system that computes it differently is "
        "a reconciliation waiting to happen.",
        r"""
balance_k = principal \frac{(1 + r)^n - (1 + r)^k}{(1 + r)^n - 1}
""",
        {"r": _P, "principal": "feature", "n": "feature", "k": "feature"},
        "amortisation schedule payoff outstanding",
    ),
    _t(
        "cpr_to_smm",
        "Mortgages and retail",
        "Single monthly mortality from an annual prepayment rate",
        "The conversion everybody in a securitisation uses and half of them invert.",
        r"""
smm = 1 - (1 - cpr)^{1/12}
""",
        {"cpr": "feature"},
        "prepayment mbs conditional rate securitisation",
    ),
    _t(
        "prepayment_logistic",
        "Mortgages and retail",
        "A prepayment model in rate incentive",
        "The refinancing incentive is the driver that matters; burnout and seasonality are "
        "the two everybody adds next.",
        r"""
inc = coupon - mortgage_{rate}
z = \gamma_0 + \gamma_1 inc + \gamma_2 age
smm = 1 / (1 + \exp(-z))
""",
        {
            "gamma_0": _P,
            "gamma_1": _P,
            "gamma_2": _P,
            "coupon": "feature",
            "mortgage_rate": "feature",
            "age": "feature",
        },
        "refinance incentive burnout seasoning s-curve",
    ),
    _t(
        "ltv",
        "Mortgages and retail",
        "Loan to value",
        "The ratio a credit policy is written in. Trivial, and worth governing because "
        "everybody computes the denominator slightly differently.",
        r"""
ltv = balance / value
""",
        {"balance": "feature", "value": "feature"},
        "collateral property indexed haircut",
    ),
    _t(
        "dscr",
        "Mortgages and retail",
        "Debt service coverage",
        "Income over debt service. A covenant is usually written on this number, which "
        "makes its definition a contractual matter rather than an analytic one.",
        r"""
dscr = noi / debt_{service}
""",
        {"noi": "feature", "debt_service": "feature"},
        "commercial real estate covenant affordability",
    ),
    _t(
        "affordability_pti",
        "Mortgages and retail",
        "Payment to income",
        "The other affordability ratio, and the one regulators cap.",
        r"""
pti = payment \cdot 12 / income
""",
        {"payment": "feature", "income": "feature"},
        "affordability stressed income underwriting",
    ),
    # ---- counterparty and regulatory ------------------------------------------------------
    _t(
        "saccr_ead",
        "Credit risk",
        "Exposure at default under SA-CCR",
        "Replacement cost plus potential future exposure, times a supervisory alpha of 1.4. "
        "Prescribed, so the model has no dials and the evidence is a test against the text.",
        r"""
ead = 1.4 (rc + pfe)
""",
        {"rc": "feature", "pfe": "feature"},
        "counterparty derivatives regulatory replacement cost alpha",
    ),
    _t(
        "cva_single",
        "Credit risk",
        "Credit valuation adjustment for one period",
        "The price of the counterparty's default over one interval. Summing the intervals is "
        "an aggregation and belongs upstream; this is the term being summed.",
        r"""
cva = lgd \cdot ee \cdot pd_{marginal} \cdot df
""",
        {"lgd": _P, "ee": "feature", "pd_marginal": "feature", "df": "feature"},
        "xva counterparty derivative adjustment expected exposure",
    ),
    _t(
        "pfe_point",
        "Credit risk",
        "Potential future exposure at a quantile",
        "The expected exposure plus a multiple of its volatility. The multiple is a parameter "
        "because it encodes the confidence somebody chose.",
        r"""
pfe = \max(ee + q \sigma_e, 0)
""",
        {"q": _P, "ee": "feature", "sigma_e": "feature"},
        "counterparty limit exposure profile quantile",
    ),
    _t(
        "roll_rate",
        "Credit risk",
        "A roll-rate transition",
        "Balance moving from one delinquency bucket to the next. A chain of these is a "
        "transition matrix, which is an aggregation; this is one cell of it.",
        r"""
next = balance \cdot rate
""",
        {"balance": "feature", "rate": "feature"},
        "delinquency bucket flow rate migration collections",
    ),
    _t(
        "vintage_hump",
        "Credit risk",
        "A seasoning curve with a peak",
        "Defaults are rare when a loan is new, peak after a year or two, then decay. The peak "
        "and the width are parameters because a committee argues about them.",
        r"""
d = (age - peak) / width
hazard = height \exp(-d^2)
""",
        {"peak": _P, "width": _P, "height": _P, "age": "feature"},
        "seasoning vintage lifecycle maturation default timing",
    ),
    _t(
        "provision_coverage",
        "Credit risk",
        "Provision coverage ratio",
        "Allowance over non-performing balance. Quoted in every results presentation and "
        "defined slightly differently in each.",
        r"""
coverage = allowance / npl
""",
        {"allowance": "feature", "npl": "feature"},
        "npl ratio impairment stock disclosure",
    ),
    # ---- capital and treasury -------------------------------------------------------------
    _t(
        "cet1_ratio",
        "Capital and treasury",
        "Common equity tier 1 ratio",
        "The ratio the whole capital regime turns on. Both halves are the output of long "
        "calculations, which is why they are inputs here.",
        r"""
cet_1 = capital / rwa
""",
        {"capital": "feature", "rwa": "feature"},
        "basel capital adequacy regulatory ratio buffer",
    ),
    _t(
        "leverage_ratio",
        "Capital and treasury",
        "Leverage ratio",
        "Deliberately not risk-weighted: a backstop to the risk-based ratio, and the one that "
        "binds when the risk weights are flattering.",
        r"""
leverage = tier_1 / exposure
""",
        {"tier_1": "feature", "exposure": "feature"},
        "backstop non risk weighted basel iii supplementary",
    ),
    _t(
        "rwa_density",
        "Capital and treasury",
        "RWA density",
        "Risk-weighted assets over total assets. The number a supervisor compares across banks "
        "when they suspect the models rather than the book.",
        r"""
density = rwa / assets
""",
        {"rwa": "feature", "assets": "feature"},
        "risk weight comparison model risk benchmarking",
    ),
    _t(
        "rorwa",
        "Capital and treasury",
        "Return on risk-weighted assets",
        "Profitability per unit of regulatory capital consumed, which is what a portfolio "
        "decision actually turns on.",
        r"""
rorwa = profit / rwa
""",
        {"profit": "feature", "rwa": "feature"},
        "return capital allocation performance hurdle",
    ),
    _t(
        "lcr",
        "Capital and treasury",
        "Liquidity coverage ratio",
        "High-quality liquid assets against thirty days of stressed outflow. The stress is "
        "prescribed, so the judgement is in the classification rather than the arithmetic.",
        r"""
lcr = hqla / outflows
""",
        {"hqla": "feature", "outflows": "feature"},
        "liquidity basel stress thirty day survival",
    ),
    _t(
        "nsfr",
        "Capital and treasury",
        "Net stable funding ratio",
        "The one-year companion to the LCR: stable funding available against stable funding "
        "required.",
        r"""
nsfr = available / required
""",
        {"available": "feature", "required": "feature"},
        "funding liquidity structural one year basel",
    ),
    _t(
        "deposit_beta",
        "Capital and treasury",
        "Deposit repricing with a beta",
        "How much of a market move a bank passes to depositors. The beta is the single most "
        "argued-over number in a net interest income forecast.",
        r"""
rate = base + \beta (market - base)
""",
        {"beta": _P, "base": "feature", "market": "feature"},
        "nii repricing pass through sensitivity alm",
    ),
    _t(
        "eve_sensitivity",
        "Capital and treasury",
        "Change in economic value of equity",
        "Duration times value times the shock. First order, and the reason a large shock needs "
        "the convexity term the template above it carries.",
        r"""
d_{eve} = -d_{gap} \cdot V \cdot shock
""",
        {"d_gap": "feature", "V": "feature", "shock": _P},
        "irrbb alm interest rate risk banking book",
    ),
]
