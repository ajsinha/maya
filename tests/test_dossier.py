"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Documentation as a graph, and the moment that had no document.

Documentation does not arrive all at once about one thing. It arrives at
different moments about different objects — a methodology paper about the model,
a convergence study about one parameter set, a data dictionary about one
featureset version — and while everything had to be filed against a model or a
version, two of those five cases were unfilable.

The case that makes it obvious is the calibrated model. Hull–White is solved
every morning: two hundred and fifty parameter sets a year, each a governed act
with a warrant behind it and a reviewer's signature on it, and none of them with
a record anybody could read. The note explaining the one morning it went wrong
lived in an email.

Two properties carry the design, and both are tested here rather than argued.

**It follows the pins, not the names.** A training record links `sb_core@v1`,
not `sb_core`. A document filed against the *set* would describe something that
has since moved — finding C-2 in documentation's clothing.

**Gaps are named.** A featureset with no data dictionary is a gap in the
dossier, not an absence a reader has to notice. A page that silently omits what
it could not find reads as complete.
"""
from __future__ import annotations

import pytest

from core.docs.subjects import (FEATURESET_VERSION, MODEL, MODEL_VERSION,
                                PARAMETER_SET, SUBJECTS, known)

URN = "maya://model/credit.pd.smallbiz"


def find(node, subject_type, label=None):
    """Depth-first search of the dossier for one node."""
    stack = [node]
    while stack:
        current = stack.pop()
        if current["subject_type"] == subject_type and \
                (label is None or current["label"] == label):
            return current
        stack.extend(current.get("children") or [])
    return None


class TestWhatADocumentCanBeAbout:
    def test_the_five_moments_all_have_a_subject(self):
        for subject in (MODEL, MODEL_VERSION, PARAMETER_SET,
                        FEATURESET_VERSION, "validation"):
            assert known(subject)

    def test_a_featureset_is_not_a_subject_but_a_version_of_one_is(self):
        """The pin. A document about the set describes something that has since
        moved, which is exactly the failure the register exists to prevent."""
        assert known(FEATURESET_VERSION)
        assert not known("featureset")

    def test_the_vocabulary_is_published_with_which_subjects_are_pinned(self,
                                                                        client):
        body = client.get("/api/v1/document-subjects").json()
        by = {s["subject"]: s for s in body["subjects"]}
        assert by[FEATURESET_VERSION]["pinned"] is True
        assert by[PARAMETER_SET]["pinned"] is True
        assert all(s["means"] for s in body["subjects"])


class TestAnAttachmentIsFiledAgainstWhatItIsAbout:
    def test_it_defaults_to_the_version_so_an_old_caller_is_unchanged(
            self, client, registered):
        r = client.post("/api/v1/attachments", files={
            "file": ("note.md", b"# a note", "text/markdown")}, data={
            "urn": URN, "kind": "model_development_document",
            "title": "A note"})
        assert r.status_code == 201, r.text
        assert r.json()["subject_type"] == MODEL_VERSION

    def test_a_subject_the_platform_cannot_resolve_is_refused(self, client,
                                                              registered):
        r = client.post("/api/v1/attachments", files={
            "file": ("note.md", b"# a note", "text/markdown")}, data={
            "urn": URN, "kind": "model_development_document",
            "title": "A note", "subject_type": "vibes"})
        assert r.status_code == 422
        assert r.json()["error"] == "unknown_subject"


class TestTheTrainingRecord:
    """The document a daily recalibration never had."""

    @pytest.fixture
    def fitted(self, client, registered, people):
        """A parameter set delivered against a warrant, the ordinary way.

        The featureset is built here rather than assumed: a training record's
        whole point is naming the version the numbers came from, so a fixture
        that skipped it would test the record without the thing it records.
        """
        dev, owner = people["d.raman"], people["j.okafor"]
        client.post("/api/v1/features", auth=dev, json={
            "name": "dscr", "entity": "borrower_id", "dtype": "numeric",
            "description": "Debt service coverage", "owner": "person/j.okafor"})
        client.post("/api/v1/featuresets", auth=dev, json={
            "name": "sb_core", "entity": "borrower_id",
            "slots": {"dscr": "numeric"}})
        # A featureset version pins a materialised view version, so the values
        # have to exist before the schema can be filled — which is the whole
        # point of the pin and not a fixture inconvenience.
        client.post("/api/v1/feature-views", auth=dev, json={
            "name": "sb_financials", "entity": "borrower_id",
            "owner": "person/j.okafor", "features": ["dscr"]})
        client.post("/api/v1/feature-views/sb_financials/materialise", auth=dev,
                    json={"rows": [
                        {"entity_id": "B0001", "event_ts": 1711843200,
                         "ingest_ts": 1716163200, "dscr": 1.42}]})
        filled = client.post("/api/v1/featuresets/sb_core/versions", auth=dev,
                             json={"bindings": {"dscr": "dscr"}})
        assert filled.status_code == 201, filled.text
        grant = client.post("/api/v1/warrants", auth=owner, json={
            "urn": URN, "principal": "svc/model-lab",
            "declared_use": "model_development", "environment": "lab"}).json()
        recorded = client.post("/api/v1/parameters", auth=dev, json={
            "urn": URN, "semver": "3.2.1", "name": "ols_v1",
            "kind": "coefficients", "provenance": "fitted",
            "values": {"intercept": -2.1, "dscr": -0.84},
            "featureset": "sb_core", "featureset_version": 1,
            "warrant_id": grant.get("id") or grant.get("grant_id"),
            "window": {"from": 1546300800, "to": 1735603200},
            "as_of": 1736899200,
            "diagnostics": {"r_squared": 0.31, "condition_number": 34.9,
                            "n": 8420}})
        assert recorded.status_code == 201, recorded.text
        return recorded.json()

    def test_it_compiles_from_the_register_without_anybody_writing_it(
            self, client, fitted):
        record = client.get(
            f"/api/v1/training-records/{fitted['id']}/preview").json()
        assert record["kind"] == "training_record"
        assert record["subject_type"] == PARAMETER_SET
        assert record["subject_id"] == fitted["id"]
        assert record["coverage"]["filled"] >= 4

    def test_it_names_the_featureset_version_rather_than_the_featureset(
            self, client, fitted):
        """The pin, in the document that most needs it: *what was this trained
        on* must answer with the schema that was in force."""
        record = client.get(
            f"/api/v1/training-records/{fitted['id']}/preview").json()
        data = next(s for s in record["sections"] if s["key"] == "data")
        assert "sb_core @ v1" in data["body"]
        assert "has since moved" in data["body"]

    def test_the_diagnostics_are_in_it_because_they_are_what_a_reviewer_reads(
            self, client, fitted):
        record = client.get(
            f"/api/v1/training-records/{fitted['id']}/preview").json()
        body = next(s for s in record["sections"]
                    if s["key"] == "diagnostics")["body"]
        assert "condition_number" in body and "34.9" in body

    def test_a_fit_with_no_warrant_is_a_gap_rather_than_a_blank(self, client,
                                                                registered,
                                                                people):
        """A fitted set with no warrant has no answer to *which data produced
        these numbers*, and the record says so rather than omitting the
        section."""
        declared = client.post("/api/v1/parameters", auth=people["d.raman"],
                               json={
            "urn": URN, "semver": "3.2.1", "name": "by_hand",
            "kind": "coefficients", "provenance": "declared",
            "values": {"intercept": 0.0}})
        assert declared.status_code == 201, declared.text
        record = client.get(
            f"/api/v1/training-records/{declared.json()['id']}/preview").json()
        authority = next(s for s in record["sections"]
                         if s["key"] == "authority")
        assert "Declared rather than fitted" in authority["body"]

    def test_compiling_it_records_that_it_happened(self, client, fitted):
        r = client.post(f"/api/v1/training-records/{fitted['id']}")
        assert r.status_code == 201, r.text
        assert r.json()["subject_id"] == fitted["id"]

    def test_previewing_does_not_author_one(self, client, fitted):
        """An export pack and a dossier want the content without performing the
        act — the same split the other documents have."""
        client.get(f"/api/v1/training-records/{fitted['id']}/preview")
        dossier = client.get("/api/v1/dossiers/credit.pd.smallbiz").json()
        node = find(dossier["root"], PARAMETER_SET)
        assert node is not None
        assert not node["compiled"], "a preview must not have authored anything"


class TestTheDossier:
    def test_it_is_a_graph_rooted_at_the_model(self, client, registered):
        dossier = client.get("/api/v1/dossiers/credit.pd.smallbiz").json()
        assert dossier["root"]["subject_type"] == MODEL
        assert find(dossier["root"], MODEL_VERSION) is not None

    def test_a_parameter_set_hangs_under_the_version_that_produced_it(
            self, client, registered, people):
        client.post("/api/v1/parameters", auth=people["d.raman"], json={
            "urn": URN, "semver": "3.2.1", "name": "by_hand",
            "kind": "coefficients", "provenance": "declared",
            "values": {"intercept": 0.0}})
        dossier = client.get("/api/v1/dossiers/credit.pd.smallbiz").json()
        version = find(dossier["root"], MODEL_VERSION)
        assert any(c["subject_type"] == PARAMETER_SET
                   for c in version["children"])

    def test_it_counts_what_it_found(self, client, registered):
        dossier = client.get("/api/v1/dossiers/credit.pd.smallbiz").json()
        assert dossier["counts"]["nodes"] >= 2
        assert "document(s) across" in dossier["detail"]

    def test_a_node_with_nothing_filed_is_a_gap_rather_than_a_blank(
            self, client, registered):
        """A reader cannot tell a thin model from a thin page unless the page
        says which it is."""
        dossier = client.get("/api/v1/dossiers/credit.pd.smallbiz").json()
        assert dossier["gaps"], "a fresh model has documentation gaps by definition"
        assert all(g["why"] for g in dossier["gaps"])
        assert any("expected" in g["why"] for g in dossier["gaps"])

    def test_a_document_filed_about_a_thing_is_found_from_that_thing(
            self, client, registered, people):
        recorded = client.post("/api/v1/parameters", auth=people["d.raman"],
                               json={
            "urn": URN, "semver": "3.2.1", "name": "by_hand",
            "kind": "coefficients", "provenance": "declared",
            "values": {"intercept": 0.0}}).json()
        filed = client.post("/api/v1/attachments", files={
            "file": ("conv.md", b"# convergence", "text/markdown")}, data={
            "urn": URN, "kind": "evidence_of_control",
            "title": "Convergence study",
            "subject_type": PARAMETER_SET, "subject_id": recorded["id"]})
        assert filed.status_code == 201, filed.text

        dossier = client.get("/api/v1/dossiers/credit.pd.smallbiz").json()
        node = find(dossier["root"], PARAMETER_SET)
        assert [a["title"] for a in node["attached"]] == ["Convergence study"]

    def test_an_unknown_model_is_a_404(self, client):
        assert client.get("/api/v1/dossiers/nothing.here").status_code == 404


class TestThePages:
    @pytest.fixture
    def page(self, client, registered):
        from tests.api_helpers import login
        login(client)
        return client

    def test_the_dossier_page_renders_the_graph(self, page):
        rendered = page.get("/dossier/credit.pd.smallbiz")
        assert rendered.status_code == 200
        assert "model version" in rendered.text or "model_version" in rendered.text
        assert "has since moved" in rendered.text, \
            "the page must say why it follows the version and not the set"

    def test_the_gaps_are_shown_rather_than_left_blank(self, page):
        assert "Gaps" in page.get("/dossier/credit.pd.smallbiz").text

    def test_the_model_page_shows_the_model_as_its_type(self, page):
        """`f : P ⊗ X → D(Y)` is the definition the platform is organised
        around, and a reader used to assemble it from four cards."""
        rendered = page.get("/model/credit.pd.smallbiz").text
        assert "THE MODEL, AS ITS TYPE" in rendered
        assert "D(Y)" in rendered
        assert "derived" in rendered, \
            "the class must be shown beside the two facts it comes from"

    def test_an_unknown_model_dossier_is_a_404_page(self, page):
        assert page.get("/dossier/nothing.here").status_code == 404
