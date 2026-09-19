"""
The public surface: the API through the SDK (in-process and over a real
socket started by ``run_maya_web.py``), typed problem documents, API-key
scoping, the CLI, and the CI gates — each shown to pass and, with a planted
violation, to fail (a gate nobody has seen fail is a gate nobody knows works).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest

from maya.core.errors import NotAuthenticated, NotFound, PermissionDenied, ValidationFailed
from maya.sdk import Client
from tests.conftest import PASSWORD, ROOT, World, build_platform, price_csv

CI = ROOT / "tools" / "ci"


@pytest.fixture(scope="module")
def api():
    platform = build_platform()
    w = World(platform)
    from maya.api.app import create_api
    app = create_api(platform)
    yield w, app
    platform.shutdown()


def _login(app, user, password=PASSWORD):
    return Client(app=app, token=Client(app=app).auth.login(user, password)["token"])


def test_problem_documents_map_to_typed_errors(api):
    w, app = api
    with pytest.raises(NotAuthenticated):
        Client(app=app).features.list()
    admin = _login(app, "admin", "maya-dev-admin")
    with pytest.raises(NotFound):
        admin.features.get("nowhere/nothing")
    dana = _login(app, "dana")
    with pytest.raises(PermissionDenied):
        dana.admin.create_user("eve", password=PASSWORD)
    with pytest.raises(ValidationFailed):
        admin.namespaces.create("bad name!")


def test_lockout_after_repeated_failures(api):
    w, app = api
    anon = Client(app=app)
    for _ in range(5):
        with pytest.raises(NotAuthenticated):
            anon.auth.login("tess", "wrong-password")
    with pytest.raises(NotAuthenticated, match="locked"):
        anon.auth.login("tess", PASSWORD)


def test_api_key_scope_environment_and_revocation(api):
    w, app = api
    admin = _login(app, "admin", "maya-dev-admin")
    admin.namespaces.create("keyed")
    dana = _login(app, "dana")
    key = dana.auth.create_api_key("ro", actions=["read"], days=7)
    kc = Client(app=app, api_key=key["api_key"])
    assert kc.auth.me()["principal_type"] == "api_key"
    kc.features.list()
    uat = key["api_key"].replace("maya_dev_", "maya_uat_")
    with pytest.raises(NotAuthenticated, match="uat"):
        Client(app=app, api_key=uat).features.list()
    with pytest.raises(PermissionDenied, match="roles you do not hold"):
        dana.auth.create_api_key("escalate", roles=["admin"])
    dana.auth.revoke_api_key(key["key_id"])
    with pytest.raises(NotAuthenticated):
        kc.features.list()


def test_credentials_are_refused_over_plain_http_to_remote_hosts():
    with pytest.raises(ValidationFailed, match="plain HTTP"):
        Client("http://maya.example.com", api_key="maya_dev_x_y")
    Client("http://127.0.0.1:1", api_key="maya_dev_x_y").close()


def test_openapi_is_published_and_complete(api):
    _, app = api
    doc = app.openapi()
    assert doc["info"]["version"]
    assert "/api/v1/features/{namespace}/{name}/pins" in doc["paths"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_real_server_over_http_with_sdk_and_cli(tmp_path):
    """`python run_maya_web.py` on a real socket, driven by the SDK and the CLI."""
    port = _free_port()
    env = dict(os.environ, MAYA_HOME=str(tmp_path), PYTHONPATH=str(ROOT))
    proc = subprocess.Popen([sys.executable, str(ROOT / "run_maya_web.py"),
                             f"--server.port={port}", "--jobs.workers=1"],
                            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 90          # a loaded machine starts slowly, not never
        while True:
            try:
                import httpx
                if httpx.get(url + "/readyz", timeout=1).status_code == 200:
                    break
            except Exception:  # noqa: BLE001 - not up yet
                pass
            if proc.poll() is not None or time.monotonic() > deadline:
                proc.kill()
                raise AssertionError(proc.stdout.read().decode() if proc.stdout else "no output")
            time.sleep(0.25)
        c = Client(url, token=Client(url).auth.login("admin", "maya-dev-admin")["token"])
        assert c.admin.health()["database"]["dialect"] == "sqlite"
        key = c.auth.create_api_key("cli", days=1)["api_key"]
        data = tmp_path / "px.csv"
        data.write_bytes(price_csv(5))
        cli_env = dict(env, MAYA_URL=url, MAYA_API_KEY=key)
        out = subprocess.run([sys.executable, "-m", "maya.cli", "--json", "feature", "quick",
                              str(data), "--name", "clipx"], cwd=ROOT, env=cli_env,
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr
        assert "scratch.admin/clipx" in out.stdout
        listing = subprocess.run([sys.executable, "-m", "maya.cli", "feature", "list"],
                                 cwd=ROOT, env=cli_env, capture_output=True, text=True,
                                 timeout=120)
        assert "clipx" in listing.stdout
        home = c.admin.health()
        assert home["audit_chain"]["ok"]
    finally:
        proc.terminate()
        proc.wait(timeout=20)


# -- gates, green and red ---------------------------------------------------------------------
def _gate(name: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CI / name)], cwd=ROOT, capture_output=True,
                          text=True, timeout=300)


@pytest.mark.parametrize("gate", ["file_size.py", "import_boundaries.py", "seam_imports.py",
                                  "version_single_source.py", "no_secrets.py",
                                  "table_contract.py", "sdk_parity.py"])
def test_gate_is_green(gate):
    result = _gate(gate)
    assert result.returncode == 0, result.stdout


PLANTS = {
    "import_boundaries.py": ("maya/services/_planted.py", "import sqlalchemy\n"),
    "seam_imports.py": ("maya/services/_planted.py", "import orjson\n"),
    "file_size.py": ("maya/services/_planted.py", "".join(f"x{i} = {i}\n" for i in range(1600))),
    "table_contract.py": ("maya/web/templates/_planted.html", "<table><tr><td>x</td></tr></table>"),
    "version_single_source.py": ("maya/services/_planted.py", None),
}


@pytest.mark.parametrize("gate", sorted(PLANTS))
def test_gate_fails_on_a_planted_violation(gate):
    rel, content = PLANTS[gate]
    if content is None:
        from maya.core.version import VERSION
        content = f'VERSION = "{VERSION}"\n'
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    try:
        result = _gate(gate)
        assert result.returncode == 1, f"{gate} did not fail:\n{result.stdout}"
    finally:
        path.unlink()


def test_web_import_boundary_fails_when_web_reaches_past_the_sdk():
    path = ROOT / "maya" / "web" / "_planted.py"
    path.write_text("from maya.services.platform import Platform\n")
    try:
        assert _gate("import_boundaries.py").returncode == 1
    finally:
        path.unlink()


def test_schema_drift_gate_fails_after_a_hand_edit():
    target = ROOT / "maya" / "persistence" / "schema" / "sqlite.sql"
    original = target.read_bytes()
    target.write_bytes(original + b"-- hand edit\n")
    try:
        result = subprocess.run([sys.executable, str(CI / "gen_schema.py"), "--check"],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert result.returncode == 1
    finally:
        target.write_bytes(original)


def test_denials_are_audited_even_though_they_roll_back(api):
    """A refusal is the exception that rolls the transaction back; its audit must survive."""
    w, app = api
    w.p.access.create_namespace(w.admin, name="denied")
    from tests.conftest import PX_DEF
    w.p.features.create(w.dana, namespace="denied", name="f", definition=PX_DEF)
    before = len(w.p.access.audit_log(w.admin, action="authz.denied"))
    with pytest.raises(PermissionDenied):
        w.p.access.grant(w.mick, kind="feature",
                         obj=w.p.access.resolve_object("feature", "denied/f"),
                         principal_type="user", principal_id="mick", level="own")
    after = w.p.access.audit_log(w.admin, action="authz.denied")
    assert len(after) == before + 1
    assert w.p.access.verify_audit()["ok"]
