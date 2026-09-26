"""
Step 1 — ten years of mortality experience, pinned, and the law approved as mathematics.

    .venv/bin/python case_studies/45-gompertz-makeham-mortality/setup.py

The feed carries sex and region beside age, but the model reads only age and calendar time:
the table is unisex by law. Carrying sex in the panel anyway is what will let the validator
measure what leaving it out costs.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (
    AS_OF,
    EXTRA_USERS,
    FEATURE_DEF,
    FEED,
    FORMULA,
    MODEL,
    NS,
    PANEL,
    PANEL_DEF,
    PIN,
    ROLES,
    Cast,
    feed,
    spec_document,
)  # noqa: E402

TITLE = "Case study 45, step 1 — experience pinned, the law approved"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The experience feed, governed and pinned")
    cast.dana.features.create(NS, FEED, FEATURE_DEF)
    got = cast.dana.features.ingest(f"{NS}/{FEED}", feed(), fmt="csv", filename=f"{FEED}.csv")
    cast.dana.features.transition(f"{NS}/{FEED}", 1, "submit")
    cast.mick.features.transition(f"{NS}/{FEED}", 1, "approve")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF)
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    cast.mick.featuresets.pin(f"{NS}/{PANEL}", 1, PIN, AS_OF.isoformat(), cascade=True)
    maya.drain()
    n.fact("cells ingested", f"{got['rows']:,} (10 years × 56 ages × 2 sexes × 3 regions)")

    n.step("The Gompertz–Makeham law with improvement")
    cast.mona.models.create(
        NS,
        MODEL,
        formula=FORMULA,
        roles=ROLES,
        description="Unisex central death rates by age and year",
    )
    cast.mona.models.update_draft(f"{NS}/{MODEL}", spec_latex=spec_document())
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve")
    v = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("inputs", ", ".join(c["name"] for c in v["input_contract"]))
    n.fact("parameters", "A, B, gamma, lambda")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
