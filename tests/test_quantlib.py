"""
MAYA — tests for the QuantLib runtime.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Most of what a bank runs is not a learned model; it is a valuation. Those models
have no parameter object to fit, and they have something the learned ones do not:
an as-of date that changes the answer.
"""
from __future__ import annotations

import pytest

from core.execution.errors import WarrantError
from core.execution.runtimes import Invocation, QuantLibRuntime

CURVE = [{"date": "2026-01-01", "rate": 0.030},
         {"date": "2027-01-01", "rate": 0.032},
         {"date": "2031-01-01", "rate": 0.036},
         {"date": "2036-01-01", "rate": 0.038}]
FIXINGS = [{"date": "2025-12-31", "rate": 0.031}]


@pytest.fixture
def ql():
    runtime = QuantLibRuntime()
    if runtime.available():
        pytest.skip(runtime.available())
    return runtime


def warrant(instrument, engine="analytic", as_of="2026-01-01", curve=CURVE,
            fixings=None, day_count="actual/365"):
    market = {"binding": "market_data", "curve": curve, "day_count": day_count}
    if as_of is not None:
        market["as_of"] = as_of
    if fixings:
        market["fixings"] = fixings
    return {"realisation": {"runtime": "quantlib",
                            "entry": {"instrument": instrument,
                                      "pricing_engine": engine}},
            "data": {"inputs": [market]}}


class TestTheDateComesFromTheWarrant:
    def test_a_warrant_with_no_evaluation_date_is_refused(self, ql):
        """A valuation that reads today is not reproducible tomorrow, and a
        backtest of it is a backtest of nothing."""
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("discount", as_of=None),
                                 {"date": "2031-01-01"}))
        assert exc.value.code == "no_evaluation_date"
        assert "reproducible tomorrow" in exc.value.remediation

    def test_the_same_warrant_prices_the_same_twice(self, ql):
        call = Invocation(warrant("discount"), {"date": "2031-01-01"})
        assert ql.invoke(call) == ql.invoke(call)

    def test_a_different_as_of_gives_a_different_answer(self, ql):
        """On a bond, where the evaluation date moves the accrual. A raw curve
        lookup is measured from the curve's own reference date and would be the
        same either way — which is worth knowing, not worth asserting wrongly."""
        bond = {"settlement": "2026-01-05", "maturity": "2031-01-05",
                "coupon": 0.04, "face": 100.0}
        early = ql.invoke(Invocation(
            warrant("fixed_bond", "discounting", as_of="2026-03-01"), bond))
        later = ql.invoke(Invocation(
            warrant("fixed_bond", "discounting", as_of="2026-06-01"), bond))
        assert early["accrued"] != later["accrued"]
        assert early["clean_price"] != later["clean_price"]

    def test_a_posix_timestamp_is_read_as_a_date(self, ql):
        """Every other clock in this platform is carried that way."""
        out = ql.invoke(Invocation(warrant("discount", as_of=1767225600.0),
                                   {"date": "2031-01-01"}))
        assert 0 < out["discount"] < 1

    def test_a_date_that_is_not_one_is_refused(self, ql):
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("discount", as_of="last Tuesday"),
                                 {"date": "2031-01-01"}))
        assert exc.value.code == "malformed_date"


class TestTheCurveComesFromTheWarrant:
    def test_a_warrant_with_no_curve_is_refused(self, ql):
        """Reaching for a market data service would put an unversioned input
        into a governed computation."""
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("discount", curve=None),
                                 {"date": "2031-01-01"}))
        assert exc.value.code == "no_curve"
        assert "unversioned input" in exc.value.remediation

    def test_a_malformed_curve_says_what_a_pillar_carries(self, ql):
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("discount", curve=[{"rate": 0.03}]),
                                 {"date": "2031-01-01"}))
        assert exc.value.code == "malformed_curve"

    def test_an_unknown_day_count_is_refused_rather_than_substituted(self, ql):
        """A day count silently swapped for another moves every cash flow."""
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("discount", day_count="business/252"),
                                 {"date": "2031-01-01"}))
        assert exc.value.code == "unknown_day_count"


class TestItPricesRealInstruments:
    def test_a_discount_factor_is_between_zero_and_one(self, ql):
        out = ql.invoke(Invocation(warrant("discount"), {"date": "2031-01-01"}))
        assert 0.7 < out["discount"] < 1.0

    def test_the_zero_rate_matches_the_curve_it_was_built_from(self, ql):
        out = ql.invoke(Invocation(warrant("zero_rate"), {"date": "2031-01-01"}))
        assert out["zero_rate"] == pytest.approx(0.036, abs=1e-6)

    def test_a_forward_rate_exceeds_the_zeros_on_an_upward_curve(self, ql):
        out = ql.invoke(Invocation(warrant("forward_rate"),
                                   {"from": "2031-01-01", "to": "2036-01-01"}))
        assert out["forward_rate"] > 0.036

    def test_a_bond_above_its_yield_prices_above_par(self, ql):
        out = ql.invoke(Invocation(warrant("fixed_bond", "discounting"),
                                   {"settlement": "2026-01-05",
                                    "maturity": "2031-01-05",
                                    "coupon": 0.04, "face": 100.0}))
        assert out["clean_price"] > 100.0
        assert set(out) == {"clean_price", "dirty_price", "accrued", "npv"}

    def test_a_swap_struck_at_its_fair_rate_is_worth_nothing(self, ql):
        args = {"start": "2026-01-05", "maturity": "2031-01-05",
                "notional": 10_000_000, "fixed_rate": 0.035}
        first = ql.invoke(Invocation(
            warrant("vanilla_swap", "discounting", fixings=FIXINGS), args))
        at_fair = ql.invoke(Invocation(
            warrant("vanilla_swap", "discounting", fixings=FIXINGS),
            {**args, "fixed_rate": first["fair_rate"]}))
        assert at_fair["npv"] == pytest.approx(0.0, abs=1.0)

    def test_a_swaption_is_worth_more_the_more_it_might_move(self, ql):
        args = {"expiry": "2027-01-05", "maturity": "2032-01-05",
                "strike": 0.035, "notional": 10_000_000}
        quiet = ql.invoke(Invocation(
            warrant("swaption", "black", fixings=FIXINGS),
            {**args, "volatility": 0.10}))
        loud = ql.invoke(Invocation(
            warrant("swaption", "black", fixings=FIXINGS),
            {**args, "volatility": 0.40}))
        assert loud["npv"] > quiet["npv"]

    def test_a_swaption_without_a_volatility_is_refused(self, ql):
        """A price computed from an assumed one is a price of a different
        instrument."""
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("swaption", "black", fixings=FIXINGS),
                                 {"expiry": "2027-01-05",
                                  "maturity": "2032-01-05", "strike": 0.035}))
        assert exc.value.code == "no_volatility"


class TestAMissingInputIsNotInvented:
    def test_one_warrant_s_fixing_does_not_leak_into_the_next(self, ql):
        """QuantLib keeps fixing history in a process-global manager. A fixing
        from one valuation still being there for the next is the unversioned
        input this runtime exists to prevent, arriving through the back door."""
        args = {"start": "2026-01-05", "maturity": "2031-01-05",
                "fixed_rate": 0.035}
        ql.invoke(Invocation(
            warrant("vanilla_swap", "discounting", fixings=FIXINGS), args))
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("vanilla_swap", "discounting"), args))
        assert exc.value.code == "missing_fixing"

    def test_a_swap_needing_a_past_fixing_says_so(self, ql):
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("vanilla_swap", "discounting"),
                                 {"start": "2026-01-05",
                                  "maturity": "2031-01-05",
                                  "fixed_rate": 0.035}))
        assert exc.value.code == "missing_fixing"
        assert "unversioned number" in exc.value.remediation

    def test_supplying_the_fixing_lets_it_price(self, ql):
        out = ql.invoke(Invocation(
            warrant("vanilla_swap", "discounting", fixings=FIXINGS),
            {"start": "2026-01-05", "maturity": "2031-01-05",
             "fixed_rate": 0.035}))
        assert out["npv"] != 0.0 and "fair_rate" in out

    def test_a_malformed_fixing_is_refused(self, ql):
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(
                warrant("vanilla_swap", "discounting",
                        fixings=[{"rate": 0.031}]),
                {"start": "2026-01-05", "maturity": "2031-01-05",
                 "fixed_rate": 0.035}))
        assert exc.value.code == "malformed_fixing"


class TestItRefusesRatherThanGuessing:
    def test_an_instrument_it_does_not_price_is_named(self, ql):
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("bermudan_callable"), {}))
        assert exc.value.code == "instrument_unsupported"
        assert "guessing which is meant" in exc.value.remediation

    def test_a_pricing_engine_it_does_not_build_is_named(self, ql):
        """An engine silently swapped for another produces a number nobody can
        reconcile."""
        with pytest.raises(WarrantError) as exc:
            ql.invoke(Invocation(warrant("discount", "montecarlo"),
                                 {"date": "2031-01-01"}))
        assert exc.value.code == "pricing_engine_unsupported"

    def test_it_publishes_what_it_can_do(self, ql):
        described = ql.describe()
        assert {i["instrument"] for i in described["instruments"]} == {
            "discount", "zero_rate", "forward_rate", "fixed_bond",
            "vanilla_swap", "swaption"}
        assert "never from the clock" in described["evaluation_date"]
        assert "L-W1" in described["trainability"]


class TestTheEngineOffersIt:
    def test_the_captive_engine_registers_it(self, tmp_path, warrants):
        from core.execution.engine import CaptiveEngine
        engine = CaptiveEngine(warrants, artifact_dir=tmp_path)
        assert "quantlib" in engine.runtimes.keys()

    def test_it_is_not_sandboxed_and_the_reason_is_stated(self):
        """It loads no artifact — the instrument and the curve arrive in the
        warrant — so there is no untrusted file to isolate from."""
        from core.execution.engine import SANDBOXED_RUNTIMES
        assert "quantlib" not in SANDBOXED_RUNTIMES
