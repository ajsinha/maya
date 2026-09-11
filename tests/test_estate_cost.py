"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

M-6: what the estate costs, and the two claims this will not make.

The obvious implementation is wrong here for the reason most obvious
implementations are wrong in this platform. **MAYA does not run models**, so it
cannot observe what one costs — a figure it computed would be a price somebody
typed multiplied by a call count it also did not observe, printed as a
measurement. And **MAYA is not on the serving path**, so a budget that claimed
to enforce would be claiming a control it has no way to exercise.

What is left is the half a register can do and nobody else can: attribute a cost
to the ownership the register actually governs the model under, and report the
share nobody attributed at all. That share is the number this exists to produce.
A bill is complete by construction, so an unattributed cost looks exactly like
an attributed one until somebody asks who owns it.
"""
from __future__ import annotations

import pytest

from core.estate.common import EstateError
from core.estate.cost import ATTRIBUTED, DIMENSIONS, UNATTRIBUTED, EstateCost
from db import EstateCostRepository

DAY = 86400.0
Q1 = (1_800_000_000.0, 1_800_000_000.0 + 90 * DAY)


@pytest.fixture
def cost(db, registry, evidence):
    return EstateCost(EstateCostRepository(db), registry, None, evidence)


def _line(cost, urn="", amount=1000.0, currency="GBP", source="cloud-bill"):
    return cost.record(amount=amount, currency=currency,
                       period_start=Q1[0], period_end=Q1[1],
                       source=source, urn=urn, reference="INV-1")


class TestItObservesNothingAndEnforcesNothing:
    def test_the_posture_says_both(self):
        out = EstateCost.posture()
        assert out["observes_cost"] is False
        assert out["enforces_a_budget"] is False

    def test_it_says_why_it_cannot_observe(self):
        assert "printing the product as a measurement" in \
            EstateCost.posture()["why_not_observe"]

    def test_it_says_why_a_budget_cannot_block(self):
        """The same objection that makes a shadow grant an attestation rather
        than a router."""
        assert "no way to exercise" in EstateCost.posture()["why_not_enforce"]

    def test_it_names_the_number_that_matters(self):
        assert "NOBODY HAS ATTRIBUTED" in \
            EstateCost.posture()["the_number_that_matters"]


class TestAttributionComesFromTheRegister:
    def test_a_line_naming_a_model_takes_the_registers_ownership(self, cost,
                                                                 a_model):
        """A cost attributed by whoever produced the bill is attributed to
        whatever they thought the ownership was."""
        out = _line(cost, a_model["urn"])
        assert out["state"] == ATTRIBUTED
        assert out["owner"] == a_model["owner"]
        assert out["legal_entity"] == a_model["legal_entity"]
        assert "rather than from the cost record" in out["detail"]

    def test_a_line_naming_nothing_is_kept_as_unattributed(self, cost):
        """That line IS the finding, and refusing it would delete the
        finding."""
        out = _line(cost)
        assert out["state"] == UNATTRIBUTED
        assert "would delete the finding" in out["detail"]

    def test_a_line_naming_an_unregistered_model_is_kept_too(self, cost):
        out = _line(cost, "maya://model/nobody.registered.this")
        assert out["state"] == UNATTRIBUTED
        assert "not a registered model" in out["detail"]

    def test_the_dimensions_are_the_registers_own(self):
        assert set(DIMENSIONS) == {"owner", "legal_entity", "domain"}


class TestWhatARecordMustCarry:
    def test_a_period_with_no_end_is_refused(self, cost):
        with pytest.raises(EstateError) as e:
            cost.record(amount=1.0, currency="GBP", period_start=Q1[0],
                        period_end=0, source="x")
        assert e.value.code == "cost_period_end_required"
        assert "comparison is the only use a cost figure has" in \
            e.value.remediation

    def test_an_inverted_period_is_refused(self, cost):
        with pytest.raises(EstateError) as e:
            cost.record(amount=1.0, currency="GBP", period_start=Q1[1],
                        period_end=Q1[0], source="x")
        assert e.value.code == "cost_period_inverted"
        assert "in a direction nobody checks" in e.value.remediation

    def test_a_negative_amount_is_refused(self, cost):
        """Netting a credit here would hide a refund inside a period it did
        not belong to."""
        with pytest.raises(EstateError) as e:
            cost.record(amount=-50.0, currency="GBP", period_start=Q1[0],
                        period_end=Q1[1], source="x")
        assert e.value.code == "cost_negative"

    def test_an_unnamed_source_is_refused(self, cost):
        with pytest.raises(EstateError) as e:
            cost.record(amount=1.0, currency="GBP", period_start=Q1[0],
                        period_end=Q1[1], source="  ")
        assert e.value.code == "cost_source_required"

    def test_a_missing_currency_is_refused(self, cost):
        with pytest.raises(EstateError) as e:
            cost.record(amount=1.0, currency="", period_start=Q1[0],
                        period_end=Q1[1], source="x")
        assert e.value.code == "cost_currency_required"


class TestShowbackReportsTheGap:
    def test_it_cuts_by_a_dimension_the_register_knows(self, cost, a_model):
        _line(cost, a_model["urn"], 900.0)
        out = cost.showback("owner")
        assert out["buckets"][0]["key"] == a_model["owner"]
        assert out["buckets"][0]["amount"] == 900.0

    def test_the_unattributed_share_is_the_headline(self, cost, a_model):
        _line(cost, a_model["urn"], 600.0)
        _line(cost, "", 400.0)
        out = cost.showback("owner")
        assert out["unattributed"] == 400.0
        assert out["unattributed_share"] == 0.4
        assert "until somebody asks who owns it" in out["detail"]

    def test_a_fully_attributed_estate_says_so(self, cost, a_model):
        _line(cost, a_model["urn"], 100.0)
        out = cost.showback("owner")
        assert out["unattributed"] == 0
        assert "rarely reports on" in out["detail"]

    def test_currencies_are_reported_and_not_converted(self, cost, a_model):
        """A total summed across currencies is wrong by the exchange rate, and
        MAYA holds no rate."""
        _line(cost, a_model["urn"], 100.0, currency="GBP")
        _line(cost, a_model["urn"], 100.0, currency="USD")
        out = cost.showback("owner")
        assert out["currencies"] == ["GBP", "USD"]
        assert "NOT converted" in out["detail"]

    def test_an_unknown_dimension_is_refused(self, cost):
        with pytest.raises(EstateError) as e:
            cost.showback("cost_centre")
        assert e.value.code == "unknown_cost_dimension"

    def test_a_window_narrows_the_report(self, cost, a_model):
        _line(cost, a_model["urn"], 500.0)
        assert cost.showback("owner", since=Q1[1] + 10 * DAY)["lines"] == 0
        assert cost.showback("owner", since=Q1[0])["lines"] == 1


class TestABudgetStopsNothing:
    def test_it_says_so_in_the_answer(self, cost, a_model):
        _line(cost, a_model["urn"], 1500.0)
        out = cost.against_budget({a_model["owner"]: 1000.0})
        assert out["enforces_anything"] is False
        assert "Nothing was blocked and nothing will be" in out["detail"]

    def test_a_breach_is_reported_with_the_overrun(self, cost, a_model):
        _line(cost, a_model["urn"], 1500.0)
        out = cost.against_budget({a_model["owner"]: 1000.0})
        assert out["breaches"] == 1
        assert "OVER by 500.00" in out["budgets"][0]["detail"]

    def test_a_budget_with_room_says_what_is_left(self, cost, a_model):
        _line(cost, a_model["urn"], 400.0)
        out = cost.against_budget({a_model["owner"]: 1000.0})
        assert out["breaches"] == 0
        assert "600.00 remaining" in out["budgets"][0]["detail"]

    def test_a_budget_for_somebody_who_spent_nothing_is_not_a_breach(
            self, cost):
        out = cost.against_budget({"person/nobody": 100.0})
        assert out["breaches"] == 0


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/cost").json()
        assert out["observes_cost"] is False

    def test_a_line_is_recorded_and_shown_back(self, client, registered):
        made = client.post("/api/v1/cost", json={
            "amount": 1234.5, "currency": "GBP",
            "period_start": Q1[0], "period_end": Q1[1],
            "source": "cloud-bill", "urn": "maya://model/credit.pd.smallbiz"})
        assert made.status_code == 201, made.text
        out = client.get("/api/v1/cost/showback").json()
        assert out["attributed"] == 1234.5

    def test_an_unattributed_line_is_accepted_and_counted(self, client,
                                                          registered):
        client.post("/api/v1/cost", json={
            "amount": 99.0, "currency": "GBP", "period_start": Q1[0],
            "period_end": Q1[1], "source": "cloud-bill"})
        out = client.get("/api/v1/cost/showback").json()
        assert out["unattributed"] == 99.0

    def test_a_budget_comparison_answers(self, client, registered):
        out = client.post("/api/v1/cost/budgets", json={
            "budgets": {"person/j.okafor": 10.0}, "by": "owner"})
        assert out.status_code == 200
        assert out.json()["enforces_anything"] is False
