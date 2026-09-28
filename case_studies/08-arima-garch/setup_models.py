"""
Step 2 — two models: a formula with joint constraints, and a recursion MAYA cannot write.

    .venv/bin/python case_studies/08-arima-garch/setup_models.py

The conditional mean is an AR(2). Once its lags are features it is a row-wise formula, and
MAYA can read it, typeset it and evaluate it. What bounds on single parameters cannot say
is that it is stationary only inside a triangle: each of phi1 and phi2 can sit well inside
(-1, 1) while the pair describe a process that explodes. So the model declares the two
joint constraints itself.

The conditional variance is a GARCH(1,1). Its right-hand side holds yesterday's variance,
a state that depends on the parameters and is not a column any lag can produce, so MAYA's
formula language cannot express it. It is registered as a declared black box, with the
stationarity constraint alpha + beta < 1, and its code goes through the ladder.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    EXTRA_USERS,
    MEAN_CONSTRAINTS,
    MEAN_FORMULA,
    MEAN_MODEL,
    MEAN_ROLES,
    NS,
    SAMPLE,
    SECTIONS_MEAN,
    SECTIONS_VOL,
    TRUE_GARCH,
    VOL_CODE,
    VOL_IR,
    VOL_MODEL,
    Cast,
    document,
)

TITLE = "Case study 8, step 2 — a formula with joint constraints, and a recursion"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)

    n.step("The conditional mean: AR(2), a formula once the lags are features")
    translated = cast.mona.models.kernel(MEAN_FORMULA, roles=MEAN_ROLES)
    ir = dict(translated["ir"])
    ir["constraints"] = MEAN_CONSTRAINTS
    cast.mona.models.create(NS, MEAN_MODEL, ir=ir, description="AR(2) conditional mean")
    cast.mona.models.update_draft(
        f"{NS}/{MEAN_MODEL}", spec_latex=document("AR(2) conditional mean", SECTIONS_MEAN)
    )
    cast.mona.models.transition(f"{NS}/{MEAN_MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MEAN_MODEL}", 1, "approve")
    n.fact("formula", translated["latex"])
    n.fact("inputs", ", ".join(f"{i['name']} ({i['role']})" for i in translated["inputs"]))
    for c in MEAN_CONSTRAINTS:
        n.say(f"  constraint: {c['why'].split(':')[0]}")

    n.step("The conditional variance: GARCH(1,1), a declared black box")
    cast.mona.models.create(NS, VOL_MODEL, kind="black_box", ir=VOL_IR)
    cast.mona.models.upload_artifact(
        f"{NS}/{VOL_MODEL}", VOL_CODE, sample=SAMPLE, params=dict(TRUE_GARCH)
    )
    maya.drain()  # the ladder runs as a job
    report = cast.mona.models.get(f"{NS}/{VOL_MODEL}")["versions"][0]["artifact_report"] or {}
    n.fact("ladder", f"passed={report.get('passed')}, sandbox tier '{report.get('tier')}'")
    for rung in report.get("rungs", []):
        n.say(f"  {rung['rung']}. {rung['name']}: {rung['detail']}")
    if not report.get("passed"):
        raise SystemExit("The GARCH artifact did not pass the ladder; see the rungs above.")
    cast.mona.models.update_draft(
        f"{NS}/{VOL_MODEL}", spec_latex=document("GARCH(1,1) conditional variance", SECTIONS_VOL)
    )
    cast.mona.models.transition(f"{NS}/{VOL_MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{VOL_MODEL}", 1, "approve")
    n.fact("constraint", VOL_IR["constraints"][0]["why"].split(":")[0])
    n.say("MAYA cannot evaluate this model itself, so it has no formula to compare the code")
    n.say("against. It can still hash the code, run it in the sandbox, refuse anything that")
    n.say("touches files or the network, and check it gives the same answer twice.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
