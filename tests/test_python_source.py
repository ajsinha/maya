"""
The python source driver (§5.2): a reviewed producer function, run only in the
sandbox, pulled into the bitemporal ingest log like any other source.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import ValidationFailed
from maya.services.sources import validate_python_source
from tests.conftest import World, build_platform

CURVE = """
import numpy as np

def produce(params):
    n = params["days"]
    days = np.arange(n)
    return {"date": [f"2026-01-{d + 1:02d}" for d in days],
            "tenor": ["1Y"] * n,
            "rate": (params["base"] + 0.001 * days).tolist()}
"""


def definition(code: str = CURVE, params: dict | None = None, **source) -> dict:
    return {
        "index": ["date", "tenor"],
        "index_types": {"date": "date", "tenor": "string"},
        "schema": [{"name": "rate", "type": "float64"}],
        "source": {
            "type": "python",
            "code": code,
            "params": params
            if params is not None
            else {"days": {"type": "int", "value": 5}, "base": {"type": "float", "value": 0.02}},
            **source,
        },
        "resolution": {"grid": "as_is", "rules": {}},
        "transform": [],
        "quality": [],
    }


@pytest.fixture(scope="module")
def py(world):
    world.p.access.create_namespace(world.admin, name="pysrc", preset="standard")
    return world


# -- review-time checks ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "source, message",
    [
        ({"code": ""}, "carries its code"),
        ({"code": "def produce(params):\n    return {"}, "syntax error on line"),
        ({"code": "def make(params):\n    return {}"}, "no function 'produce'"),
        ({"code": "def produce():\n    return {}"}, "exactly one argument, params"),
        ({"code": "def produce(params, extra):\n    return {}"}, "exactly one argument"),
        ({"code": "import os\ndef produce(params):\n    return {}"}, "'os'"),
        ({"code": "import requests\ndef produce(params):\n    return {}"}, "not on the allowlist"),
        ({"code": "def produce(params):\n    return open('/etc/passwd').read()"}, "use of 'open'"),
        ({"code": "def produce(params):\n    return params.__class__"}, "dunder access"),
        (
            {"code": CURVE, "params": {"days": {"type": "complex", "value": 1}}},
            "type must be one of",
        ),
        ({"code": CURVE, "params": {"days": {"type": "int", "value": "many"}}}, "not a valid int"),
    ],
)
def test_what_review_refuses(source, message):
    errors = validate_python_source({"type": "python", **source})
    assert any(message in e for e in errors), errors


def test_a_valid_producer_passes_review_with_a_named_entry():
    assert validate_python_source(definition()["source"]) == []
    named = definition(code=CURVE.replace("def produce", "def curve"), entry="curve")["source"]
    assert validate_python_source(named) == []


def test_submit_blocks_on_the_same_checks(py):
    w = py
    w.p.features.create(
        w.dana,
        namespace="pysrc",
        name="banned",
        definition=definition(code="import socket\ndef produce(params):\n    return {}"),
    )
    with pytest.raises(ValidationFailed, match="socket"):
        w.p.features.transition(w.dana, "pysrc/banned", 1, "submit")


# -- pulls --------------------------------------------------------------------------------------
def test_a_pull_runs_in_the_sandbox_and_lands_in_the_ingest_log(py):
    w = py
    w.p.features.create(w.dana, namespace="pysrc", name="curve", definition=definition())
    first = w.p.sources.pull(w.dana, "pysrc/curve")
    assert first["rows"] == 5 and first["source_type"] == "python"
    assert "produce() in the" in first["note"] and "sandbox" in first["note"]
    with w.p.uow() as uow:
        audit = uow.repo("audit_events").list(action="feature.pulled")[-1]["detail"]
    assert audit["source"] == "python" and audit["entry"] == "produce"
    assert audit["tier"] and len(audit["code_sha256"]) == 64 and audit["restatement"] is False
    w.p.features.transition(w.dana, "pysrc/curve", 1, "submit")
    w.p.features.transition(w.mick, "pysrc/curve", 1, "approve")
    rows = w.p.features.preview(w.dana, "maya://feature/pysrc/curve@v1")["rows"]
    assert [r["rate"] for r in rows] == pytest.approx([0.02, 0.021, 0.022, 0.023, 0.024])


def test_a_changed_result_is_a_restatement_and_the_past_stays_answerable(py):
    w = py
    d = definition()
    w.p.features.create(w.dana, namespace="pysrc", name="restated", definition=d)
    before = dt.datetime.now(dt.timezone.utc)
    w.p.sources.pull(w.dana, "pysrc/restated", knowledge_time=before)
    d["source"]["params"]["base"]["value"] = 0.05
    draft = w.p.features.get(w.dana, "pysrc/restated")["versions"][0]
    w.p.features.update_draft(
        w.dana, "pysrc/restated", d, expected_version=draft.get("row_version")
    )
    second = w.p.sources.pull(
        w.dana, "pysrc/restated", knowledge_time=before + dt.timedelta(seconds=5)
    )
    assert second["restatement"] is True
    w.p.features.transition(w.dana, "pysrc/restated", 1, "submit")
    w.p.features.transition(w.mick, "pysrc/restated", 1, "approve")
    ref = "maya://feature/pysrc/restated@v1"
    old = w.p.features.preview(w.dana, ref, as_of_known=before + dt.timedelta(seconds=1))
    new = w.p.features.preview(w.dana, ref)
    assert old["rows"][0]["rate"] == pytest.approx(0.02)
    assert new["rows"][0]["rate"] == pytest.approx(0.05)


@pytest.mark.parametrize(
    "code, message",
    [
        (
            "def produce(params):\n    raise RuntimeError('vendor calendar missing')",
            "RuntimeError: vendor calendar missing",
        ),
        ("def produce(params):\n    return 42", "must return"),
        ("def produce(params):\n    return [1, 2]", "must return"),
    ],
)
def test_a_producer_that_fails_or_returns_nonsense_is_refused(py, code, message):
    w = py
    name = f"bad{abs(hash(code)) % 10**6}"
    w.p.features.create(w.dana, namespace="pysrc", name=name, definition=definition(code=code))
    with pytest.raises(ValidationFailed, match=message):
        w.p.sources.pull(w.dana, f"pysrc/{name}")
    assert w.p.features.get(w.dana, f"pysrc/{name}")["ingests"] == []


def test_records_dataframes_and_dates_are_all_accepted(py):
    w = py
    records = (
        "import datetime\n\ndef produce(params):\n"
        "    return [{'date': datetime.date(2026, 2, d), 'tenor': '2Y', 'rate': d / 100}"
        " for d in (1, 2, 3)]\n"
    )
    frame = (
        "import pandas as pd\n\ndef produce(params):\n"
        "    return pd.DataFrame({'date': pd.to_datetime(['2026-03-02', '2026-03-03']),"
        " 'tenor': ['5Y', '5Y'], 'rate': [0.03, 0.031]})\n"
    )
    for name, code, rows in (("records", records, 3), ("frame", frame, 2)):
        w.p.features.create(
            w.dana, namespace="pysrc", name=name, definition=definition(code=code, params={})
        )
        assert w.p.sources.pull(w.dana, f"pysrc/{name}")["rows"] == rows


def test_missing_columns_are_named(py):
    w = py
    w.p.features.create(
        w.dana,
        namespace="pysrc",
        name="short",
        definition=definition(
            code="def produce(params):\n    return {'date': ['2026-01-01'], 'rate': [1.0]}",
            params={},
        ),
    )
    with pytest.raises(ValidationFailed, match="missing column.*tenor"):
        w.p.sources.pull(w.dana, "pysrc/short")


def test_a_runaway_producer_is_killed_by_the_wall_clock():
    platform = build_platform(["--sources.python.wall_seconds=3", "--sources.python.cpu_seconds=2"])
    try:
        w = World(platform)
        platform.access.create_namespace(w.admin, name="slow")
        w.p.features.create(
            w.dana,
            namespace="slow",
            name="spin",
            definition=definition(
                code="def produce(params):\n    while True:\n        pass", params={}
            ),
        )
        with pytest.raises(ValidationFailed, match="limit|killed|CPU|time"):
            w.p.sources.pull(w.dana, "slow/spin")
    finally:
        platform.shutdown()


def test_the_designer_builds_a_python_source(py):
    from starlette.datastructures import FormData

    from maya.web.routes.workbench import definition_from_form

    form = FormData(
        [
            ("mode", "source"),
            ("index_name", "date"),
            ("index_type", "date"),
            ("index_name", "tenor"),
            ("index_type", "string"),
            ("attr_name", "rate"),
            ("attr_type", "float64"),
            ("attr_unit", ""),
            ("attr_tag", ""),
            ("attr_rule", ""),
            ("source_type", "python"),
            ("python_code", CURVE),
            ("python_params", '{"days": {"type": "int", "value": 3}}'),
        ]
    )
    d = definition_from_form(form)
    assert d["source"] == {
        "type": "python",
        "code": CURVE,
        "entry": "produce",
        "params": {"days": {"type": "int", "value": 3}},
    }
    assert validate_python_source(d["source"]) == []
