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
