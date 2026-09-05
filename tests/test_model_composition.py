"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

How one model stands to another.

Features composed. Featuresets composed. Models did not, and the absence ran
deeper than a missing table: without model-to-model edges there is no blast
radius, no composite warrant, and no way to compute the result this account is
proudest of — that aggregate risk cannot be compositional, with the copy map as
the obstruction. That theorem is *about* shared dependency, and shared
dependency was not representable.
"""
from __future__ import annotations

import pytest

from core.registry.common import RegistryError


@pytest.fixture
def composition(db, registry, evidence):
    from core.registry import ModelComposition
    from db import ModelEdgeRepository
    return ModelComposition(ModelEdgeRepository(db), registry.catalogue, evidence)


@pytest.fixture
def estate(registry):
    """A small markets estate: one curve under everything, as they are."""
    for name, tier in (("rates.usd_curve", 1), ("markets.swap_pricer", 1),
                       ("markets.swaption", 2), ("risk.var", 1),
                       ("credit.pd", 2), ("credit.pd_challenger", 3)):
        urn = f"maya://model/{name}"
        registry.register(urn, name, name.split(".")[0], name.split(".")[0],
                          "person/j.okafor", "LE-US-01", "p", actor="person/o")
        registry.set_tier(registry.get(urn)["id"], tier)
    return {n: f"maya://model/{n}" for n in
            ("rates.usd_curve", "markets.swap_pricer", "markets.swaption",
             "risk.var", "credit.pd", "credit.pd_challenger")}


class TestRecordingHowModelsRelate:
    def test_a_model_can_feed_another(self, composition, estate):
        edge = composition.relate(estate["rates.usd_curve"],
                                  estate["markets.swap_pricer"], "feeds",
                                  actor="person/j.okafor")
        assert edge["kind"] == "feeds" and edge["means"]

    def test_a_model_cannot_relate_to_itself(self, composition, estate):
        with pytest.raises(RegistryError, match="cannot feeds itself"):
            composition.relate(estate["risk.var"], estate["risk.var"], "feeds")

    def test_the_same_edge_is_not_recorded_twice(self, composition, estate):
        composition.relate(estate["credit.pd"], estate["risk.var"], "feeds")
        with pytest.raises(RegistryError, match="already feeds"):
            composition.relate(estate["credit.pd"], estate["risk.var"], "feeds")

    def test_an_unknown_relation_is_refused_by_name(self, composition, estate):
        with pytest.raises(RegistryError, match="not a relation between models"):
            composition.relate(estate["credit.pd"], estate["risk.var"], "vibes")

    def test_a_cycle_in_a_propagating_relation_is_refused(self, composition,
                                                          estate):
        """A model whose output is its own input has no defined value, and a
        blast radius over it does not terminate."""
        composition.relate(estate["rates.usd_curve"], estate["markets.swap_pricer"],
                           "feeds")
        composition.relate(estate["markets.swap_pricer"], estate["risk.var"], "feeds")
        with pytest.raises(RegistryError, match="would close a cycle"):
            composition.relate(estate["risk.var"], estate["rates.usd_curve"], "feeds")

    def test_removing_an_edge_needs_a_reason(self, composition, estate):
        composition.relate(estate["credit.pd"], estate["risk.var"], "feeds")
        with pytest.raises(RegistryError, match="needs a reason"):
            composition.unrelate(estate["credit.pd"], estate["risk.var"], "feeds", "")


class TestBlastRadius:
    def _stack(self, composition, estate):
        composition.relate(estate["rates.usd_curve"], estate["markets.swap_pricer"],
                           "feeds")
        composition.relate(estate["rates.usd_curve"], estate["markets.swaption"],
                           "feeds")
        composition.relate(estate["markets.swap_pricer"], estate["risk.var"], "feeds")
        composition.relate(estate["credit.pd_challenger"], estate["credit.pd"],
                           "challenger_of")

    def test_a_change_reaches_everything_downstream(self, composition, estate):
        self._stack(composition, estate)
        out = composition.blast_radius(estate["rates.usd_curve"])
        assert {r["urn"] for r in out["reaches"]} == {
            estate["markets.swap_pricer"], estate["markets.swaption"],
            estate["risk.var"]}

    def test_distance_is_reported_so_the_immediate_ones_are_visible(
            self, composition, estate):
        self._stack(composition, estate)
        by_urn = {r["urn"]: r["distance"]
                  for r in composition.blast_radius(estate["rates.usd_curve"])["reaches"]}
        assert by_urn[estate["markets.swap_pricer"]] == 1
        assert by_urn[estate["risk.var"]] == 2

    def test_a_challenger_is_not_downstream_of_what_it_argues_with(
            self, composition, estate):
        """Counting it would inflate the answer precisely where the answer
        decides how much care a change needs."""
        self._stack(composition, estate)
        out = composition.blast_radius(estate["credit.pd_challenger"])
        assert out["reaches"] == [] and "reaches only itself" in out["detail"]

    def test_the_worst_tier_reached_is_reported(self, composition, estate):
        """A change reaching one Tier 1 model is not the same as one reaching
        five Tier 4s, and the count alone cannot say which happened."""
        self._stack(composition, estate)
        assert composition.blast_radius(estate["rates.usd_curve"])["worst_tier"] == 1


class TestSharedDependency:
    """The obstruction, made computable.

    Aggregate risk cannot be compositional because a network that COPIES a
    dependency is not the same as one that duplicates it. Supervisors ask about
    "common dependencies and shared assumptions" in prose; this is that question
    with an answer.
    """

    def test_two_models_on_one_curve_are_not_independent(self, composition,
                                                          estate):
        composition.relate(estate["rates.usd_curve"], estate["markets.swap_pricer"],
                           "feeds")
        composition.relate(estate["rates.usd_curve"], estate["markets.swaption"],
                           "feeds")
        out = composition.shared_dependencies(
            [estate["markets.swap_pricer"], estate["markets.swaption"]])
        assert len(out["shared"]) == 1
        assert out["shared"][0]["urn"] == estate["rates.usd_curve"]
        assert out["shared"][0]["count"] == 2
        assert "not" in out["detail"] and "independent faults" in out["detail"]

    def test_independently_built_inputs_share_nothing(self, composition, estate,
                                                       registry):
        """The counterpart network from the theorem: same shape, no copy."""
        second = "maya://model/rates.usd_curve_b"
        registry.register(second, "curve b", "rates", "rates", "person/o",
                          "LE-US-01", "p", actor="person/o")
        composition.relate(estate["rates.usd_curve"], estate["markets.swap_pricer"],
                           "feeds")
        composition.relate(second, estate["markets.swaption"], "feeds")
        out = composition.shared_dependencies(
            [estate["markets.swap_pricer"], estate["markets.swaption"]])
        assert out["shared"] == []
        assert "do not interact" in out["detail"]

    def test_it_finds_a_dependency_two_hops_up(self, composition, estate):
        """Shared inputs are rarely adjacent. A curve under a pricer under a VaR
        model is still the thing both rest on."""
        composition.relate(estate["rates.usd_curve"], estate["markets.swap_pricer"],
                           "feeds")
        composition.relate(estate["markets.swap_pricer"], estate["risk.var"], "feeds")
        composition.relate(estate["rates.usd_curve"], estate["markets.swaption"],
                           "feeds")
        shared = composition.shared_dependencies(
            [estate["risk.var"], estate["markets.swaption"]])["shared"]
        assert [s["urn"] for s in shared] == [estate["rates.usd_curve"]]


class TestInheritanceIsNotDependency:
    def test_derives_from_records_lineage_without_propagating(self, composition,
                                                              estate):
        """B built from A does not mean a change to A changes B: B has its own
        versions and its own approvals. The edge says where it came from."""
        composition.relate(estate["credit.pd"], estate["credit.pd_challenger"],
                           "derives_from")
        assert composition.blast_radius(estate["credit.pd"])["reaches"] == []
        edges = composition.edges_of(estate["credit.pd_challenger"])
        assert edges["upstream"][0]["kind"] == "derives_from"
        assert edges["upstream"][0]["propagates"] is False

    def test_both_directions_are_readable_from_either_end(self, composition,
                                                          estate):
        composition.relate(estate["rates.usd_curve"], estate["risk.var"], "feeds")
        assert composition.edges_of(estate["risk.var"])["upstream"][0]["urn"] \
            == estate["rates.usd_curve"]
        assert composition.edges_of(estate["rates.usd_curve"])["downstream"][0]["urn"] \
            == estate["risk.var"]
