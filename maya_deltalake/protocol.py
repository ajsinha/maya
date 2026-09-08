"""
maya_deltalake — the transaction log, as the protocol actually writes it.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Every shape here was read off a table `deltalake` produced rather than
remembered from the specification, because "what the spec says" and "what the
reference implementation writes" are the two things that have to agree and only
one of them is checkable from here.

A commit is one file, `_delta_log/00000000000000000007.json`, holding one JSON
object per line. The objects MAYA's subset needs are five:

  * ``protocol``   — the reader and writer versions required. Written once.
  * ``metaData``   — the table id, the format and the schema. Written on the
                     first commit and again whenever the schema is replaced.
  * ``add``        — a data file that is now part of the table.
  * ``remove``     — a data file that no longer is. An overwrite is `remove`
                     for everything currently live plus `add` for the new file;
                     the bytes stay on disk, which is what makes time travel to
                     an earlier version possible at all.
  * ``commitInfo`` — provenance. Optional to a reader, and written because a
                     log that cannot say which engine produced a version is a
                     log that answers "who wrote this" with a shrug.

The state at version *N* is commits 0..N replayed in order: collect the adds,
subtract the removes. There is no snapshot to consult and no index to trust —
which is the property that makes the format legible with nothing but a text
editor, and it is why this file is short.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Iterator, List, Optional, Tuple

#: The versions this writes and can read. Reader 1 / writer 2 is the plain
#: format: no deletion vectors (reader 3), no column mapping, no identity
#: columns, no row tracking. Declared rather than implied, because a reader
#: meeting a table whose `minReaderVersion` it does not support is required to
#: refuse — and that refusal is the protocol working.
MIN_READER = 1
MIN_WRITER = 2

ENGINE = "maya_deltalake"


class DeltaProtocolError(RuntimeError):
    """A table this cannot read, or a write it must not attempt.

    Distinct from an ordinary error because it always means the same thing:
    the table uses a feature outside the subset. Refused by name, so nobody has
    to guess whether the data is unreadable or merely unread.
    """


# ---------------------------------------------------------------- the schema
#: Arrow type name → Delta type name. Delta's own vocabulary, which is Spark's.
_TYPES: Dict[str, str] = {
    "bool": "boolean", "int8": "byte", "int16": "short", "int32": "integer",
    "int64": "long", "uint8": "short", "uint16": "integer", "uint32": "long",
    "uint64": "long", "halffloat": "float", "float": "float", "double": "double",
    "string": "string", "large_string": "string", "binary": "binary",
    "large_binary": "binary", "date32[day]": "date", "date64[ms]": "date",
    "null": "string",
}


def delta_type(arrow_type: Any) -> Any:
    """The Delta type for an Arrow type: a NAME, or a nested structure.

    Delta's `type` field is a string for a primitive and an object for an
    array, a map or a struct — which is how a MAYA feature with `shape: [12]`
    is described, and `shape: [3, 3]` is an array of arrays. Getting that wrong
    is not academic: shaped features are the reason a yield curve is one
    feature rather than ten, and a matrix arriving as ten tenors when eleven
    were expected is the failure the shape declaration exists to prevent.

    Refusing beats guessing for anything left over. A type silently mapped to
    `string` is a column that reads back as text under the other
    implementation, and the first thing anybody does with a feature value is
    arithmetic.
    """
    import pyarrow as pa

    if pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type):
        return {"type": "array",
                "elementType": delta_type(arrow_type.value_type),
                # Arrow carries nullability on the value FIELD, not on the
                # list; delta-rs writes `true` and matching it keeps the
                # schemas byte-comparable between the two implementations.
                "containsNull": bool(arrow_type.value_field.nullable)}
    if pa.types.is_fixed_size_list(arrow_type):
        # Delta has no fixed-size array. Widening to a variable-length one is
        # what delta-rs does and is lossless for reading: the values are the
        # same, the length ceases to be enforced by the STORE. MAYA enforces
        # shape at its own boundary anyway — `core/features/shapes.py` — so
        # the guarantee is not lost, it just is not the file format's.
        return {"type": "array",
                "elementType": delta_type(arrow_type.value_type),
                "containsNull": True}
    if pa.types.is_struct(arrow_type):
        return {"type": "struct",
                "fields": [{"name": field.name,
                            "type": delta_type(field.type),
                            "nullable": bool(field.nullable),
                            "metadata": {}}
                           for field in arrow_type]}
    if pa.types.is_map(arrow_type):
        return {"type": "map", "keyType": delta_type(arrow_type.key_type),
                "valueType": delta_type(arrow_type.item_type),
                "valueContainsNull": True}

    name = str(arrow_type)
    if name in _TYPES:
        return _TYPES[name]
    if name.startswith("timestamp"):
        return "timestamp"
    if name.startswith("decimal"):
        # decimal128(38, 10) -> decimal(38,10)
        inner = name[name.index("(") + 1:name.rindex(")")]
        return f"decimal({inner.replace(' ', '')})"
    raise DeltaProtocolError(
        f"maya_deltalake does not map the Arrow type '{name}' to a Delta type. "
        f"It handles {', '.join(sorted(set(_TYPES.values())))}, timestamp, "
        f"decimal, and arrays, structs and maps of those. Mapping it to "
        f"something plausible would give a column that reads back as a "
        f"different type under the other implementation.")


def schema_string(arrow_schema: Any) -> str:
    """Delta's `schemaString`: the struct, as JSON, as a STRING inside JSON.

    Doubly encoded in the real format, which looks like a mistake and is not —
    the log line is JSON and the schema is a JSON document carried within it.
    """
    fields = [{"name": field.name, "type": delta_type(field.type),
               "nullable": bool(field.nullable), "metadata": {}}
              for field in arrow_schema]
    return json.dumps({"type": "struct", "fields": fields},
                      separators=(",", ":"))


def schema_fields(schema_string_value: str) -> List[Dict[str, Any]]:
    return json.loads(schema_string_value).get("fields", [])


# ---------------------------------------------------------------- the actions
def now_ms() -> int:
    return int(time.time() * 1000)


def protocol_action() -> Dict[str, Any]:
    return {"protocol": {"minReaderVersion": MIN_READER,
                         "minWriterVersion": MIN_WRITER}}


def metadata_action(arrow_schema: Any, table_id: Optional[str] = None,
                    created_ms: Optional[int] = None) -> Dict[str, Any]:
    return {"metaData": {
        "id": table_id or str(uuid.uuid4()),
        "name": None, "description": None,
        "format": {"provider": "parquet", "options": {}},
        "schemaString": schema_string(arrow_schema),
        "partitionColumns": [],
        "createdTime": created_ms if created_ms is not None else now_ms(),
        "configuration": {}}}


def add_action(path: str, size: int, rows: int,
               moment: Optional[int] = None) -> Dict[str, Any]:
    moment = moment if moment is not None else now_ms()
    return {"add": {
        "path": path, "partitionValues": {}, "size": int(size),
        "modificationTime": moment, "dataChange": True,
        # `stats` is optional and `numRecords` is the half of it that matters:
        # a reader can answer "how many rows" without opening a Parquet file.
        # The min/max/nullCount that delta-rs also writes are omitted rather
        # than approximated — a statistic that is wrong is worse than absent,
        # because a query planner will believe it.
        "stats": json.dumps({"numRecords": int(rows)}, separators=(",", ":"))}}


def remove_action(path: str, size: Optional[int] = None,
                  moment: Optional[int] = None) -> Dict[str, Any]:
    action: Dict[str, Any] = {
        "path": path, "dataChange": True,
        "deletionTimestamp": moment if moment is not None else now_ms(),
        "extendedFileMetadata": True, "partitionValues": {}}
    if size is not None:
        action["size"] = int(size)
    return {"remove": action}


def commit_info(operation: str, parameters: Dict[str, Any],
                metrics: Dict[str, Any],
                moment: Optional[int] = None) -> Dict[str, Any]:
    return {"commitInfo": {
        "timestamp": moment if moment is not None else now_ms(),
        "operation": operation, "operationParameters": parameters,
        # Named, so a table carrying versions from both implementations says
        # which wrote which. That is the first question anybody asks of a
        # fallback, and the log should not need a person to answer it.
        "engineInfo": f"{ENGINE}:{MIN_READER}.{MIN_WRITER}",
        "clientVersion": ENGINE, "operationMetrics": metrics}}


# ---------------------------------------------------------------- the replay
def commit_name(version: int) -> str:
    """`00000000000000000007.json` — twenty digits, zero-padded.

    The width is part of the format rather than a nicety: readers list the
    directory and sort as STRINGS, so version 10 must sort after version 9.
    """
    return f"{version:020d}.json"


def read_commit(text: str) -> Iterator[Dict[str, Any]]:
    for line in text.splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def replay(commits: List[Tuple[int, str]]) -> Dict[str, Any]:
    """Fold the commits into the table state they describe.

    Ordered by version by the caller. Returns the live files in the order they
    were added — which is the order the rows come back in, and therefore has to
    be stable, or a read at the same version answers differently twice.
    """
    files: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    metadata: Optional[Dict[str, Any]] = None
    protocol: Dict[str, Any] = {"minReaderVersion": MIN_READER,
                                "minWriterVersion": MIN_WRITER}
    for _version, text in commits:
        for action in read_commit(text):
            if "add" in action:
                path = action["add"]["path"]
                if path not in files:
                    order.append(path)
                files[path] = action["add"]
            elif "remove" in action:
                path = action["remove"]["path"]
                files.pop(path, None)
                if path in order:
                    order.remove(path)
            elif "metaData" in action:
                metadata = action["metaData"]
            elif "protocol" in action:
                protocol = action["protocol"]
    return {"files": [files[p] for p in order], "metadata": metadata,
            "protocol": protocol}


def check_readable(protocol: Dict[str, Any]) -> None:
    """Refuse a table that needs a reader this is not.

    The protocol requires it, and it is the difference between "MAYA cannot
    read this table" and "MAYA read this table wrongly". A table with deletion
    vectors read by a reader that ignores them returns rows that were deleted.
    """
    required = int(protocol.get("minReaderVersion", MIN_READER))
    if required > MIN_READER:
        raise DeltaProtocolError(
            f"this table requires Delta reader version {required} and "
            f"maya_deltalake implements {MIN_READER}. Reading it anyway would "
            f"return rows that a version-{required} feature — deletion "
            f"vectors, column mapping — says are not there. Install the "
            f"`deltalake` package to read it.")
    features = protocol.get("readerFeatures") or []
    if features:
        raise DeltaProtocolError(
            f"this table declares the reader features {', '.join(features)}, "
            f"none of which maya_deltalake implements. Install the `deltalake` "
            f"package to read it.")
