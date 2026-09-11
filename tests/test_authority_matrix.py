"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

FR-LC-005: by amount, by entity, in order — and what an unknown amount counts as.

The quorum by tier was built and enforced. What a tier cannot express is that a
$2bn book and a $4m book are not the same decision, that authority is granted by
an entity's board and does not travel, and that a challenge signed before there
is anything to challenge is a signature about nothing.

**Most of these tests are about one line.** An unknown amount compares as less
than every floor, so the natural implementation of an amount-banded matrix falls
to the shallowest band and approves everything — while reporting itself as
enforced. The band for an unsourced model is therefore the *deepest* its tier
admits, and the answer says the band was reached by absence.
"""
from __future__ import annotations

import time

import pytest

from core.lifecycle.approval import VersionApproval
from core.lifecycle.authority import (BY_ABSENCE, REQUIRED, STANDS_FOR_DAYS,
                                      AuthorityMatrix)
from core.lifecycle.common import LifecycleError
from core.risk.sourcing import FactSourcing
from db import (AuthorityBandRepository, AuthorityDelegationRepository,
                TieringFactSourceRepository, VersionApprovalRepository,
                VersionApprovalSignatureRepository)

BIG = {"name": "tier-1-large", "tier": 1, "at_or_above": 1e9,
       "stages": [["model_risk_manager"], ["validator"]]}
SMALL = {"name": "tier-1-small", "tier": 1, "at_or_above": 0.0,
         "stages": [["validator"]]}


@pytest.fixture
def sourcing(db, registry, evidence):
    return FactSourcing(TieringFactSourceRepository(db), registry, evidence)


@pytest.fixture
def authority(db, registry, sourcing, evidence):
    return AuthorityMatrix(AuthorityBandRepository(db),
                           AuthorityDelegationRepository(db), registry,
                           sourcing=sourcing, evidence=evidence)


def _expose(sourcing, model, value):
    sourcing.record(model["id"], "exposure", source="finance.ledger",
                    reference="GL-2026-Q3", value=value, as_at=time.time())


class TestNothingChangesUntilSomebodyPublishes:
    def test_an_unpublished_matrix_is_not_consulted(self, authority):
        assert authority.published() is False

    def test_the_shipped_bands_mirror_the_tier_quorum(self, authority):
        """A feature that deepens every approval in the estate the moment it
        is deployed is a feature switched off before anybody reads it."""
        names = {b["name"] for b in authority.matrix()}
        assert names == {"tier-1", "tier-2"}

    def test_version_approval_uses_the_tier_quorum_while_unpublished(
            self, db, registry, evidence, authority, a_model):
        approvals = _approvals(db, registry, evidence, authority)
        assert approvals.roles_for(a_model) == ("model_risk_manager", "validator")
        assert approvals.banded(a_model) is None


class TestAnAmountThisRegisterDoesNotHave:
    def test_the_band_is_the_deepest_the_tier_admits(self, authority, a_model):
        """Not the shallowest. This is the whole design problem: an unknown
        amount compares as less than every floor."""
        authority.publish(SMALL)
        authority.publish(BIG)
        out = authority.required_for(a_model["urn"])
        assert out["band"] == "tier-1-large"
        assert out["amount"] is None

    def test_the_answer_says_it_was_reached_by_absence(self, authority,
                                                       a_model):
        authority.publish(SMALL)
        authority.publish(BIG)
        out = authority.required_for(a_model["urn"])
        assert out["reached_by"] == BY_ABSENCE
        assert "not a small amount" in out["detail"]
        assert "fact-sourcing" in out["detail"]

    def test_sourcing_the_exposure_decides_it_by_measurement(self, authority,
                                                             sourcing,
                                                             a_model):
        authority.publish(SMALL)
        authority.publish(BIG)
        _expose(sourcing, a_model, 4_000_000)
        out = authority.required_for(a_model["urn"])
        assert out["band"] == "tier-1-small"
        assert out["reached_by"] == "match"
        assert out["amount"] == 4_000_000

    def test_a_large_sourced_exposure_reaches_the_deep_band_honestly(
            self, authority, sourcing, a_model):
        authority.publish(SMALL)
        authority.publish(BIG)
        _expose(sourcing, a_model, 2_000_000_000)
        out = authority.required_for(a_model["urn"])
        assert out["band"] == "tier-1-large"
        assert out["reached_by"] == "match"
        assert "GL-2026-Q3" in out["detail"]

    def test_the_assessments_own_figure_is_never_used(self, db, registry,
                                                      evidence, a_model):
        """A figure typed into the tiering form would let the amount that
        decides the approval depth be chosen by whoever wants the approval."""
        blind = AuthorityMatrix(AuthorityBandRepository(db),
                                AuthorityDelegationRepository(db), registry,
                                sourcing=None, evidence=evidence)
        blind.publish(SMALL)
        blind.publish(BIG)
        assert blind.required_for(a_model["urn"])["amount"] is None

    def test_the_posture_names_the_trap(self):
        out = AuthorityMatrix.posture()
        assert "not a small amount" in out["when_the_amount_is_unknown"]
        assert "sourced exposure" in out["amount_comes_from"]


class TestTheMatrixIsMatchedMostSpecificFirst:
    def test_an_entity_row_beats_a_general_one(self, authority, sourcing,
                                               a_model):
        authority.publish(SMALL)
        authority.publish({"name": "us-broker-dealer", "tier": 1,
                           "legal_entity": "LE-US-01",
                           "stages": [["model_risk_manager"], ["validator"]]})
        _expose(sourcing, a_model, 10_000)
        assert authority.required_for(a_model["urn"])["band"] == \
            "us-broker-dealer"

    def test_a_row_for_another_entity_does_not_reach(self, authority,
                                                     sourcing, a_model):
        authority.publish(SMALL)
        authority.publish({"name": "lux-fund", "tier": 1,
                           "legal_entity": "LE-LU-09",
                           "stages": [["model_risk_manager"], ["validator"]]})
        _expose(sourcing, a_model, 10_000)
        assert authority.required_for(a_model["urn"])["band"] == "tier-1-small"

    def test_a_tier_with_no_band_is_one_signature(self, authority, registry,
                                                  a_model):
        authority.publish(BIG)
        registry.set_tier(a_model["id"], 4)
        out = authority.required_for(a_model["urn"])
        assert out["required_roles"] == []
        assert "one authorised person" in out["detail"]


class TestPublishingARow:
    def test_a_band_with_no_stages_is_refused(self, authority):
        with pytest.raises(LifecycleError) as e:
            authority.publish({"name": "empty", "tier": 1, "stages": []})
        assert e.value.code == "stages_required"

    def test_a_nameless_band_is_refused_because_rows_get_quoted(self,
                                                                authority):
        with pytest.raises(LifecycleError) as e:
            authority.publish({"stages": [["validator"]]})
        assert e.value.code == "band_name_required"
        assert "'row 4' quotes badly" in e.value.remediation

    def test_two_rows_with_one_name_are_refused(self, authority):
        authority.publish(SMALL)
        with pytest.raises(LifecycleError) as e:
            authority.publish(SMALL)
        assert e.value.code == "band_exists"

    def test_a_tier_the_platform_does_not_have_is_refused(self, authority):
        with pytest.raises(LifecycleError) as e:
            authority.publish({"name": "t9", "tier": 9,
                               "stages": [["validator"]]})
        assert e.value.code == "unknown_tier"

    def test_withdrawing_leaves_open_approvals_alone(self, authority):
        authority.publish(SMALL)
        out = authority.withdraw("tier-1-small")
        assert "re-decided closed questions" in out["detail"]
        assert authority.published() is False


class TestSequenceIsTheControl:
    def test_the_second_stage_does_not_open_first(self, authority):
        with pytest.raises(LifecycleError) as e:
            AuthorityMatrix.refuse_out_of_sequence(BIG["stages"], "validator",
                                                   [])
        assert e.value.code == "out_of_sequence"
        assert "a signature about nothing" in e.value.remediation

    def test_the_first_stage_signs_freely(self):
        AuthorityMatrix.refuse_out_of_sequence(BIG["stages"],
                                               "model_risk_manager", [])

    def test_once_the_first_stage_closes_the_second_opens(self):
        AuthorityMatrix.refuse_out_of_sequence(BIG["stages"], "validator",
                                               ["model_risk_manager"])

    def test_a_single_stage_band_is_not_sequenced(self, authority, sourcing,
                                                  a_model):
        authority.publish({"name": "flat", "tier": 1,
                           "stages": [["model_risk_manager", "validator"]]})
        _expose(sourcing, a_model, 10_000)
        out = authority.required_for(a_model["urn"])
        assert out["sequenced"] is False
        AuthorityMatrix.refuse_out_of_sequence(out["stages"], "validator", [])

    def test_it_reports_which_stage_is_open(self):
        out = AuthorityMatrix.stage_open(BIG["stages"], [])
        assert out["stage"] == 0 and out["outstanding"] == ["model_risk_manager"]
        assert out["complete"] is False

    def test_sequencing_reads_the_stages_and_never_the_matrix(self, authority,
                                                              a_model):
        """The read that answers *what would this be sequenced as* is separate
        from the check, and only the read consults the matrix."""
        authority.publish(BIG)
        out = authority.sequence_for(a_model["urn"])
        assert out["band"] == "tier-1-large" and out["sequenced"] is True


class TestDelegationsAreTraceableOrTheyAreNotDelegations:
    def test_an_instrument_is_required(self, authority):
        with pytest.raises(LifecycleError) as e:
            authority.delegate("s.iqbal", ceiling=5e8, instrument=" ")
        assert e.value.code == "instrument_required"
        assert "somebody's recollection" in e.value.remediation

    def test_every_required_field_says_why_it_is_asked_for(self):
        assert len(REQUIRED) == 3
        assert all(why.strip() for _f, why in REQUIRED)

    def test_a_ceiling_of_zero_delegates_nothing(self, authority):
        with pytest.raises(LifecycleError) as e:
            authority.delegate("s.iqbal", ceiling=0, instrument="BR-2026-04")
        assert e.value.code == "ceiling_required"

    def test_a_ceiling_that_is_not_a_number_is_refused(self, authority):
        with pytest.raises(LifecycleError) as e:
            authority.delegate("s.iqbal", ceiling="lots",
                               instrument="BR-2026-04")
        assert e.value.code == "ceiling_required"

    def test_it_expires_and_says_why(self, authority):
        out = authority.delegate("s.iqbal", ceiling=5e8,
                                 instrument="BR-2026-04")
        assert out["expires_at"] > out["granted_at"]
        assert "the reference, not the resolution" in out["detail"]
        assert str(STANDS_FOR_DAYS) in out["detail"]

    def test_an_expired_delegation_is_not_held(self, authority):
        authority.delegate("s.iqbal", ceiling=5e8, instrument="BR-2026-04")
        later = time.time() + (STANDS_FOR_DAYS + 1) * 86400
        assert authority.held_by("s.iqbal", now=later) == []


class TestWhoseWritReaches:
    def test_nothing_is_refused_until_somebody_records_a_delegation(
            self, authority, a_model):
        """A control that refuses the whole estate the day it is switched on
        is a control switched off the same day."""
        authority.refuse_beyond_delegation(a_model["urn"],
                                           {"username": "s.iqbal"})

    def test_a_person_with_no_delegation_is_refused_once_others_have_one(
            self, authority, a_model):
        authority.delegate("s.iqbal", ceiling=5e8, instrument="BR-2026-04")
        with pytest.raises(LifecycleError) as e:
            authority.refuse_beyond_delegation(a_model["urn"],
                                               {"username": "a.mehta"})
        assert e.value.code == "no_delegated_authority"

    def test_authority_does_not_travel_between_entities(self, authority,
                                                        a_model):
        authority.delegate("s.iqbal", ceiling=5e8, instrument="BR-2026-04",
                           legal_entity="LE-LU-09")
        with pytest.raises(LifecycleError) as e:
            authority.refuse_beyond_delegation(a_model["urn"],
                                               {"username": "s.iqbal"})
        assert e.value.code == "entity_out_of_delegation"
        assert "does not travel" in e.value.remediation

    def test_an_exposure_above_the_ceiling_is_refused(self, authority,
                                                      sourcing, a_model):
        authority.delegate("s.iqbal", ceiling=5e8, instrument="BR-2026-04")
        _expose(sourcing, a_model, 2_000_000_000)
        with pytest.raises(LifecycleError) as e:
            authority.refuse_beyond_delegation(a_model["urn"],
                                               {"username": "s.iqbal"})
        assert e.value.code == "beyond_delegated_authority"
        assert "system of record" in e.value.remediation

    def test_an_exposure_below_the_ceiling_passes(self, authority, sourcing,
                                                  a_model):
        authority.delegate("s.iqbal", ceiling=5e8, instrument="BR-2026-04")
        _expose(sourcing, a_model, 4_000_000)
        authority.refuse_beyond_delegation(a_model["urn"],
                                           {"username": "s.iqbal"})

    def test_an_unknown_amount_does_not_refuse_a_second_time(self, authority,
                                                             a_model):
        """The deepening already happened when the band was chosen. Refusing
        twice for one absence teaches that the matrix is arbitrary."""
        authority.delegate("s.iqbal", ceiling=1.0, instrument="BR-2026-04")
        authority.refuse_beyond_delegation(a_model["urn"],
                                           {"username": "s.iqbal"})


class TestThroughVersionApproval:
    def test_a_published_band_decides_the_required_roles(
            self, db, registry, evidence, authority, sourcing, a_model):
        authority.publish(SMALL)
        _expose(sourcing, a_model, 10_000)
        approvals = _approvals(db, registry, evidence, authority)
        assert approvals.roles_for(a_model) == ("validator",)

    def test_the_band_is_written_onto_the_approval(
            self, db, registry, evidence, authority, sourcing, a_model,
            kernel_spec, contract_spec):
        authority.publish(BIG)
        approvals = _approvals(db, registry, evidence, authority)
        registry.create_version(a_model["urn"], "1.0.0", kernel_spec,
                                contract_spec,
                                artifact_digest="sha256:" + "b" * 64)
        row = approvals.open(a_model["urn"], "1.0.0", actor="s.iqbal")
        assert row["band"] == "tier-1-large"

    def test_signing_out_of_order_is_refused_through_the_service(
            self, db, registry, evidence, authority, a_model, kernel_spec,
            contract_spec):
        authority.publish(BIG)
        approvals = _approvals(db, registry, evidence, authority)
        registry.create_version(a_model["urn"], "1.0.0", kernel_spec,
                                contract_spec,
                                artifact_digest="sha256:" + "c" * 64)
        row = approvals.open(a_model["urn"], "1.0.0", actor="s.iqbal")
        with pytest.raises(LifecycleError) as e:
            approvals.sign(row["id"],
                           {"username": "a.mehta", "roles": ["validator"]},
                           "validator")
        assert e.value.code == "out_of_sequence"

    def test_in_order_completes_the_quorum(
            self, db, registry, evidence, authority, a_model, kernel_spec,
            contract_spec):
        authority.publish(BIG)
        approvals = _approvals(db, registry, evidence, authority)
        registry.create_version(a_model["urn"], "1.0.0", kernel_spec,
                                contract_spec,
                                artifact_digest="sha256:" + "d" * 64)
        row = approvals.open(a_model["urn"], "1.0.0", actor="s.iqbal")
        approvals.sign(row["id"], {"username": "s.iqbal",
                                   "roles": ["model_risk_manager"]},
                       "model_risk_manager")
        out = approvals.sign(row["id"],
                             {"username": "a.mehta", "roles": ["validator"]},
                             "validator")
        assert out["status"] == "approved"


class TestWhatTheAdversarialPassFound:
    """Four holes, found by attacking this module after it shipped.

    Three of them are the same shape: a control that reports itself as enforced
    while something quietly relaxes it.
    """

    def test_withdrawing_a_band_cannot_move_the_bar_under_an_open_approval(
            self, db, registry, evidence, authority, a_model, kernel_spec,
            contract_spec):
        """The `band` column's own comment claimed this could not happen, and
        it could: sequencing was re-derived from the LIVE matrix at signing
        time, so an administrator could relax the order people were already
        signing under. The stages travel with the approval now."""
        authority.publish(BIG)
        approvals = _approvals(db, registry, evidence, authority)
        registry.create_version(a_model["urn"], "1.0.0", kernel_spec,
                                contract_spec,
                                artifact_digest="sha256:" + "e" * 64)
        row = approvals.open(a_model["urn"], "1.0.0", actor="s.iqbal")
        assert row["stages"] == [["model_risk_manager"], ["validator"]]
        authority.publish({"name": "flat", "tier": 1,
                           "stages": [["validator", "model_risk_manager"]]})
        authority.withdraw("tier-1-large")
        with pytest.raises(LifecycleError) as e:
            approvals.sign(row["id"],
                           {"username": "a.mehta", "roles": ["validator"]},
                           "validator")
        assert e.value.code == "out_of_sequence"

    def test_a_ceiling_in_another_currency_is_not_compared(self, authority,
                                                           sourcing, a_model):
        """500,000,000 JPY silently authorised a 200,000,000 exposure. Nothing
        in the register records a currency on an exposure — the tiering bands
        do not either — so the estate-wide assumption is now stated and a
        ceiling outside it refuses rather than passes."""
        authority.delegate("s.iqbal", ceiling=5e8, instrument="BR-2026-04",
                           currency="JPY")
        _expose(sourcing, a_model, 2e8)
        with pytest.raises(LifecycleError) as e:
            authority.refuse_beyond_delegation(a_model["urn"],
                                               {"username": "s.iqbal"})
        assert e.value.code == "ceiling_not_comparable"
        assert "many times its size" in e.value.remediation

    def test_a_ceiling_in_the_reporting_currency_still_compares(self,
                                                                authority,
                                                                sourcing,
                                                                a_model):
        authority.delegate("s.iqbal", ceiling=5e8, instrument="BR-2026-04")
        _expose(sourcing, a_model, 2e8)
        authority.refuse_beyond_delegation(a_model["urn"],
                                           {"username": "s.iqbal"})

    def test_the_posture_states_the_currency_every_exposure_is_read_as(self):
        out = AuthorityMatrix.posture()
        assert out["reporting_currency"] == "USD"
        assert "no unit" in out["why_one_currency"]

    def test_losing_the_publish_race_is_a_refusal_not_a_five_hundred(
            self, db, registry, sourcing, evidence):
        """The check is a read-then-write and the unique index decides it.
        Losing a race is not a different answer from being told the name is
        taken."""
        matrix = AuthorityMatrix(AuthorityBandRepository(db),
                                 AuthorityDelegationRepository(db), registry,
                                 sourcing=sourcing, evidence=evidence)
        matrix.publish(BIG)
        blind = AuthorityMatrix(AuthorityBandRepository(db),
                                AuthorityDelegationRepository(db), registry,
                                sourcing=sourcing, evidence=evidence)
        blind.bands.one = lambda **_k: None
        with pytest.raises(LifecycleError) as e:
            blind.publish(BIG)
        assert e.value.code == "band_exists"


class TestTheEstateView:
    def test_it_counts_models_with_no_attested_amount(self, authority,
                                                      a_model):
        out = authority.across_the_estate()
        assert out["without_a_sourced_amount"] == 1
        assert "safe direction and it is not the useful one" in out["detail"]

    def test_it_says_when_no_matrix_is_published(self, authority, a_model):
        assert "No matrix is published" in authority.across_the_estate()["detail"]

    def test_it_names_whose_delegation_has_lapsed(self, authority, a_model):
        authority.delegate("s.iqbal", ceiling=5e8, instrument="BR-2026-04")
        later = time.time() + (STANDS_FOR_DAYS + 1) * 86400
        out = authority.across_the_estate(now=later)
        assert out["expired"] == ["s.iqbal"]
        assert "grant nothing until they are re-attested" in out["detail"]


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/authority").json()
        assert out["dimensions"] == ["tier", "amount", "legal_entity"]
        assert len(out["matrix"]) == 2

    def test_a_band_is_published_over_the_wire(self, client, people):
        out = client.post("/api/v1/authority/bands", auth=people["s.iqbal"],
                          json=SMALL)
        assert out.status_code == 201, out.text
        assert out.json()["name"] == "tier-1-small"

    def test_a_band_with_no_stages_is_refused_over_the_wire(self, client,
                                                            people):
        out = client.post("/api/v1/authority/bands", auth=people["s.iqbal"],
                          json={"name": "empty", "stages": []})
        assert out.status_code == 422
        assert "stages_required" in out.text

    def test_a_delegation_with_no_instrument_is_refused(self, client, people):
        out = client.post("/api/v1/authority/delegations",
                          auth=people["s.iqbal"],
                          json={"principal": "s.iqbal", "ceiling": 5e8,
                                "instrument": "  "})
        assert out.status_code == 422
        assert "instrument_required" in out.text

    def test_one_model_answers(self, client, registered):
        out = client.get("/api/v1/authority/model",
                         params={"urn": "maya://model/credit.pd.smallbiz"})
        assert out.status_code == 200
        assert "reached_by" in out.json()

    def test_the_estate_answers(self, client, registered):
        out = client.get("/api/v1/authority/estate")
        assert out.status_code == 200
        assert "without_a_sourced_amount" in out.json()


def _approvals(db, registry, evidence, authority):
    return VersionApproval(VersionApprovalRepository(db),
                           VersionApprovalSignatureRepository(db),
                           registry, evidence, authority=authority)
