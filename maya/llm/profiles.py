"""
Logical models: a caller names a *profile*, never a provider or a model.

A profile says which provider to use, which model to ask it for, the parameters to ask with
(``max_tokens``, ``temperature``) and any option of that provider this profile needs
differently -- another base URL, another region, another key variable::

    # config/llm_profiles.yaml
    default: drafting
    profiles:
      drafting:
        provider: anthropic
        model: claude-opus-5
        max_tokens: 2048
        options: {thinking: adaptive}
      local:
        provider: ollama
        model: llama3.1
        options: {base_url: http://gpu-box:11434}

A document template asks ``ai("intended_use", "...", profile="local")`` or leaves the profile
out for the default; moving from Claude to a local model, or giving one kind of section a
cheaper one, is an edit to this file and never to a template or to code.

Without the file there is one profile, ``default``, made from the ``llm.*`` settings, so a
deployment that wants one model configures it exactly as before.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maya.core.errors import ValidationFailed

IMPLICIT = "default"
PROFILE_KEYS = {"provider", "model", "max_tokens", "temperature", "options", "description"}


@dataclass
class Profile:
    name: str
    provider: str
    model: str = ""
    max_tokens: int | None = None
    temperature: float | None = None
    options: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    source: str = "file"  # "settings", "file" or "database"

    def as_row(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "options": {k: v for k, v in self.options.items() if "key" not in k.lower()},
            "description": self.description,
            "source": self.source,
        }


class ProfileSettings:
    """The settings a provider reads, with this profile's choices laid over them.

    A provider reads ``llm.model``, ``llm.<provider>.<option>`` and the like from settings;
    handing it this view instead makes the same provider serve many profiles without knowing
    that profiles exist."""

    def __init__(self, settings: Any, profile: Profile) -> None:
        self._s, self._p = settings, profile

    def _override(self, key: str) -> Any:
        p = self._p
        if key == "llm.model" and p.model:
            return p.model
        if key == "llm.max_tokens" and p.max_tokens is not None:
            return str(p.max_tokens)
        if key == "llm.temperature" and p.temperature is not None:
            return str(p.temperature)
        prefix = f"llm.{p.provider}."
        if key.startswith(prefix) and key[len(prefix) :] in p.options:
            return str(p.options[key[len(prefix) :]])
        return None

    def get(self, key: str, default: Any = None) -> Any:
        value = self._override(key)
        return value if value is not None else self._s.get(key, default)

    def int(self, key: str, default: int = 0) -> int:
        value = self._override(key)
        return int(value) if value is not None else int(self._s.int(key, default))

    def bool(self, key: str, default: bool = False) -> bool:
        value = self._override(key)
        if value is not None:
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        return bool(self._s.bool(key, default))


def load(settings: Any) -> tuple[dict[str, Profile], str]:
    """Every profile, and the name of the default one."""
    implicit = Profile(
        IMPLICIT,
        provider=(settings.get("llm.provider", "none") or "none").strip(),
        model=(settings.get("llm.model", "") or "").strip(),
        description="made from the llm.* settings",
        source="settings",
    )
    profiles = {IMPLICIT: implicit}
    default = IMPLICIT
    path = _path(settings)
    if path is not None and path.exists():
        import yaml

        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, raw in (doc.get("profiles") or {}).items():
            profiles[str(name)] = _profile(str(name), raw or {}, path)
        default = str(doc.get("default") or default)
    chosen = (settings.get("llm.profile", "") or "").strip() or default
    if chosen not in profiles:
        raise ValidationFailed(
            f"The default model profile '{chosen}' is not defined in {path} "
            f"(profiles: {', '.join(sorted(profiles))})"
        )
    return profiles, chosen


def from_row(row: dict[str, Any]) -> Profile:
    """A profile an administrator saved in the database."""
    return Profile(
        str(row["name"]),
        provider=str(row["provider"]),
        model=str(row.get("model") or ""),
        max_tokens=row.get("max_tokens"),
        temperature=row.get("temperature"),
        options=dict(row.get("options") or {}),
        description=str(row.get("description") or ""),
        source="database",
    )


def _path(settings: Any) -> Path | None:
    raw = (settings.get("llm.profiles_file", "config/llm_profiles.yaml") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        from maya.config import project_root

        path = project_root() / path
    return path


def _profile(name: str, raw: dict[str, Any], path: Path) -> Profile:
    unknown = set(raw) - PROFILE_KEYS
    if unknown:
        raise ValidationFailed(
            f"Model profile '{name}' in {path} has unknown key(s) {sorted(unknown)}; "
            f"a profile takes {sorted(PROFILE_KEYS)}"
        )
    if not raw.get("provider"):
        raise ValidationFailed(f"Model profile '{name}' in {path} names no provider")
    return Profile(
        name,
        provider=str(raw["provider"]),
        model=str(raw.get("model") or ""),
        max_tokens=int(raw["max_tokens"]) if raw.get("max_tokens") is not None else None,
        temperature=float(raw["temperature"]) if raw.get("temperature") is not None else None,
        options=dict(raw.get("options") or {}),
        description=str(raw.get("description") or ""),
    )
