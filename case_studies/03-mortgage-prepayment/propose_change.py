"""
Step 7 — somebody proposes changing a feature under a live model, and MAYA prices it.

    .venv/bin/python case_studies/03-mortgage-prepayment/propose_change.py

This is the step the other case studies do not have, and it is the one that matters most
in practice. A model gets approved once. Its *features* get changed for years afterwards,
usually by somebody who has never met the model, and each change quietly moves every
forecast downstream of it.

Here the desk proposes something entirely reasonable: the published survey rate jumps a few
basis points a month on nothing, so smooth it with a three-month trailing mean. The argument
is sound in the abstract. The question MAYA makes answerable is the one that actually
matters — *how far does that move this book's prepayment forecast, and for which models?*

So the change is staged on a **workspace**: a copy-on-write branch of the catalog where a
definition can be edited and resolved against without touching anything in production.
MAYA then lists what is downstream of it, **replays every affected execution warrant twice**
— once against the current definition, once against the proposed one — and reports the
distribution of the difference per model. Approval becomes a merge of something whose
consequences are on the screen.

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
    CHANGE_NOTE,
    EXTRA_USERS,
    NS,
    SMOOTHED_RATE_DEF,
    WORKSPACE,
    Cast,
    find_workspace,
)

TITLE = "Case study 3, step 7 — a proposed change, replayed before it lands"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    existing = find_workspace(cast.devi, WORKSPACE)
    if existing is not None:
        n.say(f"workspace '{WORKSPACE}' already exists; using it")
        workspace = existing
    else:
        n.step("Opening a workspace: a branch of the catalog, nothing copied until written")
        workspace = cast.devi.workspaces.create(WORKSPACE, CHANGE_NOTE)
        n.fact("workspace", f"{workspace['name']} ({workspace['state']})")

    n.step("Staging the change: the survey rate, smoothed over three months")
    n.say(f"transform: {SMOOTHED_RATE_DEF['transform']}")
    staged = cast.devi.workspaces.stage(
        workspace["id"],
        kind="feature",
        ref=f"{NS}/mortgage_rate",
        definition=SMOOTHED_RATE_DEF,
        note=CHANGE_NOTE,
    )
    n.fact("staged against", f"base version v{staged['base_version_no']}")
    n.say("Nothing in production has changed. The approved feature is still v1.")

    n.step("What is downstream of it")
    impact = cast.devi.workspaces.impact(workspace["id"])
    for row in impact["downstream"]:
        n.say(f"{row['kind']:<18} {row['ref']}")
    n.fact("execution warrants affected", len(impact["warrants"]))

    n.step("Replaying every affected warrant, twice, and measuring the difference")
    job = cast.devi.workspaces.shadow_replay(workspace["id"])
    maya.drain()
    state = cast.devi.jobs.get(job["id"])
    if state["state"] != "succeeded":
        raise MayaError(f"replay {state['state']}: {state.get('error')}")
    n.fact("warrants replayed", state["result"]["warrants"])
    n.fact("warrants that moved", state["result"]["moved"])

    n.step("The report, which is kept on the workspace for the reviewer")
    report = cast.devi.workspaces.get(workspace["id"])["replay"]
    n.fact("summary", report["summary"])
    n.fact("sampled rows per warrant", report["sample_rows"])
    n.fact("coverage", report["coverage"])
    n.fact("compute budget", report["budget"])
    for entry in report["warrants"]:
        if not entry.get("replayed"):
            n.say(f"{entry['warrant']}: not replayed — {entry.get('reason')}")
            continue
        n.say(f"{entry['warrant']}")
        n.say(
            f"  monthly hazard moves: median |Δ| {entry['median_abs_shift']:.5f}, "
            f"95th {entry['p95_abs_shift']:.5f}, worst {entry['max_abs_shift']:.5f}"
        )
        n.say(
            f"  {entry['rows_over_materiality']:,} of {entry['rows_compared']:,} rows "
            f"({entry['share_over_materiality']:.1%}) move more than "
            f"{entry['materiality']:.4g}, which is the {entry['materiality_from']} threshold"
        )
        n.say(f"  worst row: {entry['worst_row']}")
    n.say(report["basis"])

    n.step("What remains true afterwards")
    n.fact("workspace state", cast.devi.workspaces.get(workspace["id"])["state"])
    live = cast.devi.features.get(f"{NS}/mortgage_rate")
    n.fact(
        "the approved feature",
        f"v{live['versions'][0]['version_no']} {live['versions'][0]['state']}",
    )
    n.say(
        "The proposal now carries its own consequences. Whoever approves it is approving a "
        "number, not a sentence about smoothing."
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
