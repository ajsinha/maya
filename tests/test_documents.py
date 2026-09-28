"""
Documents from a model's record, and the language models that draft them.

The providers are checked for exactly what they send and how they read what comes back,
through injected transports and clients -- no network. Model profiles are checked for what
they override. Documents are generated with the deterministic stub provider, with drafting
off, and from a firm's own template placed beside the built-ins; each renders as Markdown,
HTML and PDF, and approval needs a second person.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from maya.llm import profiles as prof
from maya.llm.base import LlmUnavailable, Message
from maya.llm.providers import (
    AnthropicProvider,
    AzureOpenAIProvider,
    BedrockProvider,
    NoProvider,
    OllamaProvider,
    OpenAIProvider,
    StubProvider,
)
from maya.testing.kit import complete_spec
from tests.conftest import World, build_platform


class FakeSettings(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def int(self, key, default=0):
        return int(super().get(key, default))

    def bool(self, key, default=False):
        return bool(super().get(key, default))


def _capture(reply: dict):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=reply)

    return seen, httpx.MockTransport(handler)


def test_openai_and_compatible_servers_get_chat_completions(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen, transport = _capture(
        {
            "model": "m1",
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2},
        }
    )
    s = FakeSettings({"llm.openai.model": "m1", "llm.openai.base_url": "http://vllm:8000/v1"})
    out = OpenAIProvider(s, transport).complete(
        "be brief", [Message("user", "hi")], max_tokens=50, temperature=0.1
    )
    assert seen["url"] == "http://vllm:8000/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer sk-test"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert seen["body"]["max_tokens"] == 50 and seen["body"]["temperature"] == 0.1
    assert (out.text, out.input_tokens, out.output_tokens, out.provider) == (
        "hello",
        7,
        2,
        "openai",
    )


def test_azure_ollama_and_bedrock_speak_their_own_dialects(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az")
    seen, transport = _capture({"choices": [{"message": {"content": "x"}}], "usage": {}})
    s = FakeSettings(
        {
            "llm.azure_openai.endpoint": "https://r.openai.azure.com",
            "llm.azure_openai.deployment": "gpt",
        }
    )
    AzureOpenAIProvider(s, transport).complete("", [Message("user", "q")], max_tokens=10)
    assert seen["url"].startswith(
        "https://r.openai.azure.com/openai/deployments/gpt/chat/completions?api-version="
    )
    assert seen["headers"]["api-key"] == "az"

    seen, transport = _capture(
        {"model": "llama3.1", "message": {"content": "ok"}, "eval_count": 3, "done_reason": "stop"}
    )
    out = OllamaProvider(
        FakeSettings({"llm.ollama.base_url": "http://box:11434"}), transport
    ).complete("sys", [Message("user", "q")], max_tokens=20, temperature=0.0)
    assert seen["url"] == "http://box:11434/api/chat" and seen["body"]["stream"] is False
    assert seen["body"]["options"] == {"num_predict": 20, "temperature": 0.0} and out.text == "ok"

    calls = {}

    class FakeBedrock:
        def converse(self, **kw):
            calls.update(kw)
            return {
                "output": {"message": {"content": [{"text": "b"}]}},
                "usage": {"inputTokens": 4, "outputTokens": 1},
                "stopReason": "end_turn",
            }

    out = BedrockProvider(FakeSettings({"llm.bedrock.model": "my-model"}), FakeBedrock()).complete(
        "sys", [Message("user", "q")], max_tokens=30
    )
    assert calls["modelId"] == "my-model" and calls["system"] == [{"text": "sys"}]
    assert calls["messages"] == [{"role": "user", "content": [{"text": "q"}]}]
    assert (out.text, out.input_tokens, out.stop_reason) == ("b", 4, "end_turn")


def test_anthropic_streams_through_the_sdk_with_adaptive_thinking():
    sent = {}

    class Stream:
        def __init__(self, **kw):
            sent.update(kw)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            blocks = [
                SimpleNamespace(type="thinking", text=""),
                SimpleNamespace(type="text", text="drafted"),
            ]
            return SimpleNamespace(
                content=blocks,
                model="claude-opus-5",
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=11, output_tokens=5),
            )

    client = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Stream(**kw)))
    out = AnthropicProvider(FakeSettings(), client).complete(
        "sys", [Message("user", "q")], max_tokens=99, temperature=0.3
    )
    assert sent["thinking"] == {"type": "adaptive"} and "temperature" not in sent
    assert sent["system"] == "sys" and sent["model"] == "claude-opus-5"
    assert (out.text, out.output_tokens) == ("drafted", 5)


def test_a_provider_that_cannot_answer_says_what_to_change(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    with pytest.raises(LlmUnavailable, match="llm.provider"):
        NoProvider().complete("", [Message("user", "q")])
    with pytest.raises(LlmUnavailable, match="endpoint"):
        AzureOpenAIProvider(FakeSettings(), None).complete("", [Message("user", "q")], max_tokens=5)
    with pytest.raises(LlmUnavailable, match="No model named"):
        OpenAIProvider(FakeSettings(), None).complete("", [Message("user", "q")], max_tokens=5)
    out = StubProvider().complete("", [Message("user", "Task: say hello.\nfacts")], max_tokens=5)
    assert out.text.startswith("Stub draft for say hello")


def test_a_profile_overrides_what_its_provider_reads(tmp_path):
    path = tmp_path / "profiles.yaml"
    path.write_text(
        "default: local\nprofiles:\n  local:\n    provider: ollama\n    model: qwen\n"
        "    temperature: 0.05\n    options: {base_url: 'http://gpu:11434'}\n",
        encoding="utf-8",
    )
    s = FakeSettings(
        {"llm.profiles_file": str(path), "llm.ollama.base_url": "http://localhost:11434"}
    )
    known, default = prof.load(s)
    assert default == "local" and set(known) == {"default", "local"}
    view = prof.ProfileSettings(s, known["local"])
    assert view.get("llm.ollama.base_url") == "http://gpu:11434"
    assert view.get("llm.model") == "qwen" and view.get("llm.temperature") == "0.05"
    assert OllamaProvider(view).base == "http://gpu:11434"
    path.write_text("profiles:\n  bad:\n    provider: ollama\n    colour: red\n", encoding="utf-8")
    with pytest.raises(ValidationFailed, match="unknown key"):
        prof.load(s)


@pytest.fixture(scope="module")
def estate(tmp_path_factory):
    custom = tmp_path_factory.mktemp("templates")
    (custom / "model_card.md.j2").write_text(
        "{# maya: kind=model_card; title=Firm card #}\n# Firm card for {{ facts.model.name }}\n\n"
        "{{ ai('summary', 'Summarise the model.') }}\n",
        encoding="utf-8",
    )
    (custom / "one_pager.md.j2").write_text(
        "{# maya: kind=model_card; title=One pager #}\n# {{ facts.model.name }} on one page\n",
        encoding="utf-8",
    )
    p = build_platform([f"--documents.template_dir={custom}"])
    w = World(p)
    p.access.create_namespace(w.admin, name="docs", preset="standard")
    p.models.create(
        w.mona,
        namespace="docs",
        name="linear_price",
        formula="y = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
        description="A price in x",
    )
    p.models.update_draft(w.mona, "docs/linear_price", spec_latex=complete_spec("linear_price"))
    p.models.transition(w.mona, "docs/linear_price", 1, "submit")
    p.models.transition(w.mgr, "docs/linear_price", 1, "approve")
    yield p, w
    p.shutdown()


def _generate(p, w, **kw):
    job = p.documents.submit(w.mona, "docs/linear_price", None, **kw)
    p.jobs.drain()
    with p.uow() as uow:
        done = uow.repo("jobs").get(job["id"])
    assert done["state"] == "succeeded", done.get("error")
    return p.documents.get(w.mona, done["result"]["document_id"])


def test_a_firms_template_replaces_the_built_in_and_adds_its_own(estate):
    p, w = estate
    rows = {t["name"]: t for t in p.documents.templates()}
    assert rows["model_card"]["origin"] == "custom (replaces the built-in)"
    assert rows["one_pager"]["kind"] == "model_card" and rows["one_pager"]["origin"] == "custom"
    assert rows["validation_report"]["origin"] == "built-in"
    p.ai.override = StubProvider()
    try:
        doc = _generate(p, w, kind="model_card")
    finally:
        p.ai.override = None
    assert doc["template_name"] == "model_card" and "Firm card for linear_price" in doc["markdown"]
    shown = p.documents.labelled_markdown(doc)
    assert "Drafted by stub · stub-1 from the recorded facts. Not yet reviewed" in shown
    with pytest.raises(ValidationFailed, match="is a model_card"):
        p.documents.submit(
            w.mona, "docs/linear_price", None, kind="validation_report", template="one_pager"
        )


def test_built_in_documents_render_in_three_formats_without_a_model(estate):
    p, w = estate
    for kind in ("validation_report", "model_documentation"):
        doc = _generate(p, w, kind=kind, use_ai=False)
        assert doc["provider"] is None and all(not s["drafted"] for s in doc["ai_sections"])
        assert (
            "Not drafted: this document was generated without a language model" in doc["markdown"]
        )
    report = next(
        d for d in p.documents.list(w.mona, "docs/linear_price") if d["kind"] == "validation_report"
    )
    md = p.documents.render(w.mona, report["id"], "md")["data"].decode()
    assert "## Evidence checklist" in md and "To be written by the validator" in md
    assert p.documents.render(w.mona, report["id"], "html")["data"].startswith(b"<!doctype html>")
    assert p.documents.render(w.mona, report["id"], "pdf")["data"][:5] == b"%PDF-"


def test_a_document_is_approved_by_a_second_person_and_the_label_says_so(estate):
    p, w = estate
    p.ai.override = StubProvider()
    try:
        doc = _generate(p, w, kind="model_card")
    finally:
        p.ai.override = None
    with pytest.raises(PermissionDenied, match="someone other"):
        p.documents.approve(w.mona, doc["id"])
    approved = p.documents.approve(w.mgr, doc["id"])
    assert approved["state"] == "approved" and approved["approved_by"] == "mgr"
    assert "reviewed and approved by mgr" in p.documents.labelled_markdown(
        p.documents.get(w.mona, doc["id"])
    )
    with p.uow() as uow:
        assert uow.repo("audit_events").find_one(action="ai.completion")
        assert uow.repo("audit_events").find_one(action="document.approved")


def test_the_gateway_reports_its_profiles_and_the_providers_on_offer(estate):
    p, _ = estate
    status = p.ai.status()
    assert status["default"] == "default" and status["drafting"] is False
    names = {r["name"] for r in status["providers"]}
    assert {"anthropic", "openai", "azure_openai", "ollama", "bedrock", "stub", "none"} <= names
    with pytest.raises(LlmUnavailable, match="No model profile named"):
        p.ai.resolve("nope")


def test_the_documents_tab_generates_views_and_downloads(estate):
    import re

    from starlette.testclient import TestClient

    from maya.server import build_app

    p, w = estate
    web = TestClient(build_app(p))
    page = web.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    web.post(
        "/login", data={"username": "admin", "password": "maya-dev-admin", "csrf_token": token}
    )
    tab = web.get("/models/docs/linear_price?tab=documents")
    assert tab.status_code == 200 and "How documents are made" in tab.text
    assert "not configured" in tab.text  # no model profile is ready in this estate
    token = re.search(r'name="csrf_token" value="([^"]+)"', tab.text).group(1)
    r = web.post(
        "/models/docs/linear_price/documents",
        data={"kind": "validation_report", "version_no": "1", "csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 303
    p.jobs.drain()
    doc = next(
        d for d in p.documents.list(w.admin, "docs/linear_price") if d["created_by"] == "admin"
    )
    view = web.get(f"/models/docs/linear_price/documents/{doc['id']}")
    assert view.status_code == 200 and "Validation report" in view.text
    md = web.get(f"/models/docs/linear_price/documents/{doc['id']}/download?format=md")
    assert md.status_code == 200 and b"## Evidence checklist" in md.content
