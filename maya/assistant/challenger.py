"""
The recorded challenger, through the AI gateway: any provider, any model profile.

``assistant.provider: llm`` asks the model profile ``assistant.profile`` names (empty: the
gateway's default) for the same memo ``claude`` asks Anthropic for, with the same system
prompt and the same schema. A provider that cannot enforce a schema is asked for one JSON
object in the reply and the reply is checked here: a finding whose severity or category is
not one MAYA knows is dropped, and a reply that is not JSON at all is a failure, reported on
the memo, which then holds the deterministic findings only. The model never approves,
blocks or edits anything: what it writes is a memo, attributed to the provider and model.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
import re
from typing import Any

from maya.assistant import CATEGORIES, SEVERITIES
from maya.assistant.claude import SCHEMA, SYSTEM, ChallengerUnavailable
from maya.llm.base import LlmUnavailable

MAX_TOKENS = 8000


def _json_object(text: str) -> dict[str, Any]:
    """The first JSON object in a reply, fenced or bare."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    try:
        out = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ChallengerUnavailable("The model's memo was not valid JSON") from exc
    if not isinstance(out, dict):
        raise ChallengerUnavailable("The model's memo was not a JSON object")
    return out


def challenge(
    gateway: Any,
    dossier: dict[str, Any],
    rules_memo: dict[str, Any],
    *,
    profile: str | None = None,
    object_ref: str | None = None,
) -> dict[str, Any]:
    """Ask the profile's model for a memo: {summary, findings, model} or ChallengerUnavailable."""
    request = json.dumps(
        {"dossier": dossier, "deterministic_findings": rules_memo["findings"]},
        indent=1,
        sort_keys=True,
        default=str,
    )
    prompt = (
        "Challenge this version. Answer with a single JSON object and nothing else, matching this "
        "JSON Schema:\n" + json.dumps(SCHEMA) + "\n\nThe dossier and the deterministic findings "
        "follow as JSON.\n\n" + request
    )
    try:
        out = gateway.complete(
            None,
            purpose="assistant.challenge",
            system=SYSTEM,
            prompt=prompt,
            profile=profile,
            object_ref=object_ref,
            max_tokens=MAX_TOKENS,
        )
    except LlmUnavailable as exc:
        raise ChallengerUnavailable(exc.message) from exc
    if out.stop_reason in ("max_tokens", "length"):
        raise ChallengerUnavailable("The memo was cut off at the output limit")
    memo = _json_object(out.text)
    findings = [
        {**f, "evidence": None, "source": out.provider}
        for f in memo.get("findings", [])
        if isinstance(f, dict)
        and f.get("severity") in SEVERITIES
        and f.get("category") in CATEGORIES
    ]
    return {
        "summary": str(memo.get("summary", ""))[:2000],
        "findings": findings,
        "model": f"{out.provider}/{out.model}",
    }
