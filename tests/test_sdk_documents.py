"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Documents, attachments and export packs, through the SDK, against the real app.

The transport is a seam, so every call below travels the whole stack — routes,
authorisation, the document register, the compiler, the evidence chain — and
comes back. A mock of the thing under test proves only that the mock agrees with
itself, and an SDK is precisely the code whose value is that it agrees with a
*server*.

Three properties are worth more here than method coverage.

**A refusal is raised.** Filing a document is the act that most often goes
wrong — the wrong kind, a subject that cannot be resolved, a reviewer who is the
author — and a caller who checks a returned verdict and forgets has filed
evidence that was never accepted while their script printed nothing.

**The vocabulary is asked for, never carried.** Which kinds exist, and what a
document may be filed against, are published by the platform. A copy in the SDK
would be a second list, and the second list is the one that quietly permits more.

**A gap is a fact.** The pack records what it could not reach. A test that only
checked the members present would pass on a pack that silently dropped half of
them.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))

from maya_sdk import Maya, NotFound, NotPermitted, Refused  # noqa: E402

URN = "maya://model/credit.pd.smallbiz"
NAME = "credit.pd.smallbiz"
SDK = Path(__file__).resolve().parents[1] / "sdk" / "python" / "maya_sdk"

MDD = b"# SB PD -- Model Development Document\n\nLogistic regression.\n"


class _TestClientTransport:
    """Speaks the transport interface, drives the app in-process.

    The same seam `test_sdk.py` uses. Repeated rather than imported because a
    test that reaches into another test module for its harness breaks when that
    module is split, and the class is six lines.
    """

    def __init__(self, client, auth=None):
        self.client, self.auth = client, auth

    def request(self, method, path, *, json=None, content=None, params=None,
                headers=None):
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return self.client.request(method, path, json=json, content=content,
                                   params=clean or None, headers=headers,
                                   auth=self.auth or self.client.auth)


@pytest.fixture
def maya(client, registered):
    """The SDK against a model that has been through the whole governed path."""
    return Maya(transport=_TestClientTransport(client))


@pytest.fixture
def as_person(client, registered):
    def _as(credentials):
        return Maya(transport=_TestClientTransport(client, auth=credentials))
    return _as


@pytest.fixture
def filed(as_person, people):
    """One document on file, by the owner, awaiting somebody else's review."""
    return as_person(people["j.okafor"]).attachments.attach(
        URN, content=MDD, filename="mdd.md",
        kind="model_development_document", title="SB PD MDD")


@pytest.fixture
def parameter_set(maya):
    """One point of P, declared rather than fitted.

    Declared on purpose: the record compiled from it has to say *"declared
    rather than fitted"* rather than leave the authority section blank, and that
    is the behaviour worth reaching from the SDK.
    """
    return maya.parameters.record(
        urn=URN, semver="3.2.1", name="by_hand", kind="coefficients",
        provenance="declared", values={"intercept": 0.0}, warrant_id=None)


def _literals(path: Path) -> set:
    """Every string literal in a module that is not a docstring.

    A docstring naming a subject is documentation and is the point; a *literal*
    naming one is a copy of the platform's vocabulary, and a copy can disagree
    with the original. Walked rather than grepped so that a parameter called
    `parameter_set_id` — which names a path segment rather than enumerating a
    vocabulary — is not mistaken for one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    documentation = {id(node.value) for node in ast.walk(tree)
                     if isinstance(node, ast.Expr)
                     and isinstance(node.value, ast.Constant)}
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in documentation}


class TestTheVocabularyIsAskedForRatherThanCarried:
    """A list copied into a client goes stale silently, and it goes stale in the
    permissive direction, because that is where nobody files a bug."""

    def test_the_attachment_kinds_come_back_with_what_they_mean(self, maya):
        kinds = maya.attachments.kinds()["kinds"]
        by = {k["kind"]: k["means"] for k in kinds}
        assert by["validation_report"] and by["board_paper"]

    def test_the_document_kinds_come_back_with_what_each_is_for(self, maya):
        kinds = maya.documents.kinds()["kinds"]
        by = {k["kind"]: k for k in kinds}
        assert by["model_card"]["purpose"] and by["annex_iv"]["title"]

    def test_the_subjects_say_which_of_them_are_pinned(self, maya):
        by = {s["subject"]: s for s in maya.attachments.subjects()["subjects"]}
        assert by["featureset_version"]["pinned"] is True
        assert by["parameter_set"]["pinned"] is True
        assert all(s["means"] for s in by.values())

    def test_both_classes_publish_the_same_vocabulary(self, maya):
        assert maya.documents.subjects() == maya.attachments.subjects()

    def test_the_sdk_holds_no_copy_of_the_list(self):
        """Asserted on the source, because the temptation to 'help' by carrying
        the vocabulary is exactly what would create the second list."""
        literals = _literals(SDK / "documents.py")
        carried = literals & {"model", "model_version", "parameter_set",
                              "featureset_version", "feature", "validation",
                              "model_development_document", "validation_report",
                              "independent_review", "committee_minute",
                              "board_paper", "model_card", "annex_iv"}
        assert not carried, (
            f"documents.py carries {sorted(carried)} as literals; the platform "
            "publishes the vocabulary and a copy here can disagree with it")


class TestFilingADocument:
    def test_a_document_is_filed_and_read_back(self, filed, maya):
        assert filed["state"] == "attached"
        assert filed["digest"].startswith("sha256:")
        assert maya.attachments.get(filed["id"])["title"] == "SB PD MDD"

    def test_a_file_on_disk_is_filed_by_path(self, as_person, people, tmp_path):
        paper = tmp_path / "board-paper.md"
        paper.write_bytes(b"# What was put to the board\n")
        out = as_person(people["j.okafor"]).attachments.attach(
            URN, paper, kind="board_paper", title="March board paper")
        assert out["filename"] == "board-paper.md"

    def test_the_media_type_is_guessed_so_the_text_can_be_indexed(self, filed):
        """A format whose text can be read out is indexed for search and
        citation; one that cannot is stored, served, and recorded as unread
        rather than assumed to have been read."""
        assert filed["media_type"] == "text/markdown"
        assert filed["text_indexed"] == 1

    def test_a_format_that_cannot_be_read_says_so_rather_than_pretending(
            self, as_person, people):
        out = as_person(people["j.okafor"]).attachments.attach(
            URN, content=b"%PDF-1.4 not really", filename="vendor.pdf",
            kind="vendor_documentation", title="Vendor manual")
        assert out["media_type"] == "application/pdf"
        assert out["text_indexed"] == 0

    def test_the_register_reports_how_thin_it_is(self, maya, filed):
        register = maya.attachments.list(URN)
        assert register["attached"] == 1 and register["awaiting_review"] == 1
        assert register["attachments"][0]["title"] == "SB PD MDD"

    def test_the_bytes_come_back_exactly_as_filed(self, maya, filed, tmp_path):
        back = maya.attachments.content(filed["id"], tmp_path / "back.md")
        assert back.read_bytes() == MDD

    def test_neither_a_path_nor_bytes_is_a_caller_error_not_a_request(self, maya):
        with pytest.raises(ValueError, match="either a path or content"):
            maya.attachments.attach(URN, kind="other", title="T")

    def test_a_filename_that_would_forge_the_encoding_is_refused(self, maya):
        with pytest.raises(ValueError, match="quote or a newline"):
            maya.attachments.attach(URN, content=b"x", filename='a";b.md',
                                    kind="other", title="T")


class TestAReviewIsSomebodyElse:
    def test_a_second_person_accepts_it(self, as_person, people, filed):
        out = as_person(people["a.mehta"]).attachments.review(
            filed["id"], accept=True, note="complete")
        assert out["state"] == "accepted" and out["reviewed_by"]

    def test_the_author_cannot_accept_their_own(self, maya):
        """Raised rather than returned. A caller who filed their own validation
        report and did not check a verdict would have a register that says
        accepted and a control that never operated."""
        mine = maya.attachments.attach(URN, content=b"# mine", filename="m.md",
                                       kind="evidence_of_control", title="Mine")
        with pytest.raises(NotPermitted) as exc:
            maya.attachments.review(mine["id"], accept=True)
        assert exc.value.code == "self_review"
        assert exc.value.remediation, "a refusal without a remediation is a wall"

    def test_a_rejection_needs_a_reason(self, as_person, people, filed):
        with pytest.raises(Refused) as exc:
            as_person(people["a.mehta"]).attachments.review(
                filed["id"], accept=False)
        assert exc.value.code == "reason_required"

    def test_a_rejected_document_is_still_in_the_history(self, as_person,
                                                         people, maya, filed):
        as_person(people["a.mehta"]).attachments.review(
            filed["id"], accept=False, note="no back-testing")
        history = maya.attachments.list(URN, history=True)["attachments"]
        assert [a["state"] for a in history] == ["rejected"]
        assert maya.attachments.list(URN)["rejected"] == 1, \
            "the register counts what somebody tried to file and could not"


class TestWhatADocumentIsAbout:
    def test_saying_nothing_files_against_the_version(self, filed):
        """An existing caller that knows nothing about subjects files exactly
        what it filed before."""
        assert filed["subject_type"] == "model_version"

    def test_a_convergence_study_is_filed_against_the_parameter_set(
            self, maya, parameter_set):
        """The case that had nowhere to go: a calibrated model produces a
        parameter set every morning, and the note explaining the morning it went
        wrong had nothing to hang on."""
        out = maya.attachments.attach(
            URN, content=b"# convergence", filename="conv.md",
            kind="evidence_of_control", title="Convergence study",
            subject_type="parameter_set", subject_id=parameter_set["id"])
        assert out["subject_type"] == "parameter_set"
        assert out["subject_id"] == parameter_set["id"]

    def test_a_subject_the_platform_cannot_resolve_is_refused_clearly(self, maya):
        """`featureset` is not attachable and `featureset_version` is. The
        difference is the whole point: a document filed against the set would
        describe something that has since moved."""
        with pytest.raises(Refused) as exc:
            maya.attachments.attach(
                URN, content=b"# dictionary", filename="dict.md",
                kind="other", title="Data dictionary",
                subject_type="featureset", subject_id="sb_core")
        assert exc.value.code == "unknown_subject"
        assert "featureset_version" in exc.value.remediation

    def test_a_model_level_document_has_to_be_asked_for(self, maya):
        out = maya.attachments.attach(URN, content=b"# methodology",
                                      filename="method.md", kind="other",
                                      title="Methodology", model_level=True)
        assert out["subject_type"] == "model"
        assert out["model_version_id"] is None

    def test_an_unknown_kind_is_refused_with_the_list(self, maya):
        with pytest.raises(Refused) as exc:
            maya.attachments.attach(URN, content=b"x", filename="x.md",
                                    kind="vibes", title="T")
        assert exc.value.code == "unknown_kind"
        assert "validation_report" in exc.value.remediation


class TestCompiledDocuments:
    def test_a_document_is_compiled_and_read_back(self, maya):
        out = maya.documents.compile(URN, kind="model_card")
        assert out["kind"] == "model_card"
        read = maya.documents.get(out["id"])
        assert "staleness" in read and "citations_verified" in read

    def test_the_listing_carries_staleness_rather_than_leaving_it_to_be_asked(
            self, maya):
        """A document nobody knows is stale is a document being relied on."""
        maya.documents.compile(URN, kind="model_card")
        documents = maya.documents.list(URN)["documents"]
        assert documents and all("staleness" in d for d in documents)

    def test_the_markdown_is_what_a_person_reads(self, maya):
        document = maya.documents.compile(URN, kind="model_development_document")
        body = maya.documents.markdown(document["id"])
        assert isinstance(body, str) and body.lstrip().startswith("#")

    def test_a_section_the_evidence_cannot_support_is_a_gap(self, maya):
        """The difference between a compiled document and a written one: a thin
        model produces a document that says it is thin."""
        out = maya.documents.compile(URN, kind="annex_iv")
        coverage = out["coverage"]
        assert coverage["filled"] >= 1
        assert coverage["sections"] > coverage["filled"], \
            "a fresh model cannot support every Annex IV section"
        assert coverage["complete"] is False
        unfilled = [s["key"] for s in out["sections"] if not s["filled"]]
        assert unfilled and all(out_section["body"] for out_section in out["sections"]), \
            "an unfillable section says what is missing rather than being blank"

    def test_an_unknown_document_is_a_refusal_and_not_an_empty_answer(self, maya):
        with pytest.raises(NotFound):
            maya.documents.get("no-such-document")


class TestTheDocumentationGraph:
    def test_the_dossier_is_a_graph_rooted_at_the_model(self, maya):
        dossier = maya.documents.dossier(URN)
        assert dossier["root"]["subject_type"] == "model"
        assert dossier["counts"]["nodes"] >= 2

    def test_the_short_name_and_the_full_urn_reach_the_same_dossier(self, maya):
        assert maya.documents.dossier(NAME) == maya.documents.dossier(URN)

    def test_a_node_with_nothing_filed_is_a_gap_rather_than_a_blank(self, maya):
        """A reader cannot tell a thin model from a thin page unless the page
        says which it is."""
        dossier = maya.documents.dossier(URN)
        assert dossier["gaps"] and all(g["why"] for g in dossier["gaps"])

    def test_a_document_filed_about_a_thing_is_found_from_that_thing(
            self, maya, parameter_set):
        """There is no by-subject listing endpoint; this is the read that
        answers *what is filed about this parameter set*, and it is answered on
        the platform rather than by filtering a listing here."""
        maya.attachments.attach(
            URN, content=b"# convergence", filename="conv.md",
            kind="evidence_of_control", title="Convergence study",
            subject_type="parameter_set", subject_id=parameter_set["id"])
        dossier = maya.documents.dossier(URN)
        titles = [a["title"] for node in _walk(dossier["root"])
                  for a in node.get("attached") or []]
        assert "Convergence study" in titles

    def test_an_unknown_model_is_refused_rather_than_answered_emptily(self, maya):
        with pytest.raises(NotFound):
            maya.documents.dossier("nothing.here")


class TestTheTrainingRecord:
    """The document a daily recalibration never had."""

    def test_a_preview_says_what_it_would_say_without_authoring_it(
            self, maya, parameter_set):
        record = maya.documents.preview_training_record(parameter_set["id"])
        assert record["kind"] == "training_record"
        assert record["subject_id"] == parameter_set["id"]

    def test_a_declared_fit_is_named_as_declared_rather_than_left_blank(
            self, maya, parameter_set):
        record = maya.documents.preview_training_record(parameter_set["id"])
        authority = next(s for s in record["sections"]
                         if s["key"] == "authority")
        assert "Declared rather than fitted" in authority["body"]

    def test_compiling_it_records_that_it_happened(self, maya, parameter_set):
        out = maya.documents.training_record(parameter_set["id"])
        assert out["subject_id"] == parameter_set["id"]
        assert out["subject_type"] == "parameter_set"


class TestTheExportPack:
    def test_what_a_pack_holds_is_published(self, maya):
        """A reader who does not know what a pack should contain cannot tell a
        thin model from a thin export."""
        described = maya.packages.describe()
        assert described["pack_version"] and described["contents"]["gaps.md"]

    def test_it_is_written_to_a_file_rather_than_returned(self, maya, tmp_path):
        """An export pack is not small, and an SDK that materialised it to be
        convenient would be convenient until the first real model."""
        out = maya.packages.cut(URN, tmp_path / "pack.zip")
        assert out.exists() and out.stat().st_size > 0
        assert zipfile.is_zipfile(out)

    def test_the_zip_holds_exactly_what_the_manifest_claims(self, maya, tmp_path):
        pack = maya.packages.cut(URN, tmp_path / "pack.zip")
        with zipfile.ZipFile(pack) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            for entry in manifest["files"]:
                body = archive.read(entry["name"])
                assert entry["digest"] == "sha256:" + hashlib.sha256(body).hexdigest()
                assert entry["bytes"] == len(body)
        assert {e["name"] for e in manifest["files"]} | {"manifest.json"} == names
        assert "README.md" in names and "gaps.md" in names

    def test_a_gap_is_written_down_rather_than_omitted(self, maya, tmp_path):
        """A pack that quietly left something out looks complete, and looking
        complete is worse than being thin."""
        pack = maya.packages.cut(URN, tmp_path / "pack.zip")
        with zipfile.ZipFile(pack) as archive:
            gaps = archive.read("gaps.md").decode()
            manifest = json.loads(archive.read("manifest.json"))
        assert gaps.startswith("# Gaps"), \
            "the file is present even when empty, so a reader learns it exists"
        if manifest["gaps"]:
            assert "|" in gaps, "gaps are listed with their reason, not counted"
        else:
            assert "None." in gaps

    def test_an_accepted_attachment_travels_in_the_pack(self, as_person, people,
                                                        maya, filed, tmp_path):
        as_person(people["a.mehta"]).attachments.review(
            filed["id"], accept=True, note="complete")
        pack = maya.packages.cut(URN, tmp_path / "pack.zip")
        with zipfile.ZipFile(pack) as archive:
            attached = [n for n in archive.namelist()
                        if n.startswith("attachments/")]
        assert any(n.endswith("mdd.md") for n in attached)

    def test_the_manifest_answers_without_moving_the_bytes(self, maya, tmp_path):
        """Comparing against the last pack should not require a hundred
        megabytes to find out that nothing has changed."""
        summary = maya.packages.manifest(URN)
        pack = maya.packages.cut(URN, tmp_path / "pack.zip")
        with zipfile.ZipFile(pack) as archive:
            inside = json.loads(archive.read("manifest.json"))
        assert summary["content_digest"] == inside["content_digest"]
        assert summary["pack_digest"] and summary["filename"]

    def test_narrowing_the_documents_narrows_only_the_documents(self, maya,
                                                                tmp_path):
        pack = maya.packages.cut(URN, tmp_path / "pack.zip",
                                 documents=["model_card"])
        with zipfile.ZipFile(pack) as archive:
            names = set(archive.namelist())
        assert "documents/model_card.md" in names
        assert "documents/annex_iv.md" not in names
        assert "model.json" in names and "findings.json" in names

    def test_a_kind_the_compiler_does_not_know_becomes_a_gap(self, maya,
                                                             tmp_path):
        pack = maya.packages.cut(URN, tmp_path / "pack.zip",
                                 documents=["model_card", "not_a_kind"])
        with zipfile.ZipFile(pack) as archive:
            assert "not_a_kind" in archive.read("gaps.md").decode()
            assert "documents/model_card.md" in archive.namelist()

    def test_a_pack_for_a_model_that_does_not_exist_is_refused(self, maya,
                                                               tmp_path):
        with pytest.raises(NotFound):
            maya.packages.cut("nothing.here", tmp_path / "pack.zip")

    def test_a_caller_who_may_not_read_the_model_may_not_export_it(
            self, as_person, people, tmp_path):
        """A pack is the most complete thing this platform produces about a
        model, so an export by somebody who may not read it would be the largest
        scope leak available."""
        maya = as_person(("nobody", "wrong"))
        with pytest.raises(Refused):
            maya.packages.cut(URN, tmp_path / "pack.zip")


def _walk(node):
    yield node
    for child in node.get("children") or []:
        yield from _walk(child)
