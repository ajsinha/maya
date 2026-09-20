"""
Step 4 — is the code the desk runs the same thing as the mathematics that was approved?

    .venv/bin/python case_studies/02-mortgage-cashflow/check_conformance.py

This is the heart of the study. The desk's implementation is uploaded, and MAYA runs the
six-rung ladder on it: parse and lint, entry point and signature, import allowlist, a
static ban on filesystem, process, network and dynamic-code use, a smoke run in the
sandbox, and a determinism probe. Every rung is reported.

Then the differential test. MAYA draws thousands of inputs **from the pinned tape's own
values** and compares the desk's code against its own evaluation of the documented
mathematics. The script does this three times:

1. the correct implementation, which agrees everywhere;
2. the same code with the commonest mortgage bug — amortising over the original term
   instead of the term remaining — which agrees nowhere, and cannot be submitted;
3. the correct code put back, which still cannot be submitted until the test is re-run,
   because a clean result belonged to different code.

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
    n.step("Uploading the desk's implementation, and the six-rung ladder on it")
    report = upload(cast, maya, DESK_CODE)
    n.fact("ladder", f"passed={report.get('passed')}, sandbox tier '{report.get('tier')}'")
    for rung in report.get("rungs", []):
        n.say(f"  {rung['rung']}. {rung['name']}: {rung['detail']}")

    n.step("The differential test, on the domain the model will actually be asked about")
    checked = test(cast)
    n.fact("domain", checked["domain"])
    n.fact("agreement", f"{checked['agreed']:,} of {checked['total']:,}")
    n.say(checked["statement"])

    n.step("The same code with the commonest mortgage bug in it")
    n.say("remaining = term, instead of remaining = term - age")
    upload(cast, maya, BUGGY_CODE)
    caught = test(cast)
    n.fact("agreement", f"{caught['agreed']:,} of {caught['total']:,}")
    for example in caught["counterexamples"][:2]:
        where = ", ".join(f"{k}={v:,.4g}" for k, v in example.items() if not k.startswith("_"))
        n.say(
            f"  at {where}: specification {example['_expected']:,.2f}, "
            f"code {example['_actual']:,.2f}"
        )
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting a version whose code contradicts its own mathematics", exc)

    n.step("Putting the correct code back: a clean result belonged to different code")
    upload(cast, maya, DESK_CODE)
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting code that has not been tested since it changed", exc)
    again = test(cast)
    n.fact("agreement, re-run", f"{again['agreed']:,} of {again['total']:,}")

    n.step("Submitting, and approving")
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve")
    n.fact(
        "model", f"{NS}/{MODEL} v1, {cast.mgr.models.get(f'{NS}/{MODEL}')['versions'][0]['state']}"
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
