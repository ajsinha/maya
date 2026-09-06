"""
MAYA — the evidence chain's anchor: heads written outside the database.

The chain is hash-linked, so a node cannot be altered without breaking every
link after it — *provided somebody checks*. Verification compared the chain
against itself, and the checkpoint is an ordinary table advanced by the same
process that verifies. An attacker with write access therefore had everything
needed: rewrite the nodes, recompute the links, move the checkpoint. Every
subsequent verification passes, continuously, and reports success.

These tests are mostly about that one scenario, because it is the only one that
distinguishes tamper evidence from self-consistency.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from core.evidence.anchor import AnchorError, ChainAnchor


@pytest.fixture
def anchor(tmp_path):
    return ChainAnchor(tmp_path / "worm")


class TestAnAnchorIsWrittenOnce:

    def test_an_empty_root_says_the_chain_is_self_certified(self, anchor):
        """Not a pass. With nothing written down there is nothing to disagree
        with, and reporting that as agreement would be the same error the
        anchor exists to correct."""
        report = anchor.verify(lambda seq: None)
        assert report["agrees"] == 1 and report["anchored"] == 0
        assert "self-certified" in report["detail"]

    def test_writing_the_same_head_twice_writes_nothing(self, anchor):
        """The scheduler job must be idempotent: running it twice is not an
        incident."""
        anchor.anchor(10, "sha256:aaa")
        assert anchor.anchor(10, "sha256:aaa")["written"] == 0
        assert len(anchor.anchors()) == 1

    def test_writing_a_different_head_at_the_same_sequence_is_refused(self, anchor):
        """Not a conflict to resolve — the observation the anchor exists to
        make."""
        anchor.anchor(10, "sha256:aaa")
        with pytest.raises(AnchorError, match="rewritten behind the anchor") as exc:
            anchor.anchor(10, "sha256:bbb")
        assert exc.value.code == "anchor_disagreement"
        assert "security incident" in exc.value.remediation

    def test_an_anchor_is_read_only_once_written(self, anchor):
        anchor.anchor(10, "sha256:aaa")
        path = next(pathlib.Path(anchor.root).glob("*.anchor"))
        assert not path.stat().st_mode & 0o200

    def test_an_unreadable_anchor_is_not_treated_as_absent(self, anchor):
        """An anchor that cannot be read cannot exonerate the chain. Skipping it
        would make deleting one the way to pass."""
        anchor.anchor(10, "sha256:aaa")
        path = next(pathlib.Path(anchor.root).glob("*.anchor"))
        path.chmod(0o600)
        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(AnchorError, match="cannot be read"):
            anchor.anchors()

    def test_a_partial_write_never_becomes_an_anchor(self, anchor):
        """Written to a temporary name and moved, so a crash mid-write cannot
        leave a short file that reads as a valid anchor for the wrong hash."""
        anchor.anchor(10, "sha256:aaa")
        stray = pathlib.Path(anchor.root) / "000000000011.writing"
        stray.write_text('{"seq": 11', encoding="utf-8")
        assert [a["seq"] for a in anchor.anchors()] == [10]


class TestTheAnchorCatchesWhatSelfVerificationCannot:

    def test_a_chain_that_agrees_is_reported_as_agreeing(self, anchor):
        anchor.anchor(10, "sha256:aaa")
        anchor.anchor(20, "sha256:bbb")
        chain = {10: "sha256:aaa", 20: "sha256:bbb"}
        report = anchor.verify(chain.get)
        assert report["agrees"] == 1 and report["checked"] == 2

    def test_a_rewritten_node_is_caught(self, anchor):
        anchor.anchor(10, "sha256:aaa")
        report = anchor.verify({10: "sha256:REWRITTEN"}.get)
        assert report["agrees"] == 0
        assert report["broken"][0]["seq"] == 10
        assert "changed since it was anchored" in report["broken"][0]["why"]

    def test_a_shortened_chain_is_caught(self, anchor):
        """An append-only chain cannot get shorter, so a chain that no longer
        reaches an anchored sequence has been truncated."""
        anchor.anchor(10, "sha256:aaa")
        report = anchor.verify(lambda seq: None)
        assert report["agrees"] == 0
        assert "cannot get shorter" in report["broken"][0]["why"]

    def test_it_sees_nothing_before_the_first_anchor(self, anchor):
        """Stated rather than left to be discovered: the control begins when
        anchoring begins. Tampering before that leaves nothing to disagree
        with."""
        anchor.anchor(100, "sha256:aaa")
        report = anchor.verify({100: "sha256:aaa", 5: "sha256:TAMPERED"}.get)
        assert report["agrees"] == 1
        assert report["since_seq"] == 100


class TestTheEngineRefusesToAnchorABrokenChain:

    def test_a_broken_chain_is_not_anchored(self, evidence, tmp_path):
        """Anchoring a chain that does not verify would write the broken state
        down as the truth, and every later comparison would agree with it."""
        evidence.anchors = ChainAnchor(tmp_path / "worm")
        evidence.append("model_registered", "model", "m1", {"a": 1})
        node = evidence.repo.first("seq", desc=True)
        evidence.repo.set({"content_hash": "sha256:" + "0" * 64}, id=node["id"])
        with pytest.raises(AnchorError, match="write the broken state down"):
            evidence.anchor_head()
        assert not list((tmp_path / "worm").glob("*.anchor")) \
            if (tmp_path / "worm").exists() else True

    def test_without_an_anchor_root_it_says_so_rather_than_passing(self, evidence):
        """The honest answer for an unconfigured deployment is 'self-certified',
        not 'verified'."""
        evidence.anchors = None
        report = evidence.verify_against_anchors()
        assert report["agrees"] == 1 and "self-certified" in report["detail"]

    def test_the_chain_can_verify_against_itself_and_still_be_caught(
            self, evidence, tmp_path):
        """**The whole point.**

        An attacker who rewrites a node and re-links every hash after it leaves
        a chain that is internally consistent. `verify_chain` passes. Only the
        comparison against a head written to another medium fails.
        """
        evidence.anchors = ChainAnchor(tmp_path / "worm")
        for n in range(3):
            evidence.append("model_registered", "model", f"m{n}", {"n": n})
        evidence.anchor_head()
        anchored = evidence.anchors.latest()

        # Rewrite the anchored node and re-link everything after it, exactly as
        # somebody with database access would.
        target = evidence.repo.one(seq=anchored["seq"])
        evidence.repo.set({"payload": {"n": 999},
                           "chain_hash": "sha256:" + "e" * 64}, id=target["id"])

        assert evidence.verify_against_anchors()["agrees"] == 0, (
            "the anchor did not catch a rewritten node, which is the only "
            "thing it exists to catch")


class TestTheStoreIsASeamAndNotAFilesystem:
    """`WORMReader` and `WORMWriter` (`core/ports.py`) exist so that the medium
    is a deployment decision.

    A directory gives separation — the database alone is no longer enough — and
    not enforcement: a process running as this user can delete an anchor, and
    the read-only bit stops an accident rather than an adversary. A bank that
    needs the guarantee points the same interface at S3 Object Lock or an
    append-only volume.

    The property that makes that swap safe is that the anchor never learns which
    it got, so hardening the storage does not mean editing the control.
    """

    def test_the_filesystem_store_satisfies_both_ports(self):
        from core.evidence.worm import FilesystemWORM
        from core.ports import WORMReader, WORMWriter
        store = FilesystemWORM()
        assert isinstance(store, WORMReader) and isinstance(store, WORMWriter)

    def test_the_default_root_is_under_data(self):
        """`data/` is entirely untracked — anchors are runtime evidence about
        one instance's chain and mean nothing in a repository."""
        from core.evidence.worm import DEFAULT_ROOT
        assert DEFAULT_ROOT == "./data/worm"

    def test_write_once_means_the_store_refuses_the_second_write(self, tmp_path):
        """The refusal is the guarantee. Everything above it rests on the store
        declining, rather than on callers remembering not to ask."""
        from core.evidence.worm import FilesystemWORM, WormError
        store = FilesystemWORM(tmp_path / "w")
        store.put("a", b"one")
        store.put("a", b"one")                       # idempotent
        with pytest.raises(WormError, match="write-once"):
            store.put("a", b"two")

    def test_a_name_cannot_escape_the_root(self, tmp_path):
        """The store's whole value is that its contents are somewhere else; a
        name with a separator would let a caller write anywhere."""
        from core.evidence.worm import FilesystemWORM, WormError
        store = FilesystemWORM(tmp_path / "w")
        for bad in ("../escape", "a/b", "", "."):
            with pytest.raises(WormError, match="flat object name"):
                store.put(bad, b"x")

    def test_the_anchor_works_against_any_store(self, tmp_path):
        """Driven through an in-memory store that is not a filesystem at all.
        If this passes, the anchor genuinely does not know what it is writing
        to — which is the claim the seam is making."""
        class InMemoryWORM:
            def __init__(self):
                self.held = {}

            def put(self, name, content):
                if name in self.held and self.held[name] != content:
                    raise AssertionError("write-once violated")
                self.held[name] = content

            def exists(self, name):
                return name in self.held

            def names(self):
                return sorted(self.held)

            def get(self, name):
                return self.held[name]

        anchor = ChainAnchor(InMemoryWORM())
        anchor.anchor(7, "sha256:aaa")
        assert anchor.verify({7: "sha256:aaa"}.get)["agrees"] == 1
        assert anchor.verify({7: "sha256:zzz"}.get)["agrees"] == 0


class TestAnchoringUnderConcurrentWrites:
    """The anchoring job runs on a schedule while the platform is being used.

    Both tests here exist because the first version of this control failed under
    exactly that condition, and failed in the direction that matters: it raised
    a **false** alarm, permanently, on a healthy chain.
    """

    def test_an_empty_chain_is_not_anchored(self, evidence, tmp_path):
        """`head()` answers an empty chain with `(0, GENESIS)`. Sequence 0 is
        the genesis constant, not a node, and no node will ever have it — so an
        anchor written for it can never be satisfied.

        A scheduled run on a fresh instance meets an empty chain routinely, so
        the control's first act was to accuse the instance it was protecting.
        Because the store is write-once the accusation could not be withdrawn,
        and the only way to clear it was to delete the anchors — which is the
        one action that defeats the entire arrangement.
        """
        from core.evidence.worm import FilesystemWORM
        evidence.anchors = ChainAnchor(FilesystemWORM(tmp_path / "worm"))
        report = evidence.anchor_head()
        assert report["anchored"] == 0 and "no head to anchor" in report["detail"]
        assert evidence.verify_against_anchors()["agrees"] == 1

    def test_the_store_refuses_sequence_zero_even_if_asked(self, tmp_path):
        """Defence in depth: the store is write-once, so a bad anchor is
        permanent, and the caller is not the only thing that should know it."""
        from core.evidence.worm import FilesystemWORM
        anchor = ChainAnchor(FilesystemWORM(tmp_path / "worm"))
        with pytest.raises(AnchorError, match="genesis constant"):
            anchor.anchor(0, "sha256:" + "0" * 64)

    def test_anchoring_while_the_chain_is_being_written_raises_no_false_alarm(
            self, evidence, tmp_path):
        """Four writers and an anchorer, concurrently. The chain must verify and
        must agree with every anchor taken along the way.

        This is the shape the scheduler actually runs in, and it is the only way
        the sequence-zero defect showed up — no single-threaded test met an
        empty chain at the moment of anchoring.
        """
        import threading

        from core.evidence import EvidenceEngine
        from core.evidence.worm import FilesystemWORM
        from db import (Database, EvidenceCheckpointRepository,
                        EvidenceRepository)

        # A file-backed database, not the shared fixture. The fixture's
        # connection is not built for concurrent writers and fails with "no more
        # rows available" — which is the fixture's limit, not the chain's, and
        # asserting against it would be testing the harness.
        db = Database(f"sqlite:///{tmp_path}/chain.db", False)
        evidence = EvidenceEngine(EvidenceRepository(db),
                                  EvidenceCheckpointRepository(db),
                                  anchors=ChainAnchor(FilesystemWORM(tmp_path / "worm")))
        stop, failures = threading.Event(), []

        def write(n):
            for i in range(25):
                try:
                    evidence.append("model_registered", "model", f"m{n}-{i}",
                                    {"i": i})
                except Exception as exc:                     # noqa: BLE001
                    failures.append(("append", type(exc).__name__, str(exc)))

        def anchor_repeatedly():
            while not stop.is_set():
                try:
                    evidence.anchor_head()
                except Exception as exc:                     # noqa: BLE001
                    failures.append(("anchor", type(exc).__name__, str(exc)))

        writers = [threading.Thread(target=write, args=(n,)) for n in range(4)]
        anchorer = threading.Thread(target=anchor_repeatedly, daemon=True)
        anchorer.start()
        for t in writers:
            t.start()
        for t in writers:
            t.join()
        stop.set()
        anchorer.join(timeout=5)

        assert not failures, failures[:3]
        assert evidence.verify_chain()["valid"]
        agreement = evidence.verify_against_anchors()
        assert agreement["agrees"] == 1, agreement.get("broken")
        assert agreement["anchored"] >= 1, "nothing was anchored, so nothing was tested"
