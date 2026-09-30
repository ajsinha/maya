"""
What the steps of this case study share: the application's name, its two versions, the
guardrails, and the people who act.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NS = "complaints"
DATA = Path(__file__).resolve().parent / "data"
APP = "complaint_triage"
REF = f"{NS}/{APP}"
EVAL_SET = "core"
EXTRA_USERS: dict[str, list[str]] = {}

PROVIDER = "azure_openai"  # the firm's own deployment; this estate has no endpoint for it
MODEL = "gpt-4o-2024-08-06"
TEMPLATE = (
    "A customer wrote to us:\n\n{complaint}\n\n"
    'Answer with JSON only: {{"category": one of billing, fraud, mortgage, access, other, '
    '"reply": a first reply to the customer of at most three sentences}}.'
)
SYSTEM_V1 = "You triage complaints for a retail bank and draft a courteous first reply."
SYSTEM_V2 = SYSTEM_V1 + (
    " Never repeat an account number, card number or phone number. Never promise a refund, "
    "compensation or any outcome: say which team will look into it and when."
)
PARAMETERS = {"temperature": 0, "max_tokens": 300}
GUARDRAILS = {"blocked_terms": ["guarantee", "compensation of"], "max_chars": 600, "pii": True}


def load(name: str) -> Any:
    path = DATA / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"{path} is missing. Write it with make_data.py in this folder.")
    return json.loads(path.read_text())


class Cast:
    """The people, each with their own roles and their own SDK client."""

    def __init__(self, maya: Any) -> None:
        for name in ("mona", "devi", "mgr", "admin"):
            setattr(self, name, maya.client(name))
