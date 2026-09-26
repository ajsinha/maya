"""
Step 1 — the application, its first version, and the evaluation set it will be judged on.

    .venv/bin/python case_studies/49-llm-complaint-triage/register.py

An LLM application is registered like a model: an owner, a stated use, and versions. A
version seals the provider, the model name, the system prompt, the prompt template, the
sampling parameters and the guardrails under one definition hash; change any of them and it
is a different version. The evaluation set is its holdout: named cases, hashed as content.

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
    APP,
    EVAL_SET,
    EXTRA_USERS,
    GUARDRAILS,
    MODEL,
    NS,
    PARAMETERS,
    PROVIDER,
    REF,
    SYSTEM_V1,
    TEMPLATE,
    Cast,
    load,
)  # noqa: E402

TITLE = "Case study 49, step 1 — the application, version 1, and its evaluation set"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Registering the application, with the use it will be reviewed against")
    cast.mona.llm.create_app(
        NS, APP, "route retail banking complaints to the right team and draft a first reply"
    )
    n.fact("application", REF)

    n.step("Version 1: provider, model, prompts, parameters and guardrails, sealed together")
    v = cast.mona.llm.save_version(
        REF,
        provider=PROVIDER,
        model=MODEL,
        system_prompt=SYSTEM_V1,
        prompt_template=TEMPLATE,
        parameters=PARAMETERS,
        guardrails={**GUARDRAILS, "min_pass_rate": 1.0},
    )
    n.fact("version", f"v{v['version_no']} {v['state']}, definition {v['definition_hash'][:16]}…")
    n.fact(
        "guardrails",
        f"blocked {v['guardrails']['blocked_terms']}, at most {v['guardrails']['max_chars']} characters, personal data refused",
    )

    n.step("The evaluation set: the cases every version is judged on")
    es = cast.mona.llm.save_eval_set(
        REF, EVAL_SET, load("eval_cases"), "one complaint per team, five each, and four others"
    )
    n.fact("cases", len(es["cases"]))
    n.fact(
        "checks per case",
        "valid JSON with category and reply; the right category; under 600 characters",
    )
    n.fact("content hash", f"{es['content_hash'][:16]}…")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
