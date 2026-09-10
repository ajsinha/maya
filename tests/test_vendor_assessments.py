"""Validating a model you did not build.

SR 26-2 VII and SS1/23 2.6 say the same thing, and it is the thing firms get
wrong: you cannot validate what you cannot see, so what is validated is your USE
of the model, not the model. The commonest failure is not laziness — it is a
bank asking the vendor for a validation report, receiving a thorough one, and
filing it.
"""
from __future__ import annotations

import time

import pytest

from core.validation.common import ValidationError
from core.validation.vendor import (ATTESTATION_STANDS_DAYS, CHECKLIST,
                                    CONCLUSIONS, DAY, FIRM, VENDOR,
                                    VendorAssessments)
from tests.conftest import URN


@pytest.fixture
def vendors(db, registry, evidence):
    from db import VendorAssessmentRepository, VendorItemRepository
    return VendorAssessments(VendorAssessmentRepository(db),
                             VendorItemRepository(db), registry, evidence)


@pytest.fixture
def assessment(vendors, a_model):
    return vendors.open(URN, vendor="Acme Analytics", product="RiskScore",
                        version="7.2", artifact_digest="sha256:aaa",
                        actor="a.mehta")


def _answer_all(vendors, reference, stated_at=None, version="7.2"):
    for item, spec in CHECKLIST.items():
        vendors.answer(reference, item, f"answered {item}",
                       stated_at=(stated_at or time.time())
                       if spec["discharged_by"] == VENDOR else None,
                       covers_version=version
                       if spec["discharged_by"] == VENDOR else None,
                       actor="a.mehta")


class TestTheChecklistSaysWhoMustEstablishIt:
    def test_some_items_no_vendor_statement_can_discharge(self):
        out = VendorAssessments.checklist()
        assert out["must_be_established_by_the_firm"]
        assert "own_outcomes" in out["must_be_established_by_the_firm"]
        assert "validates somebody else's work" in out["detail"]

    def test_own_outcomes_is_the_firms(self):
        """The item that actually validates the USE, and the one a supervisor
        asks about first."""
        assert CHECKLIST["own_outcomes"]["discharged_by"] == FIRM

    def test_the_vendors_own_validation_is_worth_nothing_on_its_own(self):
        spec = CHECKLIST["vendor_validation"]
        assert spec["discharged_by"] == VENDOR
        assert "worth nothing on its own" in spec["why"]

    def test_every_item_says_what_it_asks_and_why(self):
        assert all(v["asks"] and v["why"] and v["discharged_by"]
                   for v in CHECKLIST.values())

    def test_an_item_not_on_the_list_is_refused(self, vendors, assessment):
        """A checklist somebody can add a line to is one that quietly loses the
        line nobody wanted to answer."""
        with pytest.raises(ValidationError) as caught:
            vendors.answer(assessment["reference"], "vibes", "good")
        assert "quietly loses the line" in str(caught.value)


class TestOpening:
    def test_every_item_starts_outstanding(self, vendors, assessment):
        out = vendors.status(assessment["reference"])
        assert len(out["outstanding"]) == len(CHECKLIST)
        assert out["complete"] is False

    def test_an_assessment_that_cannot_say_what_it_assessed_is_refused(
            self, vendors, a_model):
        with pytest.raises(ValidationError) as caught:
            vendors.open(URN, vendor="Acme", product="X", version="  ")
        assert "cannot be repeated when the vendor ships" in str(caught.value)

    def test_two_open_at_once_are_refused(self, vendors, assessment):
        with pytest.raises(ValidationError):
            vendors.open(URN, vendor="Acme", product="X", version="8.0")

    def test_it_lands_on_the_evidence_chain(self, vendors, assessment,
                                            registry, evidence):
        model_id = registry.require(URN)["id"]
        kinds = [n["kind"] for n in evidence.for_subject(model_id)]
        assert "vendor_assessment_opened" in kinds


class TestAVendorStatementIsEvidenceThatTheVendorSaidSomething:
    def test_it_needs_a_date(self, vendors, assessment):
        """A vendor statement with no date is one nobody can tell is current."""
        with pytest.raises(ValidationError) as caught:
            vendors.answer(assessment["reference"], "vendor_validation",
                           "they had it validated by a third party")
        assert "nobody can tell is current" in str(caught.value)

    def test_a_firm_item_needs_no_date(self, vendors, assessment):
        row = vendors.answer(assessment["reference"], "own_outcomes",
                             "gini 0.61 on our own book over 2024")
        assert row["state"] == "answered"

    def test_an_old_statement_goes_stale(self, vendors, assessment):
        """A statement older than a year describes a product that has been
        through releases since."""
        vendors.answer(assessment["reference"], "conceptual_basis",
                       "a gradient-boosted scorecard",
                       stated_at=time.time() - (ATTESTATION_STANDS_DAYS + 30) * DAY)
        out = vendors.status(assessment["reference"])
        stale = [s for s in out["stale_attestations"]
                 if s["item"] == "conceptual_basis"]
        assert stale and "releases since" in stale[0]["why_stale"]

    def test_a_statement_about_another_version_is_stale(self, vendors,
                                                        assessment):
        vendors.answer(assessment["reference"], "limitations",
                       "does not cover revolving exposures",
                       stated_at=time.time(), covers_version="6.0")
        out = vendors.status(assessment["reference"])
        stale = [s for s in out["stale_attestations"]
                 if s["item"] == "limitations"]
        assert stale and "installed version is 7.2" in stale[0]["why_stale"]

    def test_an_empty_answer_records_that_somebody_opened_the_form(
            self, vendors, assessment):
        with pytest.raises(ValidationError) as caught:
            vendors.answer(assessment["reference"], "customisation", "  ")
        assert "a real answer and a different one from silence" in str(
            caught.value)

    def test_nothing_changed_is_a_real_answer(self, vendors, assessment):
        """A customised vendor model is neither the vendor's model nor the
        firm's, and both parties will say so when it goes wrong."""
        vendors.answer(assessment["reference"], "customisation",
                       "nothing was changed; used as shipped")
        assert vendors.require(assessment["reference"])["customisation"]


class TestConcluding:
    def test_concluding_fit_with_the_firms_items_open_is_refused(
            self, vendors, assessment):
        """Concluding on vendor statements alone is validating the vendor's
        work rather than your use of it."""
        for item, spec in CHECKLIST.items():
            if spec["discharged_by"] == VENDOR:
                vendors.answer(assessment["reference"], item, "said",
                               stated_at=time.time(), covers_version="7.2")
        with pytest.raises(ValidationError) as caught:
            vendors.conclude(assessment["reference"], "fit_for_use", "looks ok")
        assert "the failure SR 26-2 VII is about" in str(caught.value)

    def test_deciding_not_to_use_it_needs_less(self, vendors, assessment):
        """Deciding not to use something requires less than deciding to."""
        out = vendors.conclude(assessment["reference"], "not_fit",
                               "development population is nothing like ours",
                               actor="a.mehta")
        assert out["conclusion"] == "not_fit"

    def test_a_complete_assessment_concludes(self, vendors, assessment):
        _answer_all(vendors, assessment["reference"])
        out = vendors.conclude(assessment["reference"], "fit_for_use",
                               "own outcomes hold on our book", actor="a.mehta")
        assert out["conclusion"] == "fit_for_use"

    def test_the_conclusions_are_closed(self, vendors, assessment):
        _answer_all(vendors, assessment["reference"])
        with pytest.raises(ValidationError):
            vendors.conclude(assessment["reference"], "seems fine", "n")
        assert set(CONCLUSIONS) == {"fit_for_use", "fit_with_conditions",
                                    "not_fit"}

    def test_a_conclusion_with_no_note_is_refused(self, vendors, assessment):
        _answer_all(vendors, assessment["reference"])
        with pytest.raises(ValidationError) as caught:
            vendors.conclude(assessment["reference"], "fit_for_use", " ")
        assert "the reasoning is what somebody will be asked about" in str(
            caught.value)


class TestTheVersionChange:
    """The failure this module is really about: a vendor upgrades and the firm
    finds out from a release note, or does not."""

    def test_the_same_version_changes_nothing(self, vendors, assessment):
        out = vendors.observe_version(assessment["reference"], version="7.2")
        assert out["changed"] is False

    def test_a_new_version_reopens_it(self, vendors, assessment):
        _answer_all(vendors, assessment["reference"])
        vendors.conclude(assessment["reference"], "fit_for_use", "fine")
        out = vendors.observe_version(assessment["reference"], version="8.0")
        assert out["changed"] is True
        assert vendors.require(assessment["reference"])["state"] == "open"
        assert "an assessment of nothing" in out["detail"]

    def test_every_vendor_statement_goes_outstanding_again(self, vendors,
                                                           assessment):
        """They were made about a release that is no longer installed."""
        _answer_all(vendors, assessment["reference"])
        vendors.observe_version(assessment["reference"], version="8.0")
        out = vendors.status(assessment["reference"])
        outstanding = {e["item"] for e in out["outstanding"]}
        assert outstanding == {k for k, v in CHECKLIST.items()
                               if v["discharged_by"] == VENDOR}

    def test_the_firms_own_work_survives_a_vendor_upgrade(self, vendors,
                                                          assessment):
        """What the firm found out about its own book did not stop being true
        because the vendor shipped."""
        _answer_all(vendors, assessment["reference"])
        vendors.observe_version(assessment["reference"], version="8.0")
        out = vendors.status(assessment["reference"])
        assert not any(e["kind"] == FIRM for e in out["outstanding"])

    def test_a_moved_digest_reopens_it_even_at_the_same_version(self, vendors,
                                                                assessment):
        """The version string identifies what the vendor calls it; the digest
        identifies what is running, and the two part company at every silent
        upgrade."""
        out = vendors.observe_version(assessment["reference"], version="7.2",
                                      artifact_digest="sha256:bbb")
        assert out["changed"] is True and out["digest_moved"] is True

    def test_it_lands_on_the_evidence_chain(self, vendors, assessment,
                                            registry, evidence):
        vendors.observe_version(assessment["reference"], version="8.0")
        model_id = registry.require(URN)["id"]
        kinds = [n["kind"] for n in evidence.for_subject(model_id)]
        assert "vendor_version_changed" in kinds


class TestTheEstate:
    def test_an_estate_with_no_vendor_models_says_so(self, vendors):
        out = vendors.across_the_estate()
        assert out["count"] == 0
        assert "somebody else's" in out["detail"]

    def test_firm_items_outstanding_come_first(self, vendors, assessment):
        out = vendors.across_the_estate()
        assert out["with_firm_items_outstanding"] == 1
        assert "validate the USE rather than the model" in out["detail"]

    def test_stale_attestations_are_counted(self, vendors, assessment):
        vendors.answer(assessment["reference"], "limitations", "none stated",
                       stated_at=time.time(), covers_version="6.0")
        out = vendors.across_the_estate()
        assert out["with_stale_attestations"] == 1


class TestOverHttp:
    def _opened(self, client, people):
        r = client.post("/api/v1/vendor-assessments", auth=people["a.mehta"],
                        json={"urn": URN, "vendor": "Acme Analytics",
                              "product": "RiskScore", "version": "7.2",
                              "artifact_digest": "sha256:aaa"})
        assert r.status_code == 201, r.text
        return r.json()["reference"]

    def test_the_checklist_names_what_only_the_firm_can_establish(self, client,
                                                                  people):
        r = client.get("/api/v1/vendor-checklist", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert "own_outcomes" in body["must_be_established_by_the_firm"]
        assert "validates somebody else's work" in body["detail"]

    def test_an_assessment_is_opened_and_read_back(self, registered, people):
        reference = self._opened(registered, people)
        r = registered.get("/api/v1/vendor-assessments",
                           auth=people["a.mehta"],
                           params={"reference": reference})
        assert r.status_code == 200, r.text
        assert len(r.json()["outstanding"]) == len(CHECKLIST)

    def test_a_vendor_item_without_a_date_is_refused(self, registered,
                                                     people):
        reference = self._opened(registered, people)
        r = registered.post(f"/api/v1/vendor-assessments/{reference}/items",
                            auth=people["a.mehta"],
                            json={"item": "vendor_validation",
                                  "answer": "third-party validated"})
        assert r.status_code >= 400, r.text
        assert "nobody can tell is current" in r.json()["detail"]

    def test_concluding_fit_with_your_own_items_open_is_refused(
            self, registered, people):
        reference = self._opened(registered, people)
        r = registered.post(
            f"/api/v1/vendor-assessments/{reference}/conclude",
            auth=people["a.mehta"],
            json={"conclusion": "fit_for_use", "note": "looks fine"})
        assert r.status_code >= 400, r.text
        assert "the failure SR 26-2 VII is about" in r.json()["detail"]

    def test_a_version_change_reopens_it(self, registered, people):
        reference = self._opened(registered, people)
        r = registered.post(
            f"/api/v1/vendor-assessments/{reference}/version",
            auth=people["a.mehta"],
            json={"version": "8.0", "artifact_digest": "sha256:bbb"})
        assert r.status_code == 200, r.text
        assert r.json()["changed"] is True
        assert "an assessment of nothing" in r.json()["detail"]

    def test_the_screen_says_what_is_actually_validated(self, client, people):
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/vendor-models"})
        body = client.get("/vendor-models").text
        assert "your <em>use</em> of the model, not the model" in body
        assert "how does it perform on your book" in body
