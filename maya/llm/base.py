"""
The contract every language-model provider implements.

Deliberately small. A provider takes a system prompt and a list of messages and returns
text with token counts; everything a document needs is built on that, and anything a
provider offers beyond it (tools, images, streaming to a screen) is its own business.
A provider that cannot answer -- no key, no network, an unknown model -- raises
``LlmUnavailable`` with a sentence a person can act on, never a bare transport error.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from maya.core.errors import MayaError


class LlmUnavailable(MayaError):
    """The configured language model could not be asked; the reason says what to change."""

    code, status = "llm_unavailable", 503


@dataclass(frozen=True)
class Message:
    role: str  # "user" or "assistant"
    content: str


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def usage(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "stop_reason": self.stop_reason,
        }


class LlmProvider(Protocol):
    """What ``llm.provider`` names. ``name`` is the registered name; ``model`` the model it
    will ask, resolved from ``llm.model`` or the provider's own default."""

    name: str
    model: str

    def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float | None,
    ) -> Completion: ...

    def describe(self) -> dict[str, Any]:
        """Where it points and whether it looks usable -- without calling it."""
        ...
