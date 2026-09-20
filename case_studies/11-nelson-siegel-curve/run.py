"""
Case study 11 — the Nelson–Siegel yield curve, and whether a curve is a feature or a model.

    .venv/bin/python case_studies/11-nelson-siegel-curve/run.py

This runs every step in order against a MAYA built from nothing, in about ten seconds. It is
the unattended pass.

**For a demonstration, run the steps one at a time.** They share one MAYA at
``case_studies/runs/rates``, and between any two you can open the web UI (``show_estate.py``
prints how):

    setup_features.py         the quotes, the published curve, and the build report
    setup_featureset.py       one curve on one index, broadcast, pinned point-in-time
    setup_model.py            Nelson–Siegel from LaTeX, and the bound that cannot be written
    check_conformance.py      the ladder, then the code against the mathematics
    get_training_warrant.py   a grid search with least squares inside it, and blind scoring
    get_execution_warrant.py  live, and a request off the end of the curve
    curve_as_feature.py       the same curve as a feature, and what that costs
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
import curve_as_feature  # noqa: E402
import get_execution_warrant  # noqa: E402
import get_training_warrant  # noqa: E402
import setup_featureset  # noqa: E402
import setup_features  # noqa: E402
import setup_model  # noqa: E402
import show_estate  # noqa: E402
from maya_demo import Narrator, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 11 — the Nelson–Siegel yield curve (rates, non-linearly calibrated)"

STEPS = (
    setup_features,
    setup_featureset,
    setup_model,
    check_conformance,
    get_training_warrant,
    get_execution_warrant,
    curve_as_feature,
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
        n.done("eight steps done")
        return 0
    finally:
        maya.close()


if __name__ == "__main__":
    sys.exit(main())
