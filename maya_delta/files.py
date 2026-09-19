"""
Data-file decoding and statistics, shared by both backends.

Given the add actions of a snapshot, this module reads the Parquet files,
re-attaches the partition columns from ``partitionValues`` and conforms the
result to the table schema, so the two backends differ only in how they
arrive at the list of live files — never in how bytes become a table.

It also computes the per-file statistics (``numRecords``, ``minValues``,
``maxValues``, ``nullCount``) that the pure writer records on every add.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from maya_delta.schema import conform

HIVE_NULL = "__HIVE_DEFAULT_PARTITION__"
_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def escape_partition_value(value: str | None) -> str:
    """Hive-style directory escaping: every character outside [A-Za-z0-9._-]."""
    if value is None:
        return HIVE_NULL
    return "".join(c if c in _SAFE else "".join(f"%{b:02X}" for b in c.encode()) for c in value)


def to_add_path(relative_posix: str) -> str:
    """The URI-encoded ``path`` an add action stores for a relative file."""
    return quote(relative_posix, safe="/")


def from_add_path(root: Path, add_path: str) -> Path:
    """Filesystem location of an add action's file (relative paths only)."""
    rel = unquote(add_path)
    return root.joinpath(*rel.split("/"))


def matches(partition_values: dict[str, Any], wanted: dict[str, list[str]] | None) -> bool:
    """Partition pruning: every constrained column's value is in its allowed list."""
    if not wanted:
        return True
    for col, allowed in wanted.items():
        if partition_values.get(col) not in set(allowed):
            return False
    return True


PARALLEL_FROM = 16
READERS = min(8, os.cpu_count() or 1)


def read_files(root: Path, adds: list[dict[str, Any]], schema: pa.Schema,
               partition_columns: list[str], columns: list[str] | None = None) -> pa.Table:
    """Read ``adds`` in order, attach partition columns, conform to ``schema``."""
    out_schema = schema if columns is None else pa.schema([schema.field(c) for c in columns])
    data_cols = [f.name for f in out_schema if f.name not in partition_columns]
    def one(add: dict[str, Any]) -> pa.Table:
        path = from_add_path(root, add["path"])
        piece = pq.read_table(path, columns=data_cols, use_threads=False) if data_cols \
            else pq.read_metadata(path)
        if not isinstance(piece, pa.Table):  # partition-only projection
            piece = pa.table({"__n": pa.nulls(piece.num_rows)})
        pv = add.get("partitionValues") or {}
        for col in partition_columns:
            if col in out_schema.names:
                val = pv.get(col)
                piece = piece.append_column(col, pa.array([val] * piece.num_rows, pa.string()))
        return conform(piece, out_schema)

    # Many small files (a pin's fragments): read them side by side — the parquet reader
    # releases the GIL — and keep them in order.
    if len(adds) >= PARALLEL_FROM:
        with ThreadPoolExecutor(max_workers=READERS) as pool:
            pieces = list(pool.map(one, adds))
    else:
        pieces = [one(add) for add in adds]
    if not pieces:
        return out_schema.empty_table()
    return pa.concat_tables(pieces)


def _stat_value(v: Any) -> Any:
    if isinstance(v, _dt.datetime):
        if v.tzinfo is not None:
            v = v.astimezone(_dt.timezone.utc).replace(tzinfo=None)
            return v.isoformat(timespec="milliseconds") + "Z"
        return v.isoformat(timespec="milliseconds")
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def _statable(t: pa.DataType) -> bool:
    return (pa.types.is_integer(t) or pa.types.is_floating(t) or pa.types.is_string(t)
            or pa.types.is_date(t) or pa.types.is_timestamp(t) or pa.types.is_decimal(t))


def file_stats(table: pa.Table) -> str:
    """Delta ``stats`` JSON for one data file (top-level, non-nested columns only)."""
    mins: dict[str, Any] = {}
    maxs: dict[str, Any] = {}
    nulls: dict[str, int] = {}
    for f in table.schema:
        col = table.column(f.name)
        if pa.types.is_nested(f.type):
            continue  # nested stats are optional; delta-rs expects a nested shape for structs
        nulls[f.name] = col.null_count
        if not _statable(f.type) or col.null_count == len(col):
            continue
        if pa.types.is_floating(f.type) and pc.any(pc.is_nan(col)).as_py():
            continue
        mm = pc.min_max(col).as_py()
        lo, hi = mm["min"], mm["max"]
        if pa.types.is_string(f.type):
            if len(lo) > 32 or len(hi) > 32:
                continue
        mins[f.name], maxs[f.name] = _stat_value(lo), _stat_value(hi)
    return json.dumps({"numRecords": table.num_rows, "minValues": mins,
                       "maxValues": maxs, "nullCount": nulls}, separators=(",", ":"))
