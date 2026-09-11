"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reading a rulebook a bank already has.

## Why this is the item that decides whether T8 is a programme

A T8 model's parameter object is a **rule set**: authored rather than fitted, so
authorship is its provenance. The register can hold one, version it, require a
second person to approve it, and explain every decision it makes back to the
rule that made it. All of that works, and all of it works on rule sets somebody
typed in.

A bank's actual rulebook is not typed in anywhere. It is a decision table in a
spreadsheet that four people maintain, a DMN file exported from a BPM suite, or
a stored procedure nobody has opened since the person who wrote it left. The
distance between *the register can hold a rule set* and *the register holds this
bank's rules* is that gap, and it is the whole difference between a
demonstration and a migration.

## Why a parser is the frightening part, and what is done about it

Each of these formats is a parser, and a parser that can be subtly wrong. A
misread threshold does not fail — it produces a rule set that loads, validates,
publishes and decides differently from the rulebook it claims to be. Nobody
finds that by looking at it. So three things hold here, and they are the design
rather than the features:

**Nothing is imported. A candidate is produced.** The output is a rule set
*document* and a report, and it goes through exactly the same `check`, `trial`
and `publish` path a hand-written one does — including the second-person
approval. An importer that wrote into the register would be authoring a
parameter set on somebody's behalf, which is the one thing the rules editor was
careful not to do.

**What could not be read is named, never guessed.** A cell holding `>=650 and
<720` is two conditions and parses; one holding `good credit` is a human
judgement and does not. The second is reported as an **untranslated row**, and
an import with untranslated rows is refused as a *whole document* rather than
silently producing a rule set that is missing the hard cases — which are exactly
the rows the rulebook exists for.

**Order is carried, and the loss of it is reported.** A decision table with a
`hit policy` of FIRST is ordered and maps onto first-match directly. UNIQUE
claims the rows are disjoint, which the rule set's own shadowing check can
verify. COLLECT and PRIORITY do not map at all, and are refused by name rather
than approximated — approximating an aggregation as a first match produces a
rule set that agrees with the source on most inputs, which is worse than one
that disagrees on all of them.

## And a stored procedure is refused

The third format in the roadmap row was *a stored procedure*. It is not here and
will not be. SQL is a general language with control flow, mutation and side
effects; a translator would be a compiler, a wrong compiler is undetectable by
reading its output, and the failure mode is a rule set that is subtly not the
thing the bank has been running. `NOT_TRANSLATED` says so with a route to what
the caller actually wanted: a decision table extracted from the procedure by
somebody who understands it, which is work MAYA cannot do and should not
pretend to.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

from core.log import get_logger
from core.rules.common import RuleError

logger = get_logger(__name__)

DECISION_TABLE, DMN = "decision_table", "dmn"

#: What is refused, and what to do instead. A format named with a reason is a
#: conversation; a format missing is a support ticket.
NOT_TRANSLATED: Dict[str, str] = {
    "stored_procedure": (
        "SQL is a general language with control flow, mutation and side "
        "effects, so a translator would be a compiler — and a wrong compiler "
        "produces a rule set that loads, validates and decides differently "
        "from the procedure it claims to be, which nobody finds by reading it. "
        "Extract a decision table from the procedure with somebody who "
        "understands it, and import that"),
    "drools": (
        "a DRL file is a production-rule program with an agenda, working "
        "memory and rule chaining. First-match over a flat list is not a "
        "conservative approximation of that, it is a different evaluation "
        "model. Export the decision tables the DRL was generated from, if it "
        "was; if it was not, this wants to be a model rather than a rule set"),
    "pmml_scorecard": (
        "a PMML scorecard is a MODEL — points accumulate and a total is "
        "banded — not a rule set, and importing it as one would put an "
        "authored-parameter provenance on something that was fitted. Register "
        "it as a model version with its own artifact"),
}

#: Hit policies, and whether first-match can carry them honestly.
HIT_POLICIES: Dict[str, str] = {
    "FIRST": "ordered, and first-match is exactly this",
    "F": "ordered, and first-match is exactly this",
    "UNIQUE": "claims at most one row matches any input. Carried as first-match "
              "AND checked: the rule set's own shadowing analysis reports any "
              "row that a rule above it already covers, which is the claim "
              "failing",
    "U": "claims at most one row matches any input. Carried as first-match "
         "AND checked",
    "ANY": "claims every matching row gives the same outcome. Carried as "
           "first-match, and the shadowing report is where a disagreement "
           "would show",
    "A": "claims every matching row gives the same outcome. Carried as "
         "first-match",
}

#: Hit policies that do not map, with what each would silently become.
UNMAPPABLE: Dict[str, str] = {
    "COLLECT": "aggregates across every matching row — a sum, a count, a min. "
               "First-match would return the first row's outcome and agree "
               "with the source on most inputs, which is worse than "
               "disagreeing on all of them",
    "C": "aggregates across every matching row. First-match would silently "
         "return one of them",
    "PRIORITY": "orders by OUTPUT priority rather than by row order, so the "
                "row that wins is not the row that appears first. Reading it "
                "top-down inverts the rulebook on exactly the overlapping "
                "cases it was written to resolve",
    "P": "orders by output priority rather than row order",
    "OUTPUT ORDER": "returns every matching row, ordered by output priority",
    "RULE ORDER": "returns every matching row in row order",
    "R": "returns every matching row in row order",
}

#: A cell that is blank, or one of these, matches anything.
ANY_CELL = frozenset({"", "-", "—", "–", "*", "any", "ANY", "n/a", "N/A"})

_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_COMPARISON = re.compile(r"^(<=|>=|<|>|=|!=)\s*(-?\d+(?:\.\d+)?)$")
_RANGE = re.compile(r"^([\[\(])\s*(-?\d+(?:\.\d+)?)\s*\.\.\s*"
                    r"(-?\d+(?:\.\d+)?)\s*([\]\)])$")
_ID_SAFE = re.compile(r"[^a-z0-9]+")


class RuleSetImport:
    """Turns a decision table or a DMN file into a rule set **candidate**."""

    def __init__(self, editor=None):
        """`editor` is optional and is never written through.

        It is held so `check` can run the platform's own validation over the
        produced document against a real version's schemas — which is the
        only way to find out whether an import is usable, as opposed to
        whether it parsed.
        """
        self.editor = editor

    # ------------------------------------------------------------- describe
    @staticmethod
    def formats() -> Dict[str, Any]:
        """What can be read, what cannot, and what a caller should do instead."""
        return {
            "reads": [
                {"format": DECISION_TABLE,
                 "what": "a CSV decision table: one header row naming the "
                         "input fields and the outcomes, one row per rule, "
                         "and a blank cell meaning `anything`",
                 "columns": "inputs are named plainly; outcome columns are "
                            "prefixed `out:`; `id`, `because` and `priority` "
                            "are recognised if present"},
                {"format": DMN,
                 "what": "a DMN 1.3 decision table, as a BPM suite exports it",
                 "columns": "`inputExpression` names the field, `inputEntry` "
                            "carries the unary test, `outputEntry` the result"},
            ],
            "not_translated": [{"format": k, "why": v}
                               for k, v in NOT_TRANSLATED.items()],
            "hit_policies": {"carried": sorted(set(HIT_POLICIES)),
                             "refused": sorted(set(UNMAPPABLE))},
            "imports_anything": False,
            "detail": (
                "an import produces a rule set DOCUMENT and a report, never a "
                "parameter set. It goes through the same check, trial and "
                "publish path a hand-written rule set does, including the "
                "second-person approval — because an importer that wrote into "
                "the register would be authoring a parameter set on somebody "
                "else's behalf. Rows that could not be translated are named, "
                "and a document with any of them is refused whole: the rows a "
                "parser finds hard are the judgement calls, and those are what "
                "the rulebook exists for"),
        }

    # --------------------------------------------------------------- reading
    def read(self, fmt: str, document: Any, *,
             note: str = "") -> Dict[str, Any]:
        """Parse into a rule set candidate. Writes nothing, decides nothing."""
        if fmt in NOT_TRANSLATED:
            raise RuleError(
                "format_not_translated",
                f"'{fmt}' is not translated into a rule set",
                NOT_TRANSLATED[fmt])
        if fmt == DECISION_TABLE:
            rules, untranslated, meta = self._read_table(document)
        elif fmt == DMN:
            rules, untranslated, meta = self._read_dmn(document)
        else:
            raise RuleError(
                "unknown_import_format",
                f"'{fmt}' is not a format this reads",
                f"the two are {DECISION_TABLE} and {DMN}. Refused formats are "
                f"published with their reasons at /rule-import/formats")
        return self._report(fmt, rules, untranslated, meta, note)

    def _report(self, fmt: str, rules: List[Dict[str, Any]],
                untranslated: List[Dict[str, Any]],
                meta: Dict[str, Any], note: str) -> Dict[str, Any]:
        usable = not untranslated and bool(rules)
        document: Optional[Dict[str, Any]] = None
        if usable:
            document = {
                "rules": rules,
                # The catch-all is deliberately NOT invented from the last row.
                # A decision table's final row is often a catch-all and often
                # is not, and guessing wrong produces a rule set that decides
                # confidently on the inputs nobody thought about.
                "otherwise": meta.get("otherwise") or {},
                "note": note or meta.get("note", ""),
            }
        return {
            "format": fmt, "rules": len(rules),
            "candidate": document,
            "untranslated": untranslated,
            "needs_an_otherwise": bool(usable and not meta.get("otherwise")),
            "otherwise_from": meta.get("otherwise_from"),
            "hit_policy": meta.get("hit_policy"),
            "hit_policy_note": meta.get("hit_policy_note"),
            "imports_anything": False,
            "detail": self._detail(fmt, rules, untranslated, meta, usable),
        }

    @staticmethod
    def _detail(fmt: str, rules: List[Dict[str, Any]],
                untranslated: List[Dict[str, Any]], meta: Dict[str, Any],
                usable: bool) -> str:
        if not rules and not untranslated:
            return (f"this {fmt} document contains no rows. A table with a "
                    f"header and nothing under it is usually an export that "
                    f"ran against the wrong sheet")
        out = f"{len(rules)} row(s) translated"
        if untranslated:
            out += (f", and {len(untranslated)} could not be. The document is "
                    f"refused as a whole rather than offered without them: a "
                    f"parser finds the judgement calls hard, and the judgement "
                    f"calls are what a rulebook exists for. Each is listed "
                    f"with the cell that stopped it")
            return out
        if meta.get("hit_policy_note"):
            out += f". Hit policy {meta['hit_policy']}: {meta['hit_policy_note']}"
        if meta.get("otherwise_from"):
            out += f". The catch-all is {meta['otherwise_from']}"
        if usable and not meta.get("otherwise"):
            out += (". **No catch-all was found**, and one is not invented "
                    "from the last row — a decision table's final row is "
                    "sometimes a catch-all and sometimes is not, and guessing "
                    "wrong produces a rule set that decides confidently on "
                    "exactly the inputs nobody thought about. Add `otherwise` "
                    "before publishing")
        out += (". Nothing has been written. This is a candidate for the same "
                "check, trial and publish path a hand-written rule set takes, "
                "and it still needs somebody other than its author to approve "
                "it")
        return out

    # -------------------------------------------------------- decision table
    def _read_table(self, document: Any
                    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]],
                               Dict[str, Any]]:
        text = document.decode("utf-8") if isinstance(document, bytes) \
            else str(document)
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            return [], [], {}
        header = [h for h in (rows[0].keys() or []) if h]
        outputs = [h for h in header if h.lower().startswith("out:")]
        if not outputs:
            raise RuleError(
                "no_outcome_columns",
                "no column is prefixed `out:`, so nothing in this table says "
                "what a matching row decides",
                "prefix each outcome column with `out:` — the prefix exists "
                "because a table whose outcome columns are guessed from "
                "position breaks the first time somebody inserts a column")
        inputs = [h for h in header
                  if h not in outputs and h.lower() not in
                  ("id", "because", "priority", "hit policy", "hit_policy")]
        meta = self._table_meta(rows)
        rules: List[Dict[str, Any]] = []
        untranslated: List[Dict[str, Any]] = []
        for index, row in enumerate(rows):
            rule, problem = self._table_row(row, inputs, outputs, index)
            if rule:
                rules.append(rule)
            else:
                self._place_unconditional(problem, index, len(rows), meta,
                                          untranslated)
        return rules, untranslated, meta

    @staticmethod
    def _place_unconditional(problem: Dict[str, Any], index: int, total: int,
                             meta: Dict[str, Any],
                             untranslated: List[Dict[str, Any]]) -> None:
        """A row that constrains nothing matches everything. Where it sits is
        what decides whether that is the catch-all or a defect.

        **Last row**: it is the catch-all, by the semantics of first-match and
        not by inference from its position. Lifting it into `otherwise` is a
        derivation — the rule set language has a slot for exactly this and
        carrying it as a rule instead would be the awkward choice.

        **Anywhere else**: every row below it is unreachable. That is a defect
        in the source table rather than in the import, and reporting it is
        more use than either dropping the rows or translating a table that
        cannot behave the way it reads.
        """
        if problem.get("why") != "__unconditional__":
            untranslated.append(problem)
            return
        if index == total - 1:
            meta["otherwise"] = problem["then"]
            meta["otherwise_from"] = (
                f"the last row ('{problem['id']}'), which constrains no input "
                f"and therefore matches everything. In a first-match table "
                f"that IS the catch-all — it is lifted into `otherwise` "
                f"because the language has a slot for it, not because it "
                f"happened to be last")
            return
        untranslated.append({
            "where": problem["where"], "field": "(every input column)",
            "cell": "",
            "why": ("this row constrains no input, so it matches every "
                    "input — and it is not the last row, so every row below "
                    "it is unreachable. That is a defect in the table rather "
                    "than in this import. Either give it a condition or move "
                    "it to the end, where it is the catch-all")})

    def _table_meta(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        policy = ""
        for key in ("hit policy", "hit_policy"):
            if rows and rows[0].get(key):
                policy = str(rows[0][key]).strip().upper()
                break
        if not policy:
            # Absent means FIRST in DMN, and the register says so rather than
            # assuming silently: a reader who knows the table was UNIQUE needs
            # to see that MAYA read it as ordered.
            return {"hit_policy": "FIRST (assumed)",
                    "hit_policy_note": "no hit policy was stated. DMN's "
                                       "default is FIRST and that is what was "
                                       "read, which is stated here rather than "
                                       "assumed quietly"}
        if policy in UNMAPPABLE:
            raise RuleError(
                "hit_policy_not_mappable",
                f"hit policy {policy} does not map onto a first-match rule set",
                UNMAPPABLE[policy] + ". Re-express the table with FIRST or "
                "UNIQUE, which are the two policies a first-match rule set "
                "can carry without changing what the rulebook says")
        return {"hit_policy": policy,
                "hit_policy_note": HIT_POLICIES.get(policy, "")}

    def _table_row(self, row: Dict[str, Any], inputs: List[str],
                   outputs: List[str], index: int
                   ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        where = f"row {index + 2}"        # +2: header, and 1-based for a human
        clauses: List[Dict[str, Any]] = []
        bad: Optional[Dict[str, Any]] = None
        for field in inputs:
            cell = str(row.get(field) or "").strip()
            if cell in ANY_CELL:
                continue
            clause = _cell_to_condition(field, cell)
            if clause is None:
                bad = {"where": where, "field": field, "cell": cell,
                       "why": ("this cell is not a comparison, a range, a "
                               "literal or a list of literals. Most often it "
                               "is a human judgement — 'good credit', 'as "
                               "agreed' — which is precisely what must not be "
                               "guessed at")}
                break
            clauses.append(clause)
        if bad:
            return None, bad
        then = {}
        for column in outputs:
            value = str(row.get(column) or "").strip()
            if value:
                then[column[4:].strip()] = _literal(value)
        if not then:
            return None, {"where": where, "field": ", ".join(outputs),
                          "cell": "", "why": "the row decides nothing: every "
                                             "outcome column is empty"}
        because = str(row.get("because") or row.get("Because") or "").strip()
        if not because:
            return None, {
                "where": where, "field": "because", "cell": "",
                "why": ("the row gives no reason. The register requires one on "
                        "every rule, and it is not a formality: a rule nobody "
                        "can justify is one nobody can retire either, because "
                        "nobody knows what it was for. Add a `because` column "
                        "to the export")}
        rule_id = str(row.get("id") or row.get("Id") or "").strip() \
            or f"r{index + 1}"
        if not clauses:
            # No input cell constrains anything, so this row matches every
            # input. What that MEANS is decided by where it sits, and both
            # answers are derivations rather than guesses — which is why the
            # caller passes the position in.
            return None, {
                "where": where, "field": "(every input column)", "cell": "",
                "why": "__unconditional__", "id": _safe_id(rule_id),
                "then": then, "because": because}
        return {"id": _safe_id(rule_id),
                "when": clauses[0] if len(clauses) == 1
                else {"all": clauses},
                "then": then, "because": because}, {}

    # -------------------------------------------------------------------- DMN
    def _read_dmn(self, document: Any
                  ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]],
                             Dict[str, Any]]:
        text = document.decode("utf-8") if isinstance(document, bytes) \
            else str(document)
        root = _parse_xml(text)
        table = _first(root, "decisionTable")
        if table is None:
            raise RuleError(
                "no_decision_table",
                "this DMN document contains no decision table",
                "MAYA reads a decision table and nothing else in DMN. A "
                "literal expression, an invocation or a BKM is a program, and "
                "translating one would be writing a compiler")
        policy = (table.get("hitPolicy") or "FIRST").strip().upper()
        if policy in UNMAPPABLE:
            raise RuleError(
                "hit_policy_not_mappable",
                f"hit policy {policy} does not map onto a first-match rule set",
                UNMAPPABLE[policy] + ". Re-express the decision with FIRST or "
                "UNIQUE")
        inputs = [_label(e) for e in _all(table, "input")]
        outputs = [_label(e) for e in _all(table, "output")]
        raw_rules = _all(table, "rule")
        meta: Dict[str, Any] = {
            "hit_policy": policy,
            "hit_policy_note": HIT_POLICIES.get(policy, ""),
            "note": (table.get("id") or "")}
        rules: List[Dict[str, Any]] = []
        untranslated: List[Dict[str, Any]] = []
        for index, raw in enumerate(raw_rules):
            rule, problem = self._dmn_rule(raw, inputs, outputs, index)
            if rule:
                rules.append(rule)
            else:
                self._place_unconditional(problem, index, len(raw_rules), meta,
                                          untranslated)
        return rules, untranslated, meta

    def _dmn_rule(self, raw: Any, inputs: List[str], outputs: List[str],
                  index: int
                  ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        where = f"rule {index + 1}"
        clauses: List[Dict[str, Any]] = []
        for field, entry in zip(inputs, _all(raw, "inputEntry")):
            cell = (_text(entry) or "").strip()
            if cell in ANY_CELL:
                continue
            clause = _cell_to_condition(field, cell)
            if clause is None:
                return None, {
                    "where": where, "field": field, "cell": cell,
                    "why": ("this unary test is not a comparison, a range, a "
                            "literal or a list of literals. FEEL is an "
                            "expression language and the rest of it is not "
                            "translated, because a partially-understood "
                            "expression is worse than one that was refused")}
            clauses.append(clause)
        then = {}
        for field, entry in zip(outputs, _all(raw, "outputEntry")):
            value = (_text(entry) or "").strip()
            if value and value not in ANY_CELL:
                then[_safe_id(field)] = _literal(value)
        if not then:
            return None, {"where": where, "field": ", ".join(outputs),
                          "cell": "", "why": "the rule decides nothing"}
        because = (_text(raw, "description") or "").strip()
        if not because:
            return None, {
                "where": where, "field": "description", "cell": "",
                "why": ("the DMN rule has no description, and the register "
                        "requires a reason on every rule. Fill in the "
                        "description in the source decision — a rule nobody "
                        "can justify is one nobody can retire")}
        rule_id = (raw.get("id") or f"r{index + 1}")
        if not clauses:
            return None, {
                "where": where, "field": "(every input column)", "cell": "",
                "why": "__unconditional__", "id": _safe_id(rule_id),
                "then": then, "because": because}
        return {"id": _safe_id(rule_id),
                "when": clauses[0] if len(clauses) == 1
                else {"all": clauses},
                "then": then, "because": because}, {}

    # ---------------------------------------------------------------- check
    def check(self, urn: str, semver: str, fmt: str, document: Any,
              *, note: str = "") -> Dict[str, Any]:
        """Read, then run the platform's own validation over the result.

        Parsing tells you the document was *readable*. This tells you whether
        it is **usable against a real version's schemas** — whether the fields
        it tests exist, whether the outcomes conform, and which rules shadow
        which. That is the question somebody importing a rulebook actually
        has, and answering only the first would be the import equivalent of a
        scanner grading itself.
        """
        read = self.read(fmt, document, note=note)
        if read["candidate"] is None or self.editor is None:
            return {**read, "validated": False,
                    "why_not_validated": (
                        "the document has untranslated rows, so there is "
                        "nothing whole to validate against"
                        if read["untranslated"] else
                        "no editor is wired, so this was parsed and not "
                        "checked against a version's schemas")}
        report = self.editor.check(urn, semver, read["candidate"])
        return {**read, "validated": True, "validation": report}


# ------------------------------------------------------------------ helpers
def _cell_to_condition(field: str, cell: str) -> Optional[Dict[str, Any]]:
    """One cell as a condition, or None when it is not translatable.

    None is a real answer here and the most important one this module gives.
    Every alternative — a best guess, a regex that mostly works, treating an
    unparsed cell as `anything` — produces a rule set that runs and is not the
    rulebook.
    """
    cell = cell.strip()
    if match := _RANGE.match(cell):
        open_b, low, high, close_b = match.groups()
        # A DMN range is inclusive or exclusive per end, and `between` here is
        # inclusive of both. Rather than approximate, an exclusive end is
        # expressed as the pair of comparisons it actually is.
        if open_b == "[" and close_b == "]":
            return {"field": field, "op": "between",
                    "value": [float(low), float(high)]}
        return {"all": [
            {"field": field, "op": "ge" if open_b == "[" else "gt",
             "value": float(low)},
            {"field": field, "op": "le" if close_b == "]" else "lt",
             "value": float(high)}]}
    if match := _COMPARISON.match(cell):
        symbol, number = match.groups()
        op = {"<=": "le", ">=": "ge", "<": "lt", ">": "gt",
              "=": "eq", "!=": "ne"}[symbol]
        return {"field": field, "op": op, "value": float(number)}
    if "," in cell:
        parts = [p.strip().strip('"').strip("'") for p in cell.split(",")]
        if all(parts) and not any(_COMPARISON.match(p) for p in parts):
            return {"field": field, "op": "in", "value": [_literal(p)
                                                          for p in parts]}
        return None
    if cell.lower() in ("null", "is null"):
        return {"field": field, "op": "is_null", "value": None}
    if cell.lower() in ("not null", "is not null"):
        return {"field": field, "op": "not_null", "value": None}
    if _NUMBER.match(cell):
        return {"field": field, "op": "eq", "value": float(cell)}
    quoted = cell.strip('"').strip("'")
    if quoted and quoted == cell.strip('"').strip("'") and " " not in quoted:
        return {"field": field, "op": "eq", "value": quoted}
    if cell.startswith('"') and cell.endswith('"'):
        return {"field": field, "op": "eq", "value": cell[1:-1]}
    return None


def _literal(value: str) -> Any:
    text = value.strip().strip('"').strip("'")
    if _NUMBER.match(text):
        return float(text)
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    return text


def _safe_id(text: str) -> str:
    """Rule ids travel into logs, exports and audit reports, so they are kept
    plain — the same constraint the rule set itself enforces at parse."""
    return _ID_SAFE.sub("_", str(text).lower()).strip("_") or "rule"


#: A DMN file arrives from outside and is parsed, which is the one place in
#: this codebase that reads untrusted XML. Two attacks matter and neither needs
#: a dependency to stop.
MAX_DMN_BYTES = 8 * 1024 * 1024


def _parse_xml(text: str) -> Any:
    """Parse a DMN document, refusing the two shapes that are attacks.

    **A DOCTYPE is refused outright.** Every XML attack worth the name arrives
    through one: external entities reading `/etc/passwd` or reaching a URL from
    inside the network, and internal entity expansion turning two kilobytes
    into two gigabytes of memory. A DMN decision table has no legitimate use
    for a DOCTYPE, so refusing it costs nothing and removes the class — which
    is a better answer than a parser configured to be careful, because the
    careful configuration is the thing somebody later copies without.

    **And the document is bounded.** A parser that streams happily through a
    gigabyte of nested elements is a way to take the process down with one
    upload.

    `defusedxml` would do this too. It is not used for the reason nothing else
    here is: a governance platform that cannot be deployed air-gapped is one
    somebody works around, and this is nine lines.
    """
    if len(text) > MAX_DMN_BYTES:
        raise RuleError(
            "dmn_too_large",
            f"this document is {len(text) // 1024} KiB; the reader accepts up "
            f"to {MAX_DMN_BYTES // (1024 * 1024)} MiB",
            "a decision table this size is not a decision table anybody "
            "reads, which is the more useful finding. Split it, or accept "
            "that it wants to be a model")
    if re.search(r"<!DOCTYPE", text[:4096], re.I):
        raise RuleError(
            "dmn_declares_a_doctype",
            "this document declares a DOCTYPE, which is refused",
            "remove it and export again. A DOCTYPE is how external entities "
            "and entity-expansion attacks arrive, a decision table has no use "
            "for one, and refusing the whole construct is a control somebody "
            "cannot accidentally configure away")
    try:
        # Safe by the two checks above: no DOCTYPE reaches the parser, so
        # neither external entities nor expansion are reachable, and the size
        # is bounded. Stated here rather than suppressed silently.
        return ElementTree.fromstring(text)      # noqa: S314
    except ElementTree.ParseError as exc:
        logger.warning("DMN document is not well-formed XML: %s", exc)
        raise RuleError(
            "unreadable_dmn", f"this is not well-formed XML: {exc}",
            "export the decision again. A malformed export is a job to fix "
            "where it was produced rather than something to guess at "
            "here") from exc


def _first(node: Any, tag: str) -> Any:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] == tag:
            return child
    return None


def _all(node: Any, tag: str) -> List[Any]:
    return [c for c in node if c.tag.rsplit("}", 1)[-1] == tag]


def _label(node: Any) -> str:
    """The field an input or output column is about.

    DMN puts the expression in a nested `<text>` rather than on the element,
    and reading the element's own text yields the whitespace between tags —
    which is empty, so the fallback to `id` fired and every imported rule
    tested a field called `i1`. That produces a rule set which parses, loads
    and tests nothing, which is exactly the class of silent wrongness this
    module is built to avoid.
    """
    expression = _first(node, "inputExpression")
    if expression is not None:
        text = (_text(expression) or expression.text or "").strip()
        if text:
            return _safe_id(text)
    return _safe_id(node.get("label") or node.get("name")
                    or node.get("typeRef") or node.get("id") or "field")


def _text(node: Any, tag: str = "text") -> str:
    found = _first(node, tag)
    return (found.text or "") if found is not None else ""
