"""Approving something on terms, where the terms are checked by something.

SR 26-2 V permits a model to be used before it is validated *with compensating
controls*. Every institution already does this; what varies is whether the
controls are enforced or promised, and a conditional approval recorded as a
sentence in a committee minute is a promise.
"""
from __future__ import annotations

import time

import pytest

from core.lifecycle.common import LifecycleError
from core.lifecycle.conditions import (ATTESTED, DAY, ENFORCED, KINDS, MAX_DAYS,
                                       ApprovalConditions)
from tests.conftest import URN


@pytest.fixture
def conditions(db, registry, evidence, validation):
    from db import ApprovalConditionRepository
    return ApprovalConditions(ApprovalConditionRepository(db), registry,
                              evidence, validation=validation)


class TestTheVocabularyIsClosed:
    def test_free_text_is_refused_naming_what_can_be_checked(self, conditions,
                                                             a_model):
        """*The model will only be used for low-value cases* is not a control,
        it is a hope with a date on it."""
        with pytest.raises(LifecycleError) as caught:
            conditions.impose(URN, "only low value cases",
                              rationale="r", days=30)
        assert caught.value.code == "unknown_condition"
        assert "a hope with a date on it" in caught.value.detail
        assert "exposure_cap" in caught.value.remediation

    def test_every_kind_says_whether_it_is_enforced_or_attested(self):
        out = ApprovalConditions.vocabulary()
        assert set(out["enforced"]) | set(out["attested"]) == set(KINDS)
        assert out["enforced"] and out["attested"]
        assert all(k["how"] and k["means"] for k in out["kinds"])

    def test_the_distinction_is_stated_rather_than_implied(self):
        """A firm that believes its exposure cap is machine-enforced is worse
        off than one that knows it is a diary entry: the first has stopped
        checking."""
        assert "stopped checking" in ApprovalConditions.vocabulary()["detail"]

    def test_an_exposure_cap_is_honestly_attested(self):
        assert KINDS["exposure_cap"]["enforcement"] == ATTESTED
        assert "does not see the exposure" in KINDS["exposure_cap"]["how"]

    def test_an_environment_restriction_is_enforced(self):
        assert KINDS["environments"]["enforcement"] == ENFORCED


class TestImposingOne:
    def test_a_condition_is_recorded_with_its_enforcement(self, conditions,
                                                          a_model):
        row = conditions.impose(URN, "environments", rationale="not validated",
                                days=60, parameters={"environments": ["uat"]})
        assert row["reference"] == "COND-0001"
        assert row["enforcement"] == ENFORCED

    def test_a_condition_with_no_rationale_is_refused(self, conditions,
                                                      a_model):
        with pytest.raises(LifecycleError) as caught:
            conditions.impose(URN, "validated_by", rationale="  ", days=30)
        assert caught.value.code == "rationale_required"

    def test_an_unbounded_window_is_refused(self, conditions, a_model):
        """A conditional approval with no end date is an unconditional approval
        that has not noticed yet."""
        with pytest.raises(LifecycleError) as caught:
            conditions.impose(URN, "validated_by", rationale="r",
                              days=MAX_DAYS + 1)
        assert caught.value.code == "window_out_of_range"
        assert "lapses into permanence" in caught.value.remediation

    def test_a_condition_missing_its_parameters_is_refused(self, conditions,
                                                           a_model):
        with pytest.raises(LifecycleError) as caught:
            conditions.impose(URN, "exposure_cap", rationale="r", days=30)
        assert caught.value.code == "condition_incomplete"
        assert "amount" in caught.value.detail

    def test_it_lands_on_the_evidence_chain(self, conditions, a_model,
                                            registry, evidence):
        conditions.impose(URN, "validated_by", rationale="r", days=30)
        model_id = registry.require(URN)["id"]
        kinds = [n["kind"] for n in evidence.for_subject(model_id)]
        assert "approval_condition_imposed" in kinds

    def test_a_condition_names_no_version_by_default(self, conditions,
                                                     a_model):
        """A condition on the MODEL outlives its versions, which is what a
        use-before-validation approval usually means. Naming a version would
        silently lift it on the next one."""
        row = conditions.impose(URN, "validated_by", rationale="r", days=30)
        assert row["model_version_id"] is None


class TestTheTermsBiteAtUse:
    def test_an_unconditional_model_is_approved_outright(self, conditions,
                                                         a_model):
        out = conditions.evaluate(URN)
        assert out["holds"] is True
        assert "approved outright" in out["detail"]

    def test_a_wrong_environment_breaks_the_condition(self, conditions,
                                                      a_model):
        conditions.impose(URN, "environments", rationale="not validated",
                          days=60, parameters={"environments": ["uat"]})
        assert conditions.evaluate(URN, "uat")["holds"] is True
        broken = conditions.evaluate(URN, "prod")
        assert broken["holds"] is False
        assert "approved for uat only" in broken["broken"][0]["why"]

    def test_an_expired_condition_is_broken(self, conditions, a_model):
        """A conditional approval that outlives its conditions is an
        unconditional one nobody granted."""
        conditions.impose(URN, "validated_by", rationale="r", days=1)
        out = conditions.evaluate(URN, now=time.time() + 2 * DAY)
        assert out["holds"] is False
        assert "nobody granted" in out["broken"][0]["why"]

    def test_validated_by_holds_once_a_validation_completes(
            self, conditions, registry, validation, a_model, approved_version,
            evidence):
        conditions.impose(URN, "validated_by", rationale="use before val",
                          days=90)
        before = conditions.evaluate(URN)
        assert before["holds"] is True, "not broken until it expires"
        assert "no completed validation yet" in before["holding"][0]["why"]

    def test_a_broken_condition_refuses_resolution(self, warrants, conditions,
                                                   registry, attested_model):
        """Approval is a moment and use is continuous, so a condition checked
        only at approval is a sentence in a minute."""
        from core.execution.errors import WarrantError
        warrants.grants.issue(URN, "prod", "svc/pricer", "origination",
                              actor="s.iqbal")
        conditions.impose(URN, "environments", rationale="not validated",
                          days=60, parameters={"environments": ["uat"]})
        warrants.conditions = conditions
        with pytest.raises(WarrantError) as caught:
            warrants.resolve(URN, "prod", "svc/pricer", "origination")
        assert caught.value.code == "approval_condition_broken"
        assert "not validated" in caught.value.remediation


class TestAttestedConditions:
    def test_an_unconfirmed_one_is_stale_not_broken(self, conditions,
                                                    a_model):
        """MAYA cannot check it, so an unconfirmed one is a control nothing is
        exercising — which is a different fact from its being broken."""
        conditions.impose(URN, "exposure_cap", rationale="limited rollout",
                          days=90,
                          parameters={"amount": 5e7, "currency": "USD"})
        out = conditions.evaluate(URN)
        assert out["holds"] is True
        assert len(out["stale"]) == 1
        assert "nothing is exercising" in out["detail"]

    def test_confirming_it_makes_it_stand(self, conditions, a_model):
        row = conditions.impose(URN, "exposure_cap", rationale="r", days=90,
                                parameters={"amount": 5e7, "currency": "USD"})
        conditions.confirm(row["reference"], "person/j.okafor")
        out = conditions.evaluate(URN)
        assert out["stale"] == []
        assert "standing" in out["holding"][0]["why"]

    def test_a_confirmation_goes_stale_again(self, conditions, a_model):
        row = conditions.impose(URN, "exposure_cap", rationale="r", days=180,
                                parameters={"amount": 5e7, "currency": "USD"},
                                confirm_every_days=7)
        conditions.confirm(row["reference"], "person/j.okafor")
        out = conditions.evaluate(URN, now=time.time() + 30 * DAY)
        assert len(out["stale"]) == 1
        assert "days ago" in out["stale"][0]["why"]

    def test_confirming_an_enforced_condition_is_refused(self, conditions,
                                                         a_model):
        """Confirming something the platform already checks records an opinion
        about a fact."""
        row = conditions.impose(URN, "validated_by", rationale="r", days=30)
        with pytest.raises(LifecycleError) as caught:
            conditions.confirm(row["reference"], "person/j.okafor")
        assert caught.value.code == "not_attested"


class TestDischarging:
    def test_a_condition_is_lifted_with_a_reason(self, conditions, a_model):
        row = conditions.impose(URN, "validated_by", rationale="r", days=30)
        out = conditions.discharge(row["reference"], "validation completed",
                                   actor="s.iqbal")
        assert out["state"] == "discharged"
        assert conditions.evaluate(URN)["conditions"] == 0

    def test_lifting_without_a_reason_is_refused(self, conditions, a_model):
        row = conditions.impose(URN, "validated_by", rationale="r", days=30)
        with pytest.raises(LifecycleError) as caught:
            conditions.discharge(row["reference"], "  ")
        assert caught.value.code == "reason_required"

    def test_it_is_discharged_once(self, conditions, a_model):
        row = conditions.impose(URN, "validated_by", rationale="r", days=30)
        conditions.discharge(row["reference"], "done")
        with pytest.raises(LifecycleError) as caught:
            conditions.discharge(row["reference"], "again")
        assert caught.value.code == "not_active"


class TestTheEstate:
    def test_a_clean_estate_says_so(self, conditions, a_model):
        out = conditions.across_the_estate()
        assert out["count"] == 0
        assert "no model on this estate" in out["detail"]

    def test_it_counts_broken_and_stale_apart(self, conditions, a_model):
        conditions.impose(URN, "exposure_cap", rationale="r", days=90,
                          parameters={"amount": 1e6, "currency": "USD"})
        out = conditions.across_the_estate()
        assert out["count"] == 1
        assert out["broken"] == 0
        assert out["with_stale_attestations"] == 1
        assert "nothing is exercising" in out["detail"]

    def test_a_model_with_broken_terms_is_first(self, conditions, registry,
                                                a_model):
        conditions.impose(URN, "validated_by", rationale="r", days=1)
        out = conditions.across_the_estate(now=time.time() + 2 * DAY)
        assert out["broken"] == 1
        assert out["models"][0]["holds"] is False


class TestOverHttp:
    def test_the_kinds_are_served_with_their_enforcement(self, client, people):
        r = client.get("/api/v1/condition-kinds", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enforced"] and body["attested"]
        assert "stopped checking" in body["detail"]

    def test_a_condition_is_imposed_and_read_back(self, registered, people):
        made = registered.post("/api/v1/approval-conditions",
                               auth=people["s.iqbal"],
                               json={"urn": URN, "kind": "environments",
                                     "rationale": "not yet validated",
                                     "days": 60,
                                     "parameters": {"environments": ["uat"]}})
        assert made.status_code == 201, made.text
        got = registered.get("/api/v1/approval-conditions",
                             auth=people["d.raman"], params={"urn": URN})
        assert got.status_code == 200, got.text
        assert got.json()["active"] == 1

    def test_free_text_is_refused_by_name(self, registered, people):
        r = registered.post("/api/v1/approval-conditions",
                            auth=people["s.iqbal"],
                            json={"urn": URN, "kind": "be careful",
                                  "rationale": "r", "days": 30})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "unknown_condition"

    def test_an_unbounded_window_is_refused(self, registered, people):
        r = registered.post("/api/v1/approval-conditions",
                            auth=people["s.iqbal"],
                            json={"urn": URN, "kind": "validated_by",
                                  "rationale": "r", "days": 3650})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "window_out_of_range"

    def test_an_attested_condition_is_confirmed(self, registered, people):
        made = registered.post("/api/v1/approval-conditions",
                               auth=people["s.iqbal"],
                               json={"urn": URN, "kind": "exposure_cap",
                                     "rationale": "limited rollout",
                                     "days": 90,
                                     "parameters": {"amount": 5e7,
                                                    "currency": "USD"}})
        reference = made.json()["reference"]
        r = registered.post(
            f"/api/v1/approval-conditions/{reference}/confirm",
            auth=people["s.iqbal"], json={"note": "checked the book"})
        assert r.status_code == 200, r.text
        assert r.json()["confirmed_by"]

    def test_the_screen_states_which_controls_are_real(self, client, people):
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/lifecycle-profiles"})
        body = client.get("/lifecycle-profiles").text
        assert "enforced against attested" in body
        assert "the first has stopped checking" in body
