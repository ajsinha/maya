"""
Arrow <-> Delta schema translation.

The Delta transaction log carries the table schema as a JSON ``schemaString``
(Delta protocol, "Schema Serialization Format"). This module converts in both
directions and normalises Arrow types to the exact shape the native backend
(delta-rs) returns, so a table read by either backend compares equal:

* lists use the child name ``element``;
* maps use ``key`` / ``value`` children;
* timestamps are microsecond precision, ``timestamp`` in UTC and
  ``timestamp_ntz`` naive.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pyarrow as pa

from maya_delta.errors import MayaDeltaError

_PRIMITIVE_TO_ARROW: dict[str, pa.DataType] = {
    "string": pa.string(),
    "long": pa.int64(),
    "integer": pa.int32(),
    "short": pa.int16(),
    "byte": pa.int8(),
    "double": pa.float64(),
    "float": pa.float32(),
    "boolean": pa.bool_(),
    "binary": pa.binary(),
    "date": pa.date32(),
    "timestamp": pa.timestamp("us", tz="UTC"),
    "timestamp_ntz": pa.timestamp("us"),
}

_DECIMAL_RE = re.compile(r"^decimal\((\d+),\s*(\d+)\)$")


def _primitive_name(t: pa.DataType) -> str:
    """Delta primitive name for an Arrow type."""
    if pa.types.is_string(t) or pa.types.is_large_string(t) or pa.types.is_string_view(t):
        return "string"
    table = [
        (pa.types.is_int64, "long"),
        (pa.types.is_int32, "integer"),
        (pa.types.is_int16, "short"),
        (pa.types.is_int8, "byte"),
        (pa.types.is_float64, "double"),
        (pa.types.is_float32, "float"),
        (pa.types.is_boolean, "boolean"),
        (pa.types.is_date32, "date"),
    ]
    for pred, name in table:
        if pred(t):
            return name
    if pa.types.is_binary(t) or pa.types.is_large_binary(t):
        return "binary"
    if pa.types.is_timestamp(t):
        return "timestamp" if t.tz else "timestamp_ntz"
    if pa.types.is_decimal(t):
        return f"decimal({t.precision},{t.scale})"
    raise MayaDeltaError(f"Arrow type {t} has no Delta equivalent")


def arrow_type_to_delta(t: pa.DataType) -> Any:
    """Arrow type -> Delta JSON type (a string for primitives, a dict otherwise)."""
    if pa.types.is_list(t) or pa.types.is_large_list(t) or pa.types.is_fixed_size_list(t):
        return {
            "type": "array",
            "elementType": arrow_type_to_delta(t.value_type),
            "containsNull": t.value_field.nullable,
        }
    if pa.types.is_struct(t):
        return {
            "type": "struct",
            "fields": [field_to_delta(t.field(i)) for i in range(t.num_fields)],
        }
    if pa.types.is_map(t):
        return {
            "type": "map",
            "keyType": arrow_type_to_delta(t.key_type),
            "valueType": arrow_type_to_delta(t.item_type),
            "valueContainsNull": t.item_field.nullable,
        }
    return _primitive_name(t)


def field_to_delta(f: pa.Field) -> dict[str, Any]:
    """One Arrow field as a Delta StructField."""
    return {
        "name": f.name,
        "type": arrow_type_to_delta(f.type),
        "nullable": f.nullable,
        "metadata": {},
    }


def schema_to_delta_json(schema: pa.Schema) -> str:
    """Arrow schema -> Delta ``schemaString``."""
    return json.dumps(
        {"type": "struct", "fields": [field_to_delta(f) for f in schema]}, separators=(",", ":")
    )


def delta_type_to_arrow(t: Any) -> pa.DataType:
    """Delta JSON type -> normalised Arrow type."""
    if isinstance(t, str):
        if t in _PRIMITIVE_TO_ARROW:
            return _PRIMITIVE_TO_ARROW[t]
        m = _DECIMAL_RE.match(t)
        if m:
            return pa.decimal128(int(m.group(1)), int(m.group(2)))
        raise MayaDeltaError(f"Unknown Delta primitive type '{t}'")
    kind = t.get("type")
    if kind == "array":
        return pa.list_(
            pa.field(
                "element",
                delta_type_to_arrow(t["elementType"]),
                nullable=t.get("containsNull", True),
            )
        )
    if kind == "struct":
        return pa.struct([delta_field_to_arrow(f) for f in t["fields"]])
    if kind == "map":
        return pa.map_(
            pa.field("key", delta_type_to_arrow(t["keyType"]), nullable=False),
            pa.field(
                "value",
                delta_type_to_arrow(t["valueType"]),
                nullable=t.get("valueContainsNull", True),
            ),
        )
    raise MayaDeltaError(f"Unknown Delta complex type '{kind}'")


def delta_field_to_arrow(f: dict[str, Any]) -> pa.Field:
    """One Delta StructField -> Arrow field."""
    return pa.field(f["name"], delta_type_to_arrow(f["type"]), nullable=f.get("nullable", True))


def schema_from_delta_json(schema_string: str) -> pa.Schema:
    """Delta ``schemaString`` -> normalised Arrow schema."""
    doc = json.loads(schema_string)
    return pa.schema([delta_field_to_arrow(f) for f in doc["fields"]])


def field_metadata_has(schema_string: str, key: str) -> bool:
    """True when any (top-level or nested) field carries metadata ``key``."""

    def walk(fields: list[dict[str, Any]]) -> bool:
        for f in fields:
            if key in (f.get("metadata") or {}):
                return True
            t = f.get("type")
            if isinstance(t, dict) and t.get("type") == "struct" and walk(t["fields"]):
                return True
        return False

    return walk(json.loads(schema_string)["fields"])


def normalise_schema(schema: pa.Schema) -> pa.Schema:
    """The schema a table with ``schema`` reads back as, after a Delta round trip."""
    return schema_from_delta_json(schema_to_delta_json(schema))


def conform(table: pa.Table, schema: pa.Schema) -> pa.Table:
    """Cast ``table`` (columns in any order) onto ``schema``, column for column."""
    arrays = []
    for f in schema:
        col = table.column(f.name)
        if not col.type.equals(f.type):
            col = col.cast(f.type)
        arrays.append(col)
    return pa.Table.from_arrays(arrays, schema=schema)
