"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Retrieval policy: what MAYA does to values on the way out, by default.

Filling gaps, normalising and aligning onto an axis are decisions somebody has to
make, and leaving them to every caller has two failure modes. Either each
consumer decides differently and the same feature means different things in two
models, or the awkward ones are skipped and a column arrives full of nulls that
somebody downstream turns into zeros without saying so.

So the decision can be attached to the feature or the featureset as its
**default behaviour**, and a request may override it. The object carries what its
owner decided; the caller carries what this particular read needs; and the
resolved policy that was actually applied comes back with the data, so neither
has to be reconstructed afterwards.

**The precedence is the composition rule again**, and deliberately so: a
left-to-right fold in which the rightmost wins.

    parents (left to right)  →  the object's own defaults  →  the request

A child inherits its parents' policy and may override part of it; a request
overrides the object; and nothing overrides the request, because the caller is
the one that knows what this read is for. One rule, applied to slots, to
components, and now to policy.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.features.alignment import RULES as ALIGN_RULES
from core.features.common import FeatureError
from core.features.composition import merge
from core.features.normalisation import METHODS
from core.features.preparation import STRATEGIES

# The three things a policy may say, and nothing else: a policy that could say
# anything would be a scripting language wearing a dictionary's clothes.
SECTIONS = ("fill", "normalise", "align")


def check(policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate a policy at the moment it is written, not when it is used."""
    if not policy:
        return {}
    if unknown := sorted(set(policy) - set(SECTIONS)):
        raise FeatureError(
            f"a retrieval policy says {', '.join(SECTIONS)} and nothing else; "
            f"it does not say {', '.join(unknown)}")
    # Each section is keyed by COLUMN, and a caller who writes
    # `"normalise": "zscore"` — meaning "this column, this way" — hits
    # `.items()` on a string and gets a 500 from a function whose whole job is
    # to refuse a bad policy at the moment it is written. The shape is checked
    # before the values.
    for section in ("fill", "normalise"):
        value = policy.get(section)
        if value is not None and not isinstance(value, dict):
            raise FeatureError(
                f"'{section}' is written per column, so it is a mapping of "
                f"column to {'strategy' if section == 'fill' else 'method'} — "
                f"not {type(value).__name__}. Write "
                f"{{\"{section}\": {{\"your_column\": "
                f"\"{'median' if section == 'fill' else 'zscore'}\"}}}}")
    if (align := policy.get("align")) is not None and not isinstance(align, dict):
        raise FeatureError(
            "'align' is a mapping and takes a 'rule' — not "
            f"{type(align).__name__}. Write "
            '{"align": {"rule": "flat_forward"}}')

    fill = policy.get("fill") or {}
    for column, ask in fill.items():
        strategy = ask if isinstance(ask, str) else (ask or {}).get("strategy")
        if strategy not in STRATEGIES:
            raise FeatureError(
                f"fill of '{column}': '{strategy}' is not a strategy; expected "
                f"one of {', '.join(STRATEGIES)}")
    for column, method in (policy.get("normalise") or {}).items():
        if method not in METHODS:
            raise FeatureError(
                f"normalise of '{column}': '{method}' is not a method; expected "
                f"one of {', '.join(METHODS)}")
    align = policy.get("align") or {}
    if align and align.get("rule") not in ALIGN_RULES:
        raise FeatureError(
            f"align: '{align.get('rule')}' is not a fill rule; expected one of "
            f"{', '.join(ALIGN_RULES)}")
    return {k: v for k, v in policy.items() if v}


def combine(policies: Sequence[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """Fold policies left to right, rightmost winning — per column, not wholesale.

    Merging section by section matters. A parent that fills three columns and a
    child that normalises one should end up doing both; replacing the whole
    section would silently drop the parent's decision, and the child's author
    would never see it go.
    """
    out: Dict[str, Any] = {}
    for policy in policies:
        for section in SECTIONS:
            incoming = (policy or {}).get(section)
            if not incoming:
                continue
            if section == "align":
                out[section] = {**(out.get(section) or {}), **incoming}
            else:
                out[section] = merge(out.get(section) or {}, incoming)
    return out


def effective(row: Dict[str, Any], parents: Sequence[Dict[str, Any]] = (),
              request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The policy that will actually be applied, and where each part came from."""
    return combine([*(p.get("defaults") for p in parents),
                    row.get("defaults"), check(request)])


def explain(row: Dict[str, Any], parents: Sequence[Dict[str, Any]] = (),
            request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Which layer decided each column's treatment.

    The question about an inherited policy is never "what will it do" but "who
    decided that", and this answers the second.
    """
    layers: List[tuple] = [*((p.get("name", "?"), p.get("defaults") or {})
                             for p in parents),
                           (row.get("name", "this"), row.get("defaults") or {}),
                           ("the request", check(request))]
    source: Dict[str, Dict[str, str]] = {s: {} for s in SECTIONS}
    for who, policy in layers:
        for section in SECTIONS:
            for key in (policy.get(section) or {}):
                source[section][key] = who
    return {"policy": effective(row, parents, request),
            "decided_by": {s: v for s, v in source.items() if v},
            "precedence": "parents left to right, then the object, then the "
                          "request; the rightmost wins"}


def describe() -> Dict[str, Any]:
    return {
        "sections": list(SECTIONS),
        "precedence": "a left-to-right fold in which the rightmost wins: "
                      "parents, then the object's own defaults, then the request",
        "why": "leaving these decisions to every caller means either the same "
               "feature means different things in two models, or the awkward "
               "columns are skipped and somebody downstream turns the nulls "
               "into zeros without saying so",
        "merged": "section by section and column by column, so a parent that "
                  "fills three columns and a child that normalises one end up "
                  "doing both",
    }
