"""
Kernel templates: Market risk, valuation, climate and conduct.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.web.kernel_templates._base import _C, _P, _t

TEMPLATES: list[dict[str, Any]] = [
    # ---- market risk and portfolio -------------------------------------------------------
    _t(
        "var_normal",
        "Market risk",
        "Parametric value at risk",
        "Normal, one horizon, one confidence. The volatility is an input rather than a "
        "step, because computing it aggregates over rows; the quantile is computed from "
        "the confidence, which is a constant chosen with the policy.",
        r"""
var = -(\mu + \sigma N^{-1}(1 - c)) V
""",
        {"c": _C, "mu": "feature", "sigma": "feature", "V": "feature"},
        "value at risk parametric variance covariance confidence",
    ),
    _t(
        "expected_shortfall_normal",
        "Market risk",
        "Expected shortfall under normality",
        "The tail mean rather than the tail quantile. Note the density where the VaR has a "
        "distribution: that is the whole difference.",
        r"""
z = N^{-1}(c)
es = \left(-\mu + \sigma \frac{npdf(z)}{1 - c}\right) V
""",
        {"c": _C, "mu": "feature", "sigma": "feature", "V": "feature"},
        "cvar tail risk frtb coherent",
    ),
    _t(
        "portfolio_vol_two",
        "Market risk",
        "Volatility of a two-asset portfolio",
        "The correlation term is the point: it is what makes the whole less than the sum "
        "and what a diversification benefit is.",
        r"""
v = \sqrt{w_1^2\sigma_1^2 + w_2^2\sigma_2^2 + 2 w_1 w_2 \rho \sigma_1 \sigma_2}
""",
        {"rho": _P, "w_1": "feature", "w_2": "feature", "sigma_1": "feature", "sigma_2": "feature"},
        "diversification correlation covariance allocation",
    ),
    _t(
        "sharpe_ratio",
        "Market risk",
        "Sharpe ratio",
        "Excess return over volatility, both supplied as inputs: each is an average over a "
        "window, and an average over rows is not something a row-wise kernel computes.",
        r"""
sharpe = (r_p - r_f) / \sigma_p
""",
        {"r_f": _P, "r_p": "feature", "sigma_p": "feature"},
        "risk adjusted return information ratio performance",
    ),
    _t(
        "capm_expected_return",
        "Market risk",
        "CAPM expected return",
        "One beta, one premium. Forty years of argument about whether it holds, and it is "
        "still the line every discount rate starts from.",
        r"""
e = r_f + \beta (r_m - r_f)
""",
        {"r_f": _P, "beta": "feature", "r_m": "feature"},
        "cost of equity beta market premium",
    ),
    _t(
        "tracking_error_contrib",
        "Market risk",
        "Active weight contribution to tracking error",
        "A per-row contribution rather than the portfolio figure: the sum is the "
        "aggregation, and it belongs upstream.",
        r"""
contrib = (w - w_b) \beta \sigma_m
""",
        {"sigma_m": "feature", "beta": "feature", "w_b": "feature"},
        "active risk benchmark relative index",
    ),
    _t(
        "cornish_fisher_var",
        "Market risk",
        "Cornish–Fisher value at risk",
        "A skew and kurtosis correction to the normal quantile. Worth having when the "
        "normal assumption is visibly wrong and a full simulation is not affordable.",
        r"""
z = N^{-1}(1 - c)
adj = z + (z^2 - 1) S / 6 + (z^3 - 3 z)(K - 3) / 24 - (2 z^3 - 5 z) S^2 / 36
var = -(\mu + \sigma\,adj) V
""",
        {"c": _C, "mu": "feature", "sigma": "feature", "V": "feature"},
        "skewness kurtosis non normal tail expansion",
    ),
    # ---- valuation and corporate ---------------------------------------------------------
    _t(
        "gordon_growth",
        "Valuation",
        "Gordon growth, a perpetuity with growth",
        "One line whose whole behaviour is in the denominator: as growth approaches the "
        "discount rate the value goes to infinity, which is a statement about the model "
        "rather than about the company.",
        r"""
value = d_1 / (r - g)
""",
        {"r": _P, "g": _P, "d_1": "feature"},
        "dividend discount terminal value perpetuity",
    ),
    _t(
        "wacc",
        "Valuation",
        "Weighted average cost of capital",
        "The tax shield is the only subtle term, and it is where the arguments are.",
        r"""
wacc = w_e r_e + w_d r_d (1 - t)
""",
        {"t": _P, "w_e": "feature", "r_e": "feature", "w_d": "feature", "r_d": "feature"},
        "discount rate hurdle cost of debt equity tax shield",
    ),
    _t(
        "dcf_single",
        "Valuation",
        "One discounted cash flow",
        "The atom every valuation is assembled from. Governing it once means the assembly "
        "is the only thing left to argue about.",
        r"""
pv = cf / (1 + r)^t
""",
        {"r": _P, "cf": "feature"},
        "present value discounting net present value",
    ),
    _t(
        "fx_forward",
        "Valuation",
        "An FX forward by covered interest parity",
        "An arbitrage relation rather than a forecast, which is why it is a pricer and not "
        "a model of anything.",
        r"""
f = s \frac{1 + r_q t}{1 + r_b t}
""",
        {"r_q": _P, "r_b": _P},
        "covered interest parity points currency carry",
    ),
    # ---- valuation, continued -------------------------------------------------------------
    _t(
        "fcff",
        "Valuation",
        "Free cash flow to the firm",
        "Four line items and a tax rate. The definition varies between houses, which is the "
        "argument for writing it down once where everybody can see it.",
        r"""
fcff = ebit (1 - t) + da - capex - dwc
""",
        {"t": _P, "ebit": "feature", "da": "feature", "capex": "feature", "dwc": "feature"},
        "dcf cash flow unlevered enterprise value",
    ),
    _t(
        "residual_income",
        "Valuation",
        "Residual income",
        "Earnings after a charge for the equity used. It is the accounting form of economic "
        "profit, and the charge is where the cost of capital enters.",
        r"""
ri = earnings - charge \cdot equity
""",
        {"charge": _P, "earnings": "feature", "equity": "feature"},
        "economic profit eva abnormal earnings",
    ),
    _t(
        "implied_growth",
        "Valuation",
        "Growth implied by a price",
        "Gordon growth inverted. Worth computing before an argument about growth assumptions: "
        "it says what the market is already assuming.",
        r"""
g = r - d_1 / price
""",
        {"r": _P, "d_1": "feature", "price": "feature"},
        "reverse dcf market implied expectation dividend",
    ),
    _t(
        "ev_ebitda",
        "Valuation",
        "Enterprise value to EBITDA",
        "The multiple quoted most often and defined least consistently -- what goes into "
        "enterprise value is the argument.",
        r"""
multiple = ev / ebitda
""",
        {"ev": "feature", "ebitda": "feature"},
        "comparable multiple trading comps relative valuation",
    ),
    # ---- climate and conduct --------------------------------------------------------------
    _t(
        "carbon_intensity",
        "Climate and conduct",
        "Carbon intensity of revenue",
        "Emissions per unit of revenue, which is how a portfolio target is usually written -- "
        "and why a target can be met by the denominator moving.",
        r"""
intensity = emissions / revenue
""",
        {"emissions": "feature", "revenue": "feature"},
        "esg scope climate target physical transition",
    ),
    _t(
        "financed_emissions",
        "Climate and conduct",
        "Financed emissions by attribution",
        "The PCAF construction: a lender owns the share of a company's emissions that its "
        "lending is of the company's capital.",
        r"""
attribution = outstanding / (equity + debt)
share = attribution \cdot emissions
""",
        {"outstanding": "feature", "equity": "feature", "debt": "feature", "emissions": "feature"},
        "pcaf scope 3 attribution factor portfolio climate",
    ),
    _t(
        "benford_first_digit",
        "Climate and conduct",
        "Benford's expected frequency for a leading digit",
        "What the leading digits of an unmanipulated set should look like. A deviation is a "
        "question rather than an answer, and treating it as evidence is the usual error.",
        r"""
p = \log(1 + 1/d) / \log(10)
""",
        {"d": "feature"},
        "fraud forensic accounting anomaly first digit law",
    ),
    _t(
        "velocity_ratio",
        "Climate and conduct",
        "Transaction velocity against a baseline",
        "Today's count against the customer's own normal. A ratio rather than a count, because "
        "a threshold on the count catches the busy and misses the compromised.",
        r"""
velocity = count / \max(baseline, 1)
""",
        {"count": "feature", "baseline": "feature"},
        "fraud aml monitoring anomaly card transaction",
    ),
]
