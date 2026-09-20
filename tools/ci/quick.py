"""
The whole suite, faster: the bulk in parallel, the tests that cannot share serially.

    python tools/ci/quick.py            # everything, ~2 minutes instead of ~4.5
    python tools/ci/quick.py -k pins    # the same split, narrowed

Three groups of tests cannot run beside others, and each for a stated reason:

* **Tree scanners and tree planters.** Several gate tests plant a deliberate violation in
  the working tree (an unformatted file, an import that crosses a boundary) and assert the
  gate catches it; others scan the tree and assert it is clean. Run together in different
  workers, one sees the other's planted file and fails for a reason that has nothing to do
  with the code.
* **Real browsers.** Each needs its own headless Chrome; several at once contend for the
  profile directory and the debugging port.
* **Whole-process tests.** The multi-process server and the worker process bind ports and
  drive one ``MAYA_HOME`` between processes.

Everything else is independent — each test builds its own platform on its own storage — so
it parallelises by file. ``--dist loadfile`` keeps a module's tests together, which matters
because the module-scoped fixtures are where the setup cost is.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKERS = "4"  # measured: 4 is as fast as 8 here and does not thrash the fixtures

# planted-violation and tree-scanning tests: one worker, or they see each other's plants
SERIAL = (
    "tests/test_api_and_gates.py",
    "tests/test_gate_ladder.py",
    "tests/test_web.py",
    "tests/test_web_processes.py",
    "tests/test_worker_process.py",
)
# real browsers: measured safe at two workers (each gets its own Chrome), 56s instead of 98s
BROWSER = (
    "tests/test_browser.py",
    "tests/test_browser_canvas.py",
    "tests/test_browser_editors.py",
    "tests/test_browser_preview_and_facets.py",
)
BROWSER_WORKERS = "2"


def run(args: list[str]) -> int:
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args], cwd=ROOT
    )


def main() -> int:
    extra = sys.argv[1:]
    started = time.perf_counter()
    skip = [f"--ignore={t}" for t in (*SERIAL, *BROWSER)]
    bulk = run(["-n", WORKERS, "--dist", "loadfile", *skip, *extra])
    browsers = run(
        [
            "-n",
            BROWSER_WORKERS,
            "--dist",
            "loadfile",
            *[t for t in BROWSER if (ROOT / t).exists()],
            *extra,
        ]
    )
    serial = run([*[t for t in SERIAL if (ROOT / t).exists()], *extra])
    elapsed = time.perf_counter() - started
    print(
        f"\nquick: {elapsed:.0f}s total — bulk on {WORKERS} workers, browsers on "
        f"{BROWSER_WORKERS}, {len(SERIAL)} file(s) serial"
    )
    return bulk or browsers or serial


if __name__ == "__main__":
    sys.exit(main())
