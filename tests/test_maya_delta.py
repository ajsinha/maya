"""
maya_delta: the conformance suite on both backends, the cross-backend round
trips in both directions, and loud refusal of unsupported protocol features
(specification §7.4, SC-16).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest

from maya_delta import DeltaLake, MayaDeltaError, UnsupportedFeature, select_backend
from maya_delta.conformance.suite import CASES, sample_table

BACKENDS = ["native", "pure"]


@pytest.fixture(scope="module")
def lakes() -> dict[str, DeltaLake]:
    return {b: DeltaLake(b) for b in BACKENDS}


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("case", sorted(CASES))
def test_conformance(lakes: dict[str, DeltaLake], backend: str, case: str, tmp_path: Path) -> None:
    CASES[case](lakes[backend], tmp_path)


@pytest.mark.parametrize("writer,reader", [("native", "pure"), ("pure", "native")])
@pytest.mark.parametrize("partitioned", [False, True])
def test_cross_backend_round_trip(lakes: dict[str, DeltaLake], writer: str, reader: str,
                                  partitioned: bool, tmp_path: Path) -> None:
    w, r = lakes[writer], lakes[reader]
    part = ["part"] if partitioned else None
    for k in range(12):  # past the pure checkpoint interval
        w.write(tmp_path / "t", sample_table(3, offset=3 * k), partition_by=part)
    written = w.read(tmp_path / "t", sort_by=["id"])
    got = r.read(tmp_path / "t", sort_by=["id"])
    assert got.equals(written)
    assert got.num_rows == 36
    assert r.version(tmp_path / "t") == w.version(tmp_path / "t") == 11
    assert r.read(tmp_path / "t", version=3, sort_by=["id"]).equals(w.read(tmp_path / "t", version=3, sort_by=["id"]))


@pytest.mark.parametrize("first,second", [("native", "pure"), ("pure", "native")])
def test_interleaved_writers(lakes: dict[str, DeltaLake], first: str, second: str, tmp_path: Path) -> None:
    """Each backend appends to a table the other created; both see all rows."""
    lakes[first].write(tmp_path / "t", sample_table(2), partition_by=["part"])
    lakes[second].write(tmp_path / "t", sample_table(2, offset=2))
    lakes[first].write(tmp_path / "t", sample_table(2, offset=4))
    a = lakes["native"].read(tmp_path / "t", sort_by=["id"])
    b = lakes["pure"].read(tmp_path / "t", sort_by=["id"])
    assert a.equals(b) and a.num_rows == 6


def test_pure_reads_native_checkpoint(lakes: dict[str, DeltaLake], tmp_path: Path) -> None:
    from maya_delta.native import NativeBackend
    for k in range(4):
        lakes["native"].write(tmp_path / "t", sample_table(2, offset=2 * k))
    NativeBackend().create_checkpoint(tmp_path / "t")
    lakes["native"].write(tmp_path / "t", sample_table(2, offset=8))
    assert any(p.name.endswith(".checkpoint.parquet") for p in (tmp_path / "t" / "_delta_log").iterdir())
    # Remove the JSON commits the checkpoint covers: the pure reader must use it.
    for p in (tmp_path / "t" / "_delta_log").glob("0000000000000000000[0-2].json"):
        p.unlink()
    got = lakes["pure"].read(tmp_path / "t", sort_by=["id"])
    assert got.column("id").to_pylist() == list(range(10))


def _table_with_protocol(tmp: Path, protocol: dict) -> Path:
    DeltaLake("pure").write(tmp / "t", pa.table({"a": pa.array([1], pa.int64())}))
    entry = tmp / "t" / "_delta_log" / f"{1:020d}.json"
    entry.write_text(json.dumps({"protocol": protocol}) + "\n", encoding="utf-8")
    return tmp / "t"


@pytest.mark.parametrize("feature", ["deletionVectors", "columnMapping", "v2Checkpoint"])
def test_unsupported_reader_feature_is_refused_by_name(tmp_path: Path, feature: str) -> None:
    path = _table_with_protocol(tmp_path, {"minReaderVersion": 3, "minWriterVersion": 7,
                                           "readerFeatures": [feature], "writerFeatures": [feature]})
    with pytest.raises(UnsupportedFeature) as err:
        DeltaLake("pure").read(path)
    assert err.value.feature == feature and feature in str(err.value)


@pytest.mark.parametrize("feature", ["changeDataFeed", "clustering", "domainMetadata"])
def test_unsupported_writer_feature_is_refused_by_name(tmp_path: Path, feature: str) -> None:
    path = _table_with_protocol(tmp_path, {"minReaderVersion": 1, "minWriterVersion": 7,
                                           "writerFeatures": [feature]})
    assert DeltaLake("pure").read(path).num_rows == 1  # reading is unaffected
    with pytest.raises(UnsupportedFeature) as err:
        DeltaLake("pure").write(path, pa.table({"a": pa.array([2], pa.int64())}))
    assert err.value.feature == feature


def test_deletion_vector_on_a_file_is_refused(tmp_path: Path) -> None:
    lake = DeltaLake("pure")
    lake.write(tmp_path / "t", pa.table({"a": pa.array([1], pa.int64())}))
    add = lake.files(tmp_path / "t")[0]
    entry = tmp_path / "t" / "_delta_log" / f"{1:020d}.json"
    entry.write_text(json.dumps({"add": {"path": add["path"], "partitionValues": {}, "size": add["size"],
                                         "modificationTime": 0, "dataChange": False,
                                         "deletionVector": {"storageType": "u"}}}) + "\n")
    with pytest.raises(UnsupportedFeature, match="deletionVectors"):
        lake.read(tmp_path / "t")


def test_backend_selection_is_reported() -> None:
    auto = select_backend("auto")
    assert auto.name in ("native", "pure") and auto.reason
    assert select_backend("pure").name == "pure"
    with pytest.raises(MayaDeltaError):
        select_backend("spark")


def test_missing_table(tmp_path: Path) -> None:
    for b in BACKENDS:
        lake = DeltaLake(b)
        assert not lake.exists(tmp_path / "nope")
        with pytest.raises(MayaDeltaError):
            lake.read(tmp_path / "nope")


# -- maintenance: compaction and vacuum ---------------------------------------------------
def _small_writes(lake: DeltaLake, path: Path, n: int, partitioned: bool) -> pa.Table:
    part = ["part"] if partitioned else None
    for k in range(n):
        lake.write(path, sample_table(3, offset=3 * k), partition_by=part)
    return lake.read(path)


def _same(a: pa.Table, b: pa.Table) -> bool:
    key = [(c, "ascending") for c in ("id",)]
    return a.sort_by(key).equals(b.sort_by(key))


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("partitioned", [False, True])
def test_optimize_compacts_without_changing_content(lakes: dict[str, DeltaLake], backend: str,
                                                    partitioned: bool, tmp_path: Path) -> None:
    lake = lakes[backend]
    path = tmp_path / "t"
    before = _small_writes(lake, path, 12, partitioned)
    files_before, version_before = len(lake.files(path)), lake.version(path)
    out = lake.optimize(path, target_size=64 * 1024 * 1024)
    assert out["numFilesRemoved"] == files_before and out["numFilesAdded"] < files_before
    assert len(lake.files(path)) == out["numFilesAdded"] and lake.version(path) == version_before + 1
    assert _same(lake.read(path), before)
    assert lake.history(path)[-1]["operation"] == "OPTIMIZE"
    assert _same(lake.read(path, version=version_before), before)   # time travel still works
    other = lakes["pure" if backend == "native" else "native"]
    assert _same(other.read(path), before)                           # the other backend agrees
    again = lake.optimize(path, target_size=64 * 1024 * 1024)
    assert again["numFilesRemoved"] == 0 and lake.version(path) == version_before + 1


@pytest.mark.parametrize("backend", BACKENDS)
def test_vacuum_removes_only_unreferenced_files_past_retention(lakes: dict[str, DeltaLake],
                                                               backend: str,
                                                               tmp_path: Path) -> None:
    lake = lakes[backend]
    path = tmp_path / "t"
    before = _small_writes(lake, path, 6, partitioned=True)
    old_files = {f["path"] for f in lake.files(path)}
    lake.optimize(path, target_size=64 * 1024 * 1024)
    assert lake.vacuum(path) == []                       # just removed: inside the 7-day window
    with pytest.raises(MayaDeltaError, match="below the 168h minimum"):
        lake.vacuum(path, retention_hours=0)
    planned = lake.vacuum(path, retention_hours=0, enforce_retention=False, dry_run=True)
    assert len(planned) == len(old_files) and all((path / p).exists() for p in planned)
    deleted = lake.vacuum(path, retention_hours=0, enforce_retention=False)
    assert deleted == planned and not any((path / p).exists() for p in deleted)
    assert _same(lake.read(path), before)                # the current snapshot is untouched
    assert lake.vacuum(path, retention_hours=0, enforce_retention=False) == []


def test_pure_vacuum_also_clears_old_orphans_but_not_new_ones(tmp_path: Path) -> None:
    import os
    import time as _time
    lake = DeltaLake("pure")
    path = tmp_path / "t"
    _small_writes(lake, path, 2, partitioned=False)
    stale = path / "part-00000-orphan-old.snappy.parquet"
    fresh = path / "part-00000-orphan-new.snappy.parquet"
    for f in (stale, fresh):
        f.write_bytes(b"left by a failed write")
    long_ago = _time.time() - 30 * 24 * 3600
    os.utime(stale, (long_ago, long_ago))
    assert lake.vacuum(path) == ["part-00000-orphan-old.snappy.parquet"]
    assert fresh.exists() and not stale.exists()
