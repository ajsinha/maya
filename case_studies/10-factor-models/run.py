"""
Case study 10 — CAPM, then Fama–French, as two versions of one model.

    .venv/bin/python case_studies/10-factor-models/run.py

This runs every step of the study in order, against a MAYA built from nothing.

**For a demonstration, run the steps one at a time instead.** Each is a script in this
folder, they share one MAYA at ``case_studies/runs/factor_models``, and between any two of
them you can open the web UI (``show_estate.py`` prints how) and show what the last one
actually created:

    setup_features.py            two feeds, two indexes, two very different lags
    setup_featureset.py          one wide panel pinned, and one narrow one for later
    setup_model.py               version 1: two parameters, and the full ceremony
    get_training_warrant.py      the warrant, and a leakage exception on the *drivers*
    fit_parameters.py            the fit, and an alpha that is not skill
    get_execution_warrant.py     live in research, refused in production
    add_second_version.py        version 2, the semantic diff, and what cannot be lent
    deprecate_first_version.py   the maturity ladder, and one finding
    show_estate.py               both versions, both fits, the lineage, the audit chain

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


import add_second_version  # noqa: E402
import deprecate_first_version  # noqa: E402
import fit_parameters  # noqa: E402
import get_execution_warrant  # noqa: E402
import get_training_warrant  # noqa: E402
import setup_featureset  # noqa: E402
import setup_features  # noqa: E402
import setup_model  # noqa: E402
import show_estate  # noqa: E402
from maya_demo import Narrator, after_failure, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 10 — equity factor models (asset management, two versions of one model)"

# The order matters, and it is the only thing this file decides.
STEPS = (
    setup_features,
    setup_featureset,
    setup_model,
    get_training_warrant,
    fit_parameters,
    get_execution_warrant,
    add_second_version,
    deprecate_first_version,
    show_estate,
)


def main() -> int:
    args = arguments(__doc__ or "")
    n = Narrator(TITLE, args.quiet)
    # A full pass starts from nothing, so that running it twice means the same thing twice.
    maya = open_study(NS, reset=args.reset, args=args, fresh=True, extra_users=EXTRA_USERS)
    try:
        for step in STEPS:
            print(f"\n{'─' * 78}\n{step.TITLE}\n{'─' * 78}")
            step.main(maya, Narrator("", args.quiet))
        n.done("nine steps done")
        return 0
    except BaseException:
        after_failure(maya, NS, args)
        raise
    finally:
        maya.close()


if __name__ == "__main__":
    sys.exit(main())
