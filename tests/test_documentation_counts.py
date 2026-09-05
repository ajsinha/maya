"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The numbers in the prose, checked against the code.

A documentation review found roughly sixty false checkable claims, and the
pattern in almost all of them was the same: **a count written once and never
recounted.** Forty tables when there were forty-two. Seventeen runtimes when
there were eighteen. Five scheduler jobs when there were seven. Sixty-four
permissions when there were seventy. Thirty help topics when there were fifteen.

None of those was anybody deciding to mislead. Each was true when it was
written, and each stayed in the file while the code moved. That is exactly the
class of drift a test can hold, so this holds it: the count comes from the code,
and the documents are searched for any *other* number claimed against the same
subject.

It deliberately does not check prose. A sentence that describes a behaviour has
to be read by somebody. A number does not.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

WORDS = {21: "twenty-one",
         1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
         7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
         12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
         16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
         20: "twenty"}


def _truth():
    """Every count, taken from the code rather than from a document."""
    from core.authz.common import PERMISSIONS
    from core.authz.roles import ROLES
    from core.execution.grammar.vocabulary import BINDINGS, RUNTIMES, VERBS

    schema = (ROOT / "db" / "schema" / "sqlite.sql").read_text(encoding="utf-8")
    # The laws that actually run, counted from the table that states them. The
    # strongest claim the design makes is that the laws are the acceptance
    # criteria, and "thirteen of nineteen" is exactly the kind of number that is
    # true when written and quietly false a milestone later.
    foundations = (ROOT / "docs" / "00-mathematical-foundations.md").read_text(
        encoding="utf-8")
    law_rows = re.findall(r"^\| \*\*L-\d+\*\* \| .*?\| .*?\| (.*?) \|$",
                          foundations, re.M)
    return {
        "executable laws": sum(1 for state in law_rows
                               if "Executable" in state or "Enforcing" in state),
        "foundational laws": len(law_rows),
        "tables": len(re.findall(r"CREATE TABLE IF NOT EXISTS", schema)),
        "runtimes": len(RUNTIMES),
        "verbs": len(VERBS),
        "bindings": len(BINDINGS),
        "permissions": len(PERMISSIONS),
        "roles": len(ROLES),
        "help topics": len(list((ROOT / "content" / "help").glob("*.md"))),
        "ADRs": len(list((ROOT / "docs" / "adr").glob("ADR-*.md"))),
        "warrant examples": len(list((ROOT / "examples" / "warrants").glob("*.json"))),
    }


# The phrase each count appears in, as a regex with the number as group 1. Kept
# narrow on purpose: a loose pattern would match unrelated numbers and the test
# would be abandoned rather than believed.
CLAIMS = {
    "tables": [r"(\d+) tables, no migrations", r"two hand-written schemas, (\d+) tables"],
    # Narrow deliberately. `one of the (\w+)` matched "one of the three" in
    # unrelated prose, and a check that cries wolf is a check that gets deleted.
    "runtimes": [r"\*\*(\w+) runtimes\*\*", r"grammar's (\w+) runtimes",
                 r"(\w+) runtimes the grammar", r"realised \((\d+) runtimes\)",
                 r"`descriptor_only` is one of the (\w+)"],
    "permissions": [r"of \*\*(\d+) permissions\*\*"],
    "help topics": [r"(\d+) help topics"],
    "warrant examples": [r"(\w+) worked examples in `examples/warrants/`"],
    # Counted from the table itself, so the prose around it cannot drift from
    # the rows. This is the claim a reader is most likely to take on trust.
    "executable laws": [r"(\w+) of the twenty-one foundational laws are executable",
                        r"\*\*(\w+) of the twenty-one\*\* foundational laws are executable"],
    # The word immediately before "foundational laws" is the total. Written this
    # narrowly because the looser form captured "Thirteen" out of "thirteen of
    # the nineteen foundational laws" and reported the executable count as the
    # total — a check that cries wolf is a check that gets deleted.
    "foundational laws": [r"of the ([\w-]+) foundational laws"],
}

DOCUMENTS = (list((ROOT / "docs").glob("*.md"))
             + list((ROOT / "docs" / "adr").glob("*.md"))
             + list((ROOT / "content" / "help").glob("*.md"))
             + [ROOT / "README.md", ROOT / "config" / "application.yaml"])


def _as_number(token: str):
    if token.isdigit():
        return int(token)
    for value, word in WORDS.items():
        if word == token.lower():
            return value
    return None


@pytest.mark.parametrize("subject", sorted(CLAIMS))
def test_every_stated_count_matches_the_code(subject):
    actual = _truth()[subject]
    wrong = []
    for path in DOCUMENTS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            for pattern in CLAIMS[subject]:
                for token in re.findall(pattern, line):
                    claimed = _as_number(token)
                    if claimed is not None and claimed != actual:
                        wrong.append(
                            f"{path.relative_to(ROOT)}:{line_number} claims "
                            f"{claimed} {subject}, code has {actual}")
    assert not wrong, (
        f"these documents state a count that the code contradicts:\n    "
        + "\n    ".join(wrong)
        + "\nRecount from the code; do not adjust the code to the prose.")


def test_the_truth_table_is_reachable():
    """A guard on the guard: if a symbol moves, this fails loudly rather than
    letting every count check pass against an empty dictionary."""
    counts = _truth()
    assert set(counts) >= set(CLAIMS)
    assert all(v > 0 for v in counts.values()), counts
