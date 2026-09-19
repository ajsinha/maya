"""
Content-addressed blob store (§5.2, §7, §25 ``BlobStore``).

Uploads, code artifacts, compiled PDFs and export bundles are stored by the
sha256 of their bytes, never by the filename the user supplied, so the same
bytes uploaded twice are one blob and a hostile filename cannot traverse the
filesystem. Writes go to a temporary file and are moved into place with
``os.replace``, which is atomic on NTFS, ext4 and APFS alike.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from maya.core.errors import NotFound, ValidationFailed

CHUNK = 1 << 20


class LocalBlobStore:
    """Blobs on the local filesystem under ``<root>/blobs/ab/cd/<hash>``."""

    def __init__(self, root: Path, max_bytes: int = 2 << 30) -> None:
        self.root = root / "blobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def _path(self, digest: str) -> Path:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValidationFailed("Malformed blob hash", hash=digest)
        return self.root / digest[:2] / digest[2:4] / digest

    def put_stream(self, stream: BinaryIO) -> tuple[str, int]:
        """Stream into the store without buffering the whole payload (§13.2)."""
        h = hashlib.sha256()
        size = 0
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as out:
                while chunk := stream.read(CHUNK):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValidationFailed("Upload exceeds the size limit",
                                               limit=self.max_bytes)
                    h.update(chunk)
                    out.write(chunk)
            digest = h.hexdigest()
            dest = self._path(digest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                os.unlink(tmp)
            else:
                os.replace(tmp, dest)
            return digest, size
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def put(self, data: bytes) -> str:
        import io
        return self.put_stream(io.BytesIO(data))[0]

    def get(self, digest: str) -> bytes:
        path = self._path(digest)
        if not path.exists():
            raise NotFound(f"blob {digest[:12]}… is not in the store", hash=digest)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValidationFailed("Blob content does not match its hash: storage "
                                   "corruption", hash=digest)
        return data

    def exists(self, digest: str) -> bool:
        return self._path(digest).exists()

    def path(self, digest: str) -> Path:
        return self._path(digest)
