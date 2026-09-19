"""
Defects found by exercising the runbooks, each pinned by a test.

* the estate load refuses, before writing anything: a non-empty target, data this
  version does not know (unless allow_drop, which then names what went), and an
  estate whose own audit chain does not link;
* reinstating a warrant that is not suspended is refused;
* a custody anchor signed by a key other than this MAYA's is reported;
* the lake seam reports native only when maya_delta's own self-check passes;
* a CLI (--local) platform runs job workers but neither webhooks nor the scheduler;
* a training warrant keeps what a bare or undated feature-set reference meant;
* a model that declares parameters runs only under a named, approved parameter set.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import io
import json
import threading
import zipfile

import pytest

from maya.core.errors import NotApproved, ValidationFailed
from maya.core.version import VERSION
from maya.persistence import estate
from tests.conftest import World, approved_feature, build_platform, price_csv
from tests.test_warrants import journey  # noqa: F401 - the fixture, reused


def _rewrite(data: bytes, table: str, fn) -> bytes:
    """The estate with ``fn`` applied to one table's rows, its hash kept consistent."""
    src = zipfile.ZipFile(io.BytesIO(data))
    manifest = json.loads(src.read("manifest.json"))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.namelist():
            if item in ("manifest.json", f"tables/{table}.jsonl"):
                continue
            dst.writestr(item, src.read(item))
        rows = [json.loads(line) for line in src.read(f"tables/{table}.jsonl").decode()
                .splitlines() if line]
        body = "\n".join(json.dumps(r, sort_keys=True) for r in fn(rows))
        import hashlib
        manifest["tables"][table]["sha256"] = hashlib.sha256(body.encode()).hexdigest()
        dst.writestr(f"tables/{table}.jsonl", body)
        dst.writestr("manifest.json", json.dumps(manifest))
    return out.getvalue()


@pytest.fixture(scope="module")
def exported():
    platform = build_platform()
    w = World(platform)
    platform.access.create_namespace(w.admin, name="eq")
    approved_feature(w, "est_px", price_csv(3))
    data = estate.export(platform.db, VERSION)
    yield platform, data
    platform.shutdown()


def test_an_estate_loads_only_into_an_empty_database(exported):
    platform, data = exported
    with pytest.raises(ValidationFailed, match="already holds data"):
        platform.ops.import_estate(data)


def test_data_this_version_does_not_know_is_refused_unless_dropped_on_purpose(exported):
    platform, data = exported
    extra = _rewrite(data, "features", lambda rows: [{**r, "legacy_note": "x"} for r in rows])
    platform.db.init_schema(force=True)
    with pytest.raises(ValidationFailed, match="features: legacy_note"):
        platform.ops.import_estate(extra)
    with platform.uow() as uow:
        assert uow.repo("features").count() == 0, "nothing was written"
    out = platform.ops.import_estate(extra, allow_drop=True)
    assert out["dropped"] == {"features": ["legacy_note"]} and out["audit_chain"]["ok"]


def test_a_broken_chain_is_refused_before_anything_is_written(exported):
    platform, data = exported
    broken = _rewrite(data, "audit_events",
                      lambda rows: [{**r, "actor": "mallory"} if r["seq"] == 2 else r
                                    for r in rows])
    platform.db.init_schema(force=True)
    with pytest.raises(ValidationFailed, match="audit chain does not verify") as exc:
        platform.ops.import_estate(broken)
    assert exc.value.context["broken_at"] == 2
    with platform.uow() as uow:
        assert uow.repo("audit_events").count() == 0 and uow.repo("features").count() == 0
    platform.ops.import_estate(data)                   # the intact estate still loads


def test_reinstating_a_warrant_that_is_not_suspended_is_refused(journey):  # noqa: F811
    w = journey
    from tests.test_warrants import complete_spec
    w.p.models.create(w.mona, namespace="quant", name="rb_model", formula="y = 2*x")
    # nothing to fit: an execution warrant needs no training warrant
    w.p.models.update_draft(w.mona, "quant/rb_model", spec_latex=complete_spec("rb_model"))
    w.p.models.transition(w.mona, "quant/rb_model", 1, "submit")
    w.p.models.transition(w.mgr, "quant/rb_model", 1, "approve")
    ew = w.p.execution.create(w.mgr, namespace="quant", name="rb_live", model="quant/rb_model@v1")
    with pytest.raises(NotApproved, match="not suspended"):
        w.p.execution.reinstate(w.admin, ew["id"], "no reason")
    with w.p.uow() as uow:
        events = uow.repo("custody_events").list(warrant_id=ew["id"], event="reinstated")
    assert events == [], "a refused reinstatement leaves no custody event"


def test_an_anchor_signed_by_another_key_is_reported(world, tmp_path):
    from maya.core.crypto import Signer
    from maya.core import djson
    from maya.services.custody import CustodyService
    svc = CustodyService(world.p)
    svc.methods, svc.path = ["signature"], tmp_path / "a.jsonl"
    row = svc.anchor()
    rogue = Signer(tmp_path / "rogue-keys")
    body = djson.canonical({"seq": row["seq"], "head": row["head_hash"],
                            "at": row["detail"]["at"]}).encode()
    with world.p.uow() as uow:
        uow.repo("anchors").update(row["id"], {"signature": rogue.signature_block(body)})
    mine = [b for b in svc.verify()["broken"] if b["seq"] == row["seq"]]
    assert mine and "not this MAYA's" in " ".join(mine[0]["problems"])


def test_the_lake_seam_reports_native_only_when_the_self_check_passes(monkeypatch):
    import maya_delta
    from maya.core import backends
    monkeypatch.setattr(maya_delta, "_native_problem", lambda: "self-check failed")
    assert backends._native_lake_usable() is False
    monkeypatch.setattr(maya_delta, "_native_problem", lambda: None)
    assert backends._native_lake_usable() is backends.has_module("deltalake")


def test_a_cli_platform_runs_jobs_but_not_webhooks_or_the_scheduler():
    before = {t.name for t in threading.enumerate()}
    cli = build_platform(start_workers="jobs")         # what `maya --local` builds
    try:
        names = {t.name for t in threading.enumerate()} - before
        assert any(n.startswith("maya-worker") for n in names)
        assert "maya-webhooks" not in names
        assert cli.service("webhooks")._thread is None
    finally:
        cli.shutdown()



def test_a_warrant_keeps_what_a_bare_or_undated_reference_meant(journey):  # noqa: F811
    w = journey
    from tests.test_warrants import complete_spec
    w.p.models.create(w.mona, namespace="quant", name="rb_fixed", formula="y = 2*x")
    w.p.models.update_draft(w.mona, "quant/rb_fixed", spec_latex=complete_spec("rb_fixed"))
    w.p.models.transition(w.mona, "quant/rb_fixed", 1, "submit")
    w.p.models.transition(w.mgr, "quant/rb_fixed", 1, "approve")
    bare = w.p.warrants.create(w.devi, namespace="quant", name="rb_bare",
                               model="quant/rb_fixed@v1", featureset="quant/panel",
                               spec={"target": "y"})
    assert bare["featureset_ref"] == "maya://featureset/quant/panel@v1"
    undated = w.p.warrants.create(w.devi, namespace="quant", name="rb_undated",
                                  model="quant/rb_fixed@v1",
                                  featureset="maya://featureset/quant/panel#q1",
                                  spec={"target": "y"})
    assert undated["featureset_ref"] == "maya://featureset/quant/panel#q1/2026-02-28"
    with w.p.uow() as uow:
        ev = uow.repo("custody_events").find_one(warrant_id=bare["id"], event="created")
    assert ev["detail"]["featureset_as_given"] == "quant/panel", "the bare name is logged"


def test_a_trainable_model_runs_only_under_a_named_approved_parameter_set(journey):  # noqa: F811
    w = journey
    from tests.test_warrants import complete_spec
    w.p.models.create(w.mona, namespace="quant", name="rb_fit", formula="yhat = a*x",
                      roles={"a": "parameter"})
    w.p.models.update_draft(w.mona, "quant/rb_fit", spec_latex=complete_spec("rb_fit"))
    w.p.models.transition(w.mona, "quant/rb_fit", 1, "submit")
    w.p.models.transition(w.mgr, "quant/rb_fit", 1, "approve")
    with pytest.raises(ValidationFailed, match="needs a training warrant"):
        w.p.execution.create(w.mgr, namespace="quant", name="rb_direct", model="quant/rb_fit@v1")
    tw = w.p.warrants.create(w.devi, namespace="quant", name="rb_fit_tw",
                             model="quant/rb_fit@v1",
                             featureset="maya://featureset/quant/panel#q1/2026-02-28",
                             spec={"target": "y"})
    with pytest.raises(ValidationFailed, match="name the approved parameter set"):
        w.p.execution.create(w.mgr, namespace="quant", name="rb_noparams",
                             training_warrant_id=tw["id"])
    # the approval check refuses a row that got past creation some other way (older data)
    with w.p.uow() as uow:
        mv = uow.repo("model_versions").require(tw["model_version_id"])
        ok, why = w.p.execution.check_params(uow, {"row": {"parameter_set_id": None,
                                                           "model_version_id": mv["id"]}})
    assert not ok and "declares parameters" in why
