"""
The AI policy: who may use which AI feature, how often, how much, and what leaves MAYA.

Every call the gateway makes passes here first, as drishti's ``LlmPolicy`` does:

* **Features and roles.** Each call has a purpose, and each purpose belongs to a *feature*
  (drafting, documents, the challenger, evaluation runs, asking, explaining, narrating, the
  admin's connection test). ``ai.roles.<feature>`` names the roles that may use it; ``*`` means
  anyone signed in. MAYA itself (the challenger) is not a person and is not role-checked.
* **Rate limits.** Calls per person per minute, and per feature per minute, counted in this
  process -- a runaway script is stopped before it costs anything.
* **A daily budget.** Tokens per day across MAYA, always measurable; and money per day, for
  profiles that declare their price (``options.price_in_per_mtok`` and
  ``price_out_per_mtok``). MAYA ships no price table: a built-in price would be a guess that
  goes stale, and a cap computed from a guess is not a control.
* **Masking.** Before a prompt leaves, e-mail addresses, card numbers that pass the Luhn
  check, phone numbers and long digit runs are replaced, as are the values of any field named
  in ``ai.mask.fields``. MAYA's prompts are built from names and descriptions, not data; this
  is the second line, for the text a person typed into a description.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

# feature -> (what it is, the roles allowed by default)
FEATURES: dict[str, tuple[str, str]] = {
    "draft": (
        "Drafts of feature definitions, formulas and specification sections",
        "feature_designer,model_designer,model_developer,admin",
    ),
    "documents": (
        "Model documents and model cards written with AI",
        "model_designer,model_developer,model_manager,model_validator,model_owner,admin",
    ),
    "challenger": ("The recorded challenger's memo on a review (asked by MAYA itself)", "*"),
    "llm_eval": (
        "Live evaluation runs of LLM applications",
        "model_designer,model_developer,model_manager,model_validator,admin",
    ),
    "ask": ("Questions about the estate, in plain words", "*"),
    "explain": ("Explanations of a page, a number or a change", "*"),
    "narrate": ("Narration of diffs, restatements and monitoring, from MAYA's own figures", "*"),
    "admin": ("The connection test on Admin → AI models", "admin"),
}

# a call's purpose, by its leading word, to the feature it belongs to
_PURPOSES = (
    ("ai.test", "admin"),
    ("assistant.challenge", "challenger"),
    ("assistant.draft", "draft"),
    ("draft", "draft"),
    ("document", "documents"),
    ("llm.evaluation", "llm_eval"),
    ("ask", "ask"),
    ("explain", "explain"),
    ("narrate", "narrate"),
)


def feature_of(purpose: str) -> str:
    for prefix, feature in _PURPOSES:
        if (
            purpose == prefix
            or purpose.startswith(prefix + ":")
            or purpose.startswith(prefix + ".")
        ):
            return feature
    return "draft"  # an unnamed purpose is held to the strictest drafting roles


def roles_for(settings: Any, feature: str) -> set[str]:
    default = FEATURES.get(feature, ("", "admin"))[1]
    raw = settings.get(f"ai.roles.{feature}", default) or ""
    return {r.strip() for r in str(raw).split(",") if r.strip()}


def allowed(settings: Any, feature: str, roles: list[str] | set[str]) -> bool:
    wanted = roles_for(settings, feature)
    return "*" in wanted or bool(wanted & set(roles))


class RateLimiter:
    """Sliding one-minute windows, per key, in this process."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str, per_minute: int, now: float | None = None) -> bool:
        if per_minute <= 0:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > 60.0:
                hits.popleft()
            if len(hits) >= per_minute:
                return False
            hits.append(now)
            return True


# -- masking ---------------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_DIGITS = re.compile(r"(?<![\w.])(?:\d[ -]?){13,19}(?![\w.])")
_PHONE = re.compile(r"(?<!\w)\+?\d{1,3}[ -]?\(?\d{2,4}\)?[ -]?\d{3,4}[ -]?\d{3,4}(?!\w)")
_LONG = re.compile(r"(?<![\w.])\d{9,}(?![\w.])")


def _luhn(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        flip = not flip
    return total % 10 == 0


@dataclass
class Masked:
    text: str
    count: int


def mask(text: str, fields: list[str] | None = None, patterns: bool = True) -> Masked:
    """The prompt with personal data and named fields replaced, and how many were."""
    count = 0

    def sub(rx: re.Pattern[str], label: str, keep: Any = None) -> None:
        nonlocal text, count

        def repl(m: re.Match[str]) -> str:
            nonlocal count
            if keep is not None and not keep(m.group(0)):
                return m.group(0)
            count += 1
            return f"[{label}]"

        text = rx.sub(repl, text)

    if patterns:
        sub(_EMAIL, "email")
        sub(_DIGITS, "card", lambda s: _luhn(re.sub(r"\D", "", s)))
        sub(_PHONE, "phone")
        sub(_LONG, "number")
    for name in fields or []:
        rx = re.compile(rf"(?i)(\b{re.escape(name)}\b\s*[:=]\s*)([^\s,;]+)")
        new, n = rx.subn(lambda m: m.group(1) + "[masked]", text)
        text, count = new, count + n
    return Masked(text, count)


def cost_usd(
    options: dict[str, Any], input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """What a call cost, from the profile's declared prices; None when it declares none."""
    try:
        pin = float(options["price_in_per_mtok"])
        pout = float(options["price_out_per_mtok"])
    except (KeyError, TypeError, ValueError):
        return None
    return round(((input_tokens or 0) * pin + (output_tokens or 0) * pout) / 1_000_000, 6)
