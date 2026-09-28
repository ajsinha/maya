"""
Language models behind one small interface, and the providers that implement it.

MAYA drafts prose with a language model -- a model card's intended use, the narrative of a
validation report, the sections of a model's documentation -- and it must not care which
model or which provider does the drafting. ``LlmProvider`` is the whole contract: a system
prompt and messages in, text and token counts out. The built-in providers are in
``maya.llm.providers``; a third party adds one at the ``llm_provider`` extension point
(an entry point in the ``maya.llm_provider`` group, loaded only when ``plugins.allow``
names it), and ``llm.provider`` chooses among them by name.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from maya.llm.base import Completion, LlmProvider, LlmUnavailable, Message

__all__ = ["Completion", "LlmProvider", "LlmUnavailable", "Message"]
