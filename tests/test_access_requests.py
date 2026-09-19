"""
Access requests (§11.5): the ask, the owner's decision, the time-boxed grant it
produces, and the audit trail of both — plus the check behind §16.4's disabled
control, which has to give the rule's own words or the screen and the server
will drift apart.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from tests.conftest import PX_DEF


@pytest.fixture(scope="module")
def shut(world):
    """A private namespace with a feature dana owns and mona cannot read."""
    w = world
    w.p.access.create_namespace(
        w.admin, name="ar_shut", default_visibility="private", preset="regulated"
    )
    w.p.features.create(w.dana, namespace="ar_shut", name="ar_px", definition=PX_DEF)
    return w


def _audit(w, action):
    with w.p.uow() as uow:
        return uow.repo("audit_events").list(action=action)


def _notices(w, username, kind):
    with w.p.uow() as uow:
        user = uow.repo("users").find_one(username=username)
        return uow.repo("notifications").list(user_id=user["id"], kind=kind)


def test_a_reader_who_is_refused_is_told_why_and_offered_the_request(shut):
    w = shut
    gate = w.p.access_requests.check(w.mona, kind="feature", ref="ar_shut/ar_px")
    assert gate["allowed"] is False
    assert gate["reason"] == "you may not read this: no grant and namespace is private"
    assert gate["rule"] == "no grant and namespace is private"
    assert gate["can_request"] is True
    assert gate["pending_request"] is None


def test_the_check_says_yes_where_the_server_would_say_yes(shut):
    w = shut
    gate = w.p.access_requests.check(w.dana, kind="feature", ref="ar_shut/ar_px")
    assert gate["allowed"] is True
    assert gate["reason"] is None
    assert gate["can_request"] is False


def test_the_whole_round_trip_from_ask_to_grant(shut):
    w = shut
    row = w.p.access_requests.request(
        w.mona,
        kind="feature",
        ref="ar_shut/ar_px",
        level="read",
        reason="building a challenger model",
    )
    assert row["state"] == "pending"
    assert row["object_ref"] == "maya://feature/ar_shut/ar_px"
    assert row["days"] == 90, "time-boxed by default (§11.5)"
    # the owner receives an item, and the request is on record
    owner_items = _notices(w, "dana", "access_request")
    assert owner_items and "mona requests read" in owner_items[-1]["message"]
    assert "building a challenger model" in owner_items[-1]["message"]
    asked = [a for a in _audit(w, "access.requested") if a["object_ref"] == row["object_ref"]]
    assert asked and asked[-1]["detail"]["level"] == "read"

    # the control now says a request is outstanding rather than offering another
    gate = w.p.access_requests.check(w.mona, kind="feature", ref="ar_shut/ar_px")
    assert gate["pending_request"] == row["id"]

    # the owner decides — through an administrator, who is who holds 'G' on a feature
    out = w.p.access_requests.decide(
        w.admin, row["id"], approve=True, note="agreed for the quarter", days=30
    )
    assert out["state"] == "approved"
    assert out["decided_by"] == "admin"
    assert out["grant_id"] and out["grant"]["level"] == "read"
    expires = out["grant"]["expires_at"]
    assert 28 <= (expires - dt.datetime.now(dt.timezone.utc)).days <= 30

    # and the access is real
    assert w.p.access_requests.check(w.mona, kind="feature", ref="ar_shut/ar_px")["allowed"]
    assert w.p.features.get(w.mona, "ar_shut/ar_px")["name"] == "ar_px"

    # both halves are audited, and the requester is told
    decided = [
        a for a in _audit(w, "access.request_decided") if a["object_ref"] == row["object_ref"]
    ]
    assert decided[-1]["detail"]["decision"] == "approved"
    assert decided[-1]["detail"]["requester"] == "mona"
    assert decided[-1]["detail"]["note"] == "agreed for the quarter"
    assert decided[-1]["detail"]["grant_id"] == out["grant_id"]
    assert decided[-1]["actor"] == "admin"
    told = _notices(w, "mona", "access_decision")
    assert told and "granted your request" in told[-1]["message"]


def test_asking_for_what_you_already_have_is_refused_as_pointless(shut):
    w = shut
    with pytest.raises(ValidationFailed, match="already read this"):
        w.p.access_requests.request(w.dana, kind="feature", ref="ar_shut/ar_px")


def test_a_second_ask_returns_the_open_one(world):
    w = world
    w.p.access.create_namespace(w.admin, name="ar_dup", default_visibility="private")
    w.p.features.create(w.dana, namespace="ar_dup", name="ar_dup_px", definition=PX_DEF)
    first = w.p.access_requests.request(w.mona, kind="feature", ref="ar_dup/ar_dup_px")
    second = w.p.access_requests.request(w.mona, kind="feature", ref="ar_dup/ar_dup_px")
    assert second["id"] == first["id"]
    assert second["duplicate"] is True


def test_a_refusal_is_recorded_with_its_reason_and_grants_nothing(world):
    w = world
    w.p.access.create_namespace(w.admin, name="ar_no", default_visibility="private")
    w.p.features.create(w.dana, namespace="ar_no", name="ar_no_px", definition=PX_DEF)
    row = w.p.access_requests.request(
        w.mona, kind="feature", ref="ar_no/ar_no_px", reason="curious"
    )
    out = w.p.access_requests.decide(
        w.admin, row["id"], approve=False, note="ask your desk head first"
    )
    assert out["state"] == "denied"
    assert out["grant_id"] is None
    assert (
        w.p.access_requests.check(w.mona, kind="feature", ref="ar_no/ar_no_px")["allowed"] is False
    )
    denied = [
        a for a in _audit(w, "access.request_decided") if a["object_ref"] == row["object_ref"]
    ]
    assert denied[-1]["detail"]["decision"] == "denied"
    assert denied[-1]["detail"]["note"] == "ask your desk head first"
    told = _notices(w, "mona", "access_decision")
    assert "refused your request" in told[-1]["message"]
    assert "ask your desk head first" in told[-1]["message"]


def test_only_somebody_who_may_grant_can_decide(world):
    w = world
    w.p.access.create_namespace(w.admin, name="ar_who", default_visibility="private")
    w.p.features.create(w.dana, namespace="ar_who", name="ar_who_px", definition=PX_DEF)
    row = w.p.access_requests.request(w.mona, kind="feature", ref="ar_who/ar_who_px")
    with pytest.raises(PermissionDenied):
        w.p.access_requests.decide(w.devi, row["id"], approve=True)
    assert (
        w.p.access_requests.check(w.mona, kind="feature", ref="ar_who/ar_who_px")["allowed"]
        is False
    )


def test_a_decision_is_made_once(world):
    w = world
    w.p.access.create_namespace(w.admin, name="ar_once", default_visibility="private")
    w.p.features.create(w.dana, namespace="ar_once", name="ar_once_px", definition=PX_DEF)
    row = w.p.access_requests.request(w.mona, kind="feature", ref="ar_once/ar_once_px")
    w.p.access_requests.decide(w.admin, row["id"], approve=True)
    with pytest.raises(ValidationFailed, match="already approved"):
        w.p.access_requests.decide(w.admin, row["id"], approve=False)


def test_the_requester_can_withdraw_and_nobody_else_can(world):
    w = world
    w.p.access.create_namespace(w.admin, name="ar_wd", default_visibility="private")
    w.p.features.create(w.dana, namespace="ar_wd", name="ar_wd_px", definition=PX_DEF)
    row = w.p.access_requests.request(w.mona, kind="feature", ref="ar_wd/ar_wd_px")
    with pytest.raises(PermissionDenied):
        w.p.access_requests.withdraw(w.devi, row["id"])
    out = w.p.access_requests.withdraw(w.mona, row["id"])
    assert out["state"] == "withdrawn"
    assert _audit(w, "access.request_withdrawn")


def test_the_list_shows_yours_and_the_ones_waiting_on_you(world):
    w = world
    w.p.access.create_namespace(w.admin, name="ar_list", default_visibility="private")
    w.p.features.create(w.dana, namespace="ar_list", name="ar_list_px", definition=PX_DEF)
    row = w.p.access_requests.request(w.mona, kind="feature", ref="ar_list/ar_list_px")
    mine = [r for r in w.p.access_requests.list(w.mona) if r["id"] == row["id"]]
    assert mine and mine[0]["mine"] is True and mine[0]["you_decide"] is False
    theirs = [r for r in w.p.access_requests.list(w.admin) if r["id"] == row["id"]]
    assert theirs and theirs[0]["you_decide"] is True and theirs[0]["requester"] == "mona"
    assert theirs[0]["mine"] is False
    uninvolved = [r for r in w.p.access_requests.list(w.tess) if r["id"] == row["id"]]
    assert uninvolved == [], "a request that is neither yours nor yours to decide is not listed"
    pending = w.p.access_requests.list(w.admin, state="pending")
    assert all(r["state"] == "pending" for r in pending)
    with pytest.raises(ValidationFailed):
        w.p.access_requests.list(w.admin, state="nonsense")


def test_the_kinds_and_levels_are_the_ones_grants_use(shut):
    w = shut
    with pytest.raises(ValidationFailed, match="Access is requested on"):
        w.p.access_requests.request(w.mona, kind="pin", ref="ar_shut/ar_px")
    with pytest.raises(ValidationFailed, match="Level must be one of"):
        w.p.access_requests.request(w.mona, kind="feature", ref="ar_shut/ar_px", level="godmode")
    with pytest.raises(ValidationFailed, match="Unknown object kind"):
        w.p.access_requests.check(w.mona, kind="pin", ref="ar_shut/ar_px")


def test_a_decision_can_never_hand_out_more_than_the_decider_holds(world):
    """The grant is made under the decider's own principal, so ``can()`` still applies."""
    w = world
    w.p.access.create_namespace(w.admin, name="ar_ceiling", default_visibility="private")
    w.p.features.create(w.dana, namespace="ar_ceiling", name="ar_ceil_px", definition=PX_DEF)
    row = w.p.access_requests.request(
        w.mona, kind="feature", ref="ar_ceiling/ar_ceil_px", level="admin"
    )
    with pytest.raises(PermissionDenied, match="no 'G' on feature"):
        w.p.access_requests.decide(w.dana, row["id"], approve=True)
    still = [r for r in w.p.access_requests.list(w.mona) if r["id"] == row["id"]]
    assert still[0]["state"] == "pending", "a refused decision leaves the request open"
