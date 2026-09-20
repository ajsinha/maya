"""
§29.8's drafting: a feature definition from a description and a sample file, and drafts for
the specification sections an author has not written. The assistant could challenge a review
and nothing else, so the two places the specification asks it to *start* work were missing.

A draft is a proposal. These tests hold it to that: nothing is created, the draft validates
as a real definition would, and what it could not know is said rather than invented.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.assistant import drafts
from maya.formula import specdoc
from tests.conftest import price_csv
from tests.test_warrants import complete_spec, journey  # noqa: F401 - the fixture, reused

SAMPLE = (
    b"date,symbol,close,volume,published_at\n"
    b"2026-01-05,AAA,101.5,1000,2026-01-06T00:00:00Z\n"
    b"2026-01-06,AAA,102.0,1100,2026-01-07T00:00:00Z\n"
)


def test_a_definition_is_drafted_from_a_sample_and_a_sentence(world):
    w = world
    draft = w.p.assistant.draft_feature(
        w.dana, "Daily closing prices per symbol; gaps carry forward from the last known", SAMPLE
    )
    definition = draft["definition"]
    assert definition["index"] == ["date", "symbol"]
    assert definition["index_types"] == {"date": "date", "symbol": "string"}
    assert {a["name"] for a in definition["schema"]} == {"close", "volume"}
    assert definition["source"]["knowledge_time_column"] == "published_at"
    assert definition["resolution"]["rules"]["close"] == "forward_fill(limit=3)"
    assert {"check": "unique_on_index"} in definition["quality"]
    assert draft["valid"] and draft["errors"] == []
    assert draft["from"]["index"] and draft["review"].startswith("This is a draft")


def test_a_draft_creates_nothing_and_is_audited(world):
    w = world
    before = _features(w)
    draft = w.p.assistant.draft_feature(w.dana, "prices", SAMPLE)
    assert _features(w) == before, "a draft is a proposal, never a write"
    with w.p.uow() as uow:
        entries = uow.repo("audit_events").list(action="assistant.drafted")
    assert entries and entries[-1]["detail"]["kind"] == "feature"
    # and it is a definition MAYA will actually accept
    w.p.features.create(w.dana, namespace="eq", name="drafted_px", definition=draft["definition"])
    assert w.p.features.get(w.dana, "eq/drafted_px")["name"] == "drafted_px"


def _features(w) -> int:
    with w.p.uow() as uow:
        return uow.repo("features").count()


def test_a_sample_with_no_date_says_the_index_is_a_guess(world):
    w = world
    draft = w.p.assistant.draft_feature(w.dana, "a lookup table", b"key,value\na,1\nb,2\n")
    assert any("index is a guess" in note for note in draft["notes"])


def test_only_structure_is_read_from_the_sample(world):
    """A draft carries column names, types and null counts — never a row of data, which is
    what makes the Claude provider's version safe to send."""
    w = world
    draft = w.p.assistant.draft_feature(w.dana, "prices", price_csv(3))
    text = str(draft)
    assert "101.5" not in text and "AAA" not in text


def test_the_missing_spec_sections_are_drafted_and_the_written_ones_left_alone(journey):  # noqa: F811
    w = journey
    w.p.models.create(
        w.mona, namespace="quant", name="ad_model", formula="yhat = a*x", roles={"a": "parameter"}
    )
    out = w.p.assistant.draft_spec(w.mona, "quant/ad_model", 1)
    assert set(out["missing"]) <= set(specdoc.REQUIRED_SECTIONS)
    assert {"Purpose", "Known Weaknesses"} <= set(out["missing"]), "these are empty in a new draft"
    assert set(out["missing"]) & set(out["kept"]) == set(), "a section is missing or kept, not both"
    assert "yhat" in out["drafts"]["Purpose"] and "x" in out["drafts"]["Purpose"]
    assert "a" in out["drafts"]["Calibration Methodology"]
    assert all("STATE" in body for body in out["drafts"].values()), "each names what it lacks"
    w.p.models.update_draft(w.mona, "quant/ad_model", spec_latex=complete_spec("ad_model"))
    after = w.p.assistant.draft_spec(w.mona, "quant/ad_model", 1)
    assert after["missing"] == [] and after["kept"], "a written section is left alone"


def test_a_draft_never_pretends_to_know_the_validation_evidence():
    out = drafts.spec_sections(
        specdoc.TEMPLATE,
        {"inputs": [{"name": "x"}], "outputs": [{"name": "y"}], "body": "y = 2x"},
        specdoc.section_completeness(specdoc.TEMPLATE),
    )
    evidence = out["drafts"]["Validation Evidence"]
    assert "STATE" in evidence and "holdout" in evidence
    assert "rmse" not in evidence.lower(), "no invented numbers"


def test_the_assistant_can_be_switched_off(world, monkeypatch):
    w = world
    monkeypatch.setattr(w.p.assistant, "enabled", False)
    from maya.core.errors import CapabilityRefused

    with pytest.raises(CapabilityRefused, match="switched off"):
        w.p.assistant.draft_feature(w.dana, "prices", SAMPLE)
