"""
The maya_delta conformance suite.

One set of cases, run once per backend. Each case takes a ``DeltaLake`` and a
fresh scratch directory and raises ``AssertionError`` on any deviation. Both
backends must pass every case identically; the cross-backend round trips live
in the test module because they need both backends at once.

Protocol version numbers are asserted as ranges, never as literals: a test that
pins a number passes for the wrong reason the moment a writer is upgraded.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import decimal
import threading
from pathlib import Path
from typing import Callable

import pyarrow as pa

from maya_delta import DeltaLake, MayaDeltaError

UTC = dt.timezone.utc


def sample_table(n: int = 6, offset: int = 0) -> pa.Table:
    """A table exercising every supported logical type, including nested ones and nulls."""
    ids = list(range(offset, offset + n))
    return pa.table(
        {
            "id": pa.array(ids, pa.int64()),
            "i32": pa.array([None if i % 5 == 0 else i for i in ids], pa.int32()),
            "f64": pa.array([i * 0.5 for i in ids], pa.float64()),
            "f32": pa.array([float(i) for i in ids], pa.float32()),
            "flag": pa.array([i % 2 == 0 for i in ids], pa.bool_()),
            "name": pa.array([f"n{i}" if i % 4 else None for i in ids], pa.string()),
            "bin": pa.array([bytes([i % 256]) for i in ids], pa.binary()),
            "day": pa.array([dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in ids], pa.date32()),
            "ts": pa.array(
                [dt.datetime(2026, 1, 1, 12, tzinfo=UTC) + dt.timedelta(hours=i) for i in ids],
                pa.timestamp("us", tz="UTC"),
            ),
            "ts_ntz": pa.array(
                [dt.datetime(2026, 1, 1) + dt.timedelta(minutes=i) for i in ids], pa.timestamp("us")
            ),
            "amount": pa.array([decimal.Decimal(f"{i}.25") for i in ids], pa.decimal128(12, 2)),
            "vec": pa.array(
                [[float(i), None, 2.0 * i] if i % 3 else None for i in ids], pa.list_(pa.float64())
            ),
            "rec": pa.array(
                [{"a": i, "b": f"s{i}"} for i in ids],
                pa.struct([("a", pa.int64()), ("b", pa.string())]),
            ),
            "tags": pa.array([[("k", float(i))] for i in ids], pa.map_(pa.string(), pa.float64())),
            "part": pa.array(["even" if i % 2 == 0 else "odd" for i in ids], pa.string()),
        }
    )


def _rows(t: pa.Table) -> list[dict]:
    return t.sort_by([("id", "ascending")]).to_pylist()


def case_roundtrip_all_types(lake: DeltaLake, tmp: Path) -> None:
    src = sample_table()
    v = lake.write(tmp / "t", src)
    assert v == 0, f"first commit must be version 0, got {v}"
    got = lake.read(tmp / "t", sort_by=["id"])
    assert got.schema.names == src.schema.names, got.schema.names
    assert _rows(got) == _rows(src)


def case_append_and_version(lake: DeltaLake, tmp: Path) -> None:
    for k in range(3):
        v = lake.write(tmp / "t", sample_table(4, offset=4 * k))
        assert v == k
    assert lake.version(tmp / "t") == 2
    assert lake.read(tmp / "t").num_rows == 12


def case_overwrite(lake: DeltaLake, tmp: Path) -> None:
    lake.write(tmp / "t", sample_table(5))
    lake.write(tmp / "t", sample_table(2, offset=100), mode="overwrite")
    got = lake.read(tmp / "t", sort_by=["id"])
    assert got.column("id").to_pylist() == [100, 101]


def case_partitioned_and_pruned(lake: DeltaLake, tmp: Path) -> None:
    lake.write(tmp / "t", sample_table(8), partition_by=["part"])
    assert lake.partition_values(tmp / "t", "part") == {"even", "odd"}
    even = lake.read(tmp / "t", partitions={"part": ["even"]})
    assert set(even.column("part").to_pylist()) == {"even"} and even.num_rows == 4
    files = lake.files(tmp / "t", partitions={"part": ["odd"]})
    assert files and all(f["partitionValues"]["part"] == "odd" for f in files)
    assert lake.read(tmp / "t").schema.names == sample_table().schema.names


def case_projection(lake: DeltaLake, tmp: Path) -> None:
    lake.write(tmp / "t", sample_table(4), partition_by=["part"])
    got = lake.read(tmp / "t", columns=["part", "id"])
    assert got.schema.names == ["part", "id"]
    assert sorted(got.column("id").to_pylist()) == [0, 1, 2, 3]


def case_time_travel(lake: DeltaLake, tmp: Path) -> None:
    lake.write(tmp / "t", sample_table(3))
    lake.write(tmp / "t", sample_table(3, offset=3))
    lake.write(tmp / "t", sample_table(1, offset=50), mode="overwrite")
    assert lake.read(tmp / "t", version=0).num_rows == 3
    assert lake.read(tmp / "t", version=1).num_rows == 6
    assert lake.read(tmp / "t").num_rows == 1
    try:
        lake.read(tmp / "t", version=99)
    except MayaDeltaError:
        pass
    else:
        raise AssertionError("reading a version that does not exist must raise")


def case_history_and_protocol(lake: DeltaLake, tmp: Path) -> None:
    lake.write(tmp / "t", sample_table(2))
    lake.write(tmp / "t", sample_table(2, offset=2))
    hist = lake.history(tmp / "t")
    assert [h["version"] for h in hist] == [0, 1]
    proto = lake.protocol(tmp / "t")
    assert 1 <= proto["minReaderVersion"] <= 3, proto
    assert 2 <= proto["minWriterVersion"] <= 7, proto


def case_stats_recorded(lake: DeltaLake, tmp: Path) -> None:
    lake.write(tmp / "t", sample_table(6))
    files = lake.files(tmp / "t")
    import json

    stats = [json.loads(f["stats"]) for f in files if f.get("stats")]
    assert stats, "every add must carry statistics"
    assert sum(s["numRecords"] for s in stats) == 6
    assert min(s["minValues"]["id"] for s in stats) == 0


def case_many_commits_checkpoint(lake: DeltaLake, tmp: Path) -> None:
    for k in range(13):
        lake.write(tmp / "t", sample_table(1, offset=k))
    assert lake.version(tmp / "t") == 12
    assert sorted(lake.read(tmp / "t").column("id").to_pylist()) == list(range(13))
    assert lake.read(tmp / "t", version=5).num_rows == 6


def case_schema_mismatch_refused(lake: DeltaLake, tmp: Path) -> None:
    lake.write(tmp / "t", pa.table({"a": pa.array([1], pa.int64())}))
    try:
        lake.write(tmp / "t", pa.table({"a": pa.array(["x"])}))
    except MayaDeltaError:
        return
    raise AssertionError("appending a different schema must be refused")


def case_concurrent_appends(lake: DeltaLake, tmp: Path) -> None:
    """Racing writers: every append lands, and each version is won by exactly one commit."""
    lake.write(tmp / "t", sample_table(1, offset=0))
    errors: list[BaseException] = []

    def writer(w: int) -> None:
        try:
            for k in range(3):
                lake.write(tmp / "t", sample_table(1, offset=1000 * (w + 1) + k))
        except BaseException as exc:  # noqa: BLE001 - collected and re-raised below
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(w,)) for w in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert lake.version(tmp / "t") == 18
    assert [h["version"] for h in lake.history(tmp / "t")] == list(range(19))
    assert lake.read(tmp / "t").num_rows == 19


CASES: dict[str, Callable[[DeltaLake, Path], None]] = {
    name[len("case_") :]: fn for name, fn in sorted(globals().items()) if name.startswith("case_")
}
