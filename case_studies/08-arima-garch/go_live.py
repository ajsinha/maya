"""
Step 5 — the volatility model in production, and the day volatility spikes.

    .venv/bin/python case_studies/08-arima-garch/go_live.py

The execution warrant licenses the sealed GARCH parameters in two environments with three
covenants. The one that matters is on the output: a forecast daily variance above 0.0006 (a
2.4% daily move, about 39% a year, three times the long-run level) is not a forecast a risk
system should act on without a person looking at it. A calm week reports inside it. A crash week does not, and the warrant
suspends itself.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    CONTACT,
    EXTRA_USERS,
    LIVE,
    NS,
    VOL_CODE,
    VOL_WARRANT,
    Cast,
    find_warrant,
)

TITLE = "Case study 8, step 5 — in production, and the day volatility spikes"
MAX_VARIANCE = 0.0006
COVENANTS = [
    {"kind": "input_null_rate", "attr": "ret", "max": 0.0},
    {"kind": "input_range", "attr": "ret", "min": -0.4, "max": 0.4},
    {"kind": "output_range", "attr": "sigma2", "min": 0.0, "max": MAX_VARIANCE},
]


def desk_model() -> Any:
    """The desk's own artifact, the code MAYA validated, run where the desk runs it."""
    namespace: dict[str, Any] = {}
    exec(compile(VOL_CODE, "garch_artifact", "exec"), namespace)  # noqa: S102 - the study's own code
    return namespace["Model"]()


def batch(frame: Any, values: dict[str, float], shock: float) -> dict[str, Any]:
    """A week of scoring as the desk reports it: the last 60 days per index, with the final
    five days' returns scaled by ``shock`` to stand in for a crash."""
    rows = frame.sort_values(["index", "date"]).groupby("index").tail(60).copy()
    last = rows.groupby("index").cumcount(ascending=False) < 5
    rows.loc[last, "ret"] = rows.loc[last, "ret"].astype(float) * shock
    variance = np.asarray(
        desk_model().predict({"ret": rows["ret"], "index": rows["index"]}, values, None)
    )
    ret = rows["ret"].to_numpy(float)
    return {
        "rows": int(len(rows)),
        "input_stats": {
            "ret": {"null_rate": 0.0, "min": float(ret.min()), "max": float(ret.max())}
        },
        "output_stats": {"sigma2": {"min": float(variance.min()), "max": float(variance.max())}},
    }


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, VOL_WARRANT)
    approved = [p for p in warrant.get("parameter_sets", []) if p["state"] == "approved"]
    if not approved:
        raise SystemExit(f"No approved parameter set on '{VOL_WARRANT}' — run fit_vol.py")
    parameters = approved[0]

    n.step("The execution warrant: where, until when, under which covenants")
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        parameter_set_id=parameters["id"],
        spec={"environments": ["dev", "prod"], "contact": CONTACT, "covenants": COVENANTS},
    )
    for c in COVENANTS:
        n.say(f"  covenant: {c}")
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    n.fact("status", cast.devi.execution.bundle(ew["id"], "prod")["status"])

    with cast.devi.warrant(warrant["id"]).data() as ds:
        frame = ds.frame

    n.step("A calm week")
    calm = batch(frame, parameters["values"], 1.0)
    reported = cast.devi.execution.report(ew["id"], environment="prod", **calm)
    n.fact("largest forecast variance", f"{calm['output_stats']['sigma2']['max']:.2e}")
    n.fact("warrant", reported["status"])

    n.step("A crash week: the last five days' moves six times larger")
    crash = batch(frame, parameters["values"], 6.0)
    breach = cast.devi.execution.report(ew["id"], environment="prod", **crash)
    n.fact("largest forecast variance", f"{crash['output_stats']['sigma2']['max']:.2e}")
    n.fact("warrant", breach["status"])
    if breach["status"] != "suspended":
        raise SystemExit(
            "The crash week did not breach the covenant; the study's claim below is false"
        )
    for broken in breach["breaches"]:
        n.say(f"  breach: {broken['detail']}")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.say(f"  the next call is refused: {exc.message[:160]}")
    n.say("The model did what GARCH does after a crash: it forecast high variance. The")
    n.say("covenant says a forecast that high goes to a person before a system acts on it,")
    n.say("and MAYA took the model out of service until someone has looked.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
