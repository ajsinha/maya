"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a runtime is, from the engine's side.

The warrant grammar names nineteen ways a kernel can become runnable. An engine
does not have to implement all of them — no engine will — but it does have to be
**honest about which it implements**, and it has to refuse the rest by name
rather than by failing somewhere inside an artifact loader.

So a runtime declares its key, says what it needs, and answers whether it is
available *before* anything is loaded. A runtime whose dependency is missing is
not an error at import time and not a crash at call time: it is a refusal that
names the package.

Every runtime verifies the artifact digest before invoking. That is the point at
which the whole chain — registry, warrant, signature — either does or does not
describe the bytes about to run, and skipping it would make every link before it
decorative.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from core.execution.errors import WarrantError
from core.log import get_logger

logger = get_logger(__name__)


@dataclass
class Invocation:
    """One call: the warrant that authorised it and the inputs it was given."""
    warrant: Dict[str, Any]
    inputs: Dict[str, Any]

    @property
    def entry(self) -> Dict[str, Any]:
        return (self.warrant.get("realisation") or {}).get("entry") or {}

    @property
    def artifact(self) -> Dict[str, Any]:
        return (self.warrant.get("realisation") or {}).get("artifact") or {}

    @property
    def version_id(self) -> str:
        return (self.warrant.get("subject") or {}).get("version_id", "")

    @property
    def output_names(self) -> list:
        schema = (self.warrant.get("io_contract") or {}).get("output_schema") or []
        return [f["name"] for f in schema]


@runtime_checkable
class Runtime(Protocol):
    """Something that can turn one realisation into an answer."""

    key: str

    def available(self) -> Optional[str]:
        """None if usable, otherwise the reason it is not."""
        ...

    def invoke(self, call: Invocation) -> Any:
        ...


def digest_of(path: Path) -> str:
    """The content hash of an artifact on disk, in the platform's usual form."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def verify_artifact(path: Path, expected: Optional[str]) -> None:
    """Refuse to run bytes that are not the bytes the warrant describes.

    A warrant that names a digest and an engine that does not check it is a
    chain of custody with its last link missing — and it is the only link that
    touches what actually executes.
    """
    if not expected:
        raise WarrantError(
            "artifact_unverifiable",
            f"{path.name} carries no digest in the warrant, so what is about to "
            "run cannot be checked against what was approved",
            "register the version with an artifact_digest")
    actual = digest_of(path)
    if actual != expected:
        logger.error("artifact digest mismatch for %s: expected %s, found %s",
                     path, expected, actual)
        raise WarrantError(
            "artifact_mismatch",
            f"{path.name} does not match the digest in the warrant "
            f"(expected {expected[:23]}…, found {actual[:23]}…)",
            "the artifact has changed since it was approved; do not run it and "
            "raise a security incident")


def resolve_path(call: Invocation, root: Optional[Path]) -> Path:
    """Where the artifact actually is, refusing anything outside the root.

    A warrant is a document from elsewhere. Treating a path inside it as
    trustworthy is how a governance system becomes a file-read primitive.
    """
    uri = call.artifact.get("uri") or ""
    if not uri:
        raise WarrantError("no_artifact",
                           "the warrant names no artifact to load",
                           "register the version with an artifact uri, or use a "
                           "runtime that does not need one")
    name = uri.split("://", 1)[-1]
    if root is None:
        raise WarrantError("no_artifact_root",
                           "this engine has no artifact directory configured",
                           "set execution.captive.artifact_dir")
    path = (root / name).resolve()
    # is_relative_to, not a string prefix: '/srv/artifacts-backup/x' begins with
    # '/srv/artifacts' and is a different directory. A warrant is a document from
    # elsewhere, and a path inside it is the least trustworthy thing in it.
    if not path.is_relative_to(Path(root).resolve()):
        raise WarrantError("artifact_outside_root",
                           f"'{uri}' resolves outside the artifact directory",
                           "artifacts are read from the configured directory only")
    if not path.is_file():
        raise WarrantError("artifact_missing", f"no artifact at {uri}",
                           "publish the artifact where the engine can read it")
    return path
