"""
JSON seam (§13.4.2): orjson preferred, stdlib fallback.

``dumps``/``loads`` go through whichever backend the resolver chose.
``canonical`` never does: definition hashes are computed over canonical JSON,
which is on the hash path and therefore Type B — MAYA's own encoding (stdlib
``json`` with sorted keys and fixed separators) is the definition, whatever
accelerator happens to be installed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import hashlib
import json
import uuid
from typing import Any

from maya.core.backends import Backends

JSONDecodeError = json.JSONDecodeError


def _default(obj: Any) -> Any:
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    if isinstance(obj, (uuid.UUID, decimal.Decimal)):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    if hasattr(obj, "item"):          # numpy scalar
        return obj.item()
    if hasattr(obj, "tolist"):        # numpy array
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def dumps(obj: Any, *, indent: int | None = None) -> str:
    """Serialize to a JSON string using the resolved backend."""
    if indent is None and Backends.selected("json") == "orjson":
        import orjson
        return orjson.dumps(obj, default=_default,
                            option=orjson.OPT_NON_STR_KEYS).decode("utf-8")
    return json.dumps(obj, default=_default, indent=indent, ensure_ascii=False)


def loads(text: str | bytes) -> Any:
    """Parse JSON using the resolved backend."""
    if Backends.selected("json") == "orjson":
        import orjson
        return orjson.loads(text)
    return json.loads(text)


def canonical(obj: Any) -> str:
    """Canonical JSON text: sorted keys, no whitespace, stdlib always (Type B)."""
    return json.dumps(obj, default=_default, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)


def canonical_hash(obj: Any) -> str:
    """sha256 of the canonical JSON — the definition hash primitive."""
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()
