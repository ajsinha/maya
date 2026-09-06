"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A rule set: ordered rules, first match wins, and a stated otherwise.

    {"rules": [{"id": "btl_high_ltv",
                "when":    {...},
                "then":    {"decision": "refer"},
                "because": "BTL above 80% LTV is outside appetite (CP-2024-11)"}],
     "otherwise": {"decision": "accept"},
     "note": "Origination eligibility, retail mortgages"}

Three decisions are worth recording.

**`otherwise` is required.** Totality by construction rather than by analysis:
no input falls through, and there is no implicit default anywhere in the
platform. A rule set whose author has not written down what happens to the cases
they did not think of is a rule set whose behaviour on those cases is an
accident.

**`because` is required, per rule.** A rule with no stated reason cannot be
defended to a supervisor, cannot be reviewed by whoever owns the policy, and
cannot be retired by anybody later because nobody knows what it was for. This is
the field that makes the difference between a rule set and a stored procedure,
and it is the one an author will most want to skip.

**Rule ids are stable and author-chosen.** The digest covers the *parsed*
canonical form, so reformatting the document does not produce a new parameter
set; reordering the rules does, because order is meaning.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.log import get_logger
from core.rules.common import MAX_RULES, RuleError
from core.rules.conditions import Condition
from core.rules.domains import Undecided, covers, union_covers, satisfiable

logger = get_logger(__name__)

#: An identifier a person will read in an audit report a year from now.
_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")


class Rule:
    """One rule. Immutable once built."""

    __slots__ = ("because", "id", "then", "when")

    def __init__(self, rule_id: str, when: Condition, then: Dict[str, Any],
                 because: str):
        self.id, self.when, self.then, self.because = rule_id, when, then, because

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "when": self.when.as_dict(),
                "then": dict(sorted(self.then.items())), "because": self.because}

    def describe(self) -> str:
        outcome = ", ".join(f"{k} = {v}" for k, v in sorted(self.then.items()))
        return f"when {self.when.describe()}, then {outcome}"


class RuleSet:
    """The parameter object of a T8 model, checked."""

    def __init__(self, rules: List[Rule], otherwise: Dict[str, Any],
                 note: str = ""):
        self.rules, self.otherwise, self.note = rules, otherwise, note
        # Rules the union check could not finish on. Kept apart from
        # `shadowed`, because "not checked" is not "no problem found" and a
        # report that merged them would be claiming a coverage guarantee it did
        # not compute.
        self.undecided: List[Dict[str, str]] = []

    # ------------------------------------------------------------------ build
    @classmethod
    def parse(cls, document: Any) -> "RuleSet":
        if not isinstance(document, dict):
            raise RuleError("ruleset_malformed",
                            f"a rule set is an object, not {type(document).__name__}",
                            "supply rules and otherwise")
        raw_rules = document.get("rules")
        if not isinstance(raw_rules, list) or not raw_rules:
            raise RuleError(
                "no_rules",
                "a rule set with no rules is its otherwise, written at length",
                "add at least one rule, or register this as a constant instead")
        if len(raw_rules) > MAX_RULES:
            raise RuleError(
                "too_many_rules",
                f"{len(raw_rules)} rules; the register holds up to {MAX_RULES}",
                "past this nobody is checking the first-match ordering by "
                "reading it, and the honest answer is that this wants to be a "
                "model rather than a rule set")
        otherwise = document.get("otherwise")
        if not isinstance(otherwise, dict) or not otherwise:
            raise RuleError(
                "otherwise_required",
                "the rule set has no 'otherwise', so it does not say what "
                "happens when no rule matches",
                "add 'otherwise'; a rule set without one behaves by accident on "
                "exactly the cases its author did not think of")

        rules, seen = [], set()
        for index, raw in enumerate(raw_rules):
            rule = cls._parse_rule(raw, index)
            if rule.id in seen:
                raise RuleError(
                    "duplicate_rule_id", f"two rules are called '{rule.id}'",
                    "ids appear in decisions and audit reports; they have to "
                    "name one rule each")
            seen.add(rule.id)
            rules.append(rule)
        return cls(rules, dict(otherwise), str(document.get("note", "")))

    @staticmethod
    def _parse_rule(raw: Any, index: int) -> Rule:
        where = f"rules[{index}]"
        if not isinstance(raw, dict):
            raise RuleError("ruleset_malformed", f"{where} is not an object",
                            "each rule is an object with id, when, then, because")
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise RuleError("rule_id_required", f"{where} has no id",
                            "give the rule a short name; it will be quoted in "
                            "every decision it makes")
        if set(rule_id) - _ID_CHARS:
            raise RuleError(
                "rule_id_malformed",
                f"'{rule_id}' contains characters outside a-z, 0-9 and underscore",
                "rule ids travel into logs, exports and audit reports; keep "
                "them plain")
        then = raw.get("then")
        if not isinstance(then, dict) or not then:
            raise RuleError("outcome_required", f"{where} ('{rule_id}') has no outcome",
                            "say what the rule decides")
        because = raw.get("because")
        if not isinstance(because, str) or not because.strip():
            raise RuleError(
                "reason_required",
                f"{where} ('{rule_id}') does not say why it exists",
                "give the reason — the policy, the limit, the regulation. A "
                "rule nobody can justify is one nobody can retire either, "
                "because nobody knows what it was for")
        when = Condition.parse(raw.get("when"), path=f"{where}.when")
        return Rule(rule_id, when, dict(then), because.strip())

    # ------------------------------------------------------------------ check
    def validate(self, input_schema: Dict[str, str],
                 output_schema: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Every check, run in the order a reader would want them.

        Returns a report rather than only raising, because an author fixing a
        forty-rule set wants the whole list. Anything that makes the set
        unusable raises; anything advisory is reported.
        """
        for rule in self.rules:
            rule.when.conforms(input_schema, path=f"rule '{rule.id}'")
            if not satisfiable(rule.when):
                raise RuleError(
                    "rule_never_fires",
                    f"rule '{rule.id}' has a condition no input can satisfy: "
                    f"{rule.when.describe()}",
                    "almost always a typo in a bound; fix it, or remove the rule")

        if output_schema:
            self._conform_outcomes(output_schema)
        shadowed = self._shadowed()
        contradictions = self._contradictions()

        # Contradictions first, and the order is not cosmetic. Two rules with
        # the same condition are also a shadowing — the first covers the second
        # exactly — so reporting shadowing first made `rules_contradict`
        # unreachable, in the checker written to find unreachable rules.
        #
        # It matters because the messages point somewhere different. "This rule
        # can never fire, reorder it" sends an author to the ordering; the
        # ordering is not the mistake. Two rules saying opposite things about
        # identical inputs is a disagreement about the policy, and somebody has
        # to decide which one is meant.
        if contradictions:
            first = contradictions[0]
            raise RuleError(
                "rules_contradict",
                f"rules '{first['a']}' and '{first['b']}' have the same "
                f"condition and different outcomes",
                "first match wins, so the second can never fire — but the "
                "ordering is not the problem. Decide which outcome the policy "
                "actually means")
        if shadowed:
            first = shadowed[0]
            raise RuleError(
                "rule_unreachable",
                f"rule '{first['rule']}' can never fire: rule '{first['shadowed_by']}' "
                f"comes first and matches everything it matches",
                "reorder them, narrow the earlier rule, or delete this one. A "
                "rule that never fires still appears in the model card and in "
                "every committee paper, and nobody reading either can tell")
        return {"rules": len(self.rules), "fields": sorted(self.fields()),
                "shadowed": shadowed, "contradictions": contradictions}

    def _conform_outcomes(self, output_schema: Dict[str, str]) -> None:
        for rule, label in [(r, f"rule '{r.id}'") for r in self.rules]:
            self._conform_one(rule.then, output_schema, label)
        self._conform_one(self.otherwise, output_schema, "otherwise")

    @staticmethod
    def _conform_one(outcome: Dict[str, Any], schema: Dict[str, str],
                     label: str) -> None:
        unknown = sorted(set(outcome) - set(schema))
        if unknown:
            raise RuleError(
                "unknown_outcome_field",
                f"{label} sets {', '.join(unknown)}, which this model's output "
                f"schema does not declare",
                f"declare it on the version, or set one of: "
                f"{', '.join(sorted(schema))}")

    def _shadowed(self) -> List[Dict[str, str]]:
        """Rules the earlier rules already cover.

        Two passes, and the difference between them is reported rather than
        smoothed over, because they support different promises.

        **One earlier rule.** Cheap, and it names the culprit: *rule 7 can never
        fire because rule 3 already covers it* sends an author straight to a
        line.

        **All of them together.** `ltv > 0.8` and `ltv <= 0.8` between them
        cover everything after, and no single-rule comparison sees it. This was
        for a long time a stated limit — *no rule is shadowed by any single
        earlier rule* — on the grounds that full coverage is satisfiability and
        a solver is a dependency nobody in the bank can debug. The premise was
        right and the conclusion did not follow: a conjunction here is already a
        box, so coverage is geometry, and `union_covers` decides it exactly by
        subtraction with no solver at all.

        The union answer says *these rules together* rather than naming one, so
        it is reported as its own kind. An author told "something above covers
        this" and an author told "rule 3 covers this" are doing different work.
        """
        found: List[Dict[str, str]] = []
        for index, rule in enumerate(self.rules):
            single = next((e for e in self.rules[:index]
                           if covers(e.when, rule.when)), None)
            if single is not None:
                found.append({"rule": rule.id, "shadowed_by": single.id,
                              "by": "one_earlier_rule"})
                continue
            if not self.rules[:index]:
                continue
            try:
                if union_covers([e.when for e in self.rules[:index]], rule.when):
                    found.append({
                        "rule": rule.id,
                        "shadowed_by": ", ".join(e.id for e in self.rules[:index]),
                        "by": "the earlier rules together"})
            except Undecided as exc:
                # Undecided is not "no problems found", and must never be
                # recorded as one. The rule set is still publishable; what is
                # reported is that this rule was not checked.
                logger.info("union coverage undecided for rule '%s': %s",
                            rule.id, exc)
                found_undecided = {"rule": rule.id, "by": "undecided",
                                   "shadowed_by": ""}
                self.undecided.append(found_undecided)
        return found

    def _contradictions(self) -> List[Dict[str, str]]:
        seen: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        found = []
        for rule in self.rules:
            key = repr(rule.when.as_dict())
            if key in seen:
                first_id, first_then = seen[key]
                if first_then != rule.then:
                    found.append({"a": first_id, "b": rule.id})
            else:
                seen[key] = (rule.id, rule.then)
        return found

    # ---------------------------------------------------------------- inspect
    def fields(self) -> set:
        read: set = set()
        for rule in self.rules:
            read |= rule.when.fields()
        return read

    def canonical(self) -> Dict[str, Any]:
        """The form the digest is taken over.

        The *parsed* form, not the submitted text: two documents differing only
        in key order or whitespace are one rule set. Rule order is preserved,
        because with first-match evaluation the order is the meaning.
        """
        return {"rules": [r.as_dict() for r in self.rules],
                "otherwise": dict(sorted(self.otherwise.items())),
                "note": self.note}

    def describe(self) -> List[str]:
        """The whole set in English, in evaluation order."""
        lines = [f"{i + 1}. {r.describe()}  — {r.because}"
                 for i, r in enumerate(self.rules)]
        outcome = ", ".join(f"{k} = {v}" for k, v in sorted(self.otherwise.items()))
        lines.append(f"otherwise, {outcome}")
        return lines

    # --------------------------------------------------------------- evaluate
    def decide(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """First match wins. The answer says which rule produced it.

        `matched_rule` is not diagnostics. A decision a bank cannot attribute to
        a rule is a decision it cannot explain to the customer who was refused,
        and under most consumer-credit regimes that is the obligation, not the
        outcome itself.
        """
        for rule in self.rules:
            if rule.when.holds(row):
                return {**rule.then, "matched_rule": rule.id,
                        "because": rule.because}
        return {**self.otherwise, "matched_rule": None,
                "because": "no rule matched; the stated otherwise applies"}
