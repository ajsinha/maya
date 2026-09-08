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
from typing import Any, Dict, List, Optional

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

    def write(self, table: str, rows: List[Dict[str, Any]], mode: str = "append") -> int:
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
        write_deltalake(self.path(table), pd.DataFrame(rows), mode=mode, **extra)
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

    # --------------------------------------------------------- bitemporal read
    def as_of(self, table: str, valid_before: float, known_before: float,
              delta_version: Optional[int] = None) -> pd.DataFrame:
        """The latest fact per entity that was BOTH true by ``valid_before`` and
        known by ``known_before``.

        This is the point-in-time rule. Both bounds are required; dropping
        either is exactly the leakage this exists to prevent.
        """
        df = self.read(table, delta_version)
        if df.empty:
            return df
        eligible = df[(df[VALID_TIME] <= valid_before) & (df[INGEST_TIME] <= known_before)]
        if eligible.empty:
            return eligible
        # Sorted by the SAME total order the assembler uses, content included.
        #
        # `[VALID_TIME, INGEST_TIME]` is a partial order: two records for one
        # entity stamped identically on both clocks are equal under it, and the
        # two point-in-time implementations then broke the tie opposite ways —
        # `max(...)` keeps the first maximal element, `keep="last"` keeps the
        # last. A view holding a duplicate stamp therefore put one value in the
        # training set and made this, the independent verifier, report a
        # violation against it. `pit_order_key` is total and content-based, so
        # neither path can pick differently and a Delta rewrite cannot change
        # the answer.
        ordered = eligible.assign(
            _pit_order=[pit_order_key(r) for r in eligible.to_dict("records")]
        ).sort_values("_pit_order", kind="stable").drop(columns=["_pit_order"])
        # The last ROW per entity, not the last non-null value per column.
        #
        # `groupby().last()` does the second, and the difference is a defect
        # rather than a subtlety: a restatement that WITHDRAWS a figure -- sets
        # it null, which is a legitimate correction -- had the superseded value
        # resurrected and welded onto the withdrawal's timestamps. The row
        # returned then asserted that the old figure was known at a moment when
        # it had already been retracted: a bitemporal state that never existed,
        # produced by the function whose docstring calls itself the
        # point-in-time rule.
        #
        # It also made the two point-in-time paths disagree by construction.
        # `core/features/assembly.py` verifies an assembly by recomputing it
        # through here, so a routine withdrawal made the independent verifier
        # report a violation against a correct assembly -- which is how a
        # verifier stops being believed.
        return (ordered.drop_duplicates(subset=[ENTITY], keep="last")
                       .reset_index(drop=True))

    def vacuum_horizon_days(self, retention_days: int) -> int:
        """Retention is a governance decision held in configuration, not here."""
        return max(retention_days, 0)
