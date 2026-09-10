"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The register's edges, through the SDK, against the real application.

Same seam and the same reason as `test_sdk.py`: every call below travels the
routes, authorisation and the domain, so what is asserted is that the client
agrees with a *server* rather than with a fixture.

What these tests are actually protecting is narrower than method coverage.
Each of the six subjects here is a place where a platform is tempted to claim
more than it holds — a timestamp it did not verify, a plugin it imported to
find out about, a candidate it calls a registration, a sweep it half-accepted,
a share it calls a portal, a PDF it calls evidence. The assertions are mostly
on the *words that come back*, because the words are the control: a client that
received `verified` for a token nobody checked would have been told something
untrue, and no amount of correct plumbing underneath fixes that.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))

from maya_sdk import Maya, Refused

URN = "maya://model/credit.pd.smallbiz"


class _TestClientTransport:
    def __init__(self, client, auth=None):
        self.client, self.auth = client, auth

    def request(self, method, path, *, json=None, content=None, params=None,
                headers=None):
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return self.client.request(method, path, json=json, content=content,
                                   params=clean or None, headers=headers,
                                   auth=self.auth or self.client.auth)


@pytest.fixture
def maya(client):
    return Maya(transport=_TestClientTransport(client))


class TestTheClientIsToldWhatATimestampProves:
    def test_the_posture_reaches_the_client_whole(self, maya):
        out = maya.timestamps.posture()
        assert out["is_the_authority"] is False
        assert "NO LATER" in out["bounds"]["above"]

    def test_coverage_answers_on_a_platform_with_no_authority(self, maya):
        assert maya.timestamps.coverage()["authority_wired"] is False

    def test_stamping_is_refused_rather_than_faked(self, maya):
        with pytest.raises(Refused) as e:
            maya.timestamps.stamp()
        assert e.value.code in ("no_timestamp_authority", "nothing_anchored")
        assert e.value.remediation


class TestInstalledIsNotEnabled:
    def test_the_contract_arrives(self, maya):
        out = maya.plugins.contract()
        assert out["group"] == "maya.extensions"
        assert out["installing_is_not_enabling"] is True

    def test_discovery_states_that_it_imported_nothing(self, maya):
        assert maya.plugins.discovered()["imported_anything"] is False

    def test_enabling_an_unnamed_plugin_raises_with_remediation(self, maya):
        with pytest.raises(Refused) as e:
            maya.plugins.enable("test_types", "kendall_tau")
        assert e.value.code in ("not_enabled", "not_installed")
        assert e.value.remediation


class TestAConnectorProducesCandidates:
    EXPORT = {"registered_models": [
        {"name": "credit_pd", "user_id": "a.mehta",
         "latest_versions": [{"version": 3, "run_id": "r-1"}]}]}

    def test_reading_registers_nothing_and_says_so(self, maya):
        out = maya.connectors.read("mlflow", self.EXPORT)
        assert out["count"] == 1
        assert out["registers_anything"] is False

    def test_every_candidate_carries_what_the_source_cannot_say(self, maya):
        out = maya.connectors.read("mlflow", self.EXPORT)
        assert out["candidates"][0]["must_still_be_established"]

    def test_an_unknown_source_is_refused_by_name(self, maya):
        with pytest.raises(Refused) as e:
            maya.connectors.read("sagemaker", {})
        assert e.value.code == "unknown_source"

    def test_describe_names_the_facts_no_source_holds(self, maya):
        assert len(maya.connectors.describe()["not_in_the_source"]) >= 5


class TestASweepIsAdmissibleOrItIsNot:
    GOOD = {"scanner": "euc-sweep", "scope": "drives A and B",
            "recall_known": False,
            "candidates": [{"fingerprint": "sha256:aa", "location": "/a.xlsx",
                            "source": "drive", "confidence": 0.7,
                            "evidence": {"matched": "=LINEST("}}]}

    def test_a_good_sweep_checks_clean(self, maya):
        assert maya.scanner_contract.check(self.GOOD)["admissible"] is True

    def test_a_bad_sweep_reports_every_problem_not_the_first(self, maya):
        out = maya.scanner_contract.check({"candidates": [{}]})
        assert not out["admissible"] and len(out["problems"]) > 3

    def test_ingesting_a_bad_sweep_is_refused_whole(self, maya):
        with pytest.raises(Refused) as e:
            maya.scanner_contract.ingest({**self.GOOD, "candidates": [{}]})
        assert e.value.code == "sweep_does_not_meet_the_contract"

    def test_the_grade_says_recall_is_not_computable(self, maya):
        out = maya.scanner_contract.grade()
        assert out["recall_is_computable"] is False
        assert "did not look at" in out["detail"]


class TestAShareIsNotALogin:
    @pytest.fixture
    def registered(self, maya):
        maya.models.register(
            urn=URN, name="SB PD", model_class="credit.pd.scorecard",
            domain="credit", owner="person/j.okafor",
            legal_entity="LE-US-01", purpose="12m PD at origination")
        return URN

    def test_the_posture_says_what_it_is_not(self, maya):
        out = maya.shares.posture()
        assert out["is_a_portal"] is False
        assert out["establishes_identity"] is False

    def test_a_share_is_created_read_back_and_revoked(self, maya, registered):
        made = maya.shares.share(registered, recipient="PRA",
                                 purpose="2026 examination",
                                 content_digest="sha256:aa", days=14.0)
        assert maya.shares.status(made["reference"])["state"] == "open"
        assert maya.shares.revoke(made["reference"], "withdrawn")["state"] \
            == "revoked"

    def test_a_share_without_a_digest_is_refused(self, maya, registered):
        with pytest.raises(Refused) as e:
            maya.shares.share(registered, recipient="PRA", purpose="exam",
                              content_digest="")
        assert e.value.code == "content_digest_required"

    def test_the_estate_view_answers_what_is_out_there(self, maya, registered):
        maya.shares.share(registered, recipient="ECB", purpose="TRIM",
                          content_digest="sha256:bb")
        assert maya.shares.across_the_estate()["count"] >= 1


class TestRenderingEmitsSourceNotAPdf:
    def test_the_format_list_refuses_pdf_by_name(self, maya):
        out = maya.rendering.formats()
        assert "pdf" in [r["format"] for r in out["not_produced"]]
        assert out["renders_anything"] is False

    def test_asking_for_a_pdf_raises_with_the_reason(self, maya):
        with pytest.raises(Refused) as e:
            maya.rendering.render("no-such-document", "pdf")
        assert e.value.code == "format_not_produced"


class TestTheSdkStillDecidesNothing:
    """Asserted on the source, as the governance suite does. The six subjects
    here are the ones most likely to grow a local rule — a client that decided
    a token looked fine, or that a plugin was safe to import."""

    def test_no_local_verdict_in_the_perimeter_module(self):
        source = (Path(__file__).resolve().parents[1] / "sdk" / "python" /
                  "maya_sdk" / "perimeter.py").read_text()
        for banned in ("import importlib", "entry_points(", "def _verify",
                       "hashlib", "if confidence"):
            assert banned not in source
