"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Serialised models: putting the bytes in, and getting them back.

The digest is computed **here**, before the upload, and sent with it. That is the
one thing this module does that a thin wrapper would not, and it is the point:
the platform then checks what arrived against what was meant, so a truncated
upload is refused rather than stored under the address of whatever turned up. An
SDK that let the server hash whatever it received would make the check
tautological.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Union

CHUNK = 4 * 1024 * 1024


def digest_of(path: Union[str, Path]) -> str:
    """The sha256 of a file, in the form MAYA addresses artifacts by.

    Read in chunks, because a model file does not fit in memory twice and the
    client should not be the process that discovers this.
    """
    sha = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(CHUNK):
            sha.update(chunk)
    return "sha256:" + sha.hexdigest()


class Artifacts:
    """The content-addressed store: a file's name is its own hash."""

    def __init__(self, maya):
        self._maya = maya

    def formats(self) -> Dict[str, Any]:
        """What may be stored, and which formats execute code when they load.

        Worth reading before choosing one. `torchscript` and `tar` carry code and
        load in the sandbox and nowhere else; `onnx`, `safetensors`, `pmml`,
        `pfa`, `json` and `gguf` do not. There is no `pickle`, on purpose.
        """
        return self._maya.call("GET", "/artifact-formats")

    def put(self, path: Union[str, Path], *, format: str) -> Dict[str, Any]:
        """Store a file. Returns its digest, size and uri.

        Storing the same bytes twice stores them once, so re-uploading after a
        failed run is free rather than wasteful — `stored: false` in the answer
        means it was already held under that address.
        """
        path = Path(path)
        return self._maya.call(
            "POST", "/artifacts", content=path.read_bytes(),
            params={"format": format, "digest": digest_of(path)})

    def get(self, digest: str, into: Union[str, Path]) -> Path:
        """Fetch the bytes to a file. Returns the path."""
        body = self._maya.call("GET", f"/artifacts/{digest}", raw=True)
        destination = Path(into)
        destination.write_bytes(body)
        return destination

    def verify(self, digest: str) -> Dict[str, Any]:
        """Re-derive the hash from the bytes on disk.

        Content addressing makes tampering hard rather than impossible — the
        filesystem is still a filesystem — and this is how you find out. A
        separate call because re-hashing a multi-gigabyte file is not something a
        read should do every time.
        """
        return self._maya.call("GET", f"/artifacts/{digest}/verify")

    def usage(self) -> Dict[str, Any]:
        """How many artifacts, and how many bytes. Somebody has to be able to ask."""
        return self._maya.call("GET", "/artifact-usage")
