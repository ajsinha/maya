"""A chain resolved as one unit, and an answer that must not be used.

Two failure modes: an authorisation that routes around the upstream state, and a
shadow answer nothing can tell from a production one.
"""
from __future__ import annotations

import pytest

from core.execution.composite import COMPOSING, MAX_NODES, CompositeWarrants
from core.execution.errors import WarrantError
from core.execution.shadow import (ADVISORY, MAX_SHADOW_DAYS, ShadowTraffic)
from tests.conftest import URN

DAY = 86400.0
NOW = 1_800_000_000.0


@pytest.fixture
def chain_models(registry, composition, a_model, kernel_spec, contract_spec):
    """curve → valuation → provision, the ordinary shape."""
    for urn, name, tier in (("urn:maya:model:curve", "Curve", 3),
                            ("urn:maya:model:valuation", "Valuation", 2)):
        registry.register(urn, name, "market.curve", "markets",
                          "person/j.okafor", "LE-US-01", "p")
        registry.set_tier(registry.get(urn)["id"], tier)
    composition.relate("urn:maya:model:curve", "urn:maya:model:valuation",
                       COMPOSING, actor="person/j.okafor")
    composition.relate("urn:maya:model:valuation", URN, COMPOSING,
                       actor="person/j.okafor")
    return registry


@pytest.fixture
def composition(repos, registry, evidence, db):
    from core.registry.composition import ModelComposition
    from db import ModelEdgeRepository
    return ModelComposition(ModelEdgeRepository(db), registry.catalogue, evidence)


@pytest.fixture
def composites(registry, composition, warrants):
    return CompositeWarrants(registry, composition, warrants)


class TestTheChainIsDerivedFromTheEdges:
    def test_the_order_puts_feeders_first(self, composites, chain_models):
        out = composites.chain(URN)
        assert out["order"] == ["urn:maya:model:curve",
                                "urn:maya:model:valuation", URN]

    def test_the_tier_is_the_join(self, composites, chain_models, registry,
                                  a_model):
        """A chain is at least as risky as its riskiest part."""
        registry.set_tier(a_model["id"], 4)
        out = composites.chain(URN)
        assert out["tier"] == 2 and out["terminal_tier"] == 4
        assert "only direction anybody ever wants to move it is down" in \
            out["detail"]

    def test_a_lone_model_is_not_a_composition(self, composites, a_model):
        out = composites.chain(URN)
        assert out["nodes"] == 1
        assert "an ordinary warrant with extra words" in out["detail"]

    def test_the_register_refuses_to_create_a_cycle(self, composition,
                                                    chain_models):
        """The first line of defence, and the one that normally holds."""
        from core.registry.common import RegistryError
        with pytest.raises(RegistryError):
            composition.relate(URN, "urn:maya:model:curve", COMPOSING,
                               actor="person/j.okafor")

    def test_a_cycle_that_arrived_anyway_is_refused_rather_than_truncated(
            self, composites, composition, chain_models, registry, db):
        """The backstop. An imported estate, a restored backup or a direct
        write can put a cycle in the table that `relate` would have refused,
        and answering with a truncated order would hand a caller a chain that
        runs and is wrong.
        """
        from db import ModelEdgeRepository
        ModelEdgeRepository(db).add({
            "from_model": registry.get(URN)["id"],
            "to_model": registry.get("urn:maya:model:curve")["id"],
            "kind": COMPOSING, "note": "", "type_checked": False,
            "created_by": "import", "created_at": 0.0})
        with pytest.raises(WarrantError) as e:
            composites.chain(URN)
        assert e.value.code == "cyclic_composition"
        assert "a chain that runs and is wrong" in e.value.remediation

    def test_a_challenger_edge_does_not_compose(self, composites, composition,
                                                registry, a_model):
        registry.register("urn:maya:model:chal", "Chal", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "p")
        composition.relate("urn:maya:model:chal", URN, "challenger_of",
                           actor="person/j.okafor")
        assert composites.chain(URN)["nodes"] == 1

    def test_untiered_nodes_are_named(self, composites, composition, registry,
                                      a_model):
        registry.register("urn:maya:model:untiered", "U", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "p")
        composition.relate("urn:maya:model:untiered", URN, COMPOSING,
                           actor="person/j.okafor")
        out = composites.chain(URN)
        assert out["untiered"] == ["urn:maya:model:untiered"]
        assert "join over an incomplete set" in out["detail"]

    def test_the_depth_bound_is_published(self):
        assert MAX_NODES >= 8


class TestAChainIsAsGovernedAsItsLeastGovernedLink:
    def test_a_node_that_refuses_refuses_the_composite(self, composites,
                                                       chain_models, warrants):
        with pytest.raises(WarrantError) as e:
            composites.resolve(URN, "production", "service/pricing", "p")
        assert e.value.code == "composite_refused"
        assert "as governed as its least governed link" in e.value.remediation

    def test_every_refusing_node_is_named_not_only_the_first(self, composites,
                                                             chain_models):
        """A caller told only about the first fixes it, retries, and discovers
        the second."""
        with pytest.raises(WarrantError) as e:
            composites.resolve(URN, "production", "service/pricing", "p")
        assert "urn:maya:model:curve" in e.value.detail
        assert "urn:maya:model:valuation" in e.value.detail

    def test_check_answers_without_minting_anything(self, composites,
                                                    chain_models):
        out = composites.check(URN, "production", "service/pricing", "p")
        assert out["resolves"] is False and "error" in out

    def test_there_is_no_composite_descriptor(self, composites, registry,
                                              warrants, approved_version):
        """Signing one would assert the chain as a whole is authorised, and
        three approvals for three models were not that."""
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(URN, "prod", "svc/pricer", "origination_decision",
                       actor="person/j.okafor")
        out = composites.resolve(URN, "prod", "svc/pricer",
                                 "origination_decision")
        assert out["composite_descriptor"] is None
        assert "and that is deliberate" in out["detail"]

    def test_each_node_carries_its_own_descriptor(self, composites, registry,
                                                  warrants, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(URN, "prod", "svc/pricer", "origination_decision",
                       actor="person/j.okafor")
        out = composites.resolve(URN, "prod", "svc/pricer",
                                 "origination_decision")
        assert out["nodes"][0]["urn"] == URN
        assert out["nodes"][0]["descriptor"]

    def test_the_estate_names_chains_that_raise_a_tier(self, composites,
                                                       chain_models, registry,
                                                       a_model):
        registry.set_tier(a_model["id"], 4)
        out = composites.across_the_estate()
        assert URN in out["tier_raised_by_the_chain"]
        assert "the number a feeder graph exists to produce" in out["detail"]

    def test_an_estate_with_no_edges_says_what_that_means(self, composites,
                                                          a_model):
        assert "a feeder relation nobody entered" in \
            composites.across_the_estate()["detail"]


# ------------------------------------------------------------------ shadow
@pytest.fixture
def shadow(registry, warrants, uses, invocations, a_model):
    return ShadowTraffic(registry, warrants, warrants.grants, uses=uses,
                         invocations=invocations)


@pytest.fixture
def uses(db, registry, evidence, warrants):
    from core.registry.uses import ModelUses
    from db import ModelUseRepository
    return ModelUses(ModelUseRepository(db), registry, evidence,
                     warrants=warrants)


@pytest.fixture
def invocations(db, registry, warrants):
    from core.execution.invocations import InvocationLog
    from db import InvocationRepository
    return InvocationLog(InvocationRepository(db), registry=registry,
                         warrants=warrants)


class TestMayaIsNotInSTheServingPath:
    def test_it_says_so(self):
        out = ShadowTraffic.describe()
        assert out["mirrors_traffic"] is False
        assert out["measures_the_share"] is False
        assert out["in_the_serving_path"] is False

    def test_the_share_is_an_attestation(self, shadow, a_model):
        out = shadow.authorise(URN, "production", "service/challenger",
                               declared_use="shadow-pd", mirrors="pd-scoring",
                               share=0.05)
        assert out["share_is_measured"] is False
        assert "**attestation**" in out["detail"]

    def test_an_impossible_share_is_refused(self, shadow, a_model):
        with pytest.raises(WarrantError) as e:
            shadow.authorise(URN, "production", "service/c",
                             declared_use="s", mirrors="pd", share=1.5)
        assert e.value.code == "share_out_of_range"

    def test_it_must_name_what_it_mirrors(self, shadow, a_model):
        with pytest.raises(WarrantError) as e:
            shadow.authorise(URN, "production", "service/c",
                             declared_use="s", mirrors="  ", share=0.1)
        assert e.value.code == "mirrors_required"


class TestTheRefusalThatStopsAnEscape:
    def test_a_production_use_is_refused_for_a_shadow(self, shadow, uses,
                                                      a_model):
        """Not by anybody deciding to use it — by nothing being able to tell
        the two apart."""
        uses.declare(URN, declared_use="pd-scoring", name="PD scoring",
                     purpose="approve applicants", owner="person/j.okafor",
                     actor="person/j.okafor")
        with pytest.raises(WarrantError) as e:
            shadow.authorise(URN, "production", "service/c",
                             declared_use="pd-scoring", mirrors="pd-scoring",
                             share=0.05)
        assert e.value.code == "shadow_use_is_a_production_use"
        assert "not by anybody deciding to use it" in e.value.remediation.lower()

    def test_a_shadows_own_use_is_allowed(self, shadow, uses, a_model):
        uses.declare(URN, declared_use="pd-scoring", name="PD scoring",
                     purpose="approve applicants", owner="person/j.okafor",
                     actor="person/j.okafor")
        out = shadow.authorise(URN, "production", "service/c",
                               declared_use="pd-shadow", mirrors="pd-scoring",
                               share=0.05)
        assert out["grant"]["flavour"] == ADVISORY

    def test_the_grant_is_never_authoritative(self, shadow, a_model):
        out = shadow.authorise(URN, "production", "service/c",
                               declared_use="s", mirrors="pd", share=0.1)
        assert out["authoritative"] is False


class TestAShadowThatNeverEnds:
    def test_it_is_reported_as_overstayed(self, shadow, a_model):
        out = shadow.authorise(URN, "production", "service/c",
                               declared_use="s", mirrors="pd", share=0.1)
        issued = out["grant"]["created_at"]
        later = shadow.status(URN, now=issued + (MAX_SHADOW_DAYS + 1) * DAY)
        assert later["overstayed"]
        assert "a second production model nobody approved" in later["detail"]

    def test_a_fresh_shadow_is_not(self, shadow, a_model):
        out = shadow.authorise(URN, "production", "service/c",
                               declared_use="s", mirrors="pd", share=0.1)
        issued = out["grant"]["created_at"]
        assert shadow.status(URN, now=issued + DAY)["overstayed"] == []

    def test_no_advisory_grant_is_worth_saying(self, shadow, a_model):
        assert "unanswerable a year later" in shadow.status(URN)["detail"]

    def test_an_empty_estate_is_ambiguous_and_says_so(self, shadow, a_model):
        out = shadow.across_the_estate()
        assert "cannot tell the two apart" in out["detail"]

    def test_the_estate_sorts_overstayed_first(self, shadow, registry,
                                               a_model):
        registry.register("maya://model/other.model", "O", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "p")
        first = shadow.authorise(URN, "production", "service/c",
                                 declared_use="s", mirrors="pd",
                                 share=0.1)["grant"]["created_at"]
        shadow.authorise("maya://model/other.model", "production", "service/c",
                         declared_use="s", mirrors="pd", share=0.1)
        out = shadow.across_the_estate(
            now=first + (MAX_SHADOW_DAYS + 1) * DAY)
        assert out["models"][0]["urn"] == URN
