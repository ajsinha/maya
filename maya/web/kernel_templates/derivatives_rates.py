"""
Kernel templates: Options, derivatives, rates and curves.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.web.kernel_templates._base import _C, _P, _t

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
    # ---- options, continued ---------------------------------------------------------------
    _t(
        "put_call_parity",
        "Options and derivatives",
        "A put from a call by parity",
        "Not a model of anything: an arbitrage identity. Worth governing because a desk that "
        "prices the two separately can violate it and not notice.",
        r"""
put = call - S + K e^{-rT}
""",
        {"r": _P, "call": "feature"},
        "arbitrage identity consistency check european",
    ),
    _t(
        "bs_rho",
        "Options and derivatives",
        "Rho of a European call",
        "Sensitivity to the discount rate, and the greek that matters most when rates move "
        "and least when they do not.",
        r"""
d_1 = (\log(S/K) + (r + \sigma^2/2)T) / (\sigma\sqrt{T})
d_2 = d_1 - \sigma\sqrt{T}
rho = K T e^{-rT} ncdf(d_2)
""",
        {"sigma": _P, "r": _P},
        "greek interest rate sensitivity discounting",
    ),
    _t(
        "bs_dual_delta",
        "Options and derivatives",
        "Dual delta: sensitivity to the strike",
        "The risk-neutral probability of finishing in the money, up to a discount factor -- "
        "which is what makes it the number a structurer reaches for.",
        r"""
d_2 = (\log(S/K) + (r - \sigma^2/2)T) / (\sigma\sqrt{T})
dual = -e^{-rT} ncdf(d_2)
""",
        {"sigma": _P, "r": _P},
        "strike sensitivity exercise probability digital",
    ),
    _t(
        "implied_vol_atm",
        "Options and derivatives",
        "Brenner–Subrahmanyam at-the-money implied volatility",
        "A closed form that inverts Black--Scholes at the money to within a fraction of a "
        "volatility point, and needs no solver. Useful as a starting guess and as a check "
        "that a solver has not wandered.",
        r"""
\sigma = \sqrt{2\pi / T} \cdot price / S
""",
        {"pi": _C, "price": "feature"},
        "inversion approximation atm newton starting guess",
    ),
    # ---- rates, continued -----------------------------------------------------------------
    _t(
        "fra_rate",
        "Rates and curves",
        "A forward rate agreement rate",
        "Simple compounding rather than continuous, because that is what the contract says. "
        "The difference is small and it is the sort of small that ends up in a dispute.",
        r"""
f = ((1 + r_2 t_2) / (1 + r_1 t_1) - 1) / (t_2 - t_1)
""",
        {"r_1": "feature", "r_2": "feature", "t_1": "feature", "t_2": "feature"},
        "fra money market simple compounding libor",
    ),
    _t(
        "compounding_convert",
        "Rates and curves",
        "A discrete rate as a continuous one",
        "Two conventions for the same rate. Systems that disagree about which one they hold "
        "produce discount factors that differ in the fourth decimal and reconcile nowhere.",
        r"""
r_c = m \log(1 + r_d/m)
""",
        {"m": _C, "r_d": "feature"},
        "convention annual semiannual continuous nominal effective",
    ),
    _t(
        "dv01",
        "Rates and curves",
        "DV01 from modified duration",
        "The money a basis point moves. A trader thinks in this and a risk system usually "
        "stores the duration, so the conversion is written down often and wrongly.",
        r"""
dv = d_{mod} \cdot P / 10000
""",
        {"d_mod": "feature", "P": "feature"},
        "pv01 basis point value hedge notional",
    ),
    _t(
        "accrued_interest",
        "Rates and curves",
        "Accrued interest on a day count",
        "The day-count basis is a parameter because it is a contractual choice, not a fact "
        "about the instrument, and the choices disagree by a few days a year.",
        r"""
accrued = coupon \cdot days / basis
""",
        {"basis": _P, "coupon": "feature", "days": "feature"},
        "act360 act365 30360 clean dirty price convention",
    ),
    _t(
        "breakeven_inflation",
        "Rates and curves",
        "Break-even inflation",
        "The difference two markets imply, and not a forecast: it carries an inflation risk "
        "premium nobody can separate out from the number itself.",
        r"""
be = nominal - real
""",
        {"nominal": "feature", "real": "feature"},
        "tips linker index linked real yield premium",
    ),
    _t(
        "fisher_real",
        "Rates and curves",
        "A real rate by the Fisher relation",
        "Exact rather than the subtraction everybody uses. The two differ by the product term, "
        "which matters once inflation is not small.",
        r"""
real = (1 + nominal) / (1 + inflation) - 1
""",
        {"nominal": "feature", "inflation": "feature"},
        "fisher equation deflating real terms",
    ),
]
