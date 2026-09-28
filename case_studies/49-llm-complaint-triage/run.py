"""
Case study 49 — an LLM complaint-triage application, governed like a model.

    .venv/bin/python case_studies/49-llm-complaint-triage/run.py

Runs every step in order against the project's MAYA, in a few seconds. For a
demonstration, run the steps one at a time and open the web UI between them:

    register.py            the application, version 1, and its evaluation set
    evaluate_v1.py         version 1 scored from recorded answers, and refused
    fix_and_approve.py     version 2, a changed evaluation set, an independent approval
    inventory.py           the application in the SS1/23 inventory

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

import evaluate_v1  # noqa: E402
import fix_and_approve  # noqa: E402
import inventory  # noqa: E402
import register  # noqa: E402
from maya_demo import Narrator, after_failure, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 49 — LLM complaint triage (operations, LLM application)"
STEPS = (register, evaluate_v1, fix_and_approve, inventory)


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
