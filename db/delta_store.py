"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Delta Lake access. Confined to the persistence package with everything else
that knows how data is stored.

Feature rows are BITEMPORAL. Every row carries two clocks:

    event_ts   VALID time       — when the fact was true in the world
    ingest_ts  TRANSACTION time — when MAYA learned it

Conflating them is the dominant silent failure mode in model development: a
training set assembled from facts that had not been recorded when the decision
was taken validates beautifully and performs badly, and the gap is then
misdiagnosed as drift. Delta's own table versions give the transaction-time
axis for free, which is why Delta rather than a plain table is the substrate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd
# Chosen in one place. `deltalake` where it is installed, MAYA's own
# pure-Python subset where binary wheels are forbidden — see
# `db/delta_backend.py` for why the choice is made once rather than at
# each of the three import sites that used to make it.
from db.delta_backend import DeltaTable, write_deltalake

from core.log import get_logger

logger = get_logger(__name__)

VALID_TIME = "event_ts"
INGEST_TIME = "ingest_ts"
ENTITY = "entity_id"
RESERVED = frozenset({ENTITY, VALID_TIME, INGEST_TIME})


def pit_order_key(record: Dict[str, Any]) -> tuple:
    """The total order the point-in-time read picks its winner by.

    `(event_ts, ingest_ts)` alone is a PARTIAL order: two records for one entity
    stamped identically on both clocks are equal under it, and the two
    point-in-time implementations broke the tie opposite ways. The assembler
    took `max(...)`, which keeps the FIRST maximal element; this file sorted
    stably and took `drop_duplicates(keep="last")`, which keeps the last. So a
    view holding a duplicate stamp put one value into the training set and made
    the independent verifier report a violation against it — a correct assembly
    marked `pit_verified: false`, which is how a verifier stops being believed.

    The third component is the record's own content, canonically serialised.
    Arbitrary in the sense that neither record is genuinely later — nothing can
    make one later — but TOTAL, and independent of storage order, so a Delta
    rewrite cannot change which row wins and the two paths cannot disagree.

    It lives here, in the lower layer, because `db` may not import `core`:
    `core.features.common` re-exports it rather than keeping a second copy that
    could drift from this one.
    """
    return (record[VALID_TIME], record[INGEST_TIME],
            repr(sorted((str(k), repr(v)) for k, v in record.items()
                        if k not in RESERVED)))


#: A MAYA dtype to the Arrow type a column of it should have.
#:
#: Used only for columns that arrive ENTIRELY NULL, where Arrow infers
#: `pa.null()` and neither format can do anything useful with it — Delta stores
#: a null-typed column that reads back as nothing, and Iceberg v2 refuses it
#: outright. MAYA knows the answer: a feature declares its dtype, and a view
#: knows its features. It simply was not passing it down.
#:
#: Timestamps map to `double` because MAYA's clocks are epoch seconds
#: throughout — see the schema's own note on why they are not a date type.
ARROW_FOR: Dict[str, str] = {
    "numeric": "double", "integer": "int64", "boolean": "bool",
    "categorical": "string", "string": "string",
    "date": "double", "datetime": "double",
}


def arrow_type(dtype: str) -> Any:
    """The Arrow type for a MAYA dtype, defaulting to string.

    A default rather than a refusal, because this is only reached for a column
    with no values in it: getting it wrong costs the type of an empty column,
    and refusing would stop a materialisation over a feature that happens to
    have nothing in this window.
    """
    import pyarrow as pa

    return {"double": pa.float64(), "int64": pa.int64(), "bool": pa.bool_(),
            "string": pa.string()}[ARROW_FOR.get(dtype or "", "string")]


def typed_arrow(rows: List[Dict[str, Any]],
                dtypes: Optional[Dict[str, str]] = None) -> Any:
    """Rows as an Arrow table, with all-null columns given a real type.

    Arrow infers `pa.null()` for a column that is null in every row, which is
    the one case where inference cannot work and MAYA has the answer anyway.
    """
    import pyarrow as pa

    table = pa.Table.from_pylist(rows)
    if not dtypes:
        return table
    fields = []
    changed = False
    for field in table.schema:
        if pa.types.is_null(field.type) and field.name in dtypes:
            fields.append(pa.field(field.name, arrow_type(dtypes[field.name])))
            changed = True
        else:
            fields.append(field)
    return table.cast(pa.schema(fields)) if changed else table


def point_in_time(frame: "pd.DataFrame", valid_before: float,
                  known_before: float) -> "pd.DataFrame":
    """The latest fact per entity that was BOTH true by `valid_before` and
    known by `known_before`.

    This is the point-in-time rule. Both bounds are required; dropping either
    is exactly the leakage this exists to prevent.

    A MODULE-LEVEL function rather than a method, because MAYA now has two
    table formats and each needs it. A copy in each store would be two
    implementations of the one rule the whole platform rests on — and the
    comment below is about what happens when two implementations of it
    disagree, so writing a second one under a note saying "identical,
    deliberately" would be the joke telling itself.

    Sorted by the SAME total order the assembler uses, content included.

    `[VALID_TIME, INGEST_TIME]` is a partial order: two records for one entity
    stamped identically on both clocks are equal under it, and the two
    point-in-time implementations then broke the tie opposite ways —
    `max(...)` keeps the first maximal element, `keep="last"` keeps the last. A
    view holding a duplicate stamp therefore put one value in the training set
    and made the independent verifier report a violation against it.
    `pit_order_key` is total and content-based, so neither path can pick
    differently and a rewrite by either format cannot change the answer.

    The last ROW per entity, not the last non-null value per column.
    `groupby().last()` does the second, and the difference is a defect rather
    than a subtlety: a restatement that WITHDRAWS a figure — sets it null,
    which is a legitimate correction — had the superseded value resurrected
    and welded onto the withdrawal's timestamps. The row returned then
    asserted that the old figure was known at a moment when it had already
    been retracted: a bitemporal state that never existed, produced by the
    function whose docstring calls itself the point-in-time rule.
    """
    if frame.empty:
        return frame
    eligible = frame[(frame[VALID_TIME] <= valid_before)
                     & (frame[INGEST_TIME] <= known_before)]
    if eligible.empty:
        return eligible
    ordered = eligible.assign(
        _pit_order=[pit_order_key(r) for r in eligible.to_dict("records")]
    ).sort_values("_pit_order", kind="stable").drop(columns=["_pit_order"])
    return (ordered.drop_duplicates(subset=[ENTITY], keep="last")
                   .reset_index(drop=True))


class DeltaStore:
    """Reads and writes the Delta tables beneath a root directory."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, table: str) -> str:
        return str(self.root / table)

    def exists(self, table: str) -> bool:
        return (self.root / table / "_delta_log").exists()

    def version(self, table: str) -> int:
        """The current Delta version — the transaction-time coordinate."""
        return DeltaTable(self.path(table)).version() if self.exists(table) else -1

    def write(self, table: str, rows: List[Dict[str, Any]], mode: str = "append",
              dtypes: Optional[Dict[str, str]] = None) -> int:
        """Append rows and return the resulting table version.

        An `overwrite` replaces the schema as well as the rows. Delta keeps the
        existing schema on an overwrite unless told otherwise, which is right
        for a table being refreshed and wrong for the only case that asks for
        overwrite here: replacing an ORPHAN left by a materialisation that wrote
        Delta and failed before recording it. That orphan may have been written
        from a different set of features — the view was redefined in between,
        which is often WHY the first attempt failed — and refusing on
        `SchemaMismatchError` leaves the table permanently unwritable with no
        way through the product.
        """
        if not rows:
            return self.version(table)
        extra = {"schema_mode": "overwrite"} if mode == "overwrite" else {}
        # Through Arrow rather than straight to pandas, so a column that is
        # null in every row gets the type the FEATURE declares instead of
        # Arrow's `null` — which reads back as nothing here and is refused
        # outright by Iceberg. Both formats now write the same schema for the
        # same rows, which is the property that makes them swappable.
        write_deltalake(self.path(table), typed_arrow(rows, dtypes),
                        mode=mode, **extra)
        return self.version(table)

    def read(self, table: str, as_of_version: Optional[int] = None) -> pd.DataFrame:
        """Read the table, optionally as it stood at a past Delta version."""
        if not self.exists(table):
            return pd.DataFrame()
        dt = DeltaTable(self.path(table))
        if as_of_version is not None:
            dt.load_as_version(as_of_version)
        return dt.to_pandas()

    def row_count(self, table: str) -> int:
        return len(self.read(table))

    # ------------------------------------------------------- streaming reads
    def dataset(self, table: str, version: Optional[int] = None) -> Any:
        """A pyarrow Dataset over the table, optionally at a past version.

        Here rather than in `core/features/transfer.py`, which opened a
        `DeltaTable` itself — so the ONE layer that is supposed to know the
        table format had a second module reaching past it, and adding a
        different format meant finding every such reach. There is one now.

        A Dataset rather than a Table, because the caller streams record
        batches: materialising is exactly what that layer exists to avoid.
        """
        table_handle = DeltaTable(self.path(table))
        if version is not None:
            table_handle.load_as_version(version)
        return table_handle.to_pyarrow_dataset()

    def columns_of(self, table: str, version: Optional[int] = None) -> Set[str]:
        """What columns this table has, without reading a row."""
        if not self.exists(table):
            return set()
        return set(self.dataset(table, version).schema.names)

    # --------------------------------------------------------- bitemporal read
    def as_of(self, table: str, valid_before: float, known_before: float,
              delta_version: Optional[int] = None) -> pd.DataFrame:
        """The latest fact per entity that was BOTH true by ``valid_before`` and
        known by ``known_before``.

        The rule itself is `point_in_time` below, so that a second table format
        cannot hold a second copy of it. This reads the rows; the rule decides.
        """
        return point_in_time(self.read(table, delta_version),
                             valid_before, known_before)

    def vacuum_horizon_days(self, retention_days: int) -> int:
        """Retention is a governance decision held in configuration, not here."""
        return max(retention_days, 0)
