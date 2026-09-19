"""
The gates added to the ladder at 0.3.0, each shown to catch what it is for: an
import cycle, a changed API contract, a changed or removed SDK method, a lint
fault — and green on the code as it is.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / "tools" / "ci"
sys.path.insert(0, str(CI))

import api_snapshot  # noqa: E402
import cycle_check  # noqa: E402
import public_symbols  # noqa: E402


def test_a_load_time_cycle_is_found_and_deferred_imports_are_not(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("from pkg import b\n")
    (pkg / "b.py").write_text("import pkg.a\n")
    (pkg / "c.py").write_text("def f():\n    from pkg import a\n")  # deferred: fine
    (pkg / "d.py").write_text(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pkg import e\n"
    )
    (pkg / "e.py").write_text("from pkg import d\n")  # TYPE_CHECKING: fine
    known = {f"pkg.{p.stem}": p for p in pkg.glob("*.py") if p.stem != "__init__"}
    graph = {n: cycle_check.load_time_imports(p, n, known) for n, p in known.items()}
    assert cycle_check.cycles(graph) == [["pkg.a", "pkg.b"]]


def test_the_codebase_has_no_import_cycle():
    known = cycle_check.modules()
    graph = {n: cycle_check.load_time_imports(p, n, known) for n, p in known.items()}
    assert cycle_check.cycles(graph) == []


def test_the_api_snapshot_names_a_contract_change_and_ignores_prose():
    now = api_snapshot.contract()
    assert api_snapshot._diff(now, now) == []
    path, ops = next(iter(now["paths"].items()))
    method = next(iter(ops))
    changed = {
        **now,
        "paths": {**now["paths"], path: {**ops, method: {**ops[method], "parameters": []}}},
    }
    assert any(path in c for c in api_snapshot._diff(now, changed))
    assert api_snapshot._strip({"description": "prose", "type": "string"}) == {"type": "string"}


def test_the_sdk_snapshot_names_a_removed_or_changed_method():
    now = public_symbols.surface()
    features = now["Client"]["namespaces"]["features"]["methods"]
    assert "list" in features and "(self" in features["list"]
    removed = {
        **now,
        "Client": {
            **now["Client"],
            "namespaces": {
                **now["Client"]["namespaces"],
                "features": {
                    "class": "Features",
                    "methods": {k: v for k, v in features.items() if k != "list"},
                },
            },
        },
    }
    assert any("removed" in c and "list" in c for c in public_symbols._diff(now, removed))


@pytest.mark.parametrize(
    "gate", ["api_snapshot.py", "public_symbols.py", "cycle_check.py", "typecheck.py"]
)
def test_each_new_gate_is_green_on_the_code_as_it_is(gate):
    r = subprocess.run(
        [sys.executable, str(CI / gate)], cwd=ROOT, capture_output=True, text=True, timeout=600
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_lint_fails_on_a_planted_fault(tmp_path):
    bad = tmp_path / "planted.py"
    bad.write_text("import os\n")  # F401, unused
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(bad)], capture_output=True, text=True
    )
    assert r.returncode != 0 and "F401" in r.stdout


def test_the_lint_gate_fails_on_an_unformatted_file():
    root = Path(__file__).resolve().parents[1]
    planted = root / "tools" / "_planted_unformatted.py"
    planted.write_text("x = (1,\n  2)\n")
    try:
        r = subprocess.run(
            [sys.executable, str(root / "tools" / "ci" / "lint.py")],
            cwd=root,
            capture_output=True,
            text=True,
        )
    finally:
        planted.unlink()
    assert r.returncode != 0 and "_planted_unformatted.py is not formatted" in r.stdout
