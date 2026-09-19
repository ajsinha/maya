"""Gate 13 — the two schema files are generated from the ORM metadata (§14.3, SC-15).

    python tools/ci/gen_schema.py           # regenerate both files
    python tools/ci/gen_schema.py --check   # fail on any drift (CI)

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys

from _common import report


def main(argv: list[str]) -> int:
    from maya.persistence import schema

    if "--check" in argv:
        drifted = [
            f"schema/{d}.sql differs from the metadata; run tools/ci/gen_schema.py"
            for d, bad in schema.drift().items()
            if bad
        ]
        return report("schema files match the ORM metadata", drifted)
    for path in schema.write_files():
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
