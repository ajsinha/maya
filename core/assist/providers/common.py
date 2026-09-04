"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The shape of a language model, from the platform's side of the boundary.

MAYA has always been able to record what a generation produced, gate it against
an oracle, reject the claims it could not ground, and hold the rest until a
person signs. What it could not do was *ask*. The documentation said so plainly:
MAYA does not call a language model.

That gap is now a port with two implementations and a stated boundary.

**What a provider returns is untrusted.** This is the whole design. A provider
hands back prose and a list of claims, each claim naming the evidence it rests
on. Nothing about that is believed: the grounding gate checks every citation
against evidence the platform already holds, and a claim citing something that
does not exist is dropped before anybody reads it. So a provider cannot
introduce a fact — only a *candidate* fact, which survives exactly as far as its
citation does.

That is why the mock below is useful rather than a stub. It exercises the real
path: real capabilities, real oracles, real grounding, real attestation, real
automation-bias sampling. Only the sentence-generation is fake, and the sentence
is the part the platform was never going to trust anyway.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from core.assist.common import AssistError


@dataclass(frozen=True)
class Draft:
    """What a provider hands back. None of it is believed yet.

    ``claims`` is the part that matters: each is ``{"text": ..., "citations":
    [...]}`` -- the key the grounding gate reads -- and it will drop any whose
    citations the platform does not hold, including a claim that cites nothing. ``text`` is the provider's own prose and is kept only for the
    record -- what a reader eventually sees is assembled from the claims that
    survived.
    """
    text: str
    claims: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "claims": list(self.claims),
                "model": self.model, "provider": self.provider,
                "usage": dict(self.usage)}


@runtime_checkable
class Provider(Protocol):
    """Something that can draft. Deliberately small."""

    key: str

    def available(self) -> Optional[str]:
        """None if usable, otherwise the reason it is not."""
        ...

    def draft(self, prompt: str, *, base_model: str,
              evidence_ids: Tuple[str, ...],
              context: Dict[str, Any]) -> Draft:
        ...


def refuse_unavailable(key: str, why: str) -> AssistError:
    """One refusal shape, so a missing provider reads the same wherever it bites."""
    return AssistError(
        "provider_unavailable",
        f"the '{key}' assist provider cannot be used: {why}",
        "configure assist.provider, or use the 'mock' provider, which exercises "
        "the whole governed path without calling anything")
