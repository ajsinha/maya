"""
Step 3 — scoring a model nobody can read, blind, and asking what drives it.

    .venv/bin/python case_studies/19-vendor-bureau-score/validate.py

MAYA cannot evaluate a black box, but it can run one it has validated. The holdout is the
bank's own outcomes, escrowed on the warrant: the vendor's code is run in the sandbox on the
four input columns of those rows -- never the outcome -- and MAYA computes the metrics.
Then two questions a validator is asked about any model: does it work as well for every
region, and which inputs does it lean on? Both are answered through the same sandbox.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import EXTRA_USERS, MODEL, NS, PIN_REF, TARGET_JUSTIFICATION, WARRANT, Cast  # noqa: E402

TITLE = "Case study 19, step 3 — blind score, fairness and drivers"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The validation warrant: the bank's outcomes are the target")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        f"{NS}/{MODEL}@v1",
        PIN_REF,
        spec={"target": "default_12m", "seed": 19, "leakage_justification": TARGET_JUSTIFICATION},
    )
    n.fact("contract", "satisfied" if drawn["contract_report"]["ok"] else drawn["contract_report"])
    n.fact("leakage certificate", drawn["leakage_certificate"]["status"])

    n.step("Blind scoring: the vendor's code in the sandbox, on rows nobody at the bank has seen")
    scored = cast.devi.warrant(drawn["id"]).score_holdout()
    m = scored["metrics"]
    n.fact("holdout applications", m["rows"])
    n.fact("Brier score (RMSE²)", f"{m['rmse'] ** 2:.4f}")
    n.fact(
        "scored in",
        f"{m['scored_in']}, tier {m['sandbox_tier']}, artifact {m['artifact_hash'][:12]}…",
    )

    n.step("Performance by region, and what drives the score")
    ev = cast.devi.evidence.compute(drawn["id"], segment="region", repeats=3)["result"]
    for seg in ev["segments"]["segments"]:
        if not seg["suppressed"]:
            n.say(
                f"{seg['segment']:<6} {seg['rows']:>4} rows  MAE {seg['mae']:.3f}  bias {seg['bias']:+.3f}"
            )
    n.fact("worst-to-best MAE ratio", f"{ev['segments']['mae_ratio']:.2f}")
    n.fact("flagged regions", ", ".join(ev["segments"]["flagged"]) or "none")
    for imp in ev["importance"]:
        n.say(
            f"{imp['input']:<14} {imp['share']:>5.0%} of the importance  (RMSE +{imp['rmse_increase']:.4f} when shuffled)"
        )

    n.step("Sealing the warrant")
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    cast.mgr.training.seal(drawn["id"])
    attempts = cast.devi.training.get(drawn["id"])["holdout_attempts"]
    n.fact("holdout attempts on the warrant", f"{attempts} (the score, and the evidence run)")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
