"""
The native backend: delta-rs (the ``deltalake`` wheel).

delta-rs owns everything that is transaction-log work — commits, conflict
resolution, snapshots, history and protocol. Data files named by its snapshot
are decoded by pyarrow through ``maya_delta.files``, exactly as the pure backend
decodes them.

That split is deliberate, and the reason is a defect in delta-rs 1.6.3 rather
than taste: reading through ``DeltaTable.to_pyarrow_table()`` /
``to_pyarrow_dataset()`` leaves a native thread that deadlocks interpreter
shutdown (reproduced every time on tables with ``date`` or ``decimal`` columns;
``DeltaTable.files()`` does the same). A process that cannot exit is not a
backend anyone can run under a test runner or a worker pool, so the native
backend never calls those paths. ``get_add_actions`` does not trigger it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa

from maya_delta.errors import ConcurrentModification, MayaDeltaError, TableNotFound
from maya_delta.files import matches, read_files
from maya_delta.schema import normalise_schema, schema_from_delta_json


def _import_deltalake() -> Any:
    import deltalake  # the one place this package imports it
    return deltalake


def _wrap(exc: Exception) -> MayaDeltaError:
    name = type(exc).__name__
    if "CommitFailed" in name or "Conflict" in name:
        return ConcurrentModification(str(exc))
    if "TableNotFound" in name:
        return TableNotFound(str(exc))
    return MayaDeltaError(f"delta-rs {name}: {exc}")


class NativeBackend:
    """Delta Lake through delta-rs for the log; pyarrow for file decoding."""

    name = "native"

    def __init__(self) -> None:
        self._dl = _import_deltalake()

    @property
    def library_version(self) -> str:
        return str(getattr(self._dl, "__version__", "unknown"))

    def _table(self, path: Path, version: int | None = None) -> Any:
        if not self.exists(path):
            raise TableNotFound(f"No Delta table at {path}")
        try:
            dt = self._dl.DeltaTable(str(path))
            if version is not None:
                if version < 0 or version > dt.version():
                    raise MayaDeltaError(f"Version {version} does not exist (latest is {dt.version()})")
                dt.load_as_version(version)
            return dt
        except MayaDeltaError:
            raise
        except Exception as exc:  # delta-rs raises its own hierarchy
            raise _wrap(exc) from exc

    def exists(self, path: Path) -> bool:
        return (Path(path) / "_delta_log").is_dir() and any((Path(path) / "_delta_log").iterdir())

    def version(self, path: Path) -> int:
        return int(self._table(path).version())

    def schema(self, path: Path, version: int | None = None) -> pa.Schema:
        return schema_from_delta_json(self._table(path, version).schema().to_json())

    def _adds(self, dt: Any) -> list[dict[str, Any]]:
        """Live add actions of a snapshot, as plain dicts."""
        partition_cols = list(dt.metadata().partition_columns)
        actions = pa.table(dt.get_add_actions(flatten=False)).to_pylist()
        out = []
        for a in actions:
            pv = a.get("partition") or a.get("partition_values") or {}
            if isinstance(pv, list):
                pv = dict(pv)
            out.append({"path": a["path"], "size": int(a["size_bytes"]),
                        "partitionValues": {c: (None if pv.get(c) is None else str(pv.get(c)))
                                            for c in partition_cols},
                        "stats": _stats_json(a)})
        return out

    def read(self, path: Path, *, partitions: dict[str, list[str]] | None = None,
             columns: list[str] | None = None, version: int | None = None) -> pa.Table:
        dt = self._table(path, version)
        schema = schema_from_delta_json(dt.schema().to_json())
        adds = [a for a in self._adds(dt) if matches(a["partitionValues"], partitions)]
        return read_files(Path(path), adds, schema, list(dt.metadata().partition_columns), columns)

    def files(self, path: Path, partitions: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
        return [a for a in self._adds(self._table(path)) if matches(a["partitionValues"], partitions)]

    def history(self, path: Path) -> list[dict[str, Any]]:
        rows = self._table(path).history()
        out = []
        for r in rows:
            params = r.get("operationParameters") or {}
            out.append({"version": int(r["version"]), "timestamp": r.get("timestamp"),
                        "operation": r.get("operation"), "operationParameters": params})
        return sorted(out, key=lambda r: r["version"])

    def protocol(self, path: Path) -> dict[str, Any]:
        p = self._table(path).protocol()
        return {"minReaderVersion": int(p.min_reader_version),
                "minWriterVersion": int(p.min_writer_version),
                "readerFeatures": list(p.reader_features) if p.reader_features else None,
                "writerFeatures": list(p.writer_features) if p.writer_features else None}

    def write(self, path: Path, table: pa.Table, *, mode: str = "append",
              partition_by: list[str] | None = None) -> int:
        if mode not in ("append", "overwrite"):
            raise MayaDeltaError(f"Unsupported write mode '{mode}'")
        table = table.cast(normalise_schema(table.schema))
        kwargs: dict[str, Any] = {"mode": mode}
        if partition_by:
            kwargs["partition_by"] = list(partition_by)
        if mode == "overwrite":
            kwargs["schema_mode"] = "overwrite"
        elif self.exists(path):
            current = self.schema(path)
            if not current.equals(table.schema):
                raise MayaDeltaError(f"Append schema does not match the table schema:\n"
                                     f"table: {current}\nwrite: {table.schema}")
        try:
            self._dl.write_deltalake(str(path), table, **kwargs)
        except Exception as exc:
            raise _wrap(exc) from exc
        return self.version(path)

    def create_checkpoint(self, path: Path) -> None:
        """Ask delta-rs for a checkpoint (used to prove the pure reader reads them)."""
        self._table(path).create_checkpoint()


def _stats_json(action: dict[str, Any]) -> str | None:
    """Rebuild a Delta ``stats`` string from delta-rs's structured add-action columns."""
    if action.get("num_records") is None:
        return None

    def plain(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: plain(x) for k, x in v.items() if x is not None}
        return v if isinstance(v, (int, float, str, bool)) else str(v)

    return json.dumps({"numRecords": action["num_records"],
                       "minValues": plain(action.get("min") or {}),
                       "maxValues": plain(action.get("max") or {}),
                       "nullCount": plain(action.get("null_count") or {})}, separators=(",", ":"))


def self_check(scratch: Path) -> None:
    """Write and read a tiny table; raises if the native backend is unusable."""
    backend = NativeBackend()
    probe = pa.table({"k": pa.array([1, 2], pa.int64()), "p": pa.array(["a", "b"])})
    target = scratch / "maya_delta_self_check"
    backend.write(target, probe, mode="overwrite", partition_by=["p"])
    got = backend.read(target)
    if got.num_rows != 2 or sorted(got.column("k").to_pylist()) != [1, 2]:
        raise MayaDeltaError("native self-check read back different data")
