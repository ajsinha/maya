"""
Step 3 — the model, registered from the LaTeX the analyst wrote.

    .venv/bin/python case_studies/02-mortgage-cashflow/setup_model.py

MAYA reads LaTeX and Python into the same expression tree, and for a formula this shape
the LaTeX *is* the documentation. Having parsed it, MAYA can state the model's input
contract, and it can lift the tree back into runnable reference Python — a statement of
the specification that nobody typed twice, and the thing step 4 tests the desk's code
against.

The version is left as a draft. It cannot be submitted yet: its code has not been
checked, which is step 4.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import DESCRIPTIONS, EXTRA_USERS, FORMULA, MODEL, NS, ROLES, Cast, specification  # noqa: E402

TITLE = "Case study 2, step 3 — the model in LaTeX, and MAYA's own reference code"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Registering it, in the notation it was written in")
    for line in FORMULA.strip().splitlines():
        n.say(line)
    cast.mona.models.create(
        NS, MODEL, formula=FORMULA, roles=ROLES, description=DESCRIPTIONS[MODEL]
    )
    version = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("input contract", ", ".join(c["name"] for c in version["input_contract"]))
    n.fact(
        "parameters",
        ", ".join(
            c["name"] for c in version["formula_ir"]["inputs"] if c.get("role") == "parameter"
        ),
    )
    n.say("'remitted' is not an input: the model cannot see what it is measured against")

    n.step("The specification document, then MAYA's reference implementation")
    cast.mona.models.update_draft(f"{NS}/{MODEL}", spec_latex=specification())
    code = cast.mona.models.reference_code(f"{NS}/{MODEL}", 1)["source"]
    for line in code.strip().splitlines():
        n.say(f"  {line}")
    n.fact("state", cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["state"])
    n.say("Still a draft: nothing has yet checked that the desk's code computes this.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
