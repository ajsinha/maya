"""
Content-defined fragment boundaries (§29.3). Type B seam.

A pin is a manifest of fragments. Boundaries are chosen by *content*, not by
row count: a row ends a fragment when its canonical digest, read as an
integer, is divisible by the target size. Inserting a row therefore changes
only the fragment it lands in; every other fragment keeps its bytes and its
hash, which is what makes the marginal cost of a month-end pin its delta
(SC-12) rather than its size.

The pure implementation below is authoritative. Any accelerator must produce
byte-identical boundaries or it is the accelerator that is wrong.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ChunkParams:
    """Fragment size bounds, in rows. Part of the hash contract: recorded per pin."""

    target: int = 512
    minimum: int = 32
    maximum: int = 8192

    def as_dict(self) -> dict[str, int]:
        return {"target": self.target, "minimum": self.minimum, "maximum": self.maximum}


def boundaries(row_digests: Sequence[bytes], params: ChunkParams) -> list[tuple[int, int]]:
    """Split rows into ``[start, end)`` runs using content-defined cut points."""
    cuts: list[tuple[int, int]] = []
    start = 0
    n = len(row_digests)
    for i, digest in enumerate(row_digests):
        length = i - start + 1
        if length < params.minimum and i != n - 1:
            continue
        is_cut = int.from_bytes(digest[:8], "big") % params.target == 0
        if is_cut or length >= params.maximum:
            cuts.append((start, i + 1))
            start = i + 1
    if start < n:
        cuts.append((start, n))
    return cuts
