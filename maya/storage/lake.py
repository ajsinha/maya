"""
The ``LakeStore`` port over ``maya_delta`` (§7.1, §7.4, §29.3).

Two kinds of Delta table per feature or feature set:

* ``raw/<namespace>/<name>`` — the bitemporal ingest log. Every upload is
  appended with its ``_knowledge_time``; a restatement is a new append, never
  an overwrite (§29.1).
* ``pins/<namespace>/<name>`` — the fragment store. One Delta table, one
  partition per content-addressed fragment. A pin is an ordered list of
  fragment hashes; pinning writes only fragments the table has never seen,
  so an unchanged month costs its delta rather than its size (SC-12).

Content hashes are computed by ``maya.core.canonical`` over values, never
over file bytes, so they do not depend on which Delta backend wrote them.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa

from maya.core import canonical
from maya.core.chunker import ChunkParams, boundaries

FRAGMENT_COL = "_fragment"
ROW_COL = "_row"


@dataclass
class FragmentWrite:
    """What pinning a table wrote and what it references."""

    content_hash: str
    schema_digest: str
    fragments: list[str]
    new_fragments: list[tuple[str, int, int]]  # (hash, rows, bytes)
    rows: int
    bytes_total: int
    bytes_new: int


class LakeStore:
    """MAYA's adapter over ``maya_delta``. The only module that touches it."""

    def __init__(self, root: Path, backend: str = "auto", chunk: ChunkParams | None = None) -> None:
        from maya_delta import DeltaLake

        self.root = root / "lake"
        self.root.mkdir(parents=True, exist_ok=True)
        self.delta = DeltaLake(backend)
        self.chunk = chunk or ChunkParams()

    @property
    def backend_name(self) -> str:
        return self.delta.info.name

    def table_path(self, kind: str, namespace: str, name: str) -> Path:
        return self.root / kind / namespace / name

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    # -- maintenance: compaction and vacuum -----------------------------
    def tables(self) -> list[Path]:
        """Every Delta table under the lake root (ingest logs and fragment stores)."""
        return sorted(p.parent for p in self.root.rglob("_delta_log") if p.is_dir())

    def maintain(self, *, target_size: int, retention_hours: float) -> list[dict[str, Any]]:
        """Compact small files, then vacuum unreferenced files past retention, table by table.

        Safe for sealed pins: a pin is read by fragment value and row number, never by file,
        and the ingest log is read at its latest version.
        """
        out = []
        for path in self.tables():
            compacted = self.delta.optimize(path, target_size=target_size)
            vacuumed = self.delta.vacuum(
                path, retention_hours=retention_hours, enforce_retention=retention_hours >= 168
            )
            out.append(
                {
                    "table": self.rel(path),
                    "filesRemoved": compacted["numFilesRemoved"],
                    "filesAdded": compacted["numFilesAdded"],
                    "vacuumed": len(vacuumed),
                    "version": compacted["version"],
                }
            )
        return out

    # -- raw, bitemporal ingest ------------------------------------------
    def append_raw(self, namespace: str, name: str, table: pa.Table) -> int:
        return self.delta.write(self.table_path("raw", namespace, name), table, mode="append")

    def read_raw(self, namespace: str, name: str) -> pa.Table | None:
        path = self.table_path("raw", namespace, name)
        if not self.delta.exists(path):
            return None
        return self.delta.read(path)

    # -- content-addressed pins --------------------------------------------
    def plan_fragments(self, table: pa.Table) -> tuple[str, list[tuple[str, int, int]]]:
        """Schema digest and ``(hash, start, end)`` runs for an index-sorted table."""
        from maya.core import canonical_fast  # the same digests, a column at a time

        digests = canonical_fast.row_digests(table)
        if digests is None:  # a type it does not cover
            digests = canonical.row_digests(canonical.table_columns(table))
        runs = boundaries(digests, self.chunk)
        schema_hex = canonical.schema_digest((f.name, str(f.type)) for f in table.schema)
        return schema_hex, [(canonical.fragment_hash(digests[s:e]), s, e) for s, e in runs]

    def new_bytes(self, table: pa.Table, known: set[str]) -> int:
        """What writing ``table`` would add, in bytes, without writing it: the fragments
        ``known`` does not already hold. Used to check a quota before storing anything."""
        _, runs = self.plan_fragments(table)
        seen: set[str] = set()
        total = 0
        for digest, start, end in runs:
            if digest in known or digest in seen:
                continue
            seen.add(digest)
            total += table.slice(start, end - start).nbytes
        return total

    def write_pin(
        self, kind: str, namespace: str, name: str, table: pa.Table, known: set[str]
    ) -> FragmentWrite:
        """Write the fragments of ``table`` that ``known`` does not already hold."""
        schema_hex, runs = self.plan_fragments(table)
        path = self.table_path(kind, namespace, name)
        new: list[tuple[str, int, int]] = []
        batches = []
        seen_now: set[str] = set()
        total = 0
        for digest, start, end in runs:
            part = table.slice(start, end - start)
            size = part.nbytes
            total += size
            if digest in known or digest in seen_now:
                continue
            seen_now.add(digest)
            part = part.append_column(ROW_COL, pa.array(range(end - start), pa.int64()))
            part = part.append_column(FRAGMENT_COL, pa.array([digest] * (end - start)))
            batches.append(part)
            new.append((digest, end - start, size))
        if batches:
            self.delta.write(
                path, pa.concat_tables(batches), mode="append", partition_by=[FRAGMENT_COL]
            )
        hashes = [d for d, _, _ in runs]
        return FragmentWrite(
            canonical.content_hash(schema_hex, hashes),
            schema_hex,
            hashes,
            new,
            table.num_rows,
            total,
            sum(b for _, _, b in new),
        )

    def describe_pin(self, table: pa.Table) -> FragmentWrite:
        """What ``write_pin`` would record for ``table`` — content hash, schema digest and
        fragment manifest — with nothing written (a pin that is not materialized)."""
        schema_hex, runs = self.plan_fragments(table)
        hashes = [d for d, _, _ in runs]
        total = sum(table.slice(s, e - s).nbytes for _, s, e in runs)
        return FragmentWrite(
            canonical.content_hash(schema_hex, hashes),
            schema_hex,
            hashes,
            [],
            table.num_rows,
            total,
            0,
        )

    def read_pin(self, kind: str, namespace: str, name: str, fragments: list[str]) -> pa.Table:
        """Reassemble a pin from its manifest, in manifest order."""
        path = self.table_path(kind, namespace, name)
        if not fragments:
            raise ValueError("empty fragment manifest")
        data = self.delta.read(path, partitions={FRAGMENT_COL: sorted(set(fragments))})
        # one sort by (fragment, row), then each fragment is a contiguous slice
        data = data.take(
            pa.compute.sort_indices(
                data, sort_keys=[(FRAGMENT_COL, "ascending"), (ROW_COL, "ascending")]
            )
        )
        keys = data.column(FRAGMENT_COL).to_numpy(zero_copy_only=False)
        where: dict[str, tuple[int, int]] = {}
        if len(keys):
            import numpy as np

            edges = np.flatnonzero(keys[1:] != keys[:-1]) + 1
            starts = np.concatenate(([0], edges))
            ends = np.concatenate((edges, [len(keys)]))
            where = {str(keys[a]): (int(a), int(b)) for a, b in zip(starts, ends)}
        body = data.drop_columns([FRAGMENT_COL, ROW_COL])
        pieces = []
        for digest in fragments:
            if digest not in where:
                raise ValueError(f"fragment {digest[:12]} is missing from the lake")
            a, b = where[digest]
            pieces.append(body.slice(a, b - a))
        return pa.concat_tables(pieces)

    def verify_pin(
        self,
        kind: str,
        namespace: str,
        name: str,
        fragments: list[str],
        expected_hash: str,
        written: pa.Table | None = None,
    ) -> dict[str, Any]:
        """Re-read a pin and recompute its content hash (integrity verification).

        At sealing, ``written`` is the table whose hash was just computed: if what the
        lake returns equals it value for value, the hash is the same by construction and
        need not be recomputed. Anything short of equal is hashed and reported."""
        table = self.read_pin(kind, namespace, name, fragments)
        if written is not None and same_values(table, written):
            return {
                "ok": True,
                "expected": expected_hash,
                "actual": expected_hash,
                "rows": table.num_rows,
                "compared": "values",
            }
        schema_hex, runs = self.plan_fragments(table)
        actual = canonical.content_hash(schema_hex, [d for d, _, _ in runs])
        return {
            "ok": actual == expected_hash,
            "expected": expected_hash,
            "actual": actual,
            "rows": table.num_rows,
        }


def same_values(a: pa.Table, b: pa.Table) -> bool:
    """Equal names, types, nulls and values — with NaN equal to NaN, as the canonical
    encoding makes it — so equal tables have equal content hashes."""
    import numpy as np

    if (
        a.column_names != b.column_names
        or a.schema.types != b.schema.types
        or a.num_rows != b.num_rows
    ):
        return False
    for name in a.column_names:
        x, y = a.column(name).combine_chunks(), b.column(name).combine_chunks()
        if pa.types.is_floating(x.type):
            if not np.array_equal(np.asarray(x.is_valid()), np.asarray(y.is_valid())):
                return False
            xv = x.to_numpy(zero_copy_only=False)
            yv = y.to_numpy(zero_copy_only=False)
            valid = np.asarray(x.is_valid())
            if not np.array_equal(xv[valid], yv[valid], equal_nan=True):
                return False
        elif not x.equals(y):
            return False
    return True
