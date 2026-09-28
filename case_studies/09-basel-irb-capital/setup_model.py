"""
Step 2 — the capital formula as mathematics, with its document, approved.

    .venv/bin/python case_studies/09-basel-irb-capital/setup_model.py

The formula is typed the way the regulation prints it, ``N^{-1}(pd)`` included. Read as a
power, that superscript would make it ``1/N(pd)`` -- a formula that parses, computes and is
wrong -- so the step shows what MAYA made of it. Version 1 carries a mistake the next step
finds: the maturity goes in unfloored and uncapped.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import DESCRIPTIONS, EXTRA_USERS, FORMULA_V1, MODEL, NS, ROLES, Cast, spec_document  # noqa: E402

TITLE = "Case study 9, step 2 — the IRB formula, version 1"


def _ops(node: Any) -> set[str]:
    if isinstance(node, dict):
        found = {node["op"]} if "op" in node else set()
        for value in node.values():
            found |= _ops(value)
        return found
    if isinstance(node, list):
        return set().union(*(_ops(v) for v in node)) if node else set()
    return set()


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Registering the formula, typed as the regulation prints it")
    cast.mona.models.create(
        NS,
        MODEL,
        formula=FORMULA_V1,
        roles=ROLES,
        description=DESCRIPTIONS[MODEL],
    )
    v = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("inputs", ", ".join(c["name"] for c in v["input_contract"]))
    n.fact("parameters", "none: every constant is prescribed by regulation")
    n.fact(
        "N^{-1} read as",
        "ncdfinv (the normal quantile)" if "ncdfinv" in _ops(v["formula_ir"]) else "a power!",
    )

    n.step("The specification document, then review")
    cast.mona.models.update_draft(f"{NS}/{MODEL}", spec_latex=spec_document(1))
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve", rationale="document complete")
    n.fact("version 1", "approved by mgr")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
