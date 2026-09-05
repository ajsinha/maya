"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Everything about one model, for somebody who will not be given a login.

A supervisor, an internal auditor, an acquirer's diligence team. They cannot
query the platform, cannot take its word for anything, and will read the result
months later — and every property tested here follows from one of those three.

The two that matter most are not about completeness.

**A gap is written down.** A pack that silently omits what it could not gather
reads as complete, and the reader has no way to tell a thin model from a thin
export. That is the failure this whole discipline exists to prevent, and it is
the one an export is most likely to commit, because the omission is invisible
from the inside.

**The content digest excludes the manifest.** Otherwise every pack differs from
every other pack — the manifest carries the moment it was cut — and the one
comparison a reader actually wants, *has anything changed since last time*,
becomes a hundred-file diff.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from core.export import MANIFEST, PACK_VERSION, sha256_of

URN = "maya://model/credit.pd.smallbiz"


def open_pack(body: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(body))


@pytest.fixture
def pack(client, registered):
    r = client.post(f"/api/v1/export-packs/credit.pd.smallbiz")
    assert r.status_code == 200, r.text
    return r


class TestThePackIsSelfContained:
    def test_it_is_a_zip_with_the_parts_a_reader_needs(self, pack):
        names = set(open_pack(pack.content).namelist())
        assert MANIFEST in names and "README.md" in names and "gaps.md" in names
        assert "model.json" in names and "versions.json" in names
        assert "evidence/chain.json" in names
        assert any(n.startswith("documents/") for n in names)

    def test_the_readme_explains_how_to_verify_it(self, pack):
        readme = open_pack(pack.content).read("README.md").decode()
        assert "content digest" in readme
        assert "gaps.md" in readme, \
            "a reader told nothing about the gaps file will not open it"

    def test_the_register_state_travels_with_the_documents(self, pack):
        model = json.loads(open_pack(pack.content).read("model.json"))
        assert model["model"]["urn"] == URN
        assert "assessment" in model and "lifecycle" in model

    def test_the_evidence_chain_and_its_verification_are_both_there(self, pack):
        chain = json.loads(open_pack(pack.content).read("evidence/chain.json"))
        assert chain["nodes"], "a pack with no evidence supports nothing"
        assert "verification" in chain


class TestEveryFileIsDigested:
    def test_the_manifest_lists_every_member_with_its_hash(self, pack):
        archive = open_pack(pack.content)
        manifest = json.loads(archive.read(MANIFEST))
        listed = {f["name"]: f["digest"] for f in manifest["files"]}
        members = set(archive.namelist()) - {MANIFEST}
        assert members == set(listed), \
            "a file in the pack that the manifest does not list cannot be checked"
        for name, digest in listed.items():
            assert sha256_of(archive.read(name)) == digest, name

    def test_the_manifest_says_which_shape_it_is(self, pack):
        manifest = json.loads(open_pack(pack.content).read(MANIFEST))
        assert manifest["pack_version"] == PACK_VERSION
        assert manifest["contents"], \
            "a reader who does not know what should be here cannot tell what is missing"

    def test_the_chain_head_is_recorded(self, pack):
        """So 'has the record moved since this was cut' has an answer rather
        than an assurance."""
        chain = json.loads(open_pack(pack.content).read(MANIFEST))["chain"]
        assert chain["head_seq"] and chain["head_hash"]

    def test_the_response_carries_both_digests(self, pack):
        assert pack.headers["x-pack-digest"].startswith("sha256:")
        assert pack.headers["x-pack-content-digest"].startswith("sha256:")


class TestTheContentDigestIsTheComparison:
    def test_two_packs_of_the_same_state_agree(self, client, registered):
        """The whole point. The manifest carries the moment it was cut, so a
        digest that included it would differ every time and answer nothing."""
        first = client.post("/api/v1/export-packs/credit.pd.smallbiz")
        second = client.post("/api/v1/export-packs/credit.pd.smallbiz")
        assert (first.headers["x-pack-content-digest"]
                == second.headers["x-pack-content-digest"])

    def test_it_moves_when_the_model_does(self, client, registered, people):
        before = client.post("/api/v1/export-packs/credit.pd.smallbiz")
        raised = client.post("/api/v1/findings", auth=people["a.mehta"], json={
            "urn": URN, "title": "Documentation is thin", "severity": "Medium",
            "owner": "person/j.okafor", "category": "documentation",
            "description": "the methodology section cites nothing"})
        assert raised.status_code == 201, raised.text
        after = client.post("/api/v1/export-packs/credit.pd.smallbiz")
        assert (before.headers["x-pack-content-digest"]
                != after.headers["x-pack-content-digest"])

    def test_the_manifest_endpoint_answers_without_the_bytes(self, client, registered):
        """Comparing against the last pack should not require moving a hundred
        megabytes to find out that nothing has changed."""
        body = client.get("/api/v1/export-packs/credit.pd.smallbiz/manifest").json()
        full = client.post("/api/v1/export-packs/credit.pd.smallbiz")
        assert body["content_digest"] == full.headers["x-pack-content-digest"]


class TestAGapIsRecordedRatherThanOmitted:
    def test_the_gaps_file_is_always_present(self, pack):
        """Present even when empty, so a reader learns the file exists on a
        clean model and looks for it on a thin one."""
        gaps = open_pack(pack.content).read("gaps.md").decode()
        assert gaps.startswith("# Gaps")

    def test_an_unfillable_document_section_is_named(self, client, registered):
        gaps = open_pack(
            client.post("/api/v1/export-packs/credit.pd.smallbiz").content
        ).read("gaps.md").decode()
        manifest = json.loads(open_pack(
            client.post("/api/v1/export-packs/credit.pd.smallbiz").content
        ).read(MANIFEST))
        if manifest["gaps"]:
            assert "|" in gaps, "gaps are listed with their reason, not counted"
            assert "§" in gaps or "attachments" in gaps or "evidence" in gaps

    def test_an_unknown_document_kind_becomes_a_gap_rather_than_a_failure(
            self, client, registered):
        """A pack that died because one document would not compile gives the
        reader nothing; a pack that records it gives them the fact."""
        r = client.post("/api/v1/export-packs/credit.pd.smallbiz",
                        params={"documents": "model_card,not_a_kind"})
        assert r.status_code == 200
        gaps = open_pack(r.content).read("gaps.md").decode()
        assert "not_a_kind" in gaps
        assert "documents/model_card.md" in set(open_pack(r.content).namelist())


class TestPersonalDataIsNotReMaterialised:
    def test_a_flagged_node_carries_its_pointer_and_says_so(self, client,
                                                            registered, evidence):
        """Resolving it here would put personal data into a file an erasure
        request cannot reach, which defeats L-18 rather than exporting it."""
        model = client.get("/api/v1/models/credit.pd.smallbiz").json()["model"]
        ctx = client.app.state.ctx
        ctx["evidence"].append("subject_access_request", "model", model["id"],
                               {"borrower": "a real name"}, personal_data=True,
                               actor="admin")
        body = client.post("/api/v1/export-packs/credit.pd.smallbiz").content
        chain = json.loads(open_pack(body).read("evidence/chain.json"))
        flagged = [n for n in chain["nodes"] if n.get("contains_personal_data")]
        assert flagged, "the fixture did not produce a flagged node"
        for node in flagged:
            assert node["payload"] == {} or node["payload"].get("redacted") is True
            assert "a real name" not in json.dumps(node)
        assert "personal data" in open_pack(body).read("gaps.md").decode()


class TestScope:
    def test_cutting_a_pack_is_recorded_as_a_governance_act(self, client, registered):
        """Handing a complete record of a model to somebody outside is itself an
        act, and who took a copy is what an auditor asks about later.

        Recorded against the PACK rather than the model, deliberately: against
        the model it would land inside the next pack's own evidence segment, and
        every pack would differ from the one before it for no reason except that
        somebody had taken one.
        """
        r = client.post("/api/v1/export-packs/credit.pd.smallbiz")
        digest = r.headers["x-pack-content-digest"]
        ctx = client.app.state.ctx
        nodes = ctx["evidence"].for_subjects([digest])
        assert [n["kind"] for n in nodes] == ["export_pack_cut"]
        assert nodes[0]["payload"]["urn"] == URN
        assert nodes[0]["recorded_by"] == "admin"

    def test_a_model_that_does_not_exist_is_a_404(self, client):
        assert client.post("/api/v1/export-packs/nothing.here").status_code == 404

    def test_an_anonymous_caller_gets_nothing(self, client):
        r = client.post("/api/v1/export-packs/credit.pd.smallbiz", auth=None,
                        headers={"Authorization": ""})
        assert r.status_code in (401, 403, 404)


class TestTheShape:
    def test_members_are_ordered_and_stamped_so_two_packs_differ_only_in_content(
            self, client, registered):
        names = open_pack(
            client.post("/api/v1/export-packs/credit.pd.smallbiz").content).namelist()
        assert names == sorted(names), \
            "member order following a dict's insertion order is a diff nobody can read"

    def test_what_a_pack_contains_is_published(self, client):
        body = client.get("/api/v1/export-packs").json()
        assert body["pack_version"] == PACK_VERSION
        assert "gaps.md" in body["contents"]
        assert set(body["documents"]) == set(body["document_kinds"]), \
            "a pack cut for one reader is a pack the next reader has to ask for again"

    def test_attachments_can_be_left_out_for_size(self, client, registered):
        r = client.post("/api/v1/export-packs/credit.pd.smallbiz",
                        params={"attachments": False})
        assert r.status_code == 200
        assert not any(n.startswith("attachments/")
                       for n in open_pack(r.content).namelist())
