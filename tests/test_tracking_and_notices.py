"""
Tracking bindings (§5.8, §8.7), subscriptions (§5.7) and the notices the
platform owes without being asked (§5.5, §9.4, §29.5).

A bare reference means "the latest approved version", which is convenient right
up to the moment the parent changes. The bargain is that it never changes
quietly: the dependant is marked for re-approval and its owner is told.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest

from maya.core.clock import utcnow
from maya.core.errors import PermissionDenied, ValidationFailed
from tests.conftest import PX_DEF, approved_feature, price_csv

PANEL = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "alignment": {"mode": "inner"},
}


def _notices(w, user, kind):
    with w.p.uow() as uow:
        user_row = uow.repo("users").find_one(username=user)
        return [n for n in uow.repo("notifications").list(user_id=user_row["id"], kind=kind)]


def _latest(w, table, fk, name, obj_table):
    with w.p.uow() as uow:
        obj = uow.repo(obj_table).find_one(name=name)
        rows = uow.repo(table).list(**{fk: obj["id"]}, order_by=["-version_no"], limit=1)
        return rows[0]


# -- tracking bindings (§5.8, §8.7) ------------------------------------------------
@pytest.fixture(scope="module")
def tracked(world):
    """A feature set whose member reference is bare: it tracks its member."""
    w = world
    w.p.access.create_namespace(w.admin, name="tr", preset="regulated")
    approved_feature(w, "tr_px", price_csv(), ns="tr")
    w.p.featuresets.create(
        w.dana,
        namespace="tr",
        name="tr_panel",
        definition={
            **PANEL,
            "members": [
                {"attr": "close", "ref": "maya://feature/tr/tr_px", "source_attr": "close"}
            ],
        },
    )
    w.p.featuresets.transition(w.dana, "tr/tr_panel", 1, "submit")
    w.p.featuresets.transition(w.mick, "tr/tr_panel", 1, "approve")
    return w


def _bump(w, ref, version_no, definition):
    w.p.features.new_draft(w.dana, ref)
    w.p.features.update_draft(w.dana, ref, definition)
    w.p.features.transition(w.dana, ref, version_no, "submit")
    w.p.features.transition(w.mick, ref, version_no, "approve")


def test_a_behavioural_bump_marks_the_tracking_dependant_for_re_approval(tracked):
    w = tracked
    before = _latest(w, "feature_set_versions", "feature_set_id", "tr_panel", "feature_sets")
    assert before["needs_reapproval"] is None
    changed = copy.deepcopy(PX_DEF)
    changed["resolution"]["rules"]["close"] = "last_known_as_of(lag=2)"
    _bump(w, "tr/tr_px", 2, changed)
    after = _latest(w, "feature_set_versions", "feature_set_id", "tr_panel", "feature_sets")
    assert after["needs_reapproval"], "the set tracks tr_px and tr_px moved"
    assert "maya://feature/tr/tr_px@v2 was approved" in after["needs_reapproval"]
    assert "behavioral" in after["needs_reapproval"]
    assert any("tr_panel" in n["object_ref"] for n in _notices(w, "dana", "tracking_bump"))


def test_the_mark_is_audited_with_how_many_dependants_it_touched(tracked):
    w = tracked
    with w.p.uow() as uow:
        rows = uow.repo("audit_events").list(action="tracking.dependants_marked")
    assert rows, "marking dependants is an audited act"
    assert rows[-1]["detail"]["marked"] >= 1
    assert rows[-1]["detail"]["change_class"] == "behavioral"


def test_an_additive_bump_marks_nobody(world):
    """Adding an attribute nobody downstream reads is not a reason to re-approve."""
    w = world
    w.p.access.create_namespace(w.admin, name="tr_add", preset="regulated")
    approved_feature(w, "tr_add_px", price_csv(), ns="tr_add")
    w.p.featuresets.create(
        w.dana,
        namespace="tr_add",
        name="tr_add_panel",
        definition={
            **PANEL,
            "members": [
                {"attr": "close", "ref": "maya://feature/tr_add/tr_add_px", "source_attr": "close"}
            ],
        },
    )
    w.p.featuresets.transition(w.dana, "tr_add/tr_add_panel", 1, "submit")
    w.p.featuresets.transition(w.mick, "tr_add/tr_add_panel", 1, "approve")
    added = copy.deepcopy(PX_DEF)
    added["schema"] = added["schema"] + [{"name": "vol", "type": "float64"}]
    _bump(w, "tr_add/tr_add_px", 2, added)
    panel = _latest(w, "feature_set_versions", "feature_set_id", "tr_add_panel", "feature_sets")
    assert panel["change_class"] is None
    assert panel["needs_reapproval"] is None


def test_a_pinned_dependant_is_left_alone(world):
    """A pinned reference names a version; nothing can move under it, so nothing does."""
    w = world
    w.p.access.create_namespace(w.admin, name="tr_pin", preset="regulated")
    approved_feature(w, "tr_pin_px", price_csv(), ns="tr_pin")
    w.p.featuresets.create(
        w.dana,
        namespace="tr_pin",
        name="tr_pin_panel",
        definition={
            **PANEL,
            "members": [
                {
                    "attr": "close",
                    "ref": "maya://feature/tr_pin/tr_pin_px@v1",
                    "source_attr": "close",
                }
            ],
        },
    )
    w.p.featuresets.transition(w.dana, "tr_pin/tr_pin_panel", 1, "submit")
    w.p.featuresets.transition(w.mick, "tr_pin/tr_pin_panel", 1, "approve")
    changed = copy.deepcopy(PX_DEF)
    changed["resolution"]["rules"]["close"] = "last_known_as_of(lag=3)"
    _bump(w, "tr_pin/tr_pin_px", 2, changed)
    panel = _latest(w, "feature_set_versions", "feature_set_id", "tr_pin_panel", "feature_sets")
    assert panel["needs_reapproval"] is None


def test_deprecating_a_member_warns_the_sets_that_hold_it(tracked):
    w = tracked
    w.p.features.transition(w.mick, "tr/tr_px", 2, "deprecate")
    warnings = _notices(w, "dana", "member_deprecated")
    assert warnings, "the set's owner hears that a member was deprecated"
    assert "tr_px" in warnings[-1]["message"]
    assert "name a successor" in warnings[-1]["message"]


def test_an_inheriting_child_that_tracks_its_parent_is_marked(world):
    w = world
    w.p.access.create_namespace(w.admin, name="tr_inh", preset="regulated")
    approved_feature(w, "tr_parent", price_csv(), ns="tr_inh")
    w.p.features.create(
        w.dana,
        namespace="tr_inh",
        name="tr_child",
        definition={
            "extends": {"parent": "maya://feature/tr_inh/tr_parent", "binding": "tracking"},
            "description": "tracks its parent on purpose",
        },
    )
    w.p.features.transition(w.dana, "tr_inh/tr_child", 1, "submit")
    w.p.features.transition(w.mick, "tr_inh/tr_child", 1, "approve")
    changed = copy.deepcopy(PX_DEF)
    changed["index_types"]["symbol"] = "int64"  # breaking: the index type changed
    changed["schema"] = [{"name": "close", "type": "float64"}]
    _bump(w, "tr_inh/tr_parent", 2, changed)
    child = _latest(w, "feature_versions", "feature_id", "tr_child", "features")
    assert child["needs_reapproval"], "the child tracks the parent and the parent broke"
    assert "breaking" in child["needs_reapproval"]


def test_a_revoked_member_warrant_flags_the_composite_warrants_that_embed_it(world):
    """§9.5. The composite is a different instrument with a different owner, so it is
    told and flagged, never revoked behind the owner's back.

    The composite membership and the execution warrant are written directly here: this
    exercises the propagation over the real schema without re-deriving the whole warrant
    chain, which `tests/test_warrants.py` already covers.
    """
    w = world
    w.p.access.create_namespace(w.admin, name="tr_comp", preset="regulated")
    w.p.models.create(
        w.mona, namespace="tr_comp", name="tr_member", formula="y = a*x", roles={"a": "parameter"}
    )
    w.p.models.create(w.mona, namespace="tr_comp", name="tr_blend", kind="composite")
    with w.p.uow("system") as uow:
        member = uow.repo("models").find_one(name="tr_member")
        blend = uow.repo("models").find_one(name="tr_blend")
        ns = uow.repo("namespaces").find_one(name="tr_comp")
        mv = uow.repo("model_versions").find_one(model_id=member["id"], version_no=1)
        bv = uow.repo("model_versions").find_one(model_id=blend["id"], version_no=1)
        uow.repo("composite_members").add(
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "composite_version_id": bv["id"],
                "alias": "m",
                "member_ref": "maya://model/tr_comp/tr_member@v1",
                "binding": "pinned",
            }
        )
        warrant = uow.repo("training_warrants").add(
            {
                "namespace_id": ns["id"],
                "name": "tr_member_calib",
                "version_no": 1,
                "state": "approved",
                "owner_id": w.devi.user_id,
                "model_version_id": mv["id"],
                "featureset_ref": "maya://featureset/tr_comp/none",
                "spec": {},
            }
        )
        ew = uow.repo("execution_warrants").add(
            {
                "namespace_id": ns["id"],
                "name": "tr_blend_live",
                "version_no": 1,
                "state": "approved",
                "owner_id": w.owen.user_id,
                "model_version_id": bv["id"],
                "spec": {"valid_days": 30, "environments": ["prod"]},
            }
        )
    flagged = w.p.tracking.flag_composites_of(warrant["id"], "parameters found to be stale")
    assert [f["execution_warrant_id"] for f in flagged] == [ew["id"]]
    assert flagged[0]["member"] == "tr_member"
    told = _notices(w, "owen", "member_warrant_revoked")
    assert told and "tr_member" in told[-1]["message"]
    assert "parameters found to be stale" in told[-1]["message"]
    with w.p.uow() as uow:
        audited = uow.repo("audit_events").list(action="tracking.composite_flagged")
    assert audited and audited[-1]["object_ref"] == ew["id"]


# -- subscriptions (§5.7) ----------------------------------------------------------
def test_subscribing_and_unsubscribing(world):
    w = world
    ref = "maya://feature/eq/sub_px"
    approved_feature(w, "sub_px", price_csv(), ns="eq")
    row = w.p.subscriptions.subscribe(w.mona, ref)
    assert row["object_ref"] == ref
    again = w.p.subscriptions.subscribe(w.mona, ref)
    assert again["id"] == row["id"], "subscribing twice is not two subscriptions"
    mine = w.p.subscriptions.list(w.mona)
    assert [s["object_ref"] for s in mine if s["object_ref"] == ref]
    assert next(s for s in mine if s["object_ref"] == ref)["readable"] is True
    w.p.subscriptions.unsubscribe(w.mona, ref)
    assert ref not in [s["object_ref"] for s in w.p.subscriptions.list(w.mona)]
    with pytest.raises(ValidationFailed):
        w.p.subscriptions.unsubscribe(w.mona, ref)


def test_you_cannot_follow_what_you_cannot_read(world):
    w = world
    w.p.access.create_namespace(w.admin, name="sub_shut", default_visibility="private")
    w.p.features.create(w.dana, namespace="sub_shut", name="sub_hidden", definition=PX_DEF)
    with pytest.raises(PermissionDenied):
        w.p.subscriptions.subscribe(w.mona, "maya://feature/sub_shut/sub_hidden")
    with pytest.raises(ValidationFailed):
        w.p.subscriptions.subscribe(w.mona, "maya://warrant/train/eq/x")


def test_a_subscriber_hears_that_a_new_version_was_approved(world):
    w = world
    w.p.access.create_namespace(w.admin, name="sub_ns", preset="regulated")
    approved_feature(w, "sub_watch", price_csv(), ns="sub_ns")
    w.p.subscriptions.subscribe(w.mona, "maya://feature/sub_ns/sub_watch")
    w.p.subscriptions.subscribe(w.mick, "maya://feature/sub_ns/sub_watch")
    changed = copy.deepcopy(PX_DEF)
    changed["resolution"]["rules"]["close"] = "last_known_as_of(lag=4)"
    _bump(w, "sub_ns/sub_watch", 2, changed)
    told = _notices(w, "mona", "subscription")
    assert any("sub_watch" in n["object_ref"] for n in told)
    assert "approved v2" in told[-1]["message"]
    assert "behavioral" in told[-1]["message"]
    assert not _notices(w, "mick", "subscription"), "the approver is not told their own news"


def test_a_subscriber_who_lost_read_access_is_not_told(world):
    w = world
    w.p.access.create_namespace(w.admin, name="sub_turn", default_visibility="namespace_read")
    approved_feature(w, "sub_turn_px", price_csv(), ns="sub_turn")
    w.p.subscriptions.subscribe(w.mona, "maya://feature/sub_turn/sub_turn_px")
    with w.p.uow() as uow:
        ns = uow.repo("namespaces").find_one(name="sub_turn")
        uow.repo("namespaces").update(ns["id"], {"default_visibility": "private"})
    with w.p.uow() as uow:
        assert w.p.subscriptions.subscribers(uow, "maya://feature/sub_turn/sub_turn_px") == []
    assert w.p.subscriptions.list(w.mona)[0]["readable"] in (True, False)
    kept = [
        s
        for s in w.p.subscriptions.list(w.mona)
        if s["object_ref"] == "maya://feature/sub_turn/sub_turn_px"
    ]
    assert kept and kept[0]["readable"] is False, "the subscription survives; it goes quiet"


def test_a_sealed_pin_reaches_the_features_followers(world):
    w = world
    approved_feature(w, "sub_pin_px", price_csv(), ns="eq")
    w.p.subscriptions.subscribe(w.mona, "maya://feature/eq/sub_pin_px")
    w.p.features.pin(
        w.mick,
        "eq/sub_pin_px",
        version_no=1,
        pin_name="eom",
        as_of=dt.date(2026, 1, 20),
    )
    w.drain()
    told = [n for n in _notices(w, "mona", "subscription") if "sub_pin_px" in n["object_ref"]]
    assert told, "a dependent pin is news to a subscriber (§5.7)"
    assert "new sealed pin: eom" in told[-1]["message"]


# -- the notices nobody asked for (§5.5, §9.4, §29.5) -----------------------------
def test_a_quality_check_that_blocks_a_pin_reaches_the_owner(world):
    w = world
    stale = copy.deepcopy(PX_DEF)
    stale["quality"] = [{"check": "freshness_within", "days": 1}]
    approved_feature(w, "nq_px", price_csv(), definition=stale, ns="eq")
    w.p.features.pin(
        w.mick,
        "eq/nq_px",
        version_no=1,
        pin_name="late",
        as_of=dt.date(2026, 9, 30),  # long after the last event: the contract will refuse
    )
    w.drain()
    with w.p.uow() as uow:
        feature = uow.repo("features").find_one(name="nq_px")
        pin = uow.repo("feature_pins").find_one(feature_id=feature["id"], pin_name="late")
    assert pin["state"] == "failed"
    told = _notices(w, "dana", "quality_failed")
    assert told, "§5.5 raises an alert to the owner; nothing did before"
    assert told[-1]["object_ref"] == pin["id"]
    assert "was blocked" in told[-1]["message"]
    assert w.p.subscriptions.failed_pin_notices() == 0, "the notice is sent once, not per sweep"


def test_a_covenant_breach_reaches_the_model_manager(world):
    """§29.5 says the owner *and the model manager*; only the owner was told."""
    w = world
    w.p.access.create_namespace(w.admin, name="nb_ns", preset="regulated")
    with w.p.uow("system") as uow:
        ns = uow.repo("namespaces").find_one(name="nb_ns")
        model = uow.repo("models").add(
            {
                "namespace_id": ns["id"],
                "name": "nb_model",
                "owner_id": w.mona.user_id,
                "kind": "formula",
            }
        )
        mv = uow.repo("model_versions").add(
            {"model_id": model["id"], "version_no": 1, "state": "approved"}
        )
        uow.repo("execution_warrants").add(
            {
                "namespace_id": ns["id"],
                "name": "nb_live",
                "version_no": 1,
                "state": "approved",
                "owner_id": w.owen.user_id,
                "model_version_id": mv["id"],
                "spec": {"valid_days": 30, "environments": ["prod"]},
                "suspended_at": utcnow(),
                "suspend_reason": "null_rate on x above 0.05",
            }
        )
    assert w.p.subscriptions.breach_notices() >= 1
    told = _notices(w, "mgr", "covenant_breach")
    assert told and "SUSPENDED" in told[-1]["message"]
    assert "null_rate on x above 0.05" in told[-1]["message"]
    assert w.p.subscriptions.breach_notices() == 0, "once per suspension, not once per sweep"


def test_thirty_days_before_expiry_the_model_manager_hears_too(world):
    w = world
    w.p.access.create_namespace(w.admin, name="ne_ns", preset="regulated")
    with w.p.uow("system") as uow:
        ns = uow.repo("namespaces").find_one(name="ne_ns")
        model = uow.repo("models").add(
            {
                "namespace_id": ns["id"],
                "name": "ne_model",
                "owner_id": w.mona.user_id,
                "kind": "formula",
            }
        )
        mv = uow.repo("model_versions").add(
            {"model_id": model["id"], "version_no": 1, "state": "approved"}
        )
        uow.repo("training_warrants").add(
            {
                "namespace_id": ns["id"],
                "name": "ne_calib",
                "version_no": 1,
                "state": "approved",
                "owner_id": w.devi.user_id,
                "model_version_id": mv["id"],
                "featureset_ref": "maya://featureset/ne_ns/none",
                "spec": {},
                "expires_at": utcnow() + dt.timedelta(days=10),
            }
        )
        uow.repo("execution_warrants").add(
            {
                "namespace_id": ns["id"],
                "name": "ne_live",
                "version_no": 1,
                "state": "approved",
                "owner_id": w.owen.user_id,
                "model_version_id": mv["id"],
                "spec": {"valid_days": 30, "environments": ["prod"]},
                "valid_to": utcnow() + dt.timedelta(days=5),
            }
        )
    assert w.p.subscriptions.expiry_notices() >= 2
    manager = _notices(w, "mgr", "expiry")
    named = {n["message"].split()[0] for n in manager}
    assert {"ne_calib", "ne_live"} <= named, manager
    assert _notices(w, "devi", "expiry"), "the owner is told as well"
    assert w.p.subscriptions.expiry_notices() == 0


def test_the_sweep_reports_and_audits_what_it_sent(world):
    w = world
    counts = w.p.subscriptions.notices()
    assert set(counts) == {"expiry", "covenant_breach", "quality_failed"}
    assert all(isinstance(v, int) for v in counts.values())
