"""
Step 4 — is the code the desk runs the same thing as the mathematics that was approved?

    .venv/bin/python case_studies/02-mortgage-cashflow/check_conformance.py

This is the heart of the study. The desk's implementation is uploaded, and MAYA runs the
six-rung ladder on it: parse and lint, entry point and signature, import allowlist, a
static ban on filesystem, process, network and dynamic-code use, a smoke run in the
sandbox, and a determinism probe. Every rung is reported.

And then, with the ladder and not as a separate act somebody has to remember, the
**differential test**: MAYA compares the desk's code against its own evaluation of the
documented mathematics. The step re-runs it on a better domain — the pinned tape's own
values, rather than numbers near 1 — and then shows what happens to the same code with
the commonest mortgage bug in it: amortising over the original term instead of the term
remaining. It passes every rung of the ladder, agrees with the specification nowhere, and
cannot be submitted.

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
    BUGGY_CODE,
    DESK_CODE,
    EXTRA_USERS,
    MODEL,
    NS,
    PIN_REF,
    SAMPLE,
    SERVICING_FEE,
    Cast,
)

TITLE = "Case study 2, step 4 — the code against the mathematics"
POINTS = 2000


def upload(cast: Cast, maya: Any, source: str) -> dict[str, Any]:
    cast.mona.models.upload_artifact(
        f"{NS}/{MODEL}", source, sample=SAMPLE, params={"fee": SERVICING_FEE}
    )
    maya.drain()  # the ladder runs as a job
    return dict(cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["artifact_report"] or {})


def test(cast: Cast) -> dict[str, Any]:
    return dict(cast.mona.models.conformance(f"{NS}/{MODEL}", 1, n=POINTS, featureset=PIN_REF))


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Uploading the desk's implementation: the ladder, and the comparison with it")
    report = upload(cast, maya, DESK_CODE)
    n.fact("ladder", f"passed={report.get('passed')}, sandbox tier '{report.get('tier')}'")
    for rung in report.get("rungs", []):
        n.say(f"  {rung['rung']}. {rung['name']}: {rung['detail']}")
    got = report["conformance"]
    n.fact("comparison", f"{got['agreed']:,} of {got['total']:,} agree")
    n.fact("domain", got["domain"])
    n.say(
        "The comparison ran with the ladder — nobody had to remember to ask for it — and "
        "its result is recorded against the artifact hash it tested."
    )

    n.step("Re-running it on the domain the model will actually be asked about")
    n.say("Numbers near 1 do not test a mortgage: a 1.2-month term at a 100% coupon is not")
    n.say("a loan, and a bug that only shows on a seasoned one hides in that domain.")
    checked = test(cast)
    n.fact("domain", checked["domain"])
    n.fact("agreement", f"{checked['agreed']:,} of {checked['total']:,}")
    n.say(checked["statement"])

    n.step("The same code with the commonest mortgage bug in it")
    n.say("remaining = term, instead of remaining = term - age")
    caught = upload(cast, maya, BUGGY_CODE)["conformance"]
    n.fact("ladder", "passed=True — it is valid, running, deterministic Python")
    n.fact("agreement", f"{caught['agreed']:,} of {caught['total']:,}")
    on_the_tape = test(cast)
    n.fact(
        "agreement on the tape's own values",
        f"{on_the_tape['agreed']:,} of {on_the_tape['total']:,}",
    )
    for example in on_the_tape["counterexamples"][:2]:
        where = ", ".join(
            f"{k}={v:,.0f}" if abs(v) >= 1000 else f"{k}={v:,.4g}"
            for k, v in example.items()
            if not k.startswith("_")
        )
        n.say(
            f"  at {where}: specification {example['_expected']:,.2f}, "
            f"code {example['_actual']:,.2f}"
        )
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting a version whose code contradicts its own mathematics", exc)

    n.step("Putting the correct code back, which is tested again as it is uploaded")
    again = upload(cast, maya, DESK_CODE)["conformance"]
    n.fact("agreement", f"{again['agreed']:,} of {again['total']:,}")
    n.fact("tested against", f"{again['artifact_hash'][:16]}…")
    n.say("A clean result is never inherited: it belongs to the code it was run on.")

    n.step("Submitting, and approving")
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve")
    state = cast.mgr.models.get(f"{NS}/{MODEL}")["versions"][0]["state"]
    n.fact("model", f"{NS}/{MODEL} v1, {state}")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
