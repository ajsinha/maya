"""
The canonical row encoding of ``maya.core.canonical``, computed a column at a time.

``canonical`` is the specification of a MAYA content hash: one value at a time, in
plain Python, so anyone can read it and a bundle can ship it. Pinning a million
rows through it costs a Python call per value. This module produces the *same
bytes* for every row — and so the same row digests — by encoding whole Arrow
columns with numpy and assembling each row's bytes by offset arithmetic; only the
final per-row sha256 remains a loop.

It covers the types pins are made of: floats, integers (up to int64 and uint32),
booleans, strings, dates (date32) and timestamps (s, ms, us). For any other type
``row_digests`` returns None and the caller uses the reference. Equality with the
reference is not assumed: ``tests/test_canonical_fast.py`` compares the two on
randomised tables with nulls, NaN, signed zeros, empty and non-ASCII strings,
extremes and every supported type.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from maya.core import canonical as ref

_TS_TO_US = {"s": 1_000_000, "ms": 1_000, "us": 1}
_CANON_NAN = np.frombuffer(ref._NAN, dtype=">f8")[0]


def _segments(col: Any) -> Any:
    """(per-row lengths, valid mask, encoded bytes, per-row start in those bytes) for one
    column, or None if its type is not covered. Each row's encoding is its tag byte
    followed by a body; a null is the single byte ``N``."""
    import pyarrow as pa
    import pyarrow.compute as pc
    t = col.type
    n = len(col)
    valid = np.asarray(col.is_valid()) if col.null_count else np.ones(n, dtype=bool)
    if pa.types.is_floating(t):
        v = pc.fill_null(col.cast(pa.float64()), 0.0).to_numpy(zero_copy_only=False)
        v = v + 0.0                                              # -0.0 -> 0.0
        v = np.where(np.isnan(v), _CANON_NAN, v)
        return _fixed(ref.T_FLOAT, v.astype(">f8").view(np.uint8).reshape(n, 8), valid)
    if pa.types.is_integer(t) and t.bit_width <= 64 and not (
            pa.types.is_unsigned_integer(t) and t.bit_width == 64):
        v = pc.fill_null(col.cast(pa.int64()), 0).to_numpy(zero_copy_only=False)
        return _fixed(ref.T_INT, v.astype(">i8").view(np.uint8).reshape(n, 8), valid)
    if pa.types.is_boolean(t):
        v = pc.fill_null(col, False).to_numpy(zero_copy_only=False).astype(np.uint8)
        return _fixed(ref.T_BOOL, v.reshape(n, 1), valid)
    if pa.types.is_date32(t):
        v = pc.fill_null(col.cast(pa.int32()), 0).to_numpy(zero_copy_only=False)
        return _fixed(ref.T_DATE, v.astype(">i4").view(np.uint8).reshape(n, 4), valid)
    if pa.types.is_timestamp(t) and t.unit in _TS_TO_US:
        v = pc.fill_null(col.cast(pa.int64()), 0).to_numpy(zero_copy_only=False)
        v = v * _TS_TO_US[t.unit]
        return _fixed(ref.T_TS, v.astype(">i8").view(np.uint8).reshape(n, 8), valid)
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return _strings(col, valid)
    return None


def _fixed(tag: bytes, body: np.ndarray, valid: np.ndarray):
    n, w = body.shape
    enc = np.empty((n, w + 1), dtype=np.uint8)
    enc[:, 0] = np.where(valid, tag[0], ref.T_NULL[0])     # a null row is the byte N
    enc[:, 1:] = body
    lengths = np.where(valid, w + 1, 1)
    flat = enc.reshape(-1)
    starts = np.arange(n, dtype=np.int64) * (w + 1)
    return lengths, valid, flat, starts


def _strings(col: Any, valid: np.ndarray):
    import pyarrow as pa
    arr = col.cast(pa.large_string()).combine_chunks() if hasattr(col, "combine_chunks") \
        else col.cast(pa.large_string())
    offsets = np.frombuffer(arr.buffers()[1], dtype=np.int64)[arr.offset:arr.offset + len(arr) + 1]
    data = np.frombuffer(arr.buffers()[2], dtype=np.uint8) if arr.buffers()[2] is not None \
        else np.zeros(0, dtype=np.uint8)
    n = len(arr)
    sizes = (offsets[1:] - offsets[:-1]).astype(np.int64)
    sizes = np.where(valid, sizes, 0)
    head = np.empty((n, 5), dtype=np.uint8)
    head[:, 0] = ref.T_STR[0]
    head[:, 1:] = sizes.astype(">u4").view(np.uint8).reshape(n, 4)
    lengths = np.where(valid, 5 + sizes, 1)
    # one flat buffer per column: row i's encoding at starts[i]
    starts = np.zeros(n, dtype=np.int64)
    np.cumsum(lengths[:-1], out=starts[1:])
    flat = np.empty(int(lengths.sum()), dtype=np.uint8)
    idx5 = starts[:, None] + np.arange(5)
    flat[idx5[valid].reshape(-1)] = head[valid].reshape(-1)
    flat[starts[~valid]] = ref.T_NULL[0]
    total = int(sizes.sum())
    if total:
        row_of_byte = np.repeat(np.arange(n), sizes)
        within = np.arange(total) - np.repeat(np.cumsum(sizes) - sizes, sizes)
        src = offsets[:-1][row_of_byte] + within
        flat[starts[row_of_byte] + 5 + within] = data[src]
    return lengths, valid, flat, starts


def row_digests(table: Any) -> list[bytes] | None:
    """sha256 of every row's canonical bytes — equal to ``canonical.row_digests`` over
    ``canonical.table_columns(table)`` — or None when a column's type is not covered."""
    names = sorted(table.column_names)
    n = table.num_rows
    parts = []
    for name in names:
        col = table.column(name)
        col = col.combine_chunks() if hasattr(col, "combine_chunks") else col
        seg = _segments(col)
        if seg is None:
            return None
        parts.append(seg)
    if not parts:
        return [hashlib.sha256(b"").digest() for _ in range(n)]
    grouped = _by_layout(parts, n)
    if grouped is not None:
        return grouped
    row_len = np.sum([p[0] for p in parts], axis=0).astype(np.int64)
    row_start = np.zeros(n, dtype=np.int64)
    np.cumsum(row_len[:-1], out=row_start[1:])
    out = np.empty(int(row_len.sum()), dtype=np.uint8)
    col_off = np.zeros(n, dtype=np.int64)
    for lengths, valid, flat, starts in parts:
        dest = row_start + col_off
        maxw = int(lengths.max()) if n else 0
        if len(flat) == n * maxw and np.all(starts == np.arange(n) * maxw):
            # fixed width: copy the valid rows whole, then write N for nulls
            w = maxw
            idx = dest[valid][:, None] + np.arange(w)
            out[idx.reshape(-1)] = flat.reshape(n, w)[valid].reshape(-1)
            out[dest[~valid]] = ref.T_NULL[0]
        else:                                      # variable width (strings): byte by byte
            total = int(lengths.sum())
            row_of_byte = np.repeat(np.arange(n), lengths)
            within = np.arange(total) - np.repeat(np.cumsum(lengths) - lengths, lengths)
            out[dest[row_of_byte] + within] = flat[starts[row_of_byte] + within]
        col_off += lengths
    buf = out.tobytes()
    ends = (row_start + row_len).tolist()
    starts_l = row_start.tolist()
    sha = hashlib.sha256
    return [sha(buf[s:e]).digest() for s, e in zip(starts_l, ends)]


def _by_layout(parts: list[Any], n: int) -> list[bytes] | None:
    """The same digests, assembled without a per-byte scatter when every row has the
    same layout — each column's encoding the same length in every row (no nulls in
    fixed-width columns, equal-length strings), the usual shape of a pin. Each column is
    then an (n × length) slab and one hstack lays the rows out contiguously. None for
    any other table, which the scatter assembles."""
    if n == 0:
        return []
    slabs = []
    for lens, _, flat, starts in parts:
        width = int(lens[0])
        if not (lens == width).all():
            return None
        if len(flat) == n * width:
            slabs.append(flat.reshape(n, width))
        else:
            slabs.append(flat[starts[:, None] + np.arange(width)])
    buf = np.ascontiguousarray(np.hstack(slabs)).tobytes()
    step = sum(s.shape[1] for s in slabs)
    sha = hashlib.sha256
    return [sha(buf[i:i + step]).digest() for i in range(0, len(buf), step)]
