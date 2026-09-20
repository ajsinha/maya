"""
Case study 5 — a European option pricer whose volatility nobody can observe.

    .venv/bin/python case_studies/05-option-pricing/run.py

This runs every step in order against a MAYA built from nothing, in about fifteen seconds.
It is the unattended pass.

**For a demonstration, run the steps one at a time.** They share one MAYA at
``case_studies/runs/equity_derivatives``, and between any two you can open the web UI
(``show_estate.py`` prints how):

    setup_features.py         the chain, the spot, the dividends and the curve
    setup_featureset.py       one chain on one index, broadcast across three grains, pinned
    setup_model.py            Black–Scholes–Merton from LaTeX, and a bound on the volatility
    check_conformance.py      the ladder, then the pricer against the mathematics
    get_training_warrant.py   calibration, the smile, and blind repricing
    get_execution_warrant.py  live, and a request off the edge of the surface
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

TITLE = "Case study 5 — European option pricing (finance, calibrated)"

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
