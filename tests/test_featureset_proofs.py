"""
Feature-set behaviours that were built but never proved (plan M4):

* **Equivalence detection (§6.8).** Two algebraically identical definitions are
  refused as a near-copy when the second is submitted — member order, cosmetic
  metadata and an ``extend`` that projects its parent down to the same attributes do
  not make a definition new; a different rule, alignment, attribute name, member
  or index does. A set's own later version is never its own duplicate.
* **Withheld attributes (§6.8).** A set resolved by someone who cannot read one of
  its members returns that attribute *named and null*, never silently absent — in
  the preview, the fill report and the download manifest.
* **Cascade pin over forty members (§6.6).** With a quality failure injected at the
  39th member in lock order, the cascade rolls back entirely — no member pin left,
  one rollback recorded, the job failed once and not retried; once the data is
  corrected, the same forty pin and seal together.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import io

import pyarrow.parquet as pq
import pytest

from maya.core.errors import ConflictError
from tests.conftest import PX_DEF, approved_feature, price_csv

NS = "eq"
XY = "maya://feature/eq/fsp_xy@v1"
OTHER = "maya://feature/eq/fsp_other@v1"


@pytest.fixture(scope="module")
def members(world):
    two = dict(
        PX_DEF, schema=[{"name": "close", "type": "float64"}, {"name": "volume", "type": "float64"}]
    )
    csv = b"date,symbol,close,volume\n" + b"".join(
        f"2026-01-{d:02d},{s},{100 + d + i:.1f},{1000 * (d + i)}\n".encode()
        for d in range(1, 11)
        for i, s in enumerate(("AAA", "BBB"))
    )
    approved_feature(world, "fsp_xy", csv, definition=two)
    approved_feature(world, "fsp_other", price_csv(10))
    return world


def _set(
    members_,
    *,
    order=("px", "vol"),
    alignment="inner",
    rule=None,
    attr_px="px",
    index=("date", "symbol"),
    px_ref=XY,
):
    entries = {
        "px": {"attr": attr_px, "ref": px_ref, "source_attr": "close"},
        "vol": {"attr": "vol", "ref": XY, "source_attr": "volume"},
    }
    if rule:
        entries["px"]["rule"] = rule
    return {
        "index": list(index),
        "grid": "as_is",
        "alignment": {"mode": alignment},
        "members": [entries[k] for k in order],
    }


def _submit(w, name, definition, **kw):
    w.p.featuresets.create(w.devi, namespace=NS, name=name, definition=definition, **kw)
    return w.p.featuresets.transition(w.devi, f"{NS}/{name}", 1, "submit")


# -- equivalence -------------------------------------------------------------------------------
def test_a_reordered_copy_with_new_metadata_is_refused_naming_the_original(members):
    w = members
    assert _submit(w, "eqv_base", _set(w))["state"] == "in_review"
    with pytest.raises(ConflictError, match="equivalent feature set already exists") as exc:
        _submit(
            w,
            "eqv_copy",
            _set(w, order=("vol", "px")),
            description="a desk's own panel",
            tags=["desk"],
        )
    assert exc.value.context["existing"] == "eqv_base"
    assert "'eqv_base' v1" in exc.value.message and "near-copy" in exc.value.message
    copy = w.p.featuresets.get(w.devi, f"{NS}/eqv_copy")["versions"][0]
    assert copy["state"] == "draft" and copy["definition_hash"] is None


@pytest.mark.parametrize(
    "name, variant",
    [
        ("eqv_outer", {"alignment": "outer"}),
        ("eqv_rule", {"rule": "forward_fill(limit=1)"}),
        ("eqv_renamed", {"attr_px": "price"}),
        ("eqv_member", {"px_ref": OTHER}),
        ("eqv_index", {"index": ("symbol", "date")}),
    ],
)
def test_a_semantic_difference_is_not_a_near_copy(members, name, variant):
    w = members
    if not w.p.featuresets.list(w.devi, q="eqv_base"):
        _submit(w, "eqv_base", _set(w))
    out = _submit(w, name, _set(w, **variant))
    assert out["state"] == "in_review"
    digests = {
        v["definition_hash"]
        for s in ("eqv_base", name)
        for v in w.p.featuresets.get(w.devi, f"{NS}/{s}")["versions"]
    }
    assert len(digests) == 2 and None not in digests


def test_a_sets_own_next_version_is_not_its_own_duplicate(members):
    w = members
    _submit(w, "eqv_self", _set(w, alignment="left"))
    w.p.featuresets.transition(w.mick, f"{NS}/eqv_self", 1, "approve")
    w.p.featuresets.new_draft(w.devi, f"{NS}/eqv_self")
    out = w.p.featuresets.transition(w.devi, f"{NS}/eqv_self", 2, "submit")
    assert out["state"] == "in_review"
    v1, v2 = sorted(
        w.p.featuresets.get(w.devi, f"{NS}/eqv_self")["versions"], key=lambda v: v["version_no"]
    )
    assert v1["definition_hash"] == v2["definition_hash"]


def test_project_of_extend_is_recognised_as_the_directly_written_set(members):
    """§6.8: ``project(extend(S, …), attrs)`` and the directly written equivalent hash
    identically, so the reinvented set is refused and the existing one offered."""
    w = members
    parent = {
        "index": ["date", "symbol"],
        "grid": "as_is",
        "alignment": {"mode": "asof"},
        "members": [
            {"attr": "px", "ref": XY, "source_attr": "close"},
            {"attr": "vol", "ref": XY, "source_attr": "volume"},
            {"attr": "alt", "ref": OTHER, "source_attr": "close"},
        ],
    }
    _submit(w, "eqv_parent", parent)
    w.p.featuresets.transition(w.mick, f"{NS}/eqv_parent", 1, "approve")
    child = {
        "extends": {
            "parent": "maya://featureset/eq/eqv_parent@v1",
            "override": {"drop_attributes": ["alt"]},
        }
    }
    assert _submit(w, "eqv_projected", child)["state"] == "in_review"
    direct = dict(parent, members=parent["members"][:2])
    with pytest.raises(ConflictError) as exc:
        _submit(w, "eqv_direct", direct)
    assert exc.value.context["existing"] == "eqv_projected"
    # an inherited policy that actually says something is part of the meaning
    ruled = {
        "extends": {
            "parent": "maya://featureset/eq/eqv_parent@v1",
            "override": {
                "drop_attributes": ["alt"],
                "global_policy": {"rule": "forward_fill(limit=2)"},
            },
        }
    }
    assert _submit(w, "eqv_projected_ruled", ruled)["state"] == "in_review"


def test_a_sets_inheritance_edge_carries_its_override_count(members):
    """The same §16.3 label on the feature-set side: a desk that inherits a firm panel and
    changes three things says three, not "extends"."""
    w = members
    # attribute names of its own, so this set is not an equivalent of any other here: the
    # §6.8 near-copy guard would rightly refuse a second set that means the same thing
    parent = {
        "index": ["date", "symbol"],
        "grid": "as_is",
        "alignment": {"mode": "left"},
        "members": [
            {"attr": "ovc_px", "ref": XY, "source_attr": "close"},
            {"attr": "ovc_vol", "ref": XY, "source_attr": "volume"},
            {"attr": "ovc_alt", "ref": OTHER, "source_attr": "close"},
        ],
    }
    _submit(w, "ovc_parent", parent)
    w.p.featuresets.transition(w.mick, f"{NS}/ovc_parent", 1, "approve")
    child = {
        "extends": {
            "parent": f"maya://featureset/{NS}/ovc_parent@v1",
            "override": {
                "drop_attributes": ["ovc_alt"],
                "attribute_rules": {"ovc_px": "forward_fill(limit=1)"},
                "alignment": {"mode": "inner"},
            },
        }
    }
    _submit(w, "ovc_desk", child)
    w.p.featuresets.transition(w.mick, f"{NS}/ovc_desk", 1, "approve")
    graph = w.p.ops.lineage(f"maya://featureset/{NS}/ovc_desk@v1", direction="upstream")
    edge = next(e for e in graph["edges"] if e["type"] == "extends")
    assert edge["source"] == f"maya://featureset/{NS}/ovc_parent@v1" and edge["label"] == "3"


# -- withheld attributes -----------------------------------------------------------------------
def test_an_unreadable_member_is_withheld_named_and_null_never_dropped(members):
    w = members
    fs_def = {
        "index": ["date", "symbol"],
        "grid": "as_is",
        "alignment": {"mode": "left"},
        "members": [
            {"attr": "px", "ref": XY, "source_attr": "close"},
            {"attr": "alt", "ref": OTHER, "source_attr": "close"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace=NS, name="wh_panel", definition=fs_def)
    ref = "maya://featureset/eq/wh_panel@v1"
    full = w.p.featuresets.preview(w.devi, ref)
    assert full["manifest"]["withheld"] == []
    assert all(r["alt"] is not None for r in full["rows"])

    other = w.p.access.resolve_object("feature", "eq/fsp_other")
    w.p.access.grant(
        w.admin,
        kind="feature",
        obj=other,
        principal_type="user",
        principal_id="devi",
        level="read",
        deny=True,
    )
    shown = w.p.featuresets.preview(w.devi, ref)
    assert shown["manifest"]["withheld"] == ["alt"]
    assert "alt" in shown["columns"] and shown["total_rows"] == full["total_rows"] > 0
    assert {r["alt"] for r in shown["rows"]} == {None}
    assert [r["px"] for r in shown["rows"]] == [r["px"] for r in full["rows"]]
    res = w.p.featuresets.resolve_ref(w.devi, ref)
    schema = {a["name"]: a for a in res.meta["schema"]}
    assert schema["alt"]["withheld"] is True and not schema["px"].get("withheld")

    download = w.p.featuresets.download(w.devi, ref, fmt="parquet")
    assert download["manifest"]["withheld"] == ["alt"]
    table = pq.read_table(io.BytesIO(download["data"]))
    assert "alt" in table.column_names and table.column("alt").null_count == table.num_rows
    # someone who can read every member still sees the values
    assert w.p.featuresets.preview(w.mick, ref)["manifest"]["withheld"] == []


def test_a_set_whose_every_member_is_unreadable_says_so(members):
    from maya.core.errors import ValidationFailed

    w = members
    xy = w.p.access.resolve_object("feature", "eq/fsp_xy")
    w.p.access.grant(
        w.admin,
        kind="feature",
        obj=xy,
        principal_type="user",
        principal_id="devi",
        level="read",
        deny=True,
    )
    fs_def = {
        "index": ["date", "symbol"],
        "members": [{"attr": "px", "ref": XY, "source_attr": "close"}],
    }
    w.p.featuresets.create(w.devi, namespace=NS, name="wh_none", definition=fs_def)
    with pytest.raises(ValidationFailed, match="cannot read any member") as exc:
        w.p.featuresets.preview(w.devi, "maya://featureset/eq/wh_none@v1")
    assert exc.value.context["withheld"] == ["px"]


# -- the forty-member cascade -----------------------------------------------------------------
XK_DEF = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "x", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "range", "attr": "x", "min": 0, "max": 1000}],
}


def _xk_csv(k: int) -> bytes:
    rows = ["date,symbol,x,kt"] + [
        f"2026-01-{d:02d},{s},{k + d + j:.1f},2026-01-{d:02d}T18:00:00Z"
        for d in range(1, 6)
        for j, s in enumerate(("AAA", "BBB"))
    ]
    return ("\n".join(rows) + "\n").encode()


def test_a_forty_member_cascade_rolls_back_whole_then_seals_whole(world):
    w = world
    refs, ids = [], {}
    for k in range(40):
        name = f"m40_{k:02d}"
        approved_feature(w, name, _xk_csv(k), definition=XK_DEF)
        refs.append(f"maya://feature/eq/{name}@v1")
        ids[w.p.access.resolve_object("feature", f"eq/{name}")["id"]] = name
    lock_order = [ids[i] for i in sorted(ids)]  # the cascade pins in sorted id order
    poisoned = lock_order[38]  # member 39 of 40
    w.p.features.ingest(
        w.dana,
        f"eq/{poisoned}",
        b"date,symbol,x,kt\n2026-01-03,AAA,5000,2026-02-01T00:00:00Z\n",
        fmt="csv",
    )
    fs_def = {
        "index": ["date", "symbol"],
        "alignment": {"mode": "inner"},
        "members": [
            {"attr": f"a{k:02d}", "ref": r, "source_attr": "x"} for k, r in enumerate(refs)
        ],
    }
    w.p.featuresets.create(w.devi, namespace="eq", name="forty", definition=fs_def)
    w.p.featuresets.transition(w.devi, "eq/forty", 1, "submit")
    w.p.featuresets.transition(w.mick, "eq/forty", 1, "approve")

    boom = w.p.featuresets.pin(
        w.mick, "eq/forty", version_no=1, pin_name="boom", as_of=dt.date(2026, 1, 5), cascade=True
    )
    w.drain()
    with w.p.uow() as uow:
        fsp = uow.repo("feature_set_pins").require(boom["pin"]["id"])
        job = uow.repo("jobs").require(boom["job"]["id"])
        rollbacks = uow.repo("audit_events").list(
            action="featureset.cascade_rolled_back", object_ref=fsp["id"]
        )
        left = uow.repo("feature_pins").count(pin_name="boom")
    assert fsp["state"] == "failed" and "quality" in fsp["failure"].lower()
    assert job["state"] == "failed" and job["attempts"] == 1, "a refusal is not retried"
    assert left == 0, "the cascade left member pins behind"
    assert len(rollbacks) == 1
    assert rollbacks[0]["detail"]["member_pins_removed"] == 39  # 38 sealed + the failing one

    # the vendor corrects the value; the same forty now pin and seal as one
    w.p.features.ingest(
        w.dana,
        f"eq/{poisoned}",
        b"date,symbol,x,kt\n2026-01-03,AAA,41.0,2026-02-02T00:00:00Z\n",
        fmt="csv",
    )
    good = w.p.featuresets.pin(
        w.mick, "eq/forty", version_no=1, pin_name="good", as_of=dt.date(2026, 1, 5), cascade=True
    )
    w.drain()
    with w.p.uow() as uow:
        fsp = uow.repo("feature_set_pins").require(good["pin"]["id"])
        member_pins = uow.repo("feature_pins").list(pin_name="good")
    assert fsp["state"] == "sealed", fsp.get("failure")
    assert len(member_pins) == 40 and {p["state"] for p in member_pins} == {"sealed"}
    assert set(fsp["member_pin_ids"].values()) == {p["id"] for p in member_pins}
    assert all(p["content_hash"] for p in member_pins) and fsp["row_count"] == 10
    assert fsp["manifest"]["materialization"]["stored"] is True


# -- a named alignment driver survives pinning --------------------------------------------------
@pytest.mark.parametrize("mode", ["asof", "left"])
def test_a_set_naming_its_alignment_driver_pins(members, mode):
    """Regression: a pin resolves each member through its member pin, so the driver named
    in ``alignment.member`` must be followed there — it once failed every such pin with
    'alignment member … does not carry the set index'."""
    w = members
    name = f"driver_{mode}"
    fs_def = {
        "index": ["date", "symbol"],
        "grid": "as_is",
        "alignment": {"mode": mode, "member": OTHER},
        "members": [
            {"attr": "px", "ref": XY, "source_attr": "close"},
            {"attr": "alt", "ref": OTHER, "source_attr": "close"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace=NS, name=name, definition=fs_def)
    w.p.featuresets.transition(w.devi, f"{NS}/{name}", 1, "submit")
    w.p.featuresets.transition(w.mick, f"{NS}/{name}", 1, "approve")
    live = w.p.featuresets.preview(w.mick, f"maya://featureset/{NS}/{name}@v1")
    out = w.p.featuresets.pin(
        w.mick,
        f"{NS}/{name}",
        version_no=1,
        pin_name="drv",
        as_of=dt.date(2026, 1, 10),
        cascade=True,
    )
    w.drain()
    with w.p.uow() as uow:
        pin = uow.repo("feature_set_pins").require(out["pin"]["id"])
    assert pin["state"] == "sealed", pin.get("failure")
    assert pin["row_count"] == live["total_rows"] > 0
