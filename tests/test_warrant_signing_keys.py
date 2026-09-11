"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A signing key derived from the audience, and what that does and does not buy.

The defect this closes was raised in every review of the platform and answered,
for two years, with *asymmetric signing, not built* — which deferred the whole
problem to a key hierarchy nobody had and left the defect in place meanwhile.
The defect had two halves being treated as one.

**Who can forge** is the operational half. Under one estate-wide secret, an
engine compromised today mints a warrant for any model, any principal, any use.
Deriving the key from the audience confines that to the compromised engine
itself, and needs no asymmetry at all.

**Who can prove authorship to a third party** is the half that does need
public-key cryptography, and it is much rarer: it is showing somebody who is not
the bank that only MAYA could have issued a descriptor. Nobody asked for it.

So the tests below are about containment, and about the platform saying plainly
which of the two it has.
"""
from __future__ import annotations

import pytest

from core.execution.errors import WarrantError
from core.execution.signing import NO_AUDIENCE, WarrantSigner
from tests.api_helpers import login
from tests.conftest import URN

ENGINE_A = "service/engine-a"
ENGINE_B = "service/engine-b"


def _chain_text(client) -> str:
    """Everything the chain holds about this principal, as text.

    Read through the application's own engine rather than an endpoint: there
    is no route that lists raw nodes, deliberately — the chain is read by
    subject, and a general dump would be a way to read every payload in the
    platform with one permission.
    """
    evidence = client.app.state.ctx["evidence"]
    return str(evidence.for_subject("service/engine-a"))


def _warrant(principal, extra=None):
    doc = {"authority": {"principal": principal, "expires_at": 1e12},
           "subject": {"urn": "maya://model/x"}, **(extra or {})}
    return doc


@pytest.fixture
def signer():
    return WarrantSigner("a-real-root-secret", jitter_pct=0)


def _sealed(signer, principal):
    doc = _warrant(principal)
    doc["signature"] = {"alg": signer.ALGORITHM,
                        "key_id": signer.label_for_audience(principal),
                        "value": ""}
    doc["signature"]["value"] = signer.sign(doc)
    return doc


class TestACompromisedEngineForgesOnlyItsOwn:
    def test_two_audiences_do_not_share_a_key(self, signer):
        assert signer.key_for(ENGINE_A) != signer.key_for(ENGINE_B)

    def test_a_warrant_verifies_under_its_own_audience(self, signer):
        assert signer.verify(_sealed(signer, ENGINE_A))

    def test_holding_one_key_does_not_mint_for_another(self, signer):
        """The whole point. An attacker with engine A's key signs a warrant
        naming engine B, and MAYA rejects it — because the audience is read
        from the document, so the key it *should* have been signed under is
        not the key it *was*."""
        import hmac
        from hashlib import sha256

        from db.database import digest as canonical

        stolen = signer.key_for(ENGINE_A)
        forged = _warrant(ENGINE_B)
        forged["signature"] = {"alg": signer.ALGORITHM,
                               "key_id": signer.label_for_audience(ENGINE_B),
                               "value": ""}
        body = {k: v for k, v in forged.items() if k != "signature"}
        forged["signature"]["value"] = hmac.new(
            stolen, canonical(body).encode(), sha256).hexdigest()
        assert not signer.verify(forged)

    def test_redirecting_a_good_warrant_breaks_its_signature(self, signer):
        """An attacker who cannot mint might still try to *re-point* a warrant
        they legitimately hold. That changes the audience, which changes the
        key, so it fails here rather than needing a separate check somebody
        remembered to write."""
        doc = _sealed(signer, ENGINE_A)
        doc["authority"]["principal"] = ENGINE_B
        assert not signer.verify(doc)

    def test_the_derivation_is_one_way(self, signer):
        """An engine holding its own key cannot walk back to the root, so it
        cannot derive anybody else's."""
        derived = signer.key_for(ENGINE_A)
        assert derived != signer._key
        assert signer._key.hex() not in derived.hex()


class TestTheKeyIdIsLegibleAndDisclosesNothing:
    def test_it_names_the_root_the_generation_and_the_audience(self, signer):
        label = signer.label_for_audience(ENGINE_A)
        assert label.startswith(signer.root_label + ".g1.")

    def test_two_audiences_are_distinguishable_without_a_mapping(self, signer):
        assert (signer.label_for_audience(ENGINE_A)
                != signer.label_for_audience(ENGINE_B))

    def test_neither_half_is_the_secret(self, signer):
        label = signer.label_for_audience(ENGINE_A)
        assert "a-real-root-secret" not in label
        assert signer.key_for(ENGINE_A).hex() not in label

    def test_a_generation_bump_re_keys_every_audience(self, signer):
        later = WarrantSigner("a-real-root-secret", jitter_pct=0, generation=2)
        assert later.key_for(ENGINE_A) != signer.key_for(ENGINE_A)
        # And says so in the label, so a warrant issued under the earlier
        # generation is distinguishable rather than mysteriously invalid.
        assert ".g2." in later.label_for_audience(ENGINE_A)
        assert later.root_label == signer.root_label

    def test_an_old_generations_warrant_does_not_silently_verify(self, signer):
        later = WarrantSigner("a-real-root-secret", jitter_pct=0, generation=2)
        assert not later.verify(_sealed(signer, ENGINE_A))


class TestAWarrantWithNoPrincipal:
    def test_it_does_not_fall_back_to_the_root(self, signer):
        """The fallback would restore the estate-wide key silently, and only
        for the malformed cases — which is the worst of both."""
        doc = _warrant("")
        assert signer.audience_of(doc) == NO_AUDIENCE
        assert signer.key_for(NO_AUDIENCE) != signer._key

    def test_asking_for_a_blank_audiences_key_is_refused(self, signer):
        with pytest.raises(WarrantError) as e:
            signer.key_material_for("   ")
        assert e.value.code == "audience_required"
        assert "is how it would come back" in e.value.remediation


class TestThePlatformSaysWhichHalfItHas:
    def test_it_does_not_claim_non_repudiation(self, signer):
        out = signer.posture()
        assert any("third party" in line for line in out["does_not_prove"])
        assert "evidence to the bank" in " ".join(out["does_not_prove"])

    def test_it_states_the_containment_it_does_have(self, signer):
        assert "for ITSELF and for nobody else" in signer.posture()["containment"]

    def test_turning_it_off_is_reported_as_no_containment(self):
        off = WarrantSigner("a-real-root-secret", per_audience=False)
        out = off.posture()
        assert out["containment"].startswith("NONE")
        assert off.label_for_audience(ENGINE_A) == off.root_label

    def test_a_published_key_is_still_named(self):
        assert WarrantSigner("maya-dev-key").posture()["uses_a_published_key"]

    def test_rotation_is_explained_rather_than_implied(self, signer):
        assert "key_generation" in signer.posture()["rotation"]


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        login(client)
        out = client.get("/api/v1/warrant-signing").json()
        assert out["per_audience"] is True
        assert out["does_not_prove"]

    def test_an_engine_collects_its_own_key(self, client, people):
        out = client.post("/api/v1/warrant-signing/key",
                          params={"audience": "d.raman"},
                          auth=people["d.raman"])
        assert out.status_code == 200
        body = out.json()
        assert body["key"] and body["audience"] == "d.raman"
        assert "whether you stored this safely" in body["maya_cannot_see"]

    def test_collecting_somebody_elses_needs_an_administrator(self, client,
                                                              people):
        refused = client.post("/api/v1/warrant-signing/key",
                              params={"audience": "service/engine-a"},
                              auth=people["d.raman"])
        assert refused.status_code == 403

    def test_an_administrator_provisions_a_deployment(self, client):
        out = client.post("/api/v1/warrant-signing/key",
                          params={"audience": "service/engine-a"})
        assert out.status_code == 200 and out.json()["key"]

    def test_a_blank_audience_is_refused_by_name(self, client):
        out = client.post("/api/v1/warrant-signing/key",
                          params={"audience": "  "})
        assert out.status_code == 422
        assert "audience_required" in out.text

    def test_the_disclosure_is_on_the_chain(self, client):
        """A secret leaving the platform is a governance act, which is why it
        is a POST that records rather than a GET somebody's proxy might
        cache."""
        client.post("/api/v1/warrant-signing/key",
                    params={"audience": "service/engine-a"})
        blob = _chain_text(client)
        assert "warrant_signing_key_disclosed" in blob
        assert "service/engine-a" in blob

    def test_the_disclosure_does_not_record_the_key(self, client):
        """The record says a key was handed over, to whom and under which
        generation. Writing the key itself into an append-only chain would
        publish the secret to every holder of `evidence:read` — which is the
        same defect the key id was fixed for."""
        out = client.post("/api/v1/warrant-signing/key",
                          params={"audience": "service/engine-a"}).json()
        assert out["key"] not in _chain_text(client)

    def test_a_resolved_descriptor_carries_its_audiences_key_id(
            self, in_service):
        """The end of the chain: a descriptor an engine actually receives is
        sealed under that engine's own key, and says so in `key_id`."""
        descriptor = in_service.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination",
            "declared_use": "origination_decision"}).json()
        assert ".g1." in descriptor["signature"]["key_id"]
        # And it is NOT the root's label, which is what a shared secret would
        # have written into every descriptor in the estate.
        signer = in_service.app.state.ctx["warrants"].signer
        assert descriptor["signature"]["key_id"] != signer.root_label

    def test_the_engine_that_holds_the_key_can_verify_what_it_receives(
            self, in_service):
        """The property the disclosure exists for. An engine collects its own
        key, receives a descriptor, and checks it locally — without ever
        holding anything that signs for another principal."""
        import hmac
        from hashlib import sha256

        from db.database import digest as canonical

        handed = in_service.post("/api/v1/warrant-signing/key",
                                 params={"audience": "svc/origination"}).json()
        descriptor = in_service.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination",
            "declared_use": "origination_decision"}).json()
        body = {k: v for k, v in descriptor.items() if k != "signature"}
        recomputed = hmac.new(bytes.fromhex(handed["key"]),
                              canonical(body).encode(), sha256).hexdigest()
        assert recomputed == descriptor["signature"]["value"]

        # And the same engine cannot check — or forge — somebody else's.
        other = in_service.post("/api/v1/warrant-signing/key",
                                params={"audience": "svc/pricing"}).json()
        assert other["key"] != handed["key"]
