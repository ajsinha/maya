"""
Step 4 — the composite: a router over the two members.

    .venv/bin/python case_studies/04-heloc-exposure/setup_composite.py

    ead = drawn + where(inDraw, draw.leq, repay.leq) * (commitment - drawn)

The exposure at default is what is already drawn plus the part of the remaining line the
borrower is expected to take, and which fraction applies depends on the regime.

Three things about a composite are worth watching here. Its **input contract** is computed
by MAYA as the union of its members' contracts plus whatever its own combiner reads — nobody
maintains that list. Its **maturity is capped** at its least mature member, so a member's
deprecation is the composite's problem too. And it is a model in every other respect: its own
version, its own specification document, its own approval.

The step also tries to compose a member that is still a draft, and MAYA refuses.

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
    COMBINE,
    COMPOSITE,
    COMPOSITE_SECTIONS,
    DRAW_MODEL,
    EXTRA_USERS,
    NS,
    REPAY_MODEL,
    Cast,
    composite_ir,
    document,
)

TITLE = "Case study 4, step 4 — the composite, and what MAYA works out for itself"
HALF_BAKED = "credit_line_usage_experimental"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("The combiner, as an expression over member outputs and features")
    n.say("ead = drawn + where(inDraw, draw.leq, repay.leq) * (commitment - drawn)")
    n.say(f"IR: {COMBINE['op']} of {len(COMBINE['args'])} arguments")

    n.step("Registering it as a model of kind 'composite'")
    cast.mona.models.create(NS, COMPOSITE, kind="composite", description=DESCRIPTIONS[COMPOSITE])
    cast.mona.models.update_draft(
        f"{NS}/{COMPOSITE}",
        ir=composite_ir(),
        spec_latex=document("HELOC exposure at default", COMPOSITE_SECTIONS),
    )
    version = cast.mona.models.get(f"{NS}/{COMPOSITE}")["versions"][0]
    n.fact("kind", version["formula_ir"]["composite"]["kind"])
    n.fact("members", ", ".join(m["alias"] for m in version["formula_ir"]["composite"]["members"]))
    n.fact("training mode", version["formula_ir"]["composite"]["train"])
    n.fact("input contract MAYA computed", ", ".join(c["name"] for c in version["input_contract"]))
    n.say("Nobody wrote that contract down: it is the union of the members' plus the combiner's.")

    n.step("Submitting, and approving")
    cast.mona.models.transition(f"{NS}/{COMPOSITE}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{COMPOSITE}", 1, "approve")
    approved = cast.mgr.models.get(f"{NS}/{COMPOSITE}")["versions"][0]
    n.fact("composite", f"v1 {approved['state']}, maturity {approved['maturity']}")
    for name in (DRAW_MODEL, REPAY_MODEL):
        member = cast.mgr.models.get(f"{NS}/{name}")["versions"][0]
        n.say(f"member {name}: maturity {member['maturity']}")
    n.say("A composite is capped at its least mature member, so those two are its ceiling.")

    n.step("A composite cannot be built on a member nobody has approved")
    cast.mona.models.create(
        NS,
        HALF_BAKED,
        formula="leq = k",
        roles={"k": "parameter"},
        description=DESCRIPTIONS[HALF_BAKED],
    )
    draft_ir = composite_ir()
    draft_ir["composite"]["members"][0] = {
        "alias": "draw",
        "ref": f"maya://model/{NS}/{HALF_BAKED}@v1",
    }
    cast.mona.models.create(
        NS,
        "heloc_exposure_at_default_unfitted",
        kind="composite",
        description=DESCRIPTIONS["heloc_exposure_at_default_unfitted"],
    )
    cast.mona.models.update_draft(
        f"{NS}/heloc_exposure_at_default_unfitted",
        ir=draft_ir,
        spec_latex=document("HELOC exposure at default", COMPOSITE_SECTIONS),
    )
    try:
        cast.mona.models.transition(f"{NS}/heloc_exposure_at_default_unfitted", 1, "submit")
        cast.mgr.models.transition(f"{NS}/heloc_exposure_at_default_unfitted", 1, "approve")
        n.say("NOT REFUSED — a composite was approved over an unapproved member")
    except NotApproved as exc:
        n.refused("approving a composite whose member is still a draft", exc)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
