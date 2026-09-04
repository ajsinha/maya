"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Bulk transfer of feature values, in and out.

Everything else in this platform moves small documents: a warrant, a contract, a
finding. Feature values are not small. A featureset over a few million entities
is the ordinary case, and an API that turns it into JSON objects — one dictionary
per row, keys repeated on every line — spends most of its time and nearly all of
its memory on punctuation.

So the rule here is different from everywhere else: **nothing is materialised
whole.** Reads iterate Arrow record batches straight off the Delta files and
write them out as they go; writes parse a batch at a time and append. The peak
memory of a transfer is one batch, not one dataset, whether that dataset is a
thousand rows or a hundred million.

Four formats, and the choice is not cosmetic:

- **arrow** — the streaming format. Zero-copy on both ends, and the only one that
  is genuinely incremental in both directions. This is what an execution engine
  should use.
- **parquet** — the interchange format. Columnar and compressed, and what
  somebody will actually want on disk. Assembled to a temporary file and streamed
  from it, because a Parquet file's footer cannot be written until the end.
- **ndjson** — the lowest common denominator. Streams, and anything can read it.
- **json** — for a human looking at a page. Hard-capped, because a browser asking
  for ten million rows is a mistake and answering it is not a kindness.

The bitemporal columns are never optional in a write. A feature row without both
clocks cannot be assembled point-in-time, and accepting it here to be helpful
would put the problem two layers away from where it was caused.
"""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from core.features.common import ENTITY, INGEST_TIME, RESERVED, VALID_TIME, FeatureError
from core.log import get_logger

logger = get_logger(__name__)

ARROW, PARQUET, NDJSON, JSON = "arrow", "parquet", "ndjson", "json"
FORMATS: Tuple[str, ...] = (ARROW, PARQUET, NDJSON, JSON)

MEDIA_TYPE: Dict[str, str] = {
    ARROW: "application/vnd.apache.arrow.stream",
    PARQUET: "application/vnd.apache.parquet",
    NDJSON: "application/x-ndjson",
    JSON: "application/json",
}
BY_MEDIA_TYPE: Dict[str, str] = {v: k for k, v in MEDIA_TYPE.items()}

FORMAT_MEANING: Dict[str, str] = {
    ARROW: "streaming Arrow IPC — zero-copy, incremental both ways; use this "
           "from an execution engine",
    PARQUET: "columnar and compressed; use this when the data is going to disk",
    NDJSON: "one JSON object per line; streams, and anything can read it",
    JSON: "a single document, hard-capped; use this for a page, not for a job",
}

# Rows per Arrow batch. Large enough that the per-batch overhead disappears,
# small enough that one batch is never the thing that exhausts memory.
BATCH_ROWS = 16_384

# A row count alone is the wrong unit: 16k rows of six columns is a few
# megabytes, and 16k rows of two thousand columns is not. The batch is sized by
# CELLS, so a wide table is read in narrower slices and the "peak memory is one
# batch" claim holds for both shapes.
TARGET_CELLS = 1 << 20
MIN_BATCH_ROWS = 512


def batch_for(columns: int, ceiling: int = BATCH_ROWS) -> int:
    """How many rows to read at a time for a table this wide."""
    if columns <= 0:
        return ceiling
    return max(MIN_BATCH_ROWS, min(ceiling, TARGET_CELLS // columns))

# A JSON read is for looking at, so it is capped rather than paged forever.
JSON_CAP = 10_000


def normalise(fmt: Optional[str], accept: Optional[str] = None) -> str:
    """The format to write, from an explicit choice or an Accept header."""
    if fmt:
        if fmt not in FORMATS:
            raise FeatureError(
                f"'{fmt}' is not a transfer format; expected one of "
                f"{', '.join(FORMATS)}")
        return fmt
    for media, name in BY_MEDIA_TYPE.items():
        if accept and media in accept:
            return name
    return JSON


class _Drain:
    """A sink Arrow can write to, whose bytes can be taken away as they arrive.

    ``pa.BufferOutputStream`` only gives its contents up at the end, which is the
    opposite of what a streaming response wants.
    """

    def __init__(self) -> None:
        self._parts: List[bytes] = []

    def write(self, data) -> int:
        payload = bytes(data)
        self._parts.append(payload)
        return len(payload)

    def drain(self) -> bytes:
        out, self._parts = b"".join(self._parts), []
        return out

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None

    @property
    def closed(self) -> bool:
        return False

    def tell(self) -> int:
        return sum(len(p) for p in self._parts)

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False


class FeatureTransfer:
    """Streams feature values out of Delta and back into it."""

    def __init__(self, delta, views, sets=None, batch_rows: int = BATCH_ROWS):
        self.delta, self.views, self.sets = delta, views, sets
        self.batch_rows = batch_rows

    # ------------------------------------------------------------------ read
    def batches(self, table: str, delta_version: Optional[int] = None,
                columns: Optional[Sequence[str]] = None,
                limit: Optional[int] = None) -> Iterator[Any]:
        """Arrow record batches, straight off the files. Nothing whole."""
        import pyarrow as pa
        from deltalake import DeltaTable

        if not self.delta.exists(table):
            return
        dt = DeltaTable(self.delta.path(table))
        if delta_version is not None:
            dt.load_as_version(delta_version)
        dataset = dt.to_pyarrow_dataset()
        wanted = list(columns) if columns else None
        if wanted:
            present = set(dataset.schema.names)
            if missing := [c for c in wanted if c not in present]:
                raise FeatureError(
                    f"the table does not hold {', '.join(missing)}; asking for a "
                    f"column that is not there is a different request from asking "
                    f"for one that is empty")
        width = len(wanted) if wanted else len(dataset.schema.names)
        seen = 0
        for batch in dataset.to_batches(columns=wanted,
                                        batch_size=batch_for(width,
                                                             self.batch_rows)):
            if batch.num_rows == 0:
                continue
            if limit is not None and seen + batch.num_rows > limit:
                batch = batch.slice(0, max(limit - seen, 0))
                if batch.num_rows:
                    yield batch
                return
            seen += batch.num_rows
            yield batch

    def check_columns(self, table: str, columns: Optional[Sequence[str]],
                      delta_version: Optional[int] = None) -> None:
        """Refuse an absent column BEFORE a response starts streaming.

        A generator raises on its first pull, which is after the status line has
        already gone out — so the caller would get a 200 that stops mid-body.
        Checking here means the refusal is still a refusal.
        """
        if not columns:
            return
        from deltalake import DeltaTable
        if not self.delta.exists(table):
            return
        dt = DeltaTable(self.delta.path(table))
        if delta_version is not None:
            dt.load_as_version(delta_version)
        present = set(dt.to_pyarrow_dataset().schema.names)
        if missing := [c for c in columns if c not in present]:
            raise FeatureError(
                f"the table does not hold {', '.join(missing)}; asking for a "
                f"column that is not there is a different request from asking "
                f"for one that is empty")

    def stream(self, table: str, fmt: str = ARROW,
               delta_version: Optional[int] = None,
               columns: Optional[Sequence[str]] = None,
               limit: Optional[int] = None) -> Iterator[bytes]:
        """Bytes in the chosen format, produced as the batches arrive."""
        if fmt == ARROW:
            yield from self._arrow(table, delta_version, columns, limit)
        elif fmt == PARQUET:
            yield from self._parquet(table, delta_version, columns, limit)
        elif fmt == NDJSON:
            yield from self._ndjson(table, delta_version, columns, limit)
        else:
            raise FeatureError(
                f"'{fmt}' is not a streaming format; json is read whole and "
                f"capped, so ask for it through rows() instead")

    def _arrow(self, table, version, columns, limit) -> Iterator[bytes]:
        """One IPC stream, drained as it is written.

        One stream, not one per batch: the schema header is written once and the
        batches follow it. Emitting a fresh stream per batch produces a
        concatenation that no reader will open, which is the kind of thing that
        looks like it works until somebody tries to read it back.
        """
        import pyarrow as pa

        sink = _Drain()
        writer = None
        for batch in self.batches(table, version, columns, limit):
            if writer is None:
                writer = pa.ipc.new_stream(sink, batch.schema)
            writer.write_batch(batch)
            # Hand the bytes on as they are produced; the consumer can begin
            # work before the producer has finished reading.
            if chunk := sink.drain():
                yield chunk
        if writer is not None:
            writer.close()
            if chunk := sink.drain():
                yield chunk

    def _parquet(self, table, version, columns, limit) -> Iterator[bytes]:
        """Assembled to a temporary file, then streamed from it.

        A Parquet file's footer holds the row-group index and cannot be written
        until the last row is known, so this format cannot be produced
        incrementally. The file still never holds more than one batch in memory
        on the way in, and is read back in chunks on the way out.
        """
        import pyarrow.parquet as pq

        with tempfile.NamedTemporaryFile(suffix=".parquet") as handle:
            writer = None
            for batch in self.batches(table, version, columns, limit):
                if writer is None:
                    writer = pq.ParquetWriter(handle.name, batch.schema,
                                              compression="snappy")
                writer.write_batch(batch)
            if writer is None:
                return
            writer.close()
            handle.seek(0)
            while chunk := handle.read(1 << 20):
                yield chunk

    def _ndjson(self, table, version, columns, limit) -> Iterator[bytes]:
        for batch in self.batches(table, version, columns, limit):
            lines = [json.dumps(row, default=str)
                     for row in batch.to_pylist()]
            yield ("\n".join(lines) + "\n").encode()

    def rows(self, table: str, delta_version: Optional[int] = None,
             columns: Optional[Sequence[str]] = None,
             limit: int = JSON_CAP) -> Dict[str, Any]:
        """A capped JSON page, for a person rather than for a job."""
        capped = min(limit, JSON_CAP)
        out: List[Dict[str, Any]] = []
        for batch in self.batches(table, delta_version, columns, capped):
            out.extend(batch.to_pylist())
        total = self.delta.row_count(table) if self.delta.exists(table) else 0
        return {
            "rows": out, "returned": len(out), "total": total,
            "truncated": total > len(out),
            "detail": (f"showing {len(out):,} of {total:,} rows; JSON is capped "
                       f"at {JSON_CAP:,} — ask for arrow or parquet to take the "
                       f"whole thing"
                       if total > len(out) else f"{len(out):,} rows"),
        }

    # ----------------------------------------------------------------- write
    def parse(self, data: bytes, media_type: str) -> Iterator[Any]:
        """Record batches from an uploaded body, a batch at a time."""
        import pyarrow as pa
        import pyarrow.json as pj
        import pyarrow.parquet as pq

        fmt = BY_MEDIA_TYPE.get((media_type or "").split(";")[0].strip())
        if fmt is None:
            raise FeatureError(
                f"'{media_type}' is not a format this accepts; send one of "
                f"{', '.join(MEDIA_TYPE[f] for f in FORMATS)}")
        if not data:
            raise FeatureError("the upload is empty")
        try:
            if fmt == ARROW:
                reader = pa.ipc.open_stream(pa.BufferReader(data))
                for batch in reader:
                    yield batch
            elif fmt == PARQUET:
                table = pq.read_table(pa.BufferReader(data))
                for batch in table.to_batches(self.batch_rows):
                    yield batch
            elif fmt == NDJSON:
                table = pj.read_json(pa.BufferReader(data))
                for batch in table.to_batches(self.batch_rows):
                    yield batch
            else:
                table = pa.Table.from_pylist(json.loads(data.decode()))
                for batch in table.to_batches(self.batch_rows):
                    yield batch
        except Exception as exc:                       # noqa: BLE001 — reported
            # Nothing inside the block raises FeatureError: the format check
            # happens above it, so every exception here is a parse failure.
            logger.warning("could not parse a %s upload: %s", fmt, exc)
            raise FeatureError(
                f"the upload does not parse as {fmt}: {exc}. the declared "
                f"content type and the bytes disagree") from exc

    @staticmethod
    def check_clocks(schema_names: Sequence[str]) -> None:
        """Both clocks and the entity, or the rows cannot be assembled later.

        Accepting them here to be helpful would move the failure two layers away
        from the upload that caused it, which is where it stops being fixable.
        """
        missing = [c for c in (ENTITY, VALID_TIME, INGEST_TIME)
                   if c not in schema_names]
        if missing:
            raise FeatureError(
                f"the upload is missing {', '.join(missing)}. feature rows carry "
                f"two clocks — {VALID_TIME} (when the fact was true) and "
                f"{INGEST_TIME} (when the platform learned it) — and an entity "
                f"key; without them the rows cannot be assembled "
                f"point-in-time, and a set built from them could not be shown "
                f"free of leakage")

    def load(self, view_name: str, data: bytes, media_type: str,
             feature_names: Optional[Sequence[str]] = None,
             actor: str = "system") -> Dict[str, Any]:
        """Materialise an uploaded batch as a new feature view version.

        The whole upload becomes one version, because a version is what a
        featureset pins and half a version is not a thing anybody can pin.
        """
        import pyarrow as pa

        batches = list(self.parse(data, media_type))
        if not batches:
            raise FeatureError("the upload holds no rows")
        self.check_clocks(batches[0].schema.names)
        table = pa.Table.from_batches(batches)
        names = list(feature_names or
                     [c for c in table.schema.names if c not in RESERVED])
        rows = table.to_pylist()
        result = self.views.materialise(view_name, rows, names, actor=actor)
        return {**result, "uploaded_rows": len(rows), "columns": names,
                "detail": f"{len(rows):,} rows materialised as "
                          f"{view_name} v{result['version']}"}

    # ------------------------------------------------------------ featuresets
    def featureset_table(self, name: str, version: int) -> Dict[str, Any]:
        """Which namespaces a featureset version's data lives in.

        A featureset spans several views, so exporting one is a join rather than
        a file copy. The plan is returned so a caller can decide whether to pull
        the parts itself — which is what an engine wanting parallelism should do.
        """
        if self.sets is None:
            raise FeatureError("this transfer was built without featuresets")
        plan = self.sets.plan(name, version)
        parts = {}
        for slot in plan["slots"]:
            parts.setdefault(slot["namespace"], {
                "namespace": slot["namespace"],
                "delta_version": slot.get("delta_version"),
                "columns": []})
            parts[slot["namespace"]]["columns"].append(slot["feature"])
        return {"featureset": name, "version": version,
                "entity": plan["entity"], "digest": plan["digest"],
                "label": plan["label"], "pit_rule": plan["pit_rule"],
                "parts": list(parts.values()),
                "detail": (f"{len(plan['slots'])} slots across "
                           f"{len(parts)} namespaces; pull the parts in parallel "
                           f"or ask for the join")}

    def featureset_batches(self, name: str, version: int,
                           limit: Optional[int] = None) -> Iterator[Any]:
        """The joined featureset, one Arrow batch at a time.

        Joined on the entity key. The parts are read at their pinned Delta
        versions, so this returns what the version pinned rather than what the
        namespaces currently hold.
        """
        import pyarrow as pa

        plan = self.featureset_table(name, version)
        frames = []
        for part in plan["parts"]:
            columns = sorted({ENTITY, VALID_TIME, INGEST_TIME, *part["columns"]})
            batches = list(self.batches(part["namespace"], part["delta_version"],
                                        columns))
            if batches:
                frames.append(pa.Table.from_batches(batches))
        if not frames:
            return
        joined = frames[0]
        for other in frames[1:]:
            joined = joined.join(other, keys=ENTITY,
                                 right_suffix="_r", join_type="inner")
        if limit is not None:
            joined = joined.slice(0, limit)
        for batch in joined.to_batches(self.batch_rows):
            yield batch

    def featureset_stream(self, name: str, version: int, fmt: str = ARROW,
                          limit: Optional[int] = None) -> Iterator[bytes]:
        """The joined featureset in the chosen format."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        batches = self.featureset_batches(name, version, limit)
        if fmt == NDJSON:
            for batch in batches:
                yield ("\n".join(json.dumps(r, default=str)
                                 for r in batch.to_pylist()) + "\n").encode()
            return
        collected = list(batches)
        if not collected:
            return
        table = pa.Table.from_batches(collected)
        if fmt == ARROW:
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, table.schema) as writer:
                writer.write_table(table)
            yield sink.getvalue().to_pybytes()
        elif fmt == PARQUET:
            with tempfile.NamedTemporaryFile(suffix=".parquet") as handle:
                pq.write_table(table, handle.name, compression="snappy")
                handle.seek(0)
                while chunk := handle.read(1 << 20):
                    yield chunk
        else:
            raise FeatureError(f"'{fmt}' cannot be streamed; ask for json "
                               f"through the paged endpoint")


def describe() -> Dict[str, Any]:
    """What the transfer surface offers, so a client need not guess."""
    return {
        "formats": [{"format": f, "media_type": MEDIA_TYPE[f],
                     "means": FORMAT_MEANING[f]} for f in FORMATS],
        "batch_rows": BATCH_ROWS,
        "json_cap": JSON_CAP,
        "required_columns": [ENTITY, VALID_TIME, INGEST_TIME],
        "note": "nothing is materialised whole: reads iterate Arrow batches off "
                "the Delta files and writes parse a batch at a time, so peak "
                "memory is one batch rather than one dataset",
    }
