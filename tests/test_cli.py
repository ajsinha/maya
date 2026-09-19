"""
The command line (``python -m maya.cli``), end to end: every command against a
real platform through the SDK, human and ``--json`` output, and exit codes —
0 on success, 1 when MAYA refuses, 2 for usage errors.

The CLI's ``_client`` is pointed at an in-process platform (with job workers
running, so pins and waits complete); one test drives the genuine ``--local``
branch as well.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import json
import zipfile

import pytest

from maya.cli import __main__ as cli
from tests.conftest import World, approved_feature, build_platform, price_csv
from tests.test_warrants import XY_DEF, complete_spec, xy_csv


@pytest.fixture(scope="module")
def estate():
    from maya.sdk import Client
    from maya.server import build_app
    platform = build_platform()
    platform.jobs.start()
    w = World(platform)
    p = platform
    p.access.create_namespace(w.admin, name="eq", preset="standard")
    approved_feature(w, "px", price_csv(10))
    p.access.create_user(w.admin, username="mgr2", password="Test-password-1",
                         roles=["model_manager"])
    p.access.create_namespace(w.admin, name="quant", preset="standard")
    p.features.create(w.dana, namespace="quant", name="xy", definition=XY_DEF)
    p.features.ingest(w.dana, "quant/xy", xy_csv(), fmt="csv")
    p.features.transition(w.dana, "quant/xy", 1, "submit")
    p.features.transition(w.mick, "quant/xy", 1, "approve")
    fs_def = {"index": ["date", "symbol"], "grid": "as_is", "alignment": {"mode": "inner"},
              "members": [{"attr": a, "ref": "maya://feature/quant/xy@v1", "source_attr": a}
                          for a in ("x", "y")]}
    p.featuresets.create(w.devi, namespace="quant", name="panel", definition=fs_def)
    p.featuresets.transition(w.devi, "quant/panel", 1, "submit")
    p.featuresets.transition(w.mick, "quant/panel", 1, "approve")
    p.models.create(w.mona, namespace="quant", name="linear", formula="yhat = a*x + b",
                    roles={"a": "parameter", "b": "parameter"})
    p.models.update_draft(w.mona, "quant/linear", spec_latex=complete_spec("linear"))
    app = build_app(p)
    anon = Client(app=app, channel="cli")
    clients = {u: Client(app=app, token=anon.auth.login(u, pw)["token"], channel="cli")
               for u, pw in (("admin", "maya-dev-admin"), ("mick", "Test-password-1"),
                             ("mgr", "Test-password-1"))}
    yield w, clients
    platform.shutdown()


@pytest.fixture()
def run(estate, monkeypatch, capsys):
    """``run("feature", "list", json_out=True, who="mick")`` -> (exit, stdout, stderr)."""
    _, clients = estate
    who = {"user": "admin"}
    monkeypatch.setattr(cli, "_client", lambda args: clients[who["user"]])

    def invoke(*argv: str, json_out: bool = False, as_user: str = "admin"
               ) -> tuple[int, str, str]:
        who["user"] = as_user
        capsys.readouterr()
        code = cli.main((["--json"] if json_out else []) + list(argv))
        out = capsys.readouterr()
        return code, out.out, out.err
    return invoke


def test_feature_list_human_and_json(run):
    code, out, _ = run("feature", "list")
    assert code == 0 and out.splitlines()[0].split()[:3] == ["REF", "LATEST_VERSION", "LATEST_STATE"]
    assert "maya://feature/eq/px" in out
    code, out, _ = run("feature", "list", "--namespace", "quant", json_out=True)
    rows = json.loads(out)
    assert code == 0 and [r["name"] for r in rows] == ["xy"]
    code, out, _ = run("feature", "list", "-q", "zzz-no-match")
    assert code == 0 and out.strip() == "(none)"


def test_feature_show_and_an_unknown_ref_exits_1_naming_the_error(run):
    code, out, _ = run("feature", "show", "eq/px")
    assert code == 0 and json.loads(out)["name"] == "px"
    code, out, err = run("feature", "show", "eq/nosuch")
    assert code == cli.EXIT_REFUSED and out == "" and err.startswith("maya: NotFound:")


def test_usage_errors_exit_2(run):
    with pytest.raises(SystemExit) as exc:
        run("feature", "pin", "eq/px")                       # --version, --name, --as-of missing
    assert exc.value.code == cli.EXIT_USAGE
    with pytest.raises(SystemExit) as exc:
        run("nosuchgroup")
    assert exc.value.code == cli.EXIT_USAGE


def test_quick_upload_and_restatement(run, tmp_path):
    csv = tmp_path / "rates.csv"
    csv.write_bytes(price_csv(3, symbols=("ZZZ",)))
    code, out, _ = run("feature", "quick", str(csv))
    assert code == 0 and "scratch.admin/rates@v1: 3 rows, ungoverned" in out
    code, out, _ = run("feature", "quick", str(csv), "--name", "rates2", json_out=True)
    assert code == 0 and json.loads(out)["rows"] == 3
    code, out, _ = run("feature", "upload", "scratch.admin/rates", str(csv),
                       "--knowledge-time", "2026-06-01T00:00:00Z")
    assert code == 0 and out.strip() == "ingested 3 rows (a restatement)"


def test_pin_download_and_diff(run, tmp_path):
    code, out, _ = run("feature", "pin", "eq/px", "--version", "1", "--name", "eom",
                       "--as-of", "2026-01-31")
    assert code == 0 and "sealed " in out and "(20 rows" in out
    dest = tmp_path / "px.parquet"
    code, out, _ = run("feature", "download", "maya://feature/eq/px#eom/2026-01-31",
                       "--out", str(dest))
    assert code == 0 and dest.stat().st_size > 0 and "20 rows" in out
    import pyarrow.parquet as pq
    assert pq.read_table(dest).num_rows == 20
    code, out, _ = run("feature", "download", "eq/px@v1", "--out", str(tmp_path / "px.csv"),
                       "--format", "csv")
    lines = (tmp_path / "px.csv").read_text().splitlines()
    assert code == 0 and lines[0].startswith("# maya-manifest: ")        # self-describing CSV
    assert lines[1].startswith("date,symbol,close") and len(lines) == 22
    code, out, _ = run("feature", "diff", "eq/px", "1", "1")
    assert code == 0 and isinstance(json.loads(out), (dict, list))


def test_featureset_pin_cascade_and_download_shapes(run, tmp_path):
    code, _, err = run("featureset", "pin", "quant/panel", "--version", "1", "--name", "q1",
                       "--as-of", "2026-02-28", "--cascade")
    assert code == cli.EXIT_REFUSED and "role ceiling" in err     # admin is not a data role
    code, out, err = run("featureset", "pin", "quant/panel", "--version", "1", "--name", "q1",
                         "--as-of", "2026-02-28", "--cascade", as_user="mick")
    assert code == 0 and "content_hash" in out, (out, err)
    for shape in ("tabular", "wide"):
        dest = tmp_path / f"panel-{shape}.parquet"
        code, out, _ = run("featureset", "download", "maya://featureset/quant/panel#q1/2026-02-28",
                           "--out", str(dest), "--shape", shape)
        assert code == 0 and dest.stat().st_size > 0 and "rows" in out
    code, _, err = run("featureset", "download", "quant/panel@v1", "--out",
                       str(tmp_path / "t.parquet"), "--shape", "tensor")
    assert code == cli.EXIT_REFUSED and "tabular or wide" in err


def test_model_push_and_diff(run, estate, tmp_path):
    w, _ = estate
    src = tmp_path / "model.py"
    src.write_text("class Model:\n"
                   "    def fit(self, X, y, ctx):\n"
                   "        return {}\n\n"
                   "    def predict(self, X, params, ctx):\n"
                   "        return [params.get('a', 1.0) * v + params.get('b', 0.0) "
                   "for v in X['x']]\n")
    code, out, _ = run("model", "push", "quant/linear", str(src))
    pushed = json.loads(out)
    assert code == 0 and len(pushed["artifact_hash"]) == 64
    code, out, _ = run("job", "watch", pushed["job"]["id"])
    assert code == 0 and '"passed": true' in out
    code, out, _ = run("model", "diff", "quant/linear", "1", "1")
    assert code == 0 and out.strip() == "no change"


def test_warrant_fetch_params_seal_bundle_and_offline_verify(run, estate, tmp_path):
    w, _ = estate
    p = w.p
    p.models.transition(w.mona, "quant/linear", 1, "submit")
    p.models.transition(w.mgr, "quant/linear", 1, "approve")
    tw = p.warrants.create(w.devi, namespace="quant", name="calib", model="quant/linear@v1",
                           featureset="maya://featureset/quant/panel#q1/2026-02-28",
                           spec={"target": "y", "seed": 7})
    dest = tmp_path / "train.parquet"
    code, out, _ = run("warrant", "fetch", tw["id"], "--out", str(dest))
    assert code == 0 and "checksum verified" in out and dest.exists()
    checksum = out.rsplit(" ", 1)[1].strip()
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"values": {"a": 2.0, "b": 0.5}, "metrics": {"rmse": 0.0},
                                  "data_checksum": checksum}))
    code, out, _ = run("warrant", "upload-params", tw["id"], str(params))
    assert code == 0 and "verified data" in out
    params.write_text(json.dumps({"values": {"a": 2.0, "b": 0.5}, "data_checksum": "0" * 64}))
    code, out, _ = run("warrant", "upload-params", tw["id"], str(params))
    assert code == 0 and "UNVERIFIED DATA" in out
    code, _, err = run("warrant", "seal", tw["id"], as_user="mgr")
    assert code == cli.EXIT_REFUSED and err.startswith("maya: NotApproved"), err
    ps = next(x for x in p.warrants.get(w.devi, tw["id"])["parameter_sets"]
              if x["verified_data"])
    p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    p.warrants.transition(w.devi, tw["id"], "submit")
    p.warrants.transition(w.mgr, tw["id"], "approve")
    code, _, err = run("warrant", "seal", tw["id"])
    assert code == cli.EXIT_REFUSED and "role ceiling" in err     # admin is not a model role
    code, out, _ = run("warrant", "seal", tw["id"], as_user="mgr")
    assert code == 0 and json.loads(out)["sealed_at"]
    bundle = tmp_path / "bundle.zip"
    code, out, _ = run("export", "bundle", tw["id"], "--out", str(bundle))
    assert code == 0 and "signed bundle" in out and zipfile.is_zipfile(bundle)
    code, out, _ = run("export", "verify", str(bundle))
    assert code == 0 and "verified: True" in out and "[ok] data content hash" in out
    code, out, _ = run("export", "verify", str(bundle), json_out=True)
    assert code == 0 and json.loads(out)["verified"] is True
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(tampered, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "model/parameters.json":
                data = data.replace(b"2.0", b"3.0")
            dst.writestr(item, data)
    code, out, _ = run("export", "verify", str(tampered))
    assert code == cli.EXIT_REFUSED and "verified: False" in out and "[FAIL]" in out


def test_jobs_watch_and_cancel(run, estate):
    w, _ = estate
    out = w.p.features.pin(w.admin, "eq/px", version_no=1, pin_name="eom",
                           as_of=dt.date(2026, 1, 20))
    code, text, _ = run("job", "watch", out["job"]["id"])
    assert code == 0 and json.loads(text[text.index("{"):])["state"] == "succeeded"
    code, text, err = run("job", "cancel", out["job"]["id"])
    assert code == 0 and json.loads(text)["state"] == "succeeded"   # a finished job stays so
    code, _, err = run("job", "cancel", "0" * 32)
    assert code == cli.EXIT_REFUSED and "NotFound" in err


def test_verify_integrity(run):
    code, out, _ = run("admin", "verify-integrity")
    assert code == 0 and "drift: 0; audit chain ok: True" in out
    code, out, _ = run("admin", "verify-integrity", json_out=True)
    assert json.loads(out)["audit_chain"]["ok"] is True


def test_the_real_local_branch_needs_credentials(monkeypatch, capsys, tmp_path):
    import argparse
    monkeypatch.delenv("MAYA_PASSWORD", raising=False)
    args = argparse.Namespace(local=True, config=str(cli.Path("config/application.yaml")),
                              profile=None)
    from maya.core.errors import MayaError
    from maya.services.platform import Platform
    real_build = Platform.build
    built = []

    def build(settings, start_workers):          # the test harness's settings, no workers
        monkeypatch.setattr(Platform, "build", real_build)
        built.append(build_platform())
        return built[-1]
    monkeypatch.setattr(Platform, "build", build)
    with pytest.raises(MayaError, match="MAYA_USER and MAYA_PASSWORD"):
        cli._client(args)
    monkeypatch.setattr(Platform, "build", build)
    monkeypatch.setenv("MAYA_PASSWORD", "maya-dev-admin")
    client = cli._client(args)
    assert client.auth.me()["username"] == "admin"
    for platform in built:
        platform.shutdown()


def test_rows_formatting():
    assert cli._rows([], ["a"]) == "(none)"
    text = cli._rows([{"a": "x", "bb": 12}, {"a": "longer"}], ["a", "bb"])
    lines = text.splitlines()
    assert lines[0].startswith("A       BB") and lines[2].startswith("longer")
