"""Looking at what arrived from outside, before it is trusted.

The requirement names five checks and the honest answer is different for each.
Three need something this platform deliberately does not ship, so the port is
defined, the platform reports whether one is wired, and where none is it says so
rather than showing a tick.
"""
from __future__ import annotations

import pytest

from core.scanning import CHECKS, QUARANTINE, UploadScanner
from core.scanning.patterns import PATTERNS
from core.scanning.upload import CLEAN, MAX_BYTES
from tests.conftest import URN

A_KEY = b"-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----"


@pytest.fixture
def scanner():
    return UploadScanner()


class TestOneCopyOfThePatterns:
    def test_the_ci_gate_and_the_upload_scanner_share_them(self):
        """Two copies of a credential pattern list is two answers to *is this a
        secret*, and the copy that goes stale is the one somebody relies on."""
        import tools.ci.scan_secrets as gate
        assert gate.PATTERNS is PATTERNS

    def test_every_pattern_says_what_it_is(self):
        assert all(name and means for name, means, _ in PATTERNS)


class TestWhatItCanActuallyCheck:
    def test_the_posture_names_what_is_unavailable(self, scanner):
        """A clean result from nothing having looked is worse than no result."""
        out = scanner.posture()
        assert set(out["unavailable"]) == {"malware", "dependencies"}
        assert "the tick is what stops anybody asking" in out["detail"]

    def test_opcode_analysis_is_answered_by_exclusion(self, scanner):
        """A format that cannot execute beats a scanner that has to decide
        whether an opcode sequence is malicious."""
        assert CHECKS["opcode"]["state"] == "answered by exclusion"
        assert "arms race" in CHECKS["opcode"]["why"]
        assert "no `pickle`" in scanner.posture()["detail"]

    def test_a_wired_port_becomes_available(self):
        scanner = UploadScanner(malware=lambda payload: [])
        assert "malware" not in scanner.posture()["unavailable"]


class TestSecrets:
    def test_a_private_key_quarantines_the_upload(self, scanner):
        out = scanner.scan(A_KEY, filename="model.onnx")
        assert out["state"] == QUARANTINE
        assert out["findings"][0]["check"] == "secrets"

    def test_the_finding_never_carries_the_secret(self, scanner):
        """A finding holding the credential is a second copy of it, in a table
        more people can read than the file it came from."""
        out = scanner.scan(A_KEY)
        blob = repr(out)
        assert "MIIabc" not in blob
        assert "deliberately not recorded" in out["findings"][0]["why"]

    def test_a_credential_inside_a_binary_artifact_is_found(self, scanner):
        """Refusing to look at anything that is not clean UTF-8 would skip
        exactly the case worth catching."""
        blob = b"\x00\x01\x02" + A_KEY + b"\xff\xfe"
        assert scanner.scan(blob)["state"] == QUARANTINE

    def test_a_clean_artifact_passes(self, scanner):
        out = scanner.scan(b"just some model weights")
        assert out["state"] == CLEAN
        assert "nothing this platform can check found anything" in out["detail"]

    def test_a_truncated_scan_says_so(self, scanner):
        """A scan of the first slice presented as a scan is the same lie as a
        scan by nothing at all."""
        out = scanner.scan(b"x" * (MAX_BYTES + 10))
        assert out["truncated"] is True
        assert "the same lie as a scan by nothing at all" in out["detail"]


class TestLicences:
    def test_an_allowed_licence_passes(self, scanner):
        assert scanner.scan(b"x", declared_licences=["MIT"])["state"] == CLEAN

    def test_a_licence_off_the_list_quarantines(self, scanner):
        out = scanner.scan(b"x", declared_licences=["AGPL-3.0"])
        assert out["state"] == QUARANTINE
        assert out["findings"][0]["licence"] == "AGPL-3.0"

    def test_the_list_is_configuration_not_an_opinion(self, scanner):
        out = scanner.scan(b"x", declared_licences=["AGPL-3.0"])
        assert "nobody's counsel will accept" in out["findings"][0]["why"]

    def test_a_licence_in_a_manifest_is_found_under_any_of_its_names(self):
        scanner = UploadScanner()
        for key in ("licence", "license", "spdx", "spdx_id"):
            out = scanner.scan(b"x", manifest={key: "AGPL-3.0"})
            assert out["state"] == QUARANTINE, key

    def test_a_firm_may_widen_the_list(self):
        scanner = UploadScanner(licences=("MIT", "AGPL-3.0"))
        assert scanner.scan(b"x", declared_licences=["AGPL-3.0"])["state"] == CLEAN


class TestThePorts:
    def test_an_unwired_port_never_reports_clean(self, scanner):
        out = scanner.scan(b"x")
        assert "malware" in out["checks_unwired"]
        assert "reported rather than passed" in out["detail"]

    def test_a_wired_port_that_finds_something_quarantines(self):
        scanner = UploadScanner(
            malware=lambda payload: [{"pattern": "eicar", "why": "test file"}])
        assert scanner.scan(b"x")["state"] == QUARANTINE

    def test_a_scanner_that_falls_over_does_not_pass_the_upload(self):
        """An upload nothing could check is not an upload something checked and
        cleared."""
        def broken(payload):
            raise RuntimeError("engine down")

        out = UploadScanner(malware=broken).scan(b"x")
        assert out["state"] == QUARANTINE
        assert out["findings"][0]["pattern"] == "scanner failed"


class TestQuarantineNotBlock:
    def test_a_poisoned_attachment_is_stored_and_marked(self, attachments,
                                                        a_model,
                                                        approved_version):
        """A blocked upload is one somebody retries around; a quarantined one
        is on the record with the reason a reviewer needs."""
        attachments.scanner = UploadScanner()
        row = attachments.attach(URN, "validation_report", "Report",
                                 "report.txt", A_KEY, actor="a.mehta",
                                 media_type="text/plain")
        assert row["state"] == "quarantined"
        assert "quarantined" in row["review_note"]
        # Stored, not discarded: a scanner that deletes its own evidence leaves
        # nobody able to check whether it was right.
        assert attachments.content(row["id"]) == A_KEY

    def test_a_clean_attachment_is_untouched(self, attachments, a_model,
                                             approved_version):
        attachments.scanner = UploadScanner()
        row = attachments.attach(URN, "validation_report", "Report", "r.txt",
                                 b"a clean report", actor="a.mehta",
                                 media_type="text/plain")
        assert row["state"] == "attached"

    def test_without_a_scanner_nothing_is_marked_clean(self, attachments,
                                                       a_model,
                                                       approved_version):
        attachments.scanner = None
        row = attachments.attach(URN, "validation_report", "R", "r.txt",
                                 A_KEY, actor="a.mehta",
                                 media_type="text/plain")
        assert row["state"] == "attached", "not scanned is not the same as clean"

    def test_the_verdict_is_on_the_evidence_chain(self, attachments, a_model,
                                                  approved_version, evidence,
                                                  registry):
        attachments.scanner = UploadScanner()
        attachments.attach(URN, "validation_report", "R", "r.txt", A_KEY,
                           actor="a.mehta", media_type="text/plain")
        model_id = registry.require(URN)["id"]
        node = [n for n in evidence.for_subject(model_id)
                if n["kind"] == "document_attached"][-1]
        assert node["payload"]["state"] == "quarantined"
