"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Replay from storage.

Until now a replay needed the caller to hand the data back in. That made it an
*assisted* control: it proved the arithmetic, but only for whoever still had the
numbers, and it could not be run by anybody who did not already trust the person
supplying them.

This reads the dataset snapshot the validation episode was run against, at the
Delta version it was pinned at, and builds the two series each test needs. The
difference is not convenience. A replay that fetches its own data is a control
somebody can run *against* you; one that takes data from you is a control you
help perform.

Two things it will not do.

**It will not silently substitute data.** A validation with no snapshot, a
snapshot whose table is gone, or a test whose columns are not in the frame is
reported as *skipped* with the reason. "We checked and it matched" and "we could
not check" are opposite findings, and blurring them is worse than not replaying.

**It will not read past the pin.** The snapshot names a Delta version and the
read uses it. If the table has been written to since, the replay still sees what
the validation saw, and ``restated()`` says separately that the ground has
moved — which is a finding about the data, not about the test.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger
from core.validation.common import ValidationError

logger = get_logger(__name__)

# How a test's two series are named in the snapshot. A test records the columns
# it read in its own parameters; these are the fallbacks for the common shape.
DEFAULT_LEFT = ("actual", "label", "outcome", "y_true")
DEFAULT_RIGHT = ("predicted", "score", "prediction", "y_pred")


class SnapshotProvider:
    """Serves a replay from the dataset snapshot a validation was run against."""

    def __init__(self, snapshots, delta, features=None):
        self.snapshots, self.delta, self.features = snapshots, delta, features

    # ------------------------------------------------------------------ frame
    def frame(self, snapshot_id: str):
        """The snapshot's rows, at the Delta version it was pinned at."""
        snapshot = self.snapshots.one(id=snapshot_id)
        if snapshot is None:
            raise ValidationError(f"no dataset snapshot {snapshot_id}")
        table = snapshot["delta_table"]
        if not self.delta.exists(table):
            raise ValidationError(
                f"snapshot '{snapshot['name']}' names {table}, which is not in the "
                f"store; the data a validation was run against has been removed")
        return self.delta.read(table, snapshot.get("delta_version"))

    def describe(self, snapshot_id: str) -> Dict[str, Any]:
        """What a replay would read, and whether the ground under it has moved."""
        snapshot = self.snapshots.one(id=snapshot_id)
        if snapshot is None:
            raise ValidationError(f"no dataset snapshot {snapshot_id}")
        table = snapshot["delta_table"]
        present = self.delta.exists(table)
        current = self.delta.version(table) if present else -1
        pinned = snapshot.get("delta_version")
        return {
            "snapshot": snapshot["name"], "table": table,
            "pinned_delta_version": pinned, "current_delta_version": current,
            "readable": present,
            "restated": bool(present and pinned is not None and current > pinned),
            "row_count": snapshot.get("row_count"),
            "pit_verified": bool(snapshot.get("pit_verified")),
            "detail": self._detail(present, pinned, current),
        }

    @staticmethod
    def _detail(present: bool, pinned: Optional[int], current: int) -> str:
        if not present:
            return ("the table this snapshot names is gone; a replay would be "
                    "skipped rather than guessed at")
        if pinned is not None and current > pinned:
            return (f"the table has been written to since: v{pinned} when the "
                    f"validation ran, v{current} now. the replay reads v{pinned}, "
                    f"so a mismatch is about the test and not about the data")
        return "the table is unchanged since the validation ran"

    # --------------------------------------------------------------- provider
    def for_validation(self, validation: Dict[str, Any]):
        """A DataProvider closure over this episode's own snapshot.

        Returns a provider that yields None for every test when the episode has
        no snapshot, so the replay reports *skipped* rather than raising. An
        episode without pinned data is a normal thing that simply cannot be
        replayed from storage, and that is a finding rather than an error.
        """
        snapshot_id = validation.get("snapshot_id")
        if not snapshot_id:
            logger.info("validation %s pins no snapshot; replay from storage "
                        "will report every test as skipped", validation.get("id"))
            return lambda test_key, slice_: None

        frame = self.frame(snapshot_id)

        def provide(test_key: str, slice_: Dict[str, Any]
                    ) -> Optional[Tuple[Sequence, Sequence]]:
            return self.series(frame, slice_)

        return provide

    # ----------------------------------------------------------------- series
    def series(self, frame, slice_: Optional[Dict[str, Any]] = None,
               left: Optional[str] = None, right: Optional[str] = None):
        """The two aligned series a test consumes, sliced as it was sliced."""
        if frame is None or getattr(frame, "empty", True):
            return None
        sliced = self.apply_slice(frame, slice_)
        if sliced.empty:
            return None
        left_col = left or self._column(sliced, DEFAULT_LEFT)
        right_col = right or self._column(sliced, DEFAULT_RIGHT)
        if left_col is None or right_col is None:
            return None
        pair = sliced[[left_col, right_col]].dropna()
        if pair.empty:
            return None
        return list(pair[left_col]), list(pair[right_col])

    @staticmethod
    def _column(frame, candidates) -> Optional[str]:
        for name in candidates:
            if name in frame.columns:
                return name
        return None

    @staticmethod
    def apply_slice(frame, slice_: Optional[Dict[str, Any]]):
        """A slice is an equality filter per column, and a column it does not
        have yields nothing rather than the whole frame — a slice silently
        ignored is a replay of a different population."""
        if not slice_:
            return frame
        out = frame
        for column, value in slice_.items():
            if column not in out.columns:
                return out.iloc[0:0]
            out = out[out[column] == value]
        return out

    # ------------------------------------------------------------------ audit
    def replayable(self, validations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """How much of a model's validation history can be replayed unattended.

        The number that matters to a second line: not whether replay works, but
        what fraction of what was concluded could be checked without asking the
        person who concluded it.
        """
        total = len(validations)
        pinned = [v for v in validations if v.get("snapshot_id")]
        readable = []
        for episode in pinned:
            try:
                if self.describe(episode["snapshot_id"])["readable"]:
                    readable.append(episode)
            except ValidationError as exc:
                logger.info("validation %s is not replayable from storage: %s",
                            episode.get("id"), exc)
        return {
            "episodes": total, "with_snapshot": len(pinned),
            "readable": len(readable),
            "coverage": round(len(readable) / total, 3) if total else 0.0,
            "detail": (f"{len(readable)} of {total} episodes can be replayed "
                       f"without asking anyone for the data"
                       if total else "no validation episodes recorded"),
        }
