"""What a model cannot do, stated where it can be counted.

The operating contract carries what a machine can check — `dscr` between -5 and
20, refused at execution. It cannot carry most of what a model risk manager
writes: *calibrated on 2019–2024 and never through a rate shock above 400bp*,
*assumes the sector mix is stable*, *LGD is a flat haircut and not modelled*.
Those went in a document, and a document cannot be counted, compared between two
versions, or asked the question a supervisor actually asks — **which of these
are enforced and which are only written down?**
"""
from __future__ import annotations

import pytest

from core.limitations import KINDS, LimitationRegister
from core.registry.common import RegistryError

URN = "maya://model/credit.limits"
KERNEL = {"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
          "input_schema": [{"name": "dscr", "dtype": "numeric"}],
          "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]}
CONTRACT = {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
            "guarantees": [{"key": "pd_12m", "minimum": 0, "maximum": 1}]}


@pytest.fixture
def limits(repos, db, registry, evidence):
    from db import LimitationRepository

    registry.register(URN, "Limits", "credit", "retail", "person/o",
                      "LE-US-01", "limitation register")
    registry.create_version(URN, "1.0.0", dict(KERNEL), dict(CONTRACT))
    return LimitationRegister(LimitationRepository(db), registry, evidence)


class TestStatingOne:

    def test_an_unenforced_limitation_is_recorded_and_counted_as_such(self, limits):
        limits.record(URN, "1.0.0", "data",
                      "calibrated on 2019-2024; never through a rate shock "
                      "above 400bp", basis="the calibration window",
                      actor="person/d.raman")
        report = limits.for_version(URN, "1.0.0")
        assert report["standing"] == 1
        assert report["enforced"] == 0 and report["stated_only"] == 1
        assert "relied on a person to remember" in report["detail"]

    def test_a_limitation_may_name_the_clause_that_enforces_it(self, limits):
        limits.record(URN, "1.0.0", "scope",
                      "not valid for a DSCR outside [-5, 20]",
                      bound_key="dscr", actor="person/d.raman")
        report = limits.for_version(URN, "1.0.0")
        assert report["enforced"] == 1 and report["stated_only"] == 0

    def test_a_clause_that_does_not_exist_is_refused(self, limits):
        """The worst of the three states, because it reads as the safe one."""
        with pytest.raises(RegistryError) as refusal:
            limits.record(URN, "1.0.0", "scope", "bounded by turnover",
                          bound_key="turnover")
        assert "no such clause" in str(refusal.value)
        assert "dscr" in str(refusal.value), "name the clauses there are"

    def test_the_kinds_are_closed(self, limits):
        with pytest.raises(RegistryError, match="not a kind"):
            limits.record(URN, "1.0.0", "vibes", "feels wrong")

    def test_a_limitation_with_no_statement_is_refused(self, limits):
        with pytest.raises(RegistryError, match="records that something is"):
            limits.record(URN, "1.0.0", "data", "   ")

    def test_references_are_sequential_within_a_version(self, limits):
        first = limits.record(URN, "1.0.0", "data", "one")
        second = limits.record(URN, "1.0.0", "methodology", "two")
        assert (first["reference"], second["reference"]) == ("LIM-0001",
                                                             "LIM-0002")


class TestWithdrawingOne:

    def test_it_is_withdrawn_rather_than_deleted(self, limits):
        row = limits.record(URN, "1.0.0", "data", "one")
        limits.withdraw(row["id"], "the 2025 recalibration covers it",
                        actor="person/a.mehta")
        report = limits.for_version(URN, "1.0.0")
        assert report["standing"] == 0
        assert len(report["limitations"]) == 1, \
            "the version is immutable, so what it was understood to be stays"
        assert report["limitations"][0]["withdrawal_reason"]

    def test_withdrawing_needs_a_reason(self, limits):
        row = limits.record(URN, "1.0.0", "data", "one")
        with pytest.raises(RegistryError, match="needs a reason"):
            limits.withdraw(row["id"], "  ")

    def test_it_cannot_be_withdrawn_twice(self, limits):
        row = limits.record(URN, "1.0.0", "data", "one")
        limits.withdraw(row["id"], "covered")
        with pytest.raises(RegistryError, match="already withdrawn"):
            limits.withdraw(row["id"], "covered again")


class TestTheCountThatMatters:

    def test_no_limitations_is_itself_a_claim(self, limits):
        report = limits.for_version(URN, "1.0.0")
        assert report["standing"] == 0
        assert "a claim about the model, not an absence of one" in report["detail"]

    def test_the_split_is_the_question_a_supervisor_asks(self, limits):
        limits.record(URN, "1.0.0", "scope", "bounded", bound_key="dscr")
        limits.record(URN, "1.0.0", "data", "2019-2024 only")
        limits.record(URN, "1.0.0", "methodology", "LGD is a flat haircut")
        report = limits.for_version(URN, "1.0.0")
        assert (report["enforced"], report["stated_only"]) == (1, 2)
        assert report["by_kind"] == {"data": 1, "methodology": 1, "scope": 1}

    def test_every_kind_has_a_meaning_written_down(self):
        from core.limitations import KIND_MEANING

        assert set(KIND_MEANING) == set(KINDS)
        assert all(KIND_MEANING[k] for k in KINDS)


class TestOverTheApi:

    def _version(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "Limits", "model_class": "c", "domain": "credit",
            "owner": "person/j.okafor", "legal_entity": "LE-US-01",
            "purpose": "limitation register"})
        client.post("/api/v1/models/credit.limits/versions",
                    auth=people["d.raman"],
                    json={"semver": "1.0.0", "kernel": KERNEL,
                          "contract": CONTRACT})

    def test_the_developer_states_and_the_validator_withdraws(self, client, people):
        self._version(client, people)
        made = client.post(
            "/api/v1/limitations", auth=people["d.raman"],
            json={"urn": URN, "semver": "1.0.0",
                  "kind": "data", "statement": "2019-2024 only",
                  "basis": "the calibration window"})
        assert made.status_code == 201, made.text

        # The first line states them and may not take them back.
        refused = client.post(
            f"/api/v1/limitations/{made.json()['id']}/withdraw",
            auth=people["d.raman"], json={"reason": "no longer holds"})
        assert refused.status_code == 403, refused.text

        done = client.post(
            f"/api/v1/limitations/{made.json()['id']}/withdraw",
            auth=people["a.mehta"], json={"reason": "the 2025 recalibration"})
        assert done.status_code == 200, done.text

    def test_the_report_is_readable_by_anybody_who_reads_the_model(
            self, client, people):
        self._version(client, people)
        client.post("/api/v1/limitations", auth=people["d.raman"],
                    json={"urn": URN, "semver": "1.0.0", "kind": "scope",
                          "statement": "bounded", "bound_key": "dscr"})
        report = client.get("/api/v1/limitations", auth=people["a.mehta"],
                            params={"urn": URN, "semver": "1.0.0"}).json()
        assert report["enforced"] == 1

    def test_the_kinds_are_published(self, client, people):
        body = client.get("/api/v1/limitation-kinds",
                          auth=people["d.raman"]).json()
        assert {k["kind"] for k in body["kinds"]} == set(KINDS)
        assert all(k["means"] for k in body["kinds"])
