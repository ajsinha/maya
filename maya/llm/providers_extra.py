"""
More language-model providers: Gemini, Cohere, the named OpenAI-compatible services, and a
rule-driven mock.

The OpenAI-compatible services -- Groq, Together, Fireworks, DeepSeek, xAI, OpenRouter,
Perplexity, Hugging Face, vLLM, LM Studio, Mistral -- speak the Chat Completions API, so each
is the OpenAI provider with its own name, its own settings prefix (``llm.<name>.model``,
``.base_url``, ``.api_key_env``) and that service's public address and usual key variable as
defaults. Naming them is what lets an administrator pick "groq" from a list, see it in the
audit log as groq, and give it a profile of its own, rather than every one being "openai".

The mock answers from rules: a list of regular expressions and replies, read from
``llm.mock.rules_file`` (YAML). It is for tutorials, demonstrations and tests that need a
model to say something specific and say it every time -- the stub only echoes the task.

Every provider here keeps MAYA's contract: a failure is an ``LlmUnavailable`` with a sentence
saying what to do, and no key is ever read from anywhere but the environment.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
from typing import Any

from maya.llm.base import Completion, LlmUnavailable, Message
from maya.llm.providers import BUILT_IN, OpenAIProvider, _Http, _key, _model, _require_model

# name -> (public base URL, the environment variable its key usually lives in, a label)
COMPATIBLE: dict[str, tuple[str, str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "Groq"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY", "Together AI"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "Fireworks AI"),
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "DeepSeek"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY", "xAI"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "OpenRouter"),
    "perplexity": ("https://api.perplexity.ai", "PERPLEXITY_API_KEY", "Perplexity"),
    "huggingface": ("https://router.huggingface.co/v1", "HF_TOKEN", "Hugging Face"),
    "vllm": ("http://localhost:8000/v1", "", "vLLM (self-hosted)"),
    "lmstudio": ("http://localhost:1234/v1", "", "LM Studio (local)"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "Mistral"),
}


class _Compatible(OpenAIProvider):
    """One named OpenAI-compatible service; subclasses fix the name and defaults."""

    base_default = ""
    key_env_default = ""

    def __init__(self, settings: Any, transport: Any = None) -> None:
        _Http.__init__(self, settings, transport)
        prefix = f"llm.{self.name}"
        self.model_setting = f"{prefix}.model"
        self.model = _model(settings, f"{prefix}.model", "")
        self.base = (settings.get(f"{prefix}.base_url", self.base_default) or "").rstrip("/")

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> "_Compatible":
        return cls(settings, kw.get("transport"))

    def _url_and_headers(self) -> tuple[str, dict[str, str]]:
        setting = f"llm.{self.name}.api_key_env"
        env = (self.settings.get(setting, self.key_env_default) or "").strip()
        if not env:  # a local server (vLLM, LM Studio) takes no key
            return f"{self.base}/chat/completions", {}
        key = _key(self.settings, setting, self.key_env_default, self.name)
        return f"{self.base}/chat/completions", {"Authorization": f"Bearer {key}"}


def _compatible(name: str, base: str, env: str, label: str) -> type[_Compatible]:
    doc = f"{label}, through its OpenAI-compatible Chat Completions endpoint."
    return type(
        f"{name.title()}Provider",
        (_Compatible,),
        {"name": name, "base_default": base, "key_env_default": env, "__doc__": doc},
    )


class GeminiProvider(_Http):
    """Google's Gemini API (``generateContent``), keyed by ``GEMINI_API_KEY``."""

    name = "gemini"
    model_setting = "llm.gemini.model"

    def __init__(self, settings: Any, transport: Any = None) -> None:
        super().__init__(settings, transport)
        self.model = _model(settings, "llm.gemini.model", "")
        self.base = (
            settings.get("llm.gemini.base_url", "https://generativelanguage.googleapis.com/v1beta")
            or ""
        ).rstrip("/")

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> "GeminiProvider":
        return cls(settings, kw.get("transport"))

    def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float | None = None,
    ) -> Completion:
        model = _require_model(self.model, self.name, self.model_setting)
        key = _key(self.settings, "llm.gemini.api_key_env", "GEMINI_API_KEY", self.name)
        config: dict[str, Any] = {"maxOutputTokens": int(max_tokens)}
        if temperature is not None:
            config["temperature"] = float(temperature)
        body: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
            ],
            "generationConfig": config,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        data = self._post(
            f"{self.base}/models/{model}:generateContent", body, {"x-goog-api-key": key}
        )
        candidate = (data.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        usage = data.get("usageMetadata") or {}
        return Completion(
            "".join(str(p.get("text", "")) for p in parts),
            self.name,
            model,
            usage.get("promptTokenCount"),
            usage.get("candidatesTokenCount"),
            candidate.get("finishReason"),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "ready": bool(self.model),
            "detail": self.base,
        }


class CohereProvider(_Http):
    """Cohere's Chat API (v2), keyed by ``COHERE_API_KEY``."""

    name = "cohere"
    model_setting = "llm.cohere.model"

    def __init__(self, settings: Any, transport: Any = None) -> None:
        super().__init__(settings, transport)
        self.model = _model(settings, "llm.cohere.model", "")
        self.base = (settings.get("llm.cohere.base_url", "https://api.cohere.com/v2") or "").rstrip(
            "/"
        )

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> "CohereProvider":
        return cls(settings, kw.get("transport"))

    def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float | None = None,
    ) -> Completion:
        model = _require_model(self.model, self.name, self.model_setting)
        key = _key(self.settings, "llm.cohere.api_key_env", "COHERE_API_KEY", self.name)
        body: dict[str, Any] = {
            "model": model,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": int(max_tokens),
        }
        if temperature is not None:
            body["temperature"] = float(temperature)
        data = self._post(f"{self.base}/chat", body, {"Authorization": f"Bearer {key}"})
        content = (data.get("message") or {}).get("content") or []
        tokens = (data.get("usage") or {}).get("tokens") or {}
        return Completion(
            "".join(str(c.get("text", "")) for c in content),
            self.name,
            model,
            tokens.get("input_tokens"),
            tokens.get("output_tokens"),
            data.get("finish_reason"),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "ready": bool(self.model),
            "detail": self.base,
        }


class MockProvider:
    """Answers from rules: the first rule whose pattern matches the prompt gives the reply.

    ``llm.mock.rules_file`` is YAML: ``rules: [{match: <regex>, reply: <text>}, ...]`` and an
    optional ``default:``. Deterministic, offline, and free -- for tutorials and tests."""

    name = "mock"
    model = "mock-1"

    def __init__(self, rules: list[tuple[re.Pattern[str], str]], default: str) -> None:
        self.rules, self.default = rules, default

    @classmethod
    def from_settings(cls, settings: Any, **_: Any) -> "MockProvider":
        path = (settings.get("llm.mock.rules_file", "") or "").strip()
        rules: list[tuple[re.Pattern[str], str]] = []
        default = "The mock model has no rule for this prompt."
        if path:
            try:
                data = settings.load_yaml(path) or {}
            except (OSError, ValueError) as exc:
                raise LlmUnavailable(f"The mock provider could not read {path}: {exc}") from exc
            for rule in data.get("rules") or []:
                try:
                    rules.append((re.compile(str(rule["match"]), re.I | re.S), str(rule["reply"])))
                except (KeyError, re.error) as exc:
                    raise LlmUnavailable(f"A rule in {path} is not usable: {exc}") from exc
            default = str(data.get("default") or default)
        return cls(rules, default)

    def complete(self, system: str, messages: list[Message], **_: Any) -> Completion:
        prompt = (system + "\n" + (messages[-1].content if messages else "")).strip()
        reply = next((r for p, r in self.rules if p.search(prompt)), self.default)
        return Completion(
            reply, self.name, self.model, len(prompt.split()), len(reply.split()), "end"
        )

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "ready": True,
            "detail": f"{len(self.rules)} rule(s), offline",
        }


EXTRA: dict[str, Any] = {
    "gemini": GeminiProvider,
    "cohere": CohereProvider,
    "mock": MockProvider,
    **{name: _compatible(name, *spec) for name, spec in COMPATIBLE.items()},
}

# Every provider MAYA ships, in the order Admin → AI models lists them.
ALL: dict[str, Any] = {**BUILT_IN, **EXTRA}
