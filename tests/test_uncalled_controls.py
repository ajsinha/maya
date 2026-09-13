"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The two controls from `docs/11 §6b`, now consulted — and the sweep that found them.

Five times in one session a control turned out to be built, wired, documented
and **never called**: the feature sensitivity facts nothing evaluated, the
recertification reviewer nothing read, a legal hold the deleter never asked
about, and these two. That is a pattern rather than five accidents, so the last
test here is the sweep itself, kept so the sixth is found by a suite rather than
by somebody noticing.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from core.artifacts.common import ArtifactError
from core.artifacts.provenance import ABSENT, UNVERIFIED, VERIFIED
from core.features.common import FeatureError

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestADurableFeaturesetCannotPinSomethingTemporary:
    """`Lifecycle.refuse_if_ephemeral` stated the rule in its own docstring and
    had no caller and no test. Nothing else covered it: `ephemeral` was read
    when *destroying* a feature and never when a durable thing pinned one."""

    def test_pinning_an_ephemeral_feature_is_refused(self, full_features):
        full_features.define("scratch", "customer", "float", "a scratch column",
                        "person/a", ephemeral=True, ttl_days=1)
        full_features.create_view("scratch_view", "customer", "person/a",
                             ["scratch"])
        full_features.define_featureset("durable", "customer", "person/a",
                                   {"scratch": "float"})
        with pytest.raises(FeatureError) as refusal:
            full_features.publish_featureset("durable", {"scratch": "scratch"})
        assert "ephemeral" in str(refusal.value)
        assert "dangles tomorrow" in str(refusal.value)

    def test_a_durable_feature_pins_normally(self, full_features):
        full_features.define("dscr", "customer", "float", "d", "person/a")
        full_features.create_view("fin", "customer", "person/a", ["dscr"])
        full_features.materialise("fin", [
            {"entity_id": "C1", "event_ts": 1.0, "ingest_ts": 2.0,
             "dscr": 1.2}])
        full_features.define_featureset("ok", "customer", "person/a",
                                   {"dscr": "float"})
        assert full_features.publish_featureset("ok", {"dscr": "dscr"})["version"]

    def test_an_ephemeral_featureset_may_pin_an_ephemeral_feature(
            self, full_features):
        """Not an oversight. A scratch set built on scratch data is the case
        the flag exists for; what is refused is durable depending on
        temporary, which is the direction the harm runs in."""
        full_features.define("scratch2", "customer", "float", "s", "person/a",
                        ephemeral=True, ttl_days=1)
        full_features.create_view("scratch2_view", "customer", "person/a",
                                  ["scratch2"])
        full_features.materialise("scratch2_view", [
            {"entity_id": "C1", "event_ts": 1.0, "ingest_ts": 2.0,
             "scratch2": 1.0}])
        full_features.define_featureset("scratch_set", "customer", "person/a",
                                   {"scratch2": "float"}, ephemeral=True,
                                   ttl_days=1)
        assert full_features.publish_featureset("scratch_set",
                                           {"scratch2": "scratch2"})


class TestProvenanceIsCheckedWhereTheFirmAskedForIt:
    """`check_at_resolution` was configurable, published in the posture, and
    had no caller — so `require_verified` bought a flag and no refusal.

    Wiring it needed the verdict to be *somewhere*: provenance was verified,
    written to the evidence chain and forgotten, so the only value the check
    could have been handed was `absent`, and turning the flag on would have
    refused the whole estate."""

    def test_the_verdict_is_remembered(self, provenance):
        provenance.attest(artifact_digest="sha256:" + "a" * 64,
                          predicate="https://slsa.dev/provenance/v1",
                          statement={}, identity="builder-1")
        assert provenance.state_of("sha256:" + "a" * 64) == UNVERIFIED

    def test_an_artifact_nobody_attested_is_absent_not_unverified(self,
                                                                  provenance):
        """A different fact, and only one of them is somebody having tried."""
        assert provenance.state_of("sha256:" + "b" * 64) == ABSENT

    def test_off_by_default_lets_anything_resolve(self, provenance):
        assert provenance.require_verified is False
        provenance.check_at_resolution("sha256:" + "b" * 64, ABSENT)

    def test_on_it_refuses_an_unverified_artifact(self, provenance):
        provenance.require_verified = True
        with pytest.raises(ArtifactError) as refusal:
            provenance.check_at_resolution("sha256:" + "b" * 64, ABSENT)
        assert refusal.value.code == "provenance_not_verified"

    def test_on_it_permits_a_verified_one(self, provenance):
        provenance.require_verified = True
        provenance.check_at_resolution("sha256:" + "c" * 64, VERIFIED)

    def test_resolution_pays_nothing_when_the_control_is_off(self):
        """The flag is checked before the lookup. Resolution is on the serving
        path of everything and `NFR-PERF-002` is written in milliseconds."""
        import inspect

        from core.execution.warrants import WarrantService
        body = inspect.getsource(WarrantService._refuse_unverified_provenance)
        gate = body.index("require_verified")
        assert gate < body.index("state_of"), \
            "the state lookup happens before the flag is checked"


class TestTheSweepThatFoundThem:
    """Kept so the sixth is found by a suite rather than by somebody noticing.

    Gate-shaped methods in `core/` with no call site anywhere in the product.
    Tests do not count: a control exercised only by its own unit test is
    exactly the shape this is looking for.
    """

    #: Judged and allowed, with the reason. Not a suppression list — each of
    #: these was read and is genuinely not a gap.
    ALLOWED = {
        # A predicate on a fibre, not a gate. `kind in self.evidence`.
        "requires_evidence",
        # A convenience wrapper around `may_mutate`, which IS the port the
        # lifecycle gate is consulted through and is called.
        "require_mutable",
    }

    def test_no_gate_shaped_method_is_uncalled(self):
        # Two shapes, not one.
        #
        # The first is a GATE — something that answers whether an act is
        # permitted. The second is a WITHDRAWAL: suspend, revoke, quarantine,
        # disable. `AssistCapabilities.suspend` was built, appended
        # `ai_capability_suspended` to the chain, and had no caller, so
        # `capability_inactive` was unreachable and a misbehaving AI
        # capability could not be stopped at all. This sweep did not see it,
        # because `suspend` is not gate-shaped.
        #
        # Withdrawals are the likeliest of all controls to go unwired: they
        # are written for a day nobody has had yet, so nothing exercises them
        # and nobody notices the button is missing.
        gate = re.compile(
            r"^\s{4}def ((?:refuse|require|check|assert|may|applies|held|"
            r"enforced_by|permits|suspend|quarantine|disable|deactivate)"
            r"\w*)\(", re.M)
        product = "\n".join(
            p.read_text(encoding="utf-8")
            for p in list((ROOT / "core").rglob("*.py"))
            + list((ROOT / "routes").glob("*.py"))
            + [ROOT / "run_maya_web.py"])
        orphans = []
        for path in sorted((ROOT / "core").rglob("*.py")):
            for name in gate.findall(path.read_text(encoding="utf-8")):
                if name in self.ALLOWED:
                    continue
                # A call, or a reference passed as a callable.
                if re.search(rf"(?<!def )\b{re.escape(name)}\b(?!\s*\()",
                             product) or re.search(
                        rf"\.{re.escape(name)}\s*\(", product):
                    continue
                orphans.append(f"{path.relative_to(ROOT)}::{name}")
        assert not orphans, (
            "these read like controls and nothing in the product calls "
            "them:\n    " + "\n    ".join(orphans)
            + "\nWire it, delete it, or add it to ALLOWED with the reason.")


@pytest.fixture
def provenance(db, evidence):
    from core.artifacts.provenance import ArtifactProvenance
    from db import ArtifactProvenanceRepository
    return ArtifactProvenance(evidence=evidence,
                              repo=ArtifactProvenanceRepository(db))
