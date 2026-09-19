"""
SDK modes (§18.2.3, §18.2.7): record/replay fixtures and ``offline(bundle)``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pytest

from maya.core.errors import NotFound, PermissionDenied, ValidationFailed
from maya.sdk import Client, offline
from maya.sdk.offline import NotInBundle
from maya.sdk.replay import ReplayMiss
from tests.conftest import PASSWORD, approved_feature, price_csv
from tests.test_warrants import complete_spec, journey  # noqa: F401 - the fixture, reused


# -- record / replay ----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def api(world):
    from maya.api.app import create_api

    app = create_api(world.p)
    approved_feature(world, "taped", price_csv(4))
    return world, app


def _login(app, user):
    password = "maya-dev-admin" if user == "admin" else PASSWORD
    return Client(app=app).auth.login(user, password)["token"]


def test_a_recording_replays_with_no_server(api, tmp_path):
    w, app = api
    tape = tmp_path / "catalog.json"
    live = Client.record(tape, app=app, token=_login(app, "dana"))
    assert live.mode == "record (inproc)"
    listed = live.features.list(namespace="eq")
    shown = live.features.get("eq/taped")
    preview = live.features.preview("maya://feature/eq/taped@v1")
    download = live.features.download("maya://feature/eq/taped@v1", format="csv")
    with pytest.raises(NotFound):
        live.features.get("eq/nowhere")

    replayed = Client.replay(tape)
    assert replayed.mode == "replay"
    assert replayed.features.list(namespace="eq") == listed
    assert replayed.features.get("eq/taped") == shown
    assert replayed.features.preview("maya://feature/eq/taped@v1") == preview
    again = replayed.features.download("maya://feature/eq/taped@v1", format="csv")
    assert again["data"] == download["data"] and again["manifest"] == download["manifest"]
    with pytest.raises(NotFound, match="nowhere"):
        replayed.features.get("eq/nowhere")


def test_a_refusal_replays_as_the_same_typed_error(api, tmp_path):
    w, app = api
    tape = tmp_path / "refusal.json"
    live = Client.record(tape, app=app, token=_login(app, "dana"))
    with pytest.raises(PermissionDenied) as recorded:
        live.admin.create_user("mallory", password="Mallory-pass-1", roles=["admin"])
    with pytest.raises(PermissionDenied) as replayed:
        Client.replay(tape).admin.create_user("mallory", password="Mallory-pass-1", roles=["admin"])
    assert replayed.value.message == recorded.value.message


def test_unrecorded_and_exhausted_requests_fail_loudly(api, tmp_path):
    w, app = api
    tape = tmp_path / "one.json"
    Client.record(tape, app=app, token=_login(app, "dana")).features.list(namespace="eq")
    replay = Client.replay(tape)
    with pytest.raises(ReplayMiss, match="No recorded response for GET /features"):
        replay.features.list(namespace="other")
    replay.features.list(namespace="eq")
    replay.features.list(namespace="eq")  # a read polled more than recorded repeats
    with pytest.raises(ReplayMiss, match="POST /features"):
        replay.features.create("eq", "never", {})


def test_identical_calls_replay_in_recorded_order(api, tmp_path):
    w, app = api
    tape = tmp_path / "order.json"
    live = Client.record(tape, app=app, token=_login(app, "admin"))
    before = live.access.inbox()
    w.p.access.create_user(w.admin, username="newcomer", password=PASSWORD, roles=[])
    users_1 = live.admin.users()
    w.p.access.create_user(w.admin, username="newcomer2", password=PASSWORD, roles=[])
    users_2 = live.admin.users()
    assert len(users_2) == len(users_1) + 1
    replay = Client.replay(tape)
    assert replay.access.inbox() == before
    assert replay.admin.users() == users_1 and replay.admin.users() == users_2


def test_a_cassette_never_holds_a_credential(api, tmp_path):
    w, app = api
    tape = tmp_path / "creds.json"
    anon = Client.record(tape, app=app)
    token = anon.auth.login("dana", PASSWORD)["token"]
    text = tape.read_text()
    assert token not in text and "<redacted>" in text


def test_the_async_client_records_and_replays_and_shares_cassettes(api, tmp_path):
    """AsyncClient.record / replay, and a cassette from either client replays in the other."""
    import asyncio

    from maya.sdk import AsyncClient

    _, app = api
    token = _login(app, "dana")

    async def record_async(tape):
        live = AsyncClient.record(tape, app=app, token=token)
        assert live.mode == "record (inproc)"
        shown = await live.features.get("eq/taped")
        with pytest.raises(NotFound):
            await live.features.get("eq/nowhere")
        await live.aclose()
        return shown

    async def replay_async(tape):
        replayed = AsyncClient.replay(tape)
        shown = await replayed.features.get("eq/taped")
        with pytest.raises(NotFound, match="nowhere"):
            await replayed.features.get("eq/nowhere")
        with pytest.raises(ReplayMiss):
            await replayed.features.list()
        await replayed.aclose()
        return shown

    async_tape, sync_tape = tmp_path / "async.json", tmp_path / "sync.json"
    shown = asyncio.run(record_async(async_tape))
    assert asyncio.run(replay_async(async_tape)) == shown
    assert Client.replay(async_tape).features.get("eq/taped") == shown  # async -> sync
    live = Client.record(sync_tape, app=app, token=token)
    live.features.get("eq/taped")
    with pytest.raises(NotFound):
        live.features.get("eq/nowhere")
    assert asyncio.run(replay_async(sync_tape)) == shown  # sync -> async


def test_a_file_that_is_not_a_cassette_is_refused(tmp_path):
    bogus = tmp_path / "x.json"
    bogus.write_text('{"entries": []}')
    with pytest.raises(Exception, match="not a MAYA cassette"):
        Client.replay(bogus)


# -- offline --------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def bundle(journey):  # noqa: F811
    w = journey
    w.p.models.create(
        w.mona,
        namespace="quant",
        name="offline_lin",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    w.p.models.update_draft(w.mona, "quant/offline_lin", spec_latex=complete_spec("offline_lin"))
    w.p.models.transition(w.mona, "quant/offline_lin", 1, "submit")
    w.p.models.transition(w.mgr, "quant/offline_lin", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="offline_calib",
        model="quant/offline_lin@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 3},
    )
    data = w.p.warrants.data(w.devi, tw["id"])
    ps = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": 0.5}, data_checksum=data["manifest"]["checksum"]
    )
    w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    exported = w.p.bundles.export(w.devi, tw["id"])
    return w, tw, w.p.blobs.get(exported["blob"])


def test_a_composite_model_is_re_executed_by_the_bundle_verifier(bundle):
    """A composite of closed-form members ships generated code for the whole DAG, and
    the bundle's own verify.py re-executes it to the exported output hash."""
    import json as _json

    from maya.services.bundle import run_verifier

    w, _, _ = bundle
    w.p.models.create(
        w.mona, namespace="quant", name="lift", formula="z = c*x", roles={"c": "parameter"}
    )
    for name in ("lift",):
        w.p.models.update_draft(w.mona, f"quant/{name}", spec_latex=complete_spec(name))
        w.p.models.transition(w.mona, f"quant/{name}", 1, "submit")
        w.p.models.transition(w.mgr, f"quant/{name}", 1, "approve")
    ir = {
        "outputs": [{"name": "yhat", "type": "float64"}],
        "inputs": [{"name": "w", "type": "float64", "role": "parameter"}],
        "composite": {
            "kind": "ensemble",
            "members": [
                {"alias": "lin", "ref": "maya://model/quant/offline_lin@v1"},
                {"alias": "lift", "ref": "maya://model/quant/lift@v1"},
            ],
            "combine": {
                "op": "add",
                "args": [
                    {"ref": "lin.yhat"},
                    {"op": "mul", "args": [{"param": "w"}, {"ref": "lift.z"}]},
                ],
            },
        },
    }
    w.p.models.create(w.mona, namespace="quant", name="blend", kind="composite")
    w.p.models.update_draft(w.mona, "quant/blend", ir=ir, spec_latex=complete_spec("blend"))
    w.p.models.transition(w.mona, "quant/blend", 1, "submit")
    w.p.models.transition(w.mgr, "quant/blend", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="blend_calib",
        model="quant/blend@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 3},
    )
    data = w.p.warrants.data(w.devi, tw["id"])
    w.p.warrants.upload_parameters(
        w.devi,
        tw["id"],
        values={"lin.a": 2.0, "lin.b": 0.5, "lift.c": 0.1, "w": 0.3},
        data_checksum=data["manifest"]["checksum"],
    )
    exported = w.p.bundles.export(w.devi, tw["id"])
    manifest = exported["manifest"]
    assert manifest["reexecutable"] and manifest["model_inputs"] == ["x"], manifest
    raw = w.p.blobs.get(exported["blob"])
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert "def _member_lin" in z.read("model/reference_model.py").decode()
        assert set(_json.loads(z.read("model/member_irs.json"))) == {"lin", "lift"}
        script = z.read("verify.py").decode()
    report = run_verifier(raw, script)
    assert report["verified"], report
    check = next(c for c in report["checks"] if c["check"] == "re-execution output hash")
    assert check["ok"] and check["detail"] == manifest["output_hash"]
    x = np.array([1.0, 2.0, 3.0])
    got = offline(raw).predict({"x": x})["yhat"]  # the SDK, offline, same answer
    np.testing.assert_allclose(got, 2.0 * x + 0.5 + 0.3 * 0.1 * x)


def test_offline_serves_the_read_api_from_a_verified_bundle(bundle, tmp_path):
    w, tw, raw = bundle
    path = tmp_path / "calib.zip"
    path.write_bytes(raw)
    off = offline(path)
    assert off.mode == "offline" and all(c["ok"] is not False for c in off.report)
    assert off.verify()["verified"] is True
    uri = w.p.warrants.get(w.devi, tw["id"])["uri"]
    got = off.training.get()
    assert got["uri"] == uri == off.manifest["warrant"] and got["offline"] is True
    assert off.training.get(uri)["name"] == "offline_calib"
    table, manifest = off.training_data()
    assert table.num_rows > 0 and manifest["checksum"] == off.checksum
    assert "holdout" in manifest["partition"]
    assert off.parameters() == {"a": 2.0, "b": 0.5}
    model = off.models.get()["versions"][0]
    assert (
        model["formula_ir"]["outputs"][0]["name"] == "yhat" and "\\section" in model["spec_latex"]
    )
    assert off.certificate()["status"] == "certified"


def test_offline_predicts_from_the_signed_ir_not_the_bundled_code(bundle):
    w, tw, raw = bundle
    off = offline(raw)
    out = off.predict({"x": np.array([1.0, 2.0])})
    np.testing.assert_allclose(out["yhat"], [2.5, 4.5])
    np.testing.assert_allclose(off.predict({"x": np.array([1.0])}, {"a": 1, "b": 0})["yhat"], [1.0])


def test_offline_refuses_what_a_bundle_does_not_hold(bundle):
    w, tw, raw = bundle
    off = offline(raw)
    with pytest.raises(NotInBundle, match="features.list\\(\\) needs a live MAYA"):
        off.features.list()
    with pytest.raises(NotInBundle, match="training.seal"):
        off.training.seal(tw["id"])
    with pytest.raises(NotInBundle, match="not 'someone-else'"):
        off.training.get("someone-else")


def _tamper(raw: bytes, member: str, content: bytes | None = None) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            body = src.read(item.filename)
            if item.filename == member:
                body = content if content is not None else body + b" "
            dst.writestr(item, body)
    return out.getvalue()


def test_a_tampered_bundle_is_refused_before_anything_is_read(bundle):
    w, tw, raw = bundle
    with pytest.raises(ValidationFailed, match="file hash model/parameters.json"):
        offline(_tamper(raw, "model/parameters.json", b'{"a": 9.0, "b": 0.5}'))
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("manifest.json"))
    manifest["signature"]["signature"] = manifest["signature"]["signature"][::-1]
    with pytest.raises(ValidationFailed, match="signature"):
        offline(_tamper(raw, "manifest.json", json.dumps(manifest).encode()))
    with pytest.raises(ValidationFailed, match="not a zip"):
        offline(b"not a bundle")
