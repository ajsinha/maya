"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

FR-SEC-005: the half a rule engine cannot reach, and the answer never inferred.

Incompatible role pairs are refused when access is granted. What nothing catches
is access that was correct when it was granted and stopped being correct
afterwards — somebody moved desk, a secondment ended, a project closed. None of
that changes a role, so nothing in the rule engine ever fires.

**Most of these tests are about one number.** Every access review tool times out:
some close an unanswered item as confirmed, some close it silently, and both
report a completed review. The access nobody looked at is the access most likely
to be wrong, because the reviewer did not answer for the same reason the access
is stale — they did not know who this person was. So `unreviewed` never becomes
`confirmed`, closing decides nothing, and there is no setting that adds them.
"""
from __future__ import annotations

import time

import pytest

from core.authz.common import AuthzError
from core.authz.recertification import (CONFIRMED, DORMANT_AFTER_DAYS, REVOKED,
                                        UNREVIEWED, Recertification)
from db import RecertificationItemRepository, RecertificationRepository
from tests.conftest import PEOPLE


@pytest.fixture
def staffed(principals):
    """The suite's four duties, as accounts rather than as HTTP credentials."""
    for username, (roles, secret) in PEOPLE.items():
        principals.create(username, username, roles, password=secret)
    return principals


@pytest.fixture
def review(db, staffed, evidence):
    return Recertification(RecertificationRepository(db),
                           RecertificationItemRepository(db), staffed,
                           evidence=evidence)


class TestItNeverTimesOut:
    def test_the_posture_says_so(self):
        out = Recertification.posture()
        assert out["times_out"] is False
        assert out["unanswered_is"] == UNREVIEWED

    def test_it_says_why(self):
        assert "did not know who this person was" in \
            Recertification.posture()["why_no_timeout"]

    def test_an_unanswered_item_stays_unreviewed_after_closing(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        out = review.close("ACC-2026-Q3")
        assert out["confirmed"] == 0
        assert out["unreviewed"] == out["population"]
        assert "closing decided nothing about them" in out["detail"]

    def test_confirmed_and_unreviewed_are_reported_separately(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                      actor="s.iqbal")
        out = review.status("ACC-2026-Q3")
        assert out["confirmed"] == 1
        assert out["unreviewed"] == out["population"] - 1
        assert "nobody looked at" in out["detail"]

    def test_the_unreviewed_accounts_are_named(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal",
                    population=["a.mehta", "j.okafor"])
        review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                      actor="s.iqbal")
        assert review.status("ACC-2026-Q3")["unreviewed_accounts"] == \
            ["j.okafor"]

    def test_there_is_no_third_answer(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        with pytest.raises(AuthzError) as e:
            review.answer("ACC-2026-Q3", "a.mehta", state="unsure",
                          actor="s.iqbal")
        assert e.value.code == "unknown_answer"
        assert "no 'unsure'" in e.value.remediation


class TestTheThreeRefusals:
    def test_nobody_recertifies_their_own_access(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        with pytest.raises(AuthzError) as e:
            review.answer("ACC-2026-Q3", "s.iqbal", state=CONFIRMED,
                          actor="s.iqbal")
        assert e.value.code == "self_recertification"
        assert "nothing to think about" in e.value.remediation

    def test_a_revocation_needs_a_reason(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        with pytest.raises(AuthzError) as e:
            review.answer("ACC-2026-Q3", "a.mehta", state=REVOKED,
                          actor="s.iqbal")
        assert e.value.code == "reason_required"
        assert "administrative mistake" in e.value.remediation

    def test_a_confirmation_needs_none(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                      actor="s.iqbal")

    def test_a_campaign_over_nobody_is_refused(self, review, db):
        """An empty review that closes clean is a control reporting an
        all-clear over an estate it never saw."""
        db.execute("UPDATE principal SET status = 'suspended'")
        with pytest.raises(AuthzError) as e:
            review.open("ACC-2026-Q3", reviewer="s.iqbal")
        assert e.value.code == "empty_population"
        assert "an estate it never saw" in e.value.remediation

    def test_two_campaigns_with_one_reference_are_refused(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        with pytest.raises(AuthzError) as e:
            review.open("ACC-2026-Q3", reviewer="s.iqbal")
        assert e.value.code == "campaign_exists"

    def test_a_nameless_campaign_is_refused(self, review):
        with pytest.raises(AuthzError) as e:
            review.open("  ", reviewer="s.iqbal")
        assert e.value.code == "reference_required"
        assert "quoted in an audit finding" in e.value.remediation

    def test_somebody_outside_the_population_cannot_be_answered(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal",
                    population=["a.mehta"])
        with pytest.raises(AuthzError) as e:
            review.answer("ACC-2026-Q3", "j.okafor", state=CONFIRMED,
                          actor="s.iqbal")
        assert e.value.code == "not_in_population"

    def test_a_closed_campaign_takes_no_more_answers(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        review.close("ACC-2026-Q3")
        with pytest.raises(AuthzError) as e:
            review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                          actor="s.iqbal")
        assert e.value.code == "campaign_closed"


class TestRevokingRemovesRolesHereAndNowhereElse:
    def test_the_roles_go_in_this_register(self, review, staffed):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        out = review.answer("ACC-2026-Q3", "a.mehta", state=REVOKED,
                            reason="the secondment ended in June",
                            actor="s.iqbal")
        assert out["roles_removed_in_maya"] == ["validator"]
        assert staffed.require("a.mehta")["roles"] == []

    def test_it_says_what_it_did_not_touch(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        out = review.answer("ACC-2026-Q3", "a.mehta", state=REVOKED,
                            reason="the secondment ended in June",
                            actor="s.iqbal")
        assert "IN THIS REGISTER" in out["detail"]
        assert "somebody else's record" in out["detail"]

    def test_the_posture_says_it_revokes_nothing_outside(self):
        out = Recertification.posture()
        assert out["revokes_outside_maya"] is False
        assert "a removal it cannot see" in out["why_not_revoke_outside"]

    def test_a_confirmation_covers_the_access_as_it_stood(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        out = review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                            actor="s.iqbal")
        assert "A later change is not covered" in out["detail"]

    def test_the_answer_is_on_the_evidence_chain(self, review, evidence,
                                                 staffed):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        review.answer("ACC-2026-Q3", "a.mehta", state=REVOKED,
                      reason="the secondment ended in June", actor="s.iqbal")
        blob = str(evidence.for_subject("a.mehta"))
        assert "access_revoked" in blob and "s.iqbal" in blob


class TestWhatTheRolesWereWhenSomebodyLooked:
    def test_the_answer_stays_readable_after_the_roles_change(self, review,
                                                              staffed):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                      actor="s.iqbal")
        staffed.set_roles("a.mehta", ["auditor"])
        out = review.of("a.mehta")
        assert out["roles_then"] == ["validator"]
        assert "not covered by that answer" in out["detail"]

    def test_never_reviewed_is_not_reviewed_and_found_correct(self, review):
        out = review.of("j.okafor")
        assert out["recertified"] is False
        assert "not the same as it having been reviewed" in out["detail"]


class TestAccountsWorthASecondLook:
    def test_an_account_that_has_never_signed_in_is_flagged(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal",
                    population=["a.mehta"])
        flagged = review.status("ACC-2026-Q3")["flagged"]
        assert flagged[0]["principal"] == "a.mehta"
        assert "never signed in" in flagged[0]["why"][0]

    def test_a_dormant_account_is_flagged_by_its_age(self, review, staffed,
                                                     db):
        db.execute("UPDATE principal SET last_seen_at = :t "
                   "WHERE username = 'a.mehta'",
                   {"t": time.time() - (DORMANT_AFTER_DAYS + 5) * 86400})
        review.open("ACC-2026-Q3", reviewer="s.iqbal",
                    population=["a.mehta"])
        why = review.status("ACC-2026-Q3")["flagged"][0]["why"]
        assert any(str(DORMANT_AFTER_DAYS) in w for w in why)

    def test_an_incompatible_pair_is_flagged_by_the_rule_engine(self, review,
                                                                db):
        """The rule engine's own answer, not a second implementation of it.

        Written straight into the row, because the service refuses the grant —
        which is the case this flag exists for: a pair that became incompatible
        *after* it was granted, when somebody edited what a role carries.
        """
        db.execute("UPDATE principal SET roles = :r WHERE username = 'j.okafor'",
                   {"r": '["model_owner", "auditor"]'})
        review.open("ACC-2026-Q3", reviewer="s.iqbal",
                    population=["j.okafor"])
        why = review.status("ACC-2026-Q3")["flagged"][0]["why"]
        assert any("third line must not own" in w for w in why)

    def test_an_account_holding_no_roles_is_flagged(self, review, staffed):
        staffed.set_roles("j.okafor", [])
        review.open("ACC-2026-Q3", reviewer="s.iqbal",
                    population=["j.okafor"])
        why = review.status("ACC-2026-Q3")["flagged"][0]["why"]
        assert any("grants nothing" in w for w in why)


class TestWhatTheAdversarialPassFound:
    def test_only_the_named_reviewer_may_answer(self, review):
        """`reviewer` was recorded and never read, so anybody holding
        `principal:manage` could answer any campaign — the same defect as a
        feature tag nothing evaluates, pointed at this module's own column."""
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        with pytest.raises(AuthzError) as e:
            review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                          actor="j.okafor")
        assert e.value.code == "not_the_reviewer"
        assert "is decoration" in e.value.remediation

    def test_handing_it_over_is_an_act_with_a_reason(self, review):
        """Reviewers leave, go on secondment, and turn out to be in the
        population they were asked to review. A campaign that cannot be handed
        over is one somebody answers under the previous reviewer's account."""
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        out = review.reassign("ACC-2026-Q3", "j.okafor",
                              "s.iqbal is in the population", actor="s.iqbal")
        assert out["reviewer"] == "j.okafor" and out["was"] == "s.iqbal"
        review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                      actor="j.okafor")

    def test_a_handover_with_no_reason_is_refused(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        with pytest.raises(AuthzError) as e:
            review.reassign("ACC-2026-Q3", "j.okafor", "  ")
        assert e.value.code == "reason_required"

    def test_revoking_the_last_administrator_is_refused(self, review,
                                                        staffed):
        """`suspend` always guarded this; `set_roles` did not, and revoking
        calls `set_roles`. Taking the last `principal:manage` role away leaves
        exactly the state suspension refuses to create — nobody who can put
        anybody back."""
        staffed.create("root", "root", ["admin"],
                       password=PEOPLE["s.iqbal"][1])
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        with pytest.raises(AuthzError) as e:
            review.answer("ACC-2026-Q3", "root", state=REVOKED,
                          reason="left the firm in June", actor="s.iqbal")
        assert e.value.code == "last_administrator"
        assert staffed.require("root")["roles"] == ["admin"]

    def test_an_old_answer_does_not_read_like_a_fresh_one(self, review):
        """Counting *ever answered* makes a 2019 confirmation read exactly like
        yesterday's, which is the shape of every access review that is run once
        and reported as a standing control."""
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                      actor="s.iqbal", now=time.time() - 900 * 86400)
        out = review.across_the_estate()
        assert "a.mehta" not in out["never_recertified"]
        assert "a.mehta" in out["overdue"]
        assert "not access as it stands" in out["detail"]

    def test_a_recent_answer_is_not_overdue(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                      actor="s.iqbal")
        assert review.across_the_estate()["overdue"] == []


class TestTheEstateNumber:
    def test_it_counts_accounts_nobody_has_ever_looked_at(self, review):
        out = review.across_the_estate()
        assert "a.mehta" in out["never_recertified"]
        assert "not a review that found nothing" in out["detail"]

    def test_answering_removes_somebody_from_that_count(self, review):
        review.open("ACC-2026-Q3", reviewer="s.iqbal")
        review.answer("ACC-2026-Q3", "a.mehta", state=CONFIRMED,
                      actor="s.iqbal")
        assert "a.mehta" not in review.across_the_estate()["never_recertified"]

    def test_the_cadence_is_reported_and_never_enforced(self, review):
        out = review.across_the_estate()
        assert out["campaigns_this_period"] == 0
        assert "does not enforce it" in out["detail"]
        assert Recertification.posture()["decides_who_reviews_whom"] is False


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/recertification").json()
        assert out["times_out"] is False
        assert "never_recertified" in out

    def test_a_campaign_is_opened_over_the_wire(self, client, an_admin):
        out = client.post("/api/v1/recertification", auth=an_admin,
                          json={"reference": "ACC-2026-Q3",
                                "reviewer": "root"})
        assert out.status_code == 201, out.text
        assert out.json()["unreviewed"] == out.json()["population"]

    def test_self_recertification_is_refused_over_the_wire(self, client,
                                                           an_admin):
        client.post("/api/v1/recertification", auth=an_admin,
                    json={"reference": "ACC-2026-Q4", "reviewer": "root"})
        out = client.post("/api/v1/recertification/ACC-2026-Q4/root",
                          auth=an_admin, json={"state": "confirmed"})
        assert out.status_code == 403
        assert "self_recertification" in out.text

    def test_a_revocation_with_no_reason_is_refused_over_the_wire(
            self, client, an_admin, people):
        client.post("/api/v1/recertification", auth=an_admin,
                    json={"reference": "ACC-2026-Q5", "reviewer": "root"})
        out = client.post("/api/v1/recertification/ACC-2026-Q5/a.mehta",
                          auth=an_admin, json={"state": "revoked"})
        assert out.status_code == 422
        assert "reason_required" in out.text


@pytest.fixture
def an_admin(client, people):
    """An account that may administer principals. The suite's four cannot.

    Deliberately so: `principal:manage` is not carried by any of the four model
    duties, which is the point — deciding who may act is not one of the acts.
    """
    assert client.post("/api/v1/principals", json={
        "username": "root", "display_name": "root", "roles": ["admin"],
        "password": "root-pw-long-enough"}).status_code == 201
    return ("root", "root-pw-long-enough")
