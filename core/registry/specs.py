"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Adapters from stored JSON specifications to domain objects.

The registry persists schemas and contracts as plain JSON, because that is what
survives a database round trip and a decade of format drift. The algebra needs
them as Schema and Contract values. This module is the only place that
translates, so there is exactly one definition of what a stored spec means.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.domain import Bound, Contract, Field, Schema


def schema_of(spec: List[Dict[str, Any]]) -> Schema:
    return Schema(tuple(Field(f["name"], f["dtype"], f.get("nullable", False),
                              f.get("minimum"), f.get("maximum"),
                              f.get("symbol"), f.get("unit"))
                        for f in spec or []))


def bounds_of(items) -> tuple:
    return tuple(Bound(b["key"], b.get("minimum"), b.get("maximum"),
                       tuple(b.get("allowed", ()))) for b in items or [])


def contract_of(spec: Dict[str, Any]) -> Contract:
    spec = spec or {}
    return Contract(bounds_of(spec.get("assumptions")), bounds_of(spec.get("guarantees")))
