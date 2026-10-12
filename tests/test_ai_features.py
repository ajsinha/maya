"""
Plain-English features: ask, explain, narrate, draft a formula, and MAYA governing its own AI.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json

import pytest

from maya.core.errors import ValidationFailed
from maya.llm.base import Completion
from tests.conftest import PX_DEF, World, approved_feature, build_platform, price_csv


class Scripted:
    """A provider that answers from a queue, recording each prompt."""

    name, model = "scripted", "scripted-1"

    def __init__(self, *answers: str) -> None:
        self.answers, self.prompts = list(answers), []

    def complete(self, system, messages, **_):
        self.prompts.append(messages[-1].content)
        return Completion(self.answers.pop(0), self.name, self.model, 10, 10, "end")

    def describe(self):
        return {"provider": self.name, "model": self.model, "ready": True, "detail": ""}


@pytest.fixture(scope="module")
def w():
    p = build_platform(["--ai.rate.per_user_per_minute=0"])
    world = World(p)
    p.access.create_namespace(world.admin, name="eq", preset="standard")
    p.access.create_namespace(world.admin, name="secret", preset="standard")
    approved_feature(world, "px", price_csv())
    p.features.create(world.dana, namespace="eq", name="draft_px", definition=PX_DEF)
    yield world
    p.shutdown()


def test_a_common_phrasing_is_read_without_any_model(w):
    w.p.ai.override = Scripted()  # would fail if asked
    out = w.p.ai_features.ask(w.dana, "approved features in eq, newest first")
    assert out["how"] == "phrase" and out["model_attempts"] == 0
    assert out["query"]["kind"] == "feature"
    assert {"field": "latest_state", "op": "eq", "value": "approved"} in out["query"]["filters"]
    assert [r["name"] for r in out["rows"]] == ["px"]
    assert "newest first" in out["read_as"]


def test_a_query_runs_as_the_person_asking(w):
    # the admin reads everything; a person with no grant on a namespace sees none of it
    w.p.features.create(w.dana, namespace="secret", name="hidden", definition=PX_DEF)
    everyone = {r["name"] for r in w.p.ai_features.run(w.admin, {"kind": "feature"})}
    assert "hidden" in everyone
    mick = {r["name"] for r in w.p.ai_features.run(w.mick, {"kind": "feature", "limit": 200})}
    assert mick <= everyone


def test_a_query_outside_the_vocabulary_is_refused_naming_every_problem(w):
    with pytest.raises(ValidationFailed) as exc:
        w.p.ai_features.validate(
            w.dana,
            {
                "kind": "feature",
                "filters": [
                    {"field": "password", "op": "eq", "value": 1},
                    {"field": "name", "op": "drop", "value": 1},
                ],
            },
        )
    assert "password" in exc.value.message and "drop" in exc.value.message
    with pytest.raises(ValidationFailed, match="Unknown kind"):
        w.p.ai_features.validate(w.dana, {"kind": "users"})


def test_the_model_path_is_checked_and_retried_with_the_refusal(w):
    bad = json.dumps({"kind": "feature", "filters": [{"field": "salary", "op": "eq", "value": 1}]})
    good = json.dumps(
        {
            "kind": "feature",
            "filters": [{"field": "name", "op": "contains", "value": "px"}],
            "limit": 10,
        }
    )
    w.p.ai.override = Scripted(bad, good)
    out = w.p.ai_features.ask(w.dana, "which things mention px")
    assert out["how"] == "model" and {r["name"] for r in out["rows"]} >= {"px", "draft_px"}
    second = w.p.ai.override.prompts[-1]
    assert "REFUSED" in second and "salary" in second  # the refusal went back
    assert "TASK: ask-query" in w.p.ai.override.prompts[0]
    assert "close" not in w.p.ai.override.prompts[0].split("VOCABULARY")[1].split("QUESTION")[0]


def test_an_explanation_names_any_figure_not_in_the_record(w):
    w.p.ai.override = Scripted("px is approved, with 7 versions and a 42% fill rate.")
    out = w.p.ai_features.explain(w.dana, "feature", "eq/px")
    assert out["verified"] is False and set(out["unverified_numbers"]) >= {"7", "42"}
    w.p.ai.override = Scripted("px is an approved feature in eq.")
    assert w.p.ai_features.explain(w.dana, "feature", "eq/px")["verified"] is True
    with pytest.raises(ValidationFailed, match="explains"):
        w.p.ai_features.explain(w.dana, "user", "admin")


def test_a_formula_drafted_from_words_is_parsed_before_anyone_sees_it(w):
    broken = json.dumps({"formula": "y = \\unknownmacro{x}", "roles": {}})
    fine = json.dumps(
        {
            "formula": "p = 1/(1 + e^{-(a + b x)})",
            "roles": {"a": "parameter", "b": "parameter", "x": "feature"},
        }
    )
    w.p.ai.override = Scripted(broken, fine)
    out = w.p.ai_features.draft_formula(w.mona, "a logistic probability from x")
    assert out["attempts"] == 2 and out["kernel"]["ir"]
    assert "REFUSED" in w.p.ai.override.prompts[-1]


def test_maya_registers_its_own_ai_as_llm_applications(tmp_path):
    rules = tmp_path / "r.rules.yaml"
    rules.write_text('default: \'{"kind": "model", "filters": []}\'\n')
    p = build_platform(["--llm.provider=mock", f"--llm.mock.rules_file={rules}"])
    try:
        world = World(p)
        p.access.create_namespace(world.admin, name="ops", preset="standard")
        out = p.ai_features.register_self(world.mona, "ops")
        refs = {r["ref"] for r in out["registered"]}
        assert refs == {"ops/maya-ask", "ops/maya-explain", "ops/maya-draft-formula"}
        app = p.llm.get_app(world.mona, "ops/maya-ask")
        assert app["versions"][0]["provider"] == "mock"
        assert "structured" in app["use_case"]
        again = p.ai_features.register_self(world.mona, "ops")  # idempotent: updates drafts
        assert len(again["registered"]) == 3
    finally:
        p.shutdown()


def test_the_pages_render(w):
    from starlette.testclient import TestClient

    from maya.server import build_app
    from tests.test_web import _login

    with w.p.uow() as uow:
        user = uow.repo("users").find_one(username="admin")
        uow.repo("users").update(user["id"], {"must_change_password": False})
    web = TestClient(build_app(w.p))
    _login(web)
    page = web.get("/ask?q=approved+features+in+eq")
    assert page.status_code == 200 and "The query MAYA ran" in page.text and "px" in page.text
    assert "What you can ask about" in page.text
    assert web.get("/ask").status_code == 200
