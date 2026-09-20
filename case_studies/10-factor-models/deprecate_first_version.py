"""
Step 8 — the maturity ladder: version 1 is deprecated, and then somebody tries to retire it.

    .venv/bin/python case_studies/10-factor-models/deprecate_first_version.py

§8.6 gives a model version a maturity — ``experimental``, ``candidate``, ``approved``,
``restricted``, ``deprecated``, ``retired`` — and says two things about deprecation:
it *requires* a successor reference or an explicit statement that none exists, and MAYA
*warns every owner of a warrant that depends on it*. This step exercises both, and then
pushes one step further than the specification goes.

What happens, in order:

* deprecating version 1 with neither a successor nor a rationale is **refused**, quoting
  §8.6;
* deprecating it with version 2 named as its successor moves it, records the successor on
  the version, and puts a notification in the inbox of everyone who owns a warrant drawn
  on it — devi, who owns both training warrants, and mgr, who owns the execution warrant;
* a new training warrant on the deprecated version is **refused**: warrants are drawn on
  approved model versions;
* the execution warrant already sealed on version 1 keeps serving, which is the right
  answer — deprecation is a statement about what may be *started*, not a revocation of
  what is already licensed;
* and then an administrator retires version 1 while that warrant is still live. What MAYA
  does about that is printed rather than described here, because it is a finding and the
  study reports findings rather than expectations.

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
    EXTRA_USERS,
    LIVE_V1,
    MODEL,
    MODEL_V1,
    NS,
    PIN_REF,
    SUCCESSOR,
    TARGET,
    Cast,
    find_execution_warrant,
    version,
)

TITLE = "Case study 10, step 8 — deprecating version 1, and trying to retire it"
REF = f"{NS}/{MODEL}"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    deprecate(maya, cast, n)
    then_retire(cast, n)


def deprecate(maya: Any, cast: Cast, n: Narrator) -> None:
    """§8.6's two requirements — a successor, and a warning to every dependent warrant."""
    from maya.core.errors import NotApproved, ValidationFailed

    n.step("Deprecation without a successor, and without a word about why")
    try:
        cast.mgr.models.transition(REF, 1, "deprecate")
    except ValidationFailed as exc:
        n.refused("deprecating version 1 while saying nothing about what replaces it", exc)

    n.step("Deprecating it properly, naming version 2 as the successor")
    cast.mgr.models.transition(
        REF,
        1,
        "deprecate",
        successor=SUCCESSOR,
        rationale=(
            "Superseded by version 2, which adds the four published factors that version "
            "1's alpha was absorbing. Version 1's attribution is not wrong, it is "
            "incomplete, and the incompleteness reads as skill."
        ),
    )
    v1 = version(cast.mgr, REF, 1)
    v2 = version(cast.mgr, REF, 2)
    n.fact("version 1 state", v1["state"])
    n.fact("version 1 maturity", v1["maturity"])
    n.fact("successor recorded on the version", v1["successor_ref"])
    n.fact("version 2", f"{v2['state']}, maturity {v2['maturity']}")

    n.step("Who MAYA told, without being asked to")
    for who in ("devi", "mgr", "mona"):
        notices = [
            row
            for row in maya.client(who).access.inbox()
            if row.get("kind") == "deprecation" and MODEL in str(row.get("object_ref", ""))
        ]
        n.fact(f"{who}'s inbox", f"{len(notices)} deprecation notice(s)")
        for row in notices:
            n.say(f"  {row['message']}")
    n.say("devi owns the two training warrants; mgr owns the execution warrant serving")
    n.say("version 1. mona wrote the model and hears nothing, because she does not hold a")
    n.say("warrant — §8.6 warns warrant owners, which is who has something to stop doing.")

    n.step("A deprecated version cannot be drawn on again")
    try:
        cast.devi.training.create(
            NS, "capm_refit_2025", MODEL_V1, PIN_REF, spec={"target": TARGET, "seed": 7}
        )
    except NotApproved as exc:
        n.refused("drawing a fresh training warrant on the deprecated version", exc)

    n.step("But what was already licensed keeps running")
    live = find_execution_warrant(cast.mgr, LIVE_V1)
    n.fact(
        f"{LIVE_V1}",
        f"{cast.devi.execution.bundle(live['id'], 'uat')['status']} "
        f"(model version {live['manifest']['model']['version_no']})",
    )
    n.say("This is the right answer. Deprecation says what may be started, not what must")
    n.say("stop: the attribution that shipped last month was computed under a warrant that")
    n.say("is still sealed and still verifiable. Stopping it is what revocation is for.")


def then_retire(cast: Cast, n: Narrator) -> None:
    """The last rung, taken while a sealed execution warrant is still serving the version."""
    from maya.core.errors import MayaError, NotApproved, ValidationFailed

    live = find_execution_warrant(cast.mgr, LIVE_V1)
    n.step("And now an administrator retires it, while that warrant is still live")
    try:
        cast.admin.models.transition(
            REF, 1, "retire", rationale="closing out the 2023-24 attribution vintage"
        )
        n.fact("MAYA allowed the retirement", True)
    except (NotApproved, ValidationFailed, MayaError) as exc:
        n.refused("retiring a model version a live execution warrant depends on", exc)
    n.say(
        "Retirement is an administrative end of life, not an outage. Left unguarded it was "
        "neither: this study's first run retired the version and the warrant went on serving "
        "it, so production ran a retired model and nothing said so. Taking a model out of "
        "service now is revocation, and MAYA makes the two happen in that order."
    )

    n.step("Revoke first, then retire")
    cast.admin.execution.revoke(
        live["id"], "the 2023-24 attribution vintage is closed; version 2 has superseded it"
    )
    n.fact("capm_attribution", cast.mgr.execution.get(live["id"])["status"])
    cast.admin.models.transition(
        REF, 1, "retire", rationale="closing out the 2023-24 attribution vintage"
    )
    retired = version(cast.admin, REF, 1)
    n.fact("version 1 state", retired["state"])
    n.fact("version 1 maturity", retired["maturity"])
    n.fact(
        "the ladder version 1 walked",
        "experimental → candidate (on approval) → deprecated → retired",
    )

    n.step("What retirement did not do, which is the point of it")
    warrants = [w for w in cast.devi.training.list() if w["name"].startswith("capm")]
    for w in warrants:
        got = cast.devi.training.get(w["id"])
        n.fact(got["name"], f"{got['state']}, sealed_at {str(got['sealed_at'])[:19]}")
    n.say(
        "Sealed warrants on a retired version stay valid and stay reproducible: withdrawing "
        "them would destroy the reproducibility the seal exists to guarantee. What retirement "
        "does is tell the people who own them."
    )
    told = [
        note
        for note in cast.devi.access.inbox()
        if (note["object_ref"] or "").endswith("equity_factor_model@v1")
    ]
    n.fact("devi's notices about version 1", [note["kind"] for note in told])
    n.say(
        "Both of them, and the retirement notice is there because of this study: retirement "
        "used to warn nobody, so the owner of a sealed warrant discovered the end of its "
        "version's life by accident."
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
