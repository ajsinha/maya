"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The providers that would call somebody else's model.

These are placeholders, and they are placeholders that **refuse by name** rather
than stubs that return something plausible. The distinction is the whole point:
a stub returning fabricated prose in a governance platform is a machine writing
into the record with nothing behind it, and the first person to see the output
would have no way to tell. A refusal that says which provider, why it cannot
run, and what to do instead costs nothing and cannot be mistaken for an answer.

**What is deliberately absent, and what would have to be true to add it.**

Wiring one of these up is not a matter of filling in an HTTP call. Before a
remote model may draft into this register, four things need answering, and none
of them is code:

  * **Egress.** A governance platform that cannot be deployed air-gapped is one
    somebody works around. Every other asset here is vendored for that reason.
    A remote provider is the first component that must reach the internet, and
    whether it may is a deployment decision rather than a default.
  * **Confidentiality.** A prompt assembled from this register carries model
    inventory, validation findings and exposure figures. Which of that may leave
    the institution is a question for whoever owns the data, not for a client
    library.
  * **Reproducibility.** A remote model is not deterministic and its weights
    move underneath a version string. The warrant grammar already treats
    ``llm.prompt`` and ``llm.agent`` as stochastic runtimes for exactly this
    reason. What is recorded has to be the output and its digest, never "the
    model said so".
  * **Cost and rate limits.** Which are operational, and which is why they are
    named here rather than discovered in production.

Until those are answered for a given deployment, the honest behaviour is to
refuse. ``MockProvider`` exercises the entire governed path in the meantime --
capability gating, oracles, grounding, attestation, sampling -- because none of
that ever depended on the sentence being real.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.assist.providers.common import Draft, refuse_unavailable
from core.log import get_logger

logger = get_logger(__name__)


class _RemoteProvider:
    """Common shape: named, unavailable, and explicit about why."""

    key = "remote"
    vendor = "a remote service"
    package = ""
    env_var = ""

    def available(self) -> Optional[str]:
        return (f"MAYA does not call {self.vendor}. Nothing here is wired to an "
                f"egress path, a credential, or a confidentiality decision about "
                f"what may leave the institution")

    def draft(self, prompt: str, *, base_model: str = "",
              evidence_ids: Tuple[str, ...] = (),
              context: Optional[Dict[str, Any]] = None) -> Draft:
        logger.warning("refused a draft request for the unwired provider %r",
                       self.key)
        raise refuse_unavailable(self.key, self.available())


class AnthropicProvider(_RemoteProvider):
    key = "anthropic"
    vendor = "the Anthropic API"
    package = "anthropic"
    env_var = "ANTHROPIC_API_KEY"


class OpenAIProvider(_RemoteProvider):
    key = "openai"
    vendor = "the OpenAI API"
    package = "openai"
    env_var = "OPENAI_API_KEY"


class SelfHostedProvider(_RemoteProvider):
    """A model the institution runs itself, reached over HTTP.

    Listed separately because it is the one that answers the egress and
    confidentiality objections above by construction, and is therefore the
    likeliest first real provider rather than the least likely.
    """
    key = "self_hosted"
    vendor = "a self-hosted inference endpoint"
    env_var = "MAYA_ASSIST_ENDPOINT"
