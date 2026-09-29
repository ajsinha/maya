"""
The AI gateway: the one place MAYA asks a language model anything.

Callers name a **model profile** (``maya.llm.profiles``) -- a logical model such as
``drafting`` or ``local`` -- or nothing, for the default. Profiles come from three places,
later ones winning a name clash: the ``llm.*`` settings (one profile, ``default``), the
profiles file, and the profiles an administrator saved from **Admin → AI models**. Which
profile is the default comes, in order of precedence, from the choice an administrator made
there, then ``llm.profile``, then the file's ``default:`` line. Every process reads the
administrator's choices from the database, so switching the default takes effect at once,
everywhere, without a restart.

The gateway resolves a profile to a provider from the ``llm_provider`` extension point (a
built-in or an allowed plugin), builds it with the profile's choices laid over the settings,
and records every call in the audit log: its purpose, the profile, the provider and model,
the token counts, and the hash of the prompt. The prompt itself is not logged: it carries a
model's facts, which the audit log's readers may not be allowed to see.

What comes back is a draft. Nothing here approves, blocks or edits anything.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from maya.core.errors import PermissionDenied, ValidationFailed
from maya.llm import profiles as prof
from maya.llm.base import Completion, LlmUnavailable, Message
from maya.security.authz import Principal

DEFAULT_KEY = "llm.default_profile"
NAME = re.compile(r"^[a-z][a-z0-9_\-]{0,63}$")
SECRET_WORDS = ("api_key", "secret", "password", "token")
TEST_PROMPT = "Reply with the single word: ready."


class AiGateway:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        self.override: Any = None  # a provider object set directly (tests, embedding)
        self._cache: dict[str, Any] = {}

    # -- profiles -----------------------------------------------------------------------
    def _runtime_default(self) -> str | None:
        with self.p.uow() as uow:
            row = uow.repo("runtime_settings").find_one(key=DEFAULT_KEY)
        return str(row["value"]) if row and row.get("value") else None

    def profiles(self) -> tuple[dict[str, prof.Profile], str, str]:
        """Every profile, the default's name, and where the default was chosen."""
        known, default = prof.load(self.p.settings)
        source = (
            "the llm.profile setting"
            if self.p.settings.get("llm.profile", "")
            else "the profiles file"
        )
        with self.p.uow() as uow:
            for row in uow.repo("llm_profiles").list(order_by=["name"]):
                known[row["name"]] = prof.from_row(row)
        chosen = self._runtime_default()
        if chosen and chosen in known:
            return known, chosen, "an administrator (Admin → AI models)"
        return known, default, source

    def resolve(self, profile: str | None = None) -> tuple[prof.Profile, Any]:
        """The profile a caller named (or the default), and its provider, built for it."""
        known, default, _ = self.profiles()
        name = profile or default
        if name not in known:
            raise LlmUnavailable(
                f"No model profile named '{name}' (profiles: {', '.join(sorted(known))})"
            )
        # the cache key is the whole profile, so an edit builds a fresh provider
        return known[name], self._build(known[name])

    def status(self, p: Principal | None = None) -> dict[str, Any]:
        """Every profile with where it came from, where it points and whether it looks usable;
        which is the default and who chose it; and every provider on offer."""
        try:
            known, default, default_source = self.profiles()
        except Exception as exc:  # noqa: BLE001 - a broken profiles file is itself the status
            return {
                "default": None,
                "profiles": [],
                "providers": self._providers(),
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
                    "is_default": name == default,
                }
            )
        ready = next((r["ready"] for r in rows if r["name"] == default), False)
        return {
            "default": default,
            "default_source": default_source,
            "profiles": rows,
            "providers": self._providers(),
            "drafting": ready,
        }

    def _providers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": r["name"],
                "origin": r["origin"],
                "status": r["status"],
                "detail": r["detail"],
                "version": r["version"],
            }
            for r in self.p.plugins.rows()
            if r["point"] == "llm_provider"
        ]

    # -- administration ---------------------------------------------------------------------
    @staticmethod
    def _admin(p: Principal) -> None:
        if not p.is_admin:
            raise PermissionDenied("Only an administrator may change the model profiles")

    def set_default(self, p: Principal, profile: str | None) -> dict[str, Any]:
        """Make ``profile`` the default, now, for every process; ``None`` hands the choice
        back to the configuration."""
        self._admin(p)
        known, before, _ = self.profiles()
        if profile and profile not in known:
            raise ValidationFailed(f"No model profile named '{profile}'")
        with self.p.uow(p.username) as uow:
            repo = uow.repo("runtime_settings")
            row = repo.find_one(key=DEFAULT_KEY)
            if row is None:
                repo.add({"key": DEFAULT_KEY, "value": profile})
            else:
                repo.update(row["id"], {"value": profile})
            uow.audit(
                "ai.default_changed", detail={"from": before, "to": profile or "(configuration)"}
            )
        return self.status(p)

    def test(self, p: Principal, profile: str) -> dict[str, Any]:
        """Ask the profile's model one short question; say what came back, how fast, at what
        cost -- or what stopped it."""
        self._admin(p)
        started = time.monotonic()
        try:
            out = self.complete(
                p, purpose="ai.test", system="", prompt=TEST_PROMPT, profile=profile
            )
        except LlmUnavailable as exc:
            return {
                "profile": profile,
                "ok": False,
                "error": exc.message,
                "seconds": round(time.monotonic() - started, 2),
            }
        return {
            "profile": profile,
            "ok": True,
            "reply": out.text.strip()[:200],
            **out.usage(),
            "seconds": round(time.monotonic() - started, 2),
        }

    def save_profile(self, p: Principal, name: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Create or replace a profile in the database. It is checked as the file's are, its
        provider must be on offer, and its options may name a key's environment variable but
        never hold a key."""
        self._admin(p)
        if not NAME.match(name or ""):
            raise ValidationFailed(
                "A profile name is lower-case letters, digits, '_' or '-', starting with a letter"
            )
        unknown = set(fields) - (prof.PROFILE_KEYS - {"name"})
        if unknown:
            raise ValidationFailed(
                f"A profile takes {sorted(prof.PROFILE_KEYS)}; not {sorted(unknown)}"
            )
        provider = str(fields.get("provider") or "")
        if self.p.plugins.get("llm_provider", provider) is None:
            raise ValidationFailed(
                f"'{provider}' is not a provider on offer (see Admin → AI models)"
            )
        options = dict(fields.get("options") or {})
        leaked = [
            k
            for k in options
            if any(w in k.lower() for w in SECRET_WORDS) and not k.lower().endswith("_env")
        ]
        if leaked:
            raise ValidationFailed(
                f"Options may not hold a secret ({', '.join(leaked)}): name the environment variable "
                "that holds it instead, as api_key_env"
            )
        row = {
            "provider": provider,
            "model": str(fields.get("model") or ""),
            "max_tokens": int(fields["max_tokens"])
            if fields.get("max_tokens") not in (None, "")
            else None,
            "temperature": float(fields["temperature"])
            if fields.get("temperature") not in (None, "")
            else None,
            "options": options,
            "description": str(fields.get("description") or ""),
        }
        with self.p.uow(p.username) as uow:
            repo = uow.repo("llm_profiles")
            existing = repo.find_one(name=name)
            saved = (
                repo.update(existing["id"], row) if existing else repo.add({"name": name, **row})
            )
            uow.audit(
                "ai.profile_saved",
                detail={
                    "profile": name,
                    "provider": provider,
                    "model": row["model"],
                    "replaced": bool(existing),
                },
            )
        return prof.from_row(saved).as_row()

    def delete_profile(self, p: Principal, name: str) -> dict[str, Any]:
        """Remove a profile saved in the database. One from the file is edited there."""
        self._admin(p)
        if self._runtime_default() == name:
            raise ValidationFailed(f"'{name}' is the default; make another the default first")
        with self.p.uow(p.username) as uow:
            row = uow.repo("llm_profiles").find_one(name=name)
            if row is None:
                raise ValidationFailed(
                    f"No profile named '{name}' was saved here; one from the file is edited there"
                )
            uow.repo("llm_profiles").delete(row["id"])
            uow.audit("ai.profile_deleted", detail={"profile": name})
        return {"deleted": name}

    # -- asking ---------------------------------------------------------------------------
    def complete(
        self,
        p: Principal | None,
        *,
        purpose: str,
        system: str,
        prompt: str,
        profile: str | None = None,
        object_ref: str | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        """Ask a profile's model. ``p`` is None when MAYA itself asks (the challenger)."""
        chosen, provider = self.resolve(profile)
        return self._ask(p, chosen, provider, purpose, system, prompt, object_ref, max_tokens, None)

    def complete_declared(
        self,
        p: Principal | None,
        *,
        provider: str,
        model: str,
        purpose: str,
        system: str,
        prompt: str,
        max_tokens: int,
        temperature: float | None,
        object_ref: str | None = None,
    ) -> Completion:
        """Ask exactly the provider and model something declares -- an LLM application's
        approved version -- rather than whichever profile is the default. What is governed is
        that pairing, so it is not something an administrator's switch may change."""
        chosen = prof.Profile(
            f"declared:{provider}",
            provider=provider,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            source="declared",
        )
        return self._ask(
            p,
            chosen,
            self._build(chosen),
            purpose,
            system,
            prompt,
            object_ref,
            max_tokens,
            temperature,
        )

    def _build(self, chosen: prof.Profile) -> Any:
        if self.override is not None:
            return self.override
        key = json.dumps(chosen.as_row() | {"options": chosen.options}, sort_keys=True, default=str)
        if key not in self._cache:
            plugin = self.p.plugins.get("llm_provider", chosen.provider)
            if plugin is None or plugin.factory is None:
                raise LlmUnavailable(
                    f"The provider '{chosen.provider}' is not registered or not an allowed plugin "
                    "(see Admin → AI models)"
                )
            self._cache[key] = plugin.factory(prof.ProfileSettings(self.p.settings, chosen))
        return self._cache[key]

    def _ask(
        self,
        p: Principal | None,
        chosen: prof.Profile,
        provider: Any,
        purpose: str,
        system: str,
        prompt: str,
        object_ref: str | None,
        max_tokens: int | None,
        temperature: float | None,
    ) -> Completion:
        from maya.observability.metrics import METRICS

        view = prof.ProfileSettings(self.p.settings, chosen)
        # a document's purpose names its section; the metric keeps the kind, so series stay few
        labels = {"purpose": ":".join(purpose.split(":")[:2]), "provider": chosen.provider}
        started = time.monotonic()
        try:
            out = provider.complete(
                system,
                [Message("user", prompt)],
                max_tokens=int(max_tokens or view.int("llm.max_tokens", 2048)),
                # a declared pairing is run as declared: no temperature means the provider's own
                temperature=temperature
                if temperature is not None or chosen.source == "declared"
                else float(view.get("llm.temperature", "0.2") or 0.2),
            )
        except LlmUnavailable:
            METRICS.inc("maya_ai_completions_total", {**labels, "outcome": "unavailable"})
            raise
        METRICS.inc("maya_ai_completions_total", {**labels, "outcome": "ok"})
        METRICS.observe("maya_ai_completion_seconds", time.monotonic() - started, labels)
        for direction, n in (("input", out.input_tokens), ("output", out.output_tokens)):
            if n:
                METRICS.inc("maya_ai_tokens_total", {**labels, "direction": direction}, float(n))
        with self.p.uow(p.username if p else "assistant") as uow:
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
