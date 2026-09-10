"""What a capability may spend, checked before it spends it.

`core/assist/providers/remote.py` names this gap in its own docstring: *cost and
rate limits, which are operational, and which is why they are named here rather
than discovered in production*.

The ordering is the whole of it. Everything else about a generation — the prompt
digest, the claims, the oracle verdict, who attested it — is recorded after the
provider answered. A spend figure computed the same way tells you what happened
without stopping it happening, and the requirement's phrase is *hard-enforced at
the gateway*.
"""
from __future__ import annotations

import time

import pytest

from core.assist import AssistError, BudgetRegister, DraftingService, providers
from core.assist.budgets import (BUDGETS, DAY, DEFAULT_BUDGETS,
                                 DEFAULT_WINDOW_DAYS, WARN_AT)

NOW = 1_800_000_000.0


@pytest.fixture
def subject(evidence):
    for kind, payload in (("model_registered", {"name": "SB PD"}),
                          ("risk_assessed", {"tier": 1})):
        evidence.append(kind, "model", "m-1", payload, actor="person/j.okafor")
    return "m-1"


@pytest.fixture
def capability(capabilities):
    return capabilities.register(
        "validation_summary", "Draft a validation summary from the record",
        "B", "mock-1", "sha256:prompt", "person/a.mehta", review_sample=0.0)


@pytest.fixture
def budgets(capabilities, db, evidence):
    from db import SpendRepository
    return BudgetRegister(capabilities, SpendRepository(db), evidence)


def _call(budgets, capability, tokens=0, cost=0.0, steps=1, at=None,
          produced=True, outcome="recorded"):
    """One provider call on the spend ledger, with a known consumption.

    `produced=False` is the call that grounded nothing: the gate refused it, no
    generation row exists, and it cost exactly the same to make.
    """
    return budgets.charge(
        capability["capability_key"], tokens=tokens, cost=cost, steps=steps,
        generation_id="g-1" if produced else None,
        outcome=outcome, at=at)


class TestDeclaringOne:
    def test_a_budget_is_recorded_and_read_back(self, budgets, capability):
        out = budgets.set("validation_summary", tokens=50_000, cost=10.0,
                          steps=100)
        limits = {line["budget"]: line["limit"] for line in out["budgets"]}
        assert limits == {"tokens": 50_000.0, "cost": 10.0, "steps": 100.0}
        assert out["on_default"] == []

    def test_every_budget_says_what_it_bounds(self, budgets, capability):
        out = budgets.of("validation_summary")
        assert {line["budget"] for line in out["budgets"]} == set(BUDGETS)
        assert all(line["means"] for line in out["budgets"])

    def test_a_zero_budget_is_a_suspension_written_as_a_number(self, budgets,
                                                               capability):
        with pytest.raises(AssistError) as caught:
            budgets.set("validation_summary", tokens=0)
        assert caught.value.code == "budget_not_positive"
        assert "suspend the capability instead" in caught.value.remediation

    def test_a_window_of_zero_is_not_a_window(self, budgets, capability):
        with pytest.raises(AssistError) as caught:
            budgets.set("validation_summary", window_days=0)
        assert caught.value.code == "window_not_positive"

    def test_setting_nothing_records_a_decision_nobody_made(self, budgets,
                                                            capability):
        with pytest.raises(AssistError) as caught:
            budgets.set("validation_summary")
        assert caught.value.code == "nothing_to_set"

    def test_it_lands_on_the_evidence_chain(self, budgets, capability,
                                            evidence):
        budgets.set("validation_summary", cost=25.0)
        kinds = [n["kind"] for n in evidence.for_subject(capability["id"])]
        assert "ai_budget_set" in kinds


class TestNoBudgetIsNotUnlimited:
    def test_an_undeclared_capability_runs_on_the_default(self, budgets,
                                                          capability):
        out = budgets.of("validation_summary")
        assert set(out["on_default"]) == set(BUDGETS)
        limits = {line["budget"]: line["limit"] for line in out["budgets"]}
        assert limits == DEFAULT_BUDGETS
        assert "a number anybody chose" in out["detail"]

    def test_declaring_one_leaves_the_others_on_the_default(self, budgets,
                                                            capability):
        out = budgets.set("validation_summary", cost=10.0)
        assert out["on_default"] == ["tokens", "steps"]
        declared = {line["budget"]: line["declared"] for line in out["budgets"]}
        assert declared == {"tokens": False, "cost": True, "steps": False}

    def test_the_window_defaults_too(self, budgets, capability):
        assert budgets.of("validation_summary")["window_days"] == (
            DEFAULT_WINDOW_DAYS)


class TestSpendingIt:
    def test_consumption_accumulates_within_the_window(self, budgets,
                                                       capability):
        budgets.set("validation_summary", tokens=1000)
        for _ in range(3):
            _call(budgets, capability, tokens=100, cost=0.5)
        out = budgets.of("validation_summary")
        spent = {line["budget"]: line["spent"] for line in out["budgets"]}
        assert spent["tokens"] == 300.0
        assert spent["cost"] == 1.5
        assert spent["steps"] == 3.0

    def test_spend_outside_the_window_does_not_count(self, budgets, capability):
        """A rolling window, never a lifetime cap. A lifetime cap is reached
        once and then the capability is dead forever."""
        budgets.set("validation_summary", tokens=1000, window_days=30)
        _call(budgets, capability, tokens=900, at=time.time() - 40 * DAY)
        _call(budgets, capability, tokens=50)
        out = budgets.of("validation_summary")
        spent = {line["budget"]: line["spent"] for line in out["budgets"]}
        assert spent["tokens"] == 50.0
        assert out["within_budget"] is True

    def test_a_call_that_produced_nothing_costs_the_same(self, budgets,
                                                        capability):
        """The finding this requirement turned up. A draft the gate refuses
        leaves NO generation row, so a budget read off the generation log is
        one the least reliable capability could never exhaust."""
        budgets.set("validation_summary", tokens=100)
        _call(budgets, capability, tokens=150, produced=False,
              outcome="nothing_grounded")
        out = budgets.of("validation_summary")
        assert out["exhausted"] == ["tokens"]
        assert out["calls_that_produced_nothing"] == 1

    def test_spend_that_bought_nothing_is_counted_separately(self, budgets,
                                                             capability):
        """The number that says a capability is not working rather than busy."""
        _call(budgets, capability, tokens=10)
        _call(budgets, capability, tokens=10, produced=False,
              outcome="oracle_failed")
        _call(budgets, capability, tokens=10, produced=False,
              outcome="nothing_grounded")
        out = budgets.of("validation_summary")
        assert out["calls_in_window"] == 3
        assert out["calls_that_produced_nothing"] == 2


class TestTheGateway:
    def test_a_capability_within_budget_passes(self, budgets, capability):
        assert budgets.check("validation_summary")["within_budget"] is True

    def test_an_exhausted_budget_refuses_before_the_call(self, budgets,
                                                        capability):
        budgets.set("validation_summary", steps=2)
        for _ in range(2):
            _call(budgets, capability)
        with pytest.raises(AssistError) as caught:
            budgets.check("validation_summary")
        assert caught.value.code == "budget_exhausted"
        assert "an invoice" in caught.value.detail

    def test_the_steps_budget_is_the_one_that_bounds_a_loop(self, budgets,
                                                            capability):
        """A runaway agent is a large number of SMALL calls, and it passes a
        token budget and a cost budget for a long time before either notices."""
        budgets.set("validation_summary", tokens=1_000_000, cost=1000.0,
                    steps=5)
        for _ in range(5):
            _call(budgets, capability, tokens=1, cost=0.001)
        out = budgets.of("validation_summary")
        assert out["exhausted"] == ["steps"]
        by_name = {line["budget"]: line for line in out["budgets"]}
        assert by_name["tokens"]["share"] < 0.01
        assert by_name["cost"]["share"] < 0.01

    def test_exhaustion_refuses_but_does_not_suspend(self, budgets, capability,
                                                     capabilities):
        """Suspending is a governance act somebody takes with a reason, and a
        control that quietly retires a capability for being busy on Tuesday is
        one people work around."""
        budgets.set("validation_summary", steps=1)
        _call(budgets, capability)
        with pytest.raises(AssistError):
            budgets.check("validation_summary")
        assert capabilities.require("validation_summary")["status"] == "active"

    def test_the_refusal_says_when_the_window_refills(self, budgets,
                                                      capability):
        budgets.set("validation_summary", steps=1)
        _call(budgets, capability)
        with pytest.raises(AssistError) as caught:
            budgets.check("validation_summary")
        assert "refills as calls age out" in caught.value.remediation


class TestTheDraftingPath:
    def test_a_draft_records_what_it_consumed(self, generations, capabilities,
                                              capability, evidence, subject,
                                              budgets):
        service = DraftingService(generations, capabilities, evidence,
                                  providers.build("mock"), budgets=budgets)
        service.draft("validation_summary", "model", subject)
        out = budgets.of("validation_summary")
        spent = {line["budget"]: line["spent"] for line in out["budgets"]}
        assert spent["steps"] == 1.0, "one call is one step"
        # The mock provider reports no token count and says so rather than
        # inventing a plausible one. A budget fed invented figures would refuse
        # real work for imaginary reasons.
        assert spent["tokens"] == 0.0

    def test_an_exhausted_budget_stops_the_draft_being_asked_for(
            self, generations, capabilities, capability, evidence, subject,
            budgets):
        budgets.set("validation_summary", steps=1)
        service = DraftingService(generations, capabilities, evidence,
                                  providers.build("mock"), budgets=budgets)
        service.draft("validation_summary", "model", subject)
        before = len(generations.generations.many())
        with pytest.raises(AssistError) as caught:
            service.draft("validation_summary", "model", subject)
        assert caught.value.code == "budget_exhausted"
        assert len(generations.generations.many()) == before, (
            "the refusal must land before anything is recorded")
        assert budgets.of("validation_summary")["calls_in_window"] == 1, (
            "a call that was never made must not be charged for")

    def test_without_a_budget_register_drafting_still_works(
            self, generations, capabilities, capability, evidence, subject):
        """Optional, and when it is absent nothing is claimed."""
        service = DraftingService(generations, capabilities, evidence,
                                  providers.build("mock"))
        assert service.draft("validation_summary", "model", subject)


class TestTheEstate:
    def test_it_names_which_capabilities_run_on_a_default(self, budgets,
                                                          capabilities,
                                                          capability):
        capabilities.register("probe_generation", "Propose probes", "B",
                              "mock-1", "sha256:p2", "person/d.raman",
                              review_sample=0.0)
        budgets.set("validation_summary", tokens=10_000, cost=5.0, steps=50)
        out = budgets.across_the_estate()
        assert out["count"] == 2
        assert out["on_default"] == 1
        assert "a number nobody chose" in out["detail"]

    def test_the_closest_to_its_limit_is_first(self, budgets, capabilities,
                                               capability):
        second = capabilities.register(
            "probe_generation", "Propose probes", "B", "mock-1", "sha256:p2",
            "person/d.raman", review_sample=0.0)
        budgets.set("validation_summary", steps=100)
        budgets.set("probe_generation", steps=10)
        for _ in range(9):
            _call(budgets, second)
        out = budgets.across_the_estate()
        assert out["capabilities"][0]["capability_key"] == "probe_generation"

    def test_a_capability_past_the_warning_line_says_so_before_it_stops(
            self, budgets, capability):
        """Raising a budget is a decision better made before the work stops."""
        budgets.set("validation_summary", steps=10)
        for _ in range(int(10 * WARN_AT)):
            _call(budgets, capability)
        out = budgets.of("validation_summary")
        assert out["within_budget"] is True
        assert any(line["near"] for line in out["budgets"])
        assert "before the work stops" in out["detail"]


class TestOverHttp:
    """The gateway as a client meets it."""

    def _capability(self, client, people):
        r = client.post("/api/v1/assist/capabilities", auth=people["s.iqbal"],
                        json={"capability_key": "validation_summary",
                              "description": "Draft a validation summary",
                              "tier": "B", "base_model": "mock-1",
                              "prompt_digest": "sha256:prompt",
                              "owner": "person/a.mehta", "review_sample": 0.0})
        assert r.status_code == 201, r.text
        return "validation_summary"

    def test_an_unbudgeted_capability_reads_as_on_the_default(self, client,
                                                              people):
        key = self._capability(client, people)
        r = client.get(f"/api/v1/assist/budgets/{key}", auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body["on_default"]) == set(BUDGETS)
        assert body["within_budget"] is True

    def test_a_budget_is_set_and_read_back(self, client, people):
        key = self._capability(client, people)
        put = client.put(f"/api/v1/assist/budgets/{key}",
                         auth=people["s.iqbal"],
                         json={"tokens": 25_000, "steps": 40,
                               "window_days": 7})
        assert put.status_code == 200, put.text
        assert put.json()["window_days"] == 7.0
        limits = {line["budget"]: line["limit"]
                  for line in put.json()["budgets"]}
        assert limits["tokens"] == 25_000.0 and limits["steps"] == 40.0

    def test_a_zero_budget_is_refused_by_name(self, client, people):
        key = self._capability(client, people)
        r = client.put(f"/api/v1/assist/budgets/{key}", auth=people["s.iqbal"],
                       json={"cost": 0})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "budget_not_positive"

    def test_the_estate_view_names_what_runs_on_a_default(self, client,
                                                          people):
        self._capability(client, people)
        r = client.get("/api/v1/assist/budgets", auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1 and body["on_default"] == 1
        assert body["calls_that_produced_nothing"] == 0

    def test_the_screen_shows_the_budgets(self, client, people):
        self._capability(client, people)
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/assist"})
        body = client.get("/assist").text
        assert "afterwards is an invoice" in body
        assert "calls that bought nothing" in body
