"""
Case study 6 — the IFRS 9 expected credit loss allowance, as a composite of three models.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/run.py

Every step in order against a MAYA built from nothing. The unattended pass.

**For a demonstration, run the steps one at a time.** They share one MAYA at
``case_studies/runs/impairment``, and between any two you can open the web UI
(``show_estate.py`` prints how):

    setup_features.py         the book and the outcomes become features
    setup_featureset.py       one panel for three members and one combiner
    setup_members.py          PD, LGD and EAD as three models, three shapes
    setup_composite.py        the product, and the two parameters that belong to no member
    get_training_warrant.py   one warrant over the whole allowance
    fit_parameters.py         three fits, two judgements, and a seal that waits for all five
    check_portfolio.py        the test an expected-loss model can actually fail
    get_execution_warrant.py  live, with the stage population as the control
    show_estate.py            every number behind the allowance, and what was said about it

The README beside this file carries the theory, the mathematics and the numbers.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_portfolio  # noqa: E402
import fit_parameters  # noqa: E402
import get_execution_warrant  # noqa: E402
import get_training_warrant  # noqa: E402
import setup_composite  # noqa: E402
import setup_featureset  # noqa: E402
import setup_features  # noqa: E402
import setup_members  # noqa: E402
import show_estate  # noqa: E402
from maya_demo import Narrator, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 6 — IFRS 9 expected credit loss (banking, composite)"

STEPS = (
    setup_features,
    setup_featureset,
    setup_members,
    setup_composite,
    get_training_warrant,
    fit_parameters,
    check_portfolio,
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
        n.done("nine steps done")
        return 0
    finally:
        maya.close()


if __name__ == "__main__":
    sys.exit(main())
