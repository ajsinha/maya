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

WORDS = {21: "twenty-one", 114: "a hundred and fourteen",
         1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
         7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
         12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
         16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
         20: "twenty"}


def _typechecked():
    """(gated, backlog), from the same two functions the CI gate uses.

    Imported rather than reimplemented: a second enumeration of "which modules
    are type-checked" is a second answer, and this file exists because second
    answers drift.
    """
    import sys

    sys.path.insert(0, str(ROOT))
    from tools.ci.typecheck import backlogged, modules

    excused = backlogged()
    return len([m for m in modules() if m not in excused]), len(excused)


def _truth():
    """Every count, taken from the code rather than from a document."""
    from core.authz.common import PERMISSIONS
    from core.authz.roles import ROLES
    from core.execution.grammar.vocabulary import BINDINGS, RUNTIMES, VERBS
    from core.lifecycle import STATES
    from core.scheduler.jobs import JOBS

    schema = (ROOT / "db" / "schema" / "sqlite.sql").read_text(encoding="utf-8")
    # The laws that actually run, counted from the table that states them. The
    # strongest claim the design makes is that the laws are the acceptance
    # criteria, and "thirteen of nineteen" is exactly the kind of number that is
    # true when written and quietly false a milestone later.
    foundations = (ROOT / "docs" / "00-mathematical-foundations.md").read_text(
        encoding="utf-8")
    law_rows = re.findall(r"^\| \*\*L-\d+\*\* \| .*?\| .*?\| (.*?) \|$",
                          foundations, re.M)
    # Mutating endpoints. Claimed as "ninety" in two places and checked by
    # nobody; it was a hundred and four. The CSRF argument rests on the number
    # being large, so it is worth being right about.
    routes_src = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted((ROOT / "routes").glob("*.py")))
    mutating = len(re.findall(r"self\.app\.(?:post|put|delete|patch)\(",
                              routes_src))
    # The case studies, counted from the directories rather than from any
    # sentence about them. The suite README, the deck, the article and the
    # LaTeX paper all state this number, and the paper's argument leans on it:
    # "N demonstrations by the person who built the thing" is the objection it
    # answers, so the count and the number NOT designed to fit both matter.
    studies = sorted(d for d in (ROOT / "case_studies").iterdir()
                     if d.is_dir() and re.match(r"^\d\d_", d.name))
    return {
        "case studies": len(studies),
        "mutating endpoints": mutating,
        "executable laws": sum(1 for state in law_rows
                               if "Executable" in state or "Enforcing" in state),
        "foundational laws": len(law_rows),
        # Anchored at the start of a line. Unanchored, this matched the phrase
        # inside the schema's own header COMMENT and reported forty-seven tables
        # where there are forty-six — so the test whose entire job is to stop a
        # count drifting was itself the source of a wrong count, in every
        # document that trusted it.
        "tables": len(re.findall(r"^CREATE TABLE IF NOT EXISTS", schema, re.M)),
        # Collected rather than run. A count derived by executing the suite
        # would make this test take as long as the suite; collection is the
        # cheap half and is what the claimed number means anyway.
        "tests": _collected_tests(),
        "runtimes": len(RUNTIMES),
        # Drifted quietly: the docs said seven jobs against eight, and six
        # lifecycle states against seven — and `baselined` is the state that
        # matters most, since it exists so an imported model never looks like
        # one somebody asserted.
        "scheduler jobs": len(JOBS),
        "lifecycle states": len(STATES),
        "verbs": len(VERBS),
        "bindings": len(BINDINGS),
        "permissions": len(PERMISSIONS),
        "roles": len(ROLES),
        "help topics": len(list((ROOT / "content" / "help").glob("*.md"))),
        "ADRs": len(list((ROOT / "docs" / "adr").glob("ADR-*.md"))),
        "warrant examples": len(list((ROOT / "examples" / "warrants").glob("*.json"))),
        # The complement of the executable count, because the sentence that
        # carries one almost always carries the other and they drifted together.
        "inert laws": len(law_rows) - sum(1 for state in law_rows
                                          if "Executable" in state
                                          or "Enforcing" in state),
        # `L-W0` through `L-W13`. Stated as eleven in one ADR and fourteen in
        # five other places, which is how a reader learns to check nothing.
        # `typecheck.py` gates on these and carries the rest in a backlog file.
        # Both numbers appear in two documents each and both had drifted.
        "gated modules": _typechecked()[0],
        "backlog modules": _typechecked()[1],
        "total modules": sum(_typechecked()),
        "warrant laws": len({name for name in re.findall(
            r"L-W(\d+)", "\n".join(
                p.read_text(encoding="utf-8")
                for p in sorted((ROOT / "core").rglob("*.py"))))}),
    }


# The phrase each count appears in, as a regex with the number as group 1. Kept
# narrow on purpose: a loose pattern would match unrelated numbers and the test
# would be abandoned rather than believed.
CLAIMS = {
    # Three patterns, and the third was added after the README sat on "51
    # tables" for several milestones while the schema grew past eighty. The
    # first two require the number and the phrase "no migrations" to be
    # adjacent; the README put eight words between them. A pattern narrow
    # enough to need adjacency is a pattern that misses the sentence somebody
    # actually wrote.
    "tables": [r"(\d+) tables, no migrations",
               r"two hand-written schemas, (\d+) tables",
               r"\*\*(\d+) tables\*\*"],
    # Narrow deliberately. `one of the (\w+)` matched "one of the three" in
    # unrelated prose, and a check that cries wolf is a check that gets deleted.
    "runtimes": [r"\*\*(\w+) runtimes\*\*", r"grammar's (\w+) runtimes",
                 r"(\w+) runtimes the grammar", r"realised \((\d+) runtimes\)",
                 r"`descriptor_only` is one of the (\w+)",
                 # Both source docstrings said "seventeen" against eighteen
                 # entries, and survived because this test read documents only.
                 r"grammar names (\w+)"],
    "permissions": [r"of \*\*(\d+) permissions\*\*"],
    # The README's own status table, which is the number most readers see
    # first and the one that had drifted furthest — "over 2,300 passing"
    # against a suite of five and a half thousand. `over` and `more than` both,
    # because the phrase moved between them at some point.
    "tests": [r"\*\*over ([\d,]+) passing\*\*",
              r"\*\*[Oo]ver ([\d,]+) tests\*\*",
              r"more than ([\d,]+) tests"],
    "help topics": [r"(\d+) help topics"],
    # Spelled out in every document that mentions them, so the words are
    # matched rather than digits. `_as_number` already reads both.
    "case studies": [r"\*\*chapter 26: the (\w+) case studies\*\*",
                     r"^(\w+) worked models, each registered",
                     r"(\w+) worked examples by the same person",
                     r"the objection above applies to the worked examples as "
                     r"much as to the modules: (\w+) demonstrations"],
    "warrant examples": [r"(\w+) worked examples in `examples/warrants/`"],
    # Counted from the table itself, so the prose around it cannot drift from
    # the rows. This is the claim a reader is most likely to take on trust.
    # Two patterns were not enough, and the gap was not subtle: this pair
    # matched neither "Sixteen of twenty-one run", nor "Sixteen execute. Five
    # do not", nor "sixteen of the twenty-one stated laws execute", nor the six
    # other spellings the same claim had acquired across the documents, the
    # research paper and two decks. Every one of them said sixteen while the
    # table said eighteen — so the check that exists to stop THIS EXACT drift
    # passed, on the most-repeated number in the project, for two milestones.
    #
    # A narrow pattern is right when the risk is crying wolf. It is wrong when
    # the phrase varies and the number does not, which is what prose does.
    "executable laws": [
        r"(\w+) of the twenty-one foundational laws are executable",
        r"\*\*(\w+) of the twenty-one\*\* foundational laws are executable",
        r"(\w+) of (?:the )?twenty-one(?: stated| foundational)?"
        r"(?: foundational)? laws?(?: run| execute)",
        r"(\w+) of twenty-one (?:foundational )?laws run",
        r"\*\*(\w+) execute\.",
        r"(\w+) execute; \w+ do not",
        r"(\w+) of twenty-one is the honest number",
        r"of which (\w+) are executable",
        r"(\w+) are executable and enforcing",
        # The paper's spellings. Every one of these was in the .tex while the
        # .tex was unread.
        r"(\w+) of the twenty-one stated laws execute",
        r"implementation states twenty-one laws\. (\w+) execute",
        # And the README's, which said sixteen against eighteen and was read
        # by this test on every push without matching anything.
        r"\*\*(\w+) run in the test suite\*\*"],
    # The other half of the same sentence, and it drifted with it: five became
    # three when `L-14` and `L-17` started running, in the same documents.
    "inert laws": [r"\*\*\w+ execute\. (\w+) do not\*\*",
                   r"\w+ execute; (\w+) do not",
                   r"the (\w+) that do not are named",
                   r"twenty-one run; (\w+) do not",
                   # The paper's four spellings of the same fact, which
                   # disagreed with each other as well as with the code.
                   r"for (\w+) of the twenty-one laws",
                   r"while (\w+) are not, is the exact",
                   r"(\w+) of twenty-one laws do not execute",
                   r"(\w+) that do not run are named",
                   # A sixth spelling, in the article's closing footer, which
                   # said six while the article's own table said three.
                   r"laws with the (\w+) that don't execute",
                   # A seventh, mid-argument: "one of the five laws I list as
                   # not executable further down" — which also named the wrong
                   # law, since L-14 runs.
                   r"one of the (\w+) laws I list as not executable"],
    "warrant laws": [r"all (\w+) warrant[- ]admissibility laws",
                     r"(\w+) warrant laws"],
    "gated modules": [r"gates on(?: the)? (\d+) modules",
                      r"the (\d+) modules that (?:pass|check clean)"],
    "backlog modules": [r"carries (?:the other )?(\d+) in "],
    "total modules": [r"`--strict` across (\d+) modules",
                      r"adopting it across (\d+) modules"],
    # The word immediately before "foundational laws" is the total. Written this
    # narrowly because the looser form captured "Thirteen" out of "thirteen of
    # the nineteen foundational laws" and reported the executable count as the
    # total — a check that cries wolf is a check that gets deleted.
    "foundational laws": [r"of the ([\w-]+) foundational laws"],
    "mutating endpoints": [r"(\d+|a hundred and \w+) mutating endpoints"],
    "scheduler jobs": [r"(\w+) idempotent jobs", r"[Tt]he (\w+) jobs",
                       r"(\w+) scheduler jobs"],
    "lifecycle states": [r"(\w+)-state record machine",
                         r"(\w+) lifecycle states"],
}

# Source files are read too. `runtimes/base.py` and `runtimes/registry.py` each
# said "the grammar names seventeen" against eighteen entries, and both survived
# every pass of this test because it looked only at markdown — the count was
# wrong in the two files a reader would most trust, being the code's own account
# of itself. A docstring is documentation; there is no reason to exempt it.
DOCUMENTS = (list((ROOT / "docs").rglob("*.md"))
             + list((ROOT / "content").rglob("*.md"))
             # The LaTeX source of the research paper. It was NOT read for two
             # milestones, and the comment above this list claimed it was —
             # "across the documents, the research paper and two decks" — which
             # was true of the markdown article and false of the .tex, because
             # the glob is `*.md`.
             #
             # It is the document that then drifted, and it drifted on the one
             # number whose whole point is not drifting: the paper gave the
             # count of non-executing laws as five in its abstract, five in its
             # reading guide and six three lines later, while its own table and
             # tests/test_laws.py both said three. A paper arguing that a
             # document implying every law is checked, when some are not, is
             # THE failure the discipline prevents — and committing that failure
             # about itself.
             #
             # A reviewer read the paper closely enough to find eight other
             # things and did not find this. A glob would have.
             + list((ROOT / "docs" / "research").rglob("*.tex"))
             + [ROOT / "README.md", ROOT / "config" / "application.yaml"]
             + [p for d in ("core", "routes", "db", "sdk", "tools")
                for p in (ROOT / d).rglob("*.py")])


def _collected_tests() -> int:
    """How many tests there are, counted from the source.

    Counting `def test_` across `tests/` rather than asking pytest: invoking
    pytest from inside pytest is a recursion nobody wants, and a parametrised
    case is one test as a reader means it — the README says "over N", and over
    is true of either reading.
    """
    total = 0
    for path in (ROOT / "tests").rglob("test_*.py"):
        total += len(re.findall(r"^\s*def test_", path.read_text(), re.M))
    return total


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
        # Line by line, which is a real blind spot: a claim wrapped across two
        # lines — "a hundred and four\nmutating endpoints" — is invisible here,
        # and three of them survived a count change that way. Left line-based
        # because matching across a join would need the whole file normalised,
        # and a check that reports positions nobody can find is worse than one
        # with a stated gap. Grep for the bare number when a count changes.
        for line_number, line in enumerate(text.splitlines(), 1):
            for pattern in CLAIMS[subject]:
                # Case-insensitive. `docs/14 §17` opened with "A hundred and
                # four mutating endpoints" while §17.2 of the same file said a
                # hundred and fourteen, and this check missed the first because
                # the sentence began with a capital. A count guard that only
                # sees lower-case sentences guards the middles of sentences.
                for token in re.findall(pattern, line, re.I):
                    claimed = _as_number(token)
                    if claimed is not None and claimed != actual:
                        wrong.append(
                            f"{path.relative_to(ROOT)}:{line_number} claims "
                            f"{claimed} {subject}, code has {actual}")
    assert not wrong, (
        "these documents state a count that the code contradicts:\n    "
        + "\n    ".join(wrong)
        + "\nRecount from the code; do not adjust the code to the prose.")


def test_the_truth_table_is_reachable():
    """A guard on the guard: if a symbol moves, this fails loudly rather than
    letting every count check pass against an empty dictionary."""
    counts = _truth()
    assert set(counts) >= set(CLAIMS)
    assert all(v > 0 for v in counts.values()), counts


class TestThePaperAgreesWithTheTable:
    """The research paper states the same law census as `docs/00 §12`, in two
    forms — LaTeX and markdown — and both said *five do not run* for two
    milestones after `L-14` and `L-17` started running.

    Checked here rather than left to a reader, because the paper is the document
    most likely to be read by somebody who cannot check it against the code, and
    an inflated claim there costs more than the same claim anywhere else.
    """

    PAPER = ROOT / "docs" / "research" / "models-as-parametric-kernels.tex"
    ARTICLE = ROOT / "docs" / "research" / "models-as-parametric-kernels-article.md"

    def test_the_latex_table_marks_the_same_laws_as_not_built(self):
        rows = re.findall(r"\\textsf\{(L-\d+)\}\s*&[^&]*&\s*\\emph\{not built\}",
                          self.PAPER.read_text(encoding="utf-8"))
        assert set(rows) == {"L-6", "L-11", "L-13"}, rows

    def test_the_latex_table_states_every_law(self):
        rows = re.findall(r"\\textsf\{(L-\d+)\}\s*&", self.PAPER.read_text(
            encoding="utf-8"))
        assert len(set(rows)) == _truth()["foundational laws"], sorted(set(rows))

    def test_the_article_names_only_the_laws_that_do_not_run(self):
        """Its table is prose-titled rather than coded, so this counts rows."""
        body = self.ARTICLE.read_text(encoding="utf-8")
        block = body.split("| Law | Why it doesn't run |", 1)[1].split("\n\n", 1)[0]
        rows = [line for line in block.strip().splitlines()
                if line.startswith("|") and not line.startswith("|---")]
        assert len(rows) == _truth()["inert laws"], rows

    def test_neither_form_still_says_five(self):
        for path in (self.PAPER, self.ARTICLE):
            body = path.read_text(encoding="utf-8")
            for phrase in ("five that do not", "Five do not", "five do not run",
                           "lists it among the six"):
                assert phrase not in body, f"{path.name}: '{phrase}'"
