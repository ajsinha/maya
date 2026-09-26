"""
Step 3 — what the unisex table costs, measured; a finding; and the risk accepted in writing.

    .venv/bin/python case_studies/45-gompertz-makeham-mortality/fairness.py

The validator asks MAYA for the error and bias by sex and by region on the escrowed
holdout, and for what drives the table. By sex the bias is large and systematic: the table
understates men's mortality and overstates women's. That is not a defect to fix -- the law
forbids pricing by sex -- but it is a risk to state, size and own. So the validator raises
a finding, and a manager who is not the model's owner accepts the risk with the reason in
writing, where an auditor will find it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from maya_demo import browse_hint  # noqa: E402
from study import EXTRA_USERS, MODEL, NS, WARRANT, Cast, find_warrant  # noqa: E402

TITLE = "Case study 45, step 3 — fairness, a finding, and an accepted risk"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import PermissionDenied

    cast = Cast(maya)
    warrant = find_warrant(cast.lara, WARRANT)
    ps = next(p for p in warrant["parameter_sets"] if p["state"] == "approved")

    n.step("Error and bias by sex, and what drives the table")
    by_sex = cast.lara.evidence.compute(
        warrant["id"], parameter_set_id=ps["id"], segment="sex", repeats=3
    )["result"]
    for seg in by_sex["segments"]["segments"]:
        n.say(
            f"{seg['segment']}: {seg['rows']} cells, MAE {seg['mae']:.5f}, bias {seg['bias']:+.5f} ({'under' if seg['bias'] < 0 else 'over'}states)"
        )
    n.fact(
        "worst-to-best MAE ratio",
        f"{by_sex['segments']['mae_ratio']:.2f}: by error size, nothing stands out",
    )
    n.fact("gap in bias between the sexes", f"{by_sex['segments']['bias_gap']:.5f}")
    n.fact(
        "systematic (wrong in one direction)", ", ".join(by_sex["segments"]["systematic"]) or "none"
    )
    for imp in by_sex["importance"]:
        n.say(
            f"{imp['input']}: {imp['share']:.1%} of the importance (RMSE +{imp['rmse_increase']:.5f} when shuffled)"
        )

    n.step("And by region, for comparison")
    by_region = cast.lara.evidence.compute(
        warrant["id"], parameter_set_id=ps["id"], segment="region", importance=False
    )["result"]
    n.fact("worst-to-best MAE ratio by region", f"{by_region['segments']['mae_ratio']:.2f}")
    n.fact("gap in bias between regions", f"{by_region['segments']['bias_gap']:.5f}")
    n.fact("systematic", ", ".join(by_region["segments"]["systematic"]) or "none")

    n.step("A finding, and the risk accepted by someone other than the owner")
    male = next(s for s in by_sex["segments"]["segments"] if s["segment"] == "M")
    finding = cast.lara.governance.raise_finding(
        f"{NS}/{MODEL}",
        "Unisex table understates male and overstates female mortality",
        "medium",
        source="validation",
        detail=f"Holdout bias for men {male['bias']:+.5f}; MAE ratio by sex {by_sex['segments']['mae_ratio']:.2f}.",
    )
    try:
        cast.mona.governance.move_finding(finding["id"], "accept", "we cannot use sex anyway")
    except PermissionDenied as exc:
        n.refused("the owner accepting the risk in her own model", exc)
    accepted = cast.mgr.governance.move_finding(
        finding["id"],
        "accept",
        "Sex-based pricing is prohibited (Test-Achats, C-236/09). The cross-subsidy is measured "
        "here and reserved for; the portfolio's sex mix is monitored quarterly.",
    )
    n.fact("finding", f"{accepted['state']} by {accepted['closed_by']}")
    n.fact("resolution on record", accepted["resolution"][:70] + "…")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
