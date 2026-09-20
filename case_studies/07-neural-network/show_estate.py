"""
Step 7 — what the estate holds now, and what it admits it cannot say.

    .venv/bin/python case_studies/07-neural-network/show_estate.py

Nothing is created here except a reproducibility bundle, and that is the point of the step.
Everything the previous six did is discoverable afterwards by somebody who was not in the
room — the catalog with the model flagged opaque, the hash-chained audit log, the warrant's
chain of custody, the lineage graph — and the bundle is where MAYA states, in writing, the
one thing it cannot do: re-execute this model to check the outputs. It carries the code and
the 209 weights and hashes both, and then says the re-execution check was **not run** and
why, rather than leaving a green tick to be misread.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, browse_hint, step_script  # noqa: E402
from study import EXTRA_USERS, LIVE, MODEL, NS, PANEL, WARRANT, Cast, find_warrant  # noqa: E402

TITLE = "Case study 7, step 7 — the estate, and what it says it cannot verify"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The catalog, as the feature manager sees it")
    for kind in ("feature", "featureset", "model"):
        rows = cast.mick.catalog.browse(type=kind)
        n.fact(f"{kind}s", f"{len(rows)}: " + ", ".join(r.get("name", "?") for r in rows))
    n.fact("model risk reporting", f"{MODEL} opaque={cast.mgr.models.list(q=MODEL)[0]['opaque']}")

    n.step("The audit log: append-only, each entry carrying the hash of the last")
    chain = cast.admin.admin.verify_audit()
    n.fact("entries", f"{chain['checked']:,}")
    n.fact("chain unbroken", chain["ok"])

    n.step("The training warrant's chain of custody")
    warrant = find_warrant(cast.mgr, WARRANT)
    for event in warrant["custody"]:
        n.say(f"{event['event']} — {event.get('actor', '')}")

    n.step("Lineage: what fed what")
    graph = cast.mgr.access.lineage(f"maya://featureset/{NS}/{PANEL}@v1")
    n.fact("nodes", len(graph["nodes"]))
    n.fact("edges", len(graph["edges"]))
    for edge in graph["edges"]:
        label = f" ({edge['label']})" if edge.get("label") else ""
        n.say(f"{edge['source']}  --{edge['type']}{label}-->  {edge['target']}")

    n.step("The reproducibility bundle, and the check it refuses to claim")
    exported = cast.devi.training.export_bundle(warrant["id"])
    manifest = exported["manifest"]
    n.fact("bundle", f"{exported['size'] / 1000:.0f} kB, {len(manifest['files'])} files")
    n.fact("files", ", ".join(sorted(manifest["files"])))
    n.fact("re-executable", manifest["reexecutable"])
    n.fact("because", manifest["not_reexecutable_reason"])
    n.fact("output hash", manifest["output_hash"])
    report = cast.admin.training.verify_bundle(cast.admin.admin.blob(exported["blob"])["data"])
    n.fact("verified", report["verified"])
    for check in report["checks"]:
        mark = {True: "ok", False: "FAILED", None: "not run"}[check["ok"]]
        n.say(
            f"{mark:8} {check['check']}" + (f" — {check['detail']}" if check.get("detail") else "")
        )
    n.say("Every hash checks, the signature checks, and the one claim a reader would most")
    n.say("like — 'these weights on these rows give these scores' — is marked not run.")

    n.step("And the live model")
    for row in [r for r in cast.mgr.execution.list() if r["name"] == LIVE]:
        n.fact(row["name"], f"{row['state']}, {row.get('status', '')}")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
