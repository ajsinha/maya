"""
Step 2 — scoring version 1, and why it cannot be submitted.

    .venv/bin/python case_studies/49-llm-complaint-triage/evaluate_v1.py

The application runs on the firm's own Azure OpenAI deployment, which MAYA does not call:
asked for a live run it says so, and the answers are produced where the application runs
and submitted as a *recorded* run. Every check is deterministic and so is every guardrail.
Version 1 gets every category right -- and still fails, because two answers repeat
personal data back to the customer and one promises a refund.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import EVAL_SET, EXTRA_USERS, NS, REF, Cast, load  # noqa: E402

TITLE = "Case study 49, step 2 — version 1 scored, and refused"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved, ValidationFailed

    cast = Cast(maya)
    n.step("Asking MAYA to call the provider itself")
    try:
        cast.devi.llm.run_eval(REF, 1, EVAL_SET)
    except ValidationFailed as exc:
        n.refused("a live run against a provider MAYA does not integrate", exc)

    n.step("Scoring the answers version 1 gave, recorded by the application's harness")
    run = cast.devi.llm.run_eval(REF, 1, EVAL_SET, responses=load("answers_v1"))
    n.fact("cases passed", f"{run['passed']} of {run['cases']}")
    right = sum(all(c["passed"] for c in r["checks"]) for r in run["results"])
    n.fact("answers passing every check", f"{right} of {run['cases']}: every category is right")
    n.fact("cases with a guardrail violation", run["guardrail_violations"])
    for r in run["results"]:
        if r["guardrails"]:
            n.say(f"{r['case']}: {'; '.join(r['guardrails'])}")

    n.step("Submitting version 1")
    try:
        cast.mona.llm.submit(REF, 1)
    except NotApproved as exc:
        n.refused("submission without a clean evaluation", exc)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
