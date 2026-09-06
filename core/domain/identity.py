"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Probe-relative equivalence: the formal content of a PATCH release.

Equivalence is only ever as strong as the probe set is rich, so coverage is
reported alongside every claim and stored with it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# ----------------------------------------------------------- probe equivalence
@dataclass(frozen=True)
class Probe:
    name: str
    inputs: Dict[str, Any]


@dataclass(frozen=True)
class EquivalenceResult:
    equivalent: bool
    probe_count: int
    coverage: float
    divergences: Tuple[str, ...] = ()


def pi_equivalent(a: Dict[str, Any], b: Dict[str, Any], probes: List[Probe],
                  tolerance: float = 0.0, declared_inputs: int = 0) -> EquivalenceResult:
    """v1 == v2 relative to a probe set. The formal content of a PATCH release.

    Equivalence is only ever as strong as the probe set is rich, so coverage is
    reported alongside it and stored with the claim.
    """
    diverged = []
    for p in probes:
        x, y = a.get(p.name), b.get(p.name)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if abs(x - y) > tolerance:
                diverged.append(p.name)
        elif x != y:
            diverged.append(p.name)
    touched = {k for p in probes for k in p.inputs}
    coverage = len(touched) / declared_inputs if declared_inputs else 0.0
    return EquivalenceResult(equivalent=not diverged, probe_count=len(probes),
                             coverage=round(coverage, 4), divergences=tuple(diverged))
