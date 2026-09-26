"""
Champion and challenger on the same escrowed holdout.

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
