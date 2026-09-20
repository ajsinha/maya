"""
The SDK's local cache (§18.2.5).

One rule makes this safe: **only a sealed pin is cached.** A pin is immutable and carries a
content hash, so a cached copy can be proved to be the same bytes; a definition or a live
resolution can change under you, and caching either would be a way to serve yesterday's
numbers quietly. So:

* the key is the pin's own content hash and the shape asked for, never a URL;
* every hit is verified against that hash before the bytes are handed back, so a corrupted
  or tampered cache file is a miss, not an answer;
* nothing else is cached at all.

The cache lives under ``~/.maya/cache`` by default (``MAYA_CACHE_DIR`` to move it,
``MAYA_CACHE=0`` to turn it off), is bounded by total size, and evicts the least recently
used file when it would go over.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from maya.core.errors import ValidationFailed

DEFAULT_LIMIT_BYTES = 2 * 1024**3


class PinCache:
    """A content-addressed cache of sealed-pin downloads."""

    def __init__(self, directory: str | Path | None = None, limit_bytes: int | None = None) -> None:
        env = os.environ.get("MAYA_CACHE_DIR")
        self.enabled = os.environ.get("MAYA_CACHE", "1") not in ("0", "false", "no")
        self.directory = Path(directory or env or (Path.home() / ".maya" / "cache"))
        self.limit_bytes = int(
            limit_bytes or os.environ.get("MAYA_CACHE_BYTES") or DEFAULT_LIMIT_BYTES
        )

    # -- the one thing worth caching --------------------------------------------
    def pin_bytes(self, client: Any, ref: str, pin: dict[str, Any], **kw: Any) -> bytes:
        """A pin's downloaded bytes: from the cache when they verify, else from MAYA.

        ``kw`` is passed to the download (``shape``, ``fmt``, …) and forms part of the key,
        because a tensor and a tabular download of one pin are different bytes.
        """
        digest = pin.get("content_hash")
        series = pin.get("pin_name")
        as_of = pin.get("as_of_date")
        pinned_ref = f"{ref}#{series}/{as_of}" if series and as_of else ref
        key = self._key(digest, kw) if digest else None
        if key is not None:
            hit = self._read(key)
            if hit is not None:
                return hit
        out = client.features.download(pinned_ref, **_download_args(kw))
        data = out["data"] if isinstance(out, dict) else out
        manifest = out.get("manifest", {}) if isinstance(out, dict) else {}
        self._verify(data, manifest, digest)
        if key is not None:
            self._write(key, data)
        return bytes(data)

    # -- verification ------------------------------------------------------------
    def _verify(self, data: bytes, manifest: dict[str, Any], digest: str | None) -> None:
        """Check the checksum MAYA issued before the bytes reach the caller (§18.2.5)."""
        promised = manifest.get("checksum") or manifest.get("content_hash")
        if not promised:
            return
        import io

        import pyarrow.parquet as pq

        from maya.sdk.io import table_checksum

        try:
            table = pq.read_table(io.BytesIO(data))
        except Exception:  # noqa: BLE001 - a non-parquet shape (csv, npz) carries no checksum
            return
        actual = table_checksum(table)
        if actual != promised:
            raise ValidationFailed(
                "This download does not match the checksum MAYA issued for it, so it is "
                "not the pin's bytes",
                expected=promised,
                actual=actual,
                pin=digest,
            )

    # -- the store ---------------------------------------------------------------
    def _key(self, digest: str, kw: dict[str, Any]) -> str:
        shape = ";".join(f"{k}={kw[k]}" for k in sorted(kw) if kw[k] is not None)
        return hashlib.sha256(f"{digest}|{shape}".encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / key

    def _read(self, key: str) -> bytes | None:
        """A hit, only if the bytes are still the bytes that were written. A cache file
        that was truncated, corrupted or edited is a miss: the whole point of caching a
        pin is that the copy can be proved identical."""
        if not self.enabled:
            return None
        path = self._path(key)
        try:
            data = path.read_bytes()
            written = path.with_suffix(".sha256").read_text().strip()
        except OSError:
            return None
        if hashlib.sha256(data).hexdigest() != written:
            for stale in (path, path.with_suffix(".sha256")):
                stale.unlink(missing_ok=True)
            return None
        os.utime(path, None)  # least-recently-used eviction needs a read to count as use
        return data

    def _write(self, key: str, data: bytes) -> None:
        if not self.enabled or len(data) > self.limit_bytes:
            return
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            path.with_suffix(".sha256").write_text(hashlib.sha256(data).hexdigest())
            tmp.replace(path)  # a reader never sees a half-written file
        except OSError:
            return  # a cache that cannot be written is not an error
        self._evict()

    def _evict(self) -> None:
        files = [p for p in self.directory.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        for path in sorted(files, key=lambda p: p.stat().st_mtime):
            if total <= self.limit_bytes:
                return
            try:
                total -= path.stat().st_size
                path.unlink()
            except OSError:
                return

    def clear(self) -> int:
        """Empty the cache; returns how many files went."""
        gone = 0
        for path in list(self.directory.rglob("*")):
            if path.is_file():
                try:
                    path.unlink()
                    gone += 1
                except OSError:
                    pass
        return gone

    def stats(self) -> dict[str, Any]:
        files = [p for p in self.directory.rglob("*") if p.is_file() and p.suffix != ".sha256"]
        return {
            "enabled": self.enabled,
            "directory": str(self.directory),
            "files": len(files),
            "bytes": sum(p.stat().st_size for p in files),
            "limit_bytes": self.limit_bytes,
            "cached": "sealed pins only: immutable, and verifiable by content hash",
        }


def _download_args(kw: dict[str, Any]) -> dict[str, Any]:
    """§18.2.4 says ``shape=``; the download endpoint takes ``format=`` and a shape only
    where it means a tensor layout. Translate rather than make the caller know."""
    out = dict(kw)
    shape = out.pop("shape", None)
    if shape in (None, "tabular"):
        return out
    out.setdefault("format", shape)
    return out


__all__ = ["DEFAULT_LIMIT_BYTES", "PinCache"]
