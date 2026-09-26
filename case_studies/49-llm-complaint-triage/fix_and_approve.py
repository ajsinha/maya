"""
Step 3 — the fix, a changed evaluation set, approval, and a change after approval.

    .venv/bin/python case_studies/49-llm-complaint-triage/fix_and_approve.py

Version 1 was never submitted, so it is still a draft and the owner may edit it: the system
prompt now forbids repeating numbers and promising outcomes. Editing changes the version's
definition hash, so the failing run no longer describes it; the new answers pass. Then the
validator adds a case -- a complaint in Welsh -- and that evidence stops counting too,
because it was gathered on a set that no longer exists. Scored again on the set as it now
stands, the version is submitted and approved by a model manager who neither owns it nor
submitted it. Finally the owner changes one parameter: an approved definition never changes,
so that opens version 2, and version 1 stays the approved one until 2 is judged.

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
    EVAL_SET,
    EXTRA_USERS,
    GUARDRAILS,
    MODEL,
    NS,
    PARAMETERS,
    PROVIDER,
    REF,
    SYSTEM_V2,
    TEMPLATE,
    Cast,
    load,
)  # noqa: E402

TITLE = "Case study 49, step 3 — the fix, a changed set, approval, and version 2"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved, PermissionDenied

    cast = Cast(maya)
    n.step("Fixing the draft: a system prompt that forbids what failed")
    before = cast.mona.llm.app(REF)["versions"][0]["definition_hash"]
    v1 = cast.mona.llm.save_version(
        REF,
        provider=PROVIDER,
        model=MODEL,
        system_prompt=SYSTEM_V2,
        prompt_template=TEMPLATE,
        parameters=PARAMETERS,
        guardrails={**GUARDRAILS, "min_pass_rate": 1.0},
    )
    n.fact("still", f"v{v1['version_no']}, a draft")
    n.fact("definition hash", f"{before[:16]}… → {v1['definition_hash'][:16]}…")
    n.say("The failing run was on the old definition, so it no longer describes this version.")
    run = cast.devi.llm.run_eval(REF, 1, EVAL_SET, responses=load("answers_v2"))
    n.fact(
        "cases passed",
        f"{run['passed']} of {run['cases']}, {run['guardrail_violations']} guardrail violations",
    )

    n.step("The validator adds a case, and the evidence stops counting")
    cases = load("eval_cases") + [load("extra_case")]
    es = cast.mgr.llm.save_eval_set(REF, EVAL_SET, cases, "plus a complaint in Welsh")
    n.fact("cases now", f"{len(es['cases'])}, content hash {es['content_hash'][:16]}…")
    try:
        cast.mona.llm.submit(REF, 1)
    except NotApproved as exc:
        n.refused("submitting on evidence from a set that has since changed", exc)
    run = cast.devi.llm.run_eval(REF, 1, EVAL_SET, responses=load("answers_v2_with_extra"))
    n.fact("scored again", f"{run['passed']} of {run['cases']}")

    n.step("Submission and an independent decision")
    cast.mona.llm.submit(REF, 1)
    try:
        cast.mona.llm.decide(REF, 1, "approve", "looks good to me")
    except PermissionDenied as exc:
        n.refused("the owner approving her own application", exc)
    done = cast.mgr.llm.decide(
        REF, 1, "approve", "25 of 25 cases, no guardrail violation, Welsh handled"
    )
    n.fact("version 1", f"{done['state']} by {done['decided_by']}")

    n.step("A change after approval opens a new version")
    v2 = cast.mona.llm.save_version(
        REF,
        provider=PROVIDER,
        model=MODEL,
        system_prompt=SYSTEM_V2,
        prompt_template=TEMPLATE,
        parameters={**PARAMETERS, "max_tokens": 200},
        guardrails={**GUARDRAILS, "min_pass_rate": 1.0},
    )
    states = {v["version_no"]: v["state"] for v in cast.mgr.llm.app(REF)["versions"]}
    n.fact("versions", ", ".join(f"v{k} {v}" for k, v in sorted(states.items())))
    n.say(f"v{v2['version_no']} must earn its own evidence; v1 answers in production until then.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
