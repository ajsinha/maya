"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

FR-FEA-013 and FR-FEA-014: a tag that nothing reads.

Two requirements were marked *Partial* with almost the same sentence. Protected
characteristics and known proxies are **tagged**; no policy enforces anything.
Certification levels **exist** as a lifecycle act with their own permission; no
policy keys on them.

That is worse than an absent column, and the reason is the whole point of these
tests. An absent column is obviously absent. **A tagged estate looks governed**,
and a reviewer who sees `protected_basis: true` on a feature reasonably assumes
something acts on it.

What was missing was not a rule. `core/policy/` is where a firm's rules live and
a rule there is a predicate over a closed vocabulary of *published facts* — and
nothing in that vocabulary could see what a version's contract binds. So no rule
could be written about it however much a firm wanted one, which is why the tags
sat unread for the life of the catalogue.

This publishes the facts and **ships no default rule**, because the requirement
says *prohibit direct use in in-scope credit models while permitting controlled
use for fairness testing* — and a platform refusing on `protected_basis` alone
would refuse the fairness testing the same regulation requires.

The load-bearing test is `TestItReportsTheExposureEvenWithNoRule`. Publishing
facts and stopping there would leave a firm that never wrote the rule exactly
where it started, with no way to find out.
"""
from __future__ import annotations

import pytest

from core.features.screening import FACTS, WORST_FIRST, ContractScreening
from core.policy import vocabulary


@pytest.fixture
def screening(db, registry):
    from db import (ContractRepository, FeatureRepository,
                    FeatureViewRepository, FeatureViewVersionRepository)
    return ContractScreening(ContractRepository(db), FeatureViewRepository(db),
                             FeatureViewVersionRepository(db),
                             FeatureRepository(db), registry=registry)


def _feature(db, name, **flags):
    from db import FeatureRepository
    FeatureRepository(db).add({
        "name": name, "entity": "customer", "dtype": "float",
        "description": name, "owner": "person/j.okafor",
        "sensitivity": flags.get("sensitivity", "internal"),
        "pii": flags.get("pii", False),
        "protected_basis": flags.get("protected_basis", False),
        "proxy_risk": flags.get("proxy_risk", "none"),
        "certification": flags.get("certification", "certified"),
        "created_by": "j.okafor", "created_at": 0.0})


def _bind(db, version_id, view_name, features):
    """A view, a materialised version of it, and a contract pinning that."""
    from db import (ContractRepository, FeatureViewRepository,
                    FeatureViewVersionRepository)
    views = FeatureViewRepository(db)
    view = {"name": view_name, "entity": "customer", "owner": "o",
            "delta_table": view_name, "created_at": 0.0}
    views.add(view)
    FeatureViewVersionRepository(db).add({
        "feature_view_id": view["id"], "version": 1, "features": features,
        "delta_version": 0, "valid_time_column": "event_ts",
        "ingest_time_column": "ingest_ts", "row_count": 0,
        "quarantined": False, "assertion_report": {}, "quality_report": {},
        "materialised_at": 0.0})
    ContractRepository(db).add({
        "model_version_id": version_id, "digest": "sha256:x",
        "items": [{"view": view_name, "version": 1,
                   "feature_view_id": view["id"], "namespace": view_name}],
        "created_at": 0.0})


class TestTheFactsAreInTheVocabulary:
    """The half that was missing. A rule is a predicate over PUBLISHED facts,
    so a fact nothing publishes is one nobody can write a rule about."""

    @pytest.mark.parametrize("gate", ["version:approve", "alias:move"])
    @pytest.mark.parametrize("fact", [f for f, _ in FACTS])
    def test_every_fact_is_published_at_both_gates(self, gate, fact):
        assert fact in vocabulary(gate)

    def test_they_are_not_published_at_warrant_resolve(self):
        """Refusing a resolution for a feature the model was APPROVED with
        would take a model out of production for a decision somebody already
        made, at the worst possible moment."""
        for fact, _ in FACTS:
            assert fact not in vocabulary("warrant:resolve")

    def test_each_says_what_it_means(self):
        for _fact, means in FACTS:
            assert means.strip()


class TestItDecidesNothing:
    def test_the_posture_says_so(self):
        assert ContractScreening.posture()["decides_anything"] is False

    def test_it_says_why_there_is_no_default_rule(self):
        """A platform refusing on `protected_basis` alone would refuse the
        fairness testing the same regulation requires."""
        assert "the fairness testing the same regulation requires" in \
            ContractScreening.posture()["why_no_default_rule"]

    def test_it_names_the_defect_it_closes(self):
        assert "exists in a screenshot" in ContractScreening.posture()["detail"]

    def test_what_was_missing_was_the_facts_not_the_rule(self):
        assert "not a rule" in ContractScreening.posture()["what_was_missing"]


class TestWhatAContractBinds:
    def test_a_protected_characteristic_is_seen_through_the_view(
            self, screening, db, versioned):
        _feature(db, "age_band", protected_basis=True)
        _feature(db, "dscr")
        version = versioned
        _bind(db, version["id"], "risk.customer", ["age_band", "dscr"])
        facts = screening.facts_for(version["id"])
        assert facts["binds_protected_basis"] is True
        assert facts["protected"] == ["age_band"]

    def test_a_proxy_is_reported_separately(self, screening, db, versioned):
        """The harder case: a proxy is not obviously a protected
        characteristic, and a model built on one is discriminating without any
        column saying so."""
        _feature(db, "postcode", proxy_risk="high")
        version = versioned
        _bind(db, version["id"], "risk.geo", ["postcode"])
        facts = screening.facts_for(version["id"])
        assert facts["binds_proxy_risk"] is True
        assert facts["binds_protected_basis"] is False
        assert "without any column saying so" in facts["detail"]

    def test_an_uncertified_feature_is_seen(self, screening, db, versioned):
        _feature(db, "new_signal", certification="experimental")
        version = versioned
        _bind(db, version["id"], "risk.new", ["new_signal"])
        facts = screening.facts_for(version["id"])
        assert facts["binds_uncertified"] is True
        assert facts["lowest_certification"] == "experimental"

    def test_a_model_is_no_better_certified_than_its_worst_input(
            self, screening, db, versioned):
        _feature(db, "good", certification="certified")
        _feature(db, "bad", certification="deprecated")
        version = versioned
        _bind(db, version["id"], "risk.mixed", ["good", "bad"])
        assert screening.facts_for(version["id"])["lowest_certification"] \
            == "deprecated"

    def test_deprecated_ranks_below_experimental(self):
        """Experimental is *nobody has vouched for this yet*. Deprecated is
        *somebody has vouched against it*."""
        assert WORST_FIRST.index("deprecated") < \
            WORST_FIRST.index("experimental")

    def test_a_clean_contract_says_so(self, screening, db, versioned):
        _feature(db, "dscr")
        version = versioned
        _bind(db, version["id"], "risk.clean", ["dscr"])
        facts = screening.facts_for(version["id"])
        assert facts["binds_protected_basis"] is False
        assert "none tagged sensitive and all certified" in facts["detail"]

    def test_no_contract_is_not_the_same_as_a_clean_one(self, screening, db,
                                                        versioned):
        """A descriptor-only vendor model binds nothing, and that is normal.
        Reporting it as *binds nothing sensitive* would be a different claim."""
        version = versioned
        facts = screening.facts_for(version["id"])
        assert facts["has_contract"] is False
        assert "NOT the same as a contract that binds nothing sensitive" in \
            facts["detail"]

    def test_it_walks_the_pinned_version_not_the_current_one(
            self, screening, db, versioned):
        """A view that gained a protected characteristic after this contract
        was bound has not changed what this version reads, and reporting it
        would be a finding about a model that never saw the column."""
        from db import FeatureViewVersionRepository
        _feature(db, "dscr")
        _feature(db, "age_band", protected_basis=True)
        version = versioned
        _bind(db, version["id"], "risk.growing", ["dscr"])
        # Version 2 of the same view adds the protected column.
        from db import FeatureViewRepository
        view = FeatureViewRepository(db).one(name="risk.growing")
        FeatureViewVersionRepository(db).add({
            "feature_view_id": view["id"], "version": 2,
            "features": ["dscr", "age_band"], "delta_version": 1,
            "valid_time_column": "event_ts", "ingest_time_column": "ingest_ts",
            "row_count": 0, "quarantined": False, "assertion_report": {},
            "quality_report": {}, "materialised_at": 0.0})
        assert screening.facts_for(version["id"])["binds_protected_basis"] \
            is False


class TestItReportsTheExposureEvenWithNoRule:
    """The load-bearing property. Publishing facts and stopping there would
    leave a firm that never wrote the rule exactly where it started — tagged
    and unenforced — with no way to find out."""

    def test_the_estate_counts_models_binding_a_protected_characteristic(
            self, screening, db, versioned):
        _feature(db, "age_band", protected_basis=True)
        version = versioned
        _bind(db, version["id"], "risk.customer", ["age_band"])
        out = screening.across_the_estate()
        assert len(out["binding_protected_basis"]) == 1

    def test_it_says_when_no_rule_refuses(self, screening, db, versioned):
        _feature(db, "age_band", protected_basis=True)
        version = versioned
        _bind(db, version["id"], "risk.customer", ["age_band"])
        out = screening.across_the_estate()
        assert "No rule in force refuses on `binds_protected_basis`" in \
            out["detail"]
        assert "worse than an absent column" in out["detail"]

    def test_with_no_policies_wired_every_fact_is_unenforced(self, screening):
        assert all(not rules for rules in screening.enforced_by().values())

    def test_a_rule_naming_the_fact_is_found(self, db, registry):
        """Read from the rules actually in force rather than assumed. *No rule
        reads this* is the answer worth having, and it is only obtainable by
        looking."""
        class _Policies:
            @staticmethod
            def in_force(gate):
                return {"rule": "refuse when binds_protected_basis"} \
                    if gate == "version:approve" else None

        from db import (ContractRepository, FeatureRepository,
                        FeatureViewRepository, FeatureViewVersionRepository)
        engine = ContractScreening(
            ContractRepository(db), FeatureViewRepository(db),
            FeatureViewVersionRepository(db), FeatureRepository(db),
            registry=registry, policies=_Policies())
        assert engine.enforced_by()["binds_protected_basis"] == \
            ["version:approve"]
        assert engine.enforced_by()["binds_uncertified"] == []


class TestTheGateActuallyReceivesThem:
    """A vocabulary that advertises a fact nothing supplies is the same defect
    one layer up from the one this closes."""

    def test_the_fact_supplier_returns_all_five(self, db, registry,
                                                versioned):
        from core.policy.wiring import GateFacts
        from db import (ContractRepository, FeatureRepository,
                        FeatureViewRepository, FeatureViewVersionRepository)
        _feature(db, "age_band", protected_basis=True)
        version = versioned
        _bind(db, version["id"], "risk.customer", ["age_band"])
        screening = ContractScreening(
            ContractRepository(db), FeatureViewRepository(db),
            FeatureViewVersionRepository(db), FeatureRepository(db),
            registry=registry)
        facts = GateFacts(screening=screening)._screening(version)
        assert facts["binds_protected_basis"] is True
        assert set(facts) == {f for f, _ in FACTS}

    def test_a_screening_failure_leaves_them_false_and_says_so(self):
        """Everywhere else a failure leaves a fact at its STRICTEST value.
        These are the other way round, and the docstring explains why: a rule
        written as *refuse when binds_protected_basis* would fire on every
        version if the default were true, and a gate that refuses everything
        gets switched off within a day."""
        from core.policy.wiring import GateFacts

        class _Broken:
            @staticmethod
            def facts_for(_id):
                raise RuntimeError("no")

        facts = GateFacts(screening=_Broken())._screening({"id": "v1"})
        assert facts["binds_protected_basis"] is False
        import inspect
        source = inspect.getsource(GateFacts._screening)
        assert "permissive" in source
        assert "switched off within a day" in source


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/contract-screening").json()
        assert out["decides_anything"] is False
        assert len(out["facts"]) == 5

    def test_the_estate_answers(self, client, registered):
        out = client.get("/api/v1/contract-screening/estate")
        assert out.status_code == 200
        assert "enforced_by" in out.json()

    def test_one_version_answers(self, client, registered):
        out = client.get("/api/v1/contract-screening/version",
                         params={"urn": "maya://model/credit.pd.smallbiz",
                                 "semver": "3.2.1"})
        assert out.status_code == 200
        assert "has_contract" in out.json()

    def test_an_unknown_version_is_a_404(self, client, registered):
        out = client.get("/api/v1/contract-screening/version",
                         params={"urn": "maya://model/credit.pd.smallbiz",
                                 "semver": "9.9.9"})
        assert out.status_code == 404


@pytest.fixture
def versioned(registry, a_model, kernel_spec, contract_spec):
    """A version on the same `db` the screening fixture reads.

    The API-backed `registered` fixture builds its own database, so a
    repository opened on the `db` fixture cannot see it — which is a trap
    worth naming rather than working around silently.
    """
    from tests.conftest import URN
    registry.create_version(URN, "3.2.1", kernel_spec, contract_spec,
                            artifact_digest="sha256:" + "a" * 64)
    return registry.version(URN, "3.2.1")
