"""
How long the paths MAYA writes are allowed to get.

Windows refuses a path over 260 characters unless long paths have been enabled, and the
error it gives names the file rather than the length, so the failure reads as a corrupt
name and is diagnosed as anything but what it is. The lake is where MAYA generates its
deepest paths -- a pin table nests a partition directory naming a 64-character content hash
-- so this is where the budget is spent and where it has to be watched.

The budget below is a relative path: what MAYA adds under the lake root. Whoever deploys it
chooses the prefix, and the runbook says to keep that short and how to raise the ceiling.
What MAYA owes them is that its own contribution leaves room for a reasonable one.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

from tests.conftest import price_csv

# A Windows prefix a person would actually have: a drive, a user, a projects folder and a
# checkout. MAYA's own paths have to fit in what is left of 260 after it.
PLAUSIBLE_PREFIX = len(r"C:\Users\Alexandra\Documents\projects\maya" + "\\")
BUDGET = 260 - PLAUSIBLE_PREFIX


def test_the_lake_leaves_room_for_a_windows_prefix(world):
    """Every path the lake writes, measured from the lake root."""
    w = world
    w.p.features.create(w.dana, namespace="eq", name="px_budget", definition=_definition())
    w.p.features.ingest(w.dana, "eq/px_budget", price_csv(days=3), fmt="csv")
    w.p.features.transition(w.dana, "eq/px_budget", 1, "submit")
    w.p.features.transition(w.mick, "eq/px_budget", 1, "approve")
    w.p.features.pin(
        w.mick, "eq/px_budget", version_no=1, pin_name="budget", as_of=dt.date(2026, 2, 28)
    )
    w.drain()

    root = w.p.lake.root
    written = [p for p in root.rglob("*") if p.is_file()]
    assert written, "the pin wrote nothing, so this test is measuring an empty lake"

    longest = max(written, key=lambda p: len(str(p.relative_to(root))))
    length = len(str(longest.relative_to(root)))
    assert length <= BUDGET, (
        f"{length} characters under the lake root, over a budget of {BUDGET}: "
        f"{longest.relative_to(root)}. A Windows user with a plausible project path would "
        "be over 260 characters and the write would fail naming the file rather than the "
        "length. Shorten what MAYA generates rather than raising this number."
    )


def _definition() -> dict:
    return {
        "index": ["date", "symbol"],
        "index_types": {"date": "date", "symbol": "string"},
        "schema": [{"name": "close", "type": "float64"}],
        "source": {"type": "csv"},
        "resolution": {"grid": "as_is", "rules": {}},
        "transform": [],
        "quality": [],
    }
