"""
Defects found while documenting how MAYA fits together, each pinned by a test.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from maya.core.errors import ClientTooOld, NotApproved


def test_a_retired_execution_warrant_is_not_live_even_when_sealed():
    from maya.services.execution import ExecutionService
    from maya.services.warrants import WarrantService

    now = dt.datetime.now(dt.timezone.utc)
    ew = {"state": "retired", "sealed_at": now, "valid_to": now + dt.timedelta(days=30)}
    assert ExecutionService.status(ew) == "retired"
    assert ExecutionService.status({**ew, "state": "approved"}) == "live"
    assert WarrantService.status({"state": "withdrawn", "sealed_at": now}) == "withdrawn"
    service = ExecutionService.__new__(ExecutionService)
    with pytest.raises(NotApproved, match="retired"):
        service.check({**ew, "spec": {"environments": ["prod"], "contact": "x"}}, "prod")


def test_a_document_template_cannot_reach_python_internals(tmp_path):
    from jinja2.exceptions import SecurityError

    from maya.documents.render import Library

    (tmp_path / "model_card.md.j2").write_text(
        "{# maya: kind=model_card; title=Evil #}\n{{ ''.__class__.__mro__[1].__subclasses__() }}\n",
        encoding="utf-8",
    )
    lib = Library(tmp_path)
    with pytest.raises(SecurityError):
        lib.render(lib.get("model_card"), {})


def test_cloning_a_handle_made_from_a_full_reference_keeps_its_namespace():
    from maya.sdk.handles import FeatureHandle

    made = {}

    def create(namespace, name, definition):
        made.update(namespace=namespace, name=name, definition=definition)
        return {"name": name}

    client = SimpleNamespace(features=SimpleNamespace(create=create))
    handle = FeatureHandle.of(
        client, {"latest_version": 3}, ref="maya://feature/eq/prices@v3", kind="feature"
    )
    handle.clone("prices_adj")
    assert made["namespace"] == "eq"
    assert made["definition"]["extends"]["parent"] == "eq/prices@v3"


def test_an_sdk_too_old_for_the_server_gets_a_typed_problem(monkeypatch):
    from starlette.testclient import TestClient

    from maya.api import app as app_module
    from tests.conftest import build_platform

    p = build_platform()
    try:
        client = TestClient(app_module.create_api(p))
        r = client.get("/api/v1/auth/me", headers={"X-Maya-Client": "python/0.0.1"})
        assert r.status_code == 426
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["type"] == "client_too_old" and "maya-sdk" in r.json()["detail"]
    finally:
        p.shutdown()
    from maya.sdk._shared.errors import ERRORS_BY_CODE

    assert ERRORS_BY_CODE["client_too_old"] is ClientTooOld


def test_the_cold_pin_age_is_a_declared_setting():
    from maya.config import schema

    assert schema.find("retention.cold_after_days").default == "180"


def test_a_webhook_is_sent_to_the_address_that_was_vetted_and_rebinding_is_refused(monkeypatch):
    """Resolve once, vet, connect there: a DNS answer that turns private between the check and
    the connection must not reach the private address."""
    import socket

    import httpx

    from tests.conftest import World, build_platform

    answers = {"hooks.example.com": "93.184.216.34"}

    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answers[host], 0))]

    monkeypatch.setattr("maya.services.webhooks.socket.getaddrinfo", fake_getaddrinfo)
    seen = []

    def receiver(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    p = build_platform()  # private targets refused
    try:
        w = World(p)
        p.webhooks.transport = httpx.MockTransport(receiver)
        hook = p.webhooks.create(w.admin, name="pinned", url="https://hooks.example.com/in")
        p.webhooks.ping(w.admin, hook["id"])
        assert seen, "the ping was not sent"
        sent = seen[-1]
        assert sent.url.host == "93.184.216.34"  # the vetted address, not a second lookup
        assert sent.headers["host"] == "hooks.example.com"
        assert sent.extensions["sni_hostname"] == "hooks.example.com"  # TLS checks the name
        answers["hooks.example.com"] = "10.0.0.5"  # rebinding: the name now points inside
        before = len(seen)
        out = p.webhooks.ping(w.admin, hook["id"])
        assert len(seen) == before, "a request reached the rebinding address"
        assert out["state"] != "delivered" and "private" in (out.get("last_error") or "")
    finally:
        p.shutdown()


def test_a_page_and_its_in_process_calls_take_one_slot_and_one_rate_token():
    """A web page calls the SDK in process through the same application. With room for one
    request in flight and a burst of two, a dashboard that makes several inner calls must
    still render: its calls are part of it, not competitors for its slot."""
    import re

    from starlette.testclient import TestClient

    from maya.server import build_app
    from tests.conftest import build_platform

    p = build_platform(["--api.limits.max_concurrent=1", "--api.limits.burst=3"])
    try:
        web = TestClient(build_app(p))
        page = web.get("/login")
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        web.post(
            "/login",
            data={"username": "admin", "password": "maya-dev-admin", "csrf_token": token},
            follow_redirects=False,
        )
        home = web.get("/")  # the dashboard: queue, features, models, health, jobs...
        assert home.status_code == 200, home.text[:300]
        assert "overloaded" not in home.text and "rate_limited" not in home.text
    finally:
        p.shutdown()


def test_the_concurrency_limit_still_holds_for_separate_requests():
    import asyncio

    from maya.api.limits import NESTING, Shed

    started = asyncio.Event()
    release = asyncio.Event()
    sent: list[int] = []

    async def app(scope, receive, send):
        started.set()
        await release.wait()

    shed = Shed(app, max_concurrent=1, timeout=0)

    async def send(message):
        if message["type"] == "http.response.start":
            sent.append(message["status"])

    async def main():
        first = asyncio.create_task(shed({"type": "http"}, None, send))
        await started.wait()
        assert NESTING.get() == 0  # the admitting task's context, not this one's
        await shed({"type": "http"}, None, send)  # a separate request: refused
        release.set()
        await first

    asyncio.run(main())
    assert sent == [503]


def test_the_lineage_of_a_bare_object_is_drawn_through_its_versions(journey):  # noqa: F811
    """Lineage is recorded between versions and pins; asking about the object itself used to
    find nothing. It is now joined to each of its versions and pins that has lineage."""
    w = journey
    root = "maya://model/quant/linear"
    with w.p.uow("test") as uow:  # as a training warrant records it: between versions
        uow.repo("lineage_edges").link(
            "maya://featureset/quant/panel@v1", root + "@v1", "trained_on", "test"
        )
    g = w.p.ops.lineage(root, depth=3, p=w.devi)
    ids = {n["id"] for n in g["nodes"]}
    assert root in ids and len(ids) > 1, ids
    joins = [e for e in g["edges"] if e["type"] == "version_of" and e["target"] == root]
    assert joins and all(e["source"].startswith(root + "@") for e in joins)
    assert any(e["type"] == "trained_on" for e in g["edges"])
    # a version or pin as root is walked exactly as before
    one = w.p.ops.lineage(root + "@v1", depth=1, p=w.devi)
    assert not any(e["type"] == "version_of" for e in one["edges"])


from tests.test_warrants import journey  # noqa: E402, F401 - the fixture, reused


def test_lineage_in_both_directions_never_draws_siblings_or_cousins():
    """Two features in one feature set, whose pin trained a warrant that also took a model.
    A feature's lineage is what built it and what it feeds; the other member feature and the
    model are neither, and must not appear. The model's lineage is what uses it."""
    from tests.conftest import build_platform

    a, b = "maya://feature/ns/a@v1", "maya://feature/ns/b@v1"
    fs, warrant = "maya://featureset/ns/panel@v1", "maya://warrant/train/ns/fit@v1"
    model, live = "maya://model/ns/m@v1", "maya://warrant/exec/ns/run@v1"
    p = build_platform()
    try:
        with p.uow("test") as uow:
            repo = uow.repo("lineage_edges")
            repo.link(a, fs, "member_of")
            repo.link(b, fs, "member_of")
            repo.link(fs, warrant, "trained_on")
            repo.link(model, warrant, "trained_on")
            repo.link(warrant, live, "executed_under")
        nodes = lambda root: {n["id"] for n in p.ops.lineage(root, depth=3)["nodes"]}  # noqa: E731
        assert nodes(a) == {a, fs, warrant, live}  # not b, not the model
        assert nodes(model) == {model, warrant, live}  # not the features or the feature set
        assert nodes(fs) == {a, b, fs, warrant, live}  # its members are what built it
        assert nodes(a) != nodes(model)
        up = {n["id"] for n in p.ops.lineage(warrant, direction="upstream", depth=3)["nodes"]}
        assert up == {a, b, fs, model, warrant}
    finally:
        p.shutdown()


# -- defects found while writing the tutorials ---------------------------------------------------
def test_the_semantic_diff_names_a_changed_constant_and_a_changed_constraint():
    import copy

    from maya.formula.diff import semantic_diff

    a = {
        "inputs": [
            {"name": "k", "role": "constant", "value": 680, "type": "float64"},
            {"name": "alpha", "role": "parameter", "type": "float64"},
            {"name": "beta", "role": "parameter", "type": "float64"},
        ],
        "outputs": [{"name": "y", "type": "float64"}],
        "body": {"ref": "k"},
    }
    b = copy.deepcopy(a)
    b["inputs"][0]["value"] = 700
    b["constraints"] = [
        {
            "expr": {"op": "add", "args": [{"param": "alpha"}, {"param": "beta"}]},
            "op": "lt",
            "rhs": 1,
            "why": "stationary",
        }
    ]
    said = semantic_diff(a, b)
    assert "constant 'k' value changed from 680 to 700" in said
    assert any(s.startswith("constraint added") for s in said)
    assert any(s.startswith("constraint removed") for s in semantic_diff(b, a))


def test_lifted_python_names_its_output_after_the_returned_variable():
    from maya.formula.pylift import lift_python

    ir = lift_python(
        "def m(X, params):\n"
        "    z = params['a'] + params['b'] * X['x']\n"
        "    pd = 1 / (1 + exp(-z))\n"
        "    return pd\n"
    )
    assert ir["outputs"][0]["name"] == "pd" and "pd" not in ir["lets"]


def test_mayas_own_latex_reads_back_and_greek_subscripts_render():
    from maya.formula.latex import latex_name
    from maya.formula.parse import parse_formula

    node = parse_formula(r"\mathit{rate} \cdot \text{balance}", inputs=["rate", "balance"])
    assert node == {"op": "mul", "args": [{"ref": "rate"}, {"ref": "balance"}]}
    assert latex_name("sigmaatm") == r"\sigma_{atm}"
    assert latex_name("number") == r"\mathit{number}"  # an ordinary word is not mangled


def test_declarations_are_made_without_the_ir_and_survive_re_entering_the_formula(journey):  # noqa: F811
    w = journey
    w.p.models.create(
        w.mona,
        namespace="quant",
        name="declared",
        formula="y = a + b*x",
        roles={"a": "parameter", "b": "parameter"},
    )
    ref = "quant/declared"
    w.p.models.declare(w.mona, ref, bounds={"a": [-1, 1]}, units={"x": "GBP"})
    w.p.models.add_constraint(w.mona, ref, expression="a + b", op="lt", rhs=2, why="a cap")
    ir = w.p.models.get(w.mona, ref)["versions"][-1]["formula_ir"]
    assert next(i for i in ir["inputs"] if i["name"] == "a")["bounds"] == [-1.0, 1.0]
    assert ir["constraints"][0]["expr"]["args"][0] == {"param": "a"}
    # re-entering the mathematics keeps what was declared about it
    w.p.models.update_draft(
        w.mona, ref, formula="y = a + b*x*2", roles={"a": "parameter", "b": "parameter"}
    )
    ir = w.p.models.get(w.mona, ref)["versions"][-1]["formula_ir"]
    assert next(i for i in ir["inputs"] if i["name"] == "a")["bounds"] == [-1.0, 1.0]
    assert next(i for i in ir["inputs"] if i["name"] == "x")["unit"] == "GBP"
    assert len(ir["constraints"]) == 1
    w.p.models.remove_constraint(w.mona, ref, 0)
    assert "constraints" not in w.p.models.get(w.mona, ref)["versions"][-1]["formula_ir"]


def test_a_failed_conformance_run_is_not_undone_by_a_later_run_over_easier_ground():
    from maya.services.models import ModelService

    service = ModelService.__new__(ModelService)
    bad = {
        "artifact_hash": "h",
        "agreed": 1900,
        "total": 2000,
        "counterexamples": [],
        "domain": "resampled from the feature set",
    }
    good = {
        "artifact_hash": "h",
        "agreed": 2000,
        "total": 2000,
        "counterexamples": [],
        "domain": "drawn from 0.5 to 150,000",
    }
    row = {
        "artifact_hash": "h",
        "formula_ir": {"body": {"ref": "x"}},
        "artifact_report": {"conformance": good, "conformance_runs": [bad, good]},
    }
    ok, why = service.check_conformance(None, {"row": row})
    assert ok is False and "disagrees" in why
    row["artifact_hash"] = "new-code"  # different code: its own record starts afresh
    row["artifact_report"]["conformance"] = {**good, "artifact_hash": "new-code"}
    assert service.check_conformance(None, {"row": row})[0] is True


def test_a_saturated_comparison_is_degenerate_and_cannot_pass_the_gate():
    """The tutorials' case: a logistic saturated at 1 on every sampled row agrees with a
    wrongly centred implementation everywhere -- which proves nothing, and now says so."""
    import numpy as np

    from maya.formula.conformance import conformance_test
    from maya.formula.parse import parse_model
    from maya.services.models import ModelService

    ir = parse_model("p = 1/(1 + e^{-(w (x - 680))})", roles={"w": "parameter"})
    x = np.random.default_rng(0).uniform(0.5, 1.5, 200)

    def wrong(X, params):  # centred at 700, not 680
        return 1 / (1 + np.exp(-(params["w"] * (np.asarray(X["x"]) - 700))))

    got = conformance_test(ir, wrong, {"x": x}, {"w": -3.0})
    assert got["agreed"] == got["total"] and got["degenerate"] is True
    row = {
        "artifact_hash": "h",
        "formula_ir": ir,
        "artifact_report": {
            "conformance": {**got, "artifact_hash": "h", "domain": "unit interval"}
        },
    }
    ok, why = ModelService.__new__(ModelService).check_conformance(None, {"row": row})
    assert ok is False and "degenerate" in why


def test_the_holdout_is_not_exported_before_the_warrant_is_sealed(journey):  # noqa: F811
    """A bundle carries the escrowed holdout. Exported before the parameters are approved, it
    would let the modeller read the rows they are scored on blind."""
    from maya.core.errors import NotApproved
    from tests.conftest import sealed

    w = journey
    w.p.models.create(
        w.mona,
        namespace="quant",
        name="escrow_lin",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    from tests.test_sdk_modes import complete_spec

    w.p.models.update_draft(w.mona, "quant/escrow_lin", spec_latex=complete_spec("escrow_lin"))
    w.p.models.transition(w.mona, "quant/escrow_lin", 1, "submit")
    w.p.models.transition(w.mgr, "quant/escrow_lin", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="escrow_tw",
        model="quant/escrow_lin@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 5},
    )
    with pytest.raises(NotApproved, match="only once its training warrant is sealed"):
        w.p.bundles.export(w.devi, tw["id"])
    data = w.p.warrants.data(w.devi, tw["id"])
    w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": 0.5}, data_checksum=data["manifest"]["checksum"]
    )
    sealed(w, tw["id"])
    w.p.bundles.export(w.devi, tw["id"])
    with w.p.uow() as uow:
        last = uow.repo("audit_events").list(action="bundle.exported")[-1]
    # recorded, so a challenger on the same holdout is told its rows were disclosed
    assert last["detail"]["holdout_hash"] and last["detail"]["warrant_id"] == tw["id"]


def test_a_later_version_with_a_wider_schema_can_be_pinned_beside_the_first():
    """Every version of an object shares its pin table; a version that adds an attribute was
    refused at the lake ('Append schema does not match'). It now pins to a sibling table for
    its schema, and the first version's pin reads back exactly as before."""
    import copy

    from tests.conftest import PX_DEF, World, approved_feature, build_platform, price_csv

    p = build_platform()
    try:
        w = World(p)
        p.access.create_namespace(w.admin, name="eq", preset="standard")
        ref = approved_feature(w, "px", price_csv())
        first = p.features.pin(w.mick, ref, version_no=1, pin_name="v1", as_of=dt.date(2026, 1, 20))
        w.drain()
        p.features.new_draft(w.dana, ref)
        wider = copy.deepcopy(PX_DEF)
        wider["schema"].append({"name": "volume", "type": "float64"})
        p.features.update_draft(w.dana, ref, wider)
        csv = price_csv().decode().splitlines()
        rows = [csv[0] + ",volume"] + [line + ",100" for line in csv[1:]]
        p.features.ingest(w.dana, ref, ("\n".join(rows) + "\n").encode(), fmt="csv")
        p.features.transition(w.dana, ref, 2, "submit")
        p.features.transition(w.mick, ref, 2, "approve")
        p.features.pin(w.mick, ref, version_no=2, pin_name="v2", as_of=dt.date(2026, 1, 20))
        w.drain()
        pins = {x["pin_name"]: x for x in p.features.get(w.mick, ref)["pins"]}
        assert pins["v2"]["state"] == "sealed", pins["v2"].get("failure")
        old = p.features.preview(w.mick, "maya://feature/eq/px#v1/2026-01-20")
        new = p.features.preview(w.mick, "maya://feature/eq/px#v2/2026-01-20")
        assert "volume" not in old["columns"] and "volume" in new["columns"]
        assert old["total_rows"] == new["total_rows"] > 0
        assert first is not None
    finally:
        p.shutdown()


def test_smaller_defects_found_while_writing_the_tutorials():
    from maya.llm.profiles import Profile
    from maya.llm.providers import _local
    from maya.services.llm import pii_found

    # a card number is a card number, not also a phone number
    assert pii_found("card 4111 1111 1111 1111") == ["card number"]
    # a profile shows the variable its key lives in, never a key
    row = Profile("p", "openai", options={"api_key_env": "OPENAI_API_KEY", "api_key": "x"}).as_row()
    assert row["options"] == {"api_key_env": "OPENAI_API_KEY"}
    # only a server on this machine or network may be called without a key
    assert _local("http://localhost:8000/v1") and _local("http://10.1.2.3:1234")
    assert _local("http://gpu-box:11434") and not _local("https://api.openai.com/v1")


def test_a_yaml_no_in_the_questionnaire_is_the_word_no(tmp_path):
    from tests.conftest import build_platform

    path = tmp_path / "tiering.yaml"
    path.write_text(
        "questions:\n  - id: impact\n    text: Customers?\n    answers:\n      no: 1\n"
        "      yes: 3\n"
    )
    p = build_platform([f"--governance.tiering_questionnaire={path}"])
    try:
        answers = p.governance.questionnaire()["questions"][0]["answers"]
        assert answers == {"no": 1, "yes": 3}
    finally:
        p.shutdown()
