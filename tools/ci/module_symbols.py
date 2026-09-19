"""Gate 7a — public names per module (plan §7): at most 60.

A module that exports more than 60 public functions, classes and constants is doing
several jobs; split it. (API router modules come closest: one function per route.)

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import ast
import sys

from _common import ROOT, report

LIMIT = 60


def public_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {n for n in names if not n.startswith("_")}


def main() -> int:
    problems = []
    for pkg in ("maya", "maya_delta"):
        for path in sorted((ROOT / pkg).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            count = len(public_names(ast.parse(path.read_text(encoding="utf-8"))))
            if count > LIMIT:
                problems.append(f"{path.relative_to(ROOT)}: {count} public names (> {LIMIT})")
    return report(f"public names per module (<= {LIMIT})", problems)


if __name__ == "__main__":
    sys.exit(main())
