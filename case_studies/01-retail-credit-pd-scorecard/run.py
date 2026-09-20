"""
Case study 1 — a retail credit PD scorecard, governed end to end.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/run.py

This runs every step of the study in order, against a MAYA built from nothing, and takes
about twenty seconds. It is the unattended pass, useful for checking the study still
works and for reading the whole story at once.

**For a demonstration, run the steps one at a time instead.** Each is a script in this
folder, they share one MAYA at ``case_studies/runs/retail_credit``, and between any two
of them you can open the web UI (``show_estate.py`` prints how) and show what the last
one actually created:

    setup_features.py         three delivered feeds become three governed features
    setup_featureset.py       one panel, the bureau score aligned as-of, pinned
    setup_model.py            the scorecard as mathematics, with its document
    get_training_warrant.py   the warrant, and the leakage certificate that refuses
    fit_parameters.py         the fit, the checksum that ties it to its data, blind scoring
    get_execution_warrant.py  into production, and a covenant that takes it back out
    show_estate.py            the catalog, the audit chain, the custody, the lineage

The README beside this file carries the theory, the mathematics and the numbers.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fit_parameters  # noqa: E402
import get_execution_warrant  # noqa: E402
import get_training_warrant  # noqa: E402
import setup_featureset  # noqa: E402
import setup_features  # noqa: E402
import setup_model  # noqa: E402
import show_estate  # noqa: E402
from maya_demo import Narrator, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 1 — retail credit PD scorecard (banking, fitted)"

# The order matters, and it is the only thing this file decides.
STEPS = (
    setup_features,
    setup_featureset,
    setup_model,
    get_training_warrant,
    fit_parameters,
    get_execution_warrant,
    show_estate,
)


def main() -> int:
    args = arguments(__doc__ or "")
    n = Narrator(TITLE, args.quiet)
    # A full pass starts from nothing, so that running it twice means the same thing twice.
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
