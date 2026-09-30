"""
Build the ``maya-sdk`` distribution: the SDK alone, for end users who have no MAYA server.

The SDK lives in this repository at ``maya/sdk`` and stands on its own -- it imports nothing
from MAYA outside ``maya.sdk`` (``tests/test_sdk_standalone.py`` proves it). ``maya`` is a
namespace package, so this wheel carries only ``maya/sdk/`` and installs beside nothing else;
the server's own distribution already includes the SDK, so install one or the other.

    python tools/ops/build_sdk.py                # wheel into dist/
    python tools/ops/build_sdk.py --out /tmp/w   # somewhere else

Dependencies: httpx, PyYAML, pyarrow and numpy. Extras: ``offline`` (``cryptography``, to
check a bundle's signature) and ``polars`` (``to_polars()``).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINNED = ("httpx", "PyYAML", "pyarrow", "numpy", "cryptography", "polars")


def _version() -> str:
    text = (ROOT / "maya" / "core" / "version.py").read_text(encoding="utf-8")
    return re.search(r'^VERSION = "([^"]+)"', text, re.M).group(1)


def _pins() -> dict[str, str]:
    """The server's own pins, as lower bounds: the SDK is tested against exactly these."""
    pins = {}
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", line.strip())
        if m and m.group(1) in PINNED:
            pins[m.group(1)] = m.group(2)
    return pins


def pyproject() -> str:
    p = _pins()
    dep = lambda n: f'"{n}>={p[n]}"' if n in p else f'"{n}"'  # noqa: E731
    return f'''[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "maya-sdk"
version = "{_version()}"
description = "The Python SDK for MAYA: the client, record and replay, and offline bundles."
requires-python = ">=3.13"
authors = [{{ name = "Ashutosh Sinha", email = "ajsinha@gmail.com" }}]
license = {{ file = "LICENSE" }}
dependencies = [{dep("httpx")}, {dep("PyYAML")}, {dep("pyarrow")}, {dep("numpy")}]

[project.optional-dependencies]
offline = [{dep("cryptography")}]
polars = [{dep("polars")}]

[tool.setuptools.packages.find]
include = ["maya.sdk*"]
namespaces = true
'''


def stage(into: Path) -> Path:
    """The source tree of the distribution: maya/sdk (no maya/__init__.py), licence, metadata."""
    shutil.copytree(
        ROOT / "maya" / "sdk",
        into / "maya" / "sdk",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy(ROOT / "LICENSE", into / "LICENSE")
    (into / "pyproject.toml").write_text(pyproject(), encoding="utf-8")
    return into


def build(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = stage(Path(tmp) / "maya-sdk")
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
                str(src),
            ],
            check=True,
        )
    wheels = sorted(out.glob(f"maya_sdk-{_version()}-*.whl"))
    return wheels[-1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--out", default=str(ROOT / "dist"))
    print(build(Path(ap.parse_args().out)))


if __name__ == "__main__":
    main()
