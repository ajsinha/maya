"""
MAYA — tests for attached documents.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What these tests are really asserting is that a document register is a control
rather than a filing cabinet: it knows which version a document describes, it
will not let the author approve their own paper, and it will not quietly serve
back something other than what was approved.
"""
from __future__ import annotations

import pytest

from core.attachments import AttachmentError, DocumentStore

URN = "maya://model/credit.pd.smallbiz"
MDD = b"# Model Development Document\n\nThe scorecard is a logistic regression.\n"


# --------------------------------------------------------------------- store
class TestTheStoreIsContentAddressed:
    def test_the_same_bytes_are_stored_once(self, tmp_path):
        store = DocumentStore(tmp_path)
        first, size = store.put(MDD)
        second, again = store.put(MDD)
        assert first == second and size == again == len(MDD)
        assert len(list(tmp_path.rglob("*"))) == 2      # one fan-out dir, one object

    def test_a_changed_byte_is_a_different_document(self, tmp_path):
        store = DocumentStore(tmp_path)
        assert store.put(MDD)[0] != store.put(MDD + b" ")[0]

    def test_reading_back_verifies_the_digest(self, tmp_path):
        """What was reviewed is what is served — checked, not assumed."""
        store = DocumentStore(tmp_path)
        digest, _ = store.put(MDD)
        assert store.get(digest) == MDD
        store._path(digest).write_bytes(b"something else entirely")
        with pytest.raises(AttachmentError) as exc:
            store.get(digest)
        assert exc.value.code == "document_corrupt"

    def test_an_empty_document_is_refused(self, tmp_path):
        with pytest.raises(AttachmentError) as exc:
            DocumentStore(tmp_path).put(b"")
        assert exc.value.code == "empty_document"

    def test_a_path_that_is_not_a_digest_is_refused(self, tmp_path):
        """Otherwise the digest is a filesystem path somebody supplies."""
        with pytest.raises(AttachmentError) as exc:
            DocumentStore(tmp_path).get("sha256:../../etc/passwd")
        assert exc.value.code == "bad_digest"


# -------------------------------------------------------------------- attach
class TestADocumentIsFiledAgainstAVersion:
    def test_it_lands_on_the_current_version_by_default(self, attachments,
                                                        approved_version):
        row = attachments.attach(URN, "model_development_document",
                                 "SB PD MDD", "mdd.md", MDD, "text/markdown",
                                 actor="person/j.okafor")
        assert row["model_version_id"] == approved_version["id"]
        assert row["state"] == "attached"

    def test_model_level_has_to_be_asked_for(self, attachments, approved_version):
        row = attachments.attach(URN, "board_paper", "2026 board paper", "b.md",
                                 MDD, "text/markdown", model_level=True,
                                 actor="person/j.okafor")
        assert row["model_version_id"] is None

    def test_a_model_with_no_versions_says_so(self, attachments, a_model):
        with pytest.raises(AttachmentError) as exc:
            attachments.attach(URN, "correspondence", "Note", "n.md", MDD,
                               "text/markdown")
        assert exc.value.code == "no_version_to_attach_to"
        assert "model_level" in exc.value.remediation

    def test_a_version_that_does_not_exist_is_refused(self, attachments,
                                                      approved_version):
        with pytest.raises(AttachmentError) as exc:
            attachments.attach(URN, "validation_report", "VR", "v.md", MDD,
                               "text/markdown", semver="9.9.9")
        assert exc.value.code == "no_version_for_document"

    def test_a_kind_nobody_defined_is_refused(self, attachments, approved_version):
        with pytest.raises(AttachmentError) as exc:
            attachments.attach(URN, "vibes", "T", "t.md", MDD, "text/markdown")
        assert exc.value.code == "unknown_kind"

    def test_a_filename_is_not_a_title(self, attachments, approved_version):
        with pytest.raises(AttachmentError) as exc:
            attachments.attach(URN, "other", "   ", "t.md", MDD, "text/markdown")
        assert exc.value.code == "title_required"

    def test_the_same_file_twice_on_one_version_is_refused(self, attachments,
                                                           approved_version):
        attachments.attach(URN, "validation_report", "VR", "v.md", MDD,
                           "text/markdown")
        with pytest.raises(AttachmentError) as exc:
            attachments.attach(URN, "validation_report", "VR again", "v.md", MDD,
                               "text/markdown")
        assert exc.value.code == "already_attached"

    def test_attaching_is_witnessed(self, attachments, approved_version, repos):
        attachments.attach(URN, "validation_report", "VR", "v.md", MDD,
                           "text/markdown", actor="person/a.mensah")
        kinds = [e["kind"] for e in repos["evidence"].many()]
        assert "document_attached" in kinds


# -------------------------------------------------------------------- review
class TestReviewIsSegregated:
    @pytest.fixture
    def filed(self, attachments, approved_version):
        return attachments.attach(URN, "validation_report", "SB PD validation",
                                  "vr.md", MDD, "text/markdown",
                                  actor="person/j.okafor")

    def test_the_author_cannot_accept_their_own_document(self, attachments, filed):
        with pytest.raises(AttachmentError) as exc:
            attachments.review(filed["id"], True, "person/j.okafor")
        assert exc.value.code == "self_review"

    def test_somebody_else_can(self, attachments, filed):
        row = attachments.review(filed["id"], True, "person/a.mensah", "reads well")
        assert row["state"] == "accepted" and row["reviewed_by"] == "person/a.mensah"

    def test_rejection_needs_a_reason(self, attachments, filed):
        with pytest.raises(AttachmentError) as exc:
            attachments.review(filed["id"], False, "person/a.mensah")
        assert exc.value.code == "reason_required"

    def test_a_rejected_document_stays_in_the_register(self, attachments, filed):
        """The set of documents somebody could not file is the interesting one."""
        attachments.review(filed["id"], False, "person/a.mensah", "no back-testing")
        assert attachments.require(filed["id"])["state"] == "rejected"
        assert filed["id"] in [r["id"] for r in
                               attachments.history(filed["model_id"])]

    def test_reviewing_twice_is_refused(self, attachments, filed):
        attachments.review(filed["id"], True, "person/a.mensah")
        with pytest.raises(AttachmentError) as exc:
            attachments.review(filed["id"], True, "person/a.mensah")
        assert exc.value.code == "already_reviewed"


# --------------------------------------------------------------- supersession
class TestReplacingADocumentIsDeclared:
    def test_the_prior_document_is_marked_and_linked(self, attachments,
                                                     approved_version):
        first = attachments.attach(URN, "model_development_document", "MDD v1",
                                   "m.md", MDD, "text/markdown")
        second = attachments.attach(URN, "model_development_document", "MDD v2",
                                    "m.md", MDD + b"\nRevised.\n", "text/markdown",
                                    supersedes=first["id"])
        assert attachments.require(first["id"])["state"] == "superseded"
        assert attachments.require(first["id"])["superseded_by"] == second["id"]
        assert second["supersedes"] == first["id"]

    def test_a_superseded_document_leaves_the_current_set(self, attachments,
                                                          approved_version):
        first = attachments.attach(URN, "vendor_documentation", "Manual", "m.md",
                                   MDD, "text/markdown")
        attachments.attach(URN, "vendor_documentation", "Manual rev B", "m.md",
                           MDD + b"B", "text/markdown", supersedes=first["id"])
        current = [r["id"] for r in attachments.for_model(first["model_id"])]
        assert first["id"] not in current

    def test_superseding_it_twice_is_refused(self, attachments, approved_version):
        first = attachments.attach(URN, "other", "A", "a.md", MDD, "text/markdown")
        attachments.attach(URN, "other", "B", "b.md", MDD + b"B", "text/markdown",
                           supersedes=first["id"])
        with pytest.raises(AttachmentError) as exc:
            attachments.attach(URN, "other", "C", "c.md", MDD + b"C",
                               "text/markdown", supersedes=first["id"])
        assert exc.value.code == "already_superseded"


# ----------------------------------------------------------------- reading it
class TestWhatMachinesCanRead:
    def test_text_comes_back_as_text(self, attachments, approved_version):
        row = attachments.attach(URN, "model_development_document", "MDD", "m.md",
                                 MDD, "text/markdown")
        assert attachments.text(row["id"]).startswith("# Model Development")

    def test_a_format_we_cannot_read_says_so_rather_than_guessing(
            self, attachments, approved_version):
        """Later AI review needs to know what has actually been read."""
        row = attachments.attach(URN, "board_paper", "Board pack", "b.pdf",
                                 b"%PDF-1.4 not really", "application/pdf")
        assert row["text_indexed"] == 0
        assert attachments.text(row["id"]) is None

    def test_the_bytes_served_are_the_bytes_filed(self, attachments,
                                                  approved_version):
        row = attachments.attach(URN, "independent_review", "IVU", "i.md", MDD,
                                 "text/markdown")
        assert attachments.content(row["id"]) == MDD


# --------------------------------------------------------------------- status
class TestTheRegisterAnswersWhatIsOnFile:
    def test_an_empty_register_says_so_plainly(self, attachments, a_model):
        assert attachments.status(a_model["id"])["detail"] == "no documents attached"

    def test_it_counts_what_is_accepted_and_what_is_waiting(self, attachments,
                                                            approved_version):
        model_id = approved_version["model_id"]
        first = attachments.attach(URN, "validation_report", "VR", "v.md", MDD,
                                   "text/markdown", actor="person/j.okafor")
        attachments.attach(URN, "model_development_document", "MDD", "m.md",
                           MDD + b"x", "text/markdown", actor="person/j.okafor")
        attachments.review(first["id"], True, "person/a.mensah")
        status = attachments.status(model_id)
        assert status["attached"] == 2
        assert status["accepted"] == 1 and status["awaiting_review"] == 1
        assert set(status["kinds_present"]) == {"validation_report",
                                                "model_development_document"}

    def test_rejections_are_counted_even_though_they_are_not_current(
            self, attachments, approved_version):
        row = attachments.attach(URN, "validation_report", "VR", "v.md", MDD,
                                 "text/markdown", actor="person/j.okafor")
        attachments.review(row["id"], False, "person/a.mensah", "insufficient")
        assert attachments.status(approved_version["model_id"])["rejected"] == 1
