"""
Delegation and escalation (§10.4): a stand-in approves exactly what the
delegator could, within the window and object types given, recorded on behalf
of the delegator; SoD binds both; no chaining; overdue items escalate once.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from tests.conftest import PASSWORD, PX_DEF, price_csv

TODAY = dt.date.today()


def _submitted(w, ns, name):
    w.p.features.create(w.dana, namespace=ns, name=name, definition=PX_DEF)
    w.p.features.ingest(w.dana, f"{ns}/{name}", price_csv(3), fmt="csv")
    w.p.features.transition(w.dana, f"{ns}/{name}", 1, "submit")
    return f"{ns}/{name}"


def test_a_delegate_approves_on_behalf_within_the_window(world):
    w = world
    w.p.access.create_namespace(w.admin, name="dlg")
    w.p.access.create_user(w.admin, username="deputy", password=PASSWORD, roles=["model_owner"])
    deputy = w.principal("deputy")
    ref = _submitted(w, "dlg", "covered")
    with pytest.raises(PermissionDenied):
        w.p.features.transition(deputy, ref, 1, "approve")
    w.p.workflow_svc.delegate(w.mick, to="deputy", starts_on=TODAY, ends_on=TODAY,
                              object_types=["feature_version"], reason="leave")
    out = w.p.features.transition(deputy, ref, 1, "approve")
    assert out["state"] == "approved"
    history = w.p.workflow_svc.history("feature_version",
                                       w.p.features.get(w.dana, ref)["versions"][0]["id"])
    approval = next(h for h in history if h["transition"] == "approval")
    assert approval["actor"] == "deputy" and approval["on_behalf_of"] == "mick"
    assert any(n["kind"] == "delegation" and "mick delegated" in n["message"]
               for n in w.p.access.inbox(deputy))


def test_out_of_scope_expired_and_revoked_delegations_do_nothing(world):
    w = world
    w.p.access.create_user(w.admin, username="deputy2", password=PASSWORD, roles=["techops"])
    deputy = w.principal("deputy2")
    scoped = w.p.workflow_svc.delegate(w.mick, to="deputy2", starts_on=TODAY, ends_on=TODAY,
                                       object_types=["model_version"])
    ref = _submitted(w, "dlg", "wrong_scope")
    with pytest.raises(PermissionDenied):
        w.p.features.transition(deputy, ref, 1, "approve")
    w.p.workflow_svc.revoke_delegation(w.mick, scoped["id"])
    w.p.workflow_svc.delegate(w.mick, to="deputy2", starts_on=TODAY - dt.timedelta(days=9),
                              ends_on=TODAY - dt.timedelta(days=1))
    with pytest.raises(PermissionDenied):
        w.p.features.transition(deputy, ref, 1, "approve")


def test_sod_binds_the_delegator_and_there_is_no_chaining(world):
    w = world
    w.p.access.create_user(w.admin, username="relay", password=PASSWORD, roles=["techops"])
    w.p.access.create_user(w.admin, username="relay2", password=PASSWORD, roles=["techops"])
    w.p.workflow_svc.delegate(w.mick, to="relay", starts_on=TODAY, ends_on=TODAY)
    with pytest.raises(PermissionDenied, match="approver"):
        w.p.workflow_svc.delegate(w.principal("relay"), to="relay2", starts_on=TODAY,
                                  ends_on=TODAY)
    ref = _submitted(w, "dlg", "chain")
    with pytest.raises(PermissionDenied):          # relay2 got nothing from relay: no chaining
        w.p.features.transition(w.principal("relay2"), ref, 1, "approve")
    # a delegator who submitted the item cannot approve it through a stand-in
    w.p.access.create_user(w.admin, username="boss", password=PASSWORD,
                           roles=["feature_designer", "feature_manager"])
    boss = w.principal("boss")
    w.p.access.create_namespace(w.admin, name="strictns", preset="regulated")
    w.p.features.create(boss, namespace="strictns", name="own", definition=PX_DEF)
    w.p.features.ingest(boss, "strictns/own", price_csv(3), fmt="csv")
    w.p.features.transition(boss, "strictns/own", 1, "submit")
    w.p.workflow_svc.delegate(boss, to="relay2", starts_on=TODAY, ends_on=TODAY)
    with pytest.raises(PermissionDenied, match="delegate of boss"):
        w.p.features.transition(w.principal("relay2"), "strictns/own", 1, "approve")
    with pytest.raises(ValidationFailed, match="yourself"):
        w.p.workflow_svc.delegate(w.mick, to="mick", starts_on=TODAY, ends_on=TODAY)


def test_overdue_items_escalate_once(world):
    w = world
    w.p.access.create_namespace(w.admin, name="slow")
    ref = _submitted(w, "slow", "late")
    with w.p.uow() as uow:
        v = uow.repo("feature_versions").find_one(
            feature_id=uow.repo("features").find_one(name="late")["id"])
        for e in uow.repo("workflow_events").list(object_id=v["id"]):
            uow.repo("workflow_events").update(e["id"], {
                "created_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=9)})
    assert w.p.workflow_svc.escalate_overdue() >= 1
    assert w.p.workflow_svc.escalate_overdue() == 0, "an escalation is sent once"
    owner_inbox = w.p.access.inbox(w.admin)
    assert any(ref.split("/")[1] in n["message"] and n["kind"] == "escalation"
               for n in owner_inbox)


def test_scheduler_runs_each_sweep_on_its_interval():
    from maya.jobs.scheduler import Scheduler
    calls: list[str] = []
    s = Scheduler()
    s.every("a", 60, lambda: calls.append("a"))
    s.every("boom", 60, lambda: 1 / 0)                 # a failing sweep does not stop others
    s.every("b", 3600, lambda: calls.append("b"))
    assert s.run_due(now=0) == ["a", "b"] and calls == ["a", "b"]
    assert s.run_due(now=30) == []
    assert s.run_due(now=61) == ["a"]
