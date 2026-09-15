"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The QA scenarios are regression tests, so the suite guards them.

Every scenario in `qa/regression_suite/scenarios/` is an executable statement about a
control, written against a live instance, and most of them exist because
something was once wrong. They are worth more as a **regression suite** than
as a one-off pass, and a regression suite that can quietly stop running is
worse than none — it reports a clean bill of health for checks that were
never performed.

This does not run the scenarios (they need a live application and several
seconds each; `python -m qa.regression_suite.scenario_run` is how they run). It asserts
the things that would make a run silently cover less than it claims:

- every module still imports, so a rename does not drop a section
- every registered id is a **published** case, so results can be reported
  against the list a reader can open
- no id is registered twice, because the second registration silently wins
- the count does not fall

The last one is the blunt instrument, and it is here because every other
check in this file passes trivially when a module stops being imported.
"""
from __future__ import annotations

import importlib
import pathlib
import pkgutil
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASES = ROOT / "qa" / "QA-CASES.md"

#: Below this, something has been dropped rather than added. Raise it when
#: a batch lands; never lower it to make a failure go away.
AT_LEAST = 1799


@pytest.fixture(scope="module")
def registered():
    """Every scenario, by the case id it answers."""
    from qa.regression_suite.scenarios import common
    package = ROOT / "qa" / "regression_suite" / "scenarios"
    for info in pkgutil.iter_modules([str(package)]):
        if info.name not in ("common", "__init__"):
            importlib.import_module(f"qa.regression_suite.scenarios.{info.name}")
    return dict(common.REGISTRY)


@pytest.fixture(scope="module")
def published():
    """case id -> the subject the list states, which is columns two and three."""
    out = {}
    for match in re.finditer(
            r"^\|\s*(QA-[A-Z0-9-]+)\s*\|([^|]*)\|([^|]*)\|",
            CASES.read_text(encoding="utf-8"), re.M):
        out[match.group(1)] = f"{match.group(2).strip()} {match.group(3).strip()}"
    return out


@pytest.fixture(scope="module")
def subjects():
    """case id -> the whole published row, for checks that read the how."""
    out = {}
    for line in CASES.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*(QA-[A-Z0-9-]+)\s*\|", line)
        if match:
            out[match.group(1)] = line
    return out


#: Words carrying no subject. Without these, "with", "that" and "does" supply
#: the two-word overlap on their own and every pair looks related.
EMPTY = frozenset({
    "that", "this", "with", "from", "into", "when", "then", "does", "been",
    "have", "over", "under", "than", "what", "which", "only", "case", "test",
    "same", "more", "each", "both", "after", "before", "against", "every",
    "still", "there", "where", "while", "would", "could", "about", "cannot",
})


def _words(text: str) -> set:
    return set(re.findall(r"[a-z]{4,}", text.lower())) - EMPTY


def _says_the_same_thing(title: str, said: str) -> bool:
    """Do these two sentences have a subject in common?

    **`difflib.SequenceMatcher` was the whole check and it does not answer
    this question.** It compares CHARACTER runs, and two unrelated English
    sentences of similar length routinely score above the 0.35 the old rule
    accepted: "Two campaigns with the same reference" scored 0.44 against "A
    principal scoped to a domain the estate does not contain", so a
    recertification scenario sat on a scoping case and the list reported that
    case as covered. Twenty-six did.

    The question is about SUBJECT, so it is asked about content words. Two in
    common is enough — the two sentences are written by different hands and
    will not agree on phrasing — and the ratio is kept only as a second way
    through for the short titles where two shared words is a high bar.
    """
    import difflib
    mine, theirs = _words(title), _words(said)
    if len(mine & theirs) >= 2:
        return True
    if len(mine) <= 3 and mine & theirs:
        return True
    return difflib.SequenceMatcher(None, title.lower(), said.lower()).ratio() >= 0.60


#: Scenario/published pairs that describe one test in two vocabularies, with
#: the reason. A pair belongs here when a reader comparing them agrees they are
#: the same act — NOT when the check is inconvenient. Everything else is a
#: scenario that has to move.
AGREED = {
    "QA-AM-002",   # "the builder's name with the case flipped" / "validator
                   # named PERSON/D.Raman" — the list gives the value, the
                   # scenario gives the property.
    "QA-AM-076",   # "an unknown value" / "`banana`".
    "QA-AM-085",   # "to nobody" / "to an empty string".
    "QA-AM-186",   # "the expiry sweep" / "`waivers.expire`".
    "QA-AM-357",   # "could not compute" / "the indicator's service raised".
    "QA-AM-366",   # "under the slack threshold" / "under 25% utilisation".
    "QA-DEL-021",  # "names when and by whom" / "the date and the actor".
    "QA-DEL-027",  # "act on a tombstoned model" / "transition, attest or
                   # approve a tombstoned URN".
    "QA-DEL-057",  # "covers every table" / "compare against the schema".
    "QA-DEL-081",  # "needs storage:compact" / "as a non-administrator".
    "QA-FX-239",   # "the inline cap" / "4,096 values".
    "QA-FX-240",   # "past the cap, out of line" / "4,097 as a values_uri".
    "QA-FX-260",   # "one row below the minimum" / "29 rows, then 30".
    "QA-GOV-070",  # "a second attestation after a completed cycle" / "a model
                   # that already has one attested and closed".
    "QA-GOV-248",  # "the expiry sweep twice" / "`expire_due` twice".
    "QA-GOV-257",  # "answering their own row" / "whose own row is spelled
                   # differently answers it" — the spelling IS the point.
    "QA-PLT-028",  # "the store made unreadable" / "`data/worm/` read-only".
    "QA-PLT-177",  # "wildly different densities" / "a thousand occurrences
                   # and a hundred thousand".
    "QA-PLT-185",  # "use a suspended capability" / "suspend, use, unsuspend".
    "QA-PLT-242",  # "no body at all" / "`POST /scheduler/run` no body".
    "QA-PLT-310",  # "says what it checked" / "each named in the body".
    "QA-PLT-337",  # "an impossible lifetime" / "366 days and 0 days".
    "QA-PLT-395",  # "reachable from the address bar" / "keyboard-only, from
                   # the address bar to the primary action".
}


class TestTheScenariosAreStillThere:
    def test_every_module_imports(self, registered):
        assert registered, "no scenarios registered at all"

    def test_the_count_has_not_fallen(self, registered):
        assert len(registered) >= AT_LEAST, (
            f"{len(registered)} scenarios registered, expected at least "
            f"{AT_LEAST}. A regression suite that shrinks silently reports a "
            f"clean result for checks nobody ran")

    def test_every_section_is_represented(self, registered):
        """A dropped module takes a whole subsystem's regression with it, and
        every other assertion here would still pass."""
        prefixes = {cid.split("-")[1] for cid in registered}
        assert {"GOV", "FX", "AM", "PLT", "DEL"} <= prefixes, (
            f"only {sorted(prefixes)} are covered")


class TestTheIdentifiersAreReportable:
    def test_every_scenario_answers_a_published_case(self, registered,
                                                     published):
        """A scenario against an id nobody published cannot be reported as
        coverage of the case list — it would be a percentage of a numbering
        only the runner uses."""
        stray = sorted(set(registered) - set(published))
        assert not stray, (
            f"these scenarios answer ids that are not in qa/QA-CASES.md: "
            f"{stray[:10]}")

    def test_every_scenario_tests_what_its_case_says(self, registered,
                                                     published):
        """The id must mean the same thing in both places.

        Existence was checked and MEANING was not, and 138 of 291 scenarios
        were answering a published id about something else: a telemetry
        scenario registered as `QA-AM-400`, which the list publishes as a
        cold-start baseline case. The results file then reported those
        published cases as passed, and what had run was a different test
        entirely.

        That is precisely the defect this whole pass keeps finding — a check
        that passes for a reason other than its name — arriving in the tool
        built to find it. Existence is the cheap half of the question.
        """
        adrift = []
        for case_id, (title, _fn) in sorted(registered.items()):
            said = published.get(case_id, "")
            if case_id in AGREED:
                continue
            if not _says_the_same_thing(title, said):
                adrift.append(f"{case_id}: scenario says {title!r}, the list "
                              f"says {said[:60]!r}")
        assert not adrift, (
            "these scenarios answer a published id whose subject is "
            "different, so a result would be credited to a case about "
            f"something else ({len(adrift)} of them):\n    "
            + "\n    ".join(adrift[:12]))

    def test_every_published_case_that_claims_a_scenario_has_one(
            self, registered, subjects):
        """The other direction, and it had never been checked.

        A published row saying **reported by the suite** and naming a runner
        command is a claim that running that command produces a verdict. For
        114 rows it produced `no cases match`, and the list reported them as
        covered anyway — the QA pack's own version of the defect it exists to
        find. The rows were left behind when scenarios were re-pointed to
        correct ids; nothing looked the other way down the link.
        """
        unrun = sorted(cid for cid, row in subjects.items()
                       if "scenario_run" in row and cid not in registered)
        assert not unrun, (
            f"{len(unrun)} published case(s) say the suite reports them and "
            f"no scenario answers the id, so `--only <id>` matches nothing: "
            f"{unrun[:12]}")

    def test_no_case_is_registered_twice(self):
        """`REGISTRY[id] = ...` — the second registration wins and the first
        scenario simply never runs, with nothing said about it."""
        package = ROOT / "qa" / "regression_suite" / "scenarios"
        seen: dict = {}
        duplicates = []
        for path in sorted(package.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for cid in re.findall(r'@?case\(\s*"(QA-[A-Z0-9-]+)"', text):
                if cid in seen and seen[cid] != path.name:
                    duplicates.append(f"{cid} in {seen[cid]} and {path.name}")
                seen[cid] = path.name
        assert not duplicates, duplicates


class TestTheHarnessStillRefusesToLie:
    def test_it_signs_in_through_the_form(self):
        """Authenticating only with HTTP Basic made every screen answer 200
        with the sign-in page, and eighty-four screen cases passed without
        being opened."""
        source = (ROOT / "qa" / "regression_suite" / "harness.py").read_text(
            encoding="utf-8")
        assert "def sign_in" in source and "/login" in source

    def test_the_observer_has_its_own_client(self):
        """Passing credentials on the signed-in client leaves the admin
        session cookie attached, so every "refused without the permission"
        case was made as an administrator."""
        source = (ROOT / "qa" / "regression_suite" / "harness.py").read_text(
            encoding="utf-8")
        assert source.count("TestClient(app") >= 3

    def test_a_500_is_recorded_rather_than_raised(self):
        """`raise_server_exceptions=False`, or the first unhandled error ends
        the pass and nothing is reported about anything after it."""
        source = (ROOT / "qa" / "regression_suite" / "harness.py").read_text(
            encoding="utf-8")
        assert "raise_server_exceptions=False" in source
