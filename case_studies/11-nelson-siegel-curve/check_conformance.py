"""
Step 4 — is the desk's curve code the same thing as the mathematics that was approved?

    .venv/bin/python case_studies/11-nelson-siegel-curve/check_conformance.py

The desk's implementation is uploaded and MAYA runs the six-rung ladder on it: parse and
lint, entry point and signature, import allowlist, a static ban on filesystem, process,
network and dynamic-code use, a smoke run in the sandbox, and a determinism probe. Every rung
is reported. And with the ladder, not as a separate act somebody has to remember, the
**differential test**: MAYA compares the code against its own evaluation of the documented
mathematics.

Then the same code with the commonest Nelson–Siegel mistake in it:

    slope_loading = (1 - exp(-tau / lambda)) / tau      instead of  … / (tau / lambda)

Two things make this bug worth the study. It is *exactly* right when lambda = 1, because the
wrong loading is the right one divided by lambda — and lambda = 1 is the round number a
developer writes in a smoke test, where the loading reads (1 - e^{-tau})/tau and can be
checked against a hand calculation. And it does not leave the space the loadings span, so a
recalibration absorbs it completely: step 5 shows that the fit, the residual and every
measure of goodness are identical afterwards. A differential test against the specification
is the only thing in the building that notices.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, conformance_of, step_script  # noqa: E402
from study import (  # noqa: E402
    BUGGY_CODE,
    DESK_CODE,
    EXTRA_USERS,
    MODEL,
    NS,
    PIN_REF,
    SAMPLE,
    Cast,
)

TITLE = "Case study 11, step 4 — the code against the mathematics"
POINTS = 2000
# The parameters the desk ships with its own smoke test. lambda = 1 is not laziness, it is
# the value at which the loading is simplest to check by hand — and it is the one value at
# which the bug below cannot be seen.
DESK_SMOKE = {"beta0": 0.0430, "beta1": -0.0210, "beta2": -0.0090, "lambda": 1.0}


def upload(cast: Cast, maya: Any, source: str) -> dict[str, Any]:
    cast.mona.models.upload_artifact(f"{NS}/{MODEL}", source, sample=SAMPLE, params=DESK_SMOKE)
    maya.drain()  # the ladder runs as a job
    return dict(cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["artifact_report"] or {})


def test(cast: Cast, domain: str = PIN_REF) -> dict[str, Any]:
    return dict(cast.mona.models.conformance(f"{NS}/{MODEL}", 1, n=POINTS, featureset=domain))


def values(params: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v:.4g}" for k, v in sorted(params.items()))


def counterexamples(result: dict[str, Any], n: Narrator) -> None:
    for example in result["counterexamples"][:3]:
        n.say(
            f"  at tau={example['tau']:.4f} years: specification "
            f"{example['_expected'] * 1e4:,.1f} bp, code {example['_actual'] * 1e4:,.1f} bp"
        )


def plant_the_bug(cast: Cast, maya: Any, n: Narrator) -> None:
    """Upload the curve with the loading divided by tau, and follow what MAYA does about it."""
    from maya.core.errors import NotApproved

    n.step("The same code with the loading divided by tau instead of by tau / lambda")
    caught = conformance_of(upload(cast, maya, BUGGY_CODE))
    n.fact("ladder", "passed=True — it is valid, running, deterministic Python")
    n.fact("comparison", f"{caught['agreed']:,} of {caught['total']:,} agree")
    n.fact("run at", values(caught["params"]))
    n.say("That is the desk's own smoke test passing on broken code. The wrong loading is")
    n.say("the right one divided by lambda, so at lambda = 1 the two are the same function,")
    n.say("and the comparison agrees to the last bit on every row it looked at.")

    n.step("And on that evidence MAYA lets it through")
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    n.fact("state", cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["state"])
    n.say("The gate asks whether the last comparison against *this* artifact agreed")
    n.say("everywhere it looked. It did — at one parameter value, chosen by the developer.")
    n.say("The values are on the record beside the count, which is what lets the reviewer")
    n.say("see the problem rather than guess at it. Here she does, and sends it back.")
    cast.mgr.models.transition(
        f"{NS}/{MODEL}",
        1,
        "request_changes",
        rationale="the comparison was run at lambda=1, where a loading bug cancels; "
        "re-run it at the values MAYA picks from the declared bounds",
    )
    n.fact("state", cast.mgr.models.get(f"{NS}/{MODEL}")["versions"][0]["state"])

    n.step("Re-run at MAYA's own values, and the same submission is refused")
    honest = test(cast)
    n.fact("domain", honest["domain"])
    n.fact("run at", values(honest["params"]))
    n.fact("agreement", f"{honest['agreed']:,} of {honest['total']:,}")
    counterexamples(honest, n)
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting a version whose code contradicts its own mathematics", exc)


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Uploading the desk's implementation: the ladder, and the comparison with it")
    report = upload(cast, maya, DESK_CODE)
    n.fact("ladder", f"passed={report.get('passed')}, sandbox tier '{report.get('tier')}'")
    for rung in report.get("rungs", []):
        n.say(f"  {rung['rung']}. {rung['name']}: {rung['detail']}")
    got = conformance_of(report)
    n.fact("comparison", f"{got['agreed']:,} of {got['total']:,} agree")
    n.fact("domain", got["domain"])
    n.fact("run at", values(got["params"]))

    n.step("Re-running it on the maturities the curve will actually be asked about")
    n.say("Numbers near 1 do not test a curve: a thirty-year point and a one-month point are")
    n.say("where a loading is worth checking, and neither of them is near 1.")
    checked = test(cast)
    n.fact("domain", checked["domain"])
    n.fact("run at", values(checked["params"]))
    n.fact("agreement", f"{checked['agreed']:,} of {checked['total']:,}")
    n.say(checked["statement"])

    plant_the_bug(cast, maya, n)

    n.step("Putting the correct code back, which is tested again as it is uploaded")
    again = conformance_of(upload(cast, maya, DESK_CODE))
    n.fact("on upload", f"{again['agreed']:,} of {again['total']:,} over the default domain")
    n.say("A clean result is never inherited: it belongs to the code it was run on. And the")
    n.say("evidence kept on the version should be the evidence worth having, so the last")
    n.say("word is the pinned curve at MAYA's own parameter values:")
    final = test(cast)
    n.fact("agreement", f"{final['agreed']:,} of {final['total']:,}")
    n.fact("domain", final["domain"])
    n.fact("run at", values(final["params"]))
    recorded = (cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["artifact_report"] or {}).get(
        "conformance"
    ) or {}
    n.fact("recorded against", f"{recorded.get('artifact_hash', '')[:16]}…")

    n.step("Submitting, and approving")
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve")
    state = cast.mgr.models.get(f"{NS}/{MODEL}")["versions"][0]["state"]
    n.fact("model", f"{NS}/{MODEL} v1, {state}")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
