"""What a model is used for, as a thing rather than as a string.

`declared_use` on a warrant grant is a string, checked at resolution against the
grant that carries it. That is exactly enough to authorise a call and not enough
for anything else: a string has no owner, no dates, no product and no legal
entity, so risk cannot attach to a use and *which models fed the Q2 provision*
has no answer.
"""
from __future__ import annotations

import time

import pytest

from core.registry.common import RegistryError
from core.registry.uses import DAY, ModelUses
from tests.conftest import URN

OTHER = "maya://model/credit.ecl"


@pytest.fixture
def uses(repos, db, registry, evidence):
    from db import ModelUseRepository

    for urn in (URN, OTHER):
        registry.register(urn, urn.split("/")[-1], "credit", "retail",
                          "person/j.okafor", "LE-US-01", "p")
    return ModelUses(ModelUseRepository(db), registry, evidence)


def _declare(uses, urn=URN, **over):
    args = {"declared_use": "origination_decision", "name": "New lending",
            "owner": "person/head.of.lending", "product": "personal loan",
            "legal_entity": "LE-US-01", "decision_authority": "credit committee"}
    return uses.declare(urn, **{**args, **over})


class TestAUseIsAThing:
    def test_it_records_every_dimension_the_requirement_names(self, uses):
        made = _declare(uses, geography="US", channel="branch",
                        segment="prime")
        for field in ("product", "legal_entity", "geography", "channel",
                      "segment", "decision_authority"):
            assert made[field], f"{field} is one of the eight"
        assert made["reference"] == "USE-0001"

    def test_the_same_model_can_carry_two_risk_propositions(self, uses):
        """A PD model used at origination and for provisioning carries
        different materiality, and a register holding one row for the model
        holds one answer for both."""
        _declare(uses, declared_use="origination_decision", name="New lending")
        _declare(uses, declared_use="provisioning", name="IFRS 9 staging",
                 product="loan book")
        out = uses.for_model(URN)
        assert out["total"] == 2
        assert set(out["by_dimension"]["product"]) == {"personal loan",
                                                       "loan book"}

    def test_a_use_with_no_owner_is_refused(self, uses):
        """The owner of a use is routinely not the owner of the model, which
        is the reason the field is here rather than inherited."""
        with pytest.raises(RegistryError) as exc:
            _declare(uses, owner="")
        assert "not the owner of the model" in str(exc.value)

    def test_a_use_with_no_declared_use_string_is_refused(self, uses):
        with pytest.raises(RegistryError, match="nothing can match a call"):
            _declare(uses, declared_use="  ")

    def test_a_window_that_ends_before_it_begins_is_refused(self, uses):
        now = time.time()
        with pytest.raises(RegistryError, match="never in force"):
            _declare(uses, effective_from=now, effective_to=now - DAY)


class TestTheCommonestFormOfMisuse:
    """Not a use nobody approved — those get refused. A use somebody DID
    approve, for a period that ended, which nobody switched off."""

    def test_a_lapsed_use_is_named_with_how_long_it_has_been_over(self, uses):
        now = time.time()
        _declare(uses, effective_from=now - 100 * DAY,
                 effective_to=now - 30 * DAY)
        out = uses.lapsed()
        assert out["count"] == 1
        assert out["lapsed"][0]["days_over"] == pytest.approx(30, abs=1)
        assert "still authorised" in out["detail"]

    def test_a_use_still_in_its_window_is_not_lapsed(self, uses):
        _declare(uses, effective_to=time.time() + 100 * DAY)
        assert uses.lapsed()["count"] == 0

    def test_a_use_with_no_end_date_never_lapses(self, uses):
        _declare(uses)
        assert uses.lapsed()["count"] == 0

    def test_retiring_it_takes_it_off_the_list(self, uses):
        now = time.time()
        made = _declare(uses, effective_from=now - 100 * DAY,
                        effective_to=now - 30 * DAY)
        uses.retire(made["id"], "the product was withdrawn")
        assert uses.lapsed()["count"] == 0

    def test_retiring_without_a_reason_is_refused(self, uses):
        made = _declare(uses)
        with pytest.raises(RegistryError) as exc:
            uses.retire(made["id"], " ")
        assert "different facts" in str(exc.value)


class TestTheQ2ProvisionQuestion:
    """`at` is the half that makes it worth asking: a use in force today and
    one in force in June are different sets."""

    def test_it_finds_models_in_use_for_a_product(self, uses):
        _declare(uses, product="loan book")
        _declare(uses, OTHER, product="loan book", declared_use="provisioning",
                 name="ECL")
        _declare(uses, product="cards", declared_use="cards_decision",
                 name="Cards")
        out = uses.across_the_estate(product="loan book")
        assert out["models"] == 2

    def test_a_use_not_yet_in_force_at_that_moment_is_excluded(self, uses):
        now = time.time()
        _declare(uses, product="loan book", effective_from=now - 10 * DAY)
        assert uses.across_the_estate(product="loan book",
                                      at=now - 40 * DAY)["count"] == 0
        assert uses.across_the_estate(product="loan book",
                                      at=now)["count"] == 1

    def test_a_use_that_had_ended_by_that_moment_is_excluded(self, uses):
        now = time.time()
        _declare(uses, product="loan book", effective_from=now - 100 * DAY,
                 effective_to=now - 50 * DAY)
        assert uses.across_the_estate(product="loan book",
                                      at=now - 70 * DAY)["count"] == 1
        assert uses.across_the_estate(product="loan book", at=now)["count"] == 0

    def test_nothing_in_use_is_an_answer_and_not_a_shrug(self, uses):
        out = uses.across_the_estate(product="nothing here")
        assert out["count"] == 0
        assert "different one from *we cannot tell*" in out["detail"]


class TestAgainstTheGrants:
    class _Warrants:
        def __init__(self, grants):
            self._grants = grants

        def grants_for(self, urn):
            return self._grants

    def test_a_grant_naming_a_use_nobody_declared_is_reported(
            self, repos, db, registry, evidence):
        """The calls are authorised and nothing describes what they are for."""
        from db import ModelUseRepository

        registry.register(URN, "SB PD", "credit", "retail", "person/o",
                          "LE-US-01", "p")
        uses = ModelUses(
            ModelUseRepository(db), registry, evidence,
            warrants=self._Warrants([{"declared_use": "origination_decision"},
                                     {"declared_use": "stress_testing"}]))
        _declare(uses, declared_use="origination_decision")
        out = uses.for_model(URN)
        assert out["granted_but_undeclared"] == ["stress_testing"]
        assert "nothing describes what they are for" in out["detail"]
        assert out["uses"][0]["has_grant"] is True

    def test_a_model_with_no_declared_use_says_what_that_means(self, uses):
        out = uses.for_model(URN)
        assert "whatever string somebody put on a grant" in out["detail"]
