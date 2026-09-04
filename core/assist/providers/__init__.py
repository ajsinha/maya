"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Which model MAYA asks, and what it does when there is none.

One provider works and three refuse by name. That ratio is deliberate and is
recorded in `describe()`, so an operator can see at a glance what this instance
can actually do rather than discovering it at the moment somebody needed a draft.
"""
from core.assist.providers.common import Draft, Provider, refuse_unavailable
from core.assist.providers.mock import MockProvider
from core.assist.providers.remote import (AnthropicProvider, OpenAIProvider,
                                          SelfHostedProvider)
from core.assist.common import AssistError

PROVIDERS = {p.key: p for p in (MockProvider, AnthropicProvider,
                                OpenAIProvider, SelfHostedProvider)}


def build(key: str = "mock", **kwargs) -> Provider:
    """The named provider, or a refusal naming the ones that exist."""
    if key not in PROVIDERS:
        raise AssistError(
            "unknown_provider",
            f"'{key}' is not a provider this platform knows",
            f"use one of {', '.join(sorted(PROVIDERS))}")
    return PROVIDERS[key](**kwargs)


def describe() -> list:
    """What each provider is, and why it can or cannot be used here."""
    out = []
    for key, cls in sorted(PROVIDERS.items()):
        instance = cls()
        why = instance.available()
        out.append({"provider": key, "usable": why is None,
                    "why_not": why or ""})
    return out


__all__ = ["Draft", "Provider", "MockProvider", "AnthropicProvider",
           "OpenAIProvider", "SelfHostedProvider", "PROVIDERS", "build",
           "describe", "refuse_unavailable"]
