"""The artifact validation ladder, one refusal per rung, and the declared sandbox tier."""

from __future__ import annotations

import pytest

from maya.formula.artifact import validate_artifact
from maya.security.sandbox import run_sandboxed, sandbox_tier, tier_at_least

GOOD = """
import numpy as np


class Model:
    def fit(self, X, y, ctx):
        return {"a": 1.0}

    def predict(self, X, params, ctx):
        return np.asarray(X["x"], dtype=float) * params["a"]
"""
SAMPLE = {"x": [1.0, 2.0, 3.0]}


def _failed_at(report: dict) -> int:
    return next(r["rung"] for r in report["rungs"] if r["passed"] is False)


def test_tier_is_declared_honestly() -> None:
    tier = sandbox_tier()
    assert tier["tier"] in ("minimal", "moderate", "strong") and tier["reason"]
    if tier["tier"] == "strong":  # claimed only when a probe child verified every part
        assert "verified by a probe" in tier["reason"]
        for part in ("bubblewrap", "seccomp", "cgroup"):
            assert part in tier["mechanism"]
    assert tier_at_least("strong", "minimal") and not tier_at_least("minimal", "strong")


def test_good_artifact_passes_all_six_rungs() -> None:
    report = validate_artifact(GOOD, SAMPLE, {"a": 2.0})
    assert report["passed"], report
    assert [r["passed"] for r in report["rungs"]] == [True] * 6
    assert report["smoke_output"] == [2.0, 4.0, 6.0]
    assert report["tier"] == sandbox_tier()["tier"] and len(report["artifact_hash"]) == 64


def test_rung1_syntax() -> None:
    report = validate_artifact("class Model(:\n", SAMPLE, {})
    assert _failed_at(report) == 1
    assert report["rungs"][5]["passed"] is None and "not run" in report["rungs"][5]["detail"]


def test_rung2_signature() -> None:
    src = GOOD.replace("def predict(self, X, params, ctx)", "def predict(self, X, params)")
    report = validate_artifact(src, SAMPLE, {})
    assert _failed_at(report) == 2 and "signature" in report["rungs"][1]["detail"]


def test_rung3_os_import() -> None:
    report = validate_artifact("import os\n" + GOOD, SAMPLE, {})
    assert _failed_at(report) == 3 and "'os'" in report["rungs"][2]["detail"]


@pytest.mark.parametrize(
    "line", ["open('/etc/passwd').read()", "eval('1+1')", "exec('x=1')", "().__class__.__bases__"]
)
def test_rung4_static_ban(line: str) -> None:
    src = GOOD.replace('return {"a": 1.0}', f"{line}\n        return {{}}")
    report = validate_artifact(src, SAMPLE, {})
    assert _failed_at(report) == 4


def test_rung5_infinite_loop_killed_by_wall_clock() -> None:
    src = GOOD.replace(
        'return np.asarray(X["x"], dtype=float) * params["a"]', "while True:\n            pass"
    )
    report = validate_artifact(
        src, SAMPLE, {"a": 1.0}, limits={"cpu_seconds": 2, "memory_mb": 1024, "wall_seconds": 4}
    )
    assert _failed_at(report) == 5
    detail = report["rungs"][4]["detail"]
    assert "wall-clock" in detail or "resource limit" in detail


def test_rung5_huge_allocation_contained() -> None:
    src = GOOD.replace(
        'return np.asarray(X["x"], dtype=float) * params["a"]', "return np.ones(10_000_000_000)"
    )
    report = validate_artifact(src, SAMPLE, {"a": 1.0})
    assert _failed_at(report) == 5
    assert "Memory" in report["rungs"][4]["detail"] or "resource" in report["rungs"][4]["detail"]


def test_rung6_nondeterminism_is_a_warning() -> None:
    src = GOOD.replace(
        'return np.asarray(X["x"], dtype=float) * params["a"]',
        "return np.random.default_rng().random(3)",
    )
    report = validate_artifact(src, SAMPLE, {})
    assert report["passed"] and report["deterministic"] is False
    assert "WARNING" in report["rungs"][5]["detail"]


def test_network_disabled_in_child() -> None:
    src = "import socket\n\ndef run(X, params):\n    socket.socket()\n    return 1\n"
    res = run_sandboxed(src, "run", {"X": {}, "params": {}})
    assert not res["ok"] and "network access is disabled" in res["error"]


def test_file_write_blocked_by_rlimit() -> None:
    import platform

    if platform.system() == "Windows":
        pytest.skip("RLIMIT_FSIZE is POSIX only; Windows tier is minimal by wall clock")
    src = (
        "def run(X, params):\n    with open('x.txt', 'w') as fh:\n"
        "        fh.write('hello' * 1000)\n    return 1\n"
    )
    res = run_sandboxed(src, "run", {"X": {}, "params": {}})
    assert not res["ok"]


def test_an_interpreter_reached_through_unbound_links_still_starts(tmp_path, monkeypatch):
    """A venv made with ``~/.local/bin/python3.13 -m venv`` links through the home
    directory, which the sandbox hides. Each unbound hop must be recreated, or the child
    cannot start, the tier probe fails and MAYA falls back to the minimal tier unasked."""
    import os
    import sys

    from maya.security import sandbox

    real = os.path.realpath(sys.executable)
    hidden = tmp_path / "home" / ".local" / "bin"
    hidden.mkdir(parents=True)
    (hidden / "python3.13").symlink_to(real)
    venv = tmp_path / "venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(hidden / "python3.13")
    monkeypatch.setattr(sys, "executable", str(venv / "python"))
    args = sandbox._binds()
    pairs = list(zip(args, args[1:], args[2:]))
    assert ("--symlink", real, str(hidden / "python3.13")) in pairs


def test_the_child_finds_a_library_from_a_site_packages_the_isolated_mode_leaves_out(
    tmp_path, monkeypatch
):
    """``python -I`` drops the user site-packages, where ``pip install --user`` -- and pip on a
    Windows Python it cannot write to -- puts numpy. The child is told where the parent's
    libraries are, so a library the parent can import, the child can import too."""
    import sys

    from maya.security.sandbox import run_sandboxed

    site = tmp_path / "site-packages"
    site.mkdir()
    (site / "maya_user_site_probe.py").write_text("VALUE = 42\n", encoding="utf-8")
    monkeypatch.setattr(sys, "path", [*sys.path, str(site)])
    source = (
        "import maya_user_site_probe\n\ndef f(X, params):\n    return maya_user_site_probe.VALUE\n"
    )
    out = run_sandboxed(source, "f", {"X": {}})
    assert out["ok"], out
    assert out["result"] == 42


def test_the_bundle_verifier_finds_the_parents_libraries_and_a_failure_is_a_named_check(
    tmp_path, monkeypatch
):
    """The verifier runs isolated, as on a machine without MAYA, yet still needs pyarrow and
    numpy wherever they were installed (a user site on Windows); and a verifier that cannot
    run is reported as a failed check, never as a report with no checks in it."""
    import sys

    from maya.services.bundle import run_verifier

    site = tmp_path / "site-packages"
    site.mkdir()
    (site / "maya_verifier_probe.py").write_text("OK = True\n", encoding="utf-8")
    monkeypatch.setattr(sys, "path", [*sys.path, str(site)])
    found = run_verifier(
        b"zip",
        "import json, maya_verifier_probe\n"
        "print(json.dumps({'verified': maya_verifier_probe.OK, 'checks': []}))\n",
    )
    assert found["verified"] is True, found
    broken = run_verifier(b"zip", "raise SystemExit('pyarrow is missing')\n")
    assert broken["verified"] is False
    assert broken["checks"][0]["check"] == "the verifier ran" and broken["checks"][0]["ok"] is False
    assert "pyarrow is missing" in broken["checks"][0]["detail"]
