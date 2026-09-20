"""
The promise this file holds: a shadow replay is measured against the threshold the *model*
declares, it says honestly how much of the population it looked at, it costs a namespace no
more compute per day than that namespace allows, and the numbers reach the approver on the
review screen rather than only the designer who ran them.

Those are §29.2's four remaining claims. The materiality threshold is "declared", and only
the model knows whether its output is a price, a rate in basis points or a probability, so a
model version's own figure wins over its namespace's and over the configured default — and
the report says which of the three it used, because a report that quietly used the wrong one
reads as "nothing moved". The sampling is "honest about its coverage", so the share of the
matched rows it covered is stated per warrant and for the report. It is "gated by a
per-namespace budget", charged in row comparisons against what the audit log says previous
replays spent. And "the review screen then reads … instead of a list of names".

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import copy
import datetime as dt
import re

import pytest

from maya.core.errors import ValidationFailed
from tests.conftest import PASSWORD, approved_feature, price_csv
from tests.test_warrants import XY_DEF, complete_spec, xy_csv

CLIPPED = dict(copy.deepcopy(XY_DEF), transform=[{"op": "clip", "attr": "x", "lo": 0, "hi": 3}])
DECLARED = 1_000_000.0  # larger than any shift this change can produce, and deliberately so
CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture(scope="module")
def staged(world):
    """A feature, a panel pinned from it, a model that declares its own materiality, and an
    approved parameter set — everything a replay needs downstream of a staged change."""
    w = world
    w.p.access.create_namespace(w.admin, name="sre")
    w.p.features.create(w.dana, namespace="sre", name="xy", definition=XY_DEF)
    w.p.features.ingest(w.dana, "sre/xy", xy_csv(), fmt="csv")
    w.p.features.transition(w.dana, "sre/xy", 1, "submit")
    w.p.features.transition(w.mick, "sre/xy", 1, "approve")
    w.p.featuresets.create(
        w.devi,
        namespace="sre",
        name="panel",
        definition={
            "index": ["date", "symbol"],
            "members": [
                {"attr": a, "ref": "maya://feature/sre/xy@v1", "source_attr": a} for a in ("x", "y")
            ],
        },
    )
    w.p.featuresets.transition(w.devi, "sre/panel", 1, "submit")
    w.p.featuresets.transition(w.mick, "sre/panel", 1, "approve")
    w.p.featuresets.pin(
        w.mick, "sre/panel", version_no=1, pin_name="q1", as_of=dt.date(2026, 2, 28), cascade=True
    )
    w.drain()
    w.p.models.create(
        w.mona,
        namespace="sre",
        name="lin",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    w.p.models.update_draft(
        w.mona, "sre/lin", spec_latex=complete_spec("lin"), shadow_materiality=DECLARED
    )
    w.p.models.transition(w.mona, "sre/lin", 1, "submit")
    w.p.models.transition(w.mgr, "sre/lin", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="sre",
        name="tw",
        model="sre/lin@v1",
        featureset="maya://featureset/sre/panel#q1/2026-02-28",
        spec={"target": "y"},
    )
    checksum = w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
    ps = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": 0.5}, data_checksum=checksum
    )
    w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    return w, tw


def replay(w, name: str) -> dict:
    """Stage the clip in a fresh workspace, replay it, and give back the report."""
    ws = w.p.workspaces.create(w.dana, name)
    w.p.workspaces.stage(w.dana, ws["id"], kind="feature", ref="sre/xy", definition=CLIPPED)
    w.p.workspaces.request_replay(w.dana, ws["id"])
    w.drain()
    return dict(w.p.workspaces.get(w.dana, ws["id"])["replay"], workspace=ws["id"])


def namespace(w) -> dict:
    with w.p.uow() as uow:
        return uow.repo("namespaces").find_one(name="sre")


# -- the declared threshold --------------------------------------------------------------
def test_the_threshold_a_model_declares_is_the_one_the_replay_measures_against(staged):
    w, _ = staged
    report = replay(w, "declared-materiality")
    entry = next(r for r in report["warrants"] if r["replayed"])
    assert entry["materiality"] == DECLARED and entry["materiality_from"] == "model"
    assert entry["max_abs_shift"] > 0, "the staged clip does move this model's output"
    assert entry["rows_over_materiality"] == 0, "but not by what this model calls material"
    assert "moves 0 of 1" in report["summary"]


def test_without_a_declaration_the_namespace_and_then_the_default_decide(staged):
    w, tw = staged
    with w.p.uow() as uow:
        warrant = uow.repo("training_warrants").require(tw["id"])
        uow.repo("model_versions").update(warrant["model_version_id"], {"shadow_materiality": None})
    try:
        report = replay(w, "no-declaration")
        entry = next(r for r in report["warrants"] if r["replayed"])
        assert entry["materiality_from"] == "default"
        assert entry["rows_over_materiality"] > 0, "at the configured threshold it moves"
        assert "moves 1 of 1" in report["summary"] and "default)" in report["summary"]
    finally:
        with w.p.uow() as uow:
            uow.repo("model_versions").update(
                warrant["model_version_id"], {"shadow_materiality": DECLARED}
            )


def test_the_model_s_figure_beats_its_namespace_s_and_the_configured_one(staged):
    w, _ = staged
    svc = w.p.workspaces
    desk = {"shadow_materiality": 100.0}
    assert svc._materiality({"shadow_materiality": 7.0}, desk) == (7.0, "model")
    assert svc._materiality({}, desk) == (100.0, "namespace")
    assert svc._materiality({}, None) == (svc.materiality, "default")


# -- honest coverage ---------------------------------------------------------------------
def test_the_report_says_how_much_of_the_population_it_looked_at(staged):
    w, _ = staged
    svc = w.p.workspaces
    keep, svc.sample_rows = svc.sample_rows, 2
    try:
        report = replay(w, "coverage")
    finally:
        svc.sample_rows = keep
    entry = next(r for r in report["warrants"] if r["replayed"])
    assert entry["rows_compared"] == 2 and entry["rows_available"] > 2
    assert 0 < entry["coverage"] < 1
    cover = report["coverage"]
    assert cover["rows_compared"] == 2 and cover["rows_available"] == entry["rows_available"]
    assert 0 < cover["share"] < 1 and "most recent" in cover["sampling"]
    assert "matched rows" in report["summary"], "the summary owns up to the sample too"
    assert "recency bias" in report["basis"]


# -- the per-namespace cost budget -------------------------------------------------------
def test_a_namespace_replays_no_more_than_its_budget_allows_in_a_day(staged):
    w, _ = staged
    svc = w.p.workspaces
    ns = namespace(w)
    spent = svc._opening_spend().get(ns["id"], 0)
    w.p.access.update_namespace(w.admin, "sre", {"shadow_budget_rows": spent + 1})
    try:
        first = replay(w, "budget-under")
        assert any(r["replayed"] for r in first["warrants"]), "under the ceiling, work happens"
        assert first["budget"]["spent"]["sre"] > 0, "and what it cost is on the report"
        assert first["budget"]["rows_per_day"] == svc.budget_rows

        after = replay(w, "budget-spent")
        refused = after["warrants"][0]
        assert not refused["replayed"], "over the ceiling, the next replay does not run"
        assert "budget for the day" in refused["reason"] and "sre" in refused["reason"]
        assert refused["budget_rows"] == spent + 1 and refused["spent_rows"] > spent
        assert after["budget"]["spent"] == {}, "and nothing more was charged"
    finally:
        w.p.access.update_namespace(w.admin, "sre", {"shadow_budget_rows": 0})
    assert any(r["replayed"] for r in replay(w, "budget-off")["warrants"]), "zero: no ceiling"


def test_a_budget_is_zero_for_no_ceiling_or_a_positive_count(staged):
    w, _ = staged
    with pytest.raises(ValidationFailed, match="zero for no ceiling"):
        w.p.access.update_namespace(w.admin, "sre", {"shadow_budget_rows": -1})


# -- the numbers reach the approver ------------------------------------------------------
def test_a_version_never_rehearsed_carries_no_numeric_impact(staged):
    w, _ = staged
    approved_feature(w, "sre_plain", price_csv(4), ns="sre")
    with w.p.uow() as uow:
        feature = uow.repo("features").find_one(name="sre_plain")
        v1 = uow.repo("feature_versions").find_one(feature_id=feature["id"], version_no=1)
    r = w.p.workflow_svc.review(w.mick, "feature_version", v1["id"])
    assert r["shadow"] is None, "no workspace, no replay, and the screen says nothing"
    assert r["impact"] is not None, "the list of names is still there"


def test_the_review_screen_reads_how_much_it_moves_not_only_what_it_touches(staged):
    from starlette.testclient import TestClient

    from maya.server import build_app

    w, _ = staged
    ws = w.p.workspaces.create(w.dana, "for-review")
    w.p.workspaces.stage(w.dana, ws["id"], kind="feature", ref="sre/xy", definition=CLIPPED)
    w.p.workspaces.request_replay(w.dana, ws["id"])
    w.drain()
    submitted = w.p.workspaces.submit(w.dana, ws["id"])["submitted"][0]

    r = w.p.workflow_svc.review(w.mick, "feature_version", submitted["version_id"])
    shadow = r["shadow"]
    assert shadow and shadow["workspace_name"] == "for-review"
    assert "moves" in shadow["summary"] and shadow["generated_at"]
    assert shadow["coverage"]["rows_compared"] > 0
    assert any(entry["replayed"] for entry in shadow["warrants"])

    with w.p.uow() as uow:
        user = uow.repo("users").find_one(username="mick")
        uow.repo("users").update(user["id"], {"must_change_password": False})
    web = TestClient(build_app(w.p))
    csrf = CSRF.search(web.get("/login").text).group(1)
    web.post("/login", data={"username": "mick", "password": PASSWORD, "csrf_token": csrf})
    page = web.get(f"/workflow/review/feature_version/{submitted['version_id']}")
    assert page.status_code == 200
    assert "Numeric impact" in page.text and "for-review" in page.text
    assert re.search(r"moves \d+ of \d+ replayed dependent model", page.text)


def test_a_declared_threshold_is_positive_and_a_new_draft_keeps_it(staged):
    w, _ = staged
    draft = w.p.models.new_draft(w.mona, "sre/lin")
    assert draft["shadow_materiality"] == DECLARED, "a new version inherits the declaration"
    with pytest.raises(ValidationFailed, match="above zero"):
        w.p.models.update_draft(w.mona, "sre/lin", shadow_materiality=0)
    changed = w.p.models.update_draft(w.mona, "sre/lin", shadow_materiality=0.25)
    assert changed["shadow_materiality"] == 0.25
