"""
Case study 45 — a unisex Gompertz–Makeham mortality table.

    .venv/bin/python case_studies/45-gompertz-makeham-mortality/run.py

Runs every step in order against the project's MAYA, in about ten seconds. For a
demonstration, run the steps one at a time and open the web UI between them:

    setup.py        ten years of experience pinned, the law approved
    calibrate.py    a non-linear calibration, tied to its data, scored blind
    fairness.py     bias by sex and region measured; a finding; the risk accepted in writing

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys


def _bootstrap() -> None:
    """Make this folder and ``case_studies/`` importable, whatever launched the script."""
    from pathlib import Path

    here = Path(__file__).resolve().parent
    for path in (str(here.parent), str(here)):
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap()

import calibrate  # noqa: E402
import fairness  # noqa: E402
import setup  # noqa: E402
from maya_demo import Narrator, after_failure, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 45 — Gompertz–Makeham mortality (life sciences, non-linear)"
STEPS = (setup, calibrate, fairness)


def main() -> int:
    args = arguments(__doc__ or "")
    n = Narrator(TITLE, args.quiet)
    maya = open_study(NS, reset=args.reset, args=args, fresh=True, extra_users=EXTRA_USERS)
    try:
        for step in STEPS:
            print(f"\n{'─' * 78}\n{step.TITLE}\n{'─' * 78}")
            step.main(maya, Narrator("", args.quiet))
        n.done(f"{len(STEPS)} steps done")
        return 0
    except BaseException:
        after_failure(maya, NS, args)
        raise
    finally:
        maya.close()


if __name__ == "__main__":
    sys.exit(main())
