"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Where a serialised model actually lives.

A version could always NAME an artifact — `artifact_uri` and `artifact_digest`
were columns, and the engine verified the digest before loading. What it could
not do was **hold** one. The bytes had to be placed on disk out of band, which
meant the one thing the whole chain of custody rests on arrived by a route the
platform had no view of, and `artifact_uri` was whatever string somebody typed.

So: a content-addressed store. **The digest is the address.** That is not a
storage convenience, it is what makes the guarantee cheap:

  * "the bytes match the warrant" is true by construction rather than by a
    check somebody remembered to write;
  * storing the same weights twice stores them once, which matters when a
    challenger differs from its champion by a configuration and not a file;
  * an artifact cannot be edited in place, because edited bytes are a different
    address and the old one still resolves to what was approved.

**Streamed, never buffered.** A model file does not fit in memory twice, and a
governance platform should not be the process that discovers this. Bytes are
hashed and written as they arrive, into a staging file that is moved into place
only once the whole thing has landed — so a reader never sees half an object
under a digest that promises the whole one.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterator, Optional

from core.artifacts.common import (CHUNK, EXECUTES_ON_LOAD, FORMAT_MEANING,
                                   FORMATS, MAX_BYTES, ArtifactError)
from core.log import get_logger

logger = get_logger(__name__)


class ArtifactStore:
    """Stores model bytes under their digest and reads them back verified."""

    def __init__(self, root: Path):
        self.root = Path(root)

    # ------------------------------------------------------------------ write
    def put(self, stream: BinaryIO, fmt: str,
            declared_digest: Optional[str] = None) -> Dict[str, Any]:
        """Store an artifact, returning what it is and where it now lives.

        `declared_digest` is optional and is *checked* rather than trusted: a
        caller who knows what they are uploading can say so, and a mismatch is
        refused rather than silently stored under the address of what actually
        arrived. That is the difference between "we have the file you meant"
        and "we have a file".
        """
        if fmt not in FORMATS:
            raise ArtifactError(
                "unknown_format",
                f"'{fmt}' is not a format this stores",
                f"use one of {', '.join(FORMATS)}; the format decides how the "
                f"artifact is loaded, and working it out at load time is how a "
                f"pickle gets deserialised in a control plane")

        self.root.mkdir(parents=True, exist_ok=True)
        staged = self.root / f"upload-{os.getpid()}-{time.time_ns()}.partial"
        digest = hashlib.sha256()
        size = 0
        try:
            with staged.open("wb") as out:
                while chunk := stream.read(CHUNK):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ArtifactError(
                            "artifact_too_large",
                            f"the artifact is over {MAX_BYTES / 1e9:.0f}GB",
                            "a governance platform is not a model store of last "
                            "resort; keep the checkpoint where it belongs and "
                            "register a reference to it")
                    digest.update(chunk)
                    out.write(chunk)
            if not size:
                raise ArtifactError("empty_artifact", "the upload is empty",
                                    "send the model file as the request body")
            resolved = "sha256:" + digest.hexdigest()
            if declared_digest and declared_digest != resolved:
                raise ArtifactError(
                    "artifact_digest_mismatch",
                    f"the bytes hash to {resolved[:23]}… and you said "
                    f"{declared_digest[:23]}…",
                    "the upload was truncated or is not the file you meant; "
                    "storing it under the address of what arrived would give you "
                    "an artifact nobody asked for")
            path = self._path(resolved)
            if path.exists():
                logger.info("artifact %s is already stored; storing it twice is "
                            "storing it once", resolved[:23])
                staged.unlink(missing_ok=True)
                self._remember(path, fmt)
                return self._describe(resolved, path.stat().st_size, fmt,
                                      stored=False)
            path.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(path)
            self._remember(path, fmt)
            logger.info("stored %s artifact %s (%.1f MB)", fmt, resolved[:23],
                        size / 1e6)
            return self._describe(resolved, size, fmt, stored=True)
        finally:
            staged.unlink(missing_ok=True)

    # ------------------------------------------------------------------- read
    def open(self, digest: str) -> BinaryIO:
        """The bytes, or a refusal naming what is missing."""
        return self.require(digest).open("rb")

    def stream(self, digest: str) -> Iterator[bytes]:
        with self.open(digest) as handle:
            while chunk := handle.read(CHUNK):
                yield chunk

    def require(self, digest: str) -> Path:
        path = self._path(digest)
        if not path.exists():
            raise ArtifactError(
                "artifact_not_stored", f"nothing is stored under {digest}",
                "upload it, or register the version against an artifact that is "
                "actually here")
        return path

    def exists(self, digest: str) -> bool:
        return self._path(digest).exists()

    def verify(self, digest: str) -> Dict[str, Any]:
        """Re-derive the digest from the bytes on disk.

        Content addressing makes tampering *hard* rather than impossible: the
        filesystem is still a filesystem. Re-hashing is how you find out, and it
        is a different question from "is the address right", which is why it is
        a separate call rather than something `open` does on every read of a
        multi-gigabyte file.
        """
        path = self.require(digest)
        actual = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK):
                actual.update(chunk)
        resolved = "sha256:" + actual.hexdigest()
        intact = resolved == digest
        if not intact:
            logger.error("artifact %s does not hash to its own address (%s)",
                         digest[:23], resolved[:23])
        return {"digest": digest, "intact": intact, "recomputed": resolved,
                "size": path.stat().st_size,
                "detail": ("the bytes hash to the address they are stored under"
                           if intact else
                           "the bytes on disk are NOT what this address promises; "
                           "do not run this artifact and raise a security incident")}

    def describe(self, digest: str) -> Dict[str, Any]:
        path = self.require(digest)
        return self._describe(digest, path.stat().st_size, self._format_of(path),
                              stored=False)

    @staticmethod
    def _remember(path: Path, fmt: str) -> None:
        """The format beside the bytes.

        The address is derived from the content, so the content cannot carry the
        format — two artifacts with identical bytes and different declared
        formats are the same artifact, and the first declaration is the one that
        stands. A sidecar keeps `describe` able to answer "how is this loaded"
        without a database round trip, which matters because the warrant builder
        asks on every build.
        """
        marker = path.with_suffix(".fmt")
        if marker.exists():
            return
        try:
            marker.write_text(fmt, encoding="utf-8")
        except OSError as exc:
            # Not fatal: the bytes are stored, and the format is also on the
            # version manifest. Losing it here costs a lookup, not an artifact.
            logger.warning("could not record the format of %s beside it: %s",
                           path.name[:16], exc)

    @staticmethod
    def _format_of(path: Path) -> Optional[str]:
        marker = path.with_suffix(".fmt")
        try:
            fmt = marker.read_text(encoding="utf-8").strip()
        except OSError as exc:
            # Ordinary for an artifact stored before the sidecar existed, so
            # this is a note rather than a fault; the caller falls back to the
            # format on the version manifest.
            logger.debug("no format recorded beside %s: %s", path.name[:16], exc)
            return None
        return fmt if fmt in FORMATS else None

    # ------------------------------------------------------------------ parts
    def _path(self, digest: str) -> Path:
        if not digest or not digest.startswith("sha256:") or len(digest) != 71:
            raise ArtifactError(
                "malformed_digest",
                f"'{digest}' is not a sha256 content address",
                "an address looks like sha256: followed by 64 hex characters")
        body = digest.split(":", 1)[1]
        if any(c not in "0123456789abcdef" for c in body):
            raise ArtifactError(
                "malformed_digest", f"'{digest}' is not hexadecimal",
                "an address looks like sha256: followed by 64 hex characters")
        # Two levels of fan-out, because a single directory holding a hundred
        # thousand files is slow on every filesystem that has ever existed.
        return self.root / body[:2] / body[2:4] / body

    @staticmethod
    def _describe(digest: str, size: int, fmt: Optional[str],
                  stored: bool) -> Dict[str, Any]:
        return {
            "digest": digest, "size": size, "format": fmt,
            "uri": f"maya://artifact/{digest}",
            "means": FORMAT_MEANING.get(fmt or "", ""),
            "executes_on_load": fmt in EXECUTES_ON_LOAD,
            "stored": stored,
            "detail": (f"{size / 1e6:.1f} MB"
                       + ("" if stored else ", already held under this address")
                       + (". this format executes code when it loads, so it runs "
                          "in the sandbox and nowhere else"
                          if fmt in EXECUTES_ON_LOAD else "")),
        }

    def usage(self) -> Dict[str, Any]:
        """What the store is holding. Somebody has to be able to ask."""
        count = total = 0
        for path in self.root.rglob("*"):
            # The sidecars are bookkeeping, not artifacts, and counting them
            # would tell somebody they hold twice what they hold.
            if path.is_file() and path.suffix not in (".partial", ".fmt"):
                count += 1
                total += path.stat().st_size
        return {"artifacts": count, "bytes": total,
                "detail": f"{count:,} artifact(s), {total / 1e9:.2f} GB"}
