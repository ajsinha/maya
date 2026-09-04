"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Content-addressed document storage.

A document is stored under the digest of its bytes. Three things follow, and
each is a property this platform already relies on elsewhere.

**The same file is stored once.** A board paper covering forty models is one
object with forty attachments pointing at it.

**A document cannot be edited in place.** Change a byte and the digest changes,
which makes it a different document — so replacing one is a supersession that
somebody declares rather than an edit nobody sees. That is the same reasoning
that makes model versions immutable.

**What was reviewed is what is served.** The digest an approver accepted is the
digest a reader later fetches, and the store verifies that on the way out rather
than trusting the path it was given.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Tuple

from core.attachments.common import MAX_BYTES, AttachmentError
from core.log import get_logger

logger = get_logger(__name__)


class DocumentStore:
    """Stores document bytes under their digest, and reads them back verified."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, data: bytes) -> Tuple[str, int]:
        """Store bytes, returning (digest, size). Storing twice is storing once."""
        if not data:
            raise AttachmentError("empty_document",
                                  "the document is empty", "attach a file with content")
        if len(data) > MAX_BYTES:
            raise AttachmentError(
                "document_too_large",
                f"the document is {len(data) / 1e6:.1f}MB; the limit is "
                f"{MAX_BYTES / 1e6:.0f}MB",
                "store large artifacts where they belong and attach a reference")
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        path = self._path(digest)
        if path.exists():
            logger.info("document %s is already stored; attaching to the same object",
                        digest[:20])
            return digest, len(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written beside and moved into place, so a reader never sees a
        # half-written object under a digest that promises the whole one.
        staged = path.with_suffix(".partial")
        staged.write_bytes(data)
        staged.replace(path)
        return digest, len(data)

    def get(self, digest: str) -> bytes:
        """Read bytes back, verifying they are still what the digest promises."""
        path = self._path(digest)
        if not path.is_file():
            raise AttachmentError("document_missing",
                                  f"no stored document for {digest[:20]}…",
                                  "the object is absent from the store")
        data = path.read_bytes()
        actual = "sha256:" + hashlib.sha256(data).hexdigest()
        if actual != digest:
            logger.error("stored document %s does not match its own digest", digest)
            raise AttachmentError(
                "document_corrupt",
                f"the stored bytes for {digest[:20]}… no longer hash to that digest",
                "the store has been tampered with or has corrupted; do not use "
                "this document and raise an incident")
        return data

    def exists(self, digest: str) -> bool:
        return self._path(digest).is_file()

    def _path(self, digest: str) -> Path:
        # Fanned out by the first two hex characters: a flat directory of a
        # hundred thousand documents is a directory nothing enumerates quickly.
        bare = digest.split(":", 1)[-1]
        if len(bare) != 64 or not all(c in "0123456789abcdef" for c in bare):
            raise AttachmentError("bad_digest", f"'{digest}' is not a sha256 digest", "")
        return self.root / bare[:2] / bare
