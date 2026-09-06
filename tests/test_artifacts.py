"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Where a serialised model actually lives.

A version could always NAME an artifact, and the engine verified its digest
before loading. What it could not do was HOLD one: the bytes had to arrive on
disk out of band, so the single thing the whole chain of custody rests on came
by a route the platform had no view of, and `artifact_uri` was whatever string
somebody typed.

This is the answer to "how do you govern a neural network" — the same way as a
regression. `P` is the weights; twenty million numbers are an artifact rather
than a record, and the register holds the address, the format, the featureset
version they were trained on and the digest the engine re-checks before loading.
"""
from __future__ import annotations

import io

import pytest

from core.artifacts import ArtifactError, ArtifactStore

WEIGHTS = b"\x08\x01\x12\x0connx-ish" + b"\x00\xff" * 5000


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path / "artifacts")


class TestTheDigestIsTheAddress:
    def test_an_artifact_is_stored_under_its_own_hash(self, store):
        out = store.put(io.BytesIO(WEIGHTS), "onnx")
        assert out["digest"].startswith("sha256:") and len(out["digest"]) == 71
        assert out["size"] == len(WEIGHTS)
        assert out["uri"] == f"maya://artifact/{out['digest']}"

    def test_storing_it_twice_stores_it_once(self, store):
        """Which matters: a challenger differing from its champion by a
        configuration rather than a file should not double the storage."""
        first = store.put(io.BytesIO(WEIGHTS), "onnx")
        second = store.put(io.BytesIO(WEIGHTS), "onnx")
        assert first["digest"] == second["digest"]
        assert second["stored"] is False
        assert store.usage()["artifacts"] == 1

    def test_a_declared_digest_is_checked_rather_than_trusted(self, store):
        """The difference between 'we have the file you meant' and 'we have a
        file'. A truncated upload is refused, not stored under the address of
        whatever arrived."""
        with pytest.raises(ArtifactError) as exc:
            store.put(io.BytesIO(WEIGHTS), "onnx",
                      declared_digest="sha256:" + "0" * 64)
        assert exc.value.code == "artifact_digest_mismatch"

    def test_a_correct_declared_digest_is_accepted(self, store):
        out = store.put(io.BytesIO(WEIGHTS), "onnx")
        again = store.put(io.BytesIO(WEIGHTS), "onnx",
                          declared_digest=out["digest"])
        assert again["digest"] == out["digest"]

    def test_an_unknown_format_is_refused_by_name(self, store):
        """The format decides how the artifact is loaded, and working it out at
        load time is how a pickle gets deserialised in a control plane."""
        with pytest.raises(ArtifactError) as exc:
            store.put(io.BytesIO(WEIGHTS), "pickle")
        assert exc.value.code == "unknown_format"

    def test_an_empty_upload_is_refused(self, store):
        with pytest.raises(ArtifactError, match="empty"):
            store.put(io.BytesIO(b""), "onnx")

    def test_a_malformed_address_is_refused_rather_than_searched_for(self, store):
        with pytest.raises(ArtifactError) as exc:
            store.require("../../etc/passwd")
        assert exc.value.code == "malformed_digest"


class TestReadingItBack:
    def test_the_bytes_come_back_exactly(self, store):
        out = store.put(io.BytesIO(WEIGHTS), "onnx")
        assert b"".join(store.stream(out["digest"])) == WEIGHTS

    def test_verification_re_derives_the_hash(self, store):
        """Content addressing makes tampering hard rather than impossible — the
        filesystem is still a filesystem."""
        out = store.put(io.BytesIO(WEIGHTS), "onnx")
        assert store.verify(out["digest"])["intact"] is True

    def test_tampering_is_caught(self, store):
        out = store.put(io.BytesIO(WEIGHTS), "onnx")
        path = store.require(out["digest"])
        path.write_bytes(WEIGHTS + b"extra")
        report = store.verify(out["digest"])
        assert report["intact"] is False
        assert "do not run this artifact" in report["detail"]

    def test_an_absent_artifact_says_so(self, store):
        with pytest.raises(ArtifactError) as exc:
            store.require("sha256:" + "a" * 64)
        assert exc.value.code == "artifact_not_stored"


class TestFormatsThatRunCodeAreNamedAsSuch:
    def test_a_graph_does_not_execute_on_load(self, store):
        assert store.put(io.BytesIO(WEIGHTS), "onnx")["executes_on_load"] is False

    def test_a_torchscript_archive_does(self, store):
        """Which is why it loads in the sandbox and nowhere else. An engine
        should not be inferring this from a file extension."""
        out = store.put(io.BytesIO(WEIGHTS), "torchscript")
        assert out["executes_on_load"] is True
        assert "sandbox" in out["detail"]


class TestOverTheApi:
    def test_an_artifact_can_be_uploaded_and_fetched(self, client, people):
        client.post("/api/v1/principals", json={
            "username": "d.raman", "display_name": "D", "roles": ["model_developer"],
            "password": "dev-pw"}) if False else None
        r = client.post("/api/v1/artifacts?format=onnx", content=WEIGHTS,
                        headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 201, r.text
        digest = r.json()["digest"]
        back = client.get(f"/api/v1/artifacts/{digest}")
        assert back.status_code == 200 and back.content == WEIGHTS

    def test_the_formats_are_published_with_what_they_mean(self, client):
        body = client.get("/api/v1/artifact-formats").json()["formats"]
        by = {f["format"]: f for f in body}
        assert by["safetensors"]["executes_on_load"] is False
        assert by["torchscript"]["executes_on_load"] is True
        assert all(f["means"] for f in body)

    def test_the_store_can_be_asked_what_it_holds(self, client):
        client.post("/api/v1/artifacts?format=onnx", content=WEIGHTS)
        usage = client.get("/api/v1/artifact-usage").json()
        assert usage["artifacts"] >= 1 and usage["bytes"] >= len(WEIGHTS)


class TestTheVersionResolvesWhatMayaHolds:
    """A digest naming bytes MAYA holds is resolved, not taken on faith."""

    def test_a_version_gets_its_uri_and_size_from_the_store(self, client):
        up = client.post("/api/v1/artifacts?format=onnx", content=WEIGHTS).json()
        client.post("/api/v1/models", json={
            "urn": "maya://model/fraud.card.nn", "name": "Fraud NN",
            "model_class": "fraud.classifier", "domain": "operations",
            "owner": "person/admin", "legal_entity": "LE-1",
            "purpose": "screening"})
        r = client.post("/api/v1/models/fraud.card.nn/versions", json={
            "semver": "1.0.0", "artifact_digest": up["digest"],
            "kernel": {"parameter_kind": "learned_weights",
                       "fit_procedure": "train", "runtime": "onnx",
                       "entry": {"graph": "fraud.onnx"}}})
        assert r.status_code == 201, r.text
        version = r.json()
        assert version["artifact_uri"] == up["uri"]
        assert version["artifact_size"] == len(WEIGHTS)

    def test_a_digest_maya_does_not_hold_is_recorded_rather_than_refused(self, client):
        """Plenty of checkpoints live elsewhere and are named here so the engine
        can verify them on load. That is a different state, not an error."""
        client.post("/api/v1/models", json={
            "urn": "maya://model/vendor.score", "name": "Vendor",
            "model_class": "vendor.score", "domain": "credit",
            "owner": "person/admin", "legal_entity": "LE-1", "purpose": "x"})
        r = client.post("/api/v1/models/vendor.score/versions", json={
            "semver": "1.0.0", "artifact_digest": "sha256:" + "b" * 64,
            "artifact_uri": "s3://vendor/score.onnx",
            "kernel": {"parameter_kind": "opaque", "fit_procedure": "none"}})
        assert r.status_code == 201
        assert r.json()["artifact_uri"] == "s3://vendor/score.onnx"
        assert r.json()["artifact_size"] is None


class TestTheWarrantSaysWhatTheArtifactIs:
    def test_it_carries_size_format_and_where_to_fetch(self, client):
        from core.execution.builder import WarrantBuilder
        version = {"artifact_uri": "maya://artifact/sha256:" + "c" * 64,
                   "artifact_digest": "sha256:" + "c" * 64,
                   "artifact_size": 81443712}
        out = WarrantBuilder._realisation(
            version, {"runtime": "onnx", "artifact_format": "onnx",
                      "entry": {"graph": "g.onnx"}})
        art = out["artifact"]
        assert art["size"] == 81443712
        assert art["executes_on_load"] is False
        assert art["held_by_maya"] is True
        assert art["fetch"] == "/api/v1/artifacts/sha256:" + "c" * 64

    def test_a_format_that_runs_code_is_named_as_such(self, client):
        from core.execution.builder import WarrantBuilder
        out = WarrantBuilder._realisation(
            {"artifact_uri": "s3://x/m.pt", "artifact_digest": "sha256:" + "d" * 64},
            {"runtime": "python.callable", "artifact_format": "torchscript"})
        assert out["artifact"]["executes_on_load"] is True
        assert out["artifact"]["held_by_maya"] is False
        assert "fetch" not in out["artifact"], (
            "MAYA does not hold it, so offering a fetch path would be a lie")


class TestADigestIsAContentAddressOrItIsNotRecorded:
    """`/models/new` says a location with no digest cannot be checked.

    True — and so was the case it did not mention. The register accepted
    whatever string arrived: `sha256:not-a-digest-at-all` went onto a version
    with a 201. The store refuses a malformed address when it goes looking for
    the bytes, so the versions where this was never noticed are exactly the ones
    whose artifact lives in somebody else's engine — the opaque vendor models,
    where the digest is the entire control and `L-W12` rests on it.
    """

    @pytest.fixture
    def probe(self, client):
        """A model to hang versions off, over the API as a caller would."""
        client.post("/api/v1/models", json={
            "urn": "maya://model/probe.digest", "name": "Probe",
            "model_class": "probe", "domain": "credit",
            "owner": "person/admin", "legal_entity": "LE-1", "purpose": "x"})
        return client

    def _version(self, client, semver, kernel, **kw):
        return client.post("/api/v1/models/probe.digest/versions", json={
            "semver": semver, "kernel": kernel, **kw})

    def test_a_malformed_digest_is_refused(self, probe):
        r = self._version(probe, "9.0.0",
                          {"parameter_kind": "opaque", "fit_procedure": "none"},
                          artifact_digest="sha256:not-a-digest-at-all")
        assert r.status_code == 409, r.text
        assert "content address" in r.text

    def test_a_short_digest_is_refused(self, probe):
        r = self._version(probe, "9.0.1",
                          {"parameter_kind": "opaque", "fit_procedure": "none"},
                          artifact_digest="sha256:9f2c")
        assert r.status_code == 409 and "content address" in r.text

    def test_no_digest_at_all_is_accepted(self, probe):
        """A version with no digest is honest. One carrying a digest nothing can
        resolve is not, which is the distinction the refusal draws."""
        r = self._version(probe, "9.0.2",
                          {"parameter_kind": "none", "fit_procedure": "none"})
        assert r.status_code == 201 and r.json()["artifact_digest"] is None

    def test_a_real_content_address_is_accepted(self, probe):
        r = self._version(probe, "9.0.3",
                          {"parameter_kind": "opaque", "fit_procedure": "none"},
                          artifact_digest="sha256:" + "e" * 64)
        assert r.status_code == 201
        assert r.json()["artifact_digest"] == "sha256:" + "e" * 64

    def test_the_check_is_the_store_s_own(self):
        """One definition of a content address, in one place — or the register
        and the store disagree about what they are both holding."""
        from core.artifacts import is_content_address
        assert is_content_address("sha256:" + "f" * 64)
        assert not is_content_address("sha256:" + "g" * 64)   # not hexadecimal
        assert not is_content_address("md5:" + "a" * 64)
        assert not is_content_address(None)


class TestAKernelKeyNobodyReadsIsRefused:
    """`kernel` was a free-form dict, so a key put in the wrong place vanished.

    A developer who wrote `artifact_digest` inside `kernel` — beside `runtime`,
    `entry` and the schemas, which is exactly where it looks like it belongs —
    got a 201 and a `descriptor_only` version with no artifact bound to it.
    Nothing was wrong with the request and nothing was said.
    """

    @pytest.fixture
    def probe(self, client):
        client.post("/api/v1/models", json={
            "urn": "maya://model/probe.kernel", "name": "Probe",
            "model_class": "probe", "domain": "credit",
            "owner": "person/admin", "legal_entity": "LE-1", "purpose": "x"})
        return client

    def _version(self, client, semver, kernel):
        return client.post("/api/v1/models/probe.kernel/versions",
                           json={"semver": semver, "kernel": kernel})

    def test_a_misplaced_artifact_digest_is_refused_and_says_where_it_goes(
            self, probe):
        r = self._version(probe, "9.1.0", {
            "parameter_kind": "opaque", "fit_procedure": "none",
            "artifact_digest": "sha256:" + "a" * 64})
        assert r.status_code == 409 and "artifact_digest" in r.text

    def test_a_typo_is_refused(self, probe):
        r = self._version(probe, "9.1.1",
                          {"parameter_knid": "opaque", "fit_procedure": "none"})
        assert r.status_code == 409 and "parameter_knid" in r.text

    def test_every_key_the_code_reads_is_admitted(self, probe):
        """The whole vocabulary, so the refusal cannot become a wall."""
        r = self._version(probe, "9.1.2", {
            "parameter_kind": "learned_weights", "fit_procedure": "train",
            "output_kind": "point_estimate", "adaptive": False,
            "deterministic": True, "input_schema": [], "output_schema": [],
            "artifact_format": "onnx", "runtime": "onnxruntime",
            "entry": {"graph": "model.onnx"}, "environment": {},
            "seed": 11, "descriptor_only": False})
        assert r.status_code == 201, r.text
        assert r.json()["semver"] == "9.1.2"


class TestTheFormatIsCheckedAgainstTheBytes:
    """The format was a claim from beginning to end.

    The uploader named it on `POST /artifacts`, the version's kernel named it
    again, and nothing ever opened the file. It is not a label: it decides which
    runtime loads the artifact, and `EXECUTES_ON_LOAD` exists because two of
    these formats run somebody's code on open. An artifact declared `onnx` and
    actually a TorchScript archive is a request to run code outside the sandbox
    that isolates it, granted on the uploader's word.
    """

    ZIP = b"PK\x03\x04" + b"\x00" * 64          # a TorchScript archive is a ZIP
    GZIP = b"\x1f\x8b\x08\x00" + b"\x00" * 64
    GGUF = b"GGUF" + b"\x00" * 64

    @staticmethod
    def _put(store, payload, fmt):
        import io
        return store.put(io.BytesIO(payload), fmt)

    def test_a_zip_uploaded_as_onnx_is_refused(self, store):
        import pytest

        from core.artifacts import ArtifactError

        with pytest.raises(ArtifactError) as refusal:
            self._put(store, self.ZIP, "onnx")
        assert refusal.value.code == "artifact_format_mismatch"
        assert "torchscript" in str(refusal.value), "name what it actually is"

    def test_the_same_bytes_stored_as_what_they_are_go_in(self, store):
        assert self._put(store, self.ZIP, "torchscript")["format"] == "torchscript"

    def test_a_tarball_uploaded_as_safetensors_is_refused(self, store):
        import pytest

        from core.artifacts import ArtifactError

        with pytest.raises(ArtifactError):
            self._put(store, self.GZIP, "safetensors")

    def test_gguf_says_its_own_name(self, store):
        import pytest

        from core.artifacts import ArtifactError

        with pytest.raises(ArtifactError):
            self._put(store, self.GGUF, "json")

    def test_bytes_the_sniffer_cannot_place_are_stored_as_declared(self, store):
        """The whole design constraint. ONNX is protobuf and protobuf has no
        magic number, so an ONNX graph is unplaceable — and a sniffer that
        guessed from its first byte refused a correct TorchScript upload within
        a minute of being written. Only a positive contradiction refuses."""
        assert self._put(store, b"\x08\x07\x12\x04arbitrary", "onnx")["format"] \
            == "onnx"

    def test_pfa_and_json_are_not_reported_as_contradicting(self):
        """Both are JSON documents. Telling them apart by their keys would be
        inventing certainty, so they are treated as indistinguishable."""
        from core.artifacts.sniff import contradicts, looks_like

        assert looks_like(b'{"input": {}}') == "json"
        assert not contradicts("pfa", "json")
        assert contradicts("pfa", "gguf")


class TestAVersionMayNotRenameTheArtifactsFormat:
    """The store filled the format in when the kernel was silent and BELIEVED
    the kernel when it was not, so the two could disagree about the same bytes
    and the version's word won. `builder.py` picks the runtime from the kernel's
    declaration, so a version declaring `onnx` over an artifact stored as
    `torchscript` routed code out of the sandbox that exists to contain it.
    """

    def test_a_disagreement_with_the_store_is_refused(self, registry, store):
        import io

        import pytest

        from core.registry.common import RegistryError

        registry.attach_artifacts(store)
        stored = store.put(io.BytesIO(b"PK\x03\x04" + b"\x00" * 64),
                           "torchscript")
        urn = "maya://model/fmt.disagree"
        registry.register(urn, "Disagree", "credit", "retail", "person/o",
                          "LE-US-01", "format disagreement")
        with pytest.raises(RegistryError, match="artifact_format"):
            registry.create_version(urn, "1.0.0", {
                "parameter_kind": "opaque", "fit_procedure": "train",
                "artifact_format": "onnx",
                "input_schema": [{"name": "x", "dtype": "numeric"}],
                "output_schema": [{"name": "y", "dtype": "numeric"}]},
                artifact_digest=stored["digest"])

    def test_agreeing_with_the_store_is_fine(self, registry, store):
        import io

        registry.attach_artifacts(store)
        stored = store.put(io.BytesIO(b"PK\x03\x04" + b"\x00" * 64),
                           "torchscript")
        urn = "maya://model/fmt.agree"
        registry.register(urn, "Agree", "credit", "retail", "person/o",
                          "LE-US-01", "format agreement")
        version = registry.create_version(urn, "1.0.0", {
            "parameter_kind": "opaque", "fit_procedure": "train",
            "artifact_format": "torchscript",
            "input_schema": [{"name": "x", "dtype": "numeric"}],
            "output_schema": [{"name": "y", "dtype": "numeric"}]},
            artifact_digest=stored["digest"])
        assert version["manifest"]["kernel"]["artifact_format"] == "torchscript"
