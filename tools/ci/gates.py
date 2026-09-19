"""The gate ladder's single entry point (plan §7). Never a remembered list.

    python tools/ci/gates.py            # the fast static gates
    python tools/ci/gates.py --tests    # … then the full test suite

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
GATES = ["file_size.py", "import_boundaries.py", "seam_imports.py", "version_single_source.py",
         "no_secrets.py", "table_contract.py", "contrast.py", "sdk_parity.py"]


def main(argv: list[str]) -> int:
    failed = []
    for gate in GATES:
        rc = subprocess.call([sys.executable, str(HERE / gate)], cwd=HERE.parents[1])
        if rc:
            failed.append(gate)
    rc = subprocess.call([sys.executable, str(HERE / "gen_schema.py"), "--check"],
                         cwd=HERE.parents[1])
    if rc:
        failed.append("gen_schema.py --check")
    if "--tests" in argv and not failed:
        rc = subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=HERE.parents[1])
        if rc:
            failed.append("pytest")
    print("\n" + ("ALL GATES GREEN" if not failed else "RED: " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
