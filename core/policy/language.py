"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The rule language.

A gate that cannot be changed without a release is a gate that gets worked
around; a gate that can be changed by writing arbitrary code is not a gate at
all. So a rule is a **predicate over a closed vocabulary of facts**, and the
language is small enough to read in one sitting.

It has comparison, membership, boolean connectives, and two quantifiers over
collections. It has **no loops, no assignment, no function definitions and no
recursion**, which is what makes a rule something a reviewer can reason about
rather than something they have to run.

It is parsed with Python's own parser and walked against a whitelist of node
types, exactly as the derived-feature language is. What cannot be expressed
cannot be smuggled in.

The names a rule may use are the facts the gate publishes, and nothing else. A
name that is not a fact is refused **when the rule is written**, not when it is
evaluated — a rule that fails at the moment of a governance decision has failed
at the worst possible time.
"""
from __future__ import annotations

import ast
import logging
from typing import Any, Dict, FrozenSet, List, Sequence, Set

from core.log import get_logger, swallowed
from core.policy.common import PolicyError

logger = get_logger(__name__)

_ALLOWED = (
    ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.IfExp,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.Call,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Is, ast.IsNot,
    ast.Tuple, ast.List, ast.Set,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.BinOp, ast.USub,
    ast.GeneratorExp, ast.comprehension,
)

# The only callables. `any` and `all` take a generator so a rule can say
# something about every item in a collection without being able to iterate for
# its own purposes.
FUNCTIONS: FrozenSet[str] = frozenset({"any", "all", "len", "min", "max",
                                       "abs", "sorted", "sum"})

FUNCTION_MEANING: Dict[str, str] = {
    "any": "true when at least one item satisfies the condition",
    "all": "true when every item does — and vacuously true of nothing, which is "
           "worth remembering when a collection can be empty",
    "len": "how many",
    "min": "the smallest", "max": "the largest", "sum": "the total",
    "abs": "magnitude", "sorted": "in order",
}


# Bound once rather than reached for through __builtins__ at evaluation time:
# the environment a rule runs in should be a fixed, inspectable list.
_SAFE_FUNCTIONS: Dict[str, Any] = {
    "any": any, "all": all, "len": len, "min": min, "max": max,
    "abs": abs, "sorted": sorted, "sum": sum,
}


class Rule:
    """A parsed predicate over a named set of facts."""

    def __init__(self, source: str, vocabulary: Sequence[str]):
        self.source = (source or "").strip()
        if not self.source:
            raise PolicyError("empty_rule", "a rule with no expression is not a "
                                            "rule", "write the condition")
        self.vocabulary = set(vocabulary)
        self.tree = self._parse(self.source)
        self.names = self._names(self.tree)
        if unknown := sorted(self.names - self.vocabulary - FUNCTIONS):
            raise PolicyError(
                "unknown_fact",
                f"the rule reads {', '.join(unknown)}, which this gate does not "
                f"publish",
                f"the facts available here are "
                f"{', '.join(sorted(self.vocabulary))}. a rule that failed at "
                f"the moment of a governance decision would have failed at the "
                f"worst possible time, so it is refused now")

    @staticmethod
    def _parse(source: str) -> ast.Expression:
        try:
            tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:
            swallowed(logger, exc, "parsed a policy rule",
                      "refused now rather than at the moment of a decision",
                      logging.INFO)
            raise PolicyError(
                "rule_does_not_parse",
                f"the rule does not parse: {exc.msg}",
                "the language is comparison, membership, and/or/not, and "
                f"{', '.join(sorted(FUNCTIONS))} — nothing else") from exc
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED):
                raise PolicyError(
                    "not_in_the_language",
                    f"'{type(node).__name__}' is not part of the rule language",
                    "it has no loops, no assignment and no function definitions, "
                    "which is what makes a rule something a reviewer can reason "
                    "about rather than something they have to run")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                    raise PolicyError(
                        "unknown_function",
                        f"'{getattr(node.func, 'id', 'that')}' is not one of the "
                        f"functions this language provides",
                        f"it provides {', '.join(sorted(FUNCTIONS))}")
            if isinstance(node, ast.Name) and node.id.startswith("_"):
                raise PolicyError("reserved_name",
                                  f"'{node.id}' is not a fact; names beginning "
                                  f"with an underscore are reserved", "")
        return tree

    @staticmethod
    def _names(tree: ast.Expression) -> Set[str]:
        # Comprehension targets are the rule's own bindings, not facts.
        bound = {t.id for node in ast.walk(tree)
                 if isinstance(node, ast.comprehension)
                 for t in ast.walk(node.target) if isinstance(t, ast.Name)}
        return {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name)} - bound

    def facts_read(self) -> List[str]:
        """Which facts this rule actually consults. Its dependencies, in one call."""
        return sorted(self.names & self.vocabulary)

    def evaluate(self, facts: Dict[str, Any]) -> bool:
        """True or false, over the facts supplied. Never anything else."""
        missing = sorted(set(self.facts_read()) - set(facts))
        if missing:
            raise PolicyError(
                "fact_not_supplied",
                f"the rule reads {', '.join(missing)} and the gate did not "
                f"supply it",
                "this is a defect in the gate rather than in the rule")
        environment = {name: facts.get(name) for name in self.vocabulary}
        environment.update(_SAFE_FUNCTIONS)
        try:
            result = eval(compile(self.tree, "<rule>", "eval"),
                          {"__builtins__": {}}, environment)
        except Exception as exc:
            swallowed(logger, exc, "evaluated a policy rule",
                      "reported as a refusal to publish rather than a verdict",
                      logging.WARNING)
            raise PolicyError(
                "rule_failed",
                f"the rule did not evaluate: {exc}",
                "a rule that throws at the moment of a decision is a rule that "
                "has not been tested against the facts it reads") from exc
        # A rule returns a verdict, not a value. Anything else is a rule that
        # was written as an expression and read as a decision.
        return bool(result)


def describe() -> Dict[str, Any]:
    return {
        "operators": ["==", "!=", "<", "<=", ">", ">=", "in", "not in",
                      "is", "is not", "and", "or", "not", "x if c else y",
                      "+ - * /"],
        "functions": [{"name": f, "means": FUNCTION_MEANING.get(f, "")}
                      for f in sorted(FUNCTIONS)],
        "excluded": "loops, assignment, function definitions, attribute access, "
                    "subscripting, imports — a rule is a predicate, not a program",
        "why": "a gate that cannot be changed without a release gets worked "
               "around; a gate that can be changed by writing arbitrary code is "
               "not a gate at all",
    }
