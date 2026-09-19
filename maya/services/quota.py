"""
Namespace storage quotas and pin footprints (§7.3).

A namespace may carry a `quota_bytes`. It was stored and never read, so the figure on the
admin screen meant nothing. Here it is enforced, twice:

* **When a pin is asked for** — against an estimate, so an obviously impossible pin is
  refused before a worker spends minutes on it. The estimate comes from the feature's own
  last sealed pin where there is one (same shape, same columns), else from its declared
  schema and the rows it is about to resolve; both are stated as estimates.
* **Before the bytes are written** — against the real figure the writer computed. A queue
  of pins cannot slip past a quota by all being estimated while none is stored yet.

What is charged is **stored** bytes, not logical ones: MAYA's fragments are
content-addressed, so a re-pin of mostly unchanged data adds little, and charging its
logical size would bill a namespace repeatedly for bytes it never added. Usage is read
from the fragment rows a namespace's pins reference, so it counts each fragment once.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.core.errors import QuotaExceeded

# a rough per-value width when nothing better is known, by logical type
_WIDTHS = {
    "float64": 8,
    "float32": 4,
    "int64": 8,
    "int32": 4,
    "bool": 1,
    "date": 4,
    "timestamp": 8,
    "string": 24,
}
DEFAULT_WIDTH = 16
COMPRESSION = 0.35  # parquet + zstd on columnar numeric data, measured on MAYA's own pins


def usage(uow: Any, namespace_id: str) -> dict[str, Any]:
    """Stored and logical bytes a namespace holds, counting each fragment once."""
    feature_ids = [f["id"] for f in uow.repo("features").slim(["id"], namespace_id=namespace_id)]
    set_ids = [s["id"] for s in uow.repo("feature_sets").slim(["id"], namespace_id=namespace_id)]
    pins: list[dict[str, Any]] = []
    if feature_ids:
        pins += uow.repo("feature_pins").list(feature_id__in=feature_ids, state="sealed")
    if set_ids:
        pins += uow.repo("feature_set_pins").list(feature_set_id__in=set_ids, state="sealed")
    digests = {d for pin in pins for d in (pin["fragments"] or [])}
    stored = 0
    if digests:
        for fragment in uow.repo("fragments").list(hash__in=sorted(digests)):
            stored += int(fragment["bytes"] or 0)
    return {
        "pins": len(pins),
        "stored_bytes": stored,
        "logical_bytes": sum(int(pin["bytes_total"] or 0) for pin in pins),
        "fragments": len(digests),
    }


def estimate(
    uow: Any,
    *,
    feature_id: str | None,
    rows: int | None,
    schema: list[dict[str, Any]],
    table: str = "feature_pins",
    key: str = "feature_id",
) -> dict[str, Any]:
    """What a pin of this shape is likely to store, and where the figure came from."""
    if feature_id:
        prior = uow.repo(table).list(
            **{key: feature_id}, state="sealed", order_by=["-created_at"], limit=1
        )
        if prior and (prior[0]["row_count"] or 0) > 0 and prior[0]["bytes_new"]:
            per_row = int(prior[0]["bytes_new"]) / int(prior[0]["row_count"])
            if rows:
                return {
                    "bytes": int(per_row * rows),
                    "basis": "this feature's last sealed pin, per row",
                    "rows": rows,
                }
    width = sum(_WIDTHS.get(a.get("type", ""), DEFAULT_WIDTH) for a in schema) or DEFAULT_WIDTH
    if rows is None:
        return {"bytes": None, "basis": "no row count yet; a first pin cannot be estimated"}
    return {
        "bytes": int(rows * width * COMPRESSION),
        "basis": f"{len(schema)} attribute(s) × {rows} rows, compressed",
        "rows": rows,
    }


def check(uow: Any, namespace: dict[str, Any], adding: int | None, *, what: str = "pin") -> None:
    """Refuse when this namespace's quota cannot take ``adding`` more stored bytes."""
    quota = namespace.get("quota_bytes")
    if not quota or adding is None:
        return
    held = usage(uow, namespace["id"])["stored_bytes"]
    if held + adding <= int(quota):
        return
    raise QuotaExceeded(
        f"Namespace '{namespace['name']}' holds {held / 1e6:.0f} MB of a "
        f"{int(quota) / 1e6:.0f} MB quota; this {what} needs about "
        f"{adding / 1e6:.0f} MB more. Retire pins you no longer need, or ask an "
        "administrator to raise the quota.",
        namespace=namespace["name"],
        quota_bytes=int(quota),
        stored_bytes=held,
        needs_bytes=int(adding),
    )


__all__ = ["COMPRESSION", "check", "estimate", "usage"]
