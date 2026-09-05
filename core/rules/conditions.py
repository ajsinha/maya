"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The condition tree: parsed, type-checked, evaluated, and readable back out.

A condition is one of

    {"field": "ltv", "op": "gt", "value": 0.8}
    {"all": [<condition>, ...]}
    {"any": [<condition>, ...]}
    {"not": <condition>}

and nothing else. There is no arithmetic, no function call and no free text —
see `common.py` for why that restriction is the point rather than a limitation.

`describe()` renders a condition as an English sentence. That is not a
convenience: a rule set exists to be reviewed by whoever owns the policy it
implements, and if the reviewable form lives only in a screen then the export
pack, the committee paper and the model card each get a different rendering of
one rule, and the differences are where a misreading hides.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Set

from core.log import get_logger, swallowed
from core.rules.common import (ALL, ANY, COMBINATORS, LIST_VALUED, MAX_DEPTH,
                               NOT, NULLARY, NUMERIC_DTYPES, OPERATOR_MEANING,
                               OPERATORS, ORDERED_DTYPES, ORDERED_ONLY,
                               TEXTUAL_DTYPES, RuleError)

logger = get_logger(__name__)


class Condition:
    """One node of the tree. Immutable once built."""

    __slots__ = ("kind", "field", "op", "value", "children")

    def __init__(self, kind: str, field: Optional[str] = None,
                 op: Optional[str] = None, value: Any = None,
                 children: Sequence["Condition"] = ()):
        self.kind = kind                       # "atom" | "all" | "any" | "not"
        self.field, self.op, self.value = field, op, value
        self.children = tuple(children)

    # ------------------------------------------------------------------ build
    @classmethod
    def parse(cls, raw: Any, path: str = "when", depth: int = 0) -> "Condition":
        """Build a condition from the document, refusing anything malformed.

        Every refusal names `path`, so an author fixing a rule set with forty
        rules is told *which* one and *where* rather than that something in the
        document is wrong.
        """
        if depth > MAX_DEPTH:
            raise RuleError(
                "condition_too_deep",
                f"{path} nests more than {MAX_DEPTH} levels deep",
                "a condition nobody can hold in their head is not being "
                "reviewed; split it into separate rules, which are ordered and "
                "readable one at a time")
        if not isinstance(raw, dict):
            raise RuleError("condition_malformed",
                            f"{path} is {type(raw).__name__}, not a condition",
                            "a condition is an object: a field test, or all/any/not")

        combinators = [k for k in COMBINATORS if k in raw]
        if combinators and "field" in raw:
            raise RuleError(
                "condition_ambiguous",
                f"{path} is both a field test and a '{combinators[0]}' group",
                "a condition is one or the other; nest the field test inside "
                "the group if that is what was meant")
        if len(combinators) > 1:
            raise RuleError(
                "condition_ambiguous",
                f"{path} combines {' and '.join(combinators)} in one object, "
                f"and the order they would apply in is not stated anywhere",
                "use one combinator per object and nest the others inside it")

        if combinators:
            return cls._parse_group(raw, combinators[0], path, depth)
        return cls._parse_atom(raw, path)

    @classmethod
    def _parse_group(cls, raw: Dict[str, Any], kind: str, path: str,
                     depth: int) -> "Condition":
        body = raw[kind]
        if kind == NOT:
            return cls(NOT, children=[cls.parse(body, f"{path}.not", depth + 1)])
        if not isinstance(body, list) or not body:
            raise RuleError(
                "condition_malformed",
                f"{path}.{kind} is empty" if isinstance(body, list)
                else f"{path}.{kind} is not a list of conditions",
                "an empty 'all' is true of everything and an empty 'any' is "
                "true of nothing; neither is what anybody means to write")
        return cls(kind, children=[cls.parse(c, f"{path}.{kind}[{i}]", depth + 1)
                                   for i, c in enumerate(body)])

    @classmethod
    def _parse_atom(cls, raw: Dict[str, Any], path: str) -> "Condition":
        field, op = raw.get("field"), raw.get("op")
        if not isinstance(field, str) or not field:
            raise RuleError("condition_malformed",
                            f"{path} names no field",
                            "give the field the test reads")
        if op not in OPERATORS:
            raise RuleError(
                "unknown_operator",
                f"{path} uses operator '{op}'",
                f"use one of {', '.join(OPERATORS)}")

        has_value = "value" in raw
        if op in NULLARY and has_value:
            raise RuleError(
                "value_not_expected",
                f"{path} uses '{op}', which tests whether the field was "
                f"supplied at all, but also carries a value",
                "drop the value, or use an operator that compares one — "
                "a value the platform silently ignored would make the rule "
                "mean something other than it reads")
        if op not in NULLARY and not has_value:
            raise RuleError("value_required",
                            f"{path} uses '{op}' and carries no value",
                            f"'{op}' means '{OPERATOR_MEANING[op]}' and needs "
                            f"something to compare against")

        value = raw.get("value")
        if op in LIST_VALUED:
            if not isinstance(value, list) or not value:
                raise RuleError(
                    "value_malformed", f"{path} uses '{op}' and needs a non-empty list",
                    "give the members to test against")
            value = list(value)
        elif op == "between":
            if (not isinstance(value, (list, tuple)) or len(value) != 2):
                raise RuleError("value_malformed",
                                f"{path} uses 'between' and needs [low, high]",
                                "give exactly two bounds, low first")
            low, high = value
            if not _ordered_pair(low, high):
                raise RuleError(
                    "empty_range",
                    f"{path} is between {low} and {high}, which is an empty "
                    f"range, so the rule can never fire",
                    "put the bounds the other way round, or widen them")
            value = [low, high]
        return cls("atom", field=field, op=op, value=value)

    # ---------------------------------------------------------------- inspect
    def fields(self) -> Set[str]:
        """Every field this condition reads. Its read-set, for conformance."""
        if self.kind == "atom":
            return {self.field}                                  # type: ignore[arg-type]
        found: Set[str] = set()
        for child in self.children:
            found |= child.fields()
        return found

    def atoms(self) -> List["Condition"]:
        if self.kind == "atom":
            return [self]
        out: List[Condition] = []
        for child in self.children:
            out.extend(child.atoms())
        return out

    def as_dict(self) -> Dict[str, Any]:
        """Back to the document shape, canonically.

        Round-trips: `parse(c.as_dict()).as_dict() == c.as_dict()`. That is what
        lets the digest be taken over the *parsed* form, so two documents that
        differ only in key order are one rule set rather than two.
        """
        if self.kind == "atom":
            atom: Dict[str, Any] = {"field": self.field, "op": self.op}
            if self.op not in NULLARY:
                atom["value"] = self.value
            return atom
        if self.kind == NOT:
            return {NOT: self.children[0].as_dict()}
        return {self.kind: [c.as_dict() for c in self.children]}

    # ------------------------------------------------------------ type-check
    def conforms(self, schema: Dict[str, str], path: str = "when") -> None:
        """Refuse a condition reading a field the model does not declare, or
        comparing a categorical field with an order.

        The first is the same check `refines` makes for featureset satisfaction
        and typed composition (`L-20`, `L-21`) — a rule reading `dti` on a model
        whose input schema has no `dti` is a rule that will silently never fire,
        which is the worst of the three outcomes available.

        The second is subtler and just as real: `product_code > "MTG"` has a
        defined answer in every programming language and no meaning in any
        bank.
        """
        for atom in self.atoms():
            declared = schema.get(atom.field)                     # type: ignore[arg-type]
            if declared is None:
                raise RuleError(
                    "unknown_field",
                    f"{path} reads '{atom.field}', which this model's input "
                    f"schema does not declare",
                    f"declare it on the version, or read one of: "
                    f"{', '.join(sorted(schema)) or '(the schema is empty)'}")
            if atom.op in ORDERED_ONLY and declared not in ORDERED_DTYPES:
                raise RuleError(
                    "unordered_comparison",
                    f"{path} asks whether '{atom.field}' is "
                    f"{OPERATOR_MEANING[atom.op]} something, but it is declared "
                    f"'{declared}', which has no order",
                    "compare with eq/ne/in/not_in, or declare the field with an "
                    "ordered type if it really is one")
            _conform_value(atom, declared, path)

    # ------------------------------------------------------------- evaluate
    def holds(self, row: Dict[str, Any]) -> bool:
        """Does this condition hold of the row.

        Missing is not false. A field absent from the row is `is_null` true and
        every comparison false — so a rule reading a field nobody supplied does
        not fire, rather than firing on a coerced default. `otherwise` catches
        it, and `otherwise` is where somebody has written down what to do when
        the data is not there.
        """
        if self.kind == ALL:
            return all(c.holds(row) for c in self.children)
        if self.kind == ANY:
            return any(c.holds(row) for c in self.children)
        if self.kind == NOT:
            return not self.children[0].holds(row)
        return self._atom_holds(row)

    def _atom_holds(self, row: Dict[str, Any]) -> bool:
        present = self.field in row and row[self.field] is not None
        if self.op == "is_null":
            return not present
        if self.op == "not_null":
            return present
        if not present:
            return False
        value = row[self.field]
        if self.op == "eq":
            return value == self.value
        if self.op == "ne":
            return value != self.value
        if self.op == "in":
            return value in self.value
        if self.op == "not_in":
            return value not in self.value
        return self._compare(value)

    def _compare(self, value: Any) -> bool:
        """The ordered operators, refusing rather than coercing.

        A string arriving where a number was declared is a data defect, and
        Python would happily answer `"7" > 5` with a TypeError or, worse,
        compare two strings lexically and return something plausible. Both are
        refusals; neither is a rule outcome.
        """
        try:
            if self.op == "between":
                low, high = self.value
                return low <= value <= high
            if self.op == "lt":
                return value < self.value
            if self.op == "le":
                return value <= self.value
            if self.op == "gt":
                return value > self.value
            return value >= self.value
        except TypeError as exc:
            logger.warning("rule comparison refused: %s %s %r against %r — %s",
                           self.field, self.op, value, self.value, exc)
            raise RuleError(
                "value_not_comparable",
                f"'{self.field}' arrived as {type(value).__name__} "
                f"({value!r}) and the rule compares it with {self.value!r}",
                "fix the input, or the field's declared type; a rule set that "
                "guessed here would return an outcome nobody authored") from exc

    # -------------------------------------------------------------- describe
    def describe(self) -> str:
        """The condition in English, for a reviewer who will never read JSON."""
        if self.kind == ALL:
            return " and ".join(_bracket(c) for c in self.children)
        if self.kind == ANY:
            return " or ".join(_bracket(c) for c in self.children)
        if self.kind == NOT:
            return f"not ({self.children[0].describe()})"
        if self.op in NULLARY:
            verb = "is not supplied" if self.op == "is_null" else "is supplied"
            return f"{self.field} {verb}"
        if self.op == "between":
            return f"{self.field} is between {self.value[0]} and {self.value[1]}"
        if self.op in LIST_VALUED:
            members = ", ".join(str(v) for v in self.value)
            return f"{self.field} is {OPERATOR_MEANING[self.op]} [{members}]"
        return f"{self.field} is {OPERATOR_MEANING[self.op]} {self.value}"


def _conform_value(atom: "Condition", declared: str, path: str) -> None:
    """Refuse a rule comparing a field against a value of the wrong kind.

    This check was missing, and its absence produced **exactly the failure the
    conformance check exists to prevent**. `{"field": "ltv", "op": "eq",
    "value": "high"}` on a numeric `ltv` passed every check clean — the field is
    declared, the operator needs no order, the condition is satisfiable in the
    abstract, nothing shadows it — and it can never fire, because no numeric
    value is ever equal to the string `"high"`.

    A rule that silently never fires is the worst of the three outcomes
    available, and this one was reached through the single door `conforms` was
    not watching. The ordered operators were checked because the *operator*
    looked suspicious; `eq` looked innocent.

    Only confident refusals are made. A numeric field compared with text and a
    textual field compared with a number are both certainly wrong. A `date` is
    an epoch in some registers and an ISO string in others, and an unknown dtype
    is somebody's extension — refusing either would refuse correct rules, and a
    conformance check that cries wolf is one somebody turns off.
    """
    if atom.op in NULLARY:
        return
    values = (atom.value if atom.op in LIST_VALUED
              else (list(atom.value) if atom.op == "between" else [atom.value]))
    for value in values:
        wrong = None
        # `bool` is a subclass of `int` in Python, so a True here would slip
        # through a plain isinstance check on a numeric field — and this
        # platform does not use booleans anywhere by rule.
        numberish = isinstance(value, (int, float)) and not isinstance(value, bool)
        if declared in NUMERIC_DTYPES and not numberish:
            wrong = "a number"
        elif declared in TEXTUAL_DTYPES and not isinstance(value, str):
            wrong = "text"
        if wrong:
            raise RuleError(
                "value_wrong_type",
                f"{path} compares '{atom.field}' with {value!r}, but the field "
                f"is declared '{declared}' and its values are {wrong}. The rule "
                f"would never fire",
                f"give a value that is {wrong}, or change the field's declared "
                f"type if it is the declaration that is wrong")


def _bracket(condition: Condition) -> str:
    """Parenthesise a nested group so 'a and b or c' cannot be misread."""
    text = condition.describe()
    return f"({text})" if condition.kind in (ALL, ANY) else text


def _ordered_pair(low: Any, high: Any) -> bool:
    """low <= high, when that question has an answer.

    When it has none — a string bound against a number — the pair is treated as
    not ordered, which surfaces as `empty_range` and refuses the rule. That is
    the right outcome: `between ["A", 5]` is a typo, not a range.
    """
    try:
        return low <= high
    except TypeError as exc:
        swallowed(logger, exc, "compared the bounds of a 'between'",
                  detail=f"{low!r} and {high!r} are not ordered against each "
                         f"other, so the range is refused as empty",
                  level=logging.INFO)
        return False
