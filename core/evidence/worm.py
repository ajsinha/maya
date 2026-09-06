"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Write-once storage: the filesystem implementation, and the seam above it.

`core/ports.py` declares `WORMReader` and `WORMWriter`. This is the
implementation that ships — a directory, by default `./data/worm` — and it
exists to be replaced.

## Why the seam is here rather than in the anchor

The anchor's argument is that a chain head written to a *second medium* catches
a rewrite that self-verification cannot. That argument is only as good as the
medium, and the medium is a deployment decision: S3 with Object Lock, an
append-only volume, a WORM appliance, or — here — a directory.

If the anchor opened files itself, moving to any of those would mean editing the
anchor, and the thing being edited would be the control. With the seam, the
anchor is written once against two small protocols and never changes again.

## What the filesystem implementation does and does not give you

**Does:** separation of medium. Rewriting the control-plane database no longer
suffices, because the heads live somewhere the database cannot reach. `put`
refuses to replace an object it already holds, and every object is made
read-only after writing.

**Does not:** enforcement. A process running as this user can delete or replace
an anchor, and the read-only bit stops an accident rather than an adversary.
That is not a defect of this class — it is the honest limit of a directory, and
it is why the interface exists. `FilesystemWORM` is the development and
small-deployment answer; a bank that needs the guarantee points the same
interface at storage that enforces it.

Neither the anchor nor anything above it can tell the difference, which is
exactly the property wanted: the security of the arrangement is a procurement
decision, stated in configuration, not a code path somebody has to audit.
"""
from __future__ import annotations

import pathlib
import stat
from typing import List

from core.log import get_logger

logger = get_logger(__name__)

#: Under `data/`, which is entirely untracked — the anchors are runtime evidence
#: about one instance's chain and mean nothing in a repository.
DEFAULT_ROOT = "./data/worm"

#: Written under a temporary name and moved into place, so a crash mid-write
#: cannot leave a short object that reads as a complete one.
_STAGING = ".writing"


class WormError(RuntimeError):
    """A write-once store refused, or could not answer."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> dict:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


class FilesystemWORM:
    """A directory used as write-once storage. Satisfies both WORM ports."""

    def __init__(self, root: str | pathlib.Path = DEFAULT_ROOT):
        self.root = pathlib.Path(root)

    # -------------------------------------------------------------- WORMWriter
    def put(self, name: str, content: bytes) -> None:
        """Write once. Refuses to replace an object already held.

        The refusal is the guarantee. Everything above — the anchor, tamper
        detection, the claim that a rewritten database is caught — rests on this
        method declining a second write, rather than on callers remembering not
        to ask for one.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(name)
        if path.exists():
            held = path.read_bytes()
            if held == content:
                return                       # idempotent: the same object, again
            raise WormError(
                "worm_overwrite_refused",
                f"'{name}' is already held with different content, and this "
                f"store is write-once",
                "do not overwrite it; an object that changed is the observation "
                "the store exists to make, and the held copy is the evidence")
        staging = path.with_suffix(_STAGING)
        staging.write_bytes(content)
        staging.replace(path)
        self._freeze(path)

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    # -------------------------------------------------------------- WORMReader
    def names(self) -> List[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_file() and not p.name.endswith(_STAGING))

    def get(self, name: str) -> bytes:
        path = self._path(name)
        try:
            return path.read_bytes()
        except OSError as exc:
            logger.error("write-once object %s is unreadable: %s", name, exc)
            raise WormError(
                "worm_unreadable",
                f"'{name}' is held but cannot be read: {exc}",
                "an object that cannot be read must not be treated as absent; "
                "treat this as tampering until it is explained") from exc

    # ------------------------------------------------------------------ detail
    def _path(self, name: str) -> pathlib.Path:
        # A name is a flat object key. Anything with a separator would let a
        # caller write outside the root, and this store's whole value is that
        # its contents are somewhere else and unwritable.
        if "/" in name or "\\" in name or name in ("", ".", ".."):
            raise WormError(
                "worm_bad_name",
                f"'{name}' is not a flat object name",
                "use a name without path separators")
        return self.root / name

    @staticmethod
    def _freeze(path: pathlib.Path) -> None:
        """Read-only after writing. Stops an accident, not an adversary — worth
        doing and worth not overstating."""
        try:
            path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError as exc:
            logger.warning("could not make %s read-only: %s — the object is "
                           "written and comparable, but this root does not "
                           "support the permission", path.name, exc)
