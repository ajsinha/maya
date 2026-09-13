"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The checkpoint is a mark the verified process wrote, so something else has to
vouch for it.

C-4's third disposition was explicit: *verification compares the head against
the anchor, not merely against itself — self-consistency of a chain an attacker
controls proves nothing.* What shipped was `evidence_checkpoint`, an ordinary
table in the same database, written at the end of a successful verification.
`verify_since_checkpoint` trusted it and checked only what came after.

The reasoning was sound — the full walk is 2.9 seconds and 83 MB at forty
thousand nodes and a readiness probe cannot pay that. The consequence was that
the cheap check, the one that runs continuously, compared the chain against a
mark the same process wrote. C-4 disposition 3 recurring one abstraction above
where it was written.

`test_a_rewritten_chain_with_a_moved_mark_is_caught` is the attack. Everything
else here exists so that test cannot pass for the wrong reason.
"""
from __future__ import annotations

import pytest

import json

from core.evidence import EvidenceEngine
from core.evidence.anchor import ChainAnchor
from core.evidence.worm import FilesystemWORM


@pytest.fixture()
def anchored(db, repos, tmp_path):
    """An engine whose anchors live outside the database, as deployed."""
    from db import EvidenceCheckpointRepository
    anchors = ChainAnchor(FilesystemWORM(tmp_path / "worm"))
    return EvidenceEngine(repos["evidence"], EvidenceCheckpointRepository(db),
                          anchors=anchors), anchors


def _as_an_attacker_with_database_access(db):
    """Drop the append-only triggers.

    The triggers are a real control and they stop the naive version of this
    attack — but they are objects in the database, and an attacker who can
    write the chain can drop them first. Modelling the attacker as unable to
    do that would make this test pass because of a defence it is not testing,
    which is the failure mode the whole checkpoint story is about.
    """
    db.execute("DROP TRIGGER IF EXISTS append_only_evidence_node_update")
    db.execute("DROP TRIGGER IF EXISTS append_only_evidence_node_delete")


def _rewrite_history(engine, db, at_seq, new_actor):
    """Edit a node and recompute every hash after it, as a real attacker would.

    Changing a field and leaving the hashes alone is caught by `verify_chain`,
    which re-derives — so an attacker who has already dropped the triggers
    recomputes forward, and the chain becomes perfectly self-consistent about
    a history that did not happen. That version passes every check the chain
    can perform on itself, which is precisely why C-4 asked for an anchor.
    """
    from db.database import digest as canonical_digest
    nodes = sorted(db.query("SELECT * FROM evidence_node"),
                   key=lambda n: n["seq"])
    prev_hash = ""
    for node in nodes:
        if node["seq"] == at_seq:
            node["recorded_by"] = new_actor
        if node["seq"] < at_seq:
            prev_hash = node["chain_hash"]
            continue
        parents = json.loads(node["parents"] or "[]")
        content = engine.content_hash_of({
            "kind": node["kind"], "subject_type": node["subject_type"],
            "subject_id": node["subject_id"],
            "payload": json.loads(node["payload"] or "{}"),
            "parents": parents, "recorded_by": node["recorded_by"],
            "trust": node["trust"]})
        chain = canonical_digest([node["seq"], prev_hash, content, parents])
        db.execute(
            "UPDATE evidence_node SET recorded_by = :a, content_hash = :c, "
            "prev_hash = :p, chain_hash = :h WHERE seq = :s",
            {"a": node["recorded_by"], "c": content, "p": prev_hash,
             "h": chain, "s": node["seq"]})
        prev_hash = chain


def _fill(engine, n=6):
    for i in range(n):
        engine.append("model_registered", "model", f"m-{i}",
                      {"urn": f"urn:maya:model:m-{i}"}, actor="ana")


class TestTheAttack:
    def test_a_rewritten_chain_with_a_moved_mark_is_caught(self, anchored, db):
        """Rewrite history, then move the checkpoint on top of it.

        An attacker with database access can do both — the chain and the mark
        are two tables in one database. Before this, the incremental verifier
        read the moved mark, checked only what came after, and reported valid.
        """
        engine, _anchors = anchored
        _fill(engine, 6)
        engine.anchor_head(actor="ana")                 # a second medium, at seq 6
        _fill(engine, 3)
        engine.verify_since_checkpoint()           # mark now sits at seq 9

        # Rewrite a node BELOW the anchor, then re-point the mark at the new
        # head so the incremental walk starts after the damage.
        _as_an_attacker_with_database_access(db)
        _rewrite_history(engine, db, at_seq=3, new_actor="somebody_else")
        assert engine.verify_chain()["valid"], (
            "the rewritten chain must be self-consistent, or this test proves "
            "only that verify_chain works")
        seq, head = engine.head()
        db.execute("UPDATE evidence_checkpoint SET chain_hash = :h, seq = :s",
                   {"h": head, "s": seq})

        report = engine.verify_since_checkpoint()
        assert report.get("checkpoint_repudiated") == 1
        assert report["scope"] == "full"

    def test_the_report_says_the_ground_was_rewritten(self, anchored, db):
        engine, _ = anchored
        _fill(engine, 4)
        engine.anchor_head(actor="ana")
        engine.verify_since_checkpoint()
        _as_an_attacker_with_database_access(db)
        _rewrite_history(engine, db, at_seq=2, new_actor="x")
        report = engine.verify_since_checkpoint()
        assert "rewritten ground" in report.get("detail", "")


class TestWhatItDoesNotClaim:
    def test_no_anchor_below_the_mark_is_not_a_contradiction(self, anchored):
        """*Nothing vouches for this* and *something contradicts this* are
        different answers, and collapsing them would make every deployment
        without anchors look compromised."""
        engine, _anchors = anchored
        _fill(engine, 3)
        first = engine.verify_since_checkpoint()
        assert "checkpoint_repudiated" not in first
        _fill(engine, 2)
        assert engine.verify_since_checkpoint()["valid"]

    def test_an_engine_with_no_anchor_store_still_works(self, db, repos):
        """A deployment with no anchors is self-certified. This cannot improve
        on that, and must not refuse because of it."""
        from db import EvidenceCheckpointRepository
        engine = EvidenceEngine(repos["evidence"],
                                EvidenceCheckpointRepository(db))
        _fill(engine, 4)
        assert engine.verify_since_checkpoint()["valid"]

    def test_an_unreadable_anchor_is_treated_as_tampering(self, anchored,
                                                          tmp_path):
        """Everywhere else here an unreadable anchor is tampering until
        explained. This is the path where calling it absence would be most
        convenient."""
        engine, _anchors = anchored
        _fill(engine, 4)
        engine.anchor_head(actor="ana")
        engine.verify_since_checkpoint()
        for path in (tmp_path / "worm").rglob("*.anchor"):
            path.chmod(0o600)
            path.write_text("not json")
        report = engine.verify_since_checkpoint()
        assert report.get("checkpoint_repudiated") == 1

    def test_an_intact_chain_below_an_anchor_still_takes_the_cheap_path(
            self, anchored):
        """The whole point of the checkpoint is that the common case stays
        cheap. A corroboration that forced a full walk every time would have
        undone the fix it is protecting."""
        engine, _ = anchored
        _fill(engine, 5)
        engine.anchor_head(actor="ana")
        engine.verify_since_checkpoint()
        _fill(engine, 2)
        report = engine.verify_since_checkpoint()
        assert report["scope"] == "incremental"
        assert report["checked"] == 2
