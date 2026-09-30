"""
The SDK stands alone: end users install it without the rest of MAYA.

A fresh interpreter blocks every import of MAYA outside ``maya.sdk`` (and ``maya_delta``),
then imports every SDK module and uses what an end user uses: a client, a YAML profile, a
server error mapped to its class, canonical hashing, and an offline bundle opened, verified
and scored from its signed formula. If any of it reached back into the server's code, the
blocked import would fail the child process.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from tests.test_sdk_modes import bundle  # noqa: F401 - the signed bundle fixture, reused
from tests.test_warrants import journey  # noqa: F401 - what the bundle fixture builds on

ROOT = Path(__file__).resolve().parents[1]

CHILD = textwrap.dedent(
    r"""
    import importlib, importlib.abc, pkgutil, sys, os

    class Blocked(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            top, _, rest = name.partition(".")
            if name == "maya_delta" or name.startswith("maya_delta."):
                raise ImportError(f"blocked: {name} is not part of the SDK")
            if top == "maya" and rest and not (rest == "sdk" or rest.startswith("sdk.")):
                raise ImportError(f"blocked: {name} is not part of the SDK")
            return None

    sys.meta_path.insert(0, Blocked())

    import maya.sdk
    expect = os.environ.get("SDK_FROM")
    assert not expect or maya.sdk.__file__.startswith(expect), maya.sdk.__file__
    for mod in pkgutil.walk_packages(maya.sdk.__path__, "maya.sdk."):
        importlib.import_module(mod.name)

    # a client, built without a network call
    client = maya.sdk.connect(base_url="http://127.0.0.1:1", api_key="maya_dev_x")
    assert client is not None

    # a YAML profile with a placeholder
    from pathlib import Path
    home = Path(os.environ["SDK_HOME"])
    (home / ".maya").mkdir(parents=True, exist_ok=True)
    (home / ".maya" / "config.yaml").write_text(
        'profiles:\n  prod:\n    base_url: "https://${PROD_HOST:localhost}"\n', encoding="utf-8"
    )
    Path.home = staticmethod(lambda: home)
    from maya.sdk.client import _profile
    assert _profile("prod")["base_url"] == "https://maya.example.com"

    # a server refusal becomes the same class the server raised
    from maya.sdk._shared.errors import ERRORS_BY_CODE, NotFound
    assert ERRORS_BY_CODE["not_found"] is NotFound

    # canonical hashing
    import pyarrow as pa
    from maya.sdk._shared.canonical import table_content_hash
    assert len(table_content_hash(pa.table({"x": [1.0, 2.0]}))) == 64

    # an offline bundle: opened, verified, scored from the signed IR
    import numpy as np
    off = maya.sdk.offline(os.environ["BUNDLE"])
    assert off.verify()["verified"] is True
    np.testing.assert_allclose(off.predict({"x": np.array([1.0, 2.0])})["yhat"], [2.5, 4.5])

    leaked = sorted(
        m for m in sys.modules
        if m.startswith("maya.") and not m.startswith("maya.sdk")
    )
    assert not leaked, leaked
    print("standalone ok")
    """
)


def _wheel(project: Path, out: Path, stem: str) -> Path:
    """Build one project's wheel exactly as a release would, from its own directory."""
    import shutil

    shutil.rmtree(project / "build", ignore_errors=True)  # nothing stale can ride along
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "-q",
            "-w",
            str(out),
            str(project),
        ],
        check=True,
        capture_output=True,
    )
    return sorted(out.glob(f"{stem}-*.whl"))[-1]


def test_the_sdk_imports_and_works_with_the_rest_of_maya_blocked(bundle, tmp_path):  # noqa: F811
    _, _, raw = bundle
    path = tmp_path / "calib.zip"
    path.write_bytes(raw)
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(ROOT),
        "BUNDLE": str(path),
        "SDK_HOME": str(tmp_path / "home"),
        "PROD_HOST": "maya.example.com",
    }
    out = subprocess.run(
        [sys.executable, "-c", CHILD], env=env, cwd=tmp_path, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr[-3000:]
    assert "standalone ok" in out.stdout


def test_the_maya_sdk_wheel_carries_only_the_sdk_and_works_from_it_alone(bundle, tmp_path):  # noqa: F811
    """Built, unpacked where nothing else of MAYA exists, and used: the distribution end
    users install is exactly the SDK, and enough on its own."""
    import zipfile

    wheel = _wheel(ROOT / "sdk", tmp_path / "dist", "maya_sdk")
    names = zipfile.ZipFile(wheel).namelist()
    code = [n for n in names if not n.startswith("maya_sdk-")]
    assert code and all(n.startswith("maya/sdk/") for n in code), code
    assert "maya/__init__.py" not in names  # a namespace package: installs beside the server
    site = tmp_path / "site"
    zipfile.ZipFile(wheel).extractall(site)
    _, _, raw = bundle
    (tmp_path / "calib.zip").write_bytes(raw)
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(site),  # the wheel, and nothing from this repository
        "SDK_FROM": str(site),
        "BUNDLE": str(tmp_path / "calib.zip"),
        "SDK_HOME": str(tmp_path / "home"),
        "PROD_HOST": "maya.example.com",
    }
    out = subprocess.run(
        [sys.executable, "-c", CHILD], env=env, cwd=tmp_path, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr[-3000:]
    assert "standalone ok" in out.stdout


def test_the_server_wheel_never_bundles_the_sdk_and_depends_on_it(tmp_path):
    """The SDK is released on its own; the server installs it as a dependency, like any
    client, and carries no copy of it."""
    import zipfile

    wheel = _wheel(ROOT, tmp_path / "dist", "maya")
    z = zipfile.ZipFile(wheel)
    assert not [n for n in z.namelist() if n.startswith("maya/sdk/")]
    assert "maya/core/errors.py" in z.namelist()  # the server's own code is there
    meta = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
    assert "Requires-Dist: maya-sdk" in z.read(meta).decode()
