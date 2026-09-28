"""
The AI gateway: the one place MAYA asks a language model anything.

Callers name a **model profile** (``maya.llm.profiles``) -- a logical model such as
``drafting`` or ``local`` -- or nothing, for the default. The gateway resolves the profile to
a provider from the ``llm_provider`` extension point (a built-in or an allowed plugin),
builds it with the profile's choices laid over the settings, and records every call in the
audit log: its purpose, the profile, the provider and model, the token counts, and the hash
of the prompt. The prompt itself is not logged: it carries a model's facts, which the audit
log's readers may not be allowed to see, and its hash is enough to say which prompt
produced which draft.

What comes back is a draft. Nothing here approves, blocks or edits anything; a document
that carries drafted text says so on its face until a person approves it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
from typing import Any

from maya.llm import profiles as prof
from maya.llm.base import Completion, LlmUnavailable, Message
from maya.security.authz import Principal


class AiGateway:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        self.override: Any = None  # a provider object set directly (tests, embedding)
        self._cache: dict[str, Any] = {}

    # -- profiles -----------------------------------------------------------------------
    def profiles(self) -> tuple[dict[str, prof.Profile], str]:
        return prof.load(self.p.settings)

    def resolve(self, profile: str | None = None) -> tuple[prof.Profile, Any]:
        """The profile a caller named (or the default), and its provider, built for it."""
        known, default = self.profiles()
        name = profile or default
        if name not in known:
            raise LlmUnavailable(
                f"No model profile named '{name}' (profiles: {', '.join(sorted(known))})"
            )
        chosen = known[name]
        if self.override is not None:
            return chosen, self.override
        key = f"{name}:{chosen.provider}:{chosen.model}"
        if key not in self._cache:
            plugin = self.p.plugins.get("llm_provider", chosen.provider)
            if plugin is None or plugin.factory is None:
                raise LlmUnavailable(
                    f"Model profile '{name}' names the provider '{chosen.provider}', which is "
                    "not registered or not an allowed plugin (see Admin → Plugins)"
                )
            self._cache[key] = plugin.factory(prof.ProfileSettings(self.p.settings, chosen))
        return chosen, self._cache[key]

    def status(self, p: Principal | None = None) -> dict[str, Any]:
        """Every profile with where it points and whether it looks usable, and every
        provider on offer at the extension point."""
        try:
            known, default = self.profiles()
        except Exception as exc:  # noqa: BLE001 - a broken profiles file is itself the status
            return {
                "default": None,
                "profiles": [],
                "providers": [],
                "drafting": False,
                "error": str(exc),
            }
        rows = []
        for name, profile in known.items():
            try:
                described = self.resolve(name)[1].describe()
            except LlmUnavailable as exc:
                described = {"ready": False, "detail": exc.message, "model": profile.model}
            rows.append(
                {
                    **profile.as_row(),
                    "ready": bool(described.get("ready")),
                    "detail": described.get("detail", ""),
                    "model": described.get("model") or profile.model,
                }
            )
        offered = [
            {"name": r["name"], "origin": r["origin"], "status": r["status"], "detail": r["detail"]}
            for r in self.p.plugins.rows()
            if r["point"] == "llm_provider"
        ]
        ready = next((r["ready"] for r in rows if r["name"] == default), False)
        return {"default": default, "profiles": rows, "providers": offered, "drafting": ready}

    # -- asking ---------------------------------------------------------------------------
    def complete(
        self,
        p: Principal,
        *,
        purpose: str,
        system: str,
        prompt: str,
        profile: str | None = None,
        object_ref: str | None = None,
    ) -> Completion:
        chosen, provider = self.resolve(profile)
        view = prof.ProfileSettings(self.p.settings, chosen)
        out = provider.complete(
            system,
            [Message("user", prompt)],
            max_tokens=view.int("llm.max_tokens", 2048),
            temperature=float(view.get("llm.temperature", "0.2") or 0.2),
        )
        with self.p.uow(p.username) as uow:
            uow.audit(
                "ai.completion",
                object_ref=object_ref,
                detail={
                    "purpose": purpose,
                    "profile": chosen.name,
                    **out.usage(),
                    "prompt_sha256": hashlib.sha256((system + "\n" + prompt).encode()).hexdigest(),
                },
            )
        return out
