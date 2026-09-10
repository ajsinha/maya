"""A model is at least as sensitive as the most sensitive thing it reads.

A feature has carried a `sensitivity` since the catalogue was written. It was
free text, displayed on one screen, and read by nothing — not the model that
consumed it, not the document compiled from that model, not one control
anywhere. A field describing a legal obligation that reaches no decision is a
field that will be wrong, because nothing ever depends on it being right.
"""
from __future__ import annotations

import pytest

from core.classification import (BOTTOM, DEFAULT, LEVELS, Classification,
                                 ClassificationError, at_least, join,
                                 normalise)
from core.features.common import FeatureError

#: A contract that assumes nothing about any field. The fixture contract bounds
#: `dscr`, and a kernel must declare every field its contract assumes — a
#: separate control, and not the one under test here.
NO_ASSUMPTIONS = {"assumptions": [], "guarantees": [],
                  "on_boundary_violation": "reject"}


class TestTheLattice:
    def test_the_join_is_the_most_sensitive_part(self):
        assert join("public", "confidential", "internal") == "confidential"
        assert join("internal", "restricted") == "restricted"

    def test_the_join_of_nothing_is_the_bottom(self):
        """The identity of the join. A model reading nothing is public, which
        is correct rather than convenient — defaulting it to internal would
        classify it above one reading public data."""
        assert join() == BOTTOM == "public"

    def test_the_order_is_total(self):
        for i, low in enumerate(LEVELS):
            for high in LEVELS[i:]:
                assert join(low, high) == high

    def test_higher_is_allowed_and_lower_is_not(self):
        assert at_least("restricted", "confidential")
        assert at_least("confidential", "confidential")
        assert not at_least("internal", "confidential")


class TestTheVocabularyIsClosed:
    def test_a_case_variant_normalises(self):
        assert normalise("  Confidential ") == "confidential"

    def test_an_unknown_class_is_refused_naming_the_real_ones(self):
        """A lattice over free text is a lattice over nothing: 'Confidential',
        'confidential' and 'CONF' are three classes to a computer."""
        with pytest.raises(ClassificationError) as caught:
            normalise("CONF")
        assert caught.value.code == "unknown_classification"
        assert "restricted" in caught.value.remediation

    def test_unstated_takes_the_default_which_is_not_the_bottom(self):
        """An unstated class is unknown, and treating unknown as public is the
        assumption that makes a classification scheme worthless."""
        assert normalise("") == DEFAULT == "internal"
        assert DEFAULT != BOTTOM

    def test_a_feature_cannot_be_defined_with_an_invented_class(self, features):
        with pytest.raises(FeatureError) as caught:
            features.catalogue.define(
                "cust.secret", "customer", "float", "d", "person/d.raman",
                sensitivity="TOP SECRET")
        assert "three classes to a computer" in str(caught.value)


def _feature(features, name, sensitivity="internal", pii=False):
    return features.catalogue.define(
        name, "customer", "float", f"the {name}", "person/d.raman",
        sensitivity=sensitivity, pii=pii)


class TestPropagatingToAModel:
    @pytest.fixture
    def classify(self, registry, features):
        return Classification(registry, features)

    def _versioned(self, registry, kernel_spec, contract_spec, inputs):
        from tests.conftest import URN
        kernel = {**kernel_spec, "input_schema": [
            {"name": n, "dtype": "float"} for n in inputs]}
        registry.create_version(URN, "1.0.0", kernel, NO_ASSUMPTIONS,
                                artifact_digest="sha256:" + "a" * 64,
                                actor="d.raman")
        return URN

    def test_a_model_inherits_the_highest_of_its_features(
            self, classify, registry, a_model, features, kernel_spec,
            contract_spec):
        _feature(features, "cust.income", "internal")
        _feature(features, "cust.arrears", "confidential")
        urn = self._versioned(registry, kernel_spec, contract_spec,
                              ["cust.income", "cust.arrears"])
        out = classify.of_model(urn)
        assert out["derived"] == "confidential"
        assert out["forced_by"] == ["cust.arrears"]

    def test_it_names_the_feature_that_forces_the_floor(
            self, classify, registry, a_model, features, kernel_spec,
            contract_spec):
        _feature(features, "cust.ssn", "restricted")
        urn = self._versioned(registry, kernel_spec, contract_spec,
                              ["cust.ssn"])
        assert "cust.ssn" in classify.of_model(urn)["detail"]

    def test_pii_propagates_as_its_own_fact(self, classify, registry, a_model,
                                            features, kernel_spec,
                                            contract_spec):
        """A confidential model on personal data and one on market data are the
        same class and different legal objects."""
        _feature(features, "cust.dob", "confidential", pii=True)
        _feature(features, "mkt.spread", "confidential")
        urn = self._versioned(registry, kernel_spec, contract_spec,
                              ["cust.dob", "mkt.spread"])
        out = classify.of_model(urn)
        assert out["pii"] is True
        assert out["classification"] == "confidential"
        assert "separate fact from the level" in out["detail"]

    def test_a_model_reading_nothing_catalogued_is_not_given_a_default(
            self, classify, registry, a_model, kernel_spec, contract_spec):
        """Reporting 'internal' for a model nobody has traced is reporting an
        assumption as a finding."""
        urn = self._versioned(registry, kernel_spec, contract_spec,
                              ["not.a.feature"])
        out = classify.of_model(urn)
        assert out["traceable"] is False
        assert out["unresolved_inputs"] == ["not.a.feature"]
        assert "reporting an assumption as a finding" in out["detail"]

    def test_a_declared_input_matching_the_catalogue_is_reported_as_a_match(
            self, classify, registry, a_model, features, kernel_spec,
            contract_spec):
        """A name match is a guess, and the answer says which path it came
        from."""
        _feature(features, "cust.income", "confidential")
        urn = self._versioned(registry, kernel_spec, contract_spec,
                              ["cust.income"])
        out = classify.of_model(urn)
        assert out["declared_only"] == ["cust.income"]
        assert out["bound"] == []


class TestDeclaringIt:
    @pytest.fixture
    def classify(self, registry, features):
        return Classification(registry, features)

    def _model_reading(self, registry, features, kernel_spec, contract_spec,
                       sensitivity):
        from tests.conftest import URN
        _feature(features, "cust.arrears", sensitivity)
        kernel = {**kernel_spec,
                  "input_schema": [{"name": "cust.arrears", "dtype": "float"}]}
        registry.create_version(URN, "1.0.0", kernel, NO_ASSUMPTIONS,
                                artifact_digest="sha256:" + "a" * 64,
                                actor="d.raman")
        return URN

    def test_declaring_higher_is_allowed(self, classify, registry, a_model,
                                         features, kernel_spec, contract_spec):
        """An output can be more disclosive than any single input, which is
        most of what re-identification is."""
        urn = self._model_reading(registry, features, kernel_spec,
                                  contract_spec, "internal")
        out = classify.declare(urn, "restricted")
        assert out["classification"] == "restricted"
        assert out["derived"] == "internal"

    def test_declaring_lower_is_refused_naming_the_feature(
            self, classify, registry, a_model, features, kernel_spec,
            contract_spec):
        urn = self._model_reading(registry, features, kernel_spec,
                                  contract_spec, "restricted")
        with pytest.raises(ClassificationError) as caught:
            classify.declare(urn, "internal")
        assert caught.value.code == "below_the_derived_floor"
        assert "cust.arrears" in caught.value.detail
        assert "reclassify cust.arrears" in caught.value.remediation

    def test_the_floor_still_stands_if_a_lower_class_reaches_the_row(
            self, classify, registry, a_model, features, kernel_spec,
            contract_spec):
        """Whatever is on the row, the join wins. A declaration cannot lower
        what the parts force."""
        urn = self._model_reading(registry, features, kernel_spec,
                                  contract_spec, "confidential")
        registry.update(urn, {"attributes": {"classification": "public"}},
                        "d.raman")
        out = classify.of_model(urn)
        assert out["declared"] == "public"
        assert out["classification"] == "confidential"
        assert "the floor stands" in out["detail"]


class TestWhatADocumentInherits:
    @pytest.fixture
    def classify(self, registry, features):
        return Classification(registry, features)

    def test_a_summary_inherits_the_join_of_everything_in_it(
            self, classify, registry, features, kernel_spec, contract_spec):
        """The one people get wrong. A board pack across the estate is nearly
        always higher than whoever asked for it expected."""
        _feature(features, "mkt.spread", "public")
        _feature(features, "cust.ssn", "restricted", pii=True)
        for i, (urn, field) in enumerate((("maya://model/a", "mkt.spread"),
                                          ("maya://model/b", "cust.ssn"))):
            registry.register(urn, f"M{i}", "credit.pd.scorecard", "credit",
                              "person/j.okafor", "LE-US-01", "p",
                              actor="j.okafor")
            registry.create_version(
                urn, "1.0.0",
                {**kernel_spec,
                 "input_schema": [{"name": field, "dtype": "float"}]},
                NO_ASSUMPTIONS, artifact_digest="sha256:" + "b" * 64,
                actor="d.raman")
        out = classify.of_documents(["maya://model/a", "maya://model/b"])
        assert out["classification"] == "restricted"
        assert out["inherited_from"] == ["maya://model/b"]
        assert out["pii"] is True

    def test_a_document_about_nothing_inherits_nothing(self, classify):
        out = classify.of_documents([])
        assert out["classification"] == BOTTOM
        assert "inherits nothing" in out["detail"]

    def test_an_untraceable_model_makes_the_floor_suspect(
            self, classify, registry, kernel_spec, contract_spec):
        registry.register("maya://model/c", "MC", "credit.pd.scorecard",
                          "credit", "person/j.okafor", "LE-US-01", "p",
                          actor="j.okafor")
        registry.create_version(
            "maya://model/c", "1.0.0",
            {**kernel_spec, "input_schema": [{"name": "unknown", "dtype": "float"}]},
            NO_ASSUMPTIONS, artifact_digest="sha256:" + "c" * 64, actor="d.raman")
        out = classify.of_documents(["maya://model/c"])
        assert out["untraceable"] == ["maya://model/c"]
        assert "this floor may be too low" in out["detail"]


class TestTheEstate:
    def test_it_counts_by_level_and_names_what_is_not_working(
            self, registry, features, a_model, kernel_spec, contract_spec):
        from tests.conftest import URN
        _feature(features, "cust.ssn", "restricted")
        registry.create_version(
            URN, "1.0.0",
            {**kernel_spec, "input_schema": [{"name": "cust.ssn", "dtype": "float"}]},
            NO_ASSUMPTIONS, artifact_digest="sha256:" + "a" * 64, actor="d.raman")
        out = Classification(registry, features).across_the_estate()
        assert out["count"] == 1
        assert out["by_level"] == {"restricted": 1}


class TestOverHttp:
    def _model_reading(self, client, people, sensitivity="confidential"):
        from tests.conftest import KERNEL, NAME, URN
        client.post("/api/v1/features", auth=people["d.raman"], json={
            "name": "cust.arrears", "entity": "customer", "dtype": "float",
            "description": "months in arrears", "owner": "person/d.raman",
            "sensitivity": sensitivity})
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD"})
        made = client.post(
            f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
            json={"semver": "1.0.0",
                  "kernel": {**KERNEL, "input_schema": [
                      {"name": "cust.arrears", "dtype": "float"}]},
                  "contract": NO_ASSUMPTIONS,
                  "artifact_digest": "sha256:" + "a" * 64})
        assert made.status_code == 201, made.text
        return URN

    def test_the_levels_are_served_with_their_meanings(self, client, people):
        r = client.get("/api/v1/classification-levels", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert [level["level"] for level in body["levels"]] == list(LEVELS)
        assert all(level["means"] for level in body["levels"])
        assert "not less sensitive than its most sensitive part" in body["detail"]

    def test_a_models_class_is_derived_and_read_back(self, client, people):
        urn = self._model_reading(client, people)
        r = client.get("/api/v1/classification", auth=people["d.raman"],
                       params={"urn": urn})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["derived"] == "confidential"
        assert body["forced_by"] == ["cust.arrears"]

    def test_declaring_below_the_floor_is_refused_by_name(self, client,
                                                          people):
        urn = self._model_reading(client, people, "restricted")
        r = client.put("/api/v1/classification", auth=people["j.okafor"],
                       params={"urn": urn}, json={"classification": "public"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "below_the_derived_floor"
        assert "cust.arrears" in r.json()["detail"]

    def test_declaring_above_it_is_allowed(self, client, people):
        urn = self._model_reading(client, people, "internal")
        r = client.put("/api/v1/classification", auth=people["j.okafor"],
                       params={"urn": urn},
                       json={"classification": "restricted"})
        assert r.status_code == 200, r.text
        assert r.json()["classification"] == "restricted"

    def test_an_invented_class_is_refused(self, client, people):
        urn = self._model_reading(client, people)
        r = client.put("/api/v1/classification", auth=people["j.okafor"],
                       params={"urn": urn}, json={"classification": "SECRET"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "unknown_classification"

    def test_a_feature_with_an_invented_class_is_refused_at_definition(
            self, client, people):
        r = client.post("/api/v1/features", auth=people["d.raman"], json={
            "name": "cust.x", "entity": "customer", "dtype": "float",
            "description": "d", "owner": "person/d.raman",
            "sensitivity": "TOP SECRET"})
        # 409 rather than 422: a FeatureError, because a caller defining a
        # feature should meet the refusal type of the thing it is defining.
        assert r.status_code == 409, r.text
        assert "three classes to a computer" in r.json()["detail"]

    def test_the_screen_explains_the_lattice(self, client, people):
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/classification"})
        body = client.get("/classification").text
        assert "not less sensitive than its most" in body
        assert "cannot be traced to any feature" in body
