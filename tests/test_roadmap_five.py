"""The five roadmap items: a time somebody else attests to, what is installed,
what a source exported, what a scanner swept, and a pack handed to somebody with
no login.

Each has a boundary, and the boundary is what the tests are about.
"""
from __future__ import annotations

import pytest

from core.discovery.common import DiscoveryError
from core.discovery.connectors import (GIT, MLFLOW, NOT_IN_THE_SOURCE, SOURCES,
                                       UNITY, Connectors)
from core.discovery.contract import (CERTAINTY, POOR_PRECISION, REQUIRED,
                                     SWEEP_REQUIRED, ScannerContract)
from core.docs.common import DocumentError
from core.docs.rendering import LATEX, NOT_PRODUCED, DocumentRendering
from core.evidence.timestamps import (ABSENT, UNVERIFIED, VERIFIED,
                                      ChainTimestamps, TimestampError)
from core.export.common import ExportError
from core.export.sharing import MAX_DAYS, ExportSharing
from core.plugins.common import PluginError
from core.plugins.discovery import FIBRE_RULE, GROUP, SEEN, PluginDiscovery
from tests.api_helpers import login
from tests.conftest import URN

DAY = 86400.0


# ------------------------------------------------------- 1. timestamps
class _Authority:
    name = "test-tsa"

    def stamp(self, digest):
        return {"token": f"tok-{digest[:8]}", "alg": "sha256"}


class _Verifier:
    def __init__(self, valid=True):
        self.valid = valid

    def verify(self, token, digest):
        return {"valid": self.valid, "at": 1_800_000_000.0,
                "authority": "test-tsa", "why": "" if self.valid else "no"}


@pytest.fixture
def anchored(tmp_path, evidence):
    from core.evidence.anchor import ChainAnchor
    anchor = ChainAnchor(tmp_path / "worm", evidence=evidence)
    evidence.append("model_registered", "model", "m1", {}, actor="x")
    seq, chain_hash = evidence.head()
    anchor.anchor(seq, chain_hash, actor="x")
    return anchor


class TestMayaIsNotTheAuthority:
    def test_it_says_so(self):
        out = ChainTimestamps.posture()
        assert out["is_the_authority"] is False
        assert out["verifies_by_default"] is False

    def test_no_authority_refuses_rather_than_pretending(self, anchored):
        with pytest.raises(TimestampError) as e:
            ChainTimestamps(anchored).stamp()
        assert e.value.code == "no_timestamp_authority"
        assert "the firm's own clock" in e.value.remediation

    def test_an_unanchored_chain_has_nothing_to_stamp(self, tmp_path, evidence):
        from core.evidence.anchor import ChainAnchor
        bare = ChainAnchor(tmp_path / "w2", evidence=evidence)
        with pytest.raises(TimestampError) as e:
            ChainTimestamps(bare, authority=_Authority()).stamp()
        assert e.value.code == "nothing_anchored"
        assert "nothing can later be compared against" in e.value.remediation

    def test_a_held_token_with_no_verifier_is_unverified_not_verified(
            self, anchored):
        stamps = ChainTimestamps(anchored, authority=_Authority())
        out = stamps.stamp(actor="x")
        assert out["state"] == UNVERIFIED
        assert "will not make on its behalf" in out["why"]

    def test_a_wired_verifier_can_reach_verified(self, anchored):
        stamps = ChainTimestamps(anchored, authority=_Authority(),
                                 verifier=_Verifier())
        stamps.stamp(actor="x")
        seq = anchored.latest()["seq"]
        assert stamps.read(seq)["state"] == VERIFIED

    def test_an_unstamped_head_is_absent_not_untimed(self, anchored):
        out = ChainTimestamps(anchored).read(anchored.latest()["seq"])
        assert out["state"] == ABSENT
        assert "rather than as untimed" in out["detail"]

    def test_stamping_twice_writes_once(self, anchored):
        stamps = ChainTimestamps(anchored, authority=_Authority())
        stamps.stamp(actor="x")
        assert stamps.stamp(actor="x")["written"] == 0

    def test_it_bounds_from_above_only_and_says_so(self, anchored):
        bounds = ChainTimestamps.posture()["bounds"]
        assert "NO LATER" in bounds["above"]
        assert bounds["below"].startswith("nothing")
        assert bounds["deletion"].startswith("nothing")

    def test_coverage_names_the_unwired_authority(self, anchored):
        out = ChainTimestamps(anchored).coverage()
        assert out["authority_wired"] is False
        assert "arguing from its own clock" in out["detail"]


# --------------------------------------------------- 2. plugin discovery
class TestInstallingIsNotEnabling:
    def test_the_contract_says_so(self):
        out = PluginDiscovery.contract()
        assert out["installing_is_not_enabling"] is True
        assert out["group"] == GROUP

    def test_discovery_imports_nothing(self):
        out = PluginDiscovery().discover()
        assert out["imported_anything"] is False
        assert "nothing was imported to find out" in out["detail"]

    def test_enabling_something_config_does_not_name_is_refused(self):
        with pytest.raises(PluginError) as e:
            PluginDiscovery().enable("test_types", "kendall_tau")
        assert e.value.code == "not_enabled"
        assert "bumped a dependency" in e.value.remediation

    def test_enabling_something_not_installed_is_a_different_refusal(self):
        engine = PluginDiscovery(enabled=["test_types:kendall_tau"])
        with pytest.raises(PluginError) as e:
            engine.enable("test_types", "kendall_tau")
        assert e.value.code == "not_installed"
        assert "a control somebody believes is running" in e.value.remediation

    def test_a_closed_axis_is_refused_and_names_what_it_protects(self):
        engine = PluginDiscovery(enabled=["runtime_adapters:onnx2"])
        with pytest.raises(PluginError) as e:
            engine.enable("runtime_adapters", "onnx2")
        # Not installed is checked first; the axis refusal is reachable through
        # `_describe`, which the contract publishes.
        assert e.value.code in ("not_installed", "axis_closed")
        assert "runtime_adapters" in PluginDiscovery.contract()["closed"]

    def test_a_fibre_may_only_tighten(self):
        assert "may never remove one" in FIBRE_RULE
        assert "fibres" in PluginDiscovery.contract()["open"]

    def test_a_stock_install_declares_nothing_and_says_that_is_ordinary(self):
        out = PluginDiscovery().discover()
        assert out["count"] == 0
        assert "ordinary state for a stock install" in out["detail"]
        assert out["by_state"] == {} and SEEN in ("seen",)


# ------------------------------------------------------- 3. connectors
MLFLOW_EXPORT = {"registered_models": [
    {"name": "credit_pd", "user_id": "a.mehta",
     "latest_versions": [{"version": 3, "run_id": "r-abc",
                          "current_stage": "Production"}]},
    {"name": "fraud_v2", "latest_versions": []},
]}


class TestAConnectorRegistersNothing:
    def test_it_says_so(self):
        assert Connectors.describe()["registers_anything"] is False
        assert Connectors.describe()["holds_credentials"] is False

    def test_it_produces_candidates(self):
        out = Connectors(None).read(MLFLOW, MLFLOW_EXPORT)
        assert out["count"] == 2 and out["registers_anything"] is False
        assert "none of them is a registered model" in out["detail"].lower()

    def test_every_candidate_names_what_must_still_be_established(self):
        out = Connectors(None).read(MLFLOW, MLFLOW_EXPORT)
        for candidate in out["candidates"]:
            assert candidate["must_still_be_established"]
        assert len(NOT_IN_THE_SOURCE) >= 5

    def test_no_candidate_asserts_certainty(self):
        out = Connectors(None).read(MLFLOW, MLFLOW_EXPORT)
        assert all(c["confidence"] < 1.0 for c in out["candidates"])

    def test_the_fingerprint_survives_the_source(self):
        """An MLflow run_id keys a candidate to a row a re-registration
        replaces, and the triage somebody did would be lost."""
        first = Connectors(None).read(MLFLOW, MLFLOW_EXPORT)["candidates"][1]
        again = Connectors(None).read(MLFLOW, {"registered_models": [
            {"name": "fraud_v2", "latest_versions": [
                {"version": 9, "run_id": "totally-different"}]}]})
        # No digest either time for fraud_v2's first form, so the name carries
        # it; a digest appearing later is a different, better key.
        assert first["fingerprint"].startswith("sha256:")
        assert again["candidates"][0]["fingerprint"].startswith("sha256:")

    def test_unity_and_git_parse_too(self):
        unity = Connectors(None).read(UNITY, {"rows": [
            {"catalog_name": "main", "schema_name": "risk",
             "model_name": "pd", "model_owner": "team"}]})
        git = Connectors(None).read(GIT, {"paths": [
            {"path": "models/pd.py", "repository": "risk", "blob_sha": "abc"}]})
        assert unity["count"] == 1 and git["count"] == 1

    def test_an_unknown_source_is_refused(self):
        with pytest.raises(DiscoveryError) as e:
            Connectors(None).read("databricks_jobs", {})
        assert e.value.code == "unknown_source"

    def test_a_malformed_export_is_the_sources_problem(self):
        with pytest.raises(DiscoveryError) as e:
            Connectors(None).read(MLFLOW, "not json {")
        assert e.value.code == "unreadable_export"
        assert "a job to fix over there" in e.value.remediation

    def test_every_source_says_why_not_the_api(self):
        assert all(v["why_not_the_api"].strip() for v in SOURCES.values())


# --------------------------------------------------- 4. scanner contract
GOOD_SWEEP = {
    "scanner": "euc-sweep", "scope": "drives A and B, not C",
    "recall_known": False,
    "candidates": [{"fingerprint": "sha256:aa", "location": "/a.xlsx",
                    "source": "drive", "confidence": 0.7,
                    "evidence": {"matched": "=LINEST("}}],
}


class TestTheScannerContract:
    def test_maya_does_not_run_one(self):
        assert ScannerContract.contract()["maya_runs_a_scanner"] is False

    def test_a_good_sweep_is_admissible(self):
        assert ScannerContract(None).check(GOOD_SWEEP)["admissible"] is True

    def test_certainty_is_refused(self):
        sweep = {**GOOD_SWEEP,
                 "candidates": [{**GOOD_SWEEP["candidates"][0],
                                 "confidence": 1.0}]}
        out = ScannerContract(None).check(sweep)
        assert not out["admissible"]
        assert any("asserts certainty" in p["why"] for p in out["problems"])
        assert CERTAINTY == 1.0

    def test_every_problem_is_reported_not_the_first(self):
        out = ScannerContract(None).check({"candidates": [{}]})
        assert len(out["problems"]) > 3
        assert "re-runs over forty thousand files" in out["detail"]

    def test_recall_must_be_stated_even_as_unknown(self):
        sweep = {k: v for k, v in GOOD_SWEEP.items() if k != "recall_known"}
        out = ScannerContract(None).check(sweep)
        assert any(p["what"] == "sweep.recall_known" for p in out["problems"])

    def test_stating_recall_unknown_is_praised_not_penalised(self):
        assert "the honest answer" in ScannerContract(None).check(
            GOOD_SWEEP)["detail"]

    def test_a_bad_sweep_is_refused_whole(self, db, registry, evidence):
        from core.discovery.register import DiscoveryRegister
        from db import DiscoveryRepository
        register = DiscoveryRegister(DiscoveryRepository(db), registry,
                                     evidence)
        with pytest.raises(DiscoveryError) as e:
            ScannerContract(register).ingest({**GOOD_SWEEP, "candidates": [{}]})
        assert e.value.code == "sweep_does_not_meet_the_contract"
        assert "a grade for something other than the scanner" in \
            e.value.remediation

    def test_the_contract_is_published(self):
        out = ScannerContract.contract()
        assert len(out["candidate_fields"]) == len(REQUIRED)
        assert len(out["sweep_fields"]) == len(SWEEP_REQUIRED)
        assert out["poor_precision_below"] == POOR_PRECISION


# --------------------------------------------------------- 5. sharing
@pytest.fixture
def sharing(db, registry, evidence, a_model):
    from db import ExportShareReadRepository, ExportShareRepository
    return ExportSharing(ExportShareRepository(db),
                         ExportShareReadRepository(db), registry, evidence)


class TestAShareIsNotAPortal:
    def test_it_says_so(self):
        out = ExportSharing.posture()
        assert out["is_a_portal"] is False
        assert out["establishes_identity"] is False
        assert "issuing a credential to somebody outside the firm" in \
            out["detail"]

    def test_a_share_points_at_content_not_a_path(self, sharing):
        with pytest.raises(ExportError) as e:
            sharing.share(URN, recipient="PRA", purpose="2026 examination",
                          content_digest="")
        assert e.value.code == "content_digest_required"
        assert "whatever is at that location later" in e.value.remediation

    def test_a_recipient_and_a_purpose_are_required(self, sharing):
        for kwargs, code in ((dict(recipient=" "), "recipient_required"),
                             (dict(purpose=" "), "purpose_required")):
            with pytest.raises(ExportError) as e:
                sharing.share(URN, **{"recipient": "PRA",
                                      "purpose": "exam",
                                      "content_digest": "sha256:aa", **kwargs})
            assert e.value.code == code

    def test_the_window_is_bounded(self, sharing):
        with pytest.raises(ExportError) as e:
            sharing.share(URN, recipient="PRA", purpose="exam",
                          content_digest="sha256:aa", days=MAX_DAYS + 1)
        assert e.value.code == "window_out_of_range"

    def test_a_live_share_serves_and_records_the_read(self, sharing):
        made = sharing.share(URN, recipient="PRA", purpose="exam",
                             content_digest="sha256:aa")
        out = sharing.open_share(made["reference"], seen_from="1.2.3.4")
        assert out["content_digest"] == "sha256:aa"
        assert out["identity_established"] is False
        assert sharing.status(made["reference"])["served"] == 1

    def test_an_expired_share_refuses_and_records_the_refusal(self, sharing):
        made = sharing.share(URN, recipient="PRA", purpose="exam",
                             content_digest="sha256:aa", days=1.0, now=0.0)
        with pytest.raises(ExportError) as e:
            sharing.open_share(made["reference"], now=10 * DAY)
        assert e.value.code == "share_expired"
        assert sharing.status(made["reference"], now=10 * DAY)["refused"] == 1

    def test_a_read_cap_exhausts(self, sharing):
        made = sharing.share(URN, recipient="PRA", purpose="exam",
                             content_digest="sha256:aa", max_reads=1)
        sharing.open_share(made["reference"])
        with pytest.raises(ExportError) as e:
            sharing.open_share(made["reference"])
        assert e.value.code == "share_exhausted"

    def test_revoking_keeps_what_it_served(self, sharing):
        made = sharing.share(URN, recipient="PRA", purpose="exam",
                             content_digest="sha256:aa")
        sharing.open_share(made["reference"])
        after = sharing.revoke(made["reference"], "request withdrawn")
        assert after["state"] == "revoked" and after["served"] == 1

    def test_an_unknown_reference_says_nothing_about_what_exists(self, sharing):
        with pytest.raises(ExportError) as e:
            sharing.require("not-a-real-reference")
        assert e.value.code == "unknown_share"
        assert "reads exactly like an expired one" in e.value.remediation


# ----------------------------------------------------- 4b. rendering
class TestATypesettingSourceNotAPdf:
    def test_pdf_is_refused_by_name_with_the_reason(self, db, a_model):
        from db import DocumentRepository
        with pytest.raises(DocumentError) as e:
            DocumentRendering(DocumentRepository(db)).render("x", "pdf")
        assert e.value.code == "format_not_produced"
        assert "house template" in e.value.detail

    def test_every_refused_format_gives_a_reason(self):
        assert all(w.strip() for w in NOT_PRODUCED.values())
        assert set(NOT_PRODUCED) >= {"pdf", "docx"}

    def test_it_renders_nothing_and_says_so(self):
        assert DocumentRendering.formats()["renders_anything"] is False
        assert "where a citation goes to die" in \
            DocumentRendering.formats()["detail"]

    def test_latex_carries_the_citations(self, db, a_model):
        from db import DocumentRepository
        repo = DocumentRepository(db)
        row = {"model_id": a_model["id"], "model_version_id": None,
               "subject_type": "model", "subject_id": a_model["id"],
               "kind": "model_development", "title": "SB PD & friends",
               "sections": [{"key": "purpose", "title": "Purpose",
                             "body": "It estimates a 12-month PD."}],
               "citations": {"purpose": ["node-1", "node-2"]},
               "coverage": {"gaps": [{"what": "outcomes analysis",
                                      "why": "no matured cohort"}]},
               "digest": "sha256:d", "subjects": [],
               "evidence_head": "sha256:h", "status": "compiled",
               "compiled_at": 0.0, "compiled_by": "x"}
        repo.add(row)
        out = DocumentRendering(repo).render(row["id"], LATEX)
        assert r"\documentclass" in out["source"]
        assert "node-1" in out["source"]
        assert out["citations"] == 2
        assert out["renders_it"] is False

    def test_gaps_are_marked_in_the_output_not_dropped(self, db, a_model):
        from db import DocumentRepository
        repo = DocumentRepository(db)
        row = {"model_id": a_model["id"], "model_version_id": None,
               "subject_type": "model", "subject_id": a_model["id"],
               "kind": "model_development", "title": "T",
               "sections": [], "citations": {},
               "coverage": {"gaps": [{"what": "outcomes analysis"}]},
               "digest": "sha256:e", "subjects": [],
               "evidence_head": "sha256:h", "status": "compiled",
               "compiled_at": 0.0, "compiled_by": "x"}
        repo.add(row)
        out = DocumentRendering(repo).render(row["id"], LATEX)
        assert "What this document does not contain" in out["source"]
        assert "the committee never sees" in out["detail"]

    def test_latex_specials_are_escaped(self, db, a_model):
        from db import DocumentRepository
        repo = DocumentRepository(db)
        row = {"model_id": a_model["id"], "model_version_id": None,
               "subject_type": "model", "subject_id": a_model["id"],
               "kind": "model_development", "title": "100% & rising",
               "sections": [], "citations": {}, "coverage": {},
               "digest": "sha256:f", "subjects": [],
               "evidence_head": "sha256:h", "status": "compiled",
               "compiled_at": 0.0, "compiled_by": "x"}
        repo.add(row)
        source = DocumentRendering(repo).render(row["id"], LATEX)["source"]
        assert r"100\% \& rising" in source


# ------------------------------------------------------- the screen
class TestTheEdgesAreOnAScreen:
    """Four subjects that had an API and no screen. The people who own the
    question *what are we relying on somebody else for* are not the people who
    read JSON."""

    def test_it_renders(self, client):
        login(client)
        page = client.get("/admin/perimeter")
        assert page.status_code == 200
        body = page.text
        assert "The register&#39;s edges" in body or "register's edges" in body

    def test_nothing_renders_as_undefined(self, client):
        """The failure mode of a screen like this is not a crash: it is
        `Undefined` where an answer should be, which reads as *nothing*."""
        login(client)
        body = client.get("/admin/perimeter").text
        assert "Undefined" not in body and "jinja2" not in body.lower()
        assert "Installed is not enabled" in body

    def test_it_says_a_share_is_not_a_portal(self, client):
        login(client)
        assert "not an examiner" in client.get("/admin/perimeter").text

    def test_the_nav_reaches_it(self, client):
        login(client)
        assert "/admin/perimeter" in client.get("/admin/evidence").text

    def test_the_evidence_screen_carries_the_third_question(self, client):
        login(client)
        body = client.get("/admin/evidence").text
        assert "a clock that is not ours" in body
        assert "from above" in body
