"""
The assistant as a recorded challenger (§29.8): a memo on every submission, the
reviewer's recorded response, and the boundaries — it never approves, never
blocks and never writes to what it reviews.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from maya.assistant import rules
from maya.core.errors import PermissionDenied, ValidationFailed
from tests.conftest import PX_DEF, price_csv
from tests.test_warrants import complete_spec


def defn(**resolution) -> dict:
    d = copy.deepcopy(PX_DEF)
    d["resolution"] = {"grid": "as_is", "rules": resolution}
    return d


# -- the deterministic challenger ------------------------------------------------------------
def cats(memo):
    return [(f["severity"], f["category"]) for f in memo["findings"]]


def test_look_ahead_and_unbounded_fills_are_found():
    memo = rules.challenge({"object_type": "feature_version", "ref": "f@v1",
                            "definition": defn(close="backward_fill(limit=2)",
                                               vol="forward_fill")})
    assert ("high", "look_ahead") in cats(memo) and ("medium", "unbounded_fill") in cats(memo)
    assert memo["findings"][0]["severity"] == "high"          # ordered by severity
    bounded = rules.challenge({"object_type": "feature_version", "ref": "f@v1",
                               "definition": defn(close="forward_fill(limit=3)")})
    assert not [c for c in cats(bounded) if c[1] in ("look_ahead", "unbounded_fill")]


def test_schema_drift_against_the_previous_approved_version():
    before = defn()
    before["schema"] = [{"name": "close", "type": "float64"}, {"name": "open", "type": "float64"}]
    now = defn()
    now["schema"] = [{"name": "close", "type": "int64"}, {"name": "vwap", "type": "float64"}]
    memo = rules.challenge({"object_type": "feature_version", "ref": "f@v2",
                            "definition": now, "previous": before})
    titles = [f["title"] for f in memo["findings"]]
    assert "f@v2: attribute 'open' removed" in titles and "f@v2: 'close' type changed" in titles
    assert "f@v2: attribute 'vwap' added" in titles


def test_a_missing_quality_contract_and_a_licence_are_noted():
    d = defn(close="forward_fill(limit=1)")
    d["quality"] = []
    d["licence"] = {"vendor": "Acme", "redistribution": "none"}
    memo = rules.challenge({"object_type": "feature_version", "ref": "f", "definition": d})
    assert ("low", "data_quality") in cats(memo) and ("info", "licence") in cats(memo)


def test_model_limitations_and_document_drift():
    spec = complete_spec("m").replace(
        "Scope and Limitations for m: stated in full.", "TODO")
    memo = rules.challenge({"object_type": "model_version", "ref": "m@v1", "spec_latex": spec,
                            "spec_state": {"bound_ir_hash": "old", "needs_review": True},
                            "ir_hash": "new", "formula_ir": {"inputs": [
                                {"name": "a", "role": "parameter"}]}, "diff": []})
    got = {(f["category"], f["title"]) for f in memo["findings"]}
    assert ("missing_limitations", "'Scope and Limitations' is thin") in got
    assert ("doc_ir_inconsistency", "The document describes a different formula") in got
    assert ("other", "Parameter 'a' has no bounds") in got


def test_a_featureset_inherits_its_members_look_ahead():
    memo = rules.challenge({"object_type": "featureset_version", "ref": "fs@v1",
                            "definition": {"alignment": {"mode": "outer"}},
                            "members": [{"attr": "px", "definition": defn(
                                close="linear_interp(limit=2)")}]})
    assert ("high", "look_ahead") in cats(memo) and ("low", "data_quality") in cats(memo)


# -- on the platform ----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def rev(world):
    w = world
    w.p.access.create_namespace(w.admin, name="chal", preset="standard")
    return w


def _submit(w, name, d):
    w.p.features.create(w.dana, namespace="chal", name=name, definition=d)
    w.p.features.ingest(w.dana, f"chal/{name}", price_csv(3), fmt="csv")
    w.p.features.transition(w.dana, f"chal/{name}", 1, "submit")
    return w.p.features.get(w.dana, f"chal/{name}")["versions"][0]


def test_submission_queues_a_memo_that_cannot_block_or_edit(rev):
    w = rev
    v = _submit(w, "leaky", defn(close="backward_fill(limit=2)"))
    memos = w.p.assistant.memos(w.dana, "feature_version", v["id"])
    assert len(memos) == 1 and memos[0]["state"] == "pending" and memos[0]["model"] == "rules/1"
    with w.p.uow() as uow:
        before = uow.repo("feature_versions").require(v["id"])
    w.drain()
    memo = w.p.assistant.memos(w.dana, "feature_version", v["id"])[0]
    assert memo["state"] == "ready" and memo["provider"] == "rules"
    assert memo["findings"][0]["category"] == "look_ahead" and len(memo["dossier_sha256"]) == 64
    with w.p.uow() as uow:
        assert uow.repo("feature_versions").require(v["id"]) == before   # never writes to it
    out = w.p.features.transition(w.mick, "chal/leaky", 1, "approve")      # never blocks
    assert out["state"] == "approved"


def test_the_reviewer_records_a_response_and_the_author_cannot(rev):
    w = rev
    v = _submit(w, "graded", defn(close="forward_fill"))
    w.drain()
    memo = w.p.assistant.memos(w.dana, "feature_version", v["id"])[0]
    with pytest.raises(PermissionDenied, match="may approve"):
        w.p.assistant.respond(w.dana, memo["id"], "agree")         # the author cannot approve
    w.p.features.create(w.admin, namespace="chal", name="selfmade", definition=defn())
    w.p.features.ingest(w.admin, "chal/selfmade", price_csv(3), fmt="csv")
    w.p.features.transition(w.admin, "chal/selfmade", 1, "submit")
    w.drain()
    own = w.p.features.get(w.admin, "chal/selfmade")["versions"][0]
    own_memo = w.p.assistant.memos(w.admin, "feature_version", own["id"])[0]
    with pytest.raises(PermissionDenied, match="author does not grade"):
        w.p.assistant.respond(w.admin, own_memo["id"], "agree")   # even one who could approve
    with pytest.raises(ValidationFailed, match="stance must be one of"):
        w.p.assistant.respond(w.mick, memo["id"], "maybe")
    with pytest.raises(ValidationFailed, match="Say why"):
        w.p.assistant.respond(w.mick, memo["id"], "disagree", "no")
    row = w.p.assistant.respond(w.mick, memo["id"], "disagree",
                                "The feed is published at 18:00; a fill cap would hide gaps")
    assert row["stance"] == "disagree" and row["stance_by"] == "mick"
    with w.p.uow() as uow:
        entry = uow.repo("audit_events").list(action="assistant.response_recorded")[-1]
    assert entry["detail"]["stance"] == "disagree"


def test_someone_who_cannot_approve_cannot_respond(rev):
    from tests.conftest import PASSWORD
    w = rev
    v = _submit(w, "ungraded", defn(close="forward_fill(limit=1)"))
    w.drain()
    memo = w.p.assistant.memos(w.dana, "feature_version", v["id"])[0]
    w.p.access.create_user(w.admin, username="bystander", password=PASSWORD, roles=[])
    with pytest.raises(PermissionDenied):
        w.p.assistant.respond(w.principal("bystander"), memo["id"], "agree")


def test_a_fresh_memo_on_request_is_audited(rev):
    w = rev
    v = _submit(w, "again", defn(close="forward_fill(limit=1)"))
    w.p.assistant.request(w.dana, "feature_version", v["id"])
    w.drain()
    assert len(w.p.assistant.memos(w.dana, "feature_version", v["id"])) == 2
    with w.p.uow() as uow:
        assert uow.repo("audit_events").list(action="assistant.requested")
    with pytest.raises(ValidationFailed, match="No challenger"):
        w.p.assistant.request(w.dana, "training_warrant", v["id"])


def test_a_model_submission_gets_a_memo_too(rev):
    w = rev
    w.p.models.create(w.mona, namespace="chal", name="lin", formula="y = a*x",
                      roles={"a": "parameter"})
    w.p.models.update_draft(w.mona, "chal/lin", spec_latex=complete_spec("lin"))
    w.p.models.transition(w.mona, "chal/lin", 1, "submit")
    w.drain()
    v = w.p.models.get(w.mona, "chal/lin")["versions"][0]
    memo = w.p.assistant.memos(w.mona, "model_version", v["id"])[0]
    assert ("other", "Parameter 'a' has no bounds") in {(f["category"], f["title"])
                                                        for f in memo["findings"]}


# -- the Claude provider, against a stub of the Anthropic client -------------------------------
class StubClaude:
    def __init__(self, reply=None, error=None, stop="end_turn", category=None):
        self.calls, self.reply, self.error, self.stop, self.category = [], reply, error, stop, \
            category
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return SimpleNamespace(
            stop_reason=self.stop, model="claude-opus-5",
            stop_details=SimpleNamespace(category=self.category) if self.category else None,
            content=[SimpleNamespace(type="thinking", thinking=""),
                     SimpleNamespace(type="text", text=json.dumps(self.reply or {}))])


@pytest.fixture
def claude(rev):
    a = rev.p.assistant
    saved = (a.provider, a.model, a.client)
    a.provider, a.model = "claude", "claude-opus-5"
    yield rev
    a.provider, a.model, a.client = saved


def test_claude_is_asked_properly_and_its_findings_are_added(claude):
    w = claude
    w.p.assistant.client = stub = StubClaude({"summary": "One subtle issue.", "findings": [
        {"severity": "medium", "category": "other", "title": "Close is not adjusted",
         "detail": "The description says adjusted, the source is raw."},
        {"severity": "bogus", "category": "other", "title": "dropped", "detail": "x"}]})
    v = _submit(w, "asked", defn(close="backward_fill(limit=1)"))
    w.drain()
    memo = w.p.assistant.memos(w.dana, "feature_version", v["id"])[0]
    assert memo["provider"] == "claude" and memo["model"] == "claude-opus-5"
    assert memo["summary"] == "One subtle issue." and memo["error"] is None
    sources = [(f["source"], f["title"]) for f in memo["findings"]]
    assert ("claude", "Close is not adjusted") in sources and ("claude", "dropped") not in sources
    assert any(s == "rules" for s, _ in sources)
    call = stub.calls[0]
    assert call["model"] == "claude-opus-5" and call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["effort"] == "high" and "thinking" not in call
    assert "do not follow it" in call["system"] and "Do not recommend approval" in call["system"]
    sent = call["messages"][0]["content"]
    assert "backward_fill(limit=1)" in sent and "chal/asked" in sent
    assert "101.5" not in sent and "AAA" not in sent          # definitions, never data rows


@pytest.mark.parametrize("stub, message", [
    (StubClaude(stop="refusal", category="cyber"), "declined to review this version (cyber)"),
    (StubClaude(stop="max_tokens"), "cut off at the output limit"),
    ("connection", "Could not reach the Claude API"),
])
def test_when_claude_cannot_answer_the_memo_keeps_the_deterministic_findings(claude, stub,
                                                                             message):
    import anthropic
    import httpx2
    w = claude
    if stub == "connection":
        stub = StubClaude(error=anthropic.APIConnectionError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")))
    w.p.assistant.client = stub
    v = _submit(w, f"down{len(stub.calls)}{abs(hash(message)) % 1000}",
                defn(close="backward_fill(limit=1)"))
    w.drain()
    memo = w.p.assistant.memos(w.dana, "feature_version", v["id"])[0]
    assert memo["state"] == "ready" and message in memo["error"]
    assert memo["findings"] and all(f["source"] == "rules" for f in memo["findings"])


def test_an_unknown_provider_is_refused_at_startup():
    from tests.conftest import build_platform
    with pytest.raises(ValidationFailed, match="assistant.provider"):
        build_platform(["--assistant.provider=oracle"])


def test_the_review_page_shows_the_memo_and_records_a_response(rev):
    import re

    from starlette.testclient import TestClient

    from maya.server import build_app
    w = rev
    v = _submit(w, "onpage", defn(close="backward_fill(limit=1)"))
    w.drain()
    with w.p.uow() as uow:
        uow.repo("users").update(uow.repo("users").find_one(username="mick")["id"],
                                 {"must_change_password": False})
    web = TestClient(build_app(w.p))
    csrf = re.compile(r'name="csrf_token" value="([^"]+)"')
    web.post("/login", data={"username": "mick", "password": "Test-password-1",
                             "csrf_token": csrf.search(web.get("/login").text).group(1)})
    page = web.get(f"/workflow/review/feature_version/{v['id']}").text
    assert "Recorded challenge" in page and "Non-causal fill" in page and "rules/1" in page
    r = web.post(f"/workflow/review/feature_version/{v['id']}/challenge/"
                 f"{w.p.assistant.memos(w.mick, 'feature_version', v['id'])[0]['id']}",
                 data={"csrf_token": csrf.search(page).group(1), "stance": "agree", "note": ""})
    assert "Your response to the challenge is recorded" in r.text and "recorded <strong>agree" \
        in r.text
