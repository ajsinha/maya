"""Finding the sentence in the document nobody remembered filing.

`attachment.text_indexed` has been on the row since attachments were written. It
was set at upload, read by one status count, and nothing ever searched anything.
A register that can serve a document and cannot find one is a filing cabinet with
a URL.
"""
from __future__ import annotations

import pytest

from core.docs.common import DocumentError
from core.docs.search import MAX_LIMIT, QUOTE, DocumentSearch, terms
from tests.conftest import URN

REPORT = """Validation report for the small business PD scorecard.

The discrimination measured on the holdout sample gives a Gini of 0.61.
Calibration is within tolerance across every score band except the lowest.
The model has never been tested through a rate shock above four hundred basis
points, and that limitation is recorded against version 3.2.1.
"""

MINUTE = """Committee minute.

The committee accepted the validation and noted the rate shock limitation.
"""


@pytest.fixture
def searching(attachments, registry):
    return DocumentSearch(attachments, registry)


@pytest.fixture
def filed(attachments, a_model, approved_version):
    attachments.attach(URN, "validation_report", "Validation report",
                       "report.txt", REPORT.encode(), actor="a.mehta",
                       media_type="text/plain")
    attachments.attach(URN, "committee_minute", "Committee minute",
                       "minute.txt", MINUTE.encode(), actor="a.mehta",
                       media_type="text/plain")
    return URN


class TestTheQuery:
    def test_common_words_are_dropped(self):
        assert terms("the model and the risk") == ["model", "risk"]

    def test_a_query_of_only_common_words_is_no_query(self, searching):
        with pytest.raises(DocumentError) as caught:
            searching.search("the and of")
        assert caught.value.code == "empty_query"
        assert "counts as none" in caught.value.remediation

    def test_an_absurd_page_size_is_refused(self, searching):
        with pytest.raises(DocumentError) as caught:
            searching.search("gini", limit=MAX_LIMIT + 1)
        assert caught.value.code == "limit_out_of_range"


class TestFindingThings:
    def test_a_term_in_one_document_finds_it(self, searching, filed):
        out = searching.search("gini")
        assert out["matches"] == 1
        assert out["results"][0]["kind"] == "validation_report"

    def test_the_matching_line_is_quoted(self, searching, filed):
        """*Show me where you wrote that* is the question."""
        out = searching.search("gini")
        hit = out["results"][0]
        assert "0.61" in hit["quote"] and hit["line"]
        assert len(hit["quote"]) <= QUOTE

    def test_a_term_in_two_documents_finds_both(self, searching, filed):
        out = searching.search("limitation")
        assert out["matches"] == 2

    def test_more_of_the_query_beats_more_of_one_term(self, searching, filed):
        """A document mentioning every term once is a better answer to a
        two-word question than one mentioning the first forty times."""
        out = searching.search("rate shock committee")
        assert out["results"][0]["kind"] == "committee_minute"
        assert out["results"][0]["terms_found"] == ["rate", "shock",
                                                    "committee"]

    def test_missing_terms_are_named(self, searching, filed):
        out = searching.search("gini elephant")
        assert out["results"][0]["terms_missing"] == ["elephant"]

    def test_nothing_matching_says_how_much_was_searched(self, searching,
                                                         filed):
        out = searching.search("elephant")
        assert out["matches"] == 0 and out["documents_searched"] == 2
        assert "out of 2 document(s) searched" in out["detail"]

    def test_a_kind_filter_narrows_it(self, searching, filed):
        out = searching.search("limitation", kind="committee_minute")
        assert out["matches"] == 1

    def test_a_urn_filter_narrows_it(self, searching, filed):
        assert searching.search("gini", urn=URN)["matches"] == 1
        assert searching.search("gini", urn="maya://model/other")["matches"] == 0


class TestWhatCannotBeRead:
    def test_an_unread_document_is_reported_not_skipped(self, searching,
                                                        attachments, a_model,
                                                        approved_version):
        """Invisible is exactly how it looks to somebody who searched and found
        nothing."""
        attachments.attach(URN, "validation_report", "Scanned report",
                           "report.pdf", b"%PDF-1.4 not text",
                           actor="a.mehta", media_type="application/pdf")
        out = searching.search("gini")
        assert len(out["could_not_be_read"]) == 1
        assert "invisible to a search" in out["detail"]

    def test_coverage_is_the_figure_to_read_first(self, searching, attachments,
                                                  a_model, approved_version):
        """A search over a corpus that is forty percent unextracted is a search
        whose empty answers mean nothing."""
        attachments.attach(URN, "validation_report", "Report", "r.txt",
                           REPORT.encode(), actor="a.mehta",
                           media_type="text/plain")
        attachments.attach(URN, "vendor_documentation", "Scan", "s.pdf",
                           b"%PDF", actor="a.mehta",
                           media_type="application/pdf")
        out = searching.coverage()
        assert out["documents"] == 2 and out["unread"] == 1
        assert out["coverage"] == 0.5
        assert "means nothing" in out["detail"]

    def test_an_empty_corpus_says_so(self, searching, a_model):
        assert "no document has been filed" in searching.coverage()["detail"]


class TestScope:
    def test_an_unscoped_search_says_it_is_unscoped(self, searching, filed):
        """A search that ignored who is asking would be a way to read models a
        reader cannot see, one query at a time."""
        assert searching.search("gini")["scoped"] is False

    def test_a_scoped_search_asks_the_authoriser(self, attachments, registry,
                                                 filed):
        class Nothing:
            def visible(self, principal, models):
                return []

        scoped = DocumentSearch(attachments, registry, authz=Nothing())
        out = scoped.search("gini", principal={"username": "someone"})
        assert out["scoped"] is True and out["matches"] == 0


class TestTheSemanticHalfIsNamed:
    def test_it_says_why_not_and_what_it_would_take(self):
        """An absence somebody has to discover is indistinguishable from an
        oversight."""
        out = DocumentSearch.semantic()
        assert out["available"] is False
        assert "would have to be registered under the very rules" in (
            out["why_not"])
        assert "canary" in out["what_it_would_take"]

    def test_it_travels_with_the_coverage_answer(self, searching, a_model):
        assert searching.coverage()["semantic_search"]["available"] is False


class TestOverHttp:
    def test_a_search_is_served(self, registered, people):
        r = registered.get("/api/v1/document-search", auth=people["a.mehta"],
                           params={"q": "model"})
        assert r.status_code == 200, r.text
        assert "terms" in r.json()

    def test_an_empty_query_is_refused_by_name(self, registered, people):
        r = registered.get("/api/v1/document-search", auth=people["a.mehta"],
                           params={"q": "the and of"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "empty_query"

    def test_coverage_is_served_with_the_semantic_absence_named(
            self, registered, people):
        r = registered.get("/api/v1/document-search/coverage",
                           auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        assert r.json()["semantic_search"]["available"] is False

    def test_the_screen_says_what_an_empty_answer_means(self, registered,
                                                        people):
        registered.post("/login", data={"username": "admin",
                                        "password": "maya-admin-dev",
                                        "next": "/documents/search"})
        body = registered.get("/documents/search").text
        assert "filing cabinet with a URL" in body
        assert "cannot tell a miss from an absence" in body
