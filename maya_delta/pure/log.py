"""
The Delta transaction log — MAYA's own implementation of the declared subset.

Supported actions: ``protocol``, ``metaData``, ``add``, ``remove``,
``commitInfo`` (``txn`` is read and ignored). Supported checkpoints: classic
single-file and multi-part Parquet checkpoints, located through
``_last_checkpoint`` or by listing the log. Commits are made atomic by
exclusive create (``open(path, "x")``) of the next log entry, which is atomic on
NTFS, ext4 and APFS and needs no lock daemon.

Anything the table requires that is not in the supported sets below is refused
by name (``UnsupportedFeature``) rather than approximated.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from maya_delta.errors import MayaDeltaError, TableNotFound, UnsupportedFeature

# Reader features we implement. timestampNtz is only a type, which we map.
SUPPORTED_READER_FEATURES = frozenset({"timestampNtz"})
# Writer features we honour when writing. appendOnly is enforced (no overwrite);
# invariants is accepted only while no field declares one.
SUPPORTED_WRITER_FEATURES = frozenset({"appendOnly", "invariants", "timestampNtz"})
# Legacy (pre-feature) protocol versions and what they imply.
LEGACY_READER = {2: "columnMapping"}
LEGACY_WRITER = {
    3: "checkConstraints",
    4: "changeDataFeed/generatedColumns",
    5: "columnMapping",
    6: "identityColumns",
}

CHECKPOINT_INTERVAL = 10
_COMMIT_RE = re.compile(r"^(\d{20})\.json$")
_CKPT_RE = re.compile(r"^(\d{20})\.checkpoint(?:\.(\d{10})\.(\d{10}))?\.parquet$")
_V2_CKPT_RE = re.compile(r"^(\d{20})\.checkpoint\.[0-9a-fA-F-]{36}\.(json|parquet)$")


def log_dir(root: Path) -> Path:
    return root / "_delta_log"


def commit_path(root: Path, version: int) -> Path:
    return log_dir(root) / f"{version:020d}.json"


@dataclass
class Snapshot:
    """The replayed state of a table at one version."""

    version: int
    protocol: dict[str, Any]
    metadata: dict[str, Any]
    files: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )  # path -> add action, in add order

    @property
    def partition_columns(self) -> list[str]:
        return list(self.metadata.get("partitionColumns") or [])


def list_versions(root: Path) -> list[int]:
    """Every commit version with a JSON entry in the log, ascending."""
    d = log_dir(root)
    if not d.is_dir():
        return []
    return sorted(int(m.group(1)) for p in d.iterdir() if (m := _COMMIT_RE.match(p.name)))


def _checkpoints(root: Path) -> dict[int, list[Path]]:
    """Checkpoint parts by version. A v2 checkpoint is refused by name."""
    found: dict[int, list[Path]] = {}
    for p in log_dir(root).iterdir():
        if _V2_CKPT_RE.match(p.name):
            raise UnsupportedFeature("v2Checkpoint", f"log contains {p.name}")
        m = _CKPT_RE.match(p.name)
        if m:
            found.setdefault(int(m.group(1)), []).append(p)
    return found


def latest_version(root: Path) -> int:
    """The newest version, from commits or a checkpoint; TableNotFound if none."""
    d = log_dir(root)
    if not d.is_dir():
        raise TableNotFound(f"No Delta table at {root}")
    versions = list_versions(root)
    ckpts = _checkpoints(root)
    candidates = versions + list(ckpts)
    if not candidates:
        raise TableNotFound(f"No Delta table at {root}")
    return max(candidates)


def read_commit(root: Path, version: int) -> list[dict[str, Any]]:
    """The actions of one JSON commit, in file order."""
    text = commit_path(root, version).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _map_to_dict(value: Any) -> dict[str, Any]:
    """Checkpoint map columns arrive as lists of (key, value) pairs."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {k: v for k, v in value}


def _clean_add(add: dict[str, Any]) -> dict[str, Any]:
    out = dict(add)
    out["partitionValues"] = _map_to_dict(add.get("partitionValues"))
    if out.get("deletionVector"):
        raise UnsupportedFeature("deletionVectors", f"file {add.get('path')} carries one")
    return out


def _read_checkpoint(parts: list[Path]) -> list[dict[str, Any]]:
    """Checkpoint rows turned back into single-key action dicts."""
    actions: list[dict[str, Any]] = []
    for part in sorted(parts):
        table = pq.read_table(part)
        wanted = [c for c in ("protocol", "metaData", "add", "remove") if c in table.column_names]
        for row in table.select(wanted).to_pylist():
            for key in wanted:
                if row.get(key) is not None:
                    actions.append({key: row[key]})
    return actions


def _apply(snap: Snapshot, actions: list[dict[str, Any]]) -> None:
    for action in actions:
        if "protocol" in action:
            snap.protocol = action["protocol"]
        elif "metaData" in action:
            md = dict(action["metaData"])
            md["configuration"] = _map_to_dict(md.get("configuration"))
            snap.metadata = md
        elif "add" in action:
            add = _clean_add(action["add"])
            snap.files.pop(add["path"], None)
            snap.files[add["path"]] = add
        elif "remove" in action:
            snap.files.pop(action["remove"]["path"], None)


def check_reader_protocol(
    protocol: dict[str, Any], configuration: dict[str, Any] | None = None
) -> None:
    """Refuse, by name, a table this reader cannot faithfully read."""
    rv = int(protocol.get("minReaderVersion", 1))
    for feature in protocol.get("readerFeatures") or []:
        if feature not in SUPPORTED_READER_FEATURES:
            raise UnsupportedFeature(feature, "reader feature not implemented by the pure backend")
    if (
        rv in LEGACY_READER
        and (configuration or {}).get("delta.columnMapping.mode", "none") != "none"
    ):
        raise UnsupportedFeature(LEGACY_READER[rv])
    if rv > 3:
        raise UnsupportedFeature(f"readerVersion{rv}")


def check_writer_protocol(snap: Snapshot) -> None:
    """Refuse, by name, a table this writer cannot safely append to."""
    wv = int(snap.protocol.get("minWriterVersion", 2))
    features = snap.protocol.get("writerFeatures") or []
    for feature in features:
        if feature not in SUPPORTED_WRITER_FEATURES:
            raise UnsupportedFeature(feature, "writer feature not implemented by the pure backend")
    if wv in LEGACY_WRITER:
        raise UnsupportedFeature(LEGACY_WRITER[wv], f"implied by minWriterVersion {wv}")
    if wv > 7:
        raise UnsupportedFeature(f"writerVersion{wv}")
    from maya_delta.schema import field_metadata_has

    if field_metadata_has(snap.metadata.get("schemaString", '{"fields":[]}'), "delta.invariants"):
        raise UnsupportedFeature(
            "invariants", "a field declares an invariant the pure writer cannot enforce"
        )


def load_snapshot(root: Path, version: int | None = None) -> Snapshot:
    """Replay the log (from the best checkpoint at or below ``version``)."""
    latest = latest_version(root)
    target = latest if version is None else version
    if target < 0 or target > latest:
        raise MayaDeltaError(f"Version {target} does not exist (latest is {latest})")
    ckpts = {v: p for v, p in _checkpoints(root).items() if v <= target}
    snap = Snapshot(version=target, protocol={}, metadata={})
    start = 0
    if ckpts:
        base = max(ckpts)
        _apply(snap, _read_checkpoint(ckpts[base]))
        start = base + 1
    have = set(list_versions(root))
    for v in range(start, target + 1):
        if v not in have:
            raise MayaDeltaError(f"Log entry {v} is missing and no checkpoint covers it")
        _apply(snap, read_commit(root, v))
    if not snap.metadata:
        raise MayaDeltaError(f"Table at {root} has no metaData action")
    check_reader_protocol(snap.protocol, snap.metadata.get("configuration"))
    return snap


def try_commit(root: Path, version: int, actions: list[dict[str, Any]]) -> bool:
    """Atomically create log entry ``version``. False if someone else won it."""
    log_dir(root).mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(a, separators=(",", ":")) + "\n" for a in actions)
    try:
        with open(commit_path(root, version), "x", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
    except FileExistsError:
        return False
    return True


# ------------------------------------------------------------------ checkpoints

_PROTOCOL_T = pa.struct(
    [
        ("minReaderVersion", pa.int32()),
        ("minWriterVersion", pa.int32()),
        ("readerFeatures", pa.list_(pa.string())),
        ("writerFeatures", pa.list_(pa.string())),
    ]
)
_METADATA_T = pa.struct(
    [
        ("id", pa.string()),
        ("name", pa.string()),
        ("description", pa.string()),
        (
            "format",
            pa.struct([("provider", pa.string()), ("options", pa.map_(pa.string(), pa.string()))]),
        ),
        ("schemaString", pa.string()),
        ("partitionColumns", pa.list_(pa.string())),
        ("configuration", pa.map_(pa.string(), pa.string())),
        ("createdTime", pa.int64()),
    ]
)
_ADD_T = pa.struct(
    [
        ("path", pa.string()),
        ("partitionValues", pa.map_(pa.string(), pa.string())),
        ("size", pa.int64()),
        ("modificationTime", pa.int64()),
        ("dataChange", pa.bool_()),
        ("stats", pa.string()),
    ]
)
_REMOVE_T = pa.struct(
    [("path", pa.string()), ("deletionTimestamp", pa.int64()), ("dataChange", pa.bool_())]
)


def _protocol_row(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "minReaderVersion": int(p.get("minReaderVersion", 1)),
        "minWriterVersion": int(p.get("minWriterVersion", 2)),
        "readerFeatures": p.get("readerFeatures"),
        "writerFeatures": p.get("writerFeatures"),
    }


def _metadata_row(md: dict[str, Any]) -> dict[str, Any]:
    fmt = md.get("format") or {"provider": "parquet", "options": {}}
    return {
        "id": md.get("id"),
        "name": md.get("name"),
        "description": md.get("description"),
        "format": {
            "provider": fmt.get("provider", "parquet"),
            "options": list(_map_to_dict(fmt.get("options")).items()),
        },
        "schemaString": md["schemaString"],
        "partitionColumns": md.get("partitionColumns") or [],
        "configuration": list(_map_to_dict(md.get("configuration")).items()),
        "createdTime": md.get("createdTime"),
    }


def _add_row(a: dict[str, Any]) -> dict[str, Any]:
    stats = a.get("stats")
    return {
        "path": a["path"],
        "partitionValues": list(_map_to_dict(a.get("partitionValues")).items()),
        "size": int(a["size"]),
        "modificationTime": int(a.get("modificationTime", 0)),
        "dataChange": bool(a.get("dataChange", True)),
        "stats": stats if isinstance(stats, str) or stats is None else json.dumps(stats),
    }


def write_checkpoint(root: Path, snap: Snapshot) -> None:
    """Classic single-file Parquet checkpoint of ``snap`` plus ``_last_checkpoint``."""
    rows: list[dict[str, Any]] = [
        {"protocol": _protocol_row(snap.protocol)},
        {"metaData": _metadata_row(snap.metadata)},
    ]
    rows += [{"add": _add_row(a)} for a in snap.files.values()]
    cols: dict[str, list[Any]] = {"protocol": [], "metaData": [], "add": [], "remove": []}
    for row in rows:
        for key in cols:
            cols[key].append(row.get(key))
    table = pa.table(
        {
            "protocol": pa.array(cols["protocol"], _PROTOCOL_T),
            "metaData": pa.array(cols["metaData"], _METADATA_T),
            "add": pa.array(cols["add"], _ADD_T),
            "remove": pa.array(cols["remove"], _REMOVE_T),
        }
    )
    final = log_dir(root) / f"{snap.version:020d}.checkpoint.parquet"
    tmp = final.with_name(final.name + ".tmp")
    pq.write_table(table, tmp)
    tmp.replace(final)
    last = log_dir(root) / "_last_checkpoint"
    tmp_last = last.with_name("_last_checkpoint.tmp")
    tmp_last.write_text(json.dumps({"version": snap.version, "size": len(rows)}), encoding="utf-8")
    tmp_last.replace(last)
