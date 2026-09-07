"""What refers to what — asked once, answered for two different questions.

*Where is this feature used?* and *may I delete this?* are the same question
with different consequences, and building them separately is how they come to
disagree: a screen that lists three usages while a delete check knows about four
is a screen that says a thing is safe to remove and then refuses.

The gap this closes was real. `DELETE /models/{name}` checked that the caller
was an administrator and had given a reason, then removed the row. **Nineteen
tables carry a `model_id.`** Deleting a model with a live warrant, an open
finding, a monitor and three parameter sets left every one of those rows
pointing at an identifier that no longer resolves — and the evidence chain,
which survives the deletion by design, then described acts against a model
nobody could look up.
"""
from __future__ import annotations

import pytest

from core.references import KINDS, ReferenceIndex
from core.references.index import ReferencedError
from tests.conftest import NAME, URN


@pytest.fixture
def index(db, registry, full_features):
    return ReferenceIndex(db, registry, full_features)


@pytest.fixture
def nj_estate(db, registry, full_features):
    """The NJ estate from the featureset tests: features, derived, a view."""
    import datetime as dt

    sale = dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc).timestamp()
    f = full_features
    for name in ("living_area_sqft", "lot_size_sqft", "bedrooms"):
        f.define(name, "property_id", "numeric", name, "person/d.raman")
    f.define_derived("log_living_area", "log(living_area_sqft)", "numeric",
                     "log of floor area", "person/d.raman")
    f.define_derived("lot_to_living_ratio",
                     "lot_size_sqft / living_area_sqft", "numeric",
                     "parcel to floor area", "person/d.raman")
    rows = [{"entity_id": f"P{i}", "event_ts": sale, "ingest_ts": sale,
             "living_area_sqft": 1800.0 + i, "lot_size_sqft": 7000.0 + i,
             "bedrooms": 3} for i in range(3)]
    columns = ["living_area_sqft", "lot_size_sqft", "bedrooms"]
    f.create_view("nj_characteristics", "property_id", "person/o", columns)
    f.materialise("nj_characteristics", rows, columns)
    return ReferenceIndex(db, registry, f), f


class TestWhatRefersToAModel:

    def test_a_model_with_a_version_an_alias_and_a_warrant(self, registered,
                                                           db, features):
        """`registered` is the ordinary case: everything hangs off it."""
        ctx = registered.app.state.ctx
        report = ctx["references"].to("model", URN)
        kinds = {r["kind"] for r in report["references"]}
        assert {"model_version", "alias", "warrant"} <= kinds, kinds
        assert report["blocking"] > 0 and not report["deletable"]

    def test_a_model_nothing_refers_to_is_deletable(self, client):
        client.post("/api/v1/models", json={
            "urn": "maya://model/nothing.refers", "name": "Alone",
            "model_class": "c", "domain": "credit", "owner": "person/o",
            "legal_entity": "LE-US-01", "purpose": "registered by mistake"})
        report = client.app.state.ctx["references"].to(
            "model", "maya://model/nothing.refers")
        assert report["deletable"] and report["references"] == []
        assert report["detail"] == "nothing refers to this"

    def test_a_revoked_warrant_is_historical_rather_than_blocking(
            self, registered, people):
        """A register in which nothing may be deleted because something once
        happened grows without bound. A revoked grant reads correctly after the
        model is gone; a live one does not."""
        registered.post("/api/v1/warrants/revoke", auth=people["s.iqbal"],
                        json={"urn": URN, "reason": "test"})
        report = registered.app.state.ctx["references"].to("model", URN)
        warrants = [r for r in report["references"] if r["kind"] == "warrant"]
        assert warrants and not any(w["blocking"] for w in warrants)
        assert "revoked grant" in warrants[0]["why"]

    def test_it_names_what_refers_rather_than_saying_no(self, registered):
        r = registered.request("DELETE", f"/api/v1/models/{NAME}",
                               params={"reason": "no"})
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert "version 3.2.1" in detail
        assert "would be left pointing at nothing" in detail
        assert "retire this instead" in r.json()["remediation"]


class TestWhatRefersToAFeature:

    def test_a_view_carrying_it_blocks(self, nj_estate):
        index, name = nj_estate
        report = index.to("feature", "bedrooms")
        views = [r for r in report["references"]
                 if r["kind"] == "feature_view_version"]
        assert views and all(v["blocking"] for v in views)

    def test_a_derived_feature_reading_it_blocks(self, nj_estate):
        index, _ = nj_estate
        report = index.to("feature", "living_area_sqft")
        derived = [r for r in report["references"]
                   if r["kind"] == "derived_feature"]
        assert derived, "log_living_area and lot_to_living_ratio read it"

    def test_a_near_miss_name_is_not_a_reference(self, nj_estate):
        """`LIKE '%ltv%'` matches `ltv_band`, and a delete check that is wrong
        in that direction is one nobody can trust."""
        index, _ = nj_estate
        report = index.to("feature", "bed")
        assert report["references"] == []

    def test_an_unused_feature_is_deletable(self, nj_estate):
        index, features = nj_estate
        features.define("orphan_signal", "property_id", "numeric",
                        "defined and never used", "person/d.raman")
        assert index.to("feature", "orphan_signal")["deletable"]


class TestWhatRefersToAFeatureset:

    def test_its_own_versions_block_it(self, nj_estate):
        index, features = nj_estate
        features.define_featureset("refset", "property_id", "person/o",
                                   {"bedrooms": "numeric"},
                                   label_slot=None)
        features.publish_featureset("refset", {"bedrooms": "bedrooms"})
        report = index.to("featureset", "refset")
        assert not report["deletable"]
        assert any(r["kind"] == "featureset_version"
                   for r in report["references"])


class TestTheIndexItself:

    def test_it_refuses_a_kind_it_does_not_answer_for(self, index):
        with pytest.raises(ValueError, match="not something this index knows"):
            index.to("teapot", "x")

    def test_every_kind_it_names_can_be_asked(self, index):
        for kind in KINDS:
            assert index.to(kind, "nothing-of-this-name")["references"] == []

    def test_the_refusal_carries_a_code_like_every_other(self):
        """The discipline walker looks for the code as the first argument, and
        a class attribute would have left this status documented and raised by
        nothing as far as the walker could see."""
        exc = ReferencedError("still_referenced", "detail", "remedy")
        assert exc.code == "still_referenced"
        assert exc.as_problem()["error"] == "still_referenced"


class TestOverTheApi:

    def test_the_dependency_view_is_the_same_index(self, registered, people):
        r = registered.get("/api/v1/references", auth=people["a.mehta"],
                           params={"kind": "model", "id": URN})
        assert r.status_code == 200
        body = r.json()
        assert body["blocking"] > 0 and body["deletable"] is False
        assert all({"kind", "id", "label", "why", "blocking"} <= set(ref)
                   for ref in body["references"])

    def test_an_unknown_kind_is_a_refusal_naming_the_known_ones(
            self, registered, people):
        r = registered.get("/api/v1/references", auth=people["a.mehta"],
                           params={"kind": "teapot", "id": "x"})
        assert r.status_code == 422
        assert r.json()["error"] == "unknown_reference_kind"
        assert "model" in r.json()["detail"]
