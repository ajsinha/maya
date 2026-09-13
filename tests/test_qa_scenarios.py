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
CASES = ROOT / "docs" / "QA" / "QA-CASES.md"

#: Below this, something has been dropped rather than added. Raise it when
#: a batch lands; never lower it to make a failure go away.
AT_LEAST = 230


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
    return set(re.findall(r"^\|\s*(QA-[A-Z0-9-]+)\s*\|",
                          CASES.read_text(encoding="utf-8"), re.M))


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
        stray = sorted(set(registered) - published)
        assert not stray, (
            f"these scenarios answer ids that are not in docs/QA/QA-CASES.md: "
            f"{stray[:10]}")

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
