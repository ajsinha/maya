"""Emergency elevation, with a second signature, an end, and somebody reading it.

The `admin` role is *described* as break-glass and is exempt from the
incompatible-roles check. That is not break-glass: it is a standing account that
happens to be powerful, and a standing powerful account is precisely the thing
break-glass exists to replace.
"""
from __future__ import annotations

import time

import pytest

from core.authz import AuthzError
from core.authz.breakglass import (HOUR, OUTCOMES, REVIEW_DAYS,
                                   UNILATERAL_WINDOW_HOURS, WINDOW_HOURS,
                                   BreakGlass, DAY)


@pytest.fixture
def glass(db, principals, evidence):
    from db import BreakGlassRepository
    principals.create("r.ops", "R Ops", ["admin"], "ops-pw-long-enough")
    principals.create("s.iqbal", "S Iqbal", ["model_risk_manager"],
                      "mrm-pw-long-enough")
    return BreakGlass(BreakGlassRepository(db), principals, evidence)


def _opened(glass, unilateral=False):
    row = glass.request("r.ops", "the alias resolver is wedged", actor="r.ops")
    return glass.authorise(row["reference"],
                           "r.ops" if unilateral else "s.iqbal",
                           unilateral=unilateral)


class TestAskingForIt:
    def test_a_request_grants_nothing(self, glass):
        row = glass.request("r.ops", "the alias resolver is wedged",
                            actor="r.ops")
        assert row["state"] == "requested"
        assert glass.is_open("r.ops") is None

    def test_a_request_with_no_reason_is_refused(self, glass):
        with pytest.raises(AuthzError) as caught:
            glass.request("r.ops", "   ", actor="r.ops")
        assert caught.value.code == "reason_required"
        assert "nobody can review" in caught.value.detail

    def test_it_lands_on_the_evidence_chain(self, glass, evidence):
        glass.request("r.ops", "wedged", actor="r.ops")
        kinds = [n["kind"] for n in evidence.for_subject("r.ops")]
        assert "break_glass_requested" in kinds


class TestDualAuthorisation:
    def test_the_second_person_cannot_be_the_first(self, glass):
        row = glass.request("r.ops", "wedged", actor="r.ops")
        with pytest.raises(AuthzError) as caught:
            glass.authorise(row["reference"], "r.ops")
        assert caught.value.code == "same_person"
        assert "one person is one person" in caught.value.detail

    def test_a_second_signature_opens_it(self, glass):
        row = _opened(glass)
        assert row["state"] == "open"
        assert row["authorised_by"] == "s.iqbal"
        assert glass.is_open("r.ops")["reference"] == row["reference"]

    def test_a_unilateral_grant_is_allowed_and_flagged(self, glass):
        """Refusing outright at three in the morning is how an institution ends
        up with a shared password in a safe — no name, no reason, no window and
        no review."""
        row = _opened(glass, unilateral=True)
        assert row["unilateral"] is True
        assert row["authorised_by"] is None
        assert row["state"] == "open"

    def test_a_unilateral_grant_gets_a_shorter_window(self, glass):
        both = _opened(glass)
        glass.close(both["reference"], "done", actor="r.ops")
        glass.review(both["reference"], "appropriate", "checked", "s.iqbal")
        alone = _opened(glass, unilateral=True)
        assert (alone["expires_at"] - alone["opened_at"]) == pytest.approx(
            UNILATERAL_WINDOW_HOURS * HOUR, rel=0.01)
        assert UNILATERAL_WINDOW_HOURS < WINDOW_HOURS

    def test_flagging_a_two_person_grant_unilateral_is_refused(self, glass):
        row = glass.request("r.ops", "wedged", actor="r.ops")
        with pytest.raises(AuthzError) as caught:
            glass.authorise(row["reference"], "s.iqbal", unilateral=True)
        assert caught.value.code == "not_unilateral"


class TestExpiryIsDerived:
    def test_a_grant_past_its_window_is_closed_without_any_batch(self, glass):
        """A grant only closed when a batch runs is open whenever the batch is
        not running, which is exactly when it would matter."""
        row = _opened(glass)
        later = row["expires_at"] + 1
        assert glass.is_open("r.ops", now=later) is None
        # And the row still says open, which is the point: the state column is
        # housekeeping and the window is the control.
        assert glass.require(row["reference"])["state"] == "open"

    def test_the_batch_tidies_it_up(self, glass):
        row = _opened(glass)
        out = glass.expire_due(now=row["expires_at"] + 1)
        assert out["count"] == 1
        assert glass.require(row["reference"])["state"] == "expired"

    def test_an_unexpired_grant_is_left_alone(self, glass):
        _opened(glass)
        assert glass.expire_due()["count"] == 0


class TestTheReviewHasTeeth:
    def test_an_unreviewed_grant_refuses_the_next_request(self, glass):
        """Otherwise 'mandatory post-hoc review' is a to-do list, and a to-do
        list is what every unread break-glass log already is."""
        row = _opened(glass)
        glass.close(row["reference"], "done", actor="r.ops")
        with pytest.raises(AuthzError) as caught:
            glass.request("r.ops", "wedged again", actor="r.ops")
        assert caught.value.code == "review_outstanding"
        assert row["reference"] in caught.value.detail

    def test_reviewing_it_releases_the_next_one(self, glass):
        row = _opened(glass)
        glass.close(row["reference"], "done", actor="r.ops")
        glass.review(row["reference"], "appropriate", "matched the reason",
                     "s.iqbal")
        assert glass.request("r.ops", "wedged again", actor="r.ops")

    def test_the_user_cannot_review_their_own_elevation(self, glass):
        row = _opened(glass)
        glass.close(row["reference"], "done", actor="r.ops")
        with pytest.raises(AuthzError) as caught:
            glass.review(row["reference"], "appropriate", "fine", "r.ops")
        assert caught.value.code == "reviewed_by_the_user"
        assert "an opinion, not a control" in caught.value.remediation

    def test_an_open_grant_cannot_be_reviewed(self, glass):
        row = _opened(glass)
        with pytest.raises(AuthzError) as caught:
            glass.review(row["reference"], "appropriate", "fine", "s.iqbal")
        assert caught.value.code == "still_open"

    def test_a_review_with_no_note_records_that_somebody_clicked(self, glass):
        row = _opened(glass)
        glass.close(row["reference"], "done", actor="r.ops")
        with pytest.raises(AuthzError) as caught:
            glass.review(row["reference"], "appropriate", "  ", "s.iqbal")
        assert caught.value.code == "note_required"

    def test_the_outcomes_are_closed(self, glass):
        row = _opened(glass)
        glass.close(row["reference"], "done", actor="r.ops")
        with pytest.raises(AuthzError) as caught:
            glass.review(row["reference"], "looked at it", "n", "s.iqbal")
        assert caught.value.code == "unknown_outcome"
        assert set(OUTCOMES) == {"appropriate", "excessive", "unwarranted"}

    def test_it_is_reviewed_once(self, glass):
        row = _opened(glass)
        glass.close(row["reference"], "done", actor="r.ops")
        glass.review(row["reference"], "appropriate", "ok", "s.iqbal")
        with pytest.raises(AuthzError) as caught:
            glass.review(row["reference"], "excessive", "again", "s.iqbal")
        assert caught.value.code == "already_reviewed"

    def test_an_overdue_review_is_named_as_overdue(self, glass):
        row = _opened(glass)
        glass.close(row["reference"], "done", actor="r.ops")
        late = time.time() + (REVIEW_DAYS + 1) * DAY
        assert glass.unreviewed(now=late)[0]["overdue"] is True


class TestWhatWasDoneUnderIt:
    def test_it_is_folded_from_the_chain_and_not_logged_twice(self, glass,
                                                              evidence):
        row = _opened(glass)
        evidence.append("model_registered", "model", "m-1", {"n": 1},
                        actor="r.ops")
        evidence.append("alias_moved", "model", "m-1", {"to": "1.0.0"},
                        actor="r.ops")
        out = glass.under(row["reference"])
        assert out["acts"] == 2
        assert set(out["by_kind"]) == {"model_registered", "alias_moved"}

    def test_acts_by_somebody_else_are_not_attributed_to_it(self, glass,
                                                            evidence):
        row = _opened(glass)
        evidence.append("model_registered", "model", "m-2", {}, actor="d.raman")
        assert glass.under(row["reference"])["acts"] == 0

    def test_the_grants_own_bookkeeping_is_not_counted_as_use(self, glass):
        row = _opened(glass)
        assert glass.under(row["reference"])["acts"] == 0

    def test_a_grant_nobody_used_is_worth_noticing(self, glass):
        row = _opened(glass)
        assert "false alarm or a habit" in glass.under(row["reference"])["detail"]


class TestTheNumberThatCounts:
    """You cannot find break-glass abuse by watching break-glass: anybody
    misusing it would simply not open one."""

    def test_an_admin_act_outside_any_grant_is_counted(self, glass, evidence):
        evidence.append("model_registered", "model", "m-3", {}, actor="r.ops")
        out = glass.unglassed()
        assert out["acts"] == 1
        assert out["by_principal"] == {"r.ops": 1}
        assert "in what is missing from it" in out["detail"]

    def test_an_act_inside_a_grant_is_not(self, glass, evidence):
        _opened(glass)
        evidence.append("model_registered", "model", "m-4", {}, actor="r.ops")
        assert glass.unglassed()["acts"] == 0

    def test_a_non_admin_is_not_counted(self, glass, evidence):
        evidence.append("model_registered", "model", "m-5", {},
                        actor="s.iqbal")
        assert glass.unglassed()["acts"] == 0

    def test_the_grants_own_acts_are_not_counted_against_it(self, glass):
        glass.request("r.ops", "wedged", actor="r.ops")
        assert glass.unglassed()["acts"] == 0

    def test_it_appears_on_the_estate_view(self, glass, evidence):
        evidence.append("model_registered", "model", "m-6", {}, actor="r.ops")
        out = glass.across_the_estate()
        assert out["unglassed"]["acts"] == 1


ADMIN = ("admin", "maya-admin-dev")


class TestOverHttp:
    """Asking is authentication only; authorising and reviewing are the
    administrator's act. Refusing people the ability to *ask* for elevation is
    how a platform ends up with somebody else's password being the answer."""

    def test_a_grant_goes_all_the_way_round(self, client, people):
        admin = ADMIN
        asked = client.post("/api/v1/break-glass", auth=people["d.raman"],
                            json={"reason": "the alias resolver is wedged"})
        assert asked.status_code == 201, asked.text
        reference = asked.json()["reference"]

        opened = client.post(f"/api/v1/break-glass/{reference}/authorise",
                             auth=admin, json={})
        assert opened.status_code == 200, opened.text
        assert opened.json()["effectively_open"] is True

        closed = client.post(f"/api/v1/break-glass/{reference}/close",
                             auth=people["d.raman"], json={"reason": "fixed"})
        assert closed.status_code == 200, closed.text

        reviewed = client.post(f"/api/v1/break-glass/{reference}/review",
                               auth=admin,
                               json={"outcome": "appropriate",
                                     "note": "matched the reason given"})
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["review_outcome"] == "appropriate"

    def test_the_requester_cannot_authorise_it(self, client, people):
        admin = ADMIN
        asked = client.post("/api/v1/break-glass", auth=admin,
                            json={"reason": "wedged"})
        r = client.post(
            f"/api/v1/break-glass/{asked.json()['reference']}/authorise",
            auth=admin, json={})
        assert r.status_code == 403, r.text
        assert r.json()["error"] == "same_person"

    def test_an_unreviewed_grant_refuses_the_next_request(self, client,
                                                          people):
        admin = ADMIN
        asked = client.post("/api/v1/break-glass", auth=people["d.raman"],
                            json={"reason": "wedged"})
        reference = asked.json()["reference"]
        client.post(f"/api/v1/break-glass/{reference}/authorise",
                    auth=admin, json={})
        client.post(f"/api/v1/break-glass/{reference}/close",
                    auth=people["d.raman"], json={"reason": "fixed"})
        again = client.post("/api/v1/break-glass", auth=people["d.raman"],
                            json={"reason": "wedged again"})
        assert again.status_code == 409, again.text
        assert again.json()["error"] == "review_outstanding"

    def test_what_was_done_under_it_is_served(self, client, people):
        admin = ADMIN
        asked = client.post("/api/v1/break-glass", auth=people["d.raman"],
                            json={"reason": "wedged"})
        reference = asked.json()["reference"]
        client.post(f"/api/v1/break-glass/{reference}/authorise",
                    auth=admin, json={})
        r = client.get(f"/api/v1/break-glass/{reference}/under",
                       auth=people["s.iqbal"])
        assert r.status_code == 200, r.text
        assert "acts" in r.json()

    def test_an_unknown_reference_is_a_404(self, client, people):
        r = client.get("/api/v1/break-glass/BG-9999/under",
                       auth=people["s.iqbal"])
        assert r.status_code == 404, r.text

    def test_the_screen_leads_with_what_happened_without_a_grant(self, client,
                                                                 people):
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/break-glass"})
        body = client.get("/break-glass").text
        assert "privileged acts under no grant" in body
        assert "in what is missing from it" in body
