"""
Materialization shapes and the array serialization contract (§6.5, §7.2).

Three shapes on read — ``tabular`` (nested columns preserved), ``wide``
(nested values exploded to suffixed columns) and ``tensor`` (dense numpy
arrays plus an axis manifest) — and six export encodings, each lossless and
declared. Every export carries a manifest naming each column's logical type
and every nested attribute's axis manifest, so a reader never infers:

* Arrow IPC / Parquet: native nested types, manifest in schema metadata.
* JSON: ``{"manifest": ..., "rows": [...]}``; NDJSON: manifest on line one.
* CSV: a ``# maya-manifest: {...}`` first line, then one of three declared
  encodings for nested attributes — ``wide``, ``packed`` (base64 of
  little-endian binary) or ``json``. CSV never gets an undeclared array.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
import io
import json
import math
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc
import pyarrow.parquet as pq

from maya.core.errors import ValidationFailed
from maya.resolution.types import arrow_type, cast_series, parse_type

FORMATS = ("arrow", "parquet", "json", "ndjson", "csv")
CSV_ENCODINGS = ("wide", "packed", "json")
MANIFEST_KEY = b"maya.manifest"
_NUMPY = {"float64": "<f8", "float32": "<f4", "int64": "<i8", "int32": "<i4", "bool": "|b1"}


def axis_manifest(schema: list[dict[str, Any]]) -> dict[str, Any]:
    """Axis manifest for every nested attribute (§7.2 Rule 2)."""
    out = {}
    for a in schema:
        lt = parse_type(a["type"])
        if lt.kind not in {"list", "fixed_vector", "tensor"}:
            continue
        out[a["name"]] = {
            "dtype": lt.element, "shape": list(lt.shape) if lt.shape else None,
            "order": "row_major", "axis_names": a.get("axis_names"),
            "axis_values": a.get("axis_values"), "null_policy": "null_row",
        }
    return out


def _column_types(df: pd.DataFrame, schema: list[dict[str, Any]]) -> dict[str, str]:
    types = {a["name"]: a["type"] for a in schema}
    out = {}
    for col in df.columns:
        if col in types:
            out[col] = types[col]
        elif isinstance(df[col].dtype, pd.DatetimeTZDtype):
            out[col] = "timestamp"
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            out[col] = "date"
        elif pd.api.types.is_bool_dtype(df[col]):
            out[col] = "bool"
        elif pd.api.types.is_integer_dtype(df[col]):
            out[col] = "int64"
        elif pd.api.types.is_float_dtype(df[col]):
            out[col] = "float64"
        else:
            out[col] = "string"
    return out


def _flat(v: Any) -> Any:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return np.asarray(v).ravel().tolist()


def _array(series: pd.Series, logical: str) -> pa.Array:
    lt = parse_type(logical)
    at = arrow_type(logical)
    if lt.kind in {"list", "fixed_vector", "tensor"}:
        return pa.array([_flat(v) for v in series.tolist()], type=at)
    if lt.kind == "date":
        vals = pd.to_datetime(series)
        days = vals.to_numpy().astype("datetime64[D]")      # floor, as .date() does
        return pa.array(days, type=at, mask=vals.isna().to_numpy())
    if lt.kind == "timestamp":
        return pa.array(pd.to_datetime(series, utc=True), type=at)
    try:          # the column as it is; NaN and None become null
        return pa.array(series, type=at, from_pandas=True)
    except (pa.ArrowInvalid, pa.ArrowTypeError, TypeError, ValueError):
        return pa.array(series.astype(object).where(series.notna(), None).tolist(), type=at)


def manifest_for(df: pd.DataFrame, schema: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """The export manifest: column logical types plus axis manifests."""
    return {"columns": _column_types(df, schema), "axes": axis_manifest(schema), **extra}


def to_arrow(df: pd.DataFrame, schema: list[dict[str, Any]]) -> pa.Table:
    """Native Arrow table with MAYA types and the manifest in schema metadata."""
    types = _column_types(df, schema)
    arrays = [_array(df[c], types[c]) for c in df.columns]
    table = pa.Table.from_arrays(arrays, names=[str(c) for c in df.columns])
    meta = {MANIFEST_KEY: json.dumps(manifest_for(df, schema), sort_keys=True).encode()}
    return table.replace_schema_metadata(meta)


def parquet_safe(table: pa.Table) -> pa.Table:
    """Store fixed-size lists as plain lists for Parquet.

    A null row of a ``FIXED_SIZE_LIST`` does not survive a Parquet round trip
    in pyarrow, which would silently corrupt a tensor attribute. The shape is
    already carried by the manifest, so the physical list type loses nothing.
    """
    fields = []
    for f in table.schema:
        t = f.type
        fields.append(pa.field(f.name, pa.list_(t.value_type)) if pa.types.is_fixed_size_list(t)
                      else f)
    return table.cast(pa.schema(fields, metadata=table.schema.metadata))


def _explode(df: pd.DataFrame, schema: list[dict[str, Any]]) -> pd.DataFrame:
    axes = axis_manifest(schema)
    out = df.copy()
    for name, ax in axes.items():
        if not ax["shape"]:
            raise ValidationFailed(f"attribute '{name}' is a ragged list and cannot be widened; "
                                   "use tabular, or the packed/json CSV encoding")
        shape = tuple(ax["shape"])
        cells = [np.full(shape, np.nan) if _flat(v) is None else np.asarray(_flat(v)).reshape(shape)
                 for v in df[name].tolist()]
        stacked = np.stack(cells) if cells else np.empty((0, *shape))
        pos = out.columns.get_loc(name)
        out = out.drop(columns=[name])
        for k, idx in enumerate(np.ndindex(*shape)):
            col = f"{name}_" + "_".join(str(i) for i in idx)
            out.insert(pos + k, col, stacked[(slice(None), *idx)])
    return out


def to_shape(df: pd.DataFrame, schema: list[dict[str, Any]], shape: str) -> tuple[Any, dict[str, Any]]:
    """Materialize a frame in one of the three shapes. Returns (data, manifest)."""
    manifest = {"shape": shape, "axes": axis_manifest(schema)}
    if shape == "tabular":
        return to_arrow(df, schema), manifest
    if shape == "wide":
        return _explode(df, schema), manifest
    if shape == "tensor":
        return _tensor(df, schema), manifest
    raise ValidationFailed(f"unknown shape '{shape}'", allowed=["tabular", "wide", "tensor"])


def _tensor(df: pd.DataFrame, schema: list[dict[str, Any]]) -> dict[str, Any]:
    names = {a["name"] for a in schema}
    out: dict[str, Any] = {"index": df[[c for c in df.columns if c not in names]].copy()}
    for a in schema:
        lt = parse_type(a["type"])
        if lt.kind == "list":
            raise ValidationFailed(f"ragged attribute '{a['name']}' has no dense tensor form")
        if lt.shape:
            cells = [np.full(lt.shape, np.nan) if _flat(v) is None
                     else np.asarray(_flat(v), dtype="float64").reshape(lt.shape)
                     for v in df[a["name"]].tolist()]
            out[a["name"]] = np.stack(cells) if cells else np.empty((0, *lt.shape))
        else:
            out[a["name"]] = pd.to_numeric(df[a["name"]], errors="coerce").to_numpy(dtype="float64")
    return out


# ------------------------------------------------------------------- export

def _jsonable(df: pd.DataFrame, types: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for rec in df.to_dict(orient="records"):
        row = {}
        for k, v in rec.items():
            t = types[k]
            if parse_type(t).kind in {"list", "fixed_vector", "tensor"}:
                row[k] = _flat(v)
            elif v is None or (not isinstance(v, (list, np.ndarray)) and pd.isna(v)):
                row[k] = None
            elif t == "date":
                row[k] = pd.Timestamp(v).date().isoformat()
            elif t == "timestamp":
                row[k] = pd.Timestamp(v).isoformat()
            elif isinstance(v, np.generic):
                row[k] = v.item()
            else:
                row[k] = v if isinstance(v, (int, float, bool, str)) else str(v)
        rows.append(row)
    return rows


def _pack(v: Any, dtype: str) -> str | None:
    flat = _flat(v)
    if flat is None:
        return None
    # The "b64:" prefix keeps an empty array distinct from a null cell in CSV.
    raw = np.asarray(flat, dtype=_NUMPY.get(dtype, "<f8")).tobytes()
    return "b64:" + base64.b64encode(raw).decode()


def _csv(df: pd.DataFrame, schema: list[dict[str, Any]], encoding: str | None) -> bytes:
    axes = axis_manifest(schema)
    if axes and encoding not in CSV_ENCODINGS:
        raise ValidationFailed(
            "CSV export of nested attributes needs a declared encoding",
            nested=sorted(axes), choices={"wide": "exploded columns, readable, fixed shapes only",
                                          "packed": "base64 little-endian, lossless, not readable",
                                          "json": "JSON text per cell, readable, slow"})
    types = _column_types(df, schema)
    manifest = manifest_for(df, schema, encoding=encoding if axes else None)
    body = df.copy()
    if axes and encoding == "wide":
        body = _explode(df, schema)
    elif axes:
        for name, ax in axes.items():
            body[name] = [(_pack(v, ax["dtype"]) if encoding == "packed" else
                           (None if _flat(v) is None else json.dumps(_flat(v))))
                          for v in df[name].tolist()]
    for col in body.columns:
        if pd.api.types.is_float_dtype(body[col]):
            # repr is the shortest string that round-trips a float64 exactly.
            body[col] = [None if pd.isna(v) else repr(float(v)) for v in body[col]]
    for col, t in types.items():
        if t == "date" and col in body.columns:
            body[col] = [None if pd.isna(v) else pd.Timestamp(v).date().isoformat() for v in body[col]]
    buf = io.StringIO()
    buf.write("# maya-manifest: " + json.dumps(manifest, sort_keys=True) + "\n")
    body.to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue().encode("utf-8")


def export(df: pd.DataFrame, schema: list[dict[str, Any]], fmt: str,
           csv_encoding: str | None = None) -> bytes:
    """Serialize a frame losslessly in a declared format."""
    if fmt not in FORMATS:
        raise ValidationFailed(f"unknown export format '{fmt}'", allowed=list(FORMATS))
    if fmt == "csv":
        return _csv(df, schema, csv_encoding)
    if fmt in {"arrow", "parquet"}:
        table = to_arrow(df, schema)
        sink = pa.BufferOutputStream()
        if fmt == "arrow":
            with ipc.new_file(sink, table.schema) as w:
                w.write_table(table)
        else:
            pq.write_table(parquet_safe(table), sink)
        return sink.getvalue().to_pybytes()
    types = _column_types(df, schema)
    manifest = manifest_for(df, schema)
    rows = _jsonable(df, types)
    if fmt == "json":
        return json.dumps({"manifest": manifest, "rows": rows}, sort_keys=True).encode()
    lines = [json.dumps({"_maya_manifest": manifest}, sort_keys=True)]
    lines += [json.dumps(r, sort_keys=True) for r in rows]
    return ("\n".join(lines) + "\n").encode()


# ------------------------------------------------------------------- import

def _restore(df: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    types = manifest["columns"]
    out = pd.DataFrame(index=range(len(df)))
    for col, t in types.items():
        kind = parse_type(t).kind
        s = df[col] if col in df.columns else pd.Series([None] * len(df))
        if kind in {"list", "fixed_vector", "tensor"}:
            out[col] = [_flat(v) if v is not None and not (isinstance(v, float) and math.isnan(v))
                        else None for v in s.tolist()]
        elif kind == "date":
            out[col] = pd.to_datetime(s).astype("datetime64[ns]")
        elif kind == "timestamp":
            out[col] = pd.to_datetime(s, utc=True)
        elif kind == "string":
            out[col] = s.astype(object).where(s.notna(), None)
        else:
            out[col] = cast_series(pd.Series(s.tolist()), t)
    return out


def _unwide(df: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    for name, ax in manifest["axes"].items():
        cols = [f"{name}_" + "_".join(str(i) for i in idx) for idx in np.ndindex(*ax["shape"])]
        vals = out[cols].to_numpy(dtype="float64")
        out[name] = [None if np.isnan(r).all() else r.tolist() for r in vals]
        out = out.drop(columns=cols)
    return out


def _floats(s: pd.Series) -> pd.Series:
    """Parse with Python's float(), which is exact where pandas' fast parser is not."""
    return pd.Series([np.nan if v is None else float(v) for v in s], index=s.index, dtype="float64")


def _read_csv(data: bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    text = data.decode("utf-8")
    head, _, rest = text.partition("\n")
    manifest = json.loads(head.split(":", 1)[1])
    types = manifest["columns"]
    enc = manifest.get("encoding")
    df = pd.read_csv(io.StringIO(rest), dtype=str, keep_default_na=False, na_values=[""])
    df = df.astype(object).where(df.notna(), None)
    if enc == "wide":
        for name, ax in manifest["axes"].items():
            for idx in np.ndindex(*ax["shape"]):
                col = f"{name}_" + "_".join(str(i) for i in idx)
                df[col] = _floats(df[col])
        df = _unwide(df, manifest)
    elif enc in {"packed", "json"}:
        for name, ax in manifest["axes"].items():
            dt = _NUMPY.get(ax["dtype"], "<f8")
            df[name] = [None if v is None else
                        (np.frombuffer(base64.b64decode(v[4:]), dtype=dt).tolist() if enc == "packed"
                         else json.loads(v)) for v in df[name]]
    for col, t in types.items():
        if t in {"float64", "float32"}:
            df[col] = _floats(df[col])
    return df, manifest


def import_export(data: bytes, fmt: str) -> pd.DataFrame:
    """Read back an export produced by :func:`export` (the round-trip reader)."""
    if fmt in {"arrow", "parquet"}:
        table = ipc.open_file(pa.py_buffer(data)).read_all() if fmt == "arrow" \
            else pq.read_table(pa.py_buffer(data))
        manifest = json.loads(table.schema.metadata[MANIFEST_KEY])
        return _restore(table.to_pandas(types_mapper=None, date_as_object=True), manifest)
    if fmt == "json":
        doc = json.loads(data)
        return _restore(pd.DataFrame(doc["rows"]), doc["manifest"])
    if fmt == "ndjson":
        lines = data.decode().splitlines()
        manifest = json.loads(lines[0])["_maya_manifest"]
        return _restore(pd.DataFrame([json.loads(x) for x in lines[1:]]), manifest)
    if fmt == "csv":
        df, manifest = _read_csv(data)
        return _restore(df, manifest)
    raise ValidationFailed(f"unknown export format '{fmt}'")
