"""
The pure backend: MAYA's own Delta Lake reader and writer.

Writes Hive-partitioned Parquet files, records per-file statistics on every
add, commits by exclusive create, retries appends that lose a race (after
checking the winner did not change what the append depends on), writes a
Parquet checkpoint every ``CHECKPOINT_INTERVAL`` commits, and time-travels by
version. It does not implement deletion vectors, column mapping, change data
feed or liquid clustering, and refuses a table that requires any of them.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from maya_delta.errors import (
    ConcurrentModification,
    MayaDeltaError,
    TableNotFound,
    UnsupportedFeature,
)
from maya_delta.files import escape_partition_value, file_stats, matches, read_files, to_add_path
from maya_delta.pure import log as dlog
from maya_delta.schema import normalise_schema, schema_from_delta_json, schema_to_delta_json

ENGINE = "maya_delta-pure"
MAX_COMMIT_ATTEMPTS = 200


def _now_ms() -> int:
    return int(time.time() * 1000)


def _needs_ntz(schema: pa.Schema) -> bool:
    """True when any (nested) field is a timezone-naive timestamp."""

    def walk(t: pa.DataType) -> bool:
        if pa.types.is_timestamp(t):
            return t.tz is None
        return any(walk(t.field(i).type) for i in range(t.num_fields)) if t.num_fields else False

    return any(walk(f.type) for f in schema)


def _protocol_for(schema: pa.Schema, current: dict[str, Any] | None = None) -> dict[str, Any]:
    """The lowest protocol that can carry ``schema`` (timestamp_ntz needs table features)."""
    if not _needs_ntz(schema):
        return current or {"minReaderVersion": 1, "minWriterVersion": 2}
    reader = sorted(set((current or {}).get("readerFeatures") or []) | {"timestampNtz"})
    writer = sorted(set((current or {}).get("writerFeatures") or []) | {"timestampNtz"})
    return {
        "minReaderVersion": 3,
        "minWriterVersion": 7,
        "readerFeatures": reader,
        "writerFeatures": writer,
    }


class PureBackend:
    """Delta protocol subset implemented over pyarrow and the local filesystem."""

    name = "pure"

    # ------------------------------------------------------------------ reads

    def exists(self, path: Path) -> bool:
        try:
            dlog.latest_version(path)
        except TableNotFound:
            return False
        return True

    def version(self, path: Path) -> int:
        return dlog.latest_version(path)

    def snapshot(self, path: Path, version: int | None = None) -> dlog.Snapshot:
        return dlog.load_snapshot(path, version)

    def schema(self, path: Path, version: int | None = None) -> pa.Schema:
        return schema_from_delta_json(self.snapshot(path, version).metadata["schemaString"])

    def read(
        self,
        path: Path,
        *,
        partitions: dict[str, list[str]] | None = None,
        columns: list[str] | None = None,
        version: int | None = None,
    ) -> pa.Table:
        snap = self.snapshot(path, version)
        schema = schema_from_delta_json(snap.metadata["schemaString"])
        adds = [
            a for a in snap.files.values() if matches(a.get("partitionValues") or {}, partitions)
        ]
        return read_files(path, adds, schema, snap.partition_columns, columns)

    def files(
        self, path: Path, partitions: dict[str, list[str]] | None = None
    ) -> list[dict[str, Any]]:
        snap = self.snapshot(path)
        return [
            {
                "path": a["path"],
                "size": int(a["size"]),
                "partitionValues": dict(a.get("partitionValues") or {}),
                "stats": a.get("stats"),
            }
            for a in snap.files.values()
            if matches(a.get("partitionValues") or {}, partitions)
        ]

    def history(self, path: Path) -> list[dict[str, Any]]:
        out = []
        for v in dlog.list_versions(path):
            info = next(
                (a["commitInfo"] for a in dlog.read_commit(path, v) if "commitInfo" in a), {}
            )
            out.append(
                {
                    "version": v,
                    "timestamp": info.get("timestamp"),
                    "operation": info.get("operation"),
                    "operationParameters": info.get("operationParameters", {}),
                }
            )
        return out

    def protocol(self, path: Path) -> dict[str, Any]:
        p = self.snapshot(path).protocol
        return {
            "minReaderVersion": int(p.get("minReaderVersion", 1)),
            "minWriterVersion": int(p.get("minWriterVersion", 2)),
            "readerFeatures": p.get("readerFeatures"),
            "writerFeatures": p.get("writerFeatures"),
        }

    # ----------------------------------------------------------------- writes

    def _write_files(
        self, root: Path, table: pa.Table, partition_by: list[str]
    ) -> list[dict[str, Any]]:
        """Write data files (partition columns removed) and return their add actions."""
        groups: list[tuple[dict[str, str | None], pa.Table]] = []
        if partition_by:
            keys = table.select(partition_by).to_pylist()
            buckets: dict[tuple, list[int]] = {}
            for i, k in enumerate(keys):
                buckets.setdefault(tuple(k[c] for c in partition_by), []).append(i)
            for key, rows in buckets.items():
                part = table.take(pa.array(rows, pa.int64())).drop_columns(partition_by)
                groups.append((dict(zip(partition_by, key)), part))
        else:
            groups.append(({}, table))
        adds = []
        for pvals, data in groups:
            rel_dirs = [f"{c}={escape_partition_value(pvals[c])}" for c in partition_by]
            name = f"part-00000-{uuid.uuid4()}-c000.snappy.parquet"
            target = root.joinpath(*rel_dirs, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(data, target, compression="snappy")
            adds.append(
                {
                    "add": {
                        "path": to_add_path("/".join([*rel_dirs, name])),
                        "partitionValues": pvals,
                        "size": target.stat().st_size,
                        "modificationTime": _now_ms(),
                        "dataChange": True,
                        "stats": file_stats(data),
                    }
                }
            )
        return adds

    @staticmethod
    def _commit_info(
        mode: str, partition_by: list[str], n_files: int, n_rows: int
    ) -> dict[str, Any]:
        return {
            "commitInfo": {
                "timestamp": _now_ms(),
                "operation": "WRITE",
                "operationParameters": {
                    "mode": mode.capitalize(),
                    "partitionBy": str(partition_by),
                },
                "engineInfo": ENGINE,
                "operationMetrics": {"num_added_files": n_files, "num_added_rows": n_rows},
            }
        }

    @staticmethod
    def _new_metadata(schema: pa.Schema, partition_by: list[str]) -> dict[str, Any]:
        return {
            "metaData": {
                "id": str(uuid.uuid4()),
                "name": None,
                "description": None,
                "format": {"provider": "parquet", "options": {}},
                "schemaString": schema_to_delta_json(schema),
                "partitionColumns": partition_by,
                "configuration": {},
                "createdTime": _now_ms(),
            }
        }

    def write(
        self,
        path: Path,
        table: pa.Table,
        *,
        mode: str = "append",
        partition_by: list[str] | None = None,
    ) -> int:
        if mode not in ("append", "overwrite"):
            raise MayaDeltaError(f"Unsupported write mode '{mode}'")
        partition_by = list(partition_by or [])
        if mode == "append" and not partition_by and self.exists(path):
            partition_by = self.snapshot(path).partition_columns
        for col in partition_by:
            if col not in table.column_names:
                raise MayaDeltaError(f"Partition column '{col}' is not in the table")
        schema = normalise_schema(table.schema)
        adds = self._write_files(path, table, partition_by)
        for attempt in range(MAX_COMMIT_ATTEMPTS):
            version = self._try_once(path, schema, adds, mode, partition_by, table.num_rows)
            if version is not None:
                self._maybe_checkpoint(path, version)
                return version
        raise ConcurrentModification(
            f"Gave up committing to {path} after {MAX_COMMIT_ATTEMPTS} attempts"
        )

    def _try_once(
        self,
        path: Path,
        schema: pa.Schema,
        adds: list[dict[str, Any]],
        mode: str,
        partition_by: list[str],
        n_rows: int,
    ) -> int | None:
        """One commit attempt; None when another writer won the version."""
        info = self._commit_info(mode, partition_by, len(adds), n_rows)
        if not self.exists(path):
            actions = [
                info,
                {"protocol": _protocol_for(schema)},
                self._new_metadata(schema, partition_by),
                *adds,
            ]
            return 0 if dlog.try_commit(path, 0, actions) else None
        snap = self.snapshot(path)
        dlog.check_writer_protocol(snap)
        current = schema_from_delta_json(snap.metadata["schemaString"])
        actions: list[dict[str, Any]] = [info]
        if mode == "append":
            self._check_append(snap, current, schema, partition_by)
        else:
            if (
                "appendOnly" in (snap.protocol.get("writerFeatures") or [])
                or snap.metadata.get("configuration", {}).get("delta.appendOnly") == "true"
            ):
                raise UnsupportedFeature("appendOnly", "table is append-only; overwrite refused")
            if _needs_ntz(schema) and "timestampNtz" not in (
                snap.protocol.get("writerFeatures") or []
            ):
                actions.append({"protocol": _protocol_for(schema, snap.protocol)})
            if not current.equals(schema) or snap.partition_columns != partition_by:
                md = self._new_metadata(schema, partition_by)
                md["metaData"]["id"] = snap.metadata.get("id")
                actions.append(md)
            now = _now_ms()
            actions += [
                {
                    "remove": {
                        "path": p,
                        "deletionTimestamp": now,
                        "dataChange": True,
                        "partitionValues": a.get("partitionValues"),
                        "size": a.get("size"),
                    }
                }
                for p, a in snap.files.items()
            ]
        actions += adds
        version = snap.version + 1
        if dlog.try_commit(path, version, actions):
            return version
        if mode == "overwrite":
            raise ConcurrentModification(
                f"A concurrent commit won version {version}; overwrite not retried"
            )
        self._check_winner(path, version)
        return None

    @staticmethod
    def _check_append(
        snap: dlog.Snapshot, current: pa.Schema, schema: pa.Schema, partition_by: list[str]
    ) -> None:
        if not current.equals(schema):
            raise MayaDeltaError(
                f"Append schema does not match the table schema:\ntable: {current}\nwrite: {schema}"
            )
        if partition_by and partition_by != snap.partition_columns:
            raise MayaDeltaError(
                f"Append partition_by {partition_by} does not match "
                f"table partitioning {snap.partition_columns}"
            )

    @staticmethod
    def _check_winner(path: Path, version: int) -> None:
        """An append may be retried only if the winning commit left schema and files intact."""
        for action in dlog.read_commit(path, version):
            if "metaData" in action or "protocol" in action:
                raise ConcurrentModification(f"Concurrent commit {version} changed table metadata")
            if "remove" in action:
                raise ConcurrentModification(f"Concurrent commit {version} removed files")

    # ------------------------------------------------------------ maintenance

    def optimize(self, path: Path, *, target_size: int) -> dict[str, Any]:
        from maya_delta.pure import maintenance

        return maintenance.optimize(self, path, target_size=target_size)

    def vacuum(
        self, path: Path, *, retention_hours: float, dry_run: bool, enforce_retention: bool
    ) -> list[str]:
        from maya_delta.pure import maintenance

        return maintenance.vacuum(
            self,
            path,
            retention_hours=retention_hours,
            dry_run=dry_run,
            enforce_retention=enforce_retention,
        )

    def _maybe_checkpoint(self, path: Path, version: int) -> None:
        if version > 0 and version % dlog.CHECKPOINT_INTERVAL == 0:
            dlog.write_checkpoint(path, self.snapshot(path, version))
