"""
Case study 8 — AR(2) and GARCH(1,1) on daily index returns: a time series, governed.

    .venv/bin/python case_studies/08-arima-garch/run.py

This runs every step of the study in order, against a MAYA built from nothing. It is the
unattended pass, useful for checking the study still works and for reading the whole story
at once.

**For a demonstration, run the steps one at a time instead.** Each is a script in this
folder, and they share the project's MAYA:

    setup_data.py      the daily feed, its lags declared, pinned as it stood
    setup_models.py    AR(2) with joint constraints; GARCH(1,1) as a declared black box
    fit_mean.py        a time-ordered warrant, an explosive fit refused, a blind score
    fit_vol.py         the likelihood fit, a persistence of one refused, a sandboxed score
    go_live.py         an execution warrant, a calm week, and a crash that suspends it

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


import fit_mean  # noqa: E402
import fit_vol  # noqa: E402
import go_live  # noqa: E402
import setup_data  # noqa: E402
import setup_models  # noqa: E402
from maya_demo import Narrator, after_failure, arguments, open_study  # noqa: E402
from study import EXTRA_USERS, NS  # noqa: E402

TITLE = "Case study 8 — AR(2) and GARCH(1,1) (markets, time series)"

# The order matters, and it is the only thing this file decides.
STEPS = (setup_data, setup_models, fit_mean, fit_vol, go_live)


def main() -> int:
    args = arguments(__doc__ or "")
    n = Narrator(TITLE, args.quiet)
    maya = open_study(NS, reset=args.reset, args=args, fresh=True, extra_users=EXTRA_USERS)
    try:
        for step in STEPS:
            print(f"\n{'─' * 78}\n{step.TITLE}\n{'─' * 78}")
            step.main(maya, Narrator("", args.quiet))
        n.done("five steps done")
        return 0
    except BaseException:
        after_failure(maya, NS, args)
        raise
    finally:
        maya.close()


if __name__ == "__main__":
    sys.exit(main())
