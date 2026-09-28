"""
Step 4 — the composite, and the two numbers that belong to nobody's model.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/setup_composite.py

    sicr = pd.pd12 / pdOrigination
    ecl  = where(sicr > sicrThreshold, lifetimeFactor, 1) * pd.pd12 * lgd.lgd * ead.ead

This is what makes IFRS 9 more than a product of three models. The standard's judgement
calls — *when* has credit risk increased significantly since origination, and *how much*
more loss does a lifetime horizon imply — live in the combination rather than in any member.
They are parameters of the combiner: the numbers an impairment committee actually argues
about, and the ones a reviewer of the accounts will ask to see minuted.

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
    COMBINER_WEIGHTS,
    COMPOSITE,
    COMPOSITE_SECTIONS,
    EXTRA_USERS,
    NS,
    Cast,
    composite_ir,
    document,
)

TITLE = "Case study 6, step 4 — the composite, and the committee's two numbers"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The combination, in words and then as MAYA holds it")
    n.say("sicr = pd.pd12 / pdOrigination")
    n.say("ecl  = where(sicr > sicrThreshold, lifetimeFactor, 1) * pd.pd12 * lgd.lgd * ead.ead")

    n.step("Registering it")
    cast.mona.models.create(NS, COMPOSITE, kind="composite", description=DESCRIPTIONS[COMPOSITE])
    cast.mona.models.update_draft(
        f"{NS}/{COMPOSITE}",
        ir=composite_ir(),
        spec_latex=document("IFRS 9 expected credit loss", COMPOSITE_SECTIONS),
    )
    version = cast.mona.models.get(f"{NS}/{COMPOSITE}")["versions"][0]
    composite = version["formula_ir"]["composite"]
    n.fact("kind", composite["kind"])
    n.fact("members", ", ".join(m["alias"] for m in composite["members"]))
    n.fact("training", composite["train"])
    n.fact("contract MAYA computed", ", ".join(c["name"] for c in version["input_contract"]))
    for c in version["input_contract"]:
        n.say(f"{c['name']:<15} needed by {', '.join(c['needed_by'])}")

    n.step("And the combiner's own parameters")
    declared = [c["name"] for c in version["input_contract"] if c.get("role") == "parameter"]
    n.fact("declared as parameters", declared or "none")
    n.fact("the combiner reads", ", ".join(COMBINER_WEIGHTS))
    n.say(
        "Those two are not any member's parameters. Whether MAYA knows about them is the "
        "thing this step is here to find out, and §9 of the README says what it found."
    )

    n.step("Submitting, and approving")
    cast.mona.models.transition(f"{NS}/{COMPOSITE}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{COMPOSITE}", 1, "approve")
    approved = cast.mgr.models.get(f"{NS}/{COMPOSITE}")["versions"][0]
    n.fact("composite", f"v1 {approved['state']}, maturity {approved['maturity']}")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
