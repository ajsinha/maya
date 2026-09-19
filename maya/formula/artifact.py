"""
The six-rung validation ladder for a model code artifact (§8.3, §17.2).

1. parse (and ``ruff check`` where ruff is installed — whether it ran is recorded)
2. entry point and signature against the MayaModel interface
3. import allowlist
4. static ban on filesystem, process, network and dynamic-code use
5. smoke run in the sandbox against a sample
6. determinism probe: the smoke run twice, outputs compared (warning on mismatch)

The ladder stops at the first failing rung; later rungs are recorded as not
run, so a report never implies a check it did not perform.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from maya.security.sandbox import run_sandboxed, sandbox_tier

DEFAULT_ALLOWLIST = frozenset({
    "math", "statistics", "random", "itertools", "functools", "collections", "dataclasses",
    "typing", "json", "decimal", "fractions", "__future__",
    "numpy", "pandas", "polars", "pyarrow", "scipy", "sklearn", "statsmodels",
})
BANNED_NAMES = frozenset({"open", "eval", "exec", "compile", "__import__", "input",
                          "breakpoint", "globals", "locals", "vars", "memoryview"})
BANNED_MODULES = frozenset({"os", "sys", "subprocess", "socket", "shutil", "pathlib",
                            "importlib", "ctypes", "pickle", "marshal", "builtins", "io",
                            "multiprocessing", "threading", "signal", "urllib", "http"})
RUNGS = ("parse", "entry point", "import allowlist", "static ban", "smoke run", "determinism")
_SIG = {"fit": ["self", "X", "y", "ctx"], "predict": ["self", "X", "params", "ctx"]}


def _rung(n: int, passed: bool | None, detail: str) -> dict[str, Any]:
    return {"rung": n, "name": RUNGS[n - 1], "passed": passed, "detail": detail}


def _ruff(source: str) -> str:
    local = Path(sys.executable).with_name("ruff")
    exe = shutil.which("ruff") or (str(local) if local.exists() else None)
    if not exe:
        return "ruff not installed: lint not run"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "artifact.py"
        path.write_text(source, encoding="utf-8")
        proc = subprocess.run([exe, "check", "--select", "E9,F", "--quiet", str(path)],  # noqa: S603
                              capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode == 0:
        return "ruff check ran: clean"
    return "ruff check ran: " + proc.stdout.strip().replace(str(path), "artifact.py")[:500]


def rung_parse(source: str) -> tuple[bool, str, ast.Module | None]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return False, f"syntax error on line {exc.lineno}: {exc.msg}", None
    lint = _ruff(source)
    ok = not ("ran:" in lint and ("F821" in lint or "E9" in lint))
    return ok, lint, tree


def rung_entry(tree: ast.Module, entry: str) -> tuple[bool, str]:
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    if entry not in classes:
        return False, f"entry point class '{entry}' not found"
    methods = {n.name: n for n in classes[entry].body if isinstance(n, ast.FunctionDef)}
    for name, want in _SIG.items():
        if name not in methods:
            return False, f"'{entry}.{name}' is missing"
        got = [a.arg for a in methods[name].args.args]
        if got != want:
            return False, f"'{entry}.{name}' signature is ({', '.join(got)}), expected ({', '.join(want)})"
    return True, f"'{entry}' implements fit(X, y, ctx) and predict(X, params, ctx)"


def _imports(tree: ast.Module) -> list[tuple[str, int]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name.split(".")[0], node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append(((node.module or "").split(".")[0], node.lineno))
    return found


def rung_allowlist(tree: ast.Module, allowlist: frozenset[str]) -> tuple[bool, str]:
    bad = [(m, line) for m, line in _imports(tree) if m not in allowlist]
    if bad:
        return False, "; ".join(f"import of '{m}' on line {line} is not on the allowlist" for m, line in bad)
    return True, "every import is on the allowlist"


def rung_static_ban(tree: ast.Module) -> tuple[bool, str]:
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            problems.append(f"use of '{node.id}' on line {node.lineno}")
        elif isinstance(node, ast.Name) and node.id in BANNED_MODULES:
            problems.append(f"reference to '{node.id}' on line {node.lineno}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__") \
                and node.attr not in ("__init__", "__name__"):
            problems.append(f"dunder access '{node.attr}' on line {node.lineno}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            problems.append(f"dynamic getattr on line {node.lineno}")
    for mod, line in _imports(tree):
        if mod in BANNED_MODULES:
            problems.append(f"import of banned module '{mod}' on line {line}")
    if problems:
        return False, "; ".join(sorted(set(problems)))
    return True, "no filesystem, process, network or dynamic-code use"


def _smoke(source: str, entry: str, sample: dict[str, list[Any]], params: dict[str, Any],
           limits: dict[str, int]) -> dict[str, Any]:
    return run_sandboxed(source, entry, {"mode": "predict", "X": sample, "params": params, "seed": 0},
                         **limits)


def validate_artifact(source: str, sample: dict[str, list[Any]], params: dict[str, Any], *,
                      allowlist: frozenset[str] | set[str] | None = None, entry: str = "Model",
                      limits: dict[str, int] | None = None) -> dict[str, Any]:
    """Run the ladder; ``passed`` is true only if rungs 1–5 pass."""
    allow = frozenset(allowlist) if allowlist is not None else DEFAULT_ALLOWLIST
    limits = limits or {"cpu_seconds": 10, "memory_mb": 1024, "wall_seconds": 20}
    tier = sandbox_tier()
    rungs: list[dict[str, Any]] = []
    report: dict[str, Any] = {"passed": False, "rungs": rungs, "tier": tier["tier"],
                              "tier_reason": tier["reason"],
                              "artifact_hash": hashlib.sha256(source.encode("utf-8")).hexdigest()}

    def finish() -> dict[str, Any]:
        for n in range(len(rungs) + 1, len(RUNGS) + 1):
            rungs.append(_rung(n, None, "not run: an earlier rung failed"))
        return report

    ok, detail, tree = rung_parse(source)
    rungs.append(_rung(1, ok, detail))
    if not ok or tree is None:
        return finish()
    for n, check in ((2, lambda: rung_entry(tree, entry)), (3, lambda: rung_allowlist(tree, allow)),
                     (4, lambda: rung_static_ban(tree))):
        ok, detail = check()
        rungs.append(_rung(n, ok, detail))
        if not ok:
            return finish()
    first = _smoke(source, entry, sample, params, limits)
    if not first["ok"]:
        rungs.append(_rung(5, False, first["error"] or "smoke run failed"))
        return finish()
    rungs.append(_rung(5, True, f"smoke run succeeded in {first['duration']:.2f}s under tier "
                                f"'{first['tier']}'"))
    second = _smoke(source, entry, sample, params, limits)
    same = second["ok"] and json.dumps(first["result"], sort_keys=True) == \
        json.dumps(second["result"], sort_keys=True)
    rungs.append(_rung(6, True if same else None,
                       "two runs produced identical output" if same else
                       "WARNING: two runs with seed 0 produced different output — "
                       "non-determinism undermines reproducibility"))
    report["deterministic"] = bool(same)
    report["passed"] = True
    report["smoke_output"] = first["result"]
    return report
