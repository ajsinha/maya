"""
Case study 7 — a card-fraud neural network, governed as a declared black box.

    .venv/bin/python case_studies/07-neural-network/run.py

This runs every step of the study in order, against a MAYA built from nothing, and takes
about ten seconds. It is the unattended pass, useful for checking the study still works
and for reading the whole story at once.

**For a demonstration, run the steps one at a time instead.** Each is a script in this
folder, they share one MAYA at ``case_studies/runs/card_fraud``, and between any two of
them you can open the web UI (``show_estate.py`` prints how) and show what the last one
actually created:

    setup_features.py         three delivered feeds become three governed features
    setup_featureset.py       one panel, the profile aligned as-of, pinned
    setup_model.py            the network as a declared black box, and the ladder on its code
    get_training_warrant.py   the contract, the leakage certificate, the declared seed
    fit_parameters.py         the fit twice, the challenger, and MAYA refusing to score it
    get_execution_warrant.py  into production, and drift the covenants can still see
    show_estate.py            the catalog, the audit chain, the lineage, the bundle's refusal

The README beside this file carries the theory, the analysis and the numbers.

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
import setup_featureset  # noqa: E402
import setup_features  # noqa: E402
import setup_model  # noqa: E402
import show_estate  # noqa: E402
from maya_demo import Narrator, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 7 — a card-fraud neural network (banking, declared black box)"

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
