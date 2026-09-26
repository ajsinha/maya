"""
LLM applications governed like models: sealed versions, evaluation sets as holdouts,
deterministic checks and guardrails, recorded and live runs, approval on evidence.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from maya.services.llm import guardrail_violations, pii_found, render, template_fields

APP = "eq/complaints"
CASES = [
    {
        "id": "refund",
        "vars": {"complaint": "I was charged twice for my card fee."},
        "checks": [{"kind": "contains", "value": "refund"}, {"kind": "max_chars", "value": 400}],
    },
    {
        "id": "json",
        "vars": {"complaint": "Where is my statement?"},
        "checks": [{"kind": "json", "value": ["category"]}],
    },
]
GOOD = {
    "refund": "We are sorry. A refund of the duplicate fee is on its way.",
    "json": '{"category": "statements", "urgency": "low"}',
}


def test_checks_guardrails_and_templates():
    assert template_fields("Classify: {complaint} ({channel})") == ["complaint", "channel"]
    with pytest.raises(ValidationFailed, match="plain placeholder"):
        template_fields("{complaint!r}")
    with pytest.raises(ValidationFailed, match="does not supply"):
        render("Classify: {complaint}", {})
    assert pii_found("mail me at a.b@example.com") == ["email address"]
    assert "card number" in pii_found("card 4111 1111 1111 1111 please")
    assert "card number" not in pii_found("order 1234 5678 9012 3456")  # fails Luhn
    assert guardrail_violations({"blocked_terms": ["guarantee"]}, "We guarantee it") == [
        "blocked term 'guarantee'"
    ]


@pytest.fixture(scope="module")
def llm(world):
    w = world
    w.p.llm.create_app(
        w.mona, namespace="eq", name="complaints", use_case="triage retail complaints"
    )
    return w


def _version(w, template="Reply to this complaint: {complaint}"):
    return w.p.llm.save_version(
        w.mona,
        APP,
        provider="anthropic",
        model="claude-sonnet-5",
        system_prompt="You are a careful complaints handler.",
        prompt_template=template,
        parameters={"max_tokens": 300},
        guardrails={"blocked_terms": ["guarantee"]},
    )


def test_a_version_is_approved_only_on_evidence_by_someone_independent(llm):
    w = llm
    v = _version(w)
    assert v["version_no"] == 1 and v["state"] == "draft" and len(v["definition_hash"]) == 64
    w.p.llm.save_eval_set(w.mona, APP, name="core", cases=CASES)
    with pytest.raises(NotApproved, match="evaluation run"):
        w.p.llm.submit(w.mona, APP, 1)

    bad = dict(GOOD, refund="We guarantee a refund. Call +44 20 7946 0958.")
    run = w.p.llm.run_eval(w.mona, APP, 1, "core", responses=bad)
    assert run["mode"] == "recorded" and run["passed"] == 1 and run["guardrail_violations"] == 1
    failed = next(r for r in run["results"] if r["case"] == "refund")
    assert "blocked term 'guarantee'" in failed["guardrails"]
    assert "personal data: phone number" in failed["guardrails"]
    with pytest.raises(NotApproved):
        w.p.llm.submit(w.mona, APP, 1)

    good = w.p.llm.run_eval(w.mona, APP, 1, "core", responses=GOOD)
    assert good["pass_rate"] == 1.0
    assert w.p.llm.submit(w.mona, APP, 1)["state"] == "in_review"
    with pytest.raises(PermissionDenied, match="model manager"):
        w.p.llm.decide(w.devi, APP, 1, "approve", "fine")
    with pytest.raises(ValidationFailed):
        w.p.llm.decide(w.mgr, APP, 1, "approve", " ")
    done = w.p.llm.decide(w.mgr, APP, 1, "approve", "every case passes")
    assert done["state"] == "approved" and done["decided_by"] == "mgr"


def test_any_change_is_a_new_version_and_an_edited_eval_set_voids_old_evidence(llm):
    w = llm
    v2 = _version(w, template="Answer briefly: {complaint}")
    assert v2["version_no"] == 2 and v2["state"] == "draft"
    w.p.llm.run_eval(w.mona, APP, 2, "core", responses=GOOD)
    w.p.llm.save_eval_set(w.mona, APP, name="core", cases=CASES[:1])  # the set changed
    with pytest.raises(NotApproved):
        w.p.llm.submit(w.mona, APP, 2)
    with pytest.raises(ValidationFailed, match="missing"):
        w.p.llm.run_eval(w.mona, APP, 2, "core", responses={})
    with pytest.raises(ValidationFailed, match="no checks"):
        w.p.llm.save_eval_set(w.mona, APP, name="empty", cases=[{"id": "x", "vars": {}}])


def test_a_live_run_calls_the_provider_through_the_runner(llm):
    w = llm
    prompts = []

    def runner(version, prompt):
        prompts.append(prompt)
        return {"text": "A refund is on its way.", "stop_reason": "end_turn", "output_tokens": 7}

    w.p.llm.runner = runner
    try:
        run = w.p.llm.run_eval(w.mona, APP, 2, "core")
    finally:
        w.p.llm.runner = None
    assert run["mode"] == "live" and run["pass_rate"] == 1.0
    assert prompts == ["Answer briefly: I was charged twice for my card fee."]
    assert run["results"][0]["stop_reason"] == "end_turn"
    assert w.p.llm.submit(w.mona, APP, 2)["state"] == "in_review"
    w.p.llm.decide(w.mgr, APP, 2, "approve", "live run clean")
    states = {v["version_no"]: v["state"] for v in w.p.llm.get_app(w.mona, APP)["versions"]}
    assert states == {1: "retired", 2: "approved"}  # one approved version at a time


def test_mayas_own_calls_are_limited_to_providers_it_integrates(llm):
    w = llm
    w.p.llm.save_version(
        w.mona, APP, provider="openai", model="gpt-x", prompt_template="Q: {complaint}"
    )
    with pytest.raises(ValidationFailed, match="recorded run"):
        w.p.llm.run_eval(w.mona, APP, 3, "core")
    apps = w.p.llm.list_apps(w.devi)
    row = next(a for a in apps if a["name"] == "complaints")
    assert row["approved"]["version_no"] == 2 and row["latest"]["version_no"] == 3


def test_the_claude_completion_sends_what_the_version_declares():
    from types import SimpleNamespace

    from maya.assistant.claude import complete

    sent = {}

    class Messages:
        def create(self, **kw):
            sent.update(kw)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Hello")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=12, output_tokens=3),
            )

    out = complete(
        SimpleNamespace(messages=Messages()), model="claude-sonnet-5", system="S", prompt="P"
    )
    assert out == {
        "text": "Hello",
        "stop_reason": "end_turn",
        "input_tokens": 12,
        "output_tokens": 3,
    }
    assert "temperature" not in sent and sent["system"] == "S"
    assert sent["messages"] == [{"role": "user", "content": "P"}]
    sent.clear()
    complete(SimpleNamespace(messages=Messages()), model="m", system="", prompt="P", temperature=0)
    assert sent["temperature"] == 0.0 and "system" not in sent


def test_llm_applications_appear_in_the_inventory(llm):
    import json

    w = llm
    doc = json.loads(w.p.inventory.export(w.admin, "json", "ss1-23")["data"])
    row = next(r for r in doc["rows"] if r["name"] == "complaints")
    assert row["kind"] == "llm application" and row["status"] == "approved"
    assert row["implementation_tested"].startswith("evaluated: ")
    assert row["tier"] is None and row["model_ref"] == "maya://llm/eq/complaints"


def test_a_validator_may_add_to_the_evaluation_set_but_a_developer_may_not(llm):
    w = llm
    w.p.llm.save_eval_set(w.mgr, APP, name="validator", cases=CASES[:1])
    with pytest.raises(PermissionDenied):
        w.p.llm.save_eval_set(w.devi, APP, name="developer", cases=CASES[:1])
