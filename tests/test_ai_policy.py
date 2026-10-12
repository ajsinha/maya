"""
The AI policy and the wider provider set: who may ask, how often, how much, what is masked,
and the providers and profile files drishti's model calls for.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json

import httpx
import pytest

from maya.core.errors import PermissionDenied, QuotaExceeded
from maya.llm import policy as pol
from maya.llm.base import Completion
from tests.conftest import World, build_platform


class Capture:
    """A provider that records what it was sent and answers with fixed token counts."""

    name, model = "capture", "capture-1"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, system, messages, **_):
        self.prompts.append(messages[-1].content)
        return Completion("ok", self.name, self.model, 1000, 500, "end")

    def describe(self):
        return {"provider": self.name, "model": self.model, "ready": True, "detail": ""}


@pytest.fixture()
def w():
    p = build_platform(
        ["--ai.rate.per_user_per_minute=3", "--ai.daily_token_cap=0", "--ai.mask.fields=salary"]
    )
    world = World(p)
    world.p.ai.override = Capture()
    yield world
    p.shutdown()


def test_each_purpose_belongs_to_a_feature():
    assert pol.feature_of("ai.test") == "admin"
    assert pol.feature_of("document:model_card:intended_use") == "documents"
    assert pol.feature_of("assistant.challenge") == "challenger"
    assert pol.feature_of("llm.evaluation") == "llm_eval"
    assert pol.feature_of("ask:estate") == "ask"
    assert pol.feature_of("something-new") == "draft"  # unknown: the strictest roles


def test_a_role_outside_the_feature_is_refused_and_the_refusal_audited(w):
    with pytest.raises(PermissionDenied, match="may not use the AI feature 'documents'"):
        w.p.ai.complete(w.dana, purpose="document:model_card:x", system="", prompt="hello")
    with w.p.uow() as uow:
        refused = uow.repo("audit_events").list(action="ai.denied")
    assert refused and refused[-1]["detail"]["feature"] == "documents"
    # anyone signed in may ask; MAYA itself (no principal) is not role-checked
    assert w.p.ai.complete(w.dana, purpose="ask:estate", system="", prompt="hi").text == "ok"
    assert w.p.ai.complete(None, purpose="assistant.challenge", system="", prompt="x").text == "ok"


def test_the_rate_limit_stops_a_runaway_caller(w):
    for _ in range(3):
        w.p.ai.complete(w.mona, purpose="ask", system="", prompt="q")
    with pytest.raises(QuotaExceeded, match="per_user_per_minute"):
        w.p.ai.complete(w.mona, purpose="ask", system="", prompt="q")


def test_the_daily_budgets_refuse_once_spent():
    p = build_platform(["--ai.daily_token_cap=1200", "--ai.rate.per_user_per_minute=0"])
    try:
        w = World(p)
        p.ai.override = Capture()
        p.ai.complete(w.mona, purpose="ask", system="", prompt="q")  # 1,500 tokens: over the cap
        with pytest.raises(QuotaExceeded, match="token budget"):
            p.ai.complete(w.mona, purpose="ask", system="", prompt="q")
        assert p.ai.policy()["today"]["tokens"] == 1500
    finally:
        p.shutdown()


def test_personal_data_and_named_fields_never_reach_the_model(w):
    prompt = (
        "Customer jo@example.com paid with 4111 1111 1111 1111, call +44 20 7946 0958; "
        "salary: 85000. Account 123456789012."
    )
    w.p.ai.complete(w.mona, purpose="ask", system="", prompt=prompt)
    sent = w.p.ai.override.prompts[-1]
    for leak in ("jo@example.com", "4111 1111 1111 1111", "7946 0958", "85000", "123456789012"):
        assert leak not in sent, (leak, sent)
    assert "[email]" in sent and "[card]" in sent and "salary: [masked]" in sent
    with w.p.uow() as uow:
        done = uow.repo("audit_events").list(action="ai.completion")
    assert done[-1]["detail"]["masked"] >= 4 and done[-1]["detail"]["feature"] == "ask"
    # a 16-digit number that fails the Luhn check is not a card, and is left alone as a card
    assert "[card]" not in pol.mask("ref 1234 5678 9012 3456").text


def test_a_priced_profile_records_what_each_call_cost():
    assert pol.cost_usd({"price_in_per_mtok": 3, "price_out_per_mtok": 15}, 1000, 500) == 0.0105
    assert pol.cost_usd({}, 1000, 500) is None


def test_usage_and_policy_are_reported(w):
    w.p.ai.complete(w.mona, purpose="ask", system="", prompt="q")
    report = w.p.ai.usage(w.admin, days=1)
    assert report["calls"] >= 1 and report["by_feature"][0]["feature"] == "ask"
    with pytest.raises(PermissionDenied):
        w.p.ai.usage(w.mona)
    shown = w.p.ai.policy()
    assert {f["feature"] for f in shown["features"]} == set(pol.FEATURES)
    assert shown["mask_fields"] == ["salary"]


def test_every_drishti_provider_is_registered_and_off_by_default():
    from maya.llm.providers_extra import ALL, COMPATIBLE

    p = build_platform()
    try:
        names = {r["name"] for r in p.ai.status(None)["providers"]}
        for want in ("gemini", "cohere", "mock", *COMPATIBLE):
            assert want in names and want in ALL, want
        assert p.ai.status(None)["profiles"][0]["provider"] == "none"  # nothing on by default
    finally:
        p.shutdown()


def test_gemini_cohere_and_a_named_compatible_service_send_what_their_apis_expect(monkeypatch):
    from maya.llm.base import Message
    from maya.llm.providers_extra import EXTRA

    seen = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"] = str(request.url), request.headers
        seen["body"] = json.loads(request.content)
        if "generateContent" in seen["url"]:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": "hi"}]}, "finishReason": "STOP"}
                    ],
                    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
                },
            )
        if seen["url"].endswith("/chat"):
            return httpx.Response(
                200,
                json={
                    "message": {"content": [{"text": "hi"}]},
                    "usage": {"tokens": {"input_tokens": 3, "output_tokens": 1}},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    class S(dict):
        def get(self, key, default=None):
            return super().get(key, default)

        def int(self, key, default=0):
            return int(super().get(key, default))

    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("COHERE_API_KEY", "c")
    monkeypatch.setenv("GROQ_API_KEY", "q")
    t = httpx.MockTransport(answer)
    gem = EXTRA["gemini"](S({"llm.gemini.model": "gemini-x"}), t)
    out = gem.complete("be brief", [Message("user", "hello")], max_tokens=20)
    assert out.text == "hi" and ":generateContent" in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "g" and seen["body"]["systemInstruction"]
    coh = EXTRA["cohere"](S({"llm.cohere.model": "command-x"}), t)
    assert coh.complete("", [Message("user", "hello")], max_tokens=20).input_tokens == 3
    assert seen["headers"]["authorization"] == "Bearer c"
    groq = EXTRA["groq"](S({"llm.groq.model": "llama-x"}), t)
    assert groq.complete("", [Message("user", "hello")], max_tokens=20).text == "hi"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert groq.name == "groq"


def test_profiles_live_one_to_a_file_and_the_mock_answers_from_rules(tmp_path):
    folder = tmp_path / "ai"
    folder.mkdir()
    (folder / "offline.yaml").write_text(
        "provider: mock\nmodel: mock-1\noptions:\n  rules_file: "
        + str(folder / "m.rules.yaml")
        + "\n"
    )
    (folder / "m.rules.yaml").write_text(
        "default: no rule\nrules:\n  - match: 'single word: ready'\n    reply: ready\n"
    )
    p = build_platform([f"--llm.profiles_dir={folder}", "--llm.profile=offline"])
    try:
        w = World(p)
        profiles = {r["name"]: r for r in p.ai.status(None)["profiles"]}
        assert "offline" in profiles and "m.rules" not in profiles
        assert p.ai.test(w.admin, "offline")["ok"] is True
        out = p.ai.complete(w.mona, purpose="ask", system="", prompt="anything else")
        assert out.text == "no rule"
    finally:
        p.shutdown()
