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
                                  estate["markets.swap_pricer"], "input_to",
                                  actor="person/j.okafor")
        assert edge["kind"] == "input_to" and edge["means"]

    def test_a_model_cannot_relate_to_itself(self, composition, estate):
        with pytest.raises(RegistryError, match="cannot stand in the 'input_to' relation to itself"):
            composition.relate(estate["risk.var"], estate["risk.var"], "input_to")

    def test_the_same_edge_is_not_recorded_twice(self, composition, estate):
        composition.relate(estate["credit.pd"], estate["risk.var"], "input_to")
        with pytest.raises(RegistryError, match="already recorded as"):
            composition.relate(estate["credit.pd"], estate["risk.var"], "input_to")

    def test_an_unknown_relation_is_refused_by_name(self, composition, estate):
        with pytest.raises(RegistryError, match="not a relation between models"):
            composition.relate(estate["credit.pd"], estate["risk.var"], "vibes")

    def test_a_cycle_in_a_propagating_relation_is_refused(self, composition,
                                                          estate):
        """A model whose output is its own input has no defined value, and a
        blast radius over it does not terminate."""
        composition.relate(estate["rates.usd_curve"], estate["markets.swap_pricer"],
                           "input_to")
        composition.relate(estate["markets.swap_pricer"], estate["risk.var"], "input_to")
        with pytest.raises(RegistryError, match="would close a cycle"):
            composition.relate(estate["risk.var"], estate["rates.usd_curve"], "input_to")

    def test_removing_an_edge_needs_a_reason(self, composition, estate):
        composition.relate(estate["credit.pd"], estate["risk.var"], "input_to")
        with pytest.raises(RegistryError, match="needs a reason"):
            composition.unrelate(estate["credit.pd"], estate["risk.var"], "input_to", "")


class TestBlastRadius:
    def _stack(self, composition, estate):
        composition.relate(estate["rates.usd_curve"], estate["markets.swap_pricer"],
                           "input_to")
        composition.relate(estate["rates.usd_curve"], estate["markets.swaption"],
                           "input_to")
        composition.relate(estate["markets.swap_pricer"], estate["risk.var"], "input_to")
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
                           "input_to")
        composition.relate(estate["rates.usd_curve"], estate["markets.swaption"],
                           "input_to")
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
                           "input_to")
        composition.relate(second, estate["markets.swaption"], "input_to")
        out = composition.shared_dependencies(
            [estate["markets.swap_pricer"], estate["markets.swaption"]])
        assert out["shared"] == []
        assert "do not interact" in out["detail"]

    def test_it_finds_a_dependency_two_hops_up(self, composition, estate):
        """Shared inputs are rarely adjacent. A curve under a pricer under a VaR
        model is still the thing both rest on."""
        composition.relate(estate["rates.usd_curve"], estate["markets.swap_pricer"],
                           "input_to")
        composition.relate(estate["markets.swap_pricer"], estate["risk.var"], "input_to")
        composition.relate(estate["rates.usd_curve"], estate["markets.swaption"],
                           "input_to")
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
        composition.relate(estate["rates.usd_curve"], estate["risk.var"], "input_to")
        assert composition.edges_of(estate["risk.var"])["upstream"][0]["urn"] \
            == estate["rates.usd_curve"]
        assert composition.edges_of(estate["rates.usd_curve"])["downstream"][0]["urn"] \
            == estate["risk.var"]


class TestTheRelationIsNamedForWhatItIs:
    """`feeds` was a bad name in a bank.

    A *feed* here means a data feed — market data, a reference file, a nightly
    drop — so `A feeds B` read as though MAYA consumed or produced one. It does
    neither: it never moves data and never runs a model. The edge is a statement
    about two entries in the register, and the wire it describes is carried by
    somebody else's engine.
    """

    def test_the_published_vocabulary_offers_one_word_for_the_relation(self):
        from core.registry.composition import KINDS
        assert "input_to" in KINDS
        assert "feeds" not in KINDS, (
            "a vocabulary offering two words for one relation invites somebody "
            "to think they mean different things")

    def test_the_old_spelling_is_still_accepted_and_stored_as_the_new_one(self):
        """An existing caller and an existing row both keep working."""
        from core.registry.composition import canonical
        assert canonical("feeds") == "input_to"
        assert canonical("input_to") == "input_to"
        assert canonical("derives_from") == "derives_from"

    def test_it_is_recorded_under_the_new_name(self, composition, estate):
        edge = composition.relate(estate["rates.usd_curve"],
                                  estate["markets.swap_pricer"], "feeds",
                                  actor="person/o")
        assert edge["kind"] == "input_to"

    def test_the_meaning_says_maya_does_not_move_the_data(self):
        from core.registry.composition import KIND_MEANING
        assert "neither moves the data nor runs either end" in \
            KIND_MEANING["input_to"]

    def test_an_edge_created_as_feeds_can_be_removed_as_feeds(self, composition,
                                                              estate):
        """The alias has to work in BOTH directions or it is worse than none.

        `relate` canonicalised and `unrelate` did not, so an edge created under
        the old spelling was stored under the new one and could not be removed
        by the name it was created with — which is the worst possible shape for
        a compatibility alias: it accepts the call and then strands the row.
        """
        composition.relate(estate["rates.usd_curve"],
                           estate["markets.swap_pricer"], "feeds",
                           actor="person/o")
        removed = composition.unrelate(estate["rates.usd_curve"],
                                       estate["markets.swap_pricer"], "feeds",
                                       reason="no longer consumed",
                                       actor="person/o")
        assert removed


class TestAnEdgeCarriesSomeInputsAndNotAllOfThem:
    """`_check_composes` asked whether the source's output could stand in for
    the target's **entire** input schema.

    So a PD model feeding an ECL stack that also reads LGD, EAD and a discount
    curve was refused — *"PD does not provide lgd"*, which is true and is not
    what an edge claims. That is the ordinary shape of a model network, so the
    check refused the normal case and admitted only the degenerate one where a
    model reads nothing but its predecessor's output.

    The single test that covered composition constructed exactly that degenerate
    case, which is why it passed.
    """

    @pytest.fixture
    def typed(self, db, registry, evidence):
        """Wired WITH the version repository, so the type check actually runs.

        The file's shared `composition` fixture omits it, which makes
        `_check_composes` return early — so every test using that fixture
        exercises the edge *recording* and none of them exercises the typing.
        """
        from core.registry.composition import ModelComposition
        from db import ModelEdgeRepository, VersionRepository
        return ModelComposition(ModelEdgeRepository(db), registry.catalogue,
                                evidence, VersionRepository(db))

    @pytest.fixture
    def ecl_stack(self, registry):
        """PD → ECL, where ECL also reads three things PD does not produce."""
        def model(name, inputs, outputs):
            urn = f"maya://model/{name}"
            registry.register(urn, name, "credit", "retail", "person/o",
                              "LE-US-01", "p")
            registry.create_version(urn, "1.0.0", {
                "parameter_kind": "estimated_coefficients",
                "fit_procedure": "estimate",
                "input_schema": [{"name": n, "dtype": "numeric"} for n in inputs],
                "output_schema": [{"name": n, "dtype": "numeric"} for n in outputs]})
            return urn

        pd = model("credit.pd", ["dscr", "ltv"], ["pd_12m"])
        ecl = model("credit.ecl", ["pd_12m", "lgd", "ead", "discount_rate"],
                    ["ecl"])
        return pd, ecl

    def test_an_edge_supplying_one_of_four_inputs_is_recorded(self, typed,
                                                              ecl_stack):
        """The normal case, and the one that was refused."""
        pd, ecl = ecl_stack
        edge = typed.relate(pd, ecl, "input_to", "PD feeds the ECL stack")
        assert edge["kind"] == "input_to"

    def test_an_edge_supplying_nothing_is_still_refused(self, typed,
                                                        registry, ecl_stack):
        """The refusal has to keep meaning something. An edge carrying no field
        the target reads is the wire to nowhere it is named for."""
        pd, ecl = ecl_stack
        urn = "maya://model/unrelated.thing"
        registry.register(urn, "unrelated", "credit", "retail", "person/o",
                          "LE-US-01", "p")
        registry.create_version(urn, "1.0.0", {
            "parameter_kind": "none", "fit_procedure": "none",
            "input_schema": [], "output_schema": [{"name": "temperature",
                                                   "dtype": "numeric"}]})
        with pytest.raises(RegistryError, match="carries nothing|wire to nowhere"):
            typed.relate(urn, ecl, "input_to", "nonsense")

    def test_a_shared_field_that_does_not_type_check_is_refused(
            self, typed, registry, ecl_stack):
        """The order still applies — to the fields the two ends share. A wire
        arriving with the wrong type is worse than no wire, because everything
        downstream believes it."""
        _, ecl = ecl_stack
        urn = "maya://model/credit.pd_text"
        registry.register(urn, "pd text", "credit", "retail", "person/o",
                          "LE-US-01", "p")
        registry.create_version(urn, "1.0.0", {
            "parameter_kind": "rule_set", "fit_procedure": "author",
            "input_schema": [], "output_schema": [{"name": "pd_12m",
                                                   "dtype": "string"}]})
        with pytest.raises(RegistryError, match="share"):
            typed.relate(urn, ecl, "input_to", "wrong type on the wire")

    def test_the_composite_says_what_the_caller_must_still_supply(
            self, typed, ecl_stack):
        """This returned the source's inputs alone, so the derived type claimed
        the pair could be run on `dscr` and `ltv` — omitting the three fields
        the ECL stack reads from elsewhere."""
        pd, ecl = ecl_stack
        typed.relate(pd, ecl, "input_to", "PD feeds the ECL stack")
        composite = typed.composite_schema(pd, ecl)
        needs = {f["name"] for f in composite["input_schema"]}
        assert needs == {"dscr", "ltv", "lgd", "ead", "discount_rate"}
        assert composite["supplied_by_the_edge"] == ["pd_12m"]
        assert set(composite["still_supplied_by_the_caller"]) == {
            "lgd", "ead", "discount_rate"}
        assert [f["name"] for f in composite["output_schema"]] == ["ecl"]
