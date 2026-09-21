"""
The compute-kernel wizard's library of worked formulae.

Every entry is mathematics somebody in banking or insurance actually writes down, in the
notation they write it in, with each symbol's role declared. They are here to be read and
edited rather than used as they stand: the fastest way to learn what MAYA will accept is to
load something close to your problem and change it.

Two rules hold for every template, and ``tests/test_kernel_templates.py`` enforces both.
Each one parses into a valid formula IR, and each one generates a compute kernel -- so a
template cannot rot into an example that no longer works, which is the failure mode of every
library of samples that is not executed.

A third rule is a consequence of what the IR is. The formula IR is row-wise: one row in, one
row out, no state carried between rows and no aggregation. So a quantity that is an average,
a sum or a recursion over rows is an *input* here rather than a step -- a Sharpe ratio takes
the mean excess return and the volatility as inputs, because computing them is a different
kind of operation that belongs upstream of the model. Where a template does that, its note
says so.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

# Roles reused across many templates, so that a change of mind about one is a change in one
# place. Anything not named in a template's own roles is a feature, which is the right
# default: a feature is a column the bound feature set has to supply.
_P = "parameter"
_C = "constant"


def _t(
    key: str,
    group: str,
    title: str,
    note: str,
    formula: str,
    roles: dict[str, str] | None = None,
    keywords: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "group": group,
        "title": title,
        "note": note,
        "formula": formula.strip("\n"),
        "roles": roles or {},
        # What a search matches on, beyond the title and the group: the words somebody would
        # actually type, including the names practitioners use that are not in the title.
        "keywords": keywords,
    }


TEMPLATES: list[dict[str, Any]] = [
    # ---- options and derivatives --------------------------------------------------------
    _t(
        "bs_call",
        "Options and derivatives",
        "Black–Scholes, a European call",
        "Two intermediates and the normal CDF. The canonical closed form, and the one to "
        "read first: everything MAYA does with a formula is visible in it.",
        r"""
d_1 = (\log(S/K) + (r + \sigma^2/2)T) / (\sigma\sqrt{T})
d_2 = d_1 - \sigma\sqrt{T}
price = S\,ncdf(d_1) - K e^{-rT} ncdf(d_2)
""",
        {"sigma": _P, "r": _P},
        "option call vanilla equity premium",
    ),
    _t(
        "bs_put",
        "Options and derivatives",
        "Black–Scholes, a European put",
        "The same two intermediates, the other side of parity.",
        r"""
d_1 = (\log(S/K) + (r + \sigma^2/2)T) / (\sigma\sqrt{T})
d_2 = d_1 - \sigma\sqrt{T}
price = K e^{-rT} ncdf(-d_2) - S\,ncdf(-d_1)
""",
        {"sigma": _P, "r": _P},
        "option put vanilla equity premium",
    ),
    _t(
        "bs_delta_call",
        "Options and derivatives",
        "Delta of a European call",
        "The first greek, and the one a desk hedges on. Note that it is the same d1.",
        r"""
d_1 = (\log(S/K) + (r + \sigma^2/2)T) / (\sigma\sqrt{T})
delta = ncdf(d_1)
""",
        {"sigma": _P, "r": _P},
        "greek hedge ratio sensitivity",
    ),
    _t(
        "bs_vega",
        "Options and derivatives",
        "Vega of a European option",
        "Same for a call and a put, which is a fact about the formula rather than a "
        "convention: it uses the density rather than the distribution.",
        r"""
d_1 = (\log(S/K) + (r + \sigma^2/2)T) / (\sigma\sqrt{T})
vega = S\sqrt{T}\,npdf(d_1)
""",
        {"sigma": _P, "r": _P},
        "greek volatility sensitivity",
    ),
    _t(
        "bs_gamma",
        "Options and derivatives",
        "Gamma of a European option",
        "The convexity of the hedge. Largest at the money and shortest-dated, which the "
        "formula shows directly.",
        r"""
d_1 = (\log(S/K) + (r + \sigma^2/2)T) / (\sigma\sqrt{T})
gamma = npdf(d_1) / (S\sigma\sqrt{T})
""",
        {"sigma": _P, "r": _P},
        "greek convexity second order",
    ),
    _t(
        "black76",
        "Options and derivatives",
        "Black-76, an option on a future",
        "The forward-measure form: no spot and no carry, because the future already holds "
        "them. Used for caps, floors and swaptions.",
        r"""
d_1 = (\log(F/K) + \sigma^2 T/2) / (\sigma\sqrt{T})
d_2 = d_1 - \sigma\sqrt{T}
price = e^{-rT}(F\,ncdf(d_1) - K\,ncdf(d_2))
""",
        {"sigma": _P, "r": _P},
        "future forward cap floor swaption commodity",
    ),
    _t(
        "garman_kohlhagen",
        "Options and derivatives",
        "Garman–Kohlhagen, an FX call",
        "Black–Scholes with two rates: the foreign rate is a dividend yield by another name.",
        r"""
d_1 = (\log(S/K) + (r_d - r_f + \sigma^2/2)T) / (\sigma\sqrt{T})
d_2 = d_1 - \sigma\sqrt{T}
price = S e^{-r_f T} ncdf(d_1) - K e^{-r_d T} ncdf(d_2)
""",
        {"sigma": _P, "r_d": _P, "r_f": _P},
        "fx currency foreign exchange option",
    ),
    _t(
        "bachelier",
        "Options and derivatives",
        "Bachelier, a normal-model call",
        "Normal rather than lognormal, which is what a market that trades through zero "
        "needs. Rates desks moved to it in 2020 and did not move back.",
        r"""
d = (F - K) / (\sigma\sqrt{T})
price = e^{-rT}\left((F - K) ncdf(d) + \sigma\sqrt{T}\,npdf(d)\right)
""",
        {"sigma": _P, "r": _P},
        "normal model negative rates basis point volatility",
    ),
    _t(
        "digital_call",
        "Options and derivatives",
        "A digital (binary) call",
        "Pays one if it finishes in the money. The discontinuity is in the payoff, not in "
        "the formula, which is why the price is smooth and the hedge is not.",
        r"""
d_2 = (\log(S/K) + (r - \sigma^2/2)T) / (\sigma\sqrt{T})
price = e^{-rT} ncdf(d_2)
""",
        {"sigma": _P, "r": _P},
        "binary cash or nothing exotic",
    ),
    _t(
        "margrabe",
        "Options and derivatives",
        "Margrabe, an option to exchange one asset for another",
        "No strike and no discounting: the option is on a ratio. The volatility is of the "
        "spread, which is where the correlation enters.",
        r"""
\sigma_{x} = \sqrt{\sigma_1^2 + \sigma_2^2 - 2\rho\sigma_1\sigma_2}
d_1 = (\log(S_1/S_2) + \sigma_{x}^2 T/2) / (\sigma_{x}\sqrt{T})
d_2 = d_1 - \sigma_{x}\sqrt{T}
price = S_1 ncdf(d_1) - S_2 ncdf(d_2)
""",
        {
            "sigma_1": _P,
            "sigma_2": _P,
            "rho": _P,
            "sigma_x": _P,
            "S_1": "feature",
            "S_2": "feature",
        },
        "exchange spread correlation two asset",
    ),
    _t(
        "forward_price",
        "Options and derivatives",
        "A forward price with carry",
        "One line, and the whole of it is the cost of carry.",
        r"""
F = S e^{(r - q)T}
""",
        {"r": _P, "q": _P},
        "carry dividend yield futures basis",
    ),
    # ---- rates and curves ---------------------------------------------------------------
    _t(
        "nelson_siegel",
        "Rates and curves",
        "Nelson–Siegel, a yield curve",
        "Three factors and a decay constant. Note tau in the roles: an undeclared multi-"
        "letter name reads the way LaTeX means it, as t·a·u.",
        r"""
x = m / \tau
L_{slope} = (1 - \exp(-x)) / x
L_{curve} = L_{slope} - \exp(-x)
y = \beta_0 + \beta_1 L_{slope} + \beta_2 L_{curve}
""",
        {"tau": _P, "beta_0": _P, "beta_1": _P, "beta_2": _P},
        "term structure zero curve level slope curvature",
    ),
    _t(
        "svensson",
        "Rates and curves",
        "Svensson, Nelson–Siegel with a second hump",
        "Four factors and two decays. Central banks publish this one; it fits the long end "
        "better and is even harder to identify.",
        r"""
x = m / \tau_1
z = m / \tau_2
L_1 = (1 - \exp(-x)) / x
L_2 = L_1 - \exp(-x)
L_3 = (1 - \exp(-z)) / z - \exp(-z)
y = \beta_0 + \beta_1 L_1 + \beta_2 L_2 + \beta_3 L_3
""",
        {"tau_1": _P, "tau_2": _P, "beta_0": _P, "beta_1": _P, "beta_2": _P, "beta_3": _P},
        "term structure central bank six factor",
    ),
    _t(
        "discount_factor",
        "Rates and curves",
        "A discount factor from a zero rate",
        "Continuously compounded. The single most reused line in a rates library.",
        r"""
df = \exp(-y t)
""",
        None,
        "present value zero rate compounding",
    ),
    _t(
        "forward_rate",
        "Rates and curves",
        "A forward rate between two tenors",
        "Implied by two zero rates, which is why a curve with a kink produces a forward "
        "nobody believes.",
        r"""
f = (y_2 t_2 - y_1 t_1) / (t_2 - t_1)
""",
        {"y_1": "feature", "y_2": "feature", "t_1": "feature", "t_2": "feature"},
        "implied forward term structure bootstrapping",
    ),
    _t(
        "annuity_factor",
        "Rates and curves",
        "An annuity factor",
        "The present value of one unit per period. The denominator of a par swap rate and "
        "of a level mortgage payment alike.",
        r"""
a = (1 - (1 + r)^{-n}) / r
""",
        {"r": _P},
        "level payment pv01 dv01 swap",
    ),
    _t(
        "par_swap_rate",
        "Rates and curves",
        "A par swap rate",
        "The fixed rate that makes the swap worth nothing at inception: a ratio of two "
        "present values, both supplied as inputs here.",
        r"""
s = (df_{start} - df_{end}) / annuity
""",
        {"annuity": "feature", "df_start": "feature", "df_end": "feature"},
        "interest rate swap fixed leg floating",
    ),
    _t(
        "bond_price_flat",
        "Rates and curves",
        "A bond price at a flat yield",
        "Coupon annuity plus discounted redemption. The textbook form, and the one a "
        "trader checks a system against.",
        r"""
a = (1 - (1 + y)^{-n}) / y
price = c\,a + 100 (1 + y)^{-n}
""",
        {"y": _P},
        "fixed income clean price redemption coupon",
    ),
    _t(
        "modified_duration",
        "Rates and curves",
        "Modified duration from Macaulay",
        "The one-line conversion that half of a rates desk has typed wrongly at least once.",
        r"""
d_{mod} = d_{mac} / (1 + y/k)
""",
        {"y": _P, "k": _C, "d_mac": "feature"},
        "interest rate sensitivity convexity risk",
    ),
    _t(
        "convexity_adjustment",
        "Rates and curves",
        "A second-order price change",
        "Duration alone is a straight line through a curve. This is the correction, and the "
        "reason a large move needs it.",
        r"""
dP = -d_{mod} \cdot P \cdot dy + 0.5 C P dy^2
""",
        {"d_mod": "feature", "dy": "feature"},
        "taylor expansion duration gamma rates",
    ),
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
        "The inverse normal of the default probability is an input, because the IR has no "
        "inverse-normal operator -- so that step is computed upstream and arrives as a "
        "feature, which is the honest way to say it rather than writing something the "
        "parser will read as a reciprocal.",
        r"""
R = 0.12 \frac{1 - \exp(-50 pd)}{1 - \exp(-50)} + 0.24 \left(1 - \frac{1 - \exp(-50 pd)}{1 - \exp(-50)}\right)
b = (0.11852 - 0.05478 \log(pd))^2
mat = (1 + (M - 2.5) b) / (1 - 1.5 b)
cond = ncdf((probit_{pd} + \sqrt{R} z_{999}) / \sqrt{1 - R})
k = (lgd \cdot cond - pd \cdot lgd) \cdot mat
""",
        {"pd": "feature", "lgd": "feature", "M": "feature", "probit_pd": "feature", "z_999": _C},
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
    # ---- market risk and portfolio -------------------------------------------------------
    _t(
        "var_normal",
        "Market risk",
        "Parametric value at risk",
        "Normal, one horizon, one confidence. Two things are inputs rather than steps: the "
        "volatility, because computing it aggregates over rows, and the standard normal "
        "quantile at the confidence level -- a constant chosen with the confidence, and one "
        "the IR cannot compute because it has no inverse-normal operator.",
        r"""
var = -(\mu + \sigma z_c) V
""",
        {"z_c": _C, "mu": "feature", "sigma": "feature", "V": "feature"},
        "value at risk parametric variance covariance confidence",
    ),
    _t(
        "expected_shortfall_normal",
        "Market risk",
        "Expected shortfall under normality",
        "The tail mean rather than the tail quantile. Note the density where the VaR has a "
        "distribution: that is the whole difference.",
        r"""
es = \left(-\mu + \sigma \frac{npdf(z_c)}{1 - c}\right) V
""",
        {"z_c": _C, "c": _C, "mu": "feature", "sigma": "feature", "V": "feature"},
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
adj = z_c + (z_c^2 - 1) S / 6 + (z_c^3 - 3 z_c)(K - 3) / 24 - (2 z_c^3 - 5 z_c) S^2 / 36
var = -(\mu + \sigma\,adj) V
""",
        {"z_c": _C, "mu": "feature", "sigma": "feature", "V": "feature"},
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
]

GROUPS = [
    "Options and derivatives",
    "Rates and curves",
    "Credit risk",
    "Mortgages and retail",
    "Market risk",
    "Valuation",
    "Insurance",
    "Transforms and statistics",
]


def for_ui() -> list[dict[str, Any]]:
    """The library as the wizard's page needs it: roles flattened to the text of the box."""
    out = []
    for t in TEMPLATES:
        roles = "\n".join(f"{k}: {v}" for k, v in t["roles"].items())
        out.append({**t, "roles_text": roles})
    return out
