"""
Case study 19 — a bought bureau score, imported from MLflow and held to account.

    .venv/bin/python case_studies/19-vendor-bureau-score/run.py

Runs every step in order against the project's MAYA, in about fifteen seconds. For a
demonstration, run the steps one at a time and open the web UI between them:

    setup_data.py      two feeds with two clocks, and the year-end panel pinned
    import_model.py    the vendor's MLflow model imported, its code validated in the sandbox
    validate.py        blind scoring in the sandbox, fairness by region, what drives it
    monitor.py         live under a drift covenant: stable, watch, breach

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

import import_model  # noqa: E402
import monitor  # noqa: E402
import setup_data  # noqa: E402
import validate  # noqa: E402
from maya_demo import Narrator, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 19 — vendor bureau score (banking, bought black box)"
STEPS = (setup_data, import_model, validate, monitor)


def main() -> int:
    args = arguments(__doc__ or "")
    n = Narrator(TITLE, args.quiet)
    maya = open_study(NS, reset=args.reset, fresh=True, extra_users=EXTRA_USERS)
    try:
        for step in STEPS:
            print(f"\n{'─' * 78}\n{step.TITLE}\n{'─' * 78}")
            step.main(maya, Narrator("", args.quiet))
        n.done(f"{len(STEPS)} steps done")
        return 0
    finally:
        maya.close()


if __name__ == "__main__":
    sys.exit(main())
