"""Gate 3b — no import cycles between modules (plan §7).

Only imports that run when a module loads count: top-level statements, including
those in ``try``; imports inside functions (deliberately deferred) and under
``TYPE_CHECKING`` do not. A cycle between modules is reported with its members.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from _common import ROOT, report

PACKAGES = ("maya", "maya_delta")


def modules() -> dict[str, Path]:
    out = {}
    for pkg in PACKAGES:
        for p in (ROOT / pkg).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            name = ".".join(p.relative_to(ROOT).with_suffix("").parts)
            out[name.removesuffix(".__init__")] = p
    return out


def load_time_imports(path: Path, name: str, known: dict[str, Path]) -> set[str]:
    is_pkg = path.name == "__init__.py"
    found: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            continue
        for n in (node.body if isinstance(node, ast.Try) else [node]):
            if isinstance(n, ast.Import):
                found.update(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    parts = name.split(".")
                    base = parts[:len(parts) - n.level + (1 if is_pkg else 0)]
                    mod = ".".join(base + ([n.module] if n.module else []))
                else:
                    mod = n.module or ""
                found.add(mod)
                found.update(f"{mod}.{a.name}" for a in n.names)
    return {m for m in found if m in known and m != name}


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one module (Tarjan, iterative)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    out: list[list[str]] = []
    counter = 0
    for start in graph:
        if start in index:
            continue
        work = [(start, iter(sorted(graph[start])))]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on.add(start)
        while work:
            v, it = work[-1]
            w = next(it, None)
            if w is not None:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(graph[w]))))
                elif w in on:
                    low[v] = min(low[v], index[w])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    x = stack.pop()
                    on.discard(x)
                    comp.append(x)
                    if x == v:
                        break
                if len(comp) > 1:
                    out.append(sorted(comp))
    return out


def main() -> int:
    known = modules()
    graph = {n: load_time_imports(p, n, known) for n, p in known.items()}
    return report("import cycles", [" <-> ".join(c) for c in cycles(graph)])


if __name__ == "__main__":
    sys.exit(main())
