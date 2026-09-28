"""
The providers MAYA ships: Anthropic, OpenAI and anything that speaks its API, Azure OpenAI,
Ollama, Amazon Bedrock -- and ``none`` and ``stub``.

Each is a class with a ``from_settings`` factory, registered at the ``llm_provider``
extension point by ``maya.plugins.built_ins``. A provider reads only its own settings
(``llm.<name>.*``) plus the shared ones (``llm.model``, ``llm.timeout_seconds``), takes an
API key from the environment variable a setting names -- never from configuration -- and
turns every failure into ``LlmUnavailable`` with a sentence saying what to change.

``none`` is the default: MAYA drafts nothing until someone chooses a provider, and a
document still renders, with its AI sections marked as not drafted. ``stub`` answers
deterministically from the prompt, for tests and for demonstrating the flow offline.

Anthropic is called through its official SDK (the ``anthropic`` package), streamed so a
long draft does not hit a request timeout, with adaptive thinking unless it is switched
off. The others are plain HTTP, with ``httpx``; Bedrock needs ``boto3``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from maya.llm.base import Completion, LlmUnavailable, Message


def _model(settings: Any, own_key: str, own_default: str) -> str:
    return (settings.get("llm.model", "") or "").strip() or (
        settings.get(own_key, own_default) or ""
    ).strip()


def _key(settings: Any, setting: str, default_env: str, provider: str) -> str:
    env = (settings.get(setting, default_env) or "").strip()
    value = os.environ.get(env, "") if env else ""
    if not value:
        raise LlmUnavailable(
            f"The {provider} provider reads its API key from the environment variable "
            f"{env or '(none named)'}, which is not set. Set it, or name another in {setting}."
        )
    return value


def _require_model(model: str, provider: str, setting: str) -> str:
    if not model:
        raise LlmUnavailable(f"No model named for {provider}: set llm.model or {setting}")
    return model


class NoProvider:
    """The default: nothing is drafted until a provider is chosen."""

    name, model = "none", ""

    @classmethod
    def from_settings(cls, settings: Any, **_: Any) -> "NoProvider":
        return cls()

    def complete(self, system: str, messages: list[Message], **_: Any) -> Completion:
        raise LlmUnavailable(
            "No language model is configured. Set llm.provider (anthropic, openai, "
            "azure_openai, ollama, bedrock, or an allowed plugin) to draft with one."
        )

    def describe(self) -> dict[str, Any]:
        return {"provider": "none", "model": "", "ready": False, "detail": "nothing is drafted"}


class StubProvider:
    """Deterministic answers from the prompt itself: for tests and offline demonstrations."""

    name = "stub"

    def __init__(self, model: str = "stub-1") -> None:
        self.model = model

    @classmethod
    def from_settings(cls, settings: Any, **_: Any) -> "StubProvider":
        return cls((settings.get("llm.model", "") or "").strip() or "stub-1")

    def complete(
        self, system: str, messages: list[Message], *, max_tokens: int = 0, **_: Any
    ) -> Completion:
        prompt = messages[-1].content if messages else ""
        task = next((ln for ln in prompt.splitlines() if ln.startswith("Task:")), "Task: draft")
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:8]
        text = f"Stub draft for {task[5:].strip().rstrip('.')} (facts {digest})."
        return Completion(
            text, self.name, self.model, len(prompt.split()), len(text.split()), "end"
        )

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "stub",
            "model": self.model,
            "ready": True,
            "detail": "offline, deterministic",
        }


class AnthropicProvider:
    """Claude, through the official ``anthropic`` SDK."""

    name = "anthropic"

    def __init__(self, settings: Any, client: Any = None) -> None:
        self.settings = settings
        self.model = _model(settings, "llm.anthropic.model", "claude-opus-5")
        self.thinking = (settings.get("llm.anthropic.thinking", "adaptive") or "adaptive").strip()
        self._client = client

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> "AnthropicProvider":
        return cls(settings, kw.get("client"))

    def _sdk(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise LlmUnavailable(
                "llm.provider is anthropic, which needs the 'anthropic' package "
                "(pip install anthropic)"
            ) from exc
        key = _key(self.settings, "llm.anthropic.api_key_env", "ANTHROPIC_API_KEY", "anthropic")
        base = (self.settings.get("llm.anthropic.base_url", "") or "").strip() or None
        timeout = float(self.settings.int("llm.timeout_seconds", 120))
        self._client = anthropic.Anthropic(api_key=key, base_url=base, timeout=timeout)
        return self._client

    def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float | None = None,
    ) -> Completion:
        kwargs: dict[str, Any] = {
            "model": _require_model(self.model, "anthropic", "llm.anthropic.model"),
            "max_tokens": int(max_tokens),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system
        if self.thinking == "adaptive":
            kwargs["thinking"] = {"type": "adaptive"}  # temperature is left to the model then
        elif temperature is not None:
            kwargs["temperature"] = float(temperature)
        try:
            with self._sdk().messages.stream(**kwargs) as stream:
                message = stream.get_final_message()
        except LlmUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - the SDK's errors, said plainly
            raise LlmUnavailable(f"Anthropic did not answer: {type(exc).__name__}: {exc}") from exc
        text = "".join(
            getattr(block, "text", "")
            for block in message.content
            if getattr(block, "type", "") == "text"
        )
        usage = getattr(message, "usage", None)
        return Completion(
            text,
            self.name,
            getattr(message, "model", self.model),
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(message, "stop_reason", None),
        )

    def describe(self) -> dict[str, Any]:
        env = self.settings.get("llm.anthropic.api_key_env", "ANTHROPIC_API_KEY")
        return {
            "provider": self.name,
            "model": self.model,
            "ready": bool(os.environ.get(env or "")) or self._client is not None,
            "detail": f"key from ${env}; thinking {self.thinking}",
        }


class _Http:
    """What the HTTP providers share: one client, and failures turned into sentences."""

    name = "http"
    model = ""

    def __init__(self, settings: Any, transport: Any = None) -> None:
        self.settings = settings
        self._transport = transport

    def _post(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        import httpx

        timeout = float(self.settings.int("llm.timeout_seconds", 120))
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as http:
                r = http.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f"{self.name} at {url} did not answer: {exc}") from exc
        if r.status_code >= 400:
            raise LlmUnavailable(
                f"{self.name} refused the request ({r.status_code}): {r.text[:300]}"
            )
        return dict(r.json())


class OpenAIProvider(_Http):
    """The Chat Completions API: OpenAI itself, and every server that speaks it (vLLM,
    LM Studio, llama.cpp's server, Together, Groq and the like) by ``llm.openai.base_url``."""

    name = "openai"
    model_setting = "llm.openai.model"

    def __init__(self, settings: Any, transport: Any = None) -> None:
        super().__init__(settings, transport)
        self.model = _model(settings, "llm.openai.model", "")
        self.base = (settings.get("llm.openai.base_url", "https://api.openai.com/v1") or "").rstrip(
            "/"
        )

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> "OpenAIProvider":
        return cls(settings, kw.get("transport"))

    def _url_and_headers(self) -> tuple[str, dict[str, str]]:
        env = (self.settings.get("llm.openai.api_key_env", "OPENAI_API_KEY") or "").strip()
        key = os.environ.get(env, "") if env else ""
        headers = {"Authorization": f"Bearer {key}"} if key else {}  # a local server needs none
        return f"{self.base}/chat/completions", headers

    def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float | None = None,
    ) -> Completion:
        url, headers = self._url_and_headers()  # where to send it is checked before what
        body: dict[str, Any] = {
            "model": _require_model(self.model, self.name, self.model_setting),
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": int(max_tokens),
        }
        if temperature is not None:
            body["temperature"] = float(temperature)
        data = self._post(url, body, headers)
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return Completion(
            str((choice.get("message") or {}).get("content") or ""),
            self.name,
            str(data.get("model") or self.model),
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            choice.get("finish_reason"),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "ready": bool(self.model),
            "detail": self.base,
        }


class AzureOpenAIProvider(OpenAIProvider):
    """Azure OpenAI: a deployment at a resource endpoint, keyed by ``api-key``."""

    name = "azure_openai"
    model_setting = "llm.azure_openai.deployment"

    def __init__(self, settings: Any, transport: Any = None) -> None:
        _Http.__init__(self, settings, transport)
        self.endpoint = (settings.get("llm.azure_openai.endpoint", "") or "").rstrip("/")
        self.deployment = (settings.get("llm.azure_openai.deployment", "") or "").strip()
        self.model = _model(settings, "llm.azure_openai.deployment", "")
        self.base = self.endpoint

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> "AzureOpenAIProvider":
        return cls(settings, kw.get("transport"))

    def _url_and_headers(self) -> tuple[str, dict[str, str]]:
        if not (self.endpoint and self.deployment):
            raise LlmUnavailable("Azure OpenAI needs llm.azure_openai.endpoint and .deployment")
        key = _key(self.settings, "llm.azure_openai.api_key_env", "AZURE_OPENAI_API_KEY", self.name)
        version = self.settings.get("llm.azure_openai.api_version", "2024-10-21")
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={version}"
        return url, {"api-key": key}


class OllamaProvider(_Http):
    """A model served by Ollama, on this machine or another."""

    name = "ollama"

    def __init__(self, settings: Any, transport: Any = None) -> None:
        super().__init__(settings, transport)
        self.model = _model(settings, "llm.ollama.model", "llama3.1")
        self.base = (settings.get("llm.ollama.base_url", "http://localhost:11434") or "").rstrip(
            "/"
        )

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> "OllamaProvider":
        return cls(settings, kw.get("transport"))

    def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float | None = None,
    ) -> Completion:
        options: dict[str, Any] = {"num_predict": int(max_tokens)}
        if temperature is not None:
            options["temperature"] = float(temperature)
        body = {
            "model": _require_model(self.model, self.name, "llm.ollama.model"),
            "stream": False,
            "options": options,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        data = self._post(f"{self.base}/api/chat", body, {})
        return Completion(
            str((data.get("message") or {}).get("content") or ""),
            self.name,
            str(data.get("model") or self.model),
            data.get("prompt_eval_count"),
            data.get("eval_count"),
            data.get("done_reason"),
        )

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "ready": True, "detail": self.base}


class BedrockProvider:
    """A model on Amazon Bedrock, through the Converse API (``boto3``)."""

    name = "bedrock"

    def __init__(self, settings: Any, client: Any = None) -> None:
        self.settings = settings
        self.model = _model(settings, "llm.bedrock.model", "")
        self._client = client

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> "BedrockProvider":
        return cls(settings, kw.get("client"))

    def _boto(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise LlmUnavailable(
                "llm.provider is bedrock, which needs 'boto3' (pip install boto3)"
            ) from exc
        profile = (self.settings.get("llm.bedrock.profile", "") or "").strip() or None
        session = boto3.Session(profile_name=profile)
        region = self.settings.get("llm.bedrock.region", "us-east-1")
        self._client = session.client("bedrock-runtime", region_name=region)
        return self._client

    def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float | None = None,
    ) -> Completion:
        config: dict[str, Any] = {"maxTokens": int(max_tokens)}
        if temperature is not None:
            config["temperature"] = float(temperature)
        kwargs: dict[str, Any] = {
            "modelId": _require_model(self.model, self.name, "llm.bedrock.model"),
            "messages": [{"role": m.role, "content": [{"text": m.content}]} for m in messages],
            "inferenceConfig": config,
        }
        if system:
            kwargs["system"] = [{"text": system}]
        try:
            data = self._boto().converse(**kwargs)
        except LlmUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - botocore's errors, said plainly
            raise LlmUnavailable(f"Bedrock did not answer: {type(exc).__name__}: {exc}") from exc
        blocks = ((data.get("output") or {}).get("message") or {}).get("content") or []
        usage = data.get("usage") or {}
        return Completion(
            "".join(str(b.get("text", "")) for b in blocks),
            self.name,
            self.model,
            usage.get("inputTokens"),
            usage.get("outputTokens"),
            data.get("stopReason"),
        )

    def describe(self) -> dict[str, Any]:
        try:
            import boto3  # noqa: F401

            ready = bool(self.model)
            detail = f"region {self.settings.get('llm.bedrock.region', 'us-east-1')}"
        except ImportError:
            ready, detail = self._client is not None, "boto3 is not installed"
        return {"provider": self.name, "model": self.model, "ready": ready, "detail": detail}


BUILT_IN: dict[str, Any] = {
    "none": NoProvider,
    "stub": StubProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "azure_openai": AzureOpenAIProvider,
    "ollama": OllamaProvider,
    "bedrock": BedrockProvider,
}
