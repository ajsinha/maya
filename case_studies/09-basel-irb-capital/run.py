"""
Case study 9 — Basel IRB regulatory capital, governed end to end.

    .venv/bin/python case_studies/09-basel-irb-capital/run.py

Runs every step in order against the project's MAYA, in about fifteen seconds. For a
demonstration, run the steps one at a time and open the web UI between them:

    setup_data.py      the exposures feed, governed, and the year-end panel pinned
    setup_model.py     the IRB formula as mathematics, N^{-1} and all, version 1
    reconcile_v1.py    blind reconciliation against the regulator's reference; a finding
    remediate.py       version 2, reconciled to the last digit; the finding closed by another
    govern.py          tier 1, the first periodic review, live use, the SR 11-7 inventory

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

import govern  # noqa: E402
import reconcile_v1  # noqa: E402
import remediate  # noqa: E402
import setup_data  # noqa: E402
import setup_model  # noqa: E402
from maya_demo import Narrator, after_failure, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 9 — Basel IRB regulatory capital (banking, closed form, no fit)"
STEPS = (setup_data, setup_model, reconcile_v1, remediate, govern)


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
