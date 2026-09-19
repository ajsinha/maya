"""
What a caller may not read, the review queue, the SLA aging list, the break-glass
report and the lineage graph do not name: an object in a private namespace is
absent for an outsider and present for its owner and an administrator.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.core.errors import NotFound
from tests.conftest import PX_DEF, price_csv


@pytest.fixture(scope="module")
def shut(world):
    w = world
    w.p.access.create_namespace(w.admin, name="rs_shut", default_visibility="private")
    w.p.access.create_namespace(w.admin, name="rs_open", default_visibility="namespace_read")
    for ns in ("rs_shut", "rs_open"):
        w.p.features.create(w.dana, namespace=ns, name="rs_px", definition=PX_DEF)
        w.p.features.ingest(w.dana, f"{ns}/rs_px", price_csv(3), fmt="csv")
        w.p.features.transition(w.dana, f"{ns}/rs_px", 1, "submit")
    return w


def _queued(items, ns):
    return [i for i in items if i["namespace"] == ns]


def test_the_review_queue_names_only_what_the_caller_may_read(shut):
    w = shut
    assert _queued(w.p.workflow_svc.queue(w.devi), "rs_shut") == []
    assert _queued(w.p.workflow_svc.queue(w.devi), "rs_open")
    assert _queued(w.p.workflow_svc.queue(w.dana), "rs_shut"), "the owner sees her own"
    assert _queued(w.p.workflow_svc.queue(w.admin), "rs_shut")
    assert _queued(w.p.workflow_svc.queue_all(), "rs_shut"), "the system sweep sees all"


def test_aging_and_break_glass_are_scoped_the_same_way(shut):
    w = shut
    assert all(i["namespace"] != "rs_shut" for i in w.p.workflow_svc.aging(w.devi))
    ref = "rs_shut/rs_px"
    w.p.features.transition(
        w.admin, ref, 1, "approve", force=True, rationale="reviewer away, feed outage"
    )
    mine = [
        e
        for e in w.p.workflow_svc.break_glass_report(w.devi)
        if "rs_shut" in (e.get("object_ref") or "")
    ]
    assert mine == []
    assert [
        e
        for e in w.p.workflow_svc.break_glass_report(w.admin)
        if "rs_shut" in (e.get("object_ref") or "")
    ]


def test_lineage_leaves_out_what_the_caller_may_not_read(shut):
    w = shut
    root = "maya://feature/rs_open/rs_px"
    with w.p.uow("admin") as uow:
        uow.repo("lineage_edges").link(root, "maya://feature/rs_shut/rs_px", "feeds")
        uow.repo("lineage_edges").link(root, "maya://op/extend/abcd1234", "feeds")
    everything = w.p.ops.lineage(root)
    assert {n["id"] for n in everything["nodes"]} >= {
        "maya://feature/rs_shut/rs_px",
        "maya://op/extend/abcd1234",
    }
    seen = w.p.ops.lineage(root, p=w.devi)
    ids = {n["id"] for n in seen["nodes"]}
    assert "maya://feature/rs_shut/rs_px" not in ids and seen["hidden"] == 1
    assert "maya://op/extend/abcd1234" in ids, "an operation next to a readable node shows"
    assert all("rs_shut" not in e["source"] + e["target"] for e in seen["edges"])
    assert "maya://feature/rs_shut/rs_px" in {
        n["id"] for n in w.p.ops.lineage(root, p=w.dana)["nodes"]
    }
    with pytest.raises(NotFound):
        w.p.ops.lineage("maya://feature/rs_shut/rs_px", p=w.devi)
