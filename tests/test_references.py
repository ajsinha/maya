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
        index, _features = nj_estate
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


class TestTheDependencyScreen:
    """The screen and the delete check read the same index, which is the point:
    one listing three usages while the other knows about four would say a thing
    is safe to remove and then refuse."""

    def _login(self, client):
        from tests.api_helpers import login

        login(client)

    def test_it_is_reachable_from_the_menu(self, client):
        self._login(client)
        assert 'href="/dependencies"' in client.get("/dashboard").text

    def test_it_shows_what_refers_to_a_model(self, registered, client):
        self._login(client)
        body = registered.get("/dependencies",
                              params={"kind": "model", "id": URN}).text
        assert "would be left broken" in body
        assert "3.2.1" in body, "the version is named"

    def test_it_says_plainly_when_nothing_refers(self, registered, client):
        self._login(client)
        registered.post("/api/v1/models", json={
            "urn": "maya://model/lonely.one", "name": "Lonely",
            "model_class": "c", "domain": "credit", "owner": "person/o",
            "legal_entity": "LE-US-01", "purpose": "nothing points at it"})
        body = registered.get(
            "/dependencies",
            params={"kind": "model", "id": "maya://model/lonely.one"}).text
        assert "Nothing refers to this" in body
        assert "nothing blocks a deletion" in body

    def test_it_offers_what_exists_rather_than_an_empty_box(self, registered,
                                                            client):
        """A mistyped name answers 'nothing refers to this', which is the most
        dangerous wrong answer this screen can give."""
        self._login(client)
        body = registered.get("/dependencies", params={"kind": "model"}).text
        assert 'list="dep-suggestions"' in body
        assert URN in body, "the estate's own models are offered"

    def test_the_screen_and_the_delete_agree(self, registered, client):
        """Not asserted in prose: the page is rendered from `to()` and the
        delete calls `refuse_if_referenced`, and both are checked here against
        the same subject."""
        report = registered.app.state.ctx["references"].to("model", URN)
        # The delete FIRST, on Basic credentials: once a session cookie exists
        # the CSRF guard refuses a state-changing request without a token,
        # which is the guard working and not the delete check answering.
        refused = registered.request("DELETE", f"/api/v1/models/{NAME}",
                                     params={"reason": "x"})
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"] == "still_referenced"

        self._login(client)
        page = registered.get("/dependencies",
                              params={"kind": "model", "id": URN}).text
        assert str(report["blocking"]) in page
        assert (report["blocking"] > 0) is (refused.status_code == 409)


class TestTheDeleteControlsAreOfferedSafely:
    """A screen that offers a delete which then refuses teaches people to
    ignore refusals — the same argument the menu filtering made. So each
    control is offered only where the register would consider the act at all,
    and every one of them links to what refers to the thing first."""

    def _login(self, client):
        from tests.api_helpers import login

        login(client)

    def test_the_catalogues_link_to_the_dependency_view(self, nj_estate, client):
        self._login(client)
        for path, kind in (("/features", "feature"),
                           ("/featuresets", "featureset")):
            body = client.get(path).text
            assert f"/dependencies?kind={kind}" in body, path

    def test_a_durable_feature_is_offered_no_delete(self, client):
        """It is retired, not destroyed — offering the button would be offering
        a refusal.

        Defined through the API rather than through the `full_features` fixture:
        that service runs against the in-memory database and the application
        against a file, so a feature created there is invisible here.
        """
        client.post("/api/v1/features", json={
            "name": "durable_signal", "entity": "customer", "dtype": "numeric",
            "description": "not ephemeral", "owner": "person/d.raman"})
        self._login(client)
        body = client.get("/features").text
        assert "durable_signal" in body
        # The BUTTON, not the string — the page's own handler names the class
        # in its script whether or not a row carries one.
        assert "ms-2 destroy-feature" not in body, \
            "nothing in this catalogue is ephemeral, so nothing is deletable"

    def test_the_model_page_offers_delete_only_to_an_administrator(
            self, registered, client, people):
        """Every state-changing setup call happens BEFORE the first sign-in.

        Once a session cookie exists the CSRF guard refuses a POST without a
        token — correctly — and a setup call that silently 403s leaves the test
        asserting against the previous principal. That has now caught me three
        times in this session, in three different files.
        """
        from tests.api_helpers import login

        registered.post("/api/v1/principals", json={
            "username": "nodelete", "display_name": "N", "roles": ["validator"],
            "password": "pw-long-enough-x"})

        login(client)
        assert 'id="delete-model"' in registered.get(
            "/model/credit.pd.smallbiz").text

        login(client, "nodelete", "pw-long-enough-x")
        body = registered.get("/model/credit.pd.smallbiz").text
        assert 'id="delete-model"' not in body, \
            "a validator holds no model:delete"

    def test_it_says_retiring_is_almost_always_right(self, registered, client):
        self._login(client)
        body = registered.get("/model/credit.pd.smallbiz").text
        assert "Retiring</strong> is" in body or "Retiring" in body
        assert "/dependencies?kind=model" in body

    def test_the_client_renders_the_refusal_whole(self):
        """The refusal names what refers to the model, and a summary of it
        would drop the half somebody can act on."""
        import pathlib

        script = (pathlib.Path(__file__).resolve().parents[1] / "web" /
                  "static" / "js" / "model-algebra-lifecycle.js").read_text()
        assert "A.refusalHtml(xhr)" in script
        assert "A.remove(" in script, "through the shared client, not its own ajax"
