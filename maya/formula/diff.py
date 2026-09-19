"""
Semantic diff of two formula IRs (§8.1, §10.3).

A reviewer is told *what changed in the mathematics* — an input added, a
bound tightened, the discount factor moved from continuous to simple
compounding — rather than shown a JSON diff.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Callable

from maya.formula.ir import canonical_json, iter_nodes, refs_of
from maya.formula.latex import latex_name, node_latex


def _same(a: Any, b: Any) -> bool:
    return canonical_json(a) == canonical_json(b)


def _product_refs(node: dict[str, Any]) -> frozenset[str] | None:
    """Refs of a pure product of refs (``r*T``), else None."""
    if "ref" in node:
        return frozenset([node["ref"]])
    if node.get("op") == "mul" and all("ref" in a for a in node["args"]):
        return frozenset(a["ref"] for a in node["args"])
    return None


def _continuous_discounts(node: Any) -> set[frozenset[str]]:
    """``exp(-x*y)`` or ``exp(neg(x)*y)`` factors, keyed by the product's refs."""
    found = set()
    for n in iter_nodes(node):
        if n.get("op") != "exp":
            continue
        arg = n["args"][0]
        if arg.get("op") == "neg":
            refs = _product_refs(arg["args"][0])
        elif arg.get("op") == "mul" and any(a.get("op") == "neg" for a in arg["args"]):
            flat = [a["args"][0] if a.get("op") == "neg" else a for a in arg["args"]]
            refs = _product_refs({"op": "mul", "args": flat})
        else:
            refs = None
        if refs:
            found.add(refs)
    return found


def _simple_discounts(node: Any) -> set[frozenset[str]]:
    """``.../(1 + x*y)`` factors, keyed by the product's refs."""
    found = set()
    for n in iter_nodes(node):
        if n.get("op") != "div":
            continue
        den = n["args"][1]
        if den.get("op") == "add" and len(den["args"]) == 2 and den["args"][0].get("const") == 1:
            refs = _product_refs(den["args"][1])
            if refs:
                found.add(refs)
    return found


def _whole(ir: dict[str, Any]) -> list[Any]:
    return [ir.get("body"), *(ir.get("lets") or {}).values()]


def _compounding(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    msgs = []
    o_cont = set().union(*(_continuous_discounts(n) for n in _whole(old)))
    n_simple = set().union(*(_simple_discounts(n) for n in _whole(new)))
    o_simple = set().union(*(_simple_discounts(n) for n in _whole(old)))
    n_cont = set().union(*(_continuous_discounts(n) for n in _whole(new)))
    for refs in sorted(o_cont & n_simple, key=sorted):
        msgs.append(
            "discount factor changed from continuous to simple compounding "
            f"(over {'·'.join(sorted(refs))})"
        )
    for refs in sorted(o_simple & n_cont, key=sorted):
        msgs.append(
            "discount factor changed from simple to continuous compounding "
            f"(over {'·'.join(sorted(refs))})"
        )
    return msgs


def _io_diff(old: dict[str, Any], new: dict[str, Any], key: str) -> list[str]:
    msgs: list[str] = []
    o = {i["name"]: i for i in old.get(key, [])}
    n = {i["name"]: i for i in new.get(key, [])}
    noun = key[:-1]
    for name in sorted(n.keys() - o.keys()):
        role = n[name].get("role")
        msgs.append(
            f"{role or noun} '{name}' added" if key == "inputs" else f"output '{name}' added"
        )
    for name in sorted(o.keys() - n.keys()):
        msgs.append(f"{o[name].get('role') or noun} '{name}' removed")
    for name in sorted(o.keys() & n.keys()):
        a, b = o[name], n[name]
        label = f"{b.get('role') or noun} '{name}'"
        for field in ("type", "unit", "role", "bounds"):
            if a.get(field) != b.get(field):
                msgs.append(f"{label} {field} changed from {a.get(field)} to {b.get(field)}")
    return msgs


def _tree_msgs(where: str, a: Any, b: Any) -> list[str]:
    if _same(a, b):
        return []
    added = refs_of(b) - refs_of(a)
    dropped = refs_of(a) - refs_of(b)
    msg = f"{where} changed: ${node_latex(a)}$ → ${node_latex(b)}$"
    extra = []
    if added:
        extra.append("now uses " + ", ".join(sorted(added)))
    if dropped:
        extra.append("no longer uses " + ", ".join(sorted(dropped)))
    return [msg + (f" ({'; '.join(extra)})" if extra else "")]


def _lets_diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    o, n = old.get("lets") or {}, new.get("lets") or {}
    msgs = [
        f"let '{k}' added: ${latex_name(k)} = {node_latex(n[k])}$"
        for k in sorted(n.keys() - o.keys())
    ]
    msgs += [f"let '{k}' removed" for k in sorted(o.keys() - n.keys())]
    for k in sorted(o.keys() & n.keys()):
        msgs += _tree_msgs(f"let '{k}'", o[k], n[k])
    return msgs


def _kind_diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    def kind(ir: dict[str, Any]) -> str:
        return (
            "black box"
            if "black_box" in ir
            else "composite"
            if "composite" in ir
            else "closed form"
        )

    ko, kn = kind(old), kind(new)
    return [f"model changed from {ko} to {kn}"] if ko != kn else []


def _composite_diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    if "composite" not in old or "composite" not in new:
        return []
    o, n = old["composite"], new["composite"]
    msgs = []
    if o.get("kind") != n.get("kind"):
        msgs.append(f"composite kind changed from {o.get('kind')} to {n.get('kind')}")
    om = {m["alias"]: m for m in o.get("members", [])}
    nm = {m["alias"]: m for m in n.get("members", [])}
    msgs += [f"member '{a}' added ({nm[a]['ref']})" for a in sorted(nm.keys() - om.keys())]
    msgs += [f"member '{a}' removed ({om[a]['ref']})" for a in sorted(om.keys() - nm.keys())]
    for a in sorted(om.keys() & nm.keys()):
        for field in ("ref", "binding", "frozen"):
            if om[a].get(field) != nm[a].get(field):
                msgs.append(
                    f"member '{a}' {field} changed from {om[a].get(field)} to {nm[a].get(field)}"
                )
    msgs += _tree_msgs("combine expression", o.get("combine"), n.get("combine"))
    if o.get("train") != n.get("train"):
        msgs.append(f"training plan changed from {o.get('train')} to {n.get('train')}")
    return msgs


_RULES: list[Callable[[dict[str, Any], dict[str, Any]], list[str]]] = [
    _kind_diff,
    _compounding,
]


def semantic_diff(old_ir: dict[str, Any], new_ir: dict[str, Any]) -> list[str]:
    """Human-readable statements of what changed, most meaningful first."""
    msgs: list[str] = []
    for rule in _RULES:
        msgs += rule(old_ir, new_ir)
    msgs += _io_diff(old_ir, new_ir, "inputs")
    msgs += _io_diff(old_ir, new_ir, "outputs")
    msgs += _lets_diff(old_ir, new_ir)
    if "body" in old_ir and "body" in new_ir:
        msgs += _tree_msgs("output equation", old_ir["body"], new_ir["body"])
    msgs += _composite_diff(old_ir, new_ir)
    if (
        "black_box" in old_ir
        and "black_box" in new_ir
        and not _same(old_ir["black_box"], new_ir["black_box"])
    ):
        for field in sorted(set(old_ir["black_box"]) | set(new_ir["black_box"])):
            if old_ir["black_box"].get(field) != new_ir["black_box"].get(field):
                msgs.append(f"black box {field} changed")
    return msgs
