"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a baselined model does not have — computed, not declared.

The obvious design lets whoever imports a model declare its gaps. That design
produces a register in which every imported model has two gaps, because
declaring a third is work and nobody is checking.

So the gaps are **derived from the register itself**. MAYA looks at what a
governed model would have and reports what this one does not, which means an
importer cannot under-declare and does not have to know the list. The debt is
whatever is genuinely missing on the day, and it will shrink on its own as the
evidence arrives.

Each gap carries its materiality, because a model with no owner and a model with
no monitoring are different problems, and a register that treats them alike is
one nobody prioritises from.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence


@dataclass(frozen=True)
class Gap:
    """One thing a governed model has and this one does not."""
    key: str
    description: str
    materiality: str
    present: Callable[[Dict[str, Any]], bool]

    def missing_from(self, state: Dict[str, Any]) -> bool:
        return not self.present(state)


GAPS: Sequence[Gap] = (
    Gap("owner", "no accountable owner is recorded", "Critical",
        lambda s: bool((s["model"] or {}).get("owner"))),
    Gap("purpose", "no declared purpose, so no approved use to check against",
        "High", lambda s: bool((s["model"] or {}).get("purpose"))),
    Gap("version", "no version, so nothing is pinned and nothing is digested",
        "Critical", lambda s: bool(s.get("versions"))),
    Gap("artifact_digest",
        "no artifact digest, so what runs cannot be checked against what was approved",
        "High", lambda s: any(v.get("artifact_digest") for v in s.get("versions") or [])),
    Gap("tier", "no risk tier, so the depth of control is undecided", "Critical",
        lambda s: (s["model"] or {}).get("tier") is not None),
    Gap("contract", "no operating contract, so there are no stated assumptions",
        "High", lambda s: any(v.get("contract") for v in s.get("versions") or [])),
    Gap("feature_contract",
        "no feature contract, so serving is not pinned to exact feature versions",
        "Medium", lambda s: bool(s.get("feature_contract"))),
    Gap("validation", "no validation episode recorded", "High",
        lambda s: bool(s.get("validations"))),
    Gap("monitoring", "no monitors defined, so degradation would not be detected",
        "High", lambda s: bool((s.get("monitoring") or {}).get("monitors"))),
    Gap("documentation", "no compiled documentation", "Medium",
        lambda s: bool(s.get("documents"))),
    Gap("attestation", "the record has never been attested", "High",
        lambda s: bool((s.get("lifecycle") or {}).get("attested_at"))),
)

BY_KEY: Dict[str, Gap] = {g.key: g for g in GAPS}


def find(state: Dict[str, Any]) -> List[Gap]:
    """Every gap this model genuinely has, in declaration order."""
    return [g for g in GAPS if g.missing_from(state)]


def describe() -> List[Dict[str, str]]:
    """The full list, so an importer can see what will be checked."""
    return [{"key": g.key, "description": g.description,
             "materiality": g.materiality} for g in GAPS]
