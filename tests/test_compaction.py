"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reclaiming bytes nothing references, and the race that makes one pass wrong.

The dangerous test here is `test_a_blob_is_never_swept_on_first_sight`. An
upload writes the file and then writes the row that references it. A sweeper
walking past in between sees exactly what a real orphan looks like, and a
single-pass sweep deletes the artifact of a model somebody is registering.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.retention.common import RetentionError
from core.retention.compaction import (REFERENCED_BY, SIGHTINGS_BEFORE_SWEEP,
                                       Compaction)
from core.retention.tombstones import Tombstones
import db.schema.tables  # noqa: F401 — registers every table on METADATA
from db import BlobOrphanRepository, ModelTombstoneRepository
from db.schema.metadata import METADATA


def _version(db, vid, model_id, digest):
    """A model_version row, filling whatever else the schema insists on.

    These tests are about the refcount, not about the eleven other NOT NULL
    columns on `model_version`.
    """
    row = {"id": vid, "model_id": model_id, "semver": "1.0.0",
           "artifact_digest": digest, "status": "draft"}
    for col in METADATA.tables["model_version"].columns:
        if col.name in row or col.nullable or col.server_default is not None:
            continue
        row[col.name] = 0.0 if str(col.type).upper().startswith(
            ("DOUBLE", "FLOAT", "INTEGER")) else f"{col.name}-x"
    cols = ", ".join(row)
    db.execute(f"INSERT INTO model_version ({cols}) VALUES "
               f"({', '.join(':' + c for c in row)})", row)


class FakeStore:
    """A content-addressed store with the fan-out the real ones use."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, digest: str) -> Path:
        body = digest.split(":", 1)[1]
        return self.root / body[:2] / body[2:4] / body

    def put(self, payload: bytes) -> str:
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        path = self._path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return digest


@pytest.fixture()
def store(tmp_path):
    return FakeStore(tmp_path / "artifacts")


@pytest.fixture()
def compaction(db, store):
    return Compaction(db, BlobOrphanRepository(db), artifacts=store)


class TestTheRaceThatMakesOnePassWrong:
    def test_a_blob_is_never_swept_on_first_sight(self, compaction, store):
        """The bytes land before the row that references them. A sweep between
        the two sees a file nothing points at — which is what an orphan looks
        like, and also what an upload in progress looks like."""
        digest = store.put(b"a model somebody is registering right now")
        first = compaction.sweep()
        assert first["swept"] == 0
        assert first["marked"] == 1
        assert store._path(digest).exists()

    def test_it_goes_on_the_second_pass(self, compaction, store):
        digest = store.put(b"genuinely orphaned")
        compaction.sweep()
        second = compaction.sweep()
        assert second["swept"] == 1
        assert not store._path(digest).exists()

    def test_a_mark_is_cleared_when_a_reference_appears(self, compaction, store,
                                                        db):
        """The mark must not simply expire. A two-pass-old mark on a blob that
        acquired a reference in between would reclaim a live artifact."""
        digest = store.put(b"about to be registered")
        compaction.sweep()
        _version(db, "v-1", "m-1", digest)
        third = compaction.sweep()
        assert third["cleared"] == 1
        assert compaction.sweep()["swept"] == 0
        assert store._path(digest).exists()

    def test_two_sightings_is_the_declared_threshold(self):
        assert SIGHTINGS_BEFORE_SWEEP == 2


class TestTheRefcount:
    def test_a_referenced_blob_is_never_marked(self, compaction, store, db):
        digest = store.put(b"live")
        _version(db, "v-1", "m-1", digest)
        assert compaction.sweep()["marked"] == 0

    def test_two_models_sharing_a_checkpoint_share_one_file(self, compaction,
                                                            store, db):
        """Content addressing means a per-model delete would take the
        surviving model's bytes. Reclamation asks the register, not the
        deletion."""
        digest = store.put(b"shared")
        for n, m in (("v-1", "m-1"), ("v-2", "m-2")):
            _version(db, n, m, digest)
        db.execute("DELETE FROM model_version WHERE id = 'v-1'")
        compaction.sweep()
        assert compaction.sweep()["swept"] == 0
        assert store._path(digest).exists()

    def test_every_content_address_column_is_accounted_for(self):
        """A new column holding a digest and not listed in `REFERENCED_BY`
        means a live blob gets marked, then deleted. The refcount is only a
        refcount if it counts every reference."""
        import db.schema.tables  # noqa: F401
        from db.schema.metadata import METADATA
        known = {f"{t}.{c}" for cols in REFERENCED_BY.values()
                 for t, c in cols}
        # `manifest_digest` addresses a manifest, not a stored blob; the two
        # stores here hold artifacts and attachments only.
        ignore = {"model_version.manifest_digest"}
        found = {f"{t.name}.{c.name}" for t in METADATA.tables.values()
                 for c in t.columns
                 if c.name in ("artifact_digest", "digest")
                 and t.name in ("model_version", "attachment")}
        assert not found - known - ignore, (
            f"a content address nothing refcounts: {sorted(found - known - ignore)}")


class TestWhatItRefuses:
    def test_a_sweep_is_refused_under_an_estate_hold(self, db, store):
        class Held:
            @staticmethod
            def active():
                return [{"scope_kind": "estate", "reference": "MAT-1"}]
        c = Compaction(db, BlobOrphanRepository(db), artifacts=store,
                       holds=Held())
        with pytest.raises(RetentionError) as e:
            c.sweep()
        assert e.value.code == "under_legal_hold"

    def test_the_refusal_says_a_refcount_is_not_permission(self, db, store):
        class Held:
            @staticmethod
            def active():
                return [{"scope_kind": "estate", "reference": "MAT-1"}]
        c = Compaction(db, BlobOrphanRepository(db), artifacts=store,
                       holds=Held())
        with pytest.raises(RetentionError) as e:
            c.sweep()
        assert "not an answer to the second" in e.value.remediation

    def test_compacting_a_model_that_was_never_deleted_is_refused(self, db,
                                                                  store):
        stones = Tombstones(ModelTombstoneRepository(db))
        c = Compaction(db, BlobOrphanRepository(db), artifacts=store,
                       tombstones=stones)
        with pytest.raises(RetentionError) as e:
            c.mark_compacted("urn:maya:model:alive", actor="ana")
        assert e.value.code == "no_tombstone"

    def test_compacting_twice_is_refused(self, db, store):
        stones = Tombstones(ModelTombstoneRepository(db))
        stones.mark({"id": "m-1", "urn": "urn:maya:model:x", "name": "x",
                     "status": "retired", "created_at": 0.0},
                    reason="r", actor="ana")
        c = Compaction(db, BlobOrphanRepository(db), artifacts=store,
                       tombstones=stones)
        c.mark_compacted("urn:maya:model:x", actor="ana")
        with pytest.raises(RetentionError) as e:
            c.mark_compacted("urn:maya:model:x", actor="ana")
        assert e.value.code == "already_compacted"


class TestThePlan:
    def test_a_plan_reclaims_nothing(self, compaction, store):
        digest = store.put(b"orphan")
        compaction.plan()
        compaction.plan()
        assert store._path(digest).exists()

    def test_a_dry_run_reclaims_nothing(self, compaction, store):
        digest = store.put(b"orphan")
        compaction.sweep()
        assert compaction.sweep(dry_run=True)["swept"] == 1
        assert store._path(digest).exists()

    def test_delta_is_reported_as_out_of_reach_rather_than_skipped(self, db,
                                                                   tmp_path):
        """Silently not touching Delta and reporting nothing look the same to
        an operator staring at disk usage."""
        root = tmp_path / "delta"
        (root / "t").mkdir(parents=True)
        (root / "t" / "part-0.parquet").write_bytes(b"x" * 100)
        c = Compaction(db, BlobOrphanRepository(db), delta_root=root)
        out = c.plan()["not_reclaimable"]
        assert out["delta_bytes"] == 100
        assert "transaction log" in out["why"]
