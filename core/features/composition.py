"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Composition: a combination of features is a feature.

Two things people want are the same thing. *Inheriting* from one parent and
adding a component, and *combining* several parents into one, differ only in how
many parents there are — so there is one mechanism, and inheritance is the
one-parent case.

**The rule is a left-to-right fold, and the rightmost wins.**

    compose([a, b, c]) = merge(merge(a, b), c)

Later parents are more prominent than earlier ones, and an object's own
operations are applied last of all, because a thing's own declarations should
beat anything it inherited. Nothing else would be defensible: if a parent could
override a child, naming a parent would be an act of surrender.

That rule is not a convention. Merge-with-rightmost-wins over a keyed map is
**associative**, and the empty map is its **identity**, so composition is a
monoid — which is exactly why *a combination of features is a feature* and *a
combination of featuresets is a featureset* are true statements rather than
aspirational ones. Grouping does not matter, and the empty composition is the
thing itself.

**Every operation is total.** Dropping a component that is not there, overriding
one that is not there, adding one that already exists: each is refused. It would
be easy to make them no-ops and easier still to live with the consequence, which
is a child that quietly differs from what its author believed they had written.

**Parents are pinned.** A composition names a parent *and a version of it*. A
parent that could move underneath its children is finding C-2 wearing a third
hat: the child's digest would be stable while its contents were not.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.features.common import FeatureError

ADD, DROP, OVERRIDE = "add", "drop", "override"
OPERATIONS: Tuple[str, ...] = (ADD, DROP, OVERRIDE)

OPERATION_MEANING: Dict[str, str] = {
    ADD: "introduce a member the parents did not have; refused if one of them did",
    DROP: "remove a member the parents had; refused if none of them did",
    OVERRIDE: "replace a member the parents had; refused if none of them did",
}

# A chain longer than this is a modelling problem rather than a depth problem,
# and the message says so instead of exhausting the stack.
MAX_DEPTH = 12


def merge(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """The fold's step. Right wins, which is what makes the order meaningful."""
    return {**left, **right}


def fold(parents: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Left to right, later winning. Associative, with {} as its identity."""
    out: Dict[str, Any] = {}
    for parent in parents:
        out = merge(out, parent)
    return out


def apply(members: Dict[str, Any], operations: Sequence[Dict[str, Any]],
          what: str = "member") -> Dict[str, Any]:
    """Apply a thing's own operations. Last, and therefore most prominent."""
    out = dict(members)
    for index, operation in enumerate(operations or []):
        op = operation.get("op")
        name = operation.get("name")
        if op not in OPERATIONS:
            raise FeatureError(
                f"operation {index}: '{op}' is not one of "
                f"{', '.join(OPERATIONS)}")
        if not name:
            raise FeatureError(f"operation {index}: no {what} is named")
        if op == DROP:
            if name not in out:
                raise FeatureError(
                    f"operation {index}: cannot drop '{name}' — none of the "
                    f"parents has it. a drop that quietly does nothing leaves a "
                    f"child differing from what its author believed they wrote")
            del out[name]
            continue
        value = operation.get("value")
        if value is None:
            raise FeatureError(
                f"operation {index}: '{op}' of '{name}' carries no definition")
        if op == ADD and name in out:
            raise FeatureError(
                f"operation {index}: cannot add '{name}' — a parent already has "
                f"it. say 'override' if replacing it is what is meant; the two "
                f"read differently to a reviewer and should")
        if op == OVERRIDE and name not in out:
            raise FeatureError(
                f"operation {index}: cannot override '{name}' — no parent has "
                f"it. say 'add' if introducing it is what is meant")
        out[name] = value
    return out


def independent(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    """Whether two operations touch different members.

    The property that matters about the edit algebra: **independent edits
    commute.** If they do, two people editing a shared object produce the same
    result whichever order their edits are applied in, and a merge is a merge
    rather than a conflict whose resolution carries meaning. If they did not,
    there would be a defect that no test of a single edit could find — the same
    shape as the stateful-artefact argument, one level down.

    Asserted in `tests/test_laws.py`; exposed here so the property has a name
    rather than living only in a test.
    """
    return (left or {}).get("name") != (right or {}).get("name")


class Resolver:
    """Resolves a composition to its members, following parents by pin.

    Generic over what is being composed: a feature's components and a
    featureset's slots fold the same way, so they share the machinery and cannot
    drift apart in behaviour.
    """

    def __init__(self, load: Callable[[str, Optional[int]], Dict[str, Any]],
                 members_of: Callable[[Dict[str, Any]], Dict[str, Any]],
                 what: str = "member", noun: str = "object"):
        # load(name, version) -> the row; members_of(row) -> its OWN members
        self.load, self.members_of = load, members_of
        self.what, self.noun = what, noun

    # ----------------------------------------------------------------- resolve
    def resolve(self, row: Dict[str, Any],
                seen: Optional[List[str]] = None) -> Dict[str, Any]:
        """The members this object actually has, parents included."""
        chain = list(seen or [])
        name = row.get("name", "?")
        if name in chain:
            raise FeatureError(
                f"'{name}' composes itself through {' → '.join(chain + [name])}; "
                f"a cycle has no fixed point to resolve to")
        if len(chain) >= MAX_DEPTH:
            raise FeatureError(
                f"the composition is {len(chain)} deep at '{name}'; beyond "
                f"{MAX_DEPTH} this is a modelling problem rather than a depth "
                f"problem, and flattening it will read better than following it")
        chain.append(name)

        parents = []
        for parent in row.get("composes") or []:
            parent_row = self._parent(parent, name)
            parents.append(self.resolve(parent_row, chain))
        merged = fold(parents)
        merged = merge(merged, self.members_of(row))
        return apply(merged, row.get("operations") or [], self.what)

    def _parent(self, parent: Any, child: str) -> Dict[str, Any]:
        if isinstance(parent, str):
            parent = {"name": parent}
        name, version = parent.get("name"), parent.get("version")
        if not name:
            raise FeatureError(f"'{child}' composes something with no name")
        row = self.load(name, version)
        if row is None:
            raise FeatureError(
                f"'{child}' composes '{name}'"
                + (f" v{version}" if version is not None else "")
                + f", and there is no such {self.noun}")
        if row.get("ephemeral"):
            raise FeatureError(
                f"'{child}' composes '{name}', which is ephemeral. composing "
                f"something that will be destroyed leaves a child that resolves "
                f"today and does not tomorrow")
        return row

    # ------------------------------------------------------------------ trace
    def lineage(self, row: Dict[str, Any],
                depth: int = 0) -> List[Dict[str, Any]]:
        """The whole ancestry, in the order it folds. For a page and a reviewer."""
        out: List[Dict[str, Any]] = []
        for parent in row.get("composes") or []:
            spec = {"name": parent} if isinstance(parent, str) else parent
            parent_row = self._parent(spec, row.get("name", "?"))
            out.extend(self.lineage(parent_row, depth + 1))
            out.append({"name": parent_row.get("name"),
                        "version": spec.get("version"),
                        "depth": depth,
                        "sealed": bool(parent_row.get("sealed_at")),
                        "contributes": sorted(self.members_of(parent_row))})
        return out

    def explain(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Where every resolved member came from, and what it overrode.

        The question a reviewer asks about an inherited thing is never "what does
        it have" but "which of these did somebody here decide". This answers the
        second.
        """
        provenance: Dict[str, Dict[str, Any]] = {}
        for parent in row.get("composes") or []:
            spec = {"name": parent} if isinstance(parent, str) else parent
            parent_row = self._parent(spec, row.get("name", "?"))
            for member in self.resolve(parent_row, [row.get("name", "?")]):
                previous = provenance.get(member)
                provenance[member] = {
                    "from": parent_row.get("name"),
                    "version": spec.get("version"),
                    "overrode": previous["from"] if previous else None}
        own = self.members_of(row)
        for member in own:
            previous = provenance.get(member)
            provenance[member] = {"from": row.get("name"), "version": None,
                                  "overrode": previous["from"] if previous else None}
        for operation in row.get("operations") or []:
            name, op = operation.get("name"), operation.get("op")
            if op == DROP:
                provenance.pop(name, None)
            elif name:
                previous = provenance.get(name)
                provenance[name] = {
                    "from": f"{row.get('name')} ({op})", "version": None,
                    "overrode": previous["from"] if previous else None}
        return provenance


def describe() -> Dict[str, Any]:
    """The rule, published rather than left to be inferred from behaviour."""
    return {
        "rule": "a left-to-right fold in which the rightmost wins; an object's "
                "own declarations and operations are applied last, and are "
                "therefore the most prominent of all",
        "why": "merge-with-rightmost-wins is associative and has the empty map "
               "as its identity, so composition is a monoid — which is what "
               "makes 'a combination of features is a feature' a true statement "
               "rather than an aspiration",
        "operations": [{"op": op, "means": OPERATION_MEANING[op]}
                       for op in OPERATIONS],
        "totality": "every operation is refused when it would do nothing: a drop "
                    "of something absent, an override of something absent, an add "
                    "of something present",
        "pinning": "a composition names a parent and a version of it, because a "
                   "parent that could move underneath its children would leave "
                   "the child's digest stable while its contents were not",
        "max_depth": MAX_DEPTH,
    }
