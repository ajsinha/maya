"""
Step 1 — the book and the outcomes become two governed features.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/setup_features.py

The book carries one column most credit feeds do not: the probability of default recorded
**at origination**. IFRS 9 asks whether credit risk has increased *significantly since
initial recognition*, which is a comparison against origination and not against a
threshold, so that number has to be carried for the life of the account or the standard
cannot be applied at all.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import DESCRIPTIONS, DEFINITIONS, EXTRA_USERS, FEEDS, NEWLINE, NS, Cast, feed  # noqa: E402

TITLE = "Case study 6, step 1 — the book, and what happened next"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Reading both feeds from data/")
    raw = {name: feed(name) for name in FEEDS}
    for name, body in raw.items():
        n.fact(name, f"{body.count(NEWLINE) - 1:,} rows, {len(body) / 1e6:.2f} MB")
    book = pd.read_csv(io.BytesIO(raw["exposures"]))
    out = pd.read_csv(io.BytesIO(raw["outcomes"]))
    n.fact("accounts", f"{book['account'].nunique():,}")
    n.fact("committed / drawn", f"{book['commitment'].sum():,.0f} / {book['drawn'].sum():,.0f}")
    n.fact("twelve-month default rate", f"{out['defaulted12'].mean():.2%}")
    defaulted = out[out["defaulted12"] == 1]
    n.fact("mean loss rate given default", f"{defaulted['loss_rate'].mean():.1%}")
    n.fact("realised loss, total", f"{out['realised_loss12'].sum():,.0f}")
    n.fact("rows with no loss at all", f"{(out['realised_loss12'] == 0).mean():.1%}")
    n.say("That last figure is why §7 argues about what a per-account error can mean here.")

    n.step("Defining each one, and approving it as somebody other than its author")
    for name in FEEDS:
        cast.dana.features.create(NS, name, DEFINITIONS[name], description=DESCRIPTIONS[name])
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
        got = cast.mick.features.get(f"{NS}/{name}")["versions"][0]
        n.fact(name, f"v1 {got['state']}, {len(DEFINITIONS[name]['quality'])} quality check(s)")
    n.say(
        "One of those checks is that the origination probability lies inside (0, 1]: the "
        "stage test divides by it, so a zero there is not a safe account but a broken record."
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
