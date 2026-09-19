"""
Table maintenance for the pure backend: compaction (``OPTIMIZE``) and ``VACUUM``.

Compaction rewrites the small files of each partition into files of about the
target size, in one commit whose ``remove`` and ``add`` actions carry
``dataChange: false`` — the table's content is unchanged, only its layout. Rows
keep their snapshot order within each partition. A concurrent append is not a
conflict; a concurrent commit that removed any file being compacted is.

Vacuum deletes data files the current snapshot no longer references once they
are older than the retention window: a file removed by a commit counts from its
``deletionTimestamp``, an untracked file (left by a failed write) from its
modification time. Files the snapshot references are never touched, nor is the
log. Time travel to versions whose files were vacuumed stops working, which is
why retention below seven days must be asked for explicitly.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from maya_delta.errors import ConcurrentModification, MayaDeltaError
from maya_delta.files import read_files
from maya_delta.pure import log as dlog
from maya_delta.schema import schema_from_delta_json

DEFAULT_TARGET = 128 * 1024 * 1024
DEFAULT_RETENTION_HOURS = 168
MAX_ATTEMPTS = 50


def _now_ms() -> int:
    return int(time.time() * 1000)


def _bins(files: list[dict[str, Any]], target: int) -> list[list[dict[str, Any]]]:
    """Consecutive small files grouped into bins of about ``target`` bytes (2+ files each)."""
    small = [f for f in files if int(f["size"]) < target]
    bins: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for f in small:
        if current and size + int(f["size"]) > target:
            bins.append(current)
            current, size = [], 0
        current.append(f)
        size += int(f["size"])
    if current:
        bins.append(current)
    return [b for b in bins if len(b) >= 2]


def optimize(backend: Any, path: Path, *, target_size: int = DEFAULT_TARGET) -> dict[str, Any]:
    """Compact small files per partition; returns what was done."""
    for _ in range(MAX_ATTEMPTS):
        snap = backend.snapshot(path)
        dlog.check_writer_protocol(snap)
        schema = schema_from_delta_json(snap.metadata["schemaString"])
        parts = snap.partition_columns
        groups: dict[tuple, list[dict[str, Any]]] = {}
        for a in snap.files.values():
            key = tuple((c, (a.get("partitionValues") or {}).get(c)) for c in parts)
            groups.setdefault(key, []).append(a)
        plan = [b for files in groups.values() for b in _bins(files, target_size)]
        result = {"version": snap.version, "numFilesRemoved": 0, "numFilesAdded": 0,
                  "partitionsOptimized": 0, "numRows": 0}
        if not plan:
            return result
        actions: list[dict[str, Any]] = []
        now = _now_ms()
        for group in plan:
            table = read_files(path, group, schema, parts, None)
            adds = backend._write_files(path, table, parts)
            for add in adds:
                add["add"]["dataChange"] = False
            actions += [{"remove": {"path": a["path"], "deletionTimestamp": now,
                                    "dataChange": False,
                                    "partitionValues": a.get("partitionValues"),
                                    "size": a.get("size")}} for a in group]
            actions += adds
            result["numFilesRemoved"] += len(group)
            result["numFilesAdded"] += len(adds)
            result["numRows"] += table.num_rows
        result["partitionsOptimized"] = len({tuple(sorted((g[0].get("partitionValues") or {})
                                                          .items())) for g in plan})
        info = {"commitInfo": {"timestamp": now, "operation": "OPTIMIZE",
                               "operationParameters": {"targetSize": str(target_size)},
                               "engineInfo": "maya_delta-pure",
                               "operationMetrics": {k: result[k] for k in (
                                   "numFilesRemoved", "numFilesAdded")}}}
        version = snap.version + 1
        if dlog.try_commit(path, version, [info, *actions]):
            backend._maybe_checkpoint(path, version)
            return {**result, "version": version}
        _check_winner(path, version, {a["path"] for g in plan for a in g})
        _discard(path, [a["add"]["path"] for a in actions if "add" in a])
    raise ConcurrentModification(f"Gave up compacting {path} after {MAX_ATTEMPTS} attempts")


def _check_winner(path: Path, version: int, ours: set[str]) -> None:
    for action in dlog.read_commit(path, version):
        if "metaData" in action or "protocol" in action:
            raise ConcurrentModification(f"Concurrent commit {version} changed table metadata")
        if "remove" in action and action["remove"]["path"] in ours:
            raise ConcurrentModification(f"Concurrent commit {version} removed a file being "
                                         "compacted")


def _discard(root: Path, add_paths: list[str]) -> None:
    for p in add_paths:
        target = root.joinpath(*unquote(p).split("/"))
        target.unlink(missing_ok=True)


def vacuum(backend: Any, path: Path, *, retention_hours: float = DEFAULT_RETENTION_HOURS,
           dry_run: bool = False, enforce_retention: bool = True) -> list[str]:
    """Delete unreferenced data files older than the retention window; returns them."""
    if enforce_retention and retention_hours < DEFAULT_RETENTION_HOURS:
        raise MayaDeltaError(f"Retention of {retention_hours}h is below the "
                             f"{DEFAULT_RETENTION_HOURS}h minimum; pass enforce_retention=False "
                             "to vacuum more aggressively (time travel past it stops working)")
    snap = backend.snapshot(path)
    live = {unquote(p) for p in snap.files}
    tombstones: dict[str, int] = {}
    for v in dlog.list_versions(path):
        for action in dlog.read_commit(path, v):
            if "remove" in action:
                r = action["remove"]
                tombstones[unquote(r["path"])] = int(r.get("deletionTimestamp") or 0)
    cutoff_ms = _now_ms() - int(retention_hours * 3600 * 1000)
    doomed = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d != "_delta_log" and not d.startswith(".")]
        for name in filenames:
            if name.startswith(("_", ".")):
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(path).as_posix()
            if rel in live:
                continue
            born = tombstones.get(rel, int(full.stat().st_mtime * 1000))
            if born < cutoff_ms:
                doomed.append(rel)
    if not dry_run:
        for rel in doomed:
            (path / rel).unlink(missing_ok=True)
        _prune_empty_dirs(path)
    return sorted(doomed)


def _prune_empty_dirs(root: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        d = Path(dirpath)
        if d == root or d.name.startswith(".") or "_delta_log" in d.relative_to(root).parts:
            continue
        if not any(d.iterdir()):
            d.rmdir()


__all__ = ["optimize", "vacuum", "DEFAULT_TARGET", "DEFAULT_RETENTION_HOURS"]
