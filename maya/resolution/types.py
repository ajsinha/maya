"""
MAYA logical types and their mapping to Arrow (§5.1).

Logical types are MAYA's own vocabulary; Arrow is how they are held in memory
and on disk. Nested types are native Arrow nested types, never strings
(§7.2 Rule 1): ``fixed_vector<T,n>`` is a ``FIXED_SIZE_LIST`` and
``tensor<T,[a,b]>`` a ``FIXED_SIZE_LIST`` of length ``a*b`` whose shape is
carried in the axis manifest.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from maya.core.errors import ValidationFailed

SCALARS: dict[str, pa.DataType] = {
    "int32": pa.int32(),
    "int64": pa.int64(),
    "float32": pa.float32(),
    "float64": pa.float64(),
    "bool": pa.bool_(),
    "string": pa.string(),
    "date": pa.date32(),
    "timestamp": pa.timestamp("us", tz="UTC"),
    "duration": pa.duration("us"),
}

NUMERIC = {"int32", "int64", "float32", "float64"}


@dataclass(frozen=True)
class LogicalType:
    """A parsed logical type: a kind plus its parameters."""

    kind: str
    params: tuple[Any, ...] = ()

    @property
    def nested(self) -> bool:
        return self.kind in {"list", "fixed_vector", "tensor", "struct", "map"}

    @property
    def shape(self) -> tuple[int, ...] | None:
        if self.kind == "fixed_vector":
            return (int(self.params[1]),)
        if self.kind == "tensor":
            return tuple(int(x) for x in self.params[1])
        return None

    @property
    def element(self) -> str | None:
        if self.kind in {"list", "fixed_vector", "tensor"}:
            return str(self.params[0])
        return None


def _split_top(text: str) -> list[str]:
    """Split on commas not nested in <> or []."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "<[(":
            depth += 1
        elif ch in ">])":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def parse_type(text: str) -> LogicalType:  # noqa: C901 - one case per logical-type form
    """Parse a logical type string. Raises ValidationFailed on anything unknown."""
    t = text.strip()
    if t in SCALARS:
        return LogicalType(t)
    m = re.fullmatch(r"decimal\((\d+)\s*,\s*(\d+)\)", t)
    if m:
        return LogicalType("decimal", (int(m.group(1)), int(m.group(2))))
    m = re.fullmatch(r"(list|fixed_vector|tensor|struct|map)<(.*)>", t)
    if not m:
        raise ValidationFailed(f"unknown logical type '{text}'")
    kind, inner = m.group(1), m.group(2)
    parts = _split_top(inner)
    try:
        # every element type is itself a logical type; sizes are positive whole numbers
        if kind == "list" and len(parts) == 1:
            parse_type(parts[0])
            return LogicalType(kind, (parts[0],))
        if kind == "fixed_vector" and len(parts) == 2:
            parse_type(parts[0])
            size = int(parts[1])
            if size < 1:
                raise ValueError(size)
            return LogicalType(kind, (parts[0], size))
        if kind == "tensor" and len(parts) == 2:
            parse_type(parts[0])
            dims = tuple(int(x) for x in parts[1].strip("[]").split(","))
            if not dims or min(dims) < 1:
                raise ValueError(dims)
            return LogicalType(kind, (parts[0], dims))
        if kind == "map" and len(parts) == 2:
            parse_type(parts[0])
            parse_type(parts[1])
            return LogicalType(kind, (parts[0], parts[1]))
        if kind == "struct" and parts:
            fields = []
            for p in parts:
                name, _, ftype = p.partition(":")
                if not name.strip():
                    raise ValueError(p)
                parse_type(ftype.strip())
                fields.append((name.strip(), ftype.strip()))
            return LogicalType(kind, tuple(fields))
    except ValueError as exc:
        raise ValidationFailed(f"malformed logical type '{text}'") from exc
    raise ValidationFailed(f"malformed logical type '{text}'")


def arrow_type(logical: str) -> pa.DataType:
    """The Arrow type that holds a MAYA logical type."""
    lt = parse_type(logical)
    if lt.kind in SCALARS:
        return SCALARS[lt.kind]
    if lt.kind == "decimal":
        return pa.decimal128(*lt.params)
    if lt.kind == "list":
        return pa.list_(arrow_type(lt.params[0]))
    if lt.kind in {"fixed_vector", "tensor"}:
        return pa.list_(arrow_type(lt.params[0]), int(math.prod(lt.shape or ())))
    if lt.kind == "map":
        return pa.map_(arrow_type(lt.params[0]), arrow_type(lt.params[1]))
    return pa.struct([pa.field(n, arrow_type(ft)) for n, ft in lt.params])


def logical_from_arrow(t: pa.DataType) -> str:  # noqa: C901 - one case per Arrow type family
    """The MAYA logical type for an Arrow type (tensor shape needs a manifest)."""
    for name, at in SCALARS.items():
        if t == at:
            return name
    if pa.types.is_timestamp(t):
        return "timestamp"
    if pa.types.is_date(t):
        return "date"
    if pa.types.is_duration(t):
        return "duration"
    if pa.types.is_integer(t):
        return "int64" if t.bit_width > 32 else "int32"
    if pa.types.is_floating(t):
        return "float64" if t.bit_width > 32 else "float32"
    if pa.types.is_decimal(t):
        return f"decimal({t.precision},{t.scale})"
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "string"
    if pa.types.is_fixed_size_list(t):
        return f"fixed_vector<{logical_from_arrow(t.value_type)},{t.list_size}>"
    if pa.types.is_list(t) or pa.types.is_large_list(t):
        return f"list<{logical_from_arrow(t.value_type)}>"
    if pa.types.is_map(t):
        return f"map<{logical_from_arrow(t.key_type)},{logical_from_arrow(t.item_type)}>"
    if pa.types.is_struct(t):
        inner = ",".join(f"{f.name}:{logical_from_arrow(f.type)}" for f in t)
        return f"struct<{inner}>"
    raise ValidationFailed(f"no MAYA logical type for Arrow type {t}")


def _infer_series(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_integer_dtype(s):
        return "int64"
    if pd.api.types.is_float_dtype(s):
        return "float64"
    if isinstance(s.dtype, pd.DatetimeTZDtype):
        return "timestamp"
    if pd.api.types.is_datetime64_any_dtype(s):
        norm = s.dropna()
        return "date" if (norm == norm.dt.normalize()).all() else "timestamp"
    if pd.api.types.is_timedelta64_dtype(s):
        return "duration"
    sample = s.dropna()
    if len(sample) and all(isinstance(v, (list, tuple, np.ndarray)) for v in sample):
        return _infer_nested(sample)
    return "string"


def _infer_nested(sample: pd.Series) -> str:
    lengths = {len(v) for v in sample}
    inner = pd.Series([x for v in sample for x in v])
    elem = _infer_series(inner) if len(inner) else "float64"
    if len(lengths) == 1:
        return f"fixed_vector<{elem},{lengths.pop()}>"
    return f"list<{elem}>"


def infer_schema(data: pd.DataFrame | pa.Table) -> list[dict[str, Any]]:
    """Propose a schema. A proposal the designer confirms, never a decision."""
    if isinstance(data, pa.Table):
        return [
            {"name": f.name, "type": logical_from_arrow(f.type), "nullable": True}
            for f in data.schema
        ]
    out = []
    for col in data.columns:
        if str(col).startswith("_"):
            continue
        s = data[col]
        out.append({"name": str(col), "type": _infer_series(s), "nullable": bool(s.isna().any())})
    return out


def schema_warnings(schema: list[dict[str, Any]]) -> list[str]:
    """Advisory findings: float carrying a price tag, missing units on prices."""
    warns = []
    for a in schema:
        if a.get("tag") == "price" and a["type"].startswith("float"):
            warns.append(f"attribute '{a['name']}' is a float carrying the 'price' tag; "
                         "decimal is mandatory for monetary attributes")
    return warns


def _cast_scalar(value: Any, lt: LogicalType) -> Any:  # noqa: C901 - one case per logical type
    """Cast one value; raises ValueError/TypeError on failure."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    k = lt.kind
    if k in {"int32", "int64"}:
        f = float(value)
        if not f.is_integer():
            raise ValueError("not integral")
        bits = 31 if k == "int32" else 63
        if not -2 ** bits <= f < 2 ** bits:          # else Arrow overflows at write time
            raise ValueError(f"outside {k}")
        return int(f)
    if k in {"float32", "float64"}:
        return float(value)
    if k == "bool":
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "t"}:
            return True
        if text in {"false", "0", "no", "n", "f"}:
            return False
        raise ValueError("not boolean")
    if k == "decimal":
        try:
            return Decimal(str(value)).quantize(Decimal(1).scaleb(-lt.params[1]))
        except InvalidOperation as exc:
            raise ValueError("not decimal") from exc
    if k == "date":
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            raise ValueError("not a date")
        return ts.normalize().tz_localize(None) if ts.tzinfo else ts.normalize()
    if k == "timestamp":
        ts = pd.Timestamp(value)
        return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    if k == "string":
        return str(value)
    return value


def cast_preview(series: pd.Series, logical: str, limit: int = 5) -> dict[str, Any]:
    """How many values would fail a cast, with examples, before committing."""
    lt = parse_type(logical)
    failures, examples = 0, []
    for v in series.tolist():
        try:
            _cast_scalar(v, lt)
        except (ValueError, TypeError, OverflowError):
            failures += 1
            if len(examples) < limit:
                examples.append(v)
    return {"type": logical, "rows": int(len(series)), "failures": failures, "examples": examples}


def cast_series(series: pd.Series, logical: str) -> pd.Series:
    """Cast a series to a logical type; any failing value raises ValidationFailed."""
    lt = parse_type(logical)
    if lt.nested:
        return series
    preview = cast_preview(series, logical)
    if preview["failures"]:
        raise ValidationFailed(
            f"{preview['failures']} value(s) of '{series.name}' cannot be cast to {logical}",
            attr=str(series.name), examples=[str(x) for x in preview["examples"]],
        )
    values = [_cast_scalar(v, lt) for v in series.tolist()]
    if lt.kind in {"int32", "int64"}:
        return pd.Series(values, index=series.index, dtype="Int64", name=series.name)
    if lt.kind in {"float32", "float64"}:
        return pd.Series(values, index=series.index, dtype="float64", name=series.name)
    if lt.kind == "bool":
        return pd.Series(values, index=series.index, dtype="boolean", name=series.name)
    if lt.kind == "date":
        return pd.to_datetime(pd.Series(values, index=series.index), errors="raise") \
            .astype("datetime64[ns]").rename(series.name)
    if lt.kind == "timestamp":
        return pd.to_datetime(pd.Series(values, index=series.index), utc=True).rename(series.name)
    return pd.Series(values, index=series.index, dtype=object, name=series.name)


def cast_frame(df: pd.DataFrame, schema: list[dict[str, Any]]) -> pd.DataFrame:
    """Cast every schema attribute present in ``df``; other columns pass through."""
    out = df.copy()
    for attr in schema:
        if attr["name"] in out.columns:
            out[attr["name"]] = cast_series(out[attr["name"]], attr["type"])
    return out


def unify(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Unify two attributes of the same name: identical type, no unit/tag conflict."""
    if a["type"] != b["type"]:
        raise ValidationFailed(
            f"attribute '{a['name']}' has conflicting types {a['type']} and {b['type']}; "
            "declare an explicit cast", attr=a["name"])
    for key in ("unit", "tag"):
        if a.get(key) and b.get(key) and a[key] != b[key]:
            raise ValidationFailed(
                f"attribute '{a['name']}' has conflicting {key}s "
                f"'{a[key]}' and '{b[key]}'", attr=a["name"])
    merged = dict(a)
    merged["nullable"] = bool(a.get("nullable", True) or b.get("nullable", True))
    for key in ("unit", "tag"):
        merged[key] = a.get(key) or b.get(key)
        if merged[key] is None:
            merged.pop(key)
    return merged
