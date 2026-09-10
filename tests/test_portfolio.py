"""The register cut by the dimensions somebody actually asks about.

SR 26-2 VI asks for an inventory sufficient to understand individual *and
aggregate* risk, and filters on a list only ever answer the first.
"""
from __future__ import annotations


import pytest

from core.estate.common import EstateError
from core.estate.portfolio import DIMENSIONS, Portfolio


class FakeWorklist:
    """What each model owes, keyed by urn."""

    def __init__(self, owed=None):
        self._owed = owed or {}

    def for_model(self, model, now=None):
        return [object()] * self._owed.get(model["urn"], 0)


class FakeRisk:
    def __init__(self, rows=None):
        self._rows = rows or {}

    def many(self, model_id):
        return self._rows.get(model_id, [])


def _register(registry, n=3):
    for i in range(n):
        registry.register(f"maya://model/m{i}", f"M{i}",
                          "credit.pd.scorecard",
                          "credit" if i < 2 else "markets",
                          f"person/o{i}", "LE-US-01", "p", actor="j.okafor")
        registry.set_tier(registry.require(f"maya://model/m{i}")["id"],
                          1 if i == 0 else 3)
    return registry.list()


class TestCuttingTheRegister:
    def test_every_dimension_says_what_it_means(self):
        assert all(v for v in DIMENSIONS.values())
        assert "tier" in DIMENSIONS and "legal_entity" in DIMENSIONS

    def test_an_unknown_dimension_is_refused_naming_the_real_ones(self,
                                                                  registry):
        with pytest.raises(EstateError) as caught:
            Portfolio(registry).by("colour")
        assert caught.value.code == "unknown_dimension"
        assert "legal_entity" in caught.value.remediation

    def test_it_groups_and_counts(self, registry):
        _register(registry)
        out = Portfolio(registry).by("domain")
        by_value = {c["value"]: c["models"] for c in out["cells"]}
        assert by_value == {"credit": 2, "markets": 1}

    def test_an_untiered_model_is_named_rather_than_dropped(self, registry):
        registry.register("maya://model/x", "X", "credit.pd.scorecard",
                          "credit", "person/o", "LE-US-01", "p",
                          actor="j.okafor")
        out = Portfolio(registry).by("tier")
        assert {c["value"] for c in out["cells"]} == {"untiered"}

    def test_the_cut_is_ordered_by_what_is_outstanding(self, registry):
        """A cut sorted alphabetically buries whatever needs doing."""
        _register(registry)
        owed = {"maya://model/m2": 4}
        out = Portfolio(registry, worklist=FakeWorklist(owed)).by("domain")
        assert out["cells"][0]["value"] == "markets"
        assert "buries whatever needs doing" in out["detail"]

    def test_a_clean_estate_says_so(self, registry):
        _register(registry)
        out = Portfolio(registry, worklist=FakeWorklist()).by("domain")
        assert "nothing is outstanding anywhere" in out["detail"]


class TestTheHeatmapIsShadedByWhatIsOwed:
    def test_a_grid_is_produced(self, registry):
        _register(registry)
        out = Portfolio(registry).heatmap("domain", "tier")
        assert set(out["row_values"]) == {"credit", "markets"}
        assert set(out["column_values"]) == {"1", "3"}

    def test_the_shading_is_owed_and_not_count(self, registry):
        """A cell with forty healthy models and a cell with one that is missing
        its validation are not the same cell."""
        _register(registry)
        owed = {"maya://model/m0": 3}
        out = Portfolio(registry, worklist=FakeWorklist(owed)).heatmap(
            "domain", "tier")
        assert out["grid"]["credit"]["1"]["owed"] == 3
        assert out["grid"]["credit"]["3"]["owed"] == 0
        assert out["worst_cell"] == 3
        assert "not by count" in out["detail"]

    def test_one_dimension_against_itself_is_refused(self, registry):
        with pytest.raises(EstateError) as caught:
            Portfolio(registry).heatmap("tier", "tier")
        assert caught.value.code == "same_dimension"
        assert "a list with extra steps" in caught.value.detail


class TestTheTrendIsFoldedFromTheChain:
    def test_without_a_projection_it_says_so_rather_than_flatlining(self,
                                                                    registry):
        """A flat line looks like an answer."""
        out = Portfolio(registry).trend()
        assert out["available"] is False
        assert "would look like an answer" in out["detail"]

    def test_each_point_carries_the_chain_hash(self, registry, evidence):
        """A point somebody could have rewritten is not evidence."""
        from core.registry.asat import AsAtProjection
        _register(registry)
        out = Portfolio(registry, as_at=AsAtProjection(evidence, registry)
                        ).trend(points=3, span_days=30)
        assert out["count"] == 3
        assert all("chain_hash" in p for p in out["points"])
        assert "rather than a stored snapshot" in out["detail"]

    def test_it_is_true_for_dates_before_anybody_added_a_snapshot_table(
            self, registry, evidence):
        """The failure every register has: a nightly table that starts on the
        day somebody remembered it and is wrong for every day before."""
        from core.registry.asat import AsAtProjection
        _register(registry)
        portfolio = Portfolio(registry, as_at=AsAtProjection(evidence,
                                                             registry))
        out = portfolio.trend(points=2, span_days=365)
        assert out["points"][0]["models"] == 0, "a year ago there was nothing"
        assert out["points"][-1]["models"] == 3
        assert out["grew_by"] == 3


class TestTheAggregateQuestion:
    def test_an_estate_with_no_exposure_says_the_question_has_no_answer(
            self, registry):
        """Rather than reporting zero, which reads as *nothing is at risk*."""
        _register(registry)
        out = Portfolio(registry, worklist=FakeWorklist()).aggregate()
        assert out["exposure_known_for"] == 0
        assert "has no answer here yet" in out["detail"]

    def test_it_weights_by_exposure_and_says_what_it_covers(self, registry):
        """A weighted answer over a third of an estate presented as THE answer
        would be worse than the count it replaced."""
        models = _register(registry)
        rows = {m["id"]: [{"assessed_at": 1.0,
                           "facts": {"exposure": 1e9 if m["urn"].endswith("m0")
                                     else 1e6}}]
                for m in models[:2]}
        out = Portfolio(registry, worklist=FakeWorklist(
            {"maya://model/m0": 2}), risk=FakeRisk(rows)).aggregate()
        assert out["exposure_known_for"] == 2
        assert out["exposure_coverage"] == pytest.approx(2 / 3, rel=1e-3)
        assert out["share_of_exposure_owing"] > 0.99
        assert "covers 67% of the estate" in out["detail"]

    def test_a_model_with_no_recorded_exposure_is_not_treated_as_zero(
            self, registry):
        """A model with no recorded exposure and a model with none are
        different facts, and only one should shrink a weighted average."""
        models = _register(registry)
        rows = {models[0]["id"]: [{"assessed_at": 1.0,
                                   "facts": {"exposure": 1e9}}]}
        out = Portfolio(registry, worklist=FakeWorklist(),
                        risk=FakeRisk(rows)).aggregate()
        assert out["exposure_total"] == 1e9
        assert out["exposure_known_for"] == 1


class TestItDoesNotGoBlank:
    def test_a_worklist_that_raises_does_not_take_the_view_with_it(self,
                                                                   registry):
        """A governance dashboard that goes blank when one model is malformed
        is a dashboard nobody trusts."""
        class Exploding:
            def for_model(self, model, now=None):
                raise RuntimeError("boom")

        _register(registry)
        out = Portfolio(registry, worklist=Exploding()).by("domain")
        assert out["models"] == 3 and out["owed"] == 0


class TestOverHttp:
    def test_the_dimensions_are_served_with_their_meanings(self, client,
                                                           people):
        r = client.get("/api/v1/portfolio/dimensions", auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        names = {d["dimension"] for d in r.json()["dimensions"]}
        assert names == set(DIMENSIONS)
        assert all(d["means"] for d in r.json()["dimensions"])

    def test_a_cut_is_served(self, registered, people):
        r = registered.get("/api/v1/portfolio", auth=people["a.mehta"],
                           params={"dimension": "domain"})
        assert r.status_code == 200, r.text
        assert r.json()["cells"]

    def test_an_unknown_dimension_is_refused(self, client, people):
        r = client.get("/api/v1/portfolio", auth=people["a.mehta"],
                       params={"dimension": "colour"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "unknown_dimension"

    def test_the_heatmap_is_served(self, registered, people):
        r = registered.get("/api/v1/portfolio/heatmap", auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        assert "not by count" in r.json()["detail"]

    def test_the_trend_is_served_with_chain_hashes(self, registered, people):
        r = registered.get("/api/v1/portfolio/trend", auth=people["a.mehta"],
                           params={"points": 3, "span_days": 30})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["available"] is True and body["count"] == 3
        assert all("chain_hash" in p for p in body["points"])

    def test_the_aggregate_is_served(self, registered, people):
        r = registered.get("/api/v1/portfolio/aggregate",
                           auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        assert "exposure_coverage" in r.json()

    def test_the_screen_says_the_shading_is_not_count(self, registered,
                                                      people):
        registered.post("/login", data={"username": "admin",
                                        "password": "maya-admin-dev",
                                        "next": "/portfolio"})
        body = registered.get("/portfolio").text
        assert "never by count" in body
        assert "Not a snapshot table" in body
