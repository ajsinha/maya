"""
Step 3 — the scorecard is registered as mathematics, with a document a reviewer reads.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/setup_model.py

MAYA parses the formula into an expression tree, which is why it can state the model's
input contract before anyone trains anything, evaluate the model for blind scoring
without executing anyone's Python, and render the mathematics into the document. The
step first tries to submit the version with an empty document, and MAYA refuses by
naming every missing section.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import EXTRA_USERS, FORMULA, MODEL, NS, ROLES, Cast, specification  # noqa: E402

TITLE = "Case study 1, step 3 — the model, and the document it cannot skip"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Registering the scorecard as a formula")
    cast.mona.models.create(NS, MODEL, formula=FORMULA, roles=ROLES)
    version = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("input contract", ", ".join(c["name"] for c in version["input_contract"]))
    n.fact(
        "parameters to be fitted",
        ", ".join(
            c["name"] for c in version["formula_ir"]["inputs"] if c.get("role") == "parameter"
        ),
    )
    n.say("MAYA read the formula into a tree; the contract is what it found, not a promise")

    n.step("A model version cannot be submitted with an empty specification")
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting before the document is complete", exc)

    n.step("Filling the nine sections §8.3 requires, then submitting for review")
    cast.mona.models.update_draft(f"{NS}/{MODEL}", spec_latex=specification())
    filled = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact(
        "sections present",
        f"{sum(1 for s in filled['completeness'] if s['present'] and not s['empty'])}"
        f" of {len(filled['completeness'])}",
    )
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve")
    n.fact(
        "model", f"{NS}/{MODEL} v1, {cast.mgr.models.get(f'{NS}/{MODEL}')['versions'][0]['state']}"
    )

    n.step("The mathematics, as MAYA renders it")
    for line in (filled["latex"] or "").splitlines():
        n.say(line)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
