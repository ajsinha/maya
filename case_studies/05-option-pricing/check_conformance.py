"""
Step 4 — is the desk's pricer the same thing as the mathematics that was approved?

    .venv/bin/python case_studies/05-option-pricing/check_conformance.py

The desk's pricer is uploaded and MAYA runs the six-rung ladder on it: parse and lint, entry
point and signature, import allowlist, a static ban on filesystem, process, network and
dynamic-code use, a smoke run in the sandbox, and a determinism probe. Every rung is
reported.

And with the ladder, not as a separate act somebody has to remember, the **differential
test**: MAYA compares the pricer against its own evaluation of the documented mathematics.
The step re-runs it on the domain that matters — quotes resampled from the pinned chain
rather than numbers near 1 — and then does the same for the pricer with one plausible
mistake in it:

    d2 = d1 - sigma * T      instead of      d2 = d1 - sigma * sqrt(T)

which is exactly right at one year and wrong at every other maturity. That is the bug worth
demonstrating, because the desk quotes the 1Y pillar first, and a test written there passes
— as this step shows, by running the comparison on the pillar and watching it agree.

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
    PILLAR_REF,
    PIN_REF,
    SAMPLE,
    SIGMAS,
    Cast,
)

TITLE = "Case study 5, step 4 — the pricer against the mathematics"
POINTS = 2000
SMOKE = {name: 0.25 for name in SIGMAS}


def upload(cast: Cast, maya: Any, source: str) -> dict[str, Any]:
    cast.mona.models.upload_artifact(f"{NS}/{MODEL}", source, sample=SAMPLE, params=SMOKE)
    maya.drain()  # the ladder runs as a job
    return dict(cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["artifact_report"] or {})


def test(cast: Cast, domain: str = PIN_REF) -> dict[str, Any]:
    return dict(cast.mona.models.conformance(f"{NS}/{MODEL}", 1, n=POINTS, featureset=domain))


def where(example: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v:,.4g}" for k, v in example.items() if not k.startswith("_"))


def plant_the_bug(cast: Cast, maya: Any, n: Narrator) -> None:
    """Upload the pricer with sigma*T in it, and follow what MAYA does about it."""
    from maya.core.errors import NotApproved

    n.step("The same pricer with sigma*T where the mathematics says sigma*sqrt(T)")
    caught = upload(cast, maya, BUGGY_CODE)["conformance"]
    n.fact("ladder", "passed=True — it is valid, running, deterministic Python")
    n.fact("agreement over the unit interval", f"{caught['agreed']:,} of {caught['total']:,}")

    n.step("The same buggy pricer, tested on the 1Y pillar alone")
    n.say("Where T = 1, sigma*T and sigma*sqrt(T) are the same number:")
    pillar = test(cast, PILLAR_REF)
    n.fact("domain", pillar["domain"])
    n.fact("agreement", f"{pillar['agreed']:,} of {pillar['total']:,}")
    n.say("That is the unit test the desk would have written, passing on broken code.")

    n.step("And on that evidence MAYA lets it through")
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    n.fact("state", cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["state"])
    n.say("The gate asks whether the last comparison against *this* artifact agreed")
    n.say("everywhere it looked. It did — on a quarter of the chain. A check is only as")
    n.say("good as the domain it explored, which is why MAYA records the domain, and why")
    n.say("the reviewer's job is to read it. Here she does, and sends it back.")
    cast.mgr.models.transition(
        f"{NS}/{MODEL}",
        1,
        "request_changes",
        rationale="conformance was run on the 1Y pillar only; re-run it on the whole chain",
    )
    n.fact("state", cast.mgr.models.get(f"{NS}/{MODEL}")["versions"][0]["state"])

    n.step("Re-run on the whole chain, and the same submission is refused")
    on_the_chain = test(cast)
    n.fact("domain", on_the_chain["domain"])
    n.fact("agreement on the chain", f"{on_the_chain['agreed']:,} of {on_the_chain['total']:,}")
    for example in on_the_chain["counterexamples"][:3]:
        n.say(
            f"  at {where(example)}: specification {example['_expected']:,.2f}, "
            f"code {example['_actual']:,.2f}"
        )
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting a version whose code contradicts its own mathematics", exc)


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Uploading the desk's pricer: the ladder, and the comparison with it")
    report = upload(cast, maya, DESK_CODE)
    n.fact("ladder", f"passed={report.get('passed')}, sandbox tier '{report.get('tier')}'")
    for rung in report.get("rungs", []):
        n.say(f"  {rung['rung']}. {rung['name']}: {rung['detail']}")
    got = report["conformance"]
    n.fact("comparison", f"{got['agreed']:,} of {got['total']:,} agree")
    n.fact("domain", got["domain"])

    n.step("Re-running it on the chain the desk will actually price")
    n.say("Numbers near 1 do not test an option: a strike of 1.2 against a spot of 0.6 at a")
    n.say("volatility of 90% is not a contract, and a maturity bug hides where T is near 1.")
    checked = test(cast)
    n.fact("domain", checked["domain"])
    n.fact("agreement", f"{checked['agreed']:,} of {checked['total']:,}")
    n.say(checked["statement"])

    plant_the_bug(cast, maya, n)

    n.step("Putting the correct pricer back, which is tested again as it is uploaded")
    again = upload(cast, maya, DESK_CODE)["conformance"]
    n.fact("on upload", f"{again['agreed']:,} of {again['total']:,} over the unit interval")
    n.say("A clean result is never inherited: it belongs to the code it was run on. And the")
    n.say("evidence kept on the version should be the evidence worth having, so the last")
    n.say("word is the chain again:")
    final = test(cast)
    n.fact("agreement", f"{final['agreed']:,} of {final['total']:,}")
    n.fact("domain", final["domain"])
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
