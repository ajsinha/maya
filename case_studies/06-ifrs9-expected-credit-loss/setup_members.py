"""
Step 3 — three members, three shapes chosen for what each quantity is.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/setup_members.py

Expected credit loss is a product of three estimates, and the three are not alike:

* a **probability** belongs in [0, 1], so the PD member is a logistic;
* a **loss rate** is also a share, so the LGD member is a logistic too — a linear form would
  predict a negative loss on a well-secured account and a loss above par on a badly secured
  one, and both are impossible rather than merely unlikely;
* an **exposure** is a quantity of money with a known floor and ceiling — the balance drawn
  and the whole limit — so the EAD member is a linear interpolation between them with one
  parameter, the credit conversion factor.

Each is a model in its own right, with its own document and its own approval, before the
composite that multiplies them exists.

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
    EAD_FORMULA,
    EAD_MODEL,
    EAD_ROLES,
    EAD_SECTIONS,
    EXTRA_USERS,
    LGD_FORMULA,
    LGD_MODEL,
    LGD_ROLES,
    LGD_SECTIONS,
    NS,
    PD_FORMULA,
    PD_MODEL,
    PD_ROLES,
    PD_SECTIONS,
    Cast,
    document,
)

TITLE = "Case study 6, step 3 — the three factors, as three models"

MEMBERS = (
    (PD_MODEL, PD_FORMULA, PD_ROLES, PD_SECTIONS, "Twelve-month probability of default"),
    (LGD_MODEL, LGD_FORMULA, LGD_ROLES, LGD_SECTIONS, "Secured loss given default"),
    (EAD_MODEL, EAD_FORMULA, EAD_ROLES, EAD_SECTIONS, "Exposure at default"),
)


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    for name, formula, roles, sections, title in MEMBERS:
        n.step(name)
        for line in formula.strip().splitlines():
            n.say(line)
        cast.mona.models.create(NS, name, formula=formula, roles=roles)
        cast.mona.models.update_draft(f"{NS}/{name}", spec_latex=document(title, sections))
        cast.mona.models.transition(f"{NS}/{name}", 1, "submit")
        cast.mgr.models.transition(f"{NS}/{name}", 1, "approve")
        version = cast.mgr.models.get(f"{NS}/{name}")["versions"][0]
        n.fact("contract", ", ".join(c["name"] for c in version["input_contract"]))
        n.fact(
            "parameters",
            ", ".join(
                c["name"] for c in version["formula_ir"]["inputs"] if c.get("role") == "parameter"
            ),
        )
        n.fact("state", f"v1 {version['state']}, maturity {version['maturity']}")

    n.step("Three documents, and one weakness worth reading out")
    n.say(
        "The LGD member measures collateral coverage on the balance drawn *today*, while the "
        "loss is realised on the exposure at default — which the third member says is larger. "
        "So it overstates coverage and understates loss, by most on exactly the accounts with "
        "the largest undrawn limits. Its own Known Weaknesses section says so, names the "
        "honest fix (make the coverage read the EAD member's output, which would make this a "
        "pipeline rather than a product), and says it is not done here."
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
