"""
Step 3 — the network, registered as what it is: a declared black box with a code artifact.

    .venv/bin/python case_studies/07-neural-network/setup_model.py

Case studies 1 and 2 hand MAYA a formula and MAYA parses it into an expression tree. There
is no formula here. What MAYA gets instead is a **declared black-box node** — the
architecture, the hyperparameters, the seed, and a mandatory prose statement of what the
model estimates — plus the two things that are exact even when the mathematics is not: the
input contract, and the code.

Three refusals, in order:

* an IR with no ``body`` and no ``black_box`` node is refused — MAYA will not hold a model
  whose mathematics is merely absent; opacity has to be *declared*;
* a black-box node with a blank ``estimates`` is refused by name;
* the code artifact that loads its weights from a file fails the ladder's static ban, and
  the version cannot be submitted. That refusal is the reason a network's weights have to
  be a parameter set: the ordinary way to carry them is a file the code opens, and MAYA's
  sandbox does not let code open anything.

Then the ladder on the real artifact, and the comparison MAYA will *not* do for a black
box — the differential test against a closed form there is none of — which the desk
therefore has to do itself, by hand, against the sandbox's own output.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import network  # noqa: E402
from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    DESCRIPTIONS,
    EXTRA_USERS,
    HYPERPARAMETERS,
    LOADS_FROM_DISK,
    MODEL,
    NS,
    SAMPLE,
    SEED,
    Cast,
    artifact_source,
    model_ir,
    specification,
)

TITLE = "Case study 7, step 3 — a declared black box, and the ladder on its code"


def ladder(cast: Cast, maya: Any, source: str, params: dict[str, Any]) -> dict[str, Any]:
    """Upload an artifact and run the six-rung ladder, which MAYA does as a job."""
    cast.mona.models.upload_artifact(f"{NS}/{MODEL}", source, sample=SAMPLE, params=params)
    maya.drain()
    return dict(cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["artifact_report"] or {})


def register(cast: Cast, n: Narrator) -> None:
    """The model version: the black-box node, the two refusals, and the document."""
    from maya.core.errors import NotApproved, ValidationFailed

    n.step("Registering the network as a declared black box")
    cast.mona.models.create(
        NS, MODEL, kind="black_box", ir=model_ir(), description=DESCRIPTIONS[MODEL]
    )
    version = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("kind", cast.mona.models.get(f"{NS}/{MODEL}")["kind"])
    n.fact("opaque", version["opaque"])
    n.fact("input contract", ", ".join(c["name"] for c in version["input_contract"]))
    n.fact(
        "parameters to be fitted",
        ", ".join(
            i["name"] for i in version["formula_ir"]["inputs"] if i.get("role") == "parameter"
        ),
    )
    n.fact("fitted values", HYPERPARAMETERS["fitted_values"])
    n.fact("rendered mathematics", f"'{version['latex']}'  (there is none)")
    n.say("The contract is exact and the parameters are named, neither of which needs MAYA")
    n.say("to understand the network. What it cannot state is what the network computes.")

    n.step("MAYA will not hold a model whose mathematics is simply missing")
    try:
        cast.mona.models.update_draft(
            f"{NS}/{MODEL}", ir={k: v for k, v in model_ir().items() if k != "black_box"}
        )
    except ValidationFailed as exc:
        n.refused("an IR with neither a body nor a declared black box", exc)
    try:
        cast.mona.models.update_draft(f"{NS}/{MODEL}", ir=model_ir(estimates="  "))
    except ValidationFailed as exc:
        n.refused("a black box that does not say what it estimates", exc)

    n.step("And it cannot be submitted with an empty specification")
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting before the document is complete", exc)
    cast.mona.models.update_draft(f"{NS}/{MODEL}", spec_latex=specification())
    filled = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact(
        "sections present",
        f"{sum(1 for s in filled['completeness'] if s['present'] and not s['empty'])}"
        f" of {len(filled['completeness'])}",
    )
    n.say("For a black box the Mathematical Formulation section is where the architecture,")
    n.say("the loss, the optimiser, the seed and the stopping rule are declared in writing.")


def code(cast: Cast, maya: Any, n: Narrator) -> None:
    """The artifact: the ladder, the refusal, and the comparison MAYA will not make."""
    from maya.core.errors import NotApproved

    n.step("The obvious implementation: weights loaded from a file. The ladder refuses it")
    report = ladder(cast, maya, LOADS_FROM_DISK, {})
    for rung in report.get("rungs", []):
        mark = {True: "pass", False: "FAIL", None: "not run"}[rung["passed"]]
        n.say(f"  {rung['rung']}. {rung['name']}: {mark} — {rung['detail']}")
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting a version whose artifact failed the ladder", exc)
    n.say("This is why the weights are a parameter set and not a file: MAYA's sandbox has no")
    n.say("filesystem to load them from, so they have to arrive as approved values.")

    n.step("The desk's implementation: network.py, uploaded as bytes")
    source = artifact_source()
    initial = network.initial_parameters(SEED)
    report = ladder(cast, maya, source, {k: v.tolist() for k, v in initial.items()})
    n.fact("ladder", f"passed={report.get('passed')}, sandbox tier '{report.get('tier')}'")
    for rung in report.get("rungs", []):
        mark = {True: "pass", False: "FAIL", None: "not run"}[rung["passed"]]
        n.say(f"  {rung['rung']}. {rung['name']}: {mark} — {rung['detail']}")
    n.fact("deterministic", report.get("deterministic"))
    n.fact("artifact hash", f"{report['artifact_hash'][:16]}…")
    n.fact(
        "sha256 of network.py on disk",
        f"{hashlib.sha256(source.encode()).hexdigest()[:16]}… — the same file the desk fits with",
    )

    n.step("The comparison MAYA does for a formula, and cannot do for this")
    n.fact("conformance in the ladder's report", report.get("conformance", "absent"))
    n.fact("asking for it explicitly", cast.mona.models.conformance(f"{NS}/{MODEL}", 1))
    n.say("Case study 2's differential test compares the code against the documented")
    n.say("mathematics. There is no documented mathematics, so the test is skipped by name.")
    n.say("What is left is a comparison the desk must run itself: MAYA ran the artifact in")
    n.say("its sandbox on the declared sample, and the desk checks that output against its")
    n.say("own forward pass of the same file with the same weights.")
    mine = network.Model().predict(SAMPLE, initial, None)
    theirs = np.asarray(report["smoke_output"], dtype=float)
    n.fact("sandbox output, first three", np.round(theirs[:3], 6).tolist())
    n.fact("desk's own forward pass", np.round(mine[:3], 6).tolist())
    n.fact("largest absolute difference", f"{float(np.abs(mine - theirs).max()):.2e}")
    n.say("Nothing in MAYA required that check. Nobody would have noticed if it had failed.")

    n.step("Submitting, and approving")
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve")
    shown = cast.mgr.models.get(f"{NS}/{MODEL}")
    n.fact("model", f"{NS}/{MODEL} v1, {shown['versions'][0]['state']}")
    n.fact("as the catalog lists it", f"opaque={cast.mgr.models.list(q=MODEL)[0]['opaque']}")


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    register(cast, n)
    code(cast, maya, n)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
