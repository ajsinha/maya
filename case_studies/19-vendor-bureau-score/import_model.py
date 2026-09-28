"""
Step 2 — the vendor's model, imported from MLflow, its code validated in the sandbox.

    .venv/bin/python case_studies/19-vendor-bureau-score/import_model.py

The vendor delivered an MLflow model: an ``MLmodel`` file and the scoring code. The import
reads the signature, so the input contract is what the vendor declared rather than what
somebody typed, and seals the MLflow provenance -- run, model id, flavours -- into the
version. The code then goes through the validation ladder: parsed, its imports checked
against an allowlist, statically searched for file, network and process use, and run twice
in the sandbox to see it is deterministic.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import EXTRA_USERS, MODEL, NS, VENDOR, Cast, spec_document  # noqa: E402

TITLE = "Case study 19, step 2 — imported from MLflow, validated in the sandbox"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    ref = f"{NS}/{MODEL}"
    n.step("Importing the MLflow model")
    model = cast.mona.integrations.import_mlflow(
        NS,
        MODEL,
        (VENDOR / "MLmodel").read_text(),
        "the probability that an applicant defaults within twelve months",
        "BureauScore 4.1, bought from a credit bureau",
    )
    prov = model["imported_from"]
    n.fact("kind", model["kind"])
    n.fact("input contract, from the signature", ", ".join(i["name"] for i in prov["inputs"]))
    n.fact("MLflow run", prov["run_id"])
    n.fact("flavours", ", ".join(prov["flavors"]))

    n.step("The vendor's code through the validation ladder")
    cast.mona.models.upload_artifact(ref, (VENDOR / "vendor_bureau_credit_score.py").read_text())
    maya.drain()
    report = cast.mona.models.get(ref)["versions"][0]["artifact_report"]
    for rung in report["rungs"]:
        n.say(
            f"rung {rung['rung']} {rung['name']}: {'passed' if rung['passed'] else rung['passed']} — {rung['detail']}"
        )
    n.fact("sandbox tier", report["tier"])

    n.step("Its document, then review")
    cast.mona.models.update_draft(ref, spec_latex=spec_document())
    cast.mona.models.transition(ref, 1, "submit")
    cast.mgr.models.transition(ref, 1, "approve", rationale="vendor documentation reviewed")
    n.fact("version 1", "approved by mgr")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
