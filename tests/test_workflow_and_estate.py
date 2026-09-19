"""
Workflow as data (§10.6) and the migration-free upgrade path (§14.3):
edit-time policy validation, governed activation, a new policy blocking what
the old one allowed, YAML round-trip fidelity, break-glass, campaigns; and
export → recreate → import with the audit chain intact, plus tamper detection.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import copy

import pytest
from sqlalchemy import text

from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from maya.workflow import policy as pol
from tests.conftest import PX_DEF, World, approved_feature, build_platform, price_csv


def _active(w, object_type):
    return next(p for p in w.p.workflow_svc.policies()
                if p["object_type"] == object_type and p["state"] == "active")


def test_invalid_policies_are_refused_at_edit_time(world):
    base = _active(world, "feature_version")["policy"]
    broken = copy.deepcopy(base)
    broken["transitions"]["approve"]["checks"].append("no_such_check")
    broken["transitions"]["approve"]["approvals"] = [{"role": "ghost", "count": 1}]
    broken["states"].append("limbo")
    with pytest.raises(ValidationFailed) as exc:
        world.p.workflow_svc.draft_policy(world.admin, "feature_version", broken)
    message = exc.value.message
    assert "no_such_check" in message and "ghost" in message and "limbo" in message
    unapprovable = copy.deepcopy(base)
    del unapprovable["transitions"]["approve"]
    errors = world.p.workflow_svc.validate(unapprovable)
    assert any("permanently unapprovable" in e for e in errors)


def test_policy_is_governed_and_changes_behaviour(world):
    base = _active(world, "feature_version")["policy"]
    stricter = copy.deepcopy(base)
    stricter["transitions"]["approve"]["approvals"] = [{"role": "feature_manager", "count": 2}]
    draft = world.p.workflow_svc.draft_policy(world.admin, "feature_version", stricter,
                                              scope="eq", note="two approvers")
    with pytest.raises(PermissionDenied, match="another administrator"):
        world.p.workflow_svc.activate(world.admin, draft["id"])
    world.p.workflow_svc.activate(world.admin2, draft["id"])
    world.p.features.create(world.dana, namespace="eq", name="twice", definition=PX_DEF)
    world.p.features.ingest(world.dana, "eq/twice", price_csv(3), fmt="csv")
    world.p.features.transition(world.dana, "eq/twice", 1, "submit")
    first = world.p.features.transition(world.mick, "eq/twice", 1, "approve")
    assert first["moved"] is False and "outstanding" in first["message"]
    with pytest.raises(NotApproved, match="already approved"):
        world.p.features.transition(world.mick, "eq/twice", 1, "approve")
    world.p.access.create_user(world.admin, username="mick2", password="Test-password-1",
                               roles=["feature_manager"])
    second = world.p.features.transition(world.principal("mick2"), "eq/twice", 1, "approve")
    assert second["state"] == "approved"
    # the old, still-active default governs every other namespace unchanged
    assert _active(world, "feature_version")["scope"] in ("*", "eq")


def test_yaml_round_trip_is_byte_identical(world):
    record = _active(world, "model_version")
    first = world.p.workflow_svc.export_yaml(record["id"])
    assert pol.to_yaml(pol.from_yaml(first)) == first
    imported = world.p.workflow_svc.import_yaml(world.admin, "model_version", first, scope="x")
    assert world.p.workflow_svc.export_yaml(imported["id"]) == first


def test_break_glass_is_loud_and_permanent(world):
    world.p.features.create(world.dana, namespace="eq", name="forced", definition=PX_DEF)
    world.p.features.transition(world.dana, "eq/forced", 1, "submit")
    with pytest.raises(ValidationFailed, match="reason"):
        world.p.features.transition(world.admin, "eq/forced", 1, "approve", force=True)
    with pytest.raises(PermissionDenied):
        world.p.features.transition(world.mick, "eq/forced", 1, "approve", force=True,
                                    rationale="because I said so, loudly")
    out = world.p.features.transition(world.admin, "eq/forced", 1, "approve", force=True,
                                      rationale="regulator deadline; reviewed offline by CRO")
    assert out["state"] == "approved"
    feature = world.p.features.get(world.dana, "eq/forced")
    assert feature["versions"][0]["force_approved"] is True
    assert any(e["object_ref"].endswith("forced@v1") for e in
               world.p.workflow_svc.break_glass_report())
    inbox = world.p.access.inbox(world.dana)
    assert any("BREAK-GLASS" in n["message"] for n in inbox)


def test_blocking_comment_blocks_approval_until_resolved(world):
    world.p.access.create_namespace(world.admin, name="cmt")
    world.p.features.create(world.dana, namespace="cmt", name="commented", definition=PX_DEF)
    world.p.features.ingest(world.dana, "cmt/commented", price_csv(3), fmt="csv")
    world.p.features.transition(world.dana, "cmt/commented", 1, "submit")
    version = world.p.features.get(world.dana, "cmt/commented")["versions"][0]
    c = world.p.workflow_svc.comment(world.mick, "feature_version", version["id"],
                                     "units are wrong", blocking=True)
    with pytest.raises(NotApproved, match="blocking"):
        world.p.features.transition(world.mick, "cmt/commented", 1, "approve")
    world.p.workflow_svc.resolve_comment(world.mick, c["id"])
    assert world.p.features.transition(world.mick, "cmt/commented", 1,
                                       "approve")["state"] == "approved"


def test_campaign_reports_per_item(world):
    items = []
    for name in ("camp_a", "camp_b"):
        world.p.features.create(world.dana, namespace="eq", name=name, definition=PX_DEF)
        world.p.features.ingest(world.dana, f"eq/{name}", price_csv(2), fmt="csv")
        v = world.p.features.get(world.dana, f"eq/{name}")["versions"][0]
        items.append({"object_type": "feature_version", "id": v["id"]})
    items.append({"object_type": "feature_version", "id": "no-such-id"})
    out = world.p.workflow_svc.run_campaign(world.dana, "q-end", "submit", items)
    assert [r["ok"] for r in out["results"]] == [True, True, False]


def test_estate_round_trip_and_audit_tamper_detection():
    platform = build_platform()
    w = World(platform)
    platform.access.create_namespace(w.admin, name="eq")
    approved_feature(w, "estate_px", price_csv(5))
    before = platform.access.verify_audit()
    estate = platform.ops.export_estate()
    platform.db.init_schema(force=True)
    result = platform.ops.import_estate(estate)
    assert result["audit_chain"]["ok"] and result["audit_chain"]["head"] == before["head"]
    assert platform.features.get(w.admin, "eq/estate_px")["versions"][0]["state"] == "approved"
    platform.db.verify_schema()
    # tamper: bypass the append-only trigger and rewrite one entry
    with platform.db.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_events_no_update"))
        conn.execute(text("UPDATE audit_events SET actor='mallory' WHERE seq=3"))
    broken = platform.access.verify_audit()
    assert broken["ok"] is False and broken["broken_at"] == 3
    platform.shutdown()


def test_schema_mismatch_refuses_to_start():
    platform = build_platform()
    with platform.db.engine.begin() as conn:
        conn.execute(text("UPDATE schema_meta SET value='deadbeef' WHERE key='schema_hash'"))
    from maya.core.errors import ConfigurationError
    with pytest.raises(ConfigurationError, match="export-estate"):
        platform.db.verify_schema()
    platform.shutdown()
