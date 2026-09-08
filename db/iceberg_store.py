"""
MAYA — the same feature store, in Apache Iceberg.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

`DeltaStore` with an Iceberg table under it. Same six operations, same
bitemporal contract, same versions pinned by the same contracts — chosen by
configuration, because a bank whose lakehouse is Iceberg should not have to
keep MAYA's feature data in a second format their Trino, Athena or Snowflake
cannot read.

**Why this is a small change and not a rewrite.** MAYA asks a table format for
six things: open it, say what version it is at, read it as it stood at a past
version, read it whole, stream it, and write a new version. Iceberg has all
six. Everything above this file — the point-in-time read, the contracts that
pin a version, the assembly, the evidence — is unchanged, because none of it
knows what is underneath.

**Two differences that are not cosmetic.**

A Delta version is a small sequential integer; an Iceberg snapshot id is a
19-digit int64, and `feature_view_version.delta_version` is `BigInteger` for
that reason. MAYA's own `version` — v1, v2 — is a separate, sequential number
it has always assigned itself, so what a person reads is unchanged whichever
format is underneath.

And Iceberg needs a CATALOG where Delta needs only a path. This uses
pyiceberg's `SqlCatalog` over a SQLite file inside the warehouse directory, so
a default deployment stays self-contained and needs no external service. Point
it at Glue, Nessie, Polaris or a REST catalog through configuration when a bank
already runs one.

**Windows.** The catalog wants a `file://` warehouse URI and a SQLAlchemy URL,
and both are spelled differently on Windows — `file:///C:/maya/data` and
`sqlite:///C:/maya/data/catalog.db` against `file:///home/...` and
`sqlite:////home/...`, four slashes. `pathlib` produces both correctly and is
used rather than string concatenation, which is how that goes wrong.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from core.log import get_logger, swallowed
from db.delta_store import point_in_time, typed_arrow

logger = get_logger(__name__)

#: The catalog's own database, inside the warehouse. A file rather than a
#: service so that `python run_maya_web.py` on a laptop needs nothing else —
#: the same reason the register defaults to SQLite.
CATALOG_DB = "_iceberg_catalog.db"
CATALOG_NAME = "maya"


class IcebergStore:
    """Reads and writes the Iceberg tables beneath a root directory."""

    #: What the backend selector reports.
    format = "iceberg"

    def __init__(self, root: Path, catalog: Optional[Dict[str, str]] = None):
        # RESOLVED, because a file URI cannot express a relative path and the
        # shipped configuration says `dir: ./data`. `Path("data/delta").as_uri()`
        # raises "relative path can't be expressed as a file URI", so a default
        # install would have failed at the first write — on both platforms, and
        # nowhere in a test that passed an absolute tmp_path.
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._catalog_options = dict(catalog or {})
        self._catalog: Any = None

    # ------------------------------------------------------------- catalog
    @property
    def catalog(self) -> Any:
        """The catalog, opened once.

        Lazily, because constructing a store must not require pyiceberg to be
        installed — `db/table_backend.py` decides which store to build and a
        deployment using Delta should never meet an Iceberg import error.
        """
        if self._catalog is None:
            self._catalog = self._open_catalog()
        return self._catalog

    def _open_catalog(self) -> Any:
        try:
            from pyiceberg.catalog.sql import SqlCatalog
        except ImportError as exc:
            logger.error(
                "the table format is Iceberg and pyiceberg is not importable "
                "(%s). No feature data can be read or written until it is "
                "installed or the format is set back to delta.", exc)
            raise RuntimeError(
                "the table format is set to Iceberg and `pyiceberg` is not "
                "installed. Install it, or set MAYA_TABLE_FORMAT=delta. It is "
                "importable without its compiled Avro decoder — the pure "
                "Python fallback is a warning, not a failure."
            ) from exc

        options = dict(self._catalog_options)
        if not options:
            # `as_uri()` and `pathlib`, not string concatenation: a Windows
            # warehouse is `file:///C:/maya/data` and a POSIX one
            # `file:///home/...`, and a SQLite URL takes three slashes on the
            # first and four on the second. Both come out right from the path
            # object and wrong from an f-string somebody wrote on one platform.
            database = self.root / CATALOG_DB
            options = {"uri": f"sqlite:///{database.as_posix()}",
                       "warehouse": self.root.as_uri()}
        logger.info("Iceberg catalog at %s", options.get("uri"))
        return SqlCatalog(CATALOG_NAME, **options)

    # ------------------------------------------------------------ identity
    @staticmethod
    def identifier(table: str) -> Tuple[str, ...]:
        """MAYA's table PATH as an Iceberg identifier.

        `features/borrower/qa_borrower/v1` becomes the namespace
        `features.borrower.qa_borrower` holding the table `v1` — which is what
        the path already means, and reads correctly in any catalog browser a
        bank points at it. Flattening to one name would put
        `features__borrower__qa_borrower__v1` in front of somebody instead.
        """
        return tuple(part for part in str(table).replace("\\", "/").split("/")
                     if part)

    def path(self, table: str) -> str:
        """Where the table lives. Kept for parity with `DeltaStore`, which
        exposes it — and honest that for Iceberg it is the catalog, not the
        path, that resolves a table."""
        return str(self.root / table)

    def _ensure_namespace(self, identifier: Sequence[str]) -> None:
        namespace = tuple(identifier[:-1])
        for depth in range(1, len(namespace) + 1):
            try:
                self.catalog.create_namespace(namespace[:depth])
            except Exception as exc:                    # already there
                swallowed(logger, exc,
                          f"created the namespace {'.'.join(namespace[:depth])}",
                          detail="it already exists, which is the ordinary case",
                          level=logging.DEBUG)

    # ------------------------------------------------------------- reading
    def exists(self, table: str) -> bool:
        try:
            return bool(self.catalog.table_exists(self.identifier(table)))
        except Exception as exc:
            swallowed(logger, exc, f"asked whether the table '{table}' exists",
                      detail="treated as absent", level=logging.DEBUG)
            return False

    def version(self, table: str) -> int:
        """The current snapshot id — the transaction-time coordinate.

        A 19-digit int64 rather than Delta's 0, 1, 2. Both are opaque to
        everything above: what a contract pins is whatever this returns, and
        what a person reads is MAYA's own sequential version.
        """
        if not self.exists(table):
            return -1
        snapshot = self.catalog.load_table(self.identifier(table)).current_snapshot()
        return int(snapshot.snapshot_id) if snapshot else -1

    def _arrow(self, table: str, version: Optional[int] = None) -> Any:
        handle = self.catalog.load_table(self.identifier(table))
        scan = handle.scan(snapshot_id=version) if version is not None \
            else handle.scan()
        return scan.to_arrow()

    def read(self, table: str, as_of_version: Optional[int] = None) -> pd.DataFrame:
        if not self.exists(table):
            return pd.DataFrame()
        return self._arrow(table, as_of_version).to_pandas()

    def dataset(self, table: str, version: Optional[int] = None) -> Any:
        """A pyarrow object the transfer layer can stream in record batches.

        Iceberg has no `to_pyarrow_dataset` that honours a snapshot, so this
        returns an in-memory dataset over the scanned table. That is a REAL
        difference from Delta, where the dataset is over the files and never
        materialises — and it is stated here rather than hidden, because the
        transfer layer exists precisely so a large table does not have to be
        held whole.
        """
        import pyarrow.dataset as ds

        return ds.dataset(self._arrow(table, version))

    def columns_of(self, table: str, version: Optional[int] = None) -> Set[str]:
        if not self.exists(table):
            return set()
        handle = self.catalog.load_table(self.identifier(table))
        return {field.name for field in handle.schema().fields}

    def row_count(self, table: str) -> int:
        return len(self.read(table))

    # ------------------------------------------------------------- writing
    def write(self, table: str, rows: List[Dict[str, Any]],
              mode: str = "append",
              dtypes: Optional[Dict[str, str]] = None) -> int:
        """Write rows and return the resulting snapshot id.

        `dtypes` types the columns that arrive entirely null. Iceberg v2
        refuses `pa.null()` by specification — it is not a storable type — and
        the alternative to typing them would be creating tables at format
        version 3, which fewer engines can read and would give away the reason
        to choose Iceberg in the first place.
        """
        if not rows:
            return self.version(table)
        identifier = self.identifier(table)
        arrow = typed_arrow(rows, dtypes)
        if not self.exists(table):
            self._ensure_namespace(identifier)
            handle = self.catalog.create_table(identifier, schema=arrow.schema)
        else:
            handle = self.catalog.load_table(identifier)
            if mode == "overwrite" and \
                    handle.schema().as_arrow() != arrow.schema:
                # An overwrite REPLACING the schema is the case MAYA needs:
                # it is how an orphaned materialisation is cleared, and the
                # view may have been redefined in between — which is often why
                # the first attempt failed. Iceberg will not widen on
                # overwrite, so the table is dropped and remade.
                self.catalog.drop_table(identifier)
                handle = self.catalog.create_table(identifier,
                                                   schema=arrow.schema)
        if mode == "overwrite":
            handle.overwrite(arrow)
        else:
            handle.append(arrow)
        return self.version(table)

    # --------------------------------------------------------- bitemporal
    def as_of(self, table: str, valid_before: float, known_before: float,
              delta_version: Optional[int] = None) -> pd.DataFrame:
        """The point-in-time read — the SAME rule, called rather than copied.

        `point_in_time` lives in `db/delta_store.py` and both stores call it.
        A second implementation here, even a faster one written against
        Iceberg's own filtering, would be the disagreement `pit_order_key`
        exists to prevent: two point-in-time paths that break a tie opposite
        ways, one of them putting a value in the training set and the other
        reporting a violation against it.
        """
        return point_in_time(self.read(table, delta_version),
                             valid_before, known_before)

    def vacuum_horizon_days(self, retention_days: int) -> int:
        """Retention is a governance decision held in configuration, not here."""
        return max(retention_days, 0)


__all__ = ["CATALOG_DB", "CATALOG_NAME", "IcebergStore"]
