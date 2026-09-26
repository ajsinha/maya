"""
Shared helpers for the gate scripts. Python, not shell, so every gate runs on
Windows, Linux and macOS alike (spec §22.4).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import ast
import io
import os
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE_ROOTS = ("maya", "maya_delta", "tools", "run_maya_web.py")


def visible(path: Path) -> bool:
    """False for a file a gate test planted, unless this run is the one that planted it.

    The gate tests prove each gate fails by writing a violating ``_planted*`` file into the
    tree and running the gate on it. Another test worker running the same gates at that
    moment would otherwise see the plant too -- or see it listed and then deleted -- and
    fail for a reason that is not in the code. The planting test sets ``MAYA_CI_PLANTED``."""
    return not path.name.startswith("_planted") or os.environ.get("MAYA_CI_PLANTED") == "1"


def python_files() -> list[Path]:
    out: list[Path] = []
    for name in SOURCE_ROOTS:
        path = ROOT / name
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            out += [p for p in path.rglob("*.py") if "__pycache__" not in p.parts and visible(p)]
    return sorted(out)


def code_lines(path: Path) -> int:
    """Lines that are neither blank, comments, nor docstrings (the 1,500-line measure)."""
    text = path.read_text(encoding="utf-8")
    doc_lines: set[int] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return len(text.splitlines())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc_lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    code: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (
            tokenize.COMMENT,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENDMARKER,
        ):
            continue
        for line in range(tok.start[0], tok.end[0] + 1):
            if line not in doc_lines:
                code.add(line)
    return len(code)


def imports_of(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(a.name, node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.module, node.lineno))
            # "from pkg import mod" names pkg.mod too, so a boundary can see which module
            out += [(f"{node.module}.{a.name}", node.lineno) for a in node.names]
    return out


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def report(name: str, failures: list[str]) -> int:
    if failures:
        print(f"FAIL {name}: {len(failures)} problem(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"ok   {name}")
    return 0


def api_app():  # type: ignore[no-untyped-def]
    """Every API router on a bare FastAPI app — its OpenAPI document, with no platform.

    The routers and the prefix come from ``maya.api.app`` itself, never from a list kept
    here. A gate that remembered the list would go on passing after somebody mounted a
    twelfth router, and the endpoint would reach production with no SDK method and no UI.
    """
    from fastapi import FastAPI
    from maya.api.app import PREFIX, ROUTERS

    app = FastAPI()
    for r in ROUTERS:
        app.include_router(r, prefix=PREFIX)
    return app
