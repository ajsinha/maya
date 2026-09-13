"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the edit algebra a featureset composes under.

A feature's components and a featureset's slots fold the SAME way, sharing the
machinery so they cannot drift apart in behaviour. What that machinery has to
be is an algebra rather than a procedure: rightmost wins, the fold is
associative with the empty object as its identity, and the object's own
operations apply last.

The property that matters most is that **independent edits commute**. If they
do, two people editing a shared object produce the same result whichever order
their edits arrive in, and a merge is a merge rather than a conflict whose
resolution carries meaning. If they did not, there would be a defect no test
of a single edit could find.

And the three operations are distinguished on purpose. `add` of something a
parent already has, `override` of something no parent has, and `drop` of
something nobody has are each refused — a drop that quietly does nothing
leaves a child differing from what its author believed they wrote.
"""
from __future__ import annotations

from core.features.composition import (MAX_DEPTH, Resolver, apply, fold,
                                       independent, merge)
from core.features.common import FeatureError
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _resolver(rows: dict) -> Resolver:
    """A resolver over a dict of rows, so the algebra is exercised without a
    featureset registry standing in the way of what is being tested."""
    return Resolver(load=lambda name, version: rows.get(name),
                    members_of=lambda row: dict(row.get("members") or {}),
                    what="slot", noun="featureset")


@case("QA-FX-090", "Rightmost wins, per member")
def fx_090(ctx: Ctx) -> Result:
    """Per MEMBER, not per parent. A later parent overrides the members it
    defines and leaves the rest alone — a whole-object override would make
    composition a replacement and there would be nothing to compose."""
    left = {"a": 1, "b": 2}
    right = {"b": 20, "c": 3}
    got = fold([left, right])
    if got != {"a": 1, "b": 20, "c": 3}:
        return FAIL, f"the fold gave {got}"
    if fold([right, left]) != {"a": 1, "b": 2, "c": 3}:
        return FAIL, "reversing the parents does not reverse the winner"
    return PASS, "later parent wins on 'b' only, 'a' and 'c' both survive"


@case("QA-FX-092", "Associativity of the fold")
def fx_092(ctx: Ctx) -> Result:
    """`(A then B) then C` and `A then (B then C)` resolve identically, and
    the empty object is the identity. Without associativity the order a
    reader groups the parents in would change the answer, and lineage would
    be unreadable."""
    a, b, c = {"x": 1, "y": 1}, {"y": 2, "z": 2}, {"z": 3, "w": 3}
    left = fold([fold([a, b]), c])
    right = fold([a, fold([b, c])])
    if left != right:
        return FAIL, f"(A·B)·C = {left} and A·(B·C) = {right}"
    if fold([a, {}]) != a or fold([{}, a]) != a:
        return FAIL, "the empty object is not the identity"
    if fold([]) != {}:
        return FAIL, f"folding nothing gives {fold([])}"
    return PASS, f"associative, with {{}} as identity: {left}"


@case("QA-FX-4820", "Independent edits commute")
def fx_4820(ctx: Ctx) -> Result:
    """The property with a name. Two edits touching different members must
    produce the same object in either order, or two people editing a shared
    featureset get a result that depends on whose request arrived first —
    a defect no test of a single edit could find."""
    base = {"a": 1, "b": 2}
    one = {"op": "override", "name": "a", "value": 10}
    two = {"op": "override", "name": "b", "value": 20}
    if not independent(one, two):
        return FAIL, "two edits on different members are reported as dependent"
    if independent(one, {"op": "override", "name": "a", "value": 99}):
        return FAIL, "two edits on the SAME member are reported as independent"
    forwards = apply(base, [one, two])
    backwards = apply(base, [two, one])
    if forwards != backwards:
        return FAIL, (f"independent edits do not commute: {forwards} against "
                      f"{backwards}")
    clash = [{"op": "override", "name": "a", "value": 10},
             {"op": "override", "name": "a", "value": 99}]
    if apply(base, clash) == apply(base, list(reversed(clash))):
        return FAIL, ("two edits on one member commute, so the algebra cannot "
                      "tell a merge from a conflict")
    return PASS, f"independent edits commute to {forwards}; dependent ones do not"


@case("QA-FX-091", "The object's own operations are applied last")
def fx_091(ctx: Ctx) -> Result:
    """The child's own edit beats every parent, and it has to: an object
    whose parents could override its own declaration would be one whose
    author cannot say anything final."""
    rows = {
        "parent": {"name": "parent", "members": {"a": "from-parent"}},
        "child": {"name": "child", "composes": ["parent"],
                  "members": {},
                  "operations": [{"op": "override", "name": "a",
                                  "value": "from-child"}]},
    }
    got = _resolver(rows).resolve(rows["child"])
    if got.get("a") != "from-child":
        return FAIL, f"the parent won: {got}"
    return PASS, "the child's override is applied after the fold"


@case("QA-FX-093", "`drop` of a member no parent has")
def fx_093(ctx: Ctx) -> Result:
    """A drop that quietly does nothing leaves a child differing from what
    its author believed they wrote — and the difference only shows up when
    something downstream reads the member that was supposed to be gone."""
    try:
        apply({"a": 1}, [{"op": "drop", "name": "b"}])
    except FeatureError as exc:
        said = f"{exc}"
        if "drop" not in said or "b" not in said:
            return FAIL, f"the refusal does not name the operation: {said[:110]}"
        if "operation 0" not in said:
            return FAIL, "the refusal does not say which operation is wrong"
        return PASS, "refused, naming the operation and its index"
    return FAIL, "a drop of a member nobody has quietly did nothing"


@case("QA-FX-094", "`add` of a member a parent already has")
def fx_094(ctx: Ctx) -> Result:
    """`add` and `override` read differently to a reviewer and should. An
    `add` that silently replaced would let a child change a parent's
    definition while the diff says it introduced one."""
    try:
        apply({"a": 1}, [{"op": "add", "name": "a", "value": 2}])
    except FeatureError as exc:
        if "override" not in f"{exc}":
            return FAIL, "the refusal does not name the operation to use instead"
        return PASS, "refused, naming 'override' as the way to say it"
    return FAIL, "an add over an existing member replaced it silently"


@case("QA-FX-095", "`override` of a member no parent has")
def fx_095(ctx: Ctx) -> Result:
    """The mirror, and the direction that matters more: an override that
    introduced a member would let a typo in the name create a slot rather
    than fail."""
    try:
        apply({"a": 1}, [{"op": "override", "name": "b", "value": 2}])
    except FeatureError as exc:
        if "add" not in f"{exc}":
            return FAIL, "the refusal does not name the operation to use instead"
        return PASS, "refused, naming 'add' as the way to say it"
    return FAIL, ("an override of a member nobody has created it, so a typo "
                  "in the name makes a slot")


@case("QA-FX-096", "An operation naming no member")
def fx_096(ctx: Ctx) -> Result:
    """An operation with no name applies to nothing and would be dropped
    silently by anything that looked it up."""
    for operation in ({"op": "add", "value": 1},
                      {"op": "drop", "name": ""},
                      {"op": "override", "name": None, "value": 1}):
        try:
            apply({"a": 1}, [operation])
        except FeatureError:
            continue
        return FAIL, f"an operation naming nothing was applied: {operation}"
    try:
        apply({"a": 1}, [{"op": "sideways", "name": "a", "value": 1}])
    except FeatureError as exc:
        if "sideways" not in f"{exc}":
            return FAIL, "an unknown operation is not named in its refusal"
        return PASS, "unnamed members and unknown operations both refused"
    return FAIL, "an operation that is not one was applied"


@case("QA-FX-097", "An `add` carrying no definition")
def fx_097(ctx: Ctx) -> Result:
    """A member added with no definition is a slot with no meaning, and it
    would resolve to `None` for everything downstream that reads it."""
    for op in ("add", "override"):
        base = {"a": 1} if op == "override" else {}
        try:
            apply(base, [{"op": op, "name": "a"}])
        except FeatureError as exc:
            if "no definition" not in f"{exc}":
                return FAIL, f"'{op}' with no value refused: {f'{exc}'[:100]}"
            continue
        return FAIL, f"an '{op}' carrying no definition was applied"
    return PASS, "add and override both refuse a missing definition"


@case("QA-FX-098", "A composition cycle")
def fx_098(ctx: Ctx) -> Result:
    """A cycle has no fixed point to resolve to. Printing the chain is what
    makes it fixable — a bare *cycle detected* over a twelve-deep graph
    leaves somebody bisecting their own featuresets."""
    rows = {
        "a": {"name": "a", "composes": ["b"], "members": {}},
        "b": {"name": "b", "composes": ["c"], "members": {}},
        "c": {"name": "c", "composes": ["a"], "members": {}},
    }
    try:
        _resolver(rows).resolve(rows["a"])
    except FeatureError as exc:
        said = f"{exc}"
        if "→" not in said and "->" not in said:
            return FAIL, f"the refusal does not print the chain: {said[:110]}"
        for name in ("a", "b", "c"):
            if name not in said:
                return FAIL, f"the chain omits '{name}': {said[:110]}"
        return PASS, f"refused, printing the chain: {said[said.find('composes'):][:60]}"
    return FAIL, "a three-step cycle resolved"


@case("QA-FX-099", "A chain exactly twelve deep, then thirteen")
def fx_099(ctx: Ctx) -> Result:
    """Beyond twelve this is a modelling problem rather than a depth problem,
    and flattening it will read better than following it. The bound has to be
    where it is documented, or a firm at the edge cannot tell whether it has
    hit a limit or a bug."""
    def chain(depth: int) -> dict:
        rows = {}
        for i in range(depth):
            rows[f"f{i}"] = {"name": f"f{i}", "members": {f"m{i}": i},
                             "composes": [f"f{i + 1}"] if i + 1 < depth else []}
        return rows
    at = chain(MAX_DEPTH)
    try:
        got = _resolver(at).resolve(at["f0"])
    except FeatureError as exc:
        return FAIL, (f"a chain exactly {MAX_DEPTH} deep was refused: "
                      f"{f'{exc}'[:110]}")
    if len(got) != MAX_DEPTH:
        return FAIL, f"a {MAX_DEPTH}-deep chain resolved {len(got)} members"
    over = chain(MAX_DEPTH + 1)
    try:
        _resolver(over).resolve(over["f0"])
    except FeatureError as exc:
        if str(MAX_DEPTH) not in f"{exc}":
            return FAIL, "the refusal does not say what the bound is"
        return PASS, f"{MAX_DEPTH} resolved, {MAX_DEPTH + 1} refused by name"
    return FAIL, f"a chain {MAX_DEPTH + 1} deep resolved"


@case("QA-FX-100", "Composing something that does not exist")
def fx_100(ctx: Ctx) -> Result:
    """Refused at DEFINITION rather than at use. A featureset that resolves
    today and not tomorrow is worse than one that never resolved, because
    something will have been built on it in between."""
    rows = {"child": {"name": "child", "composes": ["nobody"], "members": {}}}
    try:
        _resolver(rows).resolve(rows["child"])
    except FeatureError as exc:
        if "nobody" not in f"{exc}":
            return FAIL, "the refusal does not name what is missing"
        if "featureset" not in f"{exc}":
            return FAIL, "the refusal does not say what kind of thing is missing"
        return PASS, "refused, naming the missing parent and its kind"
    return FAIL, "a featureset composing something that does not exist resolved"


@case("QA-FX-101", "Composing an ephemeral parent")
def fx_101(ctx: Ctx) -> Result:
    """Composing something that will be destroyed leaves a child that
    resolves today and does not tomorrow — the failure lands on whoever reads
    it next rather than on whoever wrote it."""
    rows = {
        "temp": {"name": "temp", "members": {"a": 1}, "ephemeral": True},
        "child": {"name": "child", "composes": ["temp"], "members": {}},
    }
    try:
        _resolver(rows).resolve(rows["child"])
    except FeatureError as exc:
        said = f"{exc}"
        if "ephemeral" not in said:
            return FAIL, f"refused for another reason: {said[:110]}"
        if "temp" not in said:
            return FAIL, "the refusal does not name the ephemeral parent"
        return PASS, "refused, naming the ephemeral parent"
    return FAIL, "a featureset composing an ephemeral parent resolved"


@case("QA-FX-4821", "merge is not mutation")
def fx_4821(ctx: Ctx) -> Result:
    """The fold runs over rows the register owns. A merge that mutated its
    left argument would edit a parent in place while resolving a child, and
    the parent would then resolve differently for the next reader."""
    left = {"a": 1}
    right = {"b": 2}
    merged = merge(left, right)
    if left != {"a": 1} or right != {"b": 2}:
        return FAIL, f"merge mutated its arguments: {left}, {right}"
    if merged != {"a": 1, "b": 2}:
        return FAIL, f"merge gave {merged}"
    base = {"a": 1}
    apply(base, [{"op": "override", "name": "a", "value": 2}])
    if base != {"a": 1}:
        return FAIL, f"apply mutated its input: {base}"
    parents = [{"a": 1}, {"b": 2}]
    fold(parents)
    if parents != [{"a": 1}, {"b": 2}]:
        return FAIL, f"fold mutated its parents: {parents}"
    return PASS, "merge, apply and fold all leave their inputs alone"
