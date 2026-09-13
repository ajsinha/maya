"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two renderings of unchanged state are the same document.

The compiler's docstring promised it and the compiler broke it, in a way that
is invisible from inside a single compile. Compiling appends a
`document_compiled` node against the **model**, so the next compile found it
in the model's evidence and cited it — a longer citation list, a different
digest, and a new document row, every time somebody pressed the button.

Three things rested on the broken promise:

- *Has this changed since the board saw it?* answered yes forever.
- The bibliography grew by one per compile: provenance documenting the act of
  documenting.
- Review comments are keyed on the document, and a recompile that changed
  nothing authored a second identical document — leaving the reviewer's
  unresolved question against one nobody is looking at.

`document_commented` had the same shape and the same subject, so a single
review comment also moved the digest of every later compile.
"""
from __future__ import annotations

from core.docs.context import NOT_CITED


class TestWhatADocumentDoesNotCite:
    def test_the_act_of_compiling_is_not_cited(self):
        assert "document_compiled" in NOT_CITED

    def test_commenting_on_a_document_is_not_cited(self):
        assert "document_commented" in NOT_CITED

    def test_resolving_and_withdrawing_are_not_cited(self):
        assert {"document_comment_resolved",
                "document_comment_withdrawn"} <= set(NOT_CITED)

    def test_governance_acts_are_still_cited(self):
        """The exclusion is narrow on purpose. A document that stopped citing
        approvals or attestations would be worse than one citing itself."""
        for kind in ("model_registered", "model_approved", "model_attested",
                     "version_approved", "finding_raised"):
            assert kind not in NOT_CITED

    def test_every_excluded_kind_is_about_a_document(self):
        """A guard on the rule rather than on the list: anything added here
        must be a fact about a document, not about a model."""
        assert all(kind.startswith("document_") for kind in NOT_CITED)


class TestTheCompilerReturnsTheSameDocument:
    def test_an_identical_rendering_is_not_authored_twice(self):
        """Asserted on the source, because the behaviour needs a full estate
        to exercise and the QA scenarios do that (QA-PLT-123 … 125). What
        matters here is that the lookup is still in place."""
        import inspect

        from core.docs.compiler import DocumentCompiler
        source = inspect.getsource(DocumentCompiler.compile)
        assert "one(digest=" in source, (
            "the compiler no longer looks for an existing document with the "
            "same digest, so every recompile authors a second copy and "
            "orphans the comments on the first")
        assert "return existing" in source
