"""
Step 3 — Black–Scholes–Merton, registered from the LaTeX the quant wrote.

    .venv/bin/python case_studies/05-option-pricing/setup_model.py

``ncdf`` is in MAYA's formula language, so the whole pricer is one formula model: there is
no black box, no uploaded weights, nothing MAYA cannot evaluate itself. The volatility is
the only parameter, and it is nine numbers rather than one, because a single volatility
cannot reproduce a smile — which step 5 measures rather than asserts.

Two things happen here that are worth watching. MAYA parses the LaTeX into an expression
tree and can hand the tree back as runnable reference Python, which is what step 4 tests the
desk's pricer against. And the volatility gets **bounds**, declared on the tree, which MAYA
then enforces on every parameter upload for the life of the version.

The version is left a draft. It cannot be submitted yet — its code has not been checked,
which is step 4 — and nothing can be drawn on it, which the step demonstrates.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    DESCRIPTIONS,
    EXTRA_USERS,
    FORMULA,
    MODEL,
    MODEL_REF,
    NS,
    PIN_REF,
    ROLES,
    SIGMAS,
    VOL_BOUNDS,
    WARRANT,
    Cast,
    specification,
)

TITLE = "Case study 5, step 3 — the pricer in LaTeX, and a bound on the volatility"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Registering it, in the notation it was written in")
    for line in FORMULA.strip().splitlines():
        n.say(line)
    cast.mona.models.create(
        NS, MODEL, formula=FORMULA, roles=ROLES, description=DESCRIPTIONS[MODEL]
    )
    version = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("input contract", ", ".join(c["name"] for c in version["input_contract"]))
    n.fact("parameters", ", ".join(SIGMAS))
    n.say("'mid' is not an input: the model cannot see the price it is calibrated to")

    n.step("Declaring what a volatility may be, on the tree MAYA parsed")
    ir = dict(version["formula_ir"])
    ir["inputs"] = [
        {**inp, "bounds": list(VOL_BOUNDS)} if inp["name"] in SIGMAS else inp
        for inp in ir["inputs"]
    ]
    cast.mona.models.update_draft(f"{NS}/{MODEL}", ir=ir, spec_latex=specification())
    version = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    bounds = {
        i["name"]: i.get("bounds") for i in version["formula_ir"]["inputs"] if i["name"] in SIGMAS
    }
    n.fact("bounds", f"{VOL_BOUNDS} on all {len(bounds)} volatilities")
    n.fact("IR hash", f"{version['ir_hash'][:16]}…")
    n.say("A negative volatility is now refusable by the platform rather than by review.")

    n.step("MAYA's own reference implementation, lifted from the same tree")
    code = cast.mona.models.reference_code(f"{NS}/{MODEL}", 1)["source"]
    for line in code.strip().splitlines():
        if "= params[" not in line:
            n.say(f"  {line}")
    n.say("  (the nine 'v_sigma_ij = params[...]' lines are elided here; nothing else is)")

    n.step("Nothing can be drawn on a draft")
    try:
        cast.devi.training.create(NS, WARRANT, MODEL_REF, PIN_REF, spec={"target": "mid"})
    except NotApproved as exc:
        n.refused("drawing a training warrant on a model version nobody has approved", exc)
    n.fact("state", cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["state"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
