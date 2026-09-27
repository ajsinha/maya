"""
Champion and challenger, and fairness and explainability evidence, on the escrowed holdout.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import numpy as np
import pytest

from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from maya.services.challenges import compare
from tests.test_warrants import complete_spec, journey  # noqa: F401 - the shared estate fixture

PIN = "maya://featureset/quant/panel#q1/2026-02-28"


@pytest.fixture(scope="module")
def estate(journey):  # noqa: F811
    w = journey
    w.p.models.update_draft(w.mona, "quant/linear", spec_latex=complete_spec("linear"))
    w.p.models.transition(w.mona, "quant/linear", 1, "submit")
    w.p.models.transition(w.mgr, "quant/linear", 1, "approve")
    return w


def test_the_verdict_needs_the_whole_interval_on_one_side():
    rng = np.random.default_rng(1)
    champ = rng.normal(0, 1.0, 400)
    better = compare(champ, champ * 0.5, "rmse")
    assert better["verdict"] == "challenger_better" and better["interval"][1] < 0
    assert better["challenger_wins"] > 0.9
    worse = compare(champ, champ * 2.0, "mae")
    assert worse["verdict"] == "champion_better" and worse["interval"][0] > 0
    noise = compare(champ, champ + rng.normal(0, 0.01, 400), "rmse")
    assert noise["verdict"] == "no_clear_difference"
    assert noise["interval"][0] < 0 < noise["interval"][1]
    assert compare(champ, champ * 0.5, "rmse") == better  # seeded: the same on any machine
    with pytest.raises(ValidationFailed):
        compare(np.array([1.0]), np.array([1.0]), "rmse")


def _warrant(w, name: str, b: float) -> tuple[str, str]:
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name=name,
        model="quant/linear@v1",
        featureset=PIN,
        spec={"target": "y", "seed": 7},
    )
    checksum = w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
    ps = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": b}, data_checksum=checksum
    )
    return tw["id"], ps["id"]


def test_a_challenger_is_scored_on_the_champions_rows_and_decided_independently(estate):
    w = estate
    champ, champ_ps = _warrant(w, "champ", b=0.3)
    chall, chall_ps = _warrant(w, "chall", b=0.5)  # the true intercept
    c = w.p.challenges.create(
        w.devi,
        champ,
        chall,
        champion_parameter_set_id=champ_ps,
        challenger_parameter_set_id=chall_ps,
    )
    r = c["result"]
    assert r["verdict"] == "challenger_better" and r["difference"] < 0
    assert r["challenger"] < 1e-2 and r["rows"] > 0 and r["challenger_wins"] > 0.9
    assert c["champion"]["model"] == "linear@v1" and c["state"] == "scored"
    # both scorings were counted on their warrants
    for wid in (champ, chall):
        got = w.p.warrants.get(w.devi, wid)
        assert got["holdout_attempts"] == 1
        assert got["custody"][-1]["detail"]["purpose"] == "champion-challenger"

    with pytest.raises(PermissionDenied, match="owns the challenger"):
        w.p.challenges.decide(w.devi, c["id"], "promote", "better")
    with pytest.raises(ValidationFailed):
        w.p.challenges.decide(w.mgr, c["id"], "promote", " ")
    done = w.p.challenges.decide(w.mgr, c["id"], "promote", "interval clear of zero")
    assert done["state"] == "promoted" and done["decided_by"] == "mgr"
    with pytest.raises(NotApproved):
        w.p.challenges.decide(w.mgr, c["id"], "retain", "changed my mind")
    assert c["id"] in {x["id"] for x in w.p.challenges.list(w.devi)}
    with pytest.raises(ValidationFailed, match="by itself"):
        w.p.challenges.create(w.devi, champ, champ)


def test_warrants_on_different_holdouts_are_not_compared(estate):
    w = estate
    a = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="h_a",
        model="quant/linear@v1",
        featureset=PIN,
        spec={"target": "y", "seed": 7},
    )
    b = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="h_b",
        model="quant/linear@v1",
        featureset=PIN,
        spec={"target": "y", "seed": 11},
    )
    if a["holdout_hash"] == b["holdout_hash"]:
        pytest.skip("the two seeds happened to draw the same holdout")
    with pytest.raises(ValidationFailed, match="same escrowed holdout"):
        w.p.challenges.create(w.devi, a["id"], b["id"], challenger_parameter_set_id=None)


# --------------------------------------------------------- fairness and drivers


def test_segments_suppress_small_groups_and_flag_the_worst():
    from maya.services.evidence import segments

    groups = np.array(["A"] * 40 + ["B"] * 40 + ["C"] * 3)
    err = np.concatenate([np.full(40, 0.1), np.full(40, 1.0), np.full(3, 5.0)])
    out = segments(groups, err, err + 10, min_rows=20)
    rows = {r["segment"]: r for r in out["segments"]}
    assert rows["C"]["suppressed"] and "mae" not in rows["C"]  # three rows would be three rows
    assert out["flagged"] == ["B"] and out["mae_ratio"] == pytest.approx(10.0)
    assert out["compared"] == 2 and out["suppressed"] == 1
    # equal MAE, opposite directions: nothing flagged, both systematic
    two = segments(
        np.array(["F"] * 30 + ["M"] * 30), np.array([0.5] * 30 + [-0.5] * 30), np.zeros(60)
    )
    assert two["flagged"] == [] and two["systematic"] == ["F", "M"] and two["bias_gap"] == 1.0


def test_evidence_on_the_holdout_names_the_driver_and_counts_an_attempt(estate):
    w = estate
    tw, ps = _warrant(w, "evid", b=0.4)
    before = w.p.warrants.get(w.devi, tw)["holdout_attempts"]
    row = w.p.evidence.compute(w.devi, tw, parameter_set_id=ps, segment="symbol", repeats=3)
    r = row["result"]
    assert r["importance"][0]["input"] == "x" and r["importance"][0]["share"] == 1.0
    sg = r["segments"]
    assert sg["column"] == "symbol" and sg["compared"] + sg["suppressed"] == 3
    assert w.p.warrants.get(w.devi, tw)["holdout_attempts"] == before + 1
    assert w.p.evidence.list(w.devi, tw)[0]["id"] == row["id"]
    with pytest.raises(ValidationFailed, match="not a column"):
        w.p.evidence.compute(w.devi, tw, parameter_set_id=ps, segment="nope")
    with pytest.raises(ValidationFailed, match="target"):
        w.p.evidence.compute(w.devi, tw, parameter_set_id=ps, segment="y", importance=False)


# ------------------------------------------------ dispatched training, reference re-fit


def test_a_reference_refit_finds_the_true_parameters_and_says_whether_a_set_agrees(estate):
    w = estate
    tw, off = _warrant(w, "refit_off", b=0.3)
    row = w.p.training_ops.refit(w.devi, tw, parameter_set_id=off)
    r = row["result"]
    assert abs(r["maya"]["a"] - 2.0) < 1e-6 and abs(r["maya"]["b"] - 0.5) < 1e-6
    assert r["rmse_maya"] < 1e-9 < r["rmse_given"] and r["agrees"] is False
    tw2, exact = _warrant(w, "refit_exact", b=0.5)
    assert w.p.training_ops.refit(w.devi, tw2, parameter_set_id=exact)["result"]["agrees"] is True
    assert w.p.warrants.get(w.devi, tw)["holdout_attempts"] == 0  # training rows only


def test_a_dispatched_job_fits_on_its_own_compute_and_reports_back(estate):
    import numpy as np

    from maya.api.app import create_api
    from maya.sdk import Client
    from maya.sdk.trainer import fit_under_warrant

    w = estate
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="dispatched",
        model="quant/linear@v1",
        featureset=PIN,
        spec={"target": "y", "seed": 7},
    )
    d = w.p.training_ops.dispatch(w.devi, tw["id"], image="registry.example.com/train:1")
    assert d["kubernetes_job"]["kind"] == "Job" and d["sagemaker_request"]["TrainingJobName"]
    assert d["manifest"]["warrant_id"] == tw["id"] and d["api_key"].startswith("maya_")

    def fit(train, target):  # the firm's code, on the firm's compute
        a, b = np.polyfit(train["x"], train[target], 1)  # yhat = a*x + b
        return {"a": float(a), "b": float(b)}, {"rows": len(train)}

    job_client = Client(app=create_api(w.p), token=d["api_key"])
    ps = fit_under_warrant(
        fit,
        client=job_client,
        env={"MAYA_WARRANT_ID": tw["id"], "MAYA_DISPATCH_ID": d["dispatch_id"]},
    )
    assert ps["verified_data"] and ps["metrics"]["dispatch_id"] == d["dispatch_id"]
    assert abs(ps["values"]["a"] - 2.0) < 1e-6
