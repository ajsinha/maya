"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Rule sets: the T8 parameter object, given a shape.

A **T8** model is one whose parameter object is a rule set somebody authored —
eligibility criteria, exclusion lists, limit checks, override policy, the band
assignment on the end of a scorecard. In a real bank this is the largest
population by count and the least well governed by anything, because a rule set
is usually a spreadsheet, a stored procedure, or a paragraph in a policy
document that somebody transcribed into code once.

MAYA already held these: `parameter_kind: rule_set`, `fit_procedure: author`,
`provenance: declared` — *"asserted by a person, and attested rather than
fitted"*. What it held them as was an arbitrary JSON blob in `values`. Versioned,
digested, approved by a second person, and completely opaque: the platform could
tell you the rule set had changed and not one thing about what it said.

## Why a structure and not an expression language

`core/features/expressions.py` parses a whitelisted arithmetic expression, and
the obvious move is to reuse it. It is the wrong move here, for a reason worth
stating: **a free expression is opaque to analysis.**

The entire argument for putting rule sets in a governance platform is that a
rule set is the one kind of model a non-programmer can actually review — and
that the platform can therefore say things about it that it cannot say about a
neural network. Whether a rule can ever fire. Whether two rules contradict each
other. Whether any input falls through. None of those questions can be answered
about `x * 0.3 + y > threshold`; all of them can be answered about a tree of
`field op value`.

So conditions are structured, and there is no arithmetic. A rule needing
arithmetic needs a **derived feature**, which is the same boundary MAYA draws
everywhere else: the platform transforms what it holds and does not compute new
quantities inside a governed object.

## What the structure buys

Four checks, run before a rule set can be saved:

* **Totality** — `otherwise` is required, so no input falls through. By
  construction rather than by analysis.
* **Reachability** — a rule an earlier rule already covers can never fire.
  A rule nobody can trigger is worse than an absent one: somebody believes it is
  in force. This is the `docs/11 §3` pattern, arrived at from the model side.
* **Contradiction** — the same condition reaching two different outcomes.
* **Conformance** — every field a rule reads is one the version's
  `input_schema` declares, at a compatible type. This is `refines` again, the
  same order used for featureset satisfaction and typed composition (`L-20`,
  `L-21`).
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, Tuple


class RuleError(RuntimeError):
    """A rule set was refused. The message always says which rule and why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


# --------------------------------------------------------------------- atoms
#: Comparison operators. Deliberately small: everything here is decidable over
#: an interval-and-set domain, which is what makes the reachability analysis
#: possible at all. Adding `matches` or `like` would end that.
OPERATORS: Tuple[str, ...] = (
    "eq", "ne", "lt", "le", "gt", "ge",
    "in", "not_in", "between",
    "is_null", "not_null",
)

OPERATOR_MEANING: Dict[str, str] = {
    "eq": "equal to", "ne": "not equal to",
    "lt": "less than", "le": "at most",
    "gt": "greater than", "ge": "at least",
    "in": "one of", "not_in": "none of",
    "between": "within the closed range [low, high]",
    "is_null": "not supplied", "not_null": "supplied",
}

#: Operators taking no `value` at all. Passing one is a refusal rather than an
#: ignored field: silently dropping part of a governed document is how a rule
#: comes to mean something other than what its author reads back.
NULLARY: FrozenSet[str] = frozenset({"is_null", "not_null"})

#: Operators whose `value` is a list.
LIST_VALUED: FrozenSet[str] = frozenset({"in", "not_in"})

#: Operators that require an ordered domain. Asking whether one product code is
#: less than another is a question with no answer, and a rule set that asks it
#: is one somebody will read as meaningful.
ORDERED_ONLY: FrozenSet[str] = frozenset({"lt", "le", "gt", "ge", "between"})

#: dtypes with an order. Everything else is treated as categorical — equality
#: and membership only.
ORDERED_DTYPES: FrozenSet[str] = frozenset({
    "numeric", "float", "double", "integer", "int", "number", "date", "datetime",
})

#: dtypes whose values are numbers, and dtypes whose values are text. Used to
#: refuse a rule comparing a field against a value of the wrong kind.
#:
#: `date` and `datetime` are in neither: a date is written as an epoch in some
#: registers and as an ISO string in others, and refusing one of those spellings
#: would refuse a correct rule. An unknown dtype is likewise left alone. The
#: check declines to have an opinion wherever it cannot have a confident one —
#: a conformance check that produces false refusals is one somebody turns off.
NUMERIC_DTYPES: FrozenSet[str] = frozenset({
    "numeric", "float", "double", "integer", "int", "number",
})
TEXTUAL_DTYPES: FrozenSet[str] = frozenset({
    "string", "categorical", "text", "char", "varchar",
})

# ----------------------------------------------------------------- combinators
ALL, ANY, NOT = "all", "any", "not"
COMBINATORS: Tuple[str, ...] = (ALL, ANY, NOT)

#: A condition tree deeper than this is not being reviewed by anybody, which is
#: the only reason rule sets are worth holding. Refused rather than truncated.
MAX_DEPTH = 6

#: Rules per set. Past this the first-match-wins ordering is not something a
#: person is checking, and the honest answer is that it wants to be a model.
MAX_RULES = 512
