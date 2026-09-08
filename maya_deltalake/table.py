"""
maya_deltalake — the six calls MAYA makes.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

`DeltaTable` and `write_deltalake`, shaped exactly like the ones in the
`deltalake` package for the arguments MAYA passes — and refusing, by name,
everything else. The signatures accept the extra keywords the real functions
take so that a caller passing one gets a sentence rather than a TypeError, and
so the refusal names the feature rather than the argument.
"""
from __future__ import annotations

import errno
import os
import pathlib
import uuid
from typing import Any, Dict, List, Optional, Tuple

from maya_deltalake.protocol import (DeltaProtocolError, add_action,
                                     check_readable, commit_info, commit_name,
                                     metadata_action, now_ms, protocol_action,
                                     remove_action, replay)

LOG = "_delta_log"


def _log_dir(root: pathlib.Path) -> pathlib.Path:
    return root / LOG


def _commits(root: pathlib.Path, upto: Optional[int] = None
             ) -> List[Tuple[int, str]]:
    """Every commit up to and including `upto`, in version order.

    Sorted by the integer rather than by the filename. The zero-padding makes
    those agree today and the sort is written on the number anyway, because a
    format detail holding an invariant up is a format detail somebody will
    change.
    """
    directory = _log_dir(root)
    if not directory.is_dir():
        return []
    found: List[Tuple[int, str]] = []
    for entry in directory.iterdir():
        if entry.suffix != ".json" or not entry.stem.isdigit():
            continue                       # checkpoints, _last_checkpoint, CRCs
        version = int(entry.stem)
        if upto is not None and version > upto:
            continue
        found.append((version, entry.read_text(encoding="utf-8")))
    found.sort(key=lambda pair: pair[0])
    return found


def _latest_version(root: pathlib.Path) -> int:
    directory = _log_dir(root)
    if not directory.is_dir():
        return -1
    versions = [int(e.stem) for e in directory.iterdir()
                if e.suffix == ".json" and e.stem.isdigit()]
    return max(versions) if versions else -1


class DeltaTable:
    """A Delta table on a local filesystem, read through its transaction log."""

    def __init__(self, table_uri: Any, version: Optional[int] = None,
                 storage_options: Optional[Dict[str, str]] = None, **unsupported):
        if storage_options:
            raise DeltaProtocolError(
                "maya_deltalake reads a local filesystem only, and "
                "`storage_options` configures an object store. Install the "
                "`deltalake` package for S3, GCS or Azure.")
        if unsupported:
            raise DeltaProtocolError(
                f"maya_deltalake does not support {', '.join(sorted(unsupported))}. "
                f"It implements the subset MAYA uses; install the `deltalake` "
                f"package for the rest.")
        self.table_uri = str(table_uri)
        self._root = pathlib.Path(self.table_uri)
        if not _log_dir(self._root).is_dir():
            raise DeltaProtocolError(
                f"no Delta table at {self.table_uri}: there is no {LOG} "
                f"directory. A path that is not a table and a table that is "
                f"empty are different answers, and this is the first.")
        self._pinned: Optional[int] = None
        self._state: Optional[Dict[str, Any]] = None
        if version is not None:
            self.load_as_version(version)

    # ----------------------------------------------------------------- state
    def version(self) -> int:
        """The version being read: the one pinned, or the latest."""
        return self._pinned if self._pinned is not None \
            else _latest_version(self._root)

    def load_as_version(self, version: int) -> None:
        """Time travel. Pin the read to a past version.

        Refuses a version that never existed rather than clamping to the
        newest, because "as it stood at version 9" answered with version 4 is
        the wrong answer delivered confidently — and every caller of this is
        reproducing something.
        """
        latest = _latest_version(self._root)
        if version < 0 or version > latest:
            raise DeltaProtocolError(
                f"version {version} does not exist in {self.table_uri}; the "
                f"table has 0..{latest}. Reading the nearest one instead "
                f"would answer a question nobody asked.")
        self._pinned, self._state = version, None

    def _load(self) -> Dict[str, Any]:
        if self._state is None:
            state = replay(_commits(self._root, self._pinned))
            check_readable(state["protocol"])
            self._state = state
        return self._state

    def files(self) -> List[str]:
        """The data files live at this version, relative to the table."""
        return [entry["path"] for entry in self._load()["files"]]

    @property
    def schema_string(self) -> Optional[str]:
        metadata = self._load()["metadata"]
        return metadata.get("schemaString") if metadata else None

    def metadata(self) -> Optional[Dict[str, Any]]:
        return self._load()["metadata"]

    # ------------------------------------------------------------ the reads
    def to_pyarrow_dataset(self, **unsupported) -> Any:
        """A pyarrow Dataset over the live files. Streams; never loads whole.

        This is what MAYA's transfer layer reads, precisely so that a large
        table moves in record batches rather than as one object — so returning
        something that materialises would be answering the call and defeating
        its purpose.
        """
        import pyarrow.dataset as ds

        if unsupported:
            raise DeltaProtocolError(
                f"maya_deltalake's to_pyarrow_dataset takes no "
                f"{', '.join(sorted(unsupported))}")
        paths = [str(self._root / name) for name in self.files()]
        if not paths:
            # An empty table still has a schema, and a dataset with no schema
            # would make `dataset.schema.names` raise where the real one
            # returns an empty answer.
            import pyarrow as pa

            return ds.dataset([], schema=self._empty_schema()
                              or pa.schema([]), format="parquet")
        return ds.dataset(paths, format="parquet")

    def _empty_schema(self) -> Any:
        """The declared schema, as Arrow, for a table with no files left."""
        import pyarrow as pa

        from maya_deltalake.protocol import schema_fields

        text = self.schema_string
        if not text:
            return None
        reverse = {"string": pa.string(), "long": pa.int64(),
                   "integer": pa.int32(), "short": pa.int16(),
                   "byte": pa.int8(), "double": pa.float64(),
                   "float": pa.float32(), "boolean": pa.bool_(),
                   "binary": pa.binary(), "date": pa.date32(),
                   "timestamp": pa.timestamp("us")}
        fields = []
        for field in schema_fields(text):
            kind = field.get("type")
            if isinstance(kind, str) and kind.startswith("decimal"):
                precision, scale = kind[len("decimal("):-1].split(",")
                fields.append(pa.field(field["name"],
                                       pa.decimal128(int(precision), int(scale))))
            else:
                fields.append(pa.field(field["name"],
                                       reverse.get(kind, pa.string())))
        return pa.schema(fields)

    def to_pyarrow_table(self) -> Any:
        import pyarrow as pa

        dataset = self.to_pyarrow_dataset()
        table = dataset.to_table()
        return table if table.num_rows or table.num_columns else pa.table({})

    def to_pandas(self) -> Any:
        """The whole table as a DataFrame, in the order the files were added.

        Stable within this implementation, and NOT something a caller may rely
        on across implementations: `deltalake` returns the same rows in its own
        order, and both are entitled to. Delta guarantees a set of rows, not a
        sequence.

        That is safe here because MAYA does not depend on it. The bitemporal
        read in `db/delta_store.py` sorts by `pit_order_key`, which is total
        and content-based precisely so that two point-in-time implementations
        cannot break a tie opposite ways — its own comment says "a Delta
        rewrite cannot change the answer". Swapping the backend is a Delta
        rewrite by another name, so the property that was built to stop two
        readers disagreeing is the property that makes a second writer safe.
        """
        import pandas as pd

        paths = self.files()
        if not paths:
            schema = self._empty_schema()
            return pd.DataFrame(columns=[f.name for f in schema]) if schema \
                else pd.DataFrame()
        return self.to_pyarrow_table().to_pandas()


# ------------------------------------------------------------------ writing
def write_deltalake(table_or_uri: Any, data: Any, *, mode: str = "error",
                    schema_mode: Optional[str] = None,
                    partition_by: Optional[List[str]] = None,
                    storage_options: Optional[Dict[str, str]] = None,
                    name: Optional[str] = None,
                    description: Optional[str] = None,
                    **unsupported) -> None:
    """Write a frame as a new version of a Delta table.

    `mode` is `append`, `overwrite`, `error` or `ignore`. An overwrite REMOVES
    the live files and ADDS the new one; the removed bytes stay on disk, which
    is what makes time travel back past an overwrite work at all.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    if partition_by:
        raise DeltaProtocolError(
            "maya_deltalake does not partition. MAYA writes no partitioned "
            "table, and a partitioned one written here would be read wrongly "
            "by anything that expects the partition values in the log.")
    if storage_options:
        raise DeltaProtocolError(
            "maya_deltalake writes to a local filesystem only. Install the "
            "`deltalake` package for S3, GCS or Azure.")
    if unsupported:
        raise DeltaProtocolError(
            f"maya_deltalake's write_deltalake does not support "
            f"{', '.join(sorted(unsupported))}. It implements the subset MAYA "
            f"uses; install the `deltalake` package for the rest.")
    if mode not in ("append", "overwrite", "error", "ignore"):
        raise DeltaProtocolError(
            f"'{mode}' is not a write mode; use append, overwrite, error or "
            f"ignore")

    root = pathlib.Path(str(getattr(table_or_uri, "table_uri", table_or_uri)))
    exists = _log_dir(root).is_dir()
    if exists and mode == "error":
        raise DeltaProtocolError(
            f"a Delta table already exists at {root}. Pass mode='append' to "
            f"add to it or mode='overwrite' to replace it.")
    if exists and mode == "ignore":
        return

    table = data if isinstance(data, pa.Table) else _as_arrow(data)
    previous = replay(_commits(root)) if exists else {"files": [],
                                                      "metadata": None}

    if exists and mode == "append" and previous["metadata"]:
        _check_appendable(previous["metadata"], table.schema)

    root.mkdir(parents=True, exist_ok=True)
    _log_dir(root).mkdir(parents=True, exist_ok=True)

    filename = f"part-00000-{uuid.uuid4()}-c000.snappy.parquet"
    pq.write_table(table, root / filename, compression="snappy")
    size = (root / filename).stat().st_size
    moment = now_ms()

    actions: List[Dict[str, Any]] = []
    version = _latest_version(root) + 1
    replacing_schema = (not exists) or mode == "overwrite" or (
        schema_mode == "overwrite")
    if version == 0:
        actions.append(protocol_action())
    if replacing_schema or not previous["metadata"]:
        keep = previous["metadata"] or {}
        actions.append(metadata_action(
            table.schema, table_id=keep.get("id"),
            created_ms=keep.get("createdTime")))
    removed = 0
    if mode == "overwrite":
        for entry in previous["files"]:
            actions.append(remove_action(entry["path"], entry.get("size"),
                                         moment))
            removed += 1
    actions.append(add_action(filename, size, table.num_rows, moment))
    actions.insert(0, commit_info(
        "WRITE", {"mode": mode.capitalize()},
        {"num_added_files": 1, "num_removed_files": removed,
         "num_partitions": 0, "num_added_rows": table.num_rows}, moment))

    _commit(root, version, actions, orphan=root / filename)


def _as_arrow(data: Any) -> Any:
    """A pandas DataFrame, a list of dicts, or anything Arrow already knows."""
    import pyarrow as pa

    if hasattr(data, "to_dict") and hasattr(data, "columns"):
        return pa.Table.from_pandas(data, preserve_index=False)
    if isinstance(data, list):
        return pa.Table.from_pylist(data)
    if isinstance(data, pa.RecordBatch):
        return pa.Table.from_batches([data])
    raise DeltaProtocolError(
        f"maya_deltalake writes a pandas DataFrame, a list of dicts or an "
        f"Arrow table; it was given {type(data).__name__}")


def _check_appendable(metadata: Dict[str, Any], schema: Any) -> None:
    """An append must fit the schema the table already declares.

    The real implementation raises `SchemaMismatchError` here and MAYA relies
    on it: `DeltaStore.write` passes `schema_mode="overwrite"` precisely
    because an overwrite of an orphaned table may carry a different set of
    features. Silently widening the schema on an append would let a
    materialisation write columns the contract never pinned.
    """
    from maya_deltalake.protocol import delta_type, schema_fields

    declared = {f["name"]: f["type"] for f in
                schema_fields(metadata.get("schemaString", "{}"))}
    incoming = {field.name: delta_type(field.type) for field in schema}
    added = sorted(set(incoming) - set(declared))
    changed = sorted(name for name in set(incoming) & set(declared)
                     if incoming[name] != declared[name])
    if added or changed:
        detail = []
        if added:
            detail.append(f"new column(s) {', '.join(added)}")
        if changed:
            detail.append("changed type(s) " + ", ".join(
                f"{n}: {declared[n]} -> {incoming[n]}" for n in changed))
        raise DeltaProtocolError(
            f"this append does not match the table's schema — {'; '.join(detail)}. "
            f"Pass mode='overwrite' with schema_mode='overwrite' to replace "
            f"the schema, or write the columns the table declares.")


def _commit(root: pathlib.Path, version: int, actions: List[Dict[str, Any]],
            orphan: Optional[pathlib.Path] = None) -> None:
    """Write the commit file, and fail rather than overwrite one.

    `O_EXCL` is the protocol's concurrency primitive on a POSIX filesystem:
    two writers racing for version N means exactly one creates the file and the
    other gets EEXIST. That is enough here because MAYA serialises Delta writes
    above this layer, and it is NOT enough on NFS or an object store, where
    exclusive create is not atomic — which is why this refuses to be pointed at
    one rather than appearing to work.

    On a lost race the Parquet file just written is REMOVED. Leaving it would
    orphan bytes no commit references: harmless to a reader, and indefinitely
    confusing to a person looking at the directory wondering which files count.
    """
    import json

    path = _log_dir(root) / commit_name(version)
    body = "\n".join(json.dumps(action, separators=(",", ":"))
                     for action in actions) + "\n"
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        if orphan is not None and orphan.is_file():
            orphan.unlink()
        raise DeltaProtocolError(
            f"version {version} of {root} was written by somebody else while "
            f"this write was in flight. Retry; the data file this attempt "
            f"wrote has been removed rather than left orphaned.") from exc
    except OSError as exc:                      # pragma: no cover
        if exc.errno == errno.EEXIST:
            raise DeltaProtocolError(f"version {version} already exists") from exc
        raise
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(body)
            out.flush()
            # The commit is the moment the version exists. Everything before it
            # is bytes nobody references; everything after reads it. Forcing it
            # to disk is what makes that true across a power cut rather than
            # only across a process exit.
            os.fsync(out.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
