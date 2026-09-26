"""
Step 4 — the application in the model inventory, beside the models.

    .venv/bin/python case_studies/49-llm-complaint-triage/inventory.py

Supervisors expect AI applications in the same inventory as models. It appears there with
its provider and model, its state and its evaluation evidence -- and with the model-only
columns (tier, findings, periodic review) left blank rather than invented.

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
from study import APP, EXTRA_USERS, NS, Cast  # noqa: E402

TITLE = "Case study 49, step 4 — in the inventory"


def main(maya: Any, n: Narrator) -> None:
    import json

    cast = Cast(maya)
    n.step("The SS1/23 inventory, as JSON")
    doc = json.loads(cast.mgr.governance.inventory(format="json", framework="ss1-23")["data"])
    row = next(r for r in doc["rows"] if r["name"] == APP)
    for key in (
        "model_ref",
        "kind",
        "vendor",
        "status",
        "current_version",
        "approved_by",
        "implementation_tested",
        "tier",
    ):
        n.fact(
            doc["columns"][key], row[key] if row[key] not in (None, "") else "— (not a model field)"
        )
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
