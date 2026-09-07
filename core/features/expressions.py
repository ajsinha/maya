"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The expression language for derived features.

Deliberately small. Arithmetic, a handful of total functions, comparison — and
nothing else. It is parsed with Python's own parser and then walked against a
whitelist of node types, so what cannot be expressed cannot be smuggled in: no
attribute access, no subscripting, no calls except the named functions, no
comprehensions, no lambdas, no names except declared inputs.

The line this draws is the one the platform draws everywhere else. **MAYA
transforms features it already holds; it does not run models.** Computing
``x / y`` over a stored column is the same class of act as computing the null
rate MAYA already reports for every materialisation. Running a kernel is not,
and an expression that needs a library, external data or a model is declared
``external`` — the definition is still kept, so lineage and the leakage check
still work, but the values arrive by materialisation and the register says
plainly that the platform did not compute them.

For a long time this paragraph was aspirational. ``define`` parsed the
expression before it read ``evaluator``, so the expressions ``external`` names —
the ones needing a library or a model, which by construction this grammar cannot
parse — were refused whatever you declared them as. The only way through was to
register the result as a primitive, which discards the lineage and the leakage
check that keeping the definition was entirely *for*. An unparseable expression
now declares the features it reads instead, and a definition with neither a
parse nor a declared list is refused.
"""
from __future__ import annotations

import ast
import logging
import math
from typing import Any, Callable, Dict, FrozenSet, List, Set

from core.features.common import FeatureError
from core.log import get_logger, swallowed

logger = get_logger(__name__)

# The row's own event clock, readable so that an age or a lag is correct for the
# row rather than for the moment the expression happened to run.
EVENT_YEAR = "year(event_ts)"

FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "log": lambda x: math.log(x) if x > 0 else None,
    "exp": math.exp,
    "sqrt": lambda x: math.sqrt(x) if x >= 0 else None,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
}

FUNCTION_MEANING: Dict[str, str] = {
    "log": "natural logarithm; undefined at or below zero, which yields null",
    "exp": "e to the power of",
    "sqrt": "square root; undefined below zero, which yields null",
    "abs": "absolute value",
    "min": "the smaller of two values",
    "max": "the larger of two values",
    "round": "round to the nearest integer",
    "floor": "round down",
    "ceil": "round up",
}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.IfExp,
    ast.Call, ast.Name, ast.Load, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
    ast.USub, ast.UAdd, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.And, ast.Or,
)

# Names the language provides that are not features.
BUILTIN_NAMES: FrozenSet[str] = frozenset({"event_ts", "ingest_ts",
                                           "event_year"})


class Expression:
    """A parsed, whitelisted expression over named feature values."""

    def __init__(self, source: str):
        self.source = source.strip()
        if not self.source:
            raise FeatureError("a derived feature needs an expression")
        self.tree = self._parse(self.source)
        self.names = self._names(self.tree)

    # ------------------------------------------------------------------ parse
    @staticmethod
    def _parse(source: str) -> ast.Expression:
        # 'year(event_ts)' reads better in a definition, but it is rewritten to
        # the plain name 'event_year' rather than given a function, because a
        # function taking a timestamp would be the first step towards a date
        # library living in here. Both spellings mean the same thing.
        rewritten = source.replace(EVENT_YEAR, "event_year")
        try:
            tree = ast.parse(rewritten, mode="eval")
        except SyntaxError as exc:
            logger.info("rejected a derived expression that does not parse: %s", exc.msg)
            raise FeatureError(
                f"the expression does not parse: {exc.msg}. "
                f"the language is arithmetic, comparison and "
                f"{', '.join(sorted(FUNCTIONS))} — nothing else") from exc
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED_NODES):
                raise FeatureError(
                    f"'{type(node).__name__}' is not part of the expression "
                    f"language. it allows arithmetic, comparison and "
                    f"{', '.join(sorted(FUNCTIONS))} over feature names — an "
                    f"expression needing more than that is 'external', and the "
                    f"values are materialised rather than computed here")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise FeatureError(
                    f"'{node.id}' is not a feature name; names beginning with "
                    f"a double underscore are reserved by the language")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                    name = getattr(node.func, "id", "that")
                    raise FeatureError(
                        f"'{name}' is not one of the functions this language "
                        f"provides: {', '.join(sorted(FUNCTIONS))}")
        return tree

    @staticmethod
    def _names(tree: ast.Expression) -> Set[str]:
        return {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and n.id not in FUNCTIONS}

    # ---------------------------------------------------------------- inspect
    def feature_names(self) -> List[str]:
        """The features this expression reads. Its lineage, in one call."""
        return sorted(n for n in self.names if n not in BUILTIN_NAMES)

    def reads_clock(self) -> bool:
        return bool(self.names & BUILTIN_NAMES)

    # --------------------------------------------------------------- evaluate
    def evaluate(self, row: Dict[str, Any]) -> Any:
        """Compute the value for one row, or None where the maths says so.

        A null is a legitimate answer — log of a non-positive number, division by
        zero — and is returned rather than raised, because one bad row must not
        fail a materialisation of a million. What is *not* legitimate is a
        missing input, which means the expression and the data disagree.
        """
        env: Dict[str, Any] = dict(FUNCTIONS)
        for name in self.feature_names():
            if name not in row:
                raise FeatureError(
                    f"'{name}' is read by the expression but is not in the row; "
                    f"the derived feature and its inputs disagree")
            env[name] = row[name]
        for builtin in BUILTIN_NAMES & self.names:
            env[builtin] = (_year_of(row.get("event_ts")) if builtin == "event_year"
                            else row.get(builtin))
        if any(env.get(n) is None for n in self.feature_names()):
            return None                       # an input we do not have yet
        try:
            return eval(compile(self.tree, "<derived>", "eval"), {"__builtins__": {}}, env)
        except (ZeroDivisionError, ValueError, OverflowError, TypeError) as exc:
            # The arithmetic is undefined for this row. That is a null, not a
            # failure: the definition is sound and this row does not have an
            # answer. on_error records which was intended. Logged at debug
            # because a million-row materialisation with a thousand zero
            # denominators is normal, and a warning per row would bury the log.
            #
            # TypeError is here because a null PROPAGATES. `log` and `sqrt` are
            # total and return None outside their domain -- and the moment that
            # None met the next operator, `log(dscr) * beta` raised TypeError
            # and took down the materialisation this method exists to keep
            # running. An ordinary scorecard term and a single non-positive
            # DSCR were enough. Nulls absorbing arithmetic is the same rule SQL
            # applies and the one the rest of this file assumes.
            swallowed(logger, exc, "evaluated a derived expression",
                      f"'{self.source}' is undefined for this row; recorded null",
                      logging.DEBUG)
            return None


def _year_of(event_ts: Any) -> Any:
    import datetime as _dt
    if event_ts is None:
        return None
    return _dt.datetime.fromtimestamp(float(event_ts), _dt.timezone.utc).year


def describe() -> Dict[str, Any]:
    """What the language admits, so a caller can see it before writing one."""
    return {
        "functions": [{"name": k, "means": v} for k, v in sorted(FUNCTION_MEANING.items())],
        "operators": ["+", "-", "*", "/", "//", "%", "**",
                      "<", "<=", ">", ">=", "==", "!=", "and", "or", "not",
                      "x if cond else y"],
        "clock": [{"name": EVENT_YEAR,
                   "means": "the calendar year of the row's own event time, so "
                            "an age is right for the row rather than for now"},
                  {"name": "event_ts", "means": "when the fact was true"},
                  {"name": "ingest_ts", "means": "when the platform learned it"}],
        "excluded": "attribute access, subscripting, comprehensions, lambdas, "
                    "imports, and any function not listed — an expression "
                    "needing them is 'external'",
    }
