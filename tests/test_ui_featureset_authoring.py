"""
MAYA — the featureset authoring screens.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Model developers rejected the platform because composing a featureset, filling
its slots and reading the plan back existed only as HTTP calls. These are the
screens for those acts, and the point of testing them over the real application
is that an interface tested through a shortcut is an interface nobody has
tested — the whole complaint was about what a person can reach.

Four things are asserted, in this order, because they are the four ways an
authoring page fails:

* **It renders at all.** A page with no test renders `Undefined` where the
  answer should be and nobody notices.
* **A real definition and a real version work end to end**, through the same
  endpoints the screen posts to, with the pin visible afterwards — the pin is
  the thing a reviewer needs and could not see anywhere before this.
* **A refusal reaches the person with its remediation.** Leakage is the one
  people disbelieve, so it is exercised three derivations deep, where no
  expression mentions the label at all.
* **No asset is external.** The interface has to render air-gapped, and a CDN
  reference is the sort of thing that works on every developer's machine.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.api_helpers import login as _login

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
SCRIPTS = ROOT / "web" / "static" / "js"

#: Everything this surface owns. Listed rather than globbed so that deleting a
#: page fails a test instead of silently shrinking the coverage.
PAGES = ("featureset_author_define.html", "featureset_author_bind.html",
         "featureset_author_plan.html", "featureset_author_refusals.html",
         "featureset_author_assemble.html", "featureset_author_lattice.html",
         "featureset_author_nav.html")
ASSETS = ("featureset-author-define.js", "featureset-author-bind.js",
          "featureset-author-assemble.js")

URN = "maya://model/nj.valuation"
ENTITY = "property_id"


def _csrf(client, path: str = "/featuresets/author") -> dict:
    """The session's token, read from the page as the browser hook does.

    Once a session cookie exists the authority is ambient, so the CSRF guard
    refuses an untokened state-changing request. That is the control working;
    these tests send the token rather than turning it off.
    """
    found = re.search(r'name="csrf-token" content="([^"]+)"', client.get(path).text)
    assert found, "every page carries the token, because every page can mutate"
    return {"X-MAYA-CSRF": found.group(1)}


def _prose(client, path: str) -> str:
    """A page's markup with runs of whitespace collapsed.

    These assertions are about sentences the page shows a person, and a
    sentence that happens to wrap in the template is the same sentence. Matching
    the raw bytes would make every reflow a test failure, which teaches whoever
    reflows it to stop reading the assertion.
    """
    return " ".join(client.get(path).text.split())


@pytest.fixture
def author(client):
    """A developer, a catalogue with a three-hop derivation, and a view.

    Set up over HTTP Basic and signed in afterwards: the setup is what a service
    account does, and doing it before the session exists keeps the CSRF guard
    out of the fixture without disabling it for the tests that follow.
    """
    admin = ("admin", "maya-admin-dev")
    assert client.post("/api/v1/principals", auth=admin, json={
        "username": "d.raman", "display_name": "D Raman",
        "roles": ["model_developer"], "password": "dev-pw-long-enough"}).status_code == 201
    dev = ("d.raman", "dev-pw-long-enough")

    for name, dtype in (("living_area_sqft", "numeric"), ("bedrooms", "integer"),
                        ("sale_price", "numeric"), ("lot_size", "numeric")):
        assert client.post("/api/v1/features", auth=dev, json={
            "name": name, "entity": ENTITY, "dtype": dtype,
            "description": name, "owner": "person/d.raman"}).status_code == 201

    # Three hops off the label. The last one's expression mentions neither the
    # label nor anything obviously derived from it, which is the case people
    # disbelieve and the reason the closure is transitive.
    for name, expression in (("price_per_sqft", "sale_price / living_area_sqft"),
                             ("price_index", "price_per_sqft * 100"),
                             ("affordability", "price_index / 12")):
        assert client.post("/api/v1/derived-features", auth=dev, json={
            "name": name, "expression": expression, "dtype": "numeric",
            "description": name}).status_code == 201

    assert client.post("/api/v1/feature-views", auth=dev, json={
        "name": "nj_characteristics", "entity": ENTITY, "owner": "person/d.raman",
        "features": ["living_area_sqft", "bedrooms", "sale_price", "lot_size"]
    }).status_code == 201
    assert client.post("/api/v1/feature-views/nj_characteristics/materialise",
                       auth=dev, json={"rows": [
                           {"entity_id": f"P{i}", "event_ts": 100.0 + i,
                            "ingest_ts": 110.0 + i,
                            "living_area_sqft": 1500.0 + 100 * i,
                            "bedrooms": 2 + (i % 3),
                            "sale_price": 300000.0 + 20000 * i,
                            "lot_size": 0.2 + i / 100} for i in range(10)]
                       }).status_code == 201

    # A kernel reading a column no featureset here provides, so `L-W10` has
    # something to refuse.
    client.post("/api/v1/models", auth=admin, json={
        "urn": URN, "name": "NJ Valuation", "model_class": "valuation.hedonic",
        "domain": "valuation", "owner": "person/d.raman",
        "legal_entity": "LE-US-01", "purpose": "residential valuation"})
    client.post("/api/v1/models/nj.valuation/versions", auth=admin, json={
        "semver": "1.0.0",
        "kernel": {"parameter_kind": "estimated_coefficients",
                   "fit_procedure": "estimate",
                   "input_schema": [{"name": "living_area_sqft", "dtype": "numeric"},
                                    {"name": "bedrooms", "dtype": "integer"},
                                    {"name": "garage_spaces", "dtype": "integer"}],
                   "output_schema": [{"name": "value", "dtype": "numeric"}]},
        "contract": {"assumptions": [], "guarantees": [],
                     "on_boundary_violation": "reject"},
        "artifact_digest": "sha256:" + "a" * 64})
    client.post("/api/v1/models/nj.valuation/assess", auth=admin,
                json={"exposure": 1e8, "purpose_class": "commercial"})

    _login(client, "d.raman", "dev-pw-long-enough")
    client.auth = None
    return client


@pytest.fixture
def declared(author):
    """A featureset with a label slot, declared through the screen's endpoint."""
    r = author.post("/api/v1/featuresets", headers=_csrf(author), json={
        "name": "nj_home_core", "entity": ENTITY,
        "slots": {"living_area_sqft": "numeric", "bedrooms": "integer",
                  "sale_price": "numeric"},
        "label_slot": "sale_price", "outcome_window_days": 30,
        "description": "the NJ hedonic columns"})
    assert r.status_code == 201, r.text
    return author


@pytest.fixture
def published(declared):
    """…and a version filling it, with one slot pinned explicitly."""
    r = declared.post("/api/v1/featuresets/nj_home_core/versions",
                      headers=_csrf(declared), json={
                          "bindings": {"living_area_sqft": {
                                           "feature": "living_area_sqft",
                                           "view": "nj_characteristics",
                                           "view_version": 1},
                                       "bedrooms": "bedrooms",
                                       "sale_price": "sale_price"},
                          "note": "first fill"})
    assert r.status_code == 201, r.text
    return declared


class TestEveryPageRenders:
    """A page with no test renders Undefined where the answer should be."""

    def test_the_composition_page_renders_before_anything_exists(self, author):
        body = _prose(author, "/featuresets/author")
        assert "Compose a featureset" in body
        assert "the register will say what that resolves to" in body

    def test_the_composition_page_publishes_the_fold_rather_than_assuming_it(
            self, author):
        """Composition is the part people get wrong, and they get it wrong for a
        good reason: the answer is not what you typed."""
        body = _prose(author, "/featuresets/author")
        assert "rightmost wins" in body
        assert "refused when it would do nothing" in body

    def test_the_composition_page_offers_only_types_the_catalogue_carries(
            self, author):
        """A slot's type must equal its feature's exactly, so a type nothing
        carries is a slot nothing can fill."""
        body = _prose(author, "/featuresets/author")
        assert '"numeric"' in body and '"integer"' in body

    def test_the_retrieval_vocabulary_comes_from_the_code_that_checks_it(
            self, author):
        """The older page offers `flat_forward` as a fill strategy, which is an
        alignment rule — so the example it teaches is refused."""
        body = _prose(author, "/featuresets/author")
        assert "zscore" in body and "most_frequent" in body
        assert "reaches into the future" in body

    def test_the_bind_page_renders(self, declared):
        body = _prose(declared, "/featureset/nj_home_core/bind")
        assert "Bind each slot" in body
        assert "living_area_sqft" in body and "bedrooms" in body

    def test_the_bind_page_says_there_is_no_dry_run(self, declared):
        """A screen that implied a check it cannot make would be claiming a
        control that is not there."""
        body = _prose(declared, "/featureset/nj_home_core/bind")
        assert "There is no dry run for bindings" in body
        assert "a refused publish writes nothing" in body

    def test_the_plan_page_renders(self, published):
        body = _prose(published, "/featureset/nj_home_core/plan/1")
        assert "The pins, deduplicated" in body
        assert "event_ts &lt;= label_ts" in body or "event_ts <= label_ts" in body

    def test_the_refusals_page_renders(self, published):
        body = _prose(published, "/featureset/nj_home_core/refusals")
        assert "A slot computed from the label" in body
        assert "A slot nothing fills" in body
        assert "A schema a wider model cannot consume" in body

    def test_the_assembly_page_renders(self, published):
        body = _prose(published, "/featureset/nj_home_core/assemble")
        assert "min(label_ts, as_of)" in body
        assert "P3" in body, "the spine is built against entities that exist"

    def test_the_lattice_page_renders_without_a_selection(self, author):
        body = _prose(author, "/featuresets/lattice")
        assert "can stand in for" in body
        assert "Pick two and compare" in body

    def test_an_unknown_featureset_is_404_on_every_page(self, author):
        for path in ("/featureset/ghost/bind", "/featureset/ghost/refusals",
                     "/featureset/ghost/assemble", "/featureset/ghost/plan/1"):
            assert author.get(path).status_code == 404, path

    def test_an_unknown_version_is_404_rather_than_an_empty_plan(self, published):
        """An empty shell for a version that does not exist reads as a version
        with nothing pinned, which is a different and much worse fact."""
        assert published.get("/featureset/nj_home_core/plan/99").status_code == 404

    def test_every_page_redirects_when_anonymous(self, client):
        for path in ("/featuresets/author", "/featuresets/lattice",
                     "/featureset/anything/bind"):
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 303 and "/login" in r.headers["location"], path


class TestADefinitionAndAVersionWorkEndToEnd:
    """Through the endpoints the screens post to, with the pin visible after."""

    def test_the_preview_resolves_without_declaring_anything(self, author):
        r = author.post("/api/v1/featuresets/preview", headers=_csrf(author),
                        json={"slots": {"living_area_sqft": "numeric"}})
        assert r.status_code == 200
        assert r.json()["declared_slots"] == ["living_area_sqft"]
        assert author.get("/api/v1/featuresets").json()["featuresets"] == [], \
            "a preview that declared something would fill the register with attempts"

    def test_a_version_pins_the_delta_version_and_the_page_shows_it(self, published):
        """The pin is the thing a reviewer needs and could not see before. A
        namespace without a Delta version is a path, and a path is mutable."""
        body = _prose(published, "/featureset/nj_home_core/plan/1")
        assert "features/property_id/nj_characteristics/v1" in body
        from db.table_backend import chosen

        assert f"{chosen()} " in body, (
            "the plan must show the storage pin. Its SPELLING belongs to the "
            "format — `delta v0` against `iceberg …698510` — and asserting "
            "one of them would be asserting which format this estate uses "
            "rather than that the pin is there")
        assert "and not only the path" in body

    def test_the_plan_carries_what_an_engine_reads(self, published):
        plan = published.get(
            "/api/v1/featuresets/nj_home_core/versions/1").json()
        assert plan["pit_rule"] == ("event_ts <= label_ts AND "
                                    "ingest_ts <= min(label_ts, as_of)")
        assert plan["namespaces"] == ["features/property_id/nj_characteristics/v1"]
        assert {s["slot"] for s in plan["slots"]} == {
            "living_area_sqft", "bedrooms", "sale_price"}
        assert plan["label"]["feature"] == "sale_price"

    def test_rolling_forward_leaves_the_earlier_version_where_it_was(self, published):
        """Taking up new data is a deliberate act with a diff, not something
        that happens to somebody who already trained."""
        before = published.get(
            "/api/v1/featuresets/nj_home_core/versions/1").json()["digest"]
        assert published.post("/api/v1/featuresets/nj_home_core/roll-forward",
                              headers=_csrf(published)).status_code == 201
        after = published.get(
            "/api/v1/featuresets/nj_home_core/versions/1").json()["digest"]
        assert before == after
        body = _prose(published, "/featureset/nj_home_core/plan/2")
        assert "What moved since v1" in body

    def test_a_training_set_assembles_and_reports_both_layers(self, published):
        r = published.post("/api/v1/featuresets/nj_home_core/training-sets",
                           headers=_csrf(published), json={
                               "version": 1, "as_of": 500.0,
                               "spine": [{"entity_id": f"P{i}", "label_ts": 300.0}
                                         for i in range(10)]})
        assert r.status_code == 201, r.text
        snapshot = r.json()
        assert snapshot["pit_verified"] is True
        assert snapshot["pit_report"]["layer"] == "sampled"
        assert snapshot["featureset_version"] == 1
        body = _prose(published, "/featureset/nj_home_core/assemble")
        assert "independently recomputed" in body
        assert snapshot["name"] in body

    def test_the_export_offers_the_moment_it_has_to_speak_for(self, published):
        """The older featureset page links `?format=parquet` with no `as_of`,
        which is refused: an export is a claim about what was known at a moment,
        and joining the parts without one pairs each feature's whole history
        against every other feature's."""
        body = _prose(published, "/featureset/nj_home_core/plan/1")
        assert 'name="as_of"' in body and "required" in body
        refused = published.get(
            "/api/v1/featuresets/nj_home_core/versions/1/data",
            params={"format": "json"})
        assert refused.status_code == 409
        assert "what moment it speaks for" in refused.json()["detail"]
        served = published.get(
            "/api/v1/featuresets/nj_home_core/versions/1/data",
            params={"as_of": 500.0, "format": "json"})
        assert served.status_code == 200 and served.json()["returned"] == 10

    def test_the_plan_shows_the_retrieval_policy_and_who_decided_each_part(
            self, published):
        """The question about an inherited policy is never what it will do but
        who decided that."""
        assert published.put("/api/v1/featuresets/nj_home_core/policy",
                             headers=_csrf(published),
                             json={"defaults": {"normalise": {
                                 "living_area_sqft": "zscore"}}}
                             ).status_code == 200
        body = _prose(published, "/featureset/nj_home_core/plan/1")
        assert "zscore" in body and "Decided by" in body
        assert "rightmost wins" in body

    def test_composition_shows_what_each_parent_contributes_and_the_drift(
            self, published):
        """A child whose parent has moved is a thing to be told about."""
        token = _csrf(published)
        published.post("/api/v1/featuresets", headers=token, json={
            "name": "nj_parcel", "entity": ENTITY, "slots": {"lot_size": "numeric"}})
        assert published.post("/api/v1/featuresets", headers=token, json={
            "name": "nj_full", "entity": ENTITY,
            "composes": [{"name": "nj_home_core"}, {"name": "nj_parcel"}],
            "operations": [{"op": "add", "name": "garage_spaces",
                            "value": {"dtype": "integer"}}],
            "label_slot": "sale_price"}).status_code == 201
        body = _prose(published, "/featureset/nj_full/bind")
        assert "Composed from" in body and "nj_parcel" in body
        assert "garage_spaces" in body, "a slot added by an operation is its own"
        # Setting a parent's policy is a definition change, so the child that
        # stamped the old definition drifts.
        assert published.put("/api/v1/featuresets/nj_parcel/policy", headers=token,
                             json={"defaults": {"normalise": {"lot_size": "zscore"}}}
                             ).status_code == 200
        body = _prose(published, "/featureset/nj_full/bind")
        assert "A parent has moved" in body
        assert "definition v1" in body and "definition v2" in body


class TestTheLatticeIsAskableRatherThanAsserted:
    """`refines`, `meet` and `join` had no caller in the platform at all — the
    structure was asserted in the law tests and unavailable to anybody deciding
    whether one featureset could serve two models. That question is a meet."""

    def test_a_featureset_that_does_not_cover_a_kernel_says_which_field(
            self, published):
        body = _prose(
            published, f"/featuresets/lattice?left=fs:nj_home_core&right=mv:{URN}@1.0.0")
        assert "garage_spaces" in body
        assert "does not provide" in body or "Missing" in body

    def test_the_meet_and_the_join_are_both_rendered(self, published):
        body = _prose(
            published, f"/featuresets/lattice?left=fs:nj_home_core&right=mv:{URN}@1.0.0")
        assert "the meet" in body and "the join" in body
        assert "must refine this" in body

    def test_the_top_element_is_the_identity_and_is_checked_not_claimed(
            self, published):
        body = _prose(
            published, "/featuresets/lattice?left=fs:nj_home_core&right=top")
        assert "is the identity" in body
        assert "There is deliberately no bottom" in body

    def test_a_composed_featureset_is_judged_on_what_it_inherited(
            self, published):
        """This pinned a defect, and the pin did its job.

        `FeaturesetRegistry.schema` built the comparison from the featureset's
        own row while `publish` fills the **resolved** schema — so a set
        composed from parents reported an empty schema and satisfied no kernel
        at all, which made composition unusable end to end. The screens showed
        what was enforced and named the file, rather than papering over it.

        `schema()` now resolves, so the comparison is over the slots the set
        actually has. The assertion is inverted rather than deleted, because a
        pin that is removed when the defect is fixed leaves nothing watching the
        behaviour it was pinning.
        """
        published.post("/api/v1/featuresets", headers=_csrf(published), json={
            "name": "nj_child", "entity": ENTITY,
            "composes": [{"name": "nj_home_core"}], "label_slot": "sale_price"})
        resolved = published.get(
            "/api/v1/featuresets/nj_child/resolved").json()
        inherited = {"living_area_sqft", "bedrooms", "sale_price"}
        assert set(resolved["slots"]) == inherited

        registry = published.app.state.ctx["features"].sets
        named = {f.name for f in registry.schema("nj_child").fields}
        assert named == inherited - {"sale_price"}, (
            "a composed featureset is judged on an empty schema again")

    def test_the_fold_is_shown_to_be_order_dependent(self, published):
        """Associativity and the identity are laws asserted elsewhere. What a
        screen can show is the part people get wrong: rightmost wins."""
        published.post("/api/v1/featuresets", headers=_csrf(published), json={
            "name": "nj_parcel", "entity": ENTITY, "slots": {"lot_size": "numeric"}})
        body = _prose(
            published, "/featuresets/lattice?left=fs:nj_home_core&right=fs:nj_parcel")
        assert "run both ways round" in body
        assert "not commutative" in body


class TestTheRefusalsReachThePersonWithTheirRemediation:
    """These refusals are why the object exists. A developer should meet them on
    a screen rather than in a 409 from curl."""

    def test_leakage_is_refused_three_derivations_away(self, author):
        """The case people disbelieve: `affordability`'s expression mentions
        neither the label nor anything that obviously reads it."""
        token = _csrf(author)
        author.post("/api/v1/featuresets", headers=token, json={
            "name": "nj_leaky", "entity": ENTITY,
            "slots": {"area": "numeric", "answer": "numeric"},
            "label_slot": "answer"})
        r = author.post("/api/v1/featuresets/nj_leaky/versions", headers=token,
                        json={"bindings": {"answer": "sale_price",
                                           "area": "affordability"}})
        assert r.status_code == 409, r.text
        problem = r.json()
        assert problem["error"] == "feature_refused"
        assert "computed from 'sale_price'" in problem["detail"]
        assert "leaks the answer into the training set" in problem["detail"]
        assert problem["remediation"], "a refusal a caller cannot act on is a 400"

    def test_the_refusals_page_names_every_feature_that_reads_the_label(
            self, author):
        token = _csrf(author)
        author.post("/api/v1/featuresets", headers=token, json={
            "name": "nj_leaky", "entity": ENTITY,
            "slots": {"area": "numeric", "answer": "numeric"},
            "label_slot": "answer"})
        author.post("/api/v1/featuresets/nj_leaky/versions", headers=token,
                    json={"bindings": {"answer": "sale_price",
                                       "area": "living_area_sqft"}})
        body = _prose(author, "/featureset/nj_leaky/refusals")
        for leaking in ("price_per_sqft", "price_index", "affordability"):
            assert leaking in body, leaking
        assert "however many hops away" in body
        assert "declare the thing an output rather than a feature" in body

    def test_an_unfilled_slot_is_refused_and_the_page_says_which(self, declared):
        r = declared.post("/api/v1/featuresets/nj_home_core/versions",
                          headers=_csrf(declared),
                          json={"bindings": {"bedrooms": "bedrooms"}})
        assert r.status_code == 409
        assert "unfilled" in r.json()["detail"]
        body = _prose(declared, "/featureset/nj_home_core/refusals")
        assert "A slot nothing fills" in body
        assert "unfilled" in body

    def test_a_binding_naming_no_slot_is_refused_as_a_model_change(self, declared):
        r = declared.post("/api/v1/featuresets/nj_home_core/versions",
                          headers=_csrf(declared), json={
                              "bindings": {"living_area_sqft": "living_area_sqft",
                                           "bedrooms": "bedrooms",
                                           "sale_price": "sale_price",
                                           "lot_size": "lot_size"}})
        assert r.status_code == 409
        assert "adding a slot changes the schema" in r.json()["detail"]

    def test_a_schema_a_wider_model_cannot_consume_is_shown_before_a_warrant(
            self, published):
        """Until this page the only way to find out was to try to issue a fit
        warrant, which writes."""
        body = _prose(published, "/featureset/nj_home_core/refusals")
        assert "NJ Valuation" in body and "garage_spaces" in body
        assert "schema_not_satisfied" in body
        assert "a model change and not a data change" in body

    def test_the_page_says_what_sealing_forbids_and_what_it_does_not(
            self, published):
        body = _prose(published, "/featureset/nj_home_core/refusals")
        assert "Another version" in body
        assert "final, not inert" in body

    def test_an_ambiguous_binding_is_reported_before_it_is_attempted(
            self, published):
        """Where two views carry a feature the register refuses and asks for a
        name; a screen that picked would be choosing which bytes a model trains
        on."""
        body = _prose(published, "/featureset/nj_home_core/refusals")
        assert "A binding that cannot be pinned exactly" in body
        assert ("refused even when only one version exists") in body
        assert "nj_characteristics" in body


class TestNothingIsFetchedFromTheInternet:
    """The interface must render air-gapped. A CDN reference works on every
    developer's machine and on no customer's."""

    MARKERS = ("cdn.", "//code.jquery", "googleapis", "jsdelivr", "unpkg",
               "http://", "https://")

    def test_no_page_references_an_external_asset(self, published):
        published.post("/api/v1/featuresets", headers=_csrf(published), json={
            "name": "nj_parcel", "entity": ENTITY, "slots": {"lot_size": "numeric"}})
        for path in ("/featuresets/author", "/featureset/nj_home_core/bind",
                     "/featureset/nj_home_core/plan/1",
                     "/featureset/nj_home_core/refusals",
                     "/featureset/nj_home_core/assemble",
                     "/featuresets/lattice",
                     "/featuresets/lattice?left=fs:nj_home_core&right=fs:nj_parcel"):
            body = _prose(published, path)
            for marker in self.MARKERS:
                assert marker not in body, f"{marker} referenced in {path}"

    def test_the_scripts_hold_no_url(self):
        for asset in ASSETS:
            source = (SCRIPTS / asset).read_text(encoding="utf-8")
            assert "http://" not in source and "https://" not in source, asset

    def test_the_scripts_are_served(self, author):
        for asset in ASSETS:
            r = author.get(f"/static/js/{asset}")
            assert r.status_code == 200, asset

    def test_the_pages_load_the_csrf_hook_rather_than_reimplementing_it(
            self, published):
        """A control every caller has to remember is one that will be missing
        from the page added next week."""
        for path in ("/featuresets/author", "/featureset/nj_home_core/bind",
                     "/featureset/nj_home_core/assemble"):
            assert "/static/js/csrf.js" in published.get(path).text, path
        for asset in ASSETS:
            source = (SCRIPTS / asset).read_text(encoding="utf-8")
            assert "X-MAYA-CSRF" not in source, (
                f"{asset} attaches the token itself; csrf.js already does it "
                f"for every request, and two implementations of one control "
                f"means one of them is the stale one")

    def test_every_table_on_these_pages_has_a_header_row(self):
        """Enforced across the templates elsewhere; asserted for the ones built
        in JavaScript too, which that walk cannot see."""
        for asset in ASSETS:
            source = (SCRIPTS / asset).read_text(encoding="utf-8")
            assert source.count("<table") == source.count("<thead"), (
                f"{asset} builds a table with no header row")

    def test_the_screens_own_only_what_they_are_supposed_to(self):
        for page in PAGES:
            assert (TEMPLATES / page).exists(), page
        for asset in ASSETS:
            assert (SCRIPTS / asset).exists(), asset


class TestTheScreenDecidesNothing:
    """A client that re-implemented a governance rule would be a second
    implementation, and the second disagrees with the first eventually, in the
    direction of permitting more."""

    def test_the_declare_button_is_disabled_until_the_server_answers(self):
        source = (SCRIPTS / "featureset-author-define.js").read_text(encoding="utf-8")
        assert 'featuresets/preview' in source
        assert source.count('$("#fs-declare").prop("disabled", false)') == 1, (
            "there is exactly one place the button is enabled, and it is the "
            "success handler of the preview call")

    def test_the_feature_list_is_not_filtered_to_the_slot_type(self):
        """Offered, not enforced: a mismatch is refused by the register with a
        message naming both types, and hiding the option would teach nobody."""
        source = (SCRIPTS / "featureset-author-bind.js").read_text(encoding="utf-8")
        assert "NOT filtered to the slot's dtype" in source
        assert "f.dtype" in source, "the type is shown so the mistake is visible"

    def test_no_page_carries_its_own_copy_of_the_point_in_time_rule(self, published):
        """The rule is published as a string an engine implements, from
        `core.features.sets.PIT_RULE`. A screen holding its own copy is a second
        statement of it, and the copy is the one that goes stale — which has
        happened here before, with a bound that predated the `min`."""
        from core.features.sets import PIT_RULE
        for path in ("/featureset/nj_home_core/plan/1",
                     "/featureset/nj_home_core/assemble"):
            body = _prose(published, path)
            assert PIT_RULE.replace("<=", "&lt;=") in body, path
