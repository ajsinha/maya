"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The QA case list, and the two claims that make its size mean anything.

Three thousand cases is a pile until somebody can say **what is not in it**. A
hand-written test plan misses routes invisibly — there is no way to look at one
and see the endpoint nobody thought of — so the backbone is generated from
`openapi.lock.json`, `routes/base.py` and the navbar, and this asserts the
assembled document still covers the system **as it is now** rather than as it
was on the day somebody ran the generator.

That distinction is the whole point. A case list that stops covering the system
the moment a route is added is worse than a short one, because its size argues
for a completeness it no longer has.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tools.qa import verify
from tools.qa.enumerate import build, screens

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSEMBLED = ROOT / "docs" / "QA" / "QA-CASES.md"


@pytest.fixture(scope="module")
def document() -> str:
    assert ASSEMBLED.is_file(), "run: python -m tools.qa.verify"
    return ASSEMBLED.read_text(encoding="utf-8")


class TestTheListCoversTheSystemAsItIsNow:
    def test_every_operation_and_every_refusal_is_named(self, document):
        """Re-derived from the source, not from the generator's own output —
        so adding a route or a refusal code fails this until a case exists."""
        problems = verify.check(document)
        assert not problems, "\n    ".join(problems)

    def test_the_assembled_file_is_current(self, document):
        """The committed document must match what the tools produce. A stale
        one is a plan for a system that has moved."""
        assert verify.assemble() == document, (
            "docs/QA/QA-CASES.md is out of date; run "
            "`python -m tools.qa.verify`")


class TestTheIdentifiersAreUsable:
    def test_no_case_id_means_two_things(self, document):
        """Four authors wrote in parallel. Truncating an area name to twelve
        characters collided `classification` with `classifications`."""
        ids = re.findall(r"^\|\s*(QA-[A-Z0-9-]+)\s*\|", document, re.M)
        duplicates = {i for i in ids if ids.count(i) > 1}
        assert not duplicates, f"duplicate ids: {sorted(duplicates)[:10]}"

    def test_every_id_is_matchable(self, document):
        """A UI area is `ui:dashboard`, and the colon went into the id — which
        made 109 cases invisible to the regex that counts them, and looked like
        missing cases rather than malformed ones."""
        loose = re.findall(r"^\|\s*(QA-[^|]+?)\s*\|", document, re.M)
        strict = set(re.findall(r"^\|\s*(QA-[A-Z0-9-]+)\s*\|", document, re.M))
        odd = sorted({i for i in loose if i not in strict
                      and not re.search(r"\d\s*[–-]\s*\d", i)})
        assert not odd, f"ids no tool can match: {odd[:10]}"


class TestTheListIsWorthItsSize:
    def test_it_is_large_enough_to_be_the_whole_system(self, document):
        ids = re.findall(r"^\|\s*(QA-[A-Z0-9-]+)\s*\|", document, re.M)
        assert len(ids) > 3000, f"only {len(ids)} cases"

    def test_every_case_states_an_expectation_before_it_runs(self, document):
        """The rule is that an expectation exists before the run, not that it
        uses four words.

        A first version of this demanded `accepted`, `refused` or `reported`
        and failed on ten cases — every one of them an author writing something
        better, like *"expected a positive count; suspect 0"* or *"documented
        as skipped; the code path raises"*. Those are the cases most likely to
        find a defect, because somebody read the code and predicted the
        disagreement. Forcing them into a vocabulary would have thrown away the
        prediction, so the check is that the column is filled in.
        """
        rows = [r for r in document.splitlines()
                if re.match(r"^\|\s*QA-[A-Z0-9-]+\s*\|", r)]
        empty = [r.split("|")[1].strip() for r in rows
                 if len(r.split("|")) > 4 and len(r.split("|")[4].strip()) < 8]
        assert not empty, f"cases with no expectation: {empty[:10]}"

    def test_most_cases_use_the_shared_vocabulary(self, document):
        """A prose expectation is fine; a list of them is a list nobody can
        aggregate. The canonical three have to be the norm."""
        rows = [r for r in document.splitlines()
                if re.match(r"^\|\s*QA-[A-Z0-9-]+\s*\|", r)]
        canonical = [r for r in rows
                     if re.search(r"accepted|refused|reported|EXPLORATORY",
                                  r, re.I)]
        assert len(canonical) / len(rows) > 0.95, (
            f"only {len(canonical)}/{len(rows)} cases use "
            f"accepted/refused/reported")

    def test_the_generated_backbone_still_generates(self):
        sections = build()
        assert sum(len(v) for v in sections.values()) > 1600
        assert len(screens()) > 40, (
            "the navbar parse found almost nothing; it has silently returned "
            "zero before, and a generator that finds nothing looks exactly "
            "like a system with nothing in it")
