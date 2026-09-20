"""
Case study 2 — a scheduled mortgage cashflow model that needs no training at all.

    .venv/bin/python case_studies/02-mortgage-cashflow/run.py

This runs every step in order against a MAYA built from nothing, in about fifteen seconds.
It is the unattended pass.

**For a demonstration, run the steps one at a time.** They share one MAYA at
``case_studies/runs/mortgage_alm``, and between any two you can open the web UI
(``show_estate.py`` prints how):

    setup_features.py         the loan tape and the servicer's report become features
    setup_featureset.py       one panel, the benchmark beside the inputs, pinned
    setup_model.py            the model from its LaTeX, and MAYA's own reference code
    check_conformance.py      the six-rung ladder, then the code against the mathematics
    get_training_warrant.py   a warrant that fits nothing, and blind reconciliation
    get_execution_warrant.py  live, and a tape that did not arrive
    show_estate.py            the catalog, the artifact report, the audit chain, lineage

The README beside this file carries the theory, the mathematics and the numbers.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_conformance  # noqa: E402
import get_execution_warrant  # noqa: E402
import get_training_warrant  # noqa: E402
import setup_featureset  # noqa: E402
import setup_features  # noqa: E402
import setup_model  # noqa: E402
import show_estate  # noqa: E402
from maya_demo import Narrator, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 2 — scheduled mortgage cashflow (banking, no fit)"

STEPS = (
    setup_features,
    setup_featureset,
    setup_model,
    check_conformance,
    get_training_warrant,
    get_execution_warrant,
    show_estate,
)


def main() -> int:
    args = arguments(__doc__ or "")
    n = Narrator(TITLE, args.quiet)
    maya = open_study(NS, reset=True, extra_users=EXTRA_USERS)
    try:
        for step in STEPS:
            print(f"\n{'─' * 78}\n{step.TITLE}\n{'─' * 78}")
            step.main(maya, Narrator("", args.quiet))
        n.done("seven steps done")
        return 0
    finally:
        maya.close()


if __name__ == "__main__":
    sys.exit(main())
