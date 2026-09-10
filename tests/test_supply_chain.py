"""What a version is made of, and who built the bytes.

A digest establishes integrity; a signature establishes origin, and only one of
those tells you the artifact came from your own build.
"""
from __future__ import annotations

import pytest

from core.artifacts.bom import (COMPONENT_KINDS, CYCLONEDX, NOT_KNOWN, SPDX,
                                BillOfMaterials)
from core.artifacts.common import ArtifactError
from core.artifacts.provenance import (ABSENT, PREDICATES, STATES, UNVERIFIED,
                                       VERIFIED, ArtifactProvenance)
from tests.conftest import KERNEL, URN

NO_ASSUMPTIONS = {"assumptions": [], "guarantees": [],
                  "on_boundary_violation": "reject"}
STATEMENT = {"predicate": {"builder": {"id": "https://ci.example/builder"}}}


@pytest.fixture
def versioned(registry, a_model):
    registry.create_version(URN, "1.0.0", KERNEL, NO_ASSUMPTIONS,
                            artifact_digest="sha256:" + "a" * 64,
                            actor="d.raman")
    return URN


class TestTheBillIsDerived:
    def test_a_version_yields_its_components(self, registry, versioned):
        out = BillOfMaterials(registry).components(URN, "1.0.0")
        kinds = {c["kind"] for c in out["components"]}
        assert "model" in kinds and "artifact" in kinds

    def test_the_artifact_carries_its_digest(self, registry, versioned):
        out = BillOfMaterials(registry).components(URN, "1.0.0")
        artifact = next(c for c in out["components"] if c["kind"] == "artifact")
        assert artifact["digest"].startswith("sha256:")

    def test_what_it_cannot_know_is_named_in_the_answer(self, registry,
                                                        versioned):
        """A bill of materials whose gaps are invisible is worse than a short
        one, because a scanner reports it as clean."""
        out = BillOfMaterials(registry).components(URN, "1.0.0")
        assert {g["part"] for g in out["not_known"]} == set(NOT_KNOWN)
        assert "a scanner reports it as clean" in out["detail"]

    def test_every_component_kind_maps_to_both_standards(self):
        """Two serialisers over one component list cannot drift."""
        assert all(v["spdx"] and v["cyclonedx"] and v["is"]
                   for v in COMPONENT_KINDS.values())


class TestBothDialectsFromOneDerivation:
    def test_spdx_renders(self, registry, versioned):
        out = BillOfMaterials(registry).render(URN, "1.0.0", SPDX)
        assert out["document"]["spdxVersion"] == "SPDX-3.0"
        assert out["document"]["packages"]

    def test_cyclonedx_renders(self, registry, versioned):
        out = BillOfMaterials(registry).render(URN, "1.0.0", CYCLONEDX)
        assert out["document"]["bomFormat"] == "CycloneDX"
        assert out["document"]["components"]

    def test_both_describe_the_same_components(self, registry, versioned):
        bom = BillOfMaterials(registry)
        spdx = bom.render(URN, "1.0.0", SPDX)["document"]
        cdx = bom.render(URN, "1.0.0", CYCLONEDX)["document"]
        assert len(spdx["packages"]) == len(cdx["components"])

    def test_the_gaps_are_inside_the_document_not_beside_it(self, registry,
                                                            versioned):
        """A consumer reading only the file is a scanner, and it will otherwise
        report this as complete."""
        bom = BillOfMaterials(registry)
        spdx = bom.render(URN, "1.0.0", SPDX)["document"]
        assert any("NOT INCLUDED" in a["comment"]
                   for a in spdx["annotations"])
        cdx = bom.render(URN, "1.0.0", CYCLONEDX)["document"]
        assert any(p["name"].startswith("maya:not-included")
                   for p in cdx["metadata"]["properties"])

    def test_an_unknown_format_is_refused(self, registry, versioned):
        with pytest.raises(ArtifactError) as caught:
            BillOfMaterials(registry).render(URN, "1.0.0", "yaml")
        assert caught.value.code == "unknown_bom_format"


class TestOriginIsNotIntegrity:
    def test_the_three_states_are_three_facts(self):
        """A register that collapsed unverified into absent would let an
        attestation nobody could check read as no attestation at all."""
        assert set(STATES) == {VERIFIED, UNVERIFIED, ABSENT}
        assert "a decoration" in STATES[UNVERIFIED]
        assert "somebody may believe it was" in STATES[ABSENT]

    def test_without_a_verifier_nothing_reads_as_verified(self):
        """An attestation nobody can check is a decoration."""
        out = ArtifactProvenance().verify("sha256:a", STATEMENT)
        assert out["state"] == UNVERIFIED
        assert "no verifier is wired" in out["why"]

    def test_a_wired_verifier_can_verify(self):
        provenance = ArtifactProvenance(verifier=lambda d, s: True)
        assert provenance.verify("sha256:a", STATEMENT)["state"] == VERIFIED

    def test_a_correctly_signed_artifact_from_the_wrong_builder_is_refused(
            self):
        """Exactly the case a digest cannot catch."""
        provenance = ArtifactProvenance(
            verifier=lambda d, s: True,
            trusted=["https://ci.example/other-builder"])
        out = provenance.verify("sha256:a", STATEMENT)
        assert out["state"] == UNVERIFIED
        assert "the wrong builder" in out["why"]

    def test_a_verifier_that_falls_over_does_not_pass_it(self):
        def broken(digest, statement):
            raise RuntimeError("no network")

        out = ArtifactProvenance(verifier=broken).verify("sha256:a", STATEMENT)
        assert out["state"] == UNVERIFIED
        assert "not an artifact something checked and cleared" in out["why"]

    def test_an_attestation_with_no_digest_is_about_nothing(self):
        with pytest.raises(ArtifactError) as caught:
            ArtifactProvenance().attest(artifact_digest=" ",
                                        predicate=PREDICATES[0],
                                        statement=STATEMENT)
        assert caught.value.code == "digest_required"

    def test_an_unknown_predicate_is_refused(self):
        with pytest.raises(ArtifactError) as caught:
            ArtifactProvenance().attest(artifact_digest="sha256:a",
                                        predicate="made-it-up",
                                        statement=STATEMENT)
        assert caught.value.code == "unknown_predicate"

    def test_it_lands_on_the_evidence_chain(self, evidence):
        ArtifactProvenance(evidence=evidence).attest(
            artifact_digest="sha256:a", predicate=PREDICATES[0],
            statement=STATEMENT)
        assert any(n["kind"] == "artifact_provenance_attested"
                   for n in evidence.repo.many())


class TestResolutionIsOffByDefault:
    def test_nothing_is_refused_unless_the_firm_asked(self):
        """A firm that has not wired a verifier in would otherwise find every
        model refusing on the day this shipped."""
        ArtifactProvenance().check_at_resolution("sha256:a", ABSENT)

    def test_a_firm_that_asked_gets_a_refusal(self):
        provenance = ArtifactProvenance(require_verified=True)
        with pytest.raises(ArtifactError) as caught:
            provenance.check_at_resolution("sha256:a", ABSENT)
        assert caught.value.code == "provenance_not_verified"
        assert "the attacker had access to the build" in (
            caught.value.remediation)

    def test_verified_passes_even_when_required(self):
        ArtifactProvenance(require_verified=True).check_at_resolution(
            "sha256:a", VERIFIED)

    def test_the_posture_says_maya_does_not_mint_signatures(self):
        """A governance platform that signed artifacts would hold the key that
        could forge one."""
        out = ArtifactProvenance().posture()
        assert out["verifier_wired"] is False
        assert "could forge one" in out["detail"]
        assert "only the second tells you the artifact came from your own" in (
            out["detail"])
