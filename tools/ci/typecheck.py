"""
MAYA — type checking, gated on what is clean.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

`mypy || true` in a workflow is a step that always passes, which is the defect
this codebase is named for: a control reporting success while doing nothing.
Adopting `--strict` across two hundred and fifty modules in one release
produces a blanket ignore, which is the same thing wearing a different hat.

So this gates on the modules that check cleanly **today** — 186 of 248 — and
carries the rest in `mypy_backlog.txt`. A clean module that regresses fails the
build; a backlogged module that gets fixed is a line somebody deletes.

    python tools/ci/typecheck.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Set

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = Path(__file__).with_name("mypy_backlog.txt")
ROOTS = ("core", "db", "routes", "sdk/python/maya_sdk")


def backlogged() -> Set[str]:
    lines = BACKLOG.read_text().splitlines()
    return {line.strip() for line in lines
            if line.strip() and not line.lstrip().startswith("#")}


def modules() -> List[str]:
    found: List[str] = []
    for root in ROOTS:
        found += [str(p.relative_to(ROOT)) for p in (ROOT / root).rglob("*.py")
                  if "__pycache__" not in p.parts]
    found.append("run_maya_web.py")
    return sorted(found)


def main() -> int:
    excused = backlogged()
    gated = [m for m in modules() if m not in excused]
    if not gated:
        print("nothing to check, which means the backlog covers everything")
        return 1

    print(f"type-checking {len(gated)} modules; {len(excused)} are in the backlog")
    result = subprocess.run(
        # `--follow-imports=silent`: check the named modules, and read the
        # others only for their types. Without it mypy reports errors found in
        # whatever the gated set imports, which is the backlog — so the gate
        # would fail on exactly the files it was told to excuse.
        [sys.executable, "-m", "mypy", "--config-file", str(ROOT / "pyproject.toml"),
         "--follow-imports=silent", *gated],
        cwd=ROOT, capture_output=True, text=True)
    print(result.stdout.strip() or result.stderr.strip())

    if result.returncode == 0:
        return 0
    print("\nA module that type-checks today has stopped. Fix it, or — if the "
          "change is deliberate and large — say so in the review rather than "
          "adding the file to mypy_backlog.txt, which exists to shrink.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
