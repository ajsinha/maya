"""
MAYA — which table format holds the feature data, decided once.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Delta or Iceberg, by configuration. Nothing above `db/` knows which.

**Why both.** MAYA asks a table format for six things — open, current version,
read at a past version, read whole, stream, write a new version — and both have
all six. A bank whose lakehouse is Iceberg should not have to keep its feature
data in a second format their Trino, Athena or Snowflake cannot read; a bank
with neither preference should not have to think about it, so Delta stays the
default.

**Delta is still the default**, and not by inertia: it is what four hours of
soak, 3,548 tests twice over and every worked example in the documentation have
actually run against. Iceberg is offered, not assumed.

    MAYA_TABLE_FORMAT=iceberg          # environment
    data.table_format: iceberg         # or configuration

Set it once, at the start. **Switching format on an estate that already holds
data does not migrate it** — the tables are in the old format and the new store
will not find them. That is stated in the log at start-up rather than left to be
discovered, because a feature view that silently reads as empty is the worst
possible way to learn it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.log import get_logger

logger = get_logger(__name__)

ENV = "MAYA_TABLE_FORMAT"
DELTA, ICEBERG = "delta", "iceberg"
FORMATS = (DELTA, ICEBERG)


def chosen(configured: Optional[str] = None) -> str:
    """Which format this instance uses. The environment wins over the file."""
    wanted = (os.environ.get(ENV) or configured or DELTA).strip().lower()
    if wanted not in FORMATS:
        raise ValueError(
            f"'{wanted}' is not a table format; use {' or '.join(FORMATS)}. "
            f"Set it with {ENV} or `data.table_format` in the configuration.")
    return wanted


def build(root: Path, configured: Optional[str] = None,
          catalog: Optional[Dict[str, str]] = None) -> Any:
    """The store this instance should use, and a line saying which.

    Built here rather than at each call site so that "which format is this
    estate in" has one answer and one place that decides it.
    """
    fmt = chosen(configured)
    if fmt == ICEBERG:
        from db.iceberg_store import IcebergStore

        store = IcebergStore(root, catalog=catalog)
        logger.warning(
            "feature data is stored as ICEBERG, at %s. Switching format does "
            "not migrate anything: tables written as Delta are not visible to "
            "this store, and a feature view whose data was written in the "
            "other format reads as empty rather than failing. Set %s=delta to "
            "go back.", root, ENV)
        return store

    from db.delta_store import DeltaStore

    logger.info("feature data is stored as Delta, at %s", root)
    return DeltaStore(root)


def describe(store: Any) -> Dict[str, Any]:
    """What is underneath, for `/health` and for a soak report to record.

    Both halves: the TABLE FORMAT — Delta or Iceberg — and, when it is Delta,
    which implementation is writing it, since MAYA has its own for estates that
    forbid binary wheels. A run whose result depends on either should not need
    a person to work out which was in use.
    """
    fmt = getattr(store, "format", DELTA)
    out: Dict[str, Any] = {"table_format": fmt}
    if fmt == DELTA:
        from db.delta_backend import describe as delta_describe

        out.update(delta_describe())
    else:
        out.update({"backend": "pyiceberg",
                    "catalog": getattr(store, "_catalog_options", None) or
                               "a SQLite catalog inside the warehouse",
                    "detail": "Apache Iceberg. Snapshot ids are int64, which "
                              "is why the version columns are BIGINT"})
    return out


__all__ = ["DELTA", "ENV", "FORMATS", "ICEBERG", "build", "chosen", "describe"]
