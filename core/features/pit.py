"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Point-in-time assembly and its verification.

An assembly is CAUSALLY ADMISSIBLE when every value used is the latest fact that
was both true by the label time and known by the assembly time. Stated that way
it is mechanically checkable, so MAYA checks it rather than trusting whoever
wrote the query.

Verification is three layers, and they prove different things (finding H-6):

  1. Static analysis  — both temporal bounds must be present, or the assembly is
                        REJECTED. A proof for the dominant leakage class.
  2. Sampling         — independent recomputation over a stratified sample.
                        Detects systematic violations. Does not prove absence.
  3. Adversarial      — CI injects leakage the verifier must catch, so the
                        verifier cannot silently stop working.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.log import get_logger, swallowed
import itertools

logger = get_logger(__name__)


@dataclass(frozen=True)
class AssemblyRequest:
    """A label spine plus the bounds under which features may be read."""
    spine: List[Dict[str, Any]]          # entity_id, label_ts, label
    views: List[Dict[str, Any]]          # {view, delta_version, features}
    as_of: float                         # transaction-time cut
    valid_time_bound: bool = True
    transaction_time_bound: bool = True


@dataclass
class PitReport:
    passed: bool
    layer: str
    checked: int = 0
    violations: List[Dict[str, Any]] = field(default_factory=list)
    leakage: List[str] = field(default_factory=list)
    #: Whether the leakage screen ran at all, and under which column. A screen
    #: that could not find the label returns no suspects, which reads exactly
    #: like a screen that found none — so it says which it was.
    leakage_screened: bool = False
    label_column: Optional[str] = None
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"passed": self.passed, "layer": self.layer, "checked": self.checked,
                "violations": self.violations[:20], "leakage": self.leakage,
                "leakage_screened": int(self.leakage_screened),
                "label_column": self.label_column, "detail": self.detail}


class AssemblyRejected(RuntimeError):
    """Layer 1 refused the assembly. This is a proof, not a warning."""


def static_check(req: AssemblyRequest) -> PitReport:
    """Layer 1. Both bounds are required; either missing and we refuse."""
    missing = []
    if not req.valid_time_bound:
        missing.append("valid_time")
    if not req.transaction_time_bound:
        missing.append("transaction_time")
    if missing:
        return PitReport(False, "static", detail=
                         "assembly lacks a bound on " + " and ".join(missing) +
                         "; without both, leakage cannot be excluded")
    return PitReport(True, "static", detail="both temporal bounds present")


def verify_sampled(rows: List[Dict[str, Any]], recompute, sample: int = 200) -> PitReport:
    """Layer 2. Recompute a sample by a second route and compare.

    **What it strata on, exactly.** `_stratified` buckets on the **label value**
    and nothing else. This said strata span "label period, entity and label
    value" — a claim the deck repeated from here, and neither was true. On the
    featureset path there is no `label` column at all, so every row falls into
    one bucket and the sampling is uniform.

    **And what a second route is worth here.** `_recompute` is pinned by test to
    apply the same `min(label_ts, as_of)` bound as the assembler, which is
    right — the two must not diverge — but it means this catches implementation
    drift between two paths rather than a wrong rule. Both would be wrong
    together. Layer 1's static refusal is the check that proves something about
    the data; this one proves the two code paths still agree, which is worth
    having and is a smaller claim.

    The sample is 200 rows, fixed. There is no power computation anywhere.
    """
    if not rows:
        return PitReport(True, "sampled", 0, detail="nothing to verify")
    chosen = _stratified(rows, sample)
    violations = []
    for row in chosen:
        expected = recompute(row)
        for key, want in expected.items():
            got = row.get(key)
            if not _close(got, want):
                violations.append({"entity_id": row.get("entity_id"), "feature": key,
                                   "assembled": got, "expected": want})
    return PitReport(not violations, "sampled", len(chosen), violations,
                     detail=f"{len(chosen)} of {len(rows)} rows independently recomputed")


# Above this many distinct values per row, a column is continuous for our
# purposes and the purity screen below says nothing about it.
CONTINUOUS_RATIO = 0.5


def screen_leakage(rows: List[Dict[str, Any]], label_key: str = "label"
                   ) -> Tuple[List[str], Optional[str]]:
    """The suspects, and — if the screen could not run — why not.

    `detect_leakage` returns a list, and an empty list is the same object
    whether nothing was suspicious or nothing was examined. Three separate
    conditions produce that empty list without a single column being compared:
    fewer than eight rows, no label column in the frame, and a label with only
    one distinct value. A fourth is subtler — a CONTINUOUS label, where the
    only test available is a threshold split and `_separates_perfectly`
    declines anything that is not binary. A regression training set therefore
    came back clean having been screened for nothing at all.

    This is the same function with the reason kept. `detect_leakage` stays as
    the list-only form for callers that only want the suspects.
    """
    if len(rows) < 8:
        return [], (f"only {len(rows)} rows; below eight a relationship between "
                    f"a column and the label is not evidence of anything")
    if label_key not in rows[0]:
        return [], f"no '{label_key}' column in the assembled frame"
    labels = [r.get(label_key) for r in rows]
    distinct_labels = len(set(labels))
    if distinct_labels < 2:
        return [], f"every row carries the same '{label_key}', so nothing separates"
    if distinct_labels > 2 and distinct_labels / len(labels) > CONTINUOUS_RATIO:
        return [], (f"'{label_key}' is continuous, and the only screen available "
                    f"for a continuous column is a threshold split, which means "
                    f"nothing unless the label is binary")
    return detect_leakage(rows, label_key), None


def detect_leakage(rows: List[Dict[str, Any]], label_key: str = "label") -> List[str]:
    """A crude but useful screen: a feature that is a perfect predictor of the
    label is almost always the label leaking under another name.

    **Two screens, chosen by the column, and the reason is a defect this used to
    have.** The original test bucketed values by label and flagged a column when
    every bucket held exactly one label. For a *continuous* feature every value
    is distinct, so every bucket holds one row and therefore one label --
    trivially, by construction, regardless of any relationship to the label. An
    ordinary forty-row training set with one float feature and random labels came
    back flagged, so `pit_verified` was False for essentially every real
    training set, and a control that is always false is a control nobody reads.

    So: a repeating column is screened for **purity**, which is what the original
    test meant and which is informative only when values recur. A continuous one
    is screened for **perfect separation** -- a single threshold that splits the
    labels exactly -- which is what "predicts the label perfectly" means for a
    number. Neither screen is a proof; both are cheap and both fire on the shape
    a leak actually has.
    """
    if len(rows) < 8 or label_key not in rows[0]:
        return []
    labels = [r.get(label_key) for r in rows]
    if len(set(labels)) < 2:
        return []
    suspects = []
    for key in rows[0]:
        if key in (label_key, "entity_id", "label_ts"):
            continue
        values = [r.get(key) for r in rows]
        if any(v is None for v in values):
            continue
        distinct = len(set(values))
        if distinct < 2:
            continue
        if distinct / len(values) > CONTINUOUS_RATIO:
            if _separates_perfectly(values, labels):
                suspects.append(key)
            continue
        mapping: Dict[Any, set] = {}
        for v, lab in zip(values, labels):
            mapping.setdefault(v, set()).add(lab)
        if all(len(s) == 1 for s in mapping.values()):
            suspects.append(key)
    return suspects


def _separates_perfectly(values: List[Any], labels: List[Any]) -> bool:
    """Whether one threshold on this column splits the labels exactly.

    Only meaningful for numbers and only for a binary label; anything else is
    reported as unscreenable rather than as clean, by returning False and
    leaving it to the sampled recomputation and the derived-feature lineage
    check, which are the screens that actually prove something.
    """
    if len(set(labels)) != 2:
        return False
    try:
        pairs = sorted((float(v), lab) for v, lab in zip(values, labels))
    except (TypeError, ValueError) as exc:
        swallowed(logger, exc, "screened a high-cardinality column for leakage",
                  detail="it does not order as numbers, so a threshold test "
                         "means nothing; it is left to the sampled "
                         "recomputation and the lineage check",
                  level=logging.DEBUG)
        return False
    ordered = [lab for _, lab in pairs]
    # Exactly one change of label along the sorted column: everything below the
    # threshold is one class and everything above it is the other.
    changes = sum(1 for a, b in itertools.pairwise(ordered) if a != b)
    return changes == 1


def _stratified(rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    """Strata by label value: a leak confined to a rare class is exactly where
    uniform sampling fails and where the damage is greatest."""
    if len(rows) <= n:
        return list(rows)
    buckets: Dict[Any, List[Dict[str, Any]]] = {}
    for r in rows:
        buckets.setdefault(r.get("label"), []).append(r)
    per = max(1, n // max(len(buckets), 1))
    return [r for b in buckets.values() for r in b[::max(1, len(b) // per)][:per]][:n]


def _close(a: Any, b: Any, tol: float = 1e-9) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tol
    return a == b
