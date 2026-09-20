"""
Step 3 — Nelson–Siegel, registered from the LaTeX the curve quant wrote.

    .venv/bin/python case_studies/11-nelson-siegel-curve/setup_model.py

Four lines of LaTeX, three of them intermediates, and MAYA has the whole curve as an
expression tree: no black box, no uploaded weights, nothing it cannot evaluate itself. The
two factor loadings are named — ``L_slope`` and ``L_curve`` — because they are what a reader
of the specification has to recognise and what the calibration in step 5 asks the model for.

Then the bounds, one per parameter, declared on the tree MAYA parsed. Three of them are
exactly right. The fourth constraint anybody who has fitted this curve wants —
$\\beta_0 + \\beta_1 > 0$, a non-negative instantaneous short rate — is a statement about two
parameters at once, and there is no place for it in a table of per-parameter bounds. This
step says so; step 5 shows what it costs.

The version is left a draft: its code has not been checked, which is step 4, and nothing can
be drawn on it, which the step demonstrates.

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
    BOUNDS,
    CONSTRAINTS,
    EXTRA_USERS,
    FORMULA,
    MODEL,
    MODEL_REF,
    NS,
    PARAMS,
    PIN_REF,
    ROLES,
    WARRANT,
    Cast,
    specification,
)

TITLE = "Case study 11, step 3 — the curve in LaTeX, and the bound that cannot be written"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Registering it, in the notation it was written in")
    for line in FORMULA.strip().splitlines():
        n.say(line)
    cast.mona.models.create(NS, MODEL, formula=FORMULA, roles=ROLES)
    version = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("input contract", ", ".join(c["name"] for c in version["input_contract"]))
    n.fact("parameters", ", ".join(PARAMS))
    n.fact("intermediates", ", ".join(sorted(version["formula_ir"]["lets"])))
    n.say("A maturity in, a yield out. 'y' is the target and is not an input, and nor is the")
    n.say("par quote: the curve cannot see the number it is fitted to.")
    n.say("Note what MAYA had to be told: '\\tau' is declared in roles, because LaTeX reads")
    n.say("an undeclared 'tau' the way LaTeX means it — t times a times u.")

    n.step("Declaring what each parameter may be, on the tree MAYA parsed")
    ir = dict(version["formula_ir"])
    ir["inputs"] = [
        {**inp, "bounds": list(BOUNDS[inp["name"]])} if inp["name"] in BOUNDS else inp
        for inp in ir["inputs"]
    ]
    ir["constraints"] = CONSTRAINTS
    cast.mona.models.update_draft(f"{NS}/{MODEL}", ir=ir, spec_latex=specification())
    version = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    for inp in version["formula_ir"]["inputs"]:
        if inp["name"] in BOUNDS:
            n.fact(inp["name"], f"bounds {inp['bounds']}")
    n.fact("IR hash", f"{version['ir_hash'][:16]}…")
    n.say("beta0 >= 0 says the long rate is not negative, and MAYA will enforce it on every")
    n.say("upload for the life of the version.")
    for c in version["formula_ir"].get("constraints", []):
        n.fact("constraint", f"{c['expr']['op']}(beta0, beta1) {c['op']} {c['rhs']}")
        n.say(f"  because: {c['why']}")
    n.say("That one spans two parameters, and a bound belongs to one, so it could not be said")
    n.say("here at all until this study asked for it. Step 5 uploads a set that satisfies all")
    n.say("four rows of the bounds table and implies a short rate of -6.7%.")

    n.step("MAYA's own reference implementation, lifted from the same tree")
    code = cast.mona.models.reference_code(f"{NS}/{MODEL}", 1)["source"]
    body = code[code.index("def predict") :]
    for line in body.strip().splitlines():
        n.say(f"  {line}")
    n.say("Nobody typed that twice: it is generated from the tree the LaTeX produced, which")
    n.say("is what makes step 4's comparison and step 5's blind scoring possible at all.")

    n.step("The specification document, and what MAYA checks about it")
    sections = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["completeness"]
    empty = [s["section"] for s in sections if not s["present"] or s["empty"]]
    n.fact("required sections", f"{len(sections)} required, {len(empty)} empty")
    n.say("An empty required section blocks submission, so Calibration Methodology and Known")
    n.say("Weaknesses are written before the model may move, not afterwards.")

    n.step("Nothing can be drawn on a draft")
    try:
        cast.devi.training.create(NS, WARRANT, MODEL_REF, PIN_REF, spec={"target": "y"})
    except NotApproved as exc:
        n.refused("drawing a training warrant on a model version nobody has approved", exc)
    n.fact("state", cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["state"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
