"""
Case study 3 — a mortgage prepayment model, and a change proposed underneath it.

    .venv/bin/python case_studies/03-mortgage-prepayment/run.py

Every step in order against a MAYA built from nothing. The unattended pass.

**For a demonstration, run the steps one at a time.** They share one MAYA at
``case_studies/runs/mortgage_prepay``, and between any two you can open the web UI
(``show_estate.py`` prints how):

    setup_features.py         four feeds become features, two of them not about loans
    setup_featureset.py       one panel, joining loan-level and market-level data
    setup_model.py            the hazard, with its scalings declared in the model
    get_training_warrant.py   the warrant, and the exception a forward-looking target needs
    fit_parameters.py         the fit against the generating process, and blind scoring
    get_execution_warrant.py  live, and a rate environment the model never saw
    propose_change.py         a definition change staged, and replayed before it lands
    show_estate.py            the catalog, the lineage, the open proposal, the audit chain

The README beside this file carries the theory, the mathematics and the numbers.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys


def _bootstrap() -> None:
    """Make this folder and ``case_studies/`` importable, whatever launched the script.

    A study is seven scripts that import each other and one shared helper, so the very
    first thing a reader meets is an import. When that fails -- launched from an IDE with
    a different working directory, or with an interpreter that is not the project's -- the
    bare ImportError names ``maya_demo`` and explains nothing, which is a poor first
    sentence for a demonstration."""
    import sys
    from pathlib import Path

    here = Path(__file__).resolve().parent
    for path in (str(here.parent), str(here)):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import maya_demo  # noqa: F401
    except ImportError as exc:  # pragma: no cover - the diagnostic, not the happy path
        raise SystemExit(
            f"Could not import the case-study helper ({exc}).\n"
            f"Expected it beside this folder, at {here.parent / 'maya_demo.py'}.\n"
            "Run a study with the project's own interpreter, from the project root:\n"
            f"    .venv/bin/python {Path(__file__).resolve().relative_to(Path.cwd())}\n"
            "    (on Windows: .venv\\Scripts\\python <the same path>)\n"
            "If that path looks wrong, the working directory is not the project root."
        ) from exc


_bootstrap()


import fit_parameters  # noqa: E402
import get_execution_warrant  # noqa: E402
import get_training_warrant  # noqa: E402
import propose_change  # noqa: E402
import setup_featureset  # noqa: E402
import setup_features  # noqa: E402
import setup_model  # noqa: E402
import show_estate  # noqa: E402
from maya_demo import Narrator, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 3 — mortgage prepayment (banking, fitted hazard)"

STEPS = (
    setup_features,
    setup_featureset,
    setup_model,
    get_training_warrant,
    fit_parameters,
    get_execution_warrant,
    propose_change,
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
