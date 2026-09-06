"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The QuantLib runtime.

Most of what a bank runs is not a learned model. It is a valuation: a discount
factor, a swap, a swaption, a bond. Those models have **no parameter object to
fit** — their constants come from theory and their inputs come from a curve —
which is what trainability class T0 means, and why the grammar refuses to warrant
one for fitting.

They do have something the others do not: **an as-of date that changes the
answer**. A price is a price *on a date*, against a curve *as it stood*. So this
runtime does two things that the ONNX and PMML runtimes do not have to:

**It sets the evaluation date from the warrant, never from the clock.** A
valuation that reads today's date is not reproducible tomorrow, and a backtest of
it is a backtest of nothing. If the warrant does not say when, this refuses
rather than defaulting to now — the default would be the wrong answer that looks
right.

**It builds the curve from what the warrant carries**, and nothing else. Reaching
for a market data service here would put an unversioned input into a governed
computation, which is the whole failure the platform exists to make visible.

The instruments are a deliberately small set. QuantLib can price a great deal;
what belongs in a *captive* engine is enough to demonstrate the governed path end
to end against something real, and an honest refusal for the rest.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from core.execution.errors import WarrantError
from core.execution.runtimes.base import Invocation
from core.log import get_logger, swallowed

logger = get_logger(__name__)

DISCOUNT, ZERO_RATE, FORWARD_RATE = "discount", "zero_rate", "forward_rate"
FIXED_BOND, VANILLA_SWAP, SWAPTION = "fixed_bond", "vanilla_swap", "swaption"

INSTRUMENTS: Tuple[str, ...] = (DISCOUNT, ZERO_RATE, FORWARD_RATE,
                                FIXED_BOND, VANILLA_SWAP, SWAPTION)

INSTRUMENT_MEANING: Dict[str, str] = {
    DISCOUNT: "the discount factor to a date, off the supplied curve",
    ZERO_RATE: "the continuously compounded zero rate to a date",
    FORWARD_RATE: "the forward rate between two dates",
    FIXED_BOND: "a fixed-rate bond: clean price, dirty price and accrued",
    VANILLA_SWAP: "a fixed-for-floating swap: NPV and fair rate",
    SWAPTION: "a European swaption under Black, with a supplied volatility",
}

# Which pricing engines this runtime knows how to construct. A warrant naming
# one it does not is refused by name rather than silently priced another way.
ENGINES: Tuple[str, ...] = ("analytic", "discounting", "black")

DAY_COUNTS = {"actual/360": "Actual360", "actual/365": "Actual365Fixed",
              "30/360": "Thirty360", "actual/actual": "ActualActual"}


class QuantLibRuntime:
    """Prices instruments against a curve the warrant carries."""

    key = "quantlib"

    def available(self) -> Optional[str]:
        try:
            import QuantLib
        except ImportError as exc:
            swallowed(logger, exc, "the quantlib runtime is not usable here",
                      detail="warrants naming it will be refused with the reason",
                      level=logging.DEBUG)
            return f"QuantLib is not installed ({exc}); pip install QuantLib"
        return None

    # ---------------------------------------------------------------- invoke
    def invoke(self, call: Invocation) -> Any:
        if (why := self.available()):
            raise WarrantError("runtime_unavailable", why,
                               "install the package, or route this warrant to an "
                               "engine that has it")
        import QuantLib as ql

        entry = call.entry
        instrument = entry.get("instrument")
        if instrument not in INSTRUMENTS:
            raise WarrantError(
                "instrument_unsupported",
                f"this engine does not price '{instrument}'; it prices "
                f"{', '.join(INSTRUMENTS)}",
                "route the warrant to an engine that does, or price it as one "
                "of these — guessing which is meant would be worse than refusing")
        engine = entry.get("pricing_engine")
        if engine not in ENGINES:
            raise WarrantError(
                "pricing_engine_unsupported",
                f"this engine does not build a '{engine}' pricing engine; it "
                f"builds {', '.join(ENGINES)}",
                "a warrant naming an engine that is silently swapped for another "
                "produces a number nobody can reconcile")

        as_of = self._as_of(call, ql)
        ql.Settings.instance().evaluationDate = as_of
        curve = self._curve(call, as_of, ql)
        return self._price(instrument, engine, call, as_of, curve, ql)

    # ------------------------------------------------------------------ date
    @staticmethod
    def _as_of(call: Invocation, ql) -> Any:
        """The evaluation date, from the warrant and never from the clock.

        A valuation that reads today's date is not reproducible tomorrow, and a
        backtest of it is a backtest of nothing. Defaulting to now would be the
        wrong answer that looks right.
        """
        raw = (call.inputs.get("as_of")
               or (call.entry or {}).get("as_of")
               or _market(call).get("as_of"))
        if raw is None:
            raise WarrantError(
                "no_evaluation_date",
                "this warrant does not say what date to value at",
                "a price is a price on a date; supply as_of in the market data "
                "binding or in the call, because valuing at 'now' would not be "
                "reproducible tomorrow")
        return _to_date(raw, ql)

    # ----------------------------------------------------------------- curve
    def _curve(self, call: Invocation, as_of, ql):
        """A curve from what the warrant carries, and from nothing else."""
        market = _market(call)
        pillars = market.get("curve") or call.inputs.get("curve")
        if not pillars:
            raise WarrantError(
                "no_curve",
                "this warrant carries no curve to discount against",
                "supply the curve in the market_data binding; reaching for a "
                "market data service here would put an unversioned input into a "
                "governed computation")
        try:
            dates, rates = [], []
            for pillar in pillars:
                dates.append(_to_date(pillar["date"], ql))
                rates.append(float(pillar["rate"]))
            # A zero curve needs a point at the evaluation date. Anchoring at the
            # first pillar's rate is flat extrapolation to the short end, and
            # only added when the curve does not already start there — a
            # duplicated pillar is a different error with a worse message.
            if dates and dates[0] > as_of:
                dates.insert(0, as_of)
                rates.insert(0, rates[0])
        except (KeyError, TypeError, ValueError) as exc:
            swallowed(logger, exc, "read the curve out of a warrant",
                      "refused as malformed rather than priced on a partial "
                      "curve", logging.INFO)
            raise WarrantError(
                "malformed_curve",
                f"the curve does not read as a list of dated rates: {exc}",
                "each pillar carries a date and a rate") from exc

        day_count = _day_count(market.get("day_count", "actual/365"), ql)
        curve = ql.ZeroCurve(dates, rates, day_count)
        curve.enableExtrapolation()
        return ql.YieldTermStructureHandle(curve)

    # ----------------------------------------------------------------- price
    def _price(self, instrument: str, engine: str, call: Invocation, as_of,
               curve, ql) -> Dict[str, Any]:
        inputs = call.inputs
        if instrument == DISCOUNT:
            return {"discount": curve.discount(_to_date(inputs["date"], ql))}
        if instrument == ZERO_RATE:
            rate = curve.zeroRate(_to_date(inputs["date"], ql),
                                  curve.dayCounter(), ql.Continuous).rate()
            return {"zero_rate": rate}
        if instrument == FORWARD_RATE:
            rate = curve.forwardRate(_to_date(inputs["from"], ql),
                                     _to_date(inputs["to"], ql),
                                     curve.dayCounter(), ql.Continuous).rate()
            return {"forward_rate": rate}
        if instrument == FIXED_BOND:
            return self._bond(call, as_of, curve, ql)
        if instrument == VANILLA_SWAP:
            return self._swap(call, as_of, curve, ql)
        return self._swaption(call, as_of, curve, ql)

    @staticmethod
    def _bond(call: Invocation, as_of, curve, ql) -> Dict[str, Any]:
        i = call.inputs
        schedule = ql.Schedule(
            _to_date(i.get("issue", i["settlement"]), ql),
            _to_date(i["maturity"], ql),
            ql.Period(int(i.get("frequency", 2)), ql.Times if False else ql.Years)
            if False else ql.Period(ql.Semiannual),
            ql.TARGET(), ql.Unadjusted, ql.Unadjusted,
            ql.DateGeneration.Backward, False)
        bond = ql.FixedRateBond(int(i.get("settlement_days", 2)),
                                float(i.get("face", 100.0)), schedule,
                                [float(i["coupon"])], ql.Thirty360(ql.Thirty360.BondBasis))
        bond.setPricingEngine(ql.DiscountingBondEngine(curve))
        return {"clean_price": bond.cleanPrice(), "dirty_price": bond.dirtyPrice(),
                "accrued": bond.accruedAmount(), "npv": bond.NPV()}

    @staticmethod
    def _swap(call: Invocation, as_of, curve, ql) -> Dict[str, Any]:
        i = call.inputs
        index = _index(call, curve, ql)
        start = _to_date(i.get("start", i.get("effective")), ql)
        end = _to_date(i["maturity"], ql)
        fixed = ql.Schedule(start, end, ql.Period(ql.Annual), ql.TARGET(),
                            ql.Unadjusted, ql.Unadjusted,
                            ql.DateGeneration.Forward, False)
        floating = ql.Schedule(start, end, ql.Period(ql.Semiannual), ql.TARGET(),
                               ql.ModifiedFollowing, ql.ModifiedFollowing,
                               ql.DateGeneration.Forward, False)
        swap = ql.VanillaSwap(
            ql.VanillaSwap.Payer if i.get("side", "payer") == "payer"
            else ql.VanillaSwap.Receiver,
            float(i.get("notional", 1_000_000.0)), fixed, float(i["fixed_rate"]),
            ql.Thirty360(ql.Thirty360.BondBasis), floating, index, 0.0,
            ql.Actual360())
        swap.setPricingEngine(ql.DiscountingSwapEngine(curve))
        return _priced(lambda: {"npv": swap.NPV(), "fair_rate": swap.fairRate(),
                                "fixed_leg_npv": swap.fixedLegNPV(),
                                "floating_leg_npv": swap.floatingLegNPV()})

    @staticmethod
    def _swaption(call: Invocation, as_of, curve, ql) -> Dict[str, Any]:
        i = call.inputs
        if "volatility" not in i:
            raise WarrantError(
                "no_volatility",
                "a swaption under Black needs a volatility, and this warrant "
                "carries none",
                "supply volatility; a price computed from an assumed one is a "
                "price of a different instrument")
        index = _index(call, curve, ql)
        start = _to_date(i["expiry"], ql)
        end = _to_date(i["maturity"], ql)
        fixed = ql.Schedule(start, end, ql.Period(ql.Annual), ql.TARGET(),
                            ql.Unadjusted, ql.Unadjusted,
                            ql.DateGeneration.Forward, False)
        floating = ql.Schedule(start, end, ql.Period(ql.Semiannual), ql.TARGET(),
                               ql.ModifiedFollowing, ql.ModifiedFollowing,
                               ql.DateGeneration.Forward, False)
        underlying = ql.VanillaSwap(
            ql.VanillaSwap.Payer, float(i.get("notional", 1_000_000.0)),
            fixed, float(i["strike"]),
            ql.Thirty360(ql.Thirty360.BondBasis), floating, index, 0.0,
            ql.Actual360())
        swaption = ql.Swaption(underlying, ql.EuropeanExercise(start))
        swaption.setPricingEngine(ql.BlackSwaptionEngine(
            curve, ql.QuoteHandle(ql.SimpleQuote(float(i["volatility"])))))
        return _priced(lambda: {"npv": swaption.NPV(),
                                "underlying_fair_rate": underlying.fairRate()})

    # -------------------------------------------------------------- describe
    @staticmethod
    def describe() -> Dict[str, Any]:
        return {
            "runtime": "quantlib",
            "instruments": [{"instrument": k, "prices": INSTRUMENT_MEANING[k]}
                            for k in INSTRUMENTS],
            "pricing_engines": list(ENGINES),
            "evaluation_date": "taken from the warrant, never from the clock: a "
                               "valuation that reads today is not reproducible "
                               "tomorrow",
            "curve": "built from what the warrant carries and nothing else; "
                     "reaching for a market data service would put an "
                     "unversioned input into a governed computation",
            "trainability": "these are T0 — their parameters come from theory, "
                            "not from data — so law L-W1 refuses to warrant one "
                            "for fitting, and that refusal is the class working "
                            "rather than a limitation",
        }


def _index(call: Invocation, curve, ql):
    """The floating index, with whatever past fixings the warrant carries.

    A swap whose first fixing predates the evaluation date needs that fixing.
    It is an input like any other, and inventing one here would put an
    unversioned number into a governed valuation.
    """
    index = ql.Euribor6M(curve)
    # QuantLib keeps fixing history in a PROCESS-GLOBAL manager, so a fixing
    # supplied by one warrant would still be there for the next valuation —
    # which is precisely the unversioned input this runtime exists to prevent,
    # arriving through the back door. Each valuation starts from an empty
    # history and sees only what its own warrant carries.
    ql.IndexManager.instance().clearHistories()
    fixings = (call.inputs.get("fixings")
               or _market(call).get("fixings") or [])
    for fixing in fixings:
        try:
            index.addFixing(_to_date(fixing["date"], ql), float(fixing["rate"]),
                            True)
        except (KeyError, TypeError, ValueError) as exc:
            swallowed(logger, exc, "read a fixing out of a warrant",
                      "refused rather than skipped; a skipped fixing is an "
                      "invented one", logging.INFO)
            raise WarrantError(
                "malformed_fixing",
                f"a fixing does not read as a date and a rate: {exc}",
                "each fixing carries a date and a rate") from exc
    return index


def _priced(compute):
    """Run a valuation, turning QuantLib's own refusals into ours.

    A missing fixing is not an internal error; it is a warrant that did not
    carry an input the instrument needs, and the caller can fix that.
    """
    try:
        return compute()
    except RuntimeError as exc:
        message = str(exc)
        swallowed(logger, exc, "priced an instrument",
                  "QuantLib refused; translated into a warrant refusal the "
                  "caller can act on", logging.INFO)
        if "fixing" in message.lower():
            raise WarrantError(
                "missing_fixing",
                f"the instrument needs a past fixing the warrant does not "
                f"carry: {message}",
                "supply fixings alongside the curve; a valuation that invented "
                "one would put an unversioned number into a governed "
                "computation") from exc
        raise WarrantError(
            "valuation_failed", f"the valuation did not complete: {message}",
            "the instrument and the market data the warrant carries do not "
            "fit together") from exc


def _market(call: Invocation) -> Dict[str, Any]:
    """The market_data input binding, if the warrant carries one."""
    for binding in (call.warrant.get("data") or {}).get("inputs") or []:
        if binding.get("binding") == "market_data":
            return binding
    return {}


def _day_count(name: str, ql):
    attribute = DAY_COUNTS.get(str(name).lower())
    if attribute is None:
        raise WarrantError(
            "unknown_day_count",
            f"'{name}' is not a day count this engine knows; it knows "
            f"{', '.join(sorted(DAY_COUNTS))}",
            "a day count silently swapped for another moves every cash flow")
    factory = getattr(ql, attribute)
    return factory(ql.Thirty360.BondBasis) if attribute == "Thirty360" else factory()


def _to_date(value: Any, ql):
    """A QuantLib date from an ISO string, a serial, or a QuantLib date."""
    if hasattr(value, "serialNumber"):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # A POSIX timestamp, which is how every other clock in this platform is
        # carried; a bare serial would be ambiguous between the two conventions.
        import datetime as dt
        moment = dt.datetime.fromtimestamp(float(value), dt.timezone.utc)
        return ql.Date(moment.day, moment.month, moment.year)
    text = str(value)
    try:
        year, month, day = (int(p) for p in text.replace("/", "-").split("-")[:3])
    except ValueError as exc:
        swallowed(logger, exc, "read a date out of a warrant",
                  f"{value!r} is not a date the engine can read", logging.INFO)
        raise WarrantError(
            "malformed_date", f"'{value}' is not a date this engine can read",
            "supply an ISO date (YYYY-MM-DD) or a POSIX timestamp") from exc
    return ql.Date(day, month, year)
