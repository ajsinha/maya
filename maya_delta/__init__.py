"""
maya_delta — the lakehouse layer (specification §7.4).

One API over two interchangeable backends:

* ``native`` — delta-rs through the ``deltalake`` wheel, chosen when it imports
  and passes a self-check (write and read a tiny table);
* ``pure``   — MAYA's own implementation of a declared subset of the Delta
  transaction-log protocol over pyarrow.

The backend is chosen once, the choice and the reason are reported through
``LakeBackendInfo``, and any caller may pin it (``"native"`` / ``"pure"``).
Selection is never silent. This package holds no MAYA domain knowledge.

Result contract, identical for both backends: ``read`` returns the table schema
in the order recorded in the log (partition columns keep their position), with
normalised types (lists named ``element``; timestamps in microseconds, UTC when
zoned), and rows in snapshot file order. Row order across files is not a Delta
guarantee; pass ``sort_by`` when order matters.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa

from maya_delta.errors import (
    ConcurrentModification,
    MayaDeltaError,
    TableNotFound,
    UnsupportedFeature,
)

__all__ = [
    "DeltaLake",
    "LakeBackendInfo",
    "select_backend",
    "MayaDeltaError",
    "UnsupportedFeature",
    "ConcurrentModification",
    "TableNotFound",
]


@dataclass(frozen=True)
class LakeBackendInfo:
    """Which backend is in use, what it is, and why it was chosen."""

    name: str  # "native" | "pure"
    detail: str  # e.g. "deltalake 1.6.3"
    reason: str  # why this backend and not the other


class _Backend(Protocol):
    name: str

    def exists(self, path: Path) -> bool: ...
    def version(self, path: Path) -> int: ...
    def read(
        self,
        path: Path,
        *,
        partitions: dict[str, list[str]] | None = ...,
        columns: list[str] | None = ...,
        version: int | None = ...,
    ) -> pa.Table: ...
    def write(
        self, path: Path, table: pa.Table, *, mode: str = ..., partition_by: list[str] | None = ...
    ) -> int: ...
    def files(
        self, path: Path, partitions: dict[str, list[str]] | None = ...
    ) -> list[dict[str, Any]]: ...
    def delete_partitions(self, path: Path, partitions: dict[str, list[str]]) -> dict[str, Any]: ...
    def history(self, path: Path) -> list[dict[str, Any]]: ...
    def protocol(self, path: Path) -> dict[str, Any]: ...
    def optimize(self, path: Path, *, target_size: int) -> dict[str, Any]: ...
    def vacuum(
        self, path: Path, *, retention_hours: float, dry_run: bool, enforce_retention: bool
    ) -> list[str]: ...


def _native_problem() -> str | None:
    """None if the native backend is usable here, else why not.

    On Windows the answer is always a reason, and it is not a defect in the library. The
    native writer names its data files in the Delta convention --
    ``part-00000-<uuid>-c000.snappy.parquet``, 67 characters -- and MAYA's pin tables sit
    under a partition directory naming a 64-character content hash. Add a project path and
    a namespace and the total passes the 260 characters Windows enforces unless long paths
    have been turned on, at which point a write fails with an error about the file name
    rather than about the length. The pure backend names the same file in 22 characters, so
    `auto` chooses it there. `native` may still be pinned by configuration -- it works, and
    on a machine with long paths enabled it is the faster of the two."""
    if os.name == "nt":
        return (
            "on Windows the native writer's file names put MAYA's pin paths over the 260"
            " character limit; set lake.backend=native to pin it anyway (see the runbook)"
        )
    try:
        from maya_delta import native

        backend = native.NativeBackend()
    except Exception as exc:  # ImportError, or a broken wheel
        return f"deltalake does not import ({type(exc).__name__}: {exc})"
    try:
        with tempfile.TemporaryDirectory(prefix="maya_delta_") as tmp:
            native.self_check(Path(tmp))
    except Exception as exc:
        return f"deltalake {backend.library_version} failed the self-check ({exc})"
    return None


_SELECTION_CACHE: dict[str, LakeBackendInfo] = {}


def select_backend(preference: str = "auto") -> LakeBackendInfo:
    """Resolve the backend. ``auto`` prefers native; pinning native when unusable raises."""
    if preference not in ("auto", "native", "pure"):
        raise MayaDeltaError(f"Unknown lake backend '{preference}' (expected auto, native or pure)")
    if preference in _SELECTION_CACHE:
        return _SELECTION_CACHE[preference]
    if preference == "pure":
        info = LakeBackendInfo(
            "pure", "maya_delta pure-Python Delta protocol subset", "pinned by configuration"
        )
    else:
        problem = _native_problem()
        if problem is None:
            from maya_delta import native

            detail = f"deltalake {native.NativeBackend().library_version}"
            why = (
                "pinned by configuration"
                if preference == "native"
                else "deltalake imports and passed the self-check"
            )
            info = LakeBackendInfo("native", detail, why)
        elif preference == "native":
            raise MayaDeltaError(f"lake backend pinned to 'native' but {problem}")
        else:
            info = LakeBackendInfo(
                "pure", "maya_delta pure-Python Delta protocol subset", f"fallback: {problem}"
            )
    _SELECTION_CACHE[preference] = info
    return info


def _make(name: str) -> _Backend:
    if name == "native":
        from maya_delta.native import NativeBackend

        return NativeBackend()
    from maya_delta.pure.table import PureBackend

    return PureBackend()


class DeltaLake:
    """The facade. Construct once with a backend preference; use everywhere."""

    def __init__(self, backend: str = "auto") -> None:
        self.info = select_backend(backend)
        self._b: _Backend = _make(self.info.name)

    @property
    def backend_name(self) -> str:
        return self.info.name

    def write(
        self,
        path: str | Path,
        table: pa.Table,
        *,
        mode: str = "append",
        partition_by: list[str] | None = None,
    ) -> int:
        """Write ``table``; returns the new table version."""
        return self._b.write(Path(path), table, mode=mode, partition_by=partition_by)

    def read(
        self,
        path: str | Path,
        *,
        partitions: dict[str, list[str]] | None = None,
        columns: list[str] | None = None,
        version: int | None = None,
        sort_by: list[str] | None = None,
    ) -> pa.Table:
        """Read the table (pruned to ``partitions``, projected to ``columns``, at ``version``)."""
        out = self._b.read(Path(path), partitions=partitions, columns=columns, version=version)
        if sort_by:
            out = out.sort_by([(c, "ascending") for c in sort_by])
        return out

    def delete_partitions(
        self, path: str | Path, partitions: dict[str, list[str]]
    ) -> dict[str, Any]:
        """Drop the files of the named partitions in one commit: ``{version, filesRemoved,
        bytesRemoved}``. A Delta remove, so time travel still answers until a vacuum past
        the retention window frees the bytes."""
        return self._b.delete_partitions(Path(path), partitions)

    def version(self, path: str | Path) -> int:
        return self._b.version(Path(path))

    def exists(self, path: str | Path) -> bool:
        return self._b.exists(Path(path))

    def history(self, path: str | Path) -> list[dict[str, Any]]:
        return self._b.history(Path(path))

    def files(
        self, path: str | Path, partitions: dict[str, list[str]] | None = None
    ) -> list[dict[str, Any]]:
        return self._b.files(Path(path), partitions)

    def partition_values(self, path: str | Path, column: str) -> set[str]:
        """Distinct values of a partition column in the current snapshot."""
        return {f["partitionValues"].get(column) for f in self._b.files(Path(path))}

    def protocol(self, path: str | Path) -> dict[str, Any]:
        return self._b.protocol(Path(path))

    # -- maintenance -------------------------------------------------------------------
    def optimize(self, path: str | Path, *, target_size: int = 128 * 1024 * 1024) -> dict[str, Any]:
        """Compact each partition's small files into files of about ``target_size`` bytes.

        One commit, ``dataChange: false``: the content is unchanged, only the layout.
        Returns ``{version, numFilesRemoved, numFilesAdded, partitionsOptimized, numRows}``.
        """
        return self._b.optimize(Path(path), target_size=target_size)

    def vacuum(
        self,
        path: str | Path,
        *,
        retention_hours: float = 168,
        dry_run: bool = False,
        enforce_retention: bool = True,
    ) -> list[str]:
        """Delete data files no longer referenced and older than the retention window.

        Returns the files deleted (or, with ``dry_run``, that would be). Retention under
        168 hours is refused unless ``enforce_retention=False``: time travel to versions
        whose files are vacuumed stops working.
        """
        return self._b.vacuum(
            Path(path),
            retention_hours=retention_hours,
            dry_run=dry_run,
            enforce_retention=enforce_retention,
        )
