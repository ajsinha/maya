"""
Canonical data encoding and content hashing (§7.2 Rule 4). Type B seam.

This module *is* the specification of a MAYA content hash. It is never
delegated to an accelerator, and it is computed over values, never over file
bytes, so two pins of the same data hash identically whichever engine or
``maya_delta`` backend wrote them.

The canonical form of a table:

* columns in ascending name order;
* rows in ascending order of the index columns (the caller sorts; the
  encoder asserts nothing about order because the fragment chunker needs to
  hash rows in the order they will be stored);
* every value encoded with a one-byte type tag and a fixed binary layout:
  integers as signed 64-bit big-endian, floats as IEEE-754 binary64
  big-endian (with every NaN collapsed to one bit pattern), decimals as
  their normalised text, dates as days since 1970-01-01, timestamps as UTC
  microseconds, strings and bytes length-prefixed, nested lists and structs
  recursively in declared order, and null as its own tag.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import hashlib
import math
import struct
from typing import Any, Iterable, Sequence

_EPOCH = _dt.date(1970, 1, 1)
_NAN = struct.pack(">d", float("nan"))

T_NULL, T_BOOL, T_INT, T_FLOAT, T_STR, T_BYTES = b"N", b"B", b"I", b"F", b"S", b"Y"
T_DATE, T_TS, T_DEC, T_LIST, T_MAP, T_DUR = b"D", b"T", b"M", b"L", b"K", b"U"


def encode_value(value: Any) -> bytes:  # noqa: C901 - the hash's definition: one literal case per type
    """Encode one value into its canonical bytes."""
    if value is None:
        return T_NULL
    if isinstance(value, bool):
        return T_BOOL + (b"\x01" if value else b"\x00")
    if isinstance(value, int):
        return T_INT + value.to_bytes(8, "big", signed=True)
    if isinstance(value, float):
        if math.isnan(value):
            return T_FLOAT + _NAN
        return T_FLOAT + struct.pack(">d", value + 0.0)  # -0.0 -> 0.0
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return T_STR + len(raw).to_bytes(4, "big") + raw
    if isinstance(value, (bytes, bytearray)):
        return T_BYTES + len(value).to_bytes(4, "big") + bytes(value)
    if isinstance(value, _dt.datetime):
        return _encode_ts(value)
    if isinstance(value, _dt.date):
        return T_DATE + (value - _EPOCH).days.to_bytes(4, "big", signed=True)
    if isinstance(value, _dt.timedelta):
        us = (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds
        return T_DUR + us.to_bytes(8, "big", signed=True)
    if isinstance(value, decimal.Decimal):
        raw = format(value.normalize(), "f").encode("ascii")
        return T_DEC + len(raw).to_bytes(2, "big") + raw
    if isinstance(value, dict):
        return _encode_mapping(value)
    if isinstance(value, (list, tuple)):
        body = b"".join(encode_value(v) for v in value)
        return T_LIST + len(value).to_bytes(4, "big") + body
    if hasattr(value, "item"):  # numpy scalar
        return encode_value(value.item())
    if hasattr(value, "tolist"):  # numpy array
        return encode_value(value.tolist())
    raise TypeError(f"No canonical encoding for {type(value).__name__}")


def _encode_ts(value: _dt.datetime) -> bytes:
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.timezone.utc)
    delta = value - _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)
    us = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return T_TS + us.to_bytes(8, "big", signed=True)


def _encode_mapping(value: dict[Any, Any]) -> bytes:
    # A struct keeps its declared field order; a map from pyarrow arrives as a
    # list of (key, value) tuples and is handled by the list branch.
    parts = [encode_value(str(k)) + encode_value(v) for k, v in value.items()]
    return T_MAP + len(parts).to_bytes(4, "big") + b"".join(parts)


def encode_row(values: Sequence[Any]) -> bytes:
    """Canonical bytes of one row (values already in canonical column order)."""
    return b"".join(encode_value(v) for v in values)


def row_digests(columns: dict[str, list[Any]]) -> list[bytes]:
    """sha256 digest of every row, columns taken in ascending name order."""
    names = sorted(columns)
    cols = [columns[n] for n in names]
    n_rows = len(cols[0]) if cols else 0
    return [hashlib.sha256(encode_row([c[i] for c in cols])).digest() for i in range(n_rows)]


def schema_digest(schema: Iterable[tuple[str, str]]) -> str:
    """Digest of (name, logical type) pairs in ascending name order."""
    h = hashlib.sha256()
    for name, logical in sorted(schema):
        h.update(encode_value(name) + encode_value(logical))
    return h.hexdigest()


def fragment_hash(row_digest_run: Sequence[bytes]) -> str:
    """Content hash of a fragment: sha256 over its row digests, in order."""
    h = hashlib.sha256()
    h.update(len(row_digest_run).to_bytes(8, "big"))
    for d in row_digest_run:
        h.update(d)
    return h.hexdigest()


def content_hash(schema_hex: str, fragment_hashes: Sequence[str]) -> str:
    """Pin content hash: schema digest plus the ordered fragment hashes."""
    h = hashlib.sha256(b"maya-content-v1\x00" + schema_hex.encode("ascii"))
    for fh in fragment_hashes:
        h.update(fh.encode("ascii"))
    return h.hexdigest()


def table_columns(table: Any) -> dict[str, list[Any]]:
    """Python values per column from a pyarrow Table (the one decoding path)."""
    return {name: table.column(name).to_pylist() for name in table.column_names}


def table_content_hash(table: Any) -> str:
    """Single-fragment content hash of a whole Arrow table.

    The checksum MAYA issues on a training-data download and verifies on
    parameter upload; the SDK and bundle verifier recompute it the same way.
    """
    cols = table_columns(table)
    digests = row_digests(cols)
    schema = schema_digest((f.name, str(f.type)) for f in table.schema)
    return content_hash(schema, [fragment_hash(digests)])
