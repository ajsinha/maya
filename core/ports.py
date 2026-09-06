"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Ports — the narrow interfaces one part of the core offers another.

The registry must refuse to promote a model that has an open blocking finding,
and warrant resolution must refuse to serve one. Neither should therefore have to
import the validation package: a governance gate that only works when the whole
system is assembled in one order is not a gate, it is a coincidence.

So they depend on this protocol instead, and the application wires an
implementation in. Anything that can answer "what is blocking this model" —
the findings register today, an external GRC system tomorrow — satisfies it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Protocol, Tuple, runtime_checkable


@runtime_checkable
class BlockingSource(Protocol):
    """Answers what currently blocks a model from moving or being served."""

    def blocking_for(self, model_id: str) -> List[Dict[str, Any]]:
        """Open findings that block. Empty means nothing stands in the way."""
        ...


@runtime_checkable
class LifecycleGate(Protocol):
    """Answers whether a model record currently accepts changes.

    The registry must be able to refuse a change to an attested record without
    knowing that amendments and attestations exist. It asks this instead, and
    gets back a verdict and a sentence explaining it.
    """

    def may_mutate(self, model_id: str) -> Tuple[bool, str]:
        """(allowed, reason). The reason is empty when allowed."""
        ...


@runtime_checkable
class WORMReader(Protocol):
    """Reads from write-once storage.

    Separated from the writer because the two are held by different parties in
    any deployment that means it. Verification needs only this half, so a
    verifying process can be given read credentials and nothing else — and a
    reader that cannot write is a reader that cannot be turned against the
    evidence it exists to check.
    """

    def names(self) -> List[str]:
        """Everything held, in a stable order. A listing is the history."""
        ...

    def get(self, name: str) -> bytes:
        """One object's bytes. Raises if it is absent or unreadable — an object
        that cannot be read must never be treated as absent, or deleting one
        becomes the way to pass."""
        ...


@runtime_checkable
class WORMWriter(Protocol):
    """Writes to write-once storage.

    `put` must **refuse to replace** an object that already exists. That refusal
    is the whole of the guarantee: everything above it — the evidence anchor,
    tamper detection, the argument that a rewritten database is caught — rests
    on the store declining a second write to a name it already holds, rather
    than on the caller remembering not to ask.

    A filesystem directory satisfies this by convention and not by enforcement;
    S3 with Object Lock, a WORM appliance or an append-only volume satisfies it
    properly. Both are the same interface, which is the point: which one a
    deployment uses is a configuration decision, and nothing above this line
    changes.
    """

    def put(self, name: str, content: bytes) -> None:
        """Write once. Raises if `name` is already held with other content."""
        ...

    def exists(self, name: str) -> bool:
        ...
