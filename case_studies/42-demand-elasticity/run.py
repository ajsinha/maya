"""
Case study 42 — demand elasticity: champion against challenger.

    .venv/bin/python case_studies/42-demand-elasticity/run.py

Runs every step in order against the project's MAYA, in about five seconds. For a
demonstration, run the steps one at a time and open the web UI between them:

    setup.py       the sales feed pinned, the champion and challenger approved
    fit_both.py    each fitted under its own warrant, on the same escrowed holdout
    challenge.py   a paired comparison, and a decision somebody independent takes

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

import challenge  # noqa: E402
import fit_both  # noqa: E402
import setup  # noqa: E402
from maya_demo import Narrator, after_failure, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 42 — demand elasticity (economics, champion and challenger)"
STEPS = (setup, fit_both, challenge)


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
