"""
Composite models (§8.7, §9.5): a DAG of member model versions plus a
combination rule, governed as one model under one warrant.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
from typing import Any

from maya.core.errors import ValidationFailed

KINDS = ("ensemble", "pipeline", "router", "residual", "hierarchical")
TRAIN_MODES = ("sequential", "parallel", "joint")
BINDINGS = ("pinned", "tracking")
MAX_DEPTH = 4

# governance order; a composite is capped at its lowest member
MATURITY_ORDER = ("retired", "deprecated", "restricted", "experimental", "candidate", "approved")


def validate_composite(comp: Any) -> list[str]:
    """Structural errors in a composite node."""
    from maya.formula.ir import _node_errors  # shared node checker

    if not isinstance(comp, dict):
        return ["composite must be an object"]
    errors: list[str] = []
    if comp.get("kind") not in KINDS:
        errors.append(f"composite kind must be one of {KINDS}")
    members = comp.get("members") or []
    if not members:
        errors.append("a composite needs at least one member")
    aliases = [m.get("alias") for m in members if isinstance(m, dict)]
    if len(aliases) != len(set(aliases)):
        errors.append("member aliases must be unique")
    for m in members:
        if not isinstance(m, dict) or not m.get("alias") or not m.get("ref"):
            errors.append("each member needs an alias and a ref")
            continue
        if m.get("binding", "pinned") not in BINDINGS:
            errors.append(f"member '{m['alias']}': binding must be one of {BINDINGS}")
        if m.get("frozen") and not m.get("borrowed_parameter_set"):
            errors.append(f"member '{m['alias']}' is frozen but borrows no approved parameter set")
    if "combine" not in comp:
        errors.append("a composite needs a combine expression")
    else:
        errors.extend(_node_errors(comp["combine"], "composite.combine"))
    train = comp.get("train") or {}
    if train and train.get("mode", "sequential") not in TRAIN_MODES:
        errors.append(f"training mode must be one of {TRAIN_MODES}")
    order = train.get("order")
    if order and sorted(order) != sorted(aliases):
        errors.append("training order must name every member exactly once")
    return errors


def union_contract(
    member_irs: dict[str, dict[str, Any]], aliases: dict[str, dict[str, str]] | None = None
) -> list[dict[str, Any]]:
    """The union of member input contracts (§8.7).

    ``aliases`` maps ``{member_alias: {member_input: contract_name}}`` so two
    members wanting one attribute under different names share it. Two members
    wanting the same name with different types is a ContractMismatch.
    """
    from maya.formula.ir import input_contract

    aliases = aliases or {}
    merged: dict[str, dict[str, Any]] = {}
    for alias in sorted(member_irs):
        ir = member_irs[alias]
        items = union_contract(ir.get("_members", {})) if "composite" in ir else input_contract(ir)
        for item in items:
            name = aliases.get(alias, {}).get(item["name"], item["name"])
            if name in merged:
                prev = merged[name]
                if prev["type"] != item["type"]:
                    raise _mismatch(name, prev, item, alias)
                prev["needed_by"].append(alias)
            else:
                merged[name] = {
                    "name": name,
                    "type": item["type"],
                    "unit": item.get("unit"),
                    "role": "feature",
                    "needed_by": [alias],
                }
    return [merged[k] for k in sorted(merged)]


def _mismatch(name: str, prev: dict[str, Any], item: dict[str, Any], alias: str) -> Exception:
    from maya.core.errors import ContractMismatch

    return ContractMismatch(
        f"attribute '{name}' is wanted as {prev['type']} by {prev['needed_by']} "
        f"and as {item['type']} by '{alias}'",
        attribute=name,
    )


def capped_maturity(member_maturities: dict[str, str] | list[str]) -> str:
    """The highest maturity a composite may hold: its lowest member's."""
    values = (
        list(member_maturities.values())
        if isinstance(member_maturities, dict)
        else list(member_maturities)
    )
    if not values:
        return "experimental"
    for m in values:
        if m not in MATURITY_ORDER:
            raise ValidationFailed(f"unknown maturity '{m}'")
    return min(values, key=MATURITY_ORDER.index)


def blocking_members(member_maturities: dict[str, str], target: str) -> list[str]:
    """Members whose maturity is below ``target``, named for the reviewer."""
    rank = MATURITY_ORDER.index(target)
    return sorted(a for a, m in member_maturities.items() if MATURITY_ORDER.index(m) < rank)


def member_seeds(seed: int, aliases: list[str]) -> dict[str, int]:
    """Per-member seeds derived deterministically from one seed (§9.5)."""
    out = {}
    for alias in aliases:
        digest = hashlib.sha256(f"{seed}:{alias}".encode()).digest()
        out[alias] = int.from_bytes(digest[:4], "big")
    return out


def detect_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """A cycle in ``{node: [children]}``, as a path, or None."""
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for child in graph.get(node, []):
            if state.get(child) == 1:
                return stack[stack.index(child) :] + [child]
            if state.get(child) is None:
                found = visit(child)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in sorted(graph):
        if state.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


def nesting_depth(graph: dict[str, list[str]], root: str) -> int:
    """Composite nesting depth from ``root`` (a plain model is depth 0)."""
    children = graph.get(root, [])
    if not children:
        return 0
    return 1 + max(nesting_depth(graph, c) for c in children)


def check_structure(graph: dict[str, list[str]], root: str, max_depth: int = MAX_DEPTH) -> None:
    """Refuse cycles and over-deep nesting at definition time."""
    cycle = detect_cycle(graph)
    if cycle:
        raise ValidationFailed("composite members form a cycle: " + " -> ".join(cycle), cycle=cycle)
    depth = nesting_depth(graph, root)
    if depth > max_depth:
        raise ValidationFailed(
            f"composite nesting depth {depth} exceeds the cap of {max_depth}", depth=depth
        )


def is_partially_opaque(member_irs: dict[str, dict[str, Any]]) -> list[str]:
    """Members that are declared black boxes (opacity propagates)."""
    return sorted(a for a, ir in member_irs.items() if "black_box" in ir)
