"""
The SDK's caches (§18.2.5).

One rule makes the data cache safe: **only a sealed pin is cached.** A pin is immutable and
carries a content hash, so a cached copy can be proved to be the same bytes; a definition or
a live resolution can change under you, and caching either would be a way to serve
yesterday's numbers quietly. So:

* the key is the pin's own content hash and the shape asked for, never a URL;
* every hit is verified against that hash before the bytes are handed back, so a corrupted
  or tampered cache file is a miss, not an answer;
* an interrupted download leaves a part file, and the next attempt asks for the rest of
  exactly those bytes rather than starting again — ending at the same verification, and
  throwing the part away rather than caching it if it fails;
* no pin data is cached that is not sealed.

``ReadCache`` is a different thing and is not an exception to that rule: it holds the last
body a read returned against the ``ETag`` MAYA issued for it, and re-serves that body only
when MAYA answers 304 — so nothing is ever served that the server has not just affirmed.
What it saves is the payload, not the round trip, and not the server's authority.

The pin cache lives under ``~/.maya/cache`` by default (``MAYA_CACHE_DIR`` to move it,
``MAYA_CACHE=0`` to turn it off), is bounded by total size, and evicts the least recently
used file when it would go over.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any

from maya.core.errors import ValidationFailed

DEFAULT_LIMIT_BYTES = 2 * 1024**3
READS_HELD = 256
READ_BODY_LIMIT = 4 * 1024**2


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
        args = _download_args(kw)
        streams = hasattr(getattr(client, "_transport", None), "download")
        if key is not None and self.enabled and streams:
            return self._resumed(client, pinned_ref, key, args, digest)
        # No content hash means the pin is not sealed yet, and an unsealed pin is still
        # moving: its bytes are neither cacheable nor worth resuming. Fetch it whole, verify
        # it, hand it back, keep nothing.
        out = client.features.download(pinned_ref, **args)
        data = out["data"] if isinstance(out, dict) else out
        manifest = out.get("manifest", {}) if isinstance(out, dict) else {}
        self._verify(data, manifest, digest)
        if key is not None:
            self._write(key, data)
        return bytes(data)

    def _resumed(
        self, client: Any, pinned_ref: str, key: str, args: dict[str, Any], digest: str | None
    ) -> bytes:
        """The download that survives a dropped connection: bytes land in a part file, a
        later attempt continues from it, and the whole of it faces the same checksum the
        one-shot path faces. A part that fails that check is not this pin — it is dropped,
        not cached, so the next attempt starts clean instead of resuming onto bad bytes."""
        part = self._path(key).with_suffix(".part")
        out = client.features.download(pinned_ref, to=part, **args)
        data = part.read_bytes()
        try:
            self._verify(data, out.get("manifest") or {}, digest)
        except ValidationFailed:
            _discard(part)
            raise
        self._promote(key, part, data)
        return data

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
        except Exception as exc:
            # MAYA's checksum is over values, so only a Parquet download can be checked
            # against it; a csv, arrow or npz shape carries no checksum over its own bytes.
            # Where it *can* be checked, bytes that will not read are a failure and not a
            # shape to be excused — that is what catches a resume stitched together wrongly.
            if (manifest.get("format") or "parquet") != "parquet":
                return
            raise ValidationFailed(
                "This download will not read as the Parquet MAYA said it sent, so it is "
                "not the pin's bytes",
                pin=digest,
                reason=str(exc)[:200],
            ) from exc
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

    def _promote(self, key: str, part: Path, data: bytes) -> None:
        """A verified part becomes the cache entry by being renamed, not copied."""
        if not self.enabled or len(data) > self.limit_bytes:
            _discard(part)
            return
        path = self._path(key)
        try:
            path.with_suffix(".sha256").write_text(hashlib.sha256(data).hexdigest())
            part.replace(path)  # a reader never sees a half-written file
            _validator(part).unlink(missing_ok=True)
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


class ReadCache:
    """The last body of each read, held against the ``ETag`` MAYA issued for it (§18.1).

    A read goes out carrying ``If-None-Match``; when the server answers 304 the held body is
    handed back, and when it answers 200 the new one replaces it. Nothing is ever served
    without asking, so this does not cache a definition in the sense §18.2.1 forbids — the
    server decides on every single read, and what the caller is spared is the payload.

    One of these belongs to one transport and therefore to one credential, because what a
    read returns depends on who asked. It also carries the validator a write sends back as
    ``If-Match``: a mutation guarded by a read the caller has not made sends nothing, which
    is honest — there is no version it could claim to have seen.
    """

    def __init__(self, held: int = READS_HELD, body_limit: int = READ_BODY_LIMIT) -> None:
        self.held = held
        # A body worth more memory than this is not held at all. The saving is a payload a
        # caller was about to receive anyway; paying for it in resident memory for the life
        # of a long-lived client is a worse deal the bigger the body gets.
        self.body_limit = body_limit
        self.enabled = os.environ.get("MAYA_CACHE", "1") not in ("0", "false", "no")
        self._entries: OrderedDict[str, tuple[str, Any]] = OrderedDict()

    def prepare(self, call: Any) -> tuple[str | None, dict[str, str]]:
        """The key this call's answer is remembered under, and the headers to send."""
        headers = dict(call.headers)
        key = self.key(call.method, call.path, call.params) if self._cacheable(call) else None
        if key is not None:
            tag = self._tag(key)
            if tag:
                headers["If-None-Match"] = tag
        if call.guard:
            tag = self._tag(self.key("GET", call.guard, {}))
            if tag:
                headers["If-Match"] = tag
        return key, headers

    def served(self, key: str) -> Any:
        """The held body, copied, so a caller that edits what it was given edits its own."""
        self._entries.move_to_end(key)
        return copy.deepcopy(self._entries[key][1])

    def remember(self, key: str | None, etag: str | None, value: Any, size: int = 0) -> None:
        if key is None or not etag or not self.enabled or size > self.body_limit:
            return
        self._entries[key] = (etag, copy.deepcopy(value))
        self._entries.move_to_end(key)
        while len(self._entries) > self.held:
            self._entries.popitem(last=False)

    def wrote(self, call: Any) -> None:
        """Forget the validator a successful guarded write just consumed.

        After the write lands, the caller holds a read of the state *before* it, and that
        validator no longer describes anything. Keeping it would make the next write send a
        precondition that is certain to fail — two edits in a row would be impossible without
        a read in between, which is a trap rather than a safeguard. Dropping it means the
        next write sends no ``If-Match`` unless the caller reads again, which is the honest
        position: there is no version it could claim to have seen."""
        if call.guard:
            self._entries.pop(self.key("GET", call.guard, {}), None)

    def clear(self) -> None:
        self._entries.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "reads": len(self._entries),
            "held": self.held,
            "body_limit": self.body_limit,
        }

    @staticmethod
    def key(method: str, path: str, params: dict[str, Any] | None) -> str:
        shape = json.dumps(
            {k: v for k, v in (params or {}).items() if v is not None}, sort_keys=True, default=str
        )
        return f"{method} {path} {shape}"

    def _tag(self, key: str) -> str | None:
        entry = self._entries.get(key) if self.enabled else None
        return entry[0] if entry else None

    @staticmethod
    def _cacheable(call: Any) -> bool:
        """Only a plain GET of a JSON body. A download's bytes are the pin cache's business,
        and a request that carries a body or a file is not a read."""
        return (
            call.method == "GET"
            and not call.raw
            and call.json_body is None
            and not call.files
            and not call.data
        )


def _validator(part: Path) -> Path:
    from maya.sdk.transport import validator_path

    return validator_path(part)


def _discard(part: Path) -> None:
    for path in (part, _validator(part)):
        path.unlink(missing_ok=True)


def _download_args(kw: dict[str, Any]) -> dict[str, Any]:
    """§18.2.4 says ``shape=``; the download endpoint takes ``format=`` and a shape only
    where it means a tensor layout. Translate rather than make the caller know."""
    out = dict(kw)
    shape = out.pop("shape", None)
    if shape in (None, "tabular"):
        return out
    out.setdefault("format", shape)
    return out


__all__ = ["DEFAULT_LIMIT_BYTES", "READS_HELD", "PinCache", "ReadCache"]
