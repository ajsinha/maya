"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The reference EUC scanner, and the sweep it hands over.

This was the last item in the roadmap's reach section, and it is the one that
had to be built **outside** the platform. A sweep needs read access to every
shared drive, notebook server and repository in the institution — the broadest
standing access anybody holds — and granting it to the governance register would
hand the system whose whole argument is that it holds no standing power the
largest standing power in the building. So the crawl runs where the data is, and
`tools/scanner/` is a worked reference a firm can run, read, or replace.

Two properties matter more than what it finds.

**It shares no code with the register it reports to.** A scanner that imported
`core/` would have findings that are partly the register's own opinion, and the
precision figure the register computes would then be grading itself. Asserted on
the imports.

**What it drops is counted.** Every discovery programme that fails does so the
same way — the sweep runs, nobody can face four thousand findings, and next
month the same four thousand come back — and the quiet version of that failure
is a scanner that silently skips the files it found hard. Unreadable files, files
over the size limit and matches below the floor are all reported, because the
register cannot see what it was not sent.
"""
from __future__ import annotations

import ast
import json
import pathlib
import zipfile

import pytest

from core.discovery.contract import CERTAINTY, ScannerContract
from tools.scanner import sweep as scanner

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def estate(tmp_path):
    """A small share with the shapes a real one has."""
    (tmp_path / "finance").mkdir()
    (tmp_path / "finance" / "provision.py").write_text(
        "import statsmodels.api as sm\n"
        "model = sm.OLS(y, X).fit()\n"
        "pd_12m = model.predict(new)\n")
    (tmp_path / "finance" / "readme.txt").write_text("nothing here")
    (tmp_path / "risk").mkdir()
    (tmp_path / "risk" / "notes.ipynb").write_text(json.dumps({
        "cells": [{"cell_type": "code",
                   "source": ["from sklearn.linear_model import "
                              "LogisticRegression\n", "clf.fit(X, y)\n"],
                   "outputs": []}]}))
    # A sheet that fits something.
    _workbook(tmp_path / "risk" / "limits.xlsx",
              "<f>LINEST(B2:B99,A2:A99)</f><f>VLOOKUP(A2,Grid,3)</f>")
    # A sheet that only looks things up: a real candidate, but a weaker one.
    _workbook(tmp_path / "risk" / "lookup.xlsx", "<f>VLOOKUP(A2,Rates,2)</f>")
    # Something nothing should descend into.
    (tmp_path / "risk" / "node_modules").mkdir()
    (tmp_path / "risk" / "node_modules" / "x.py").write_text(
        "import sklearn\nm.fit(a,b)\n")
    return tmp_path


def _workbook(path, formulas):
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("xl/worksheets/sheet1.xml",
                      f"<worksheet>{formulas}</worksheet>")


class TestItRunsOutsideThePlatform:
    def test_it_imports_nothing_from_core(self):
        """A scanner sharing code with the register would have findings that
        are partly the register's own opinion, and the precision figure the
        register computes would be grading itself."""
        tree = ast.parse((ROOT / "tools" / "scanner" / "sweep.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("core", "db",
                                                           "routes"))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(("core", "db", "routes"))

    def test_it_needs_nothing_installed(self):
        """It is meant to run on a file server inside a bank's perimeter. A
        scanner that needs a package install first is one nobody runs."""
        tree = ast.parse((ROOT / "tools" / "scanner" / "sweep.py").read_text())
        third_party = {"pandas", "openpyxl", "requests", "numpy", "httpx"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in third_party


class TestWhatItFinds:
    def test_it_finds_a_fit_in_a_script(self, estate):
        out = scanner.sweep([estate], scope="finance and risk")
        locations = [c["location"] for c in out["candidates"]]
        assert any("provision.py" in loc for loc in locations)

    def test_it_reads_a_notebooks_source(self, estate):
        out = scanner.sweep([estate])
        assert any("notes.ipynb" in c["location"] for c in out["candidates"])

    def test_it_reads_formulas_out_of_a_workbook_without_a_dependency(
            self, estate):
        out = scanner.sweep([estate])
        sheet = [c for c in out["candidates"] if "limits.xlsx" in c["location"]]
        assert sheet, "the workbook's formulas were not read"
        signals = {s["signal"] for s in sheet[0]["evidence"]["signals"]}
        assert "regression" in signals

    def test_a_fit_outranks_a_lookup(self, estate):
        """The confidence is a triage ORDER, and this is what it has to get
        right: somebody working down the queue should reach the sheet that
        estimated parameters before the one that reads a rate table."""
        out = scanner.sweep([estate])
        by_name = {pathlib.Path(c["location"]).name: c["confidence"]
                   for c in out["candidates"]}
        assert by_name["limits.xlsx"] > by_name.get("lookup.xlsx", 0)

    def test_plain_text_is_not_a_candidate(self, estate):
        out = scanner.sweep([estate])
        assert not any("readme.txt" in c["location"]
                       for c in out["candidates"])

    def test_it_does_not_descend_into_vendored_directories(self, estate):
        out = scanner.sweep([estate])
        assert not any("node_modules" in c["location"]
                       for c in out["candidates"])

    def test_a_notebooks_outputs_are_not_evidence(self, tmp_path):
        """A printed dataframe full of the word `coefficient` is not evidence
        that the notebook fits anything, and including outputs is how a scanner
        reaches thirty percent precision."""
        (tmp_path / "n.ipynb").write_text(json.dumps({"cells": [{
            "cell_type": "code", "source": ["print(df)\n"],
            "outputs": [{"text": ["coefficient beta_ intercept sklearn "
                                  "model.fit(X,y)"]}]}]}))
        assert scanner.sweep([tmp_path])["candidates"] == []


class TestWhatItRefusesToClaim:
    def test_confidence_is_strictly_below_certainty(self, estate):
        out = scanner.sweep([estate])
        assert all(c["confidence"] < CERTAINTY for c in out["candidates"])
        assert scanner.MAX_CONFIDENCE < CERTAINTY

    def test_recall_is_never_claimed(self, estate):
        """A scanner cannot know what it did not look at."""
        assert scanner.sweep([estate])["recall_known"] is False

    def test_it_proposes_euc_rather_than_model(self, estate):
        """Sending a spreadsheet into the model register puts a tier-4
        obligation set on something that needs an owner and a review date."""
        out = scanner.sweep([estate])
        assert {c["proposed_as"] for c in out["candidates"]} == {"euc"}

    def test_the_evidence_is_what_matched_not_a_score(self, estate):
        """A triager needs to see `LINEST(` and where it was. A scanner that
        reported only a score is one nobody can grade, because nobody can tell
        a true finding from a false one without opening the file anyway."""
        out = scanner.sweep([estate])
        sheet = next(c for c in out["candidates"]
                     if "limits.xlsx" in c["location"])
        matched = [s["matched"] for s in sheet["evidence"]["signals"]]
        assert any("LINEST" in m for m in matched)
        assert all(s["why"].strip() for s in sheet["evidence"]["signals"])


class TestWhatItDropsIsCounted:
    def test_a_file_it_cannot_read_is_reported_not_skipped(self, tmp_path):
        """A legacy .xls is a binary format this does not read, and a file
        nothing looked at is not a file with nothing in it."""
        (tmp_path / "old.xls").write_bytes(b"\xd0\xcf\x11\xe0legacy")
        out = scanner.sweep([tmp_path])
        assert out["coverage"]["unreadable"] == 1
        assert "could not be read" in out["detail"]

    def test_a_file_over_the_limit_is_counted(self, tmp_path):
        (tmp_path / "big.py").write_text("import sklearn\n" + "x" * 5000)
        out = scanner.sweep([tmp_path], max_bytes=100)
        assert out["coverage"]["too_large"] == 1
        assert "the easy half of the estate" in out["detail"]

    def test_the_floor_travels_with_the_sweep(self, estate):
        """A precision figure means something different at 0.4 than at 0.7,
        and the register cannot see what was dropped."""
        out = scanner.sweep([estate], floor=0.7)
        assert out["confidence_floor"] == 0.7
        assert out["coverage"]["below_floor"] >= 1
        assert "shortens the queue" in out["detail"]

    def test_duplicate_content_collapses_onto_one_candidate(self, tmp_path):
        """So a triager decides once. The same workbook in two folders is the
        same workbook."""
        for name in ("a", "b"):
            (tmp_path / name).mkdir()
            (tmp_path / name / "m.py").write_text("import sklearn\nm.fit(a,b)\n")
        out = scanner.sweep([tmp_path])
        assert len(out["candidates"]) == 1
        assert out["coverage"]["duplicates"] == 1
        assert out["candidates"][0]["evidence"]["also_at"]


class TestTheFingerprintOutlivesThePath:
    def test_moving_a_file_does_not_make_a_new_candidate(self, tmp_path):
        """Keying on the path means next month's sweep raises it again and the
        dismissal somebody recorded is lost — which is exactly how a discovery
        queue comes back the same size forever."""
        (tmp_path / "one").mkdir()
        (tmp_path / "one" / "m.py").write_text("import sklearn\nm.fit(a,b)\n")
        before = scanner.sweep([tmp_path])["candidates"][0]["fingerprint"]
        (tmp_path / "two").mkdir()
        (tmp_path / "one" / "m.py").rename(tmp_path / "two" / "renamed.py")
        after = scanner.sweep([tmp_path])["candidates"][0]["fingerprint"]
        assert before == after


class TestTheSweepMeetsTheContract:
    def test_a_real_sweep_is_admissible(self, estate):
        """The point of the whole exercise: what this produces is what the
        register asked for, checked by the register's own contract rather than
        by this test's opinion of it."""
        out = scanner.sweep([estate], scope="finance and risk, not archive")
        report = ScannerContract(None).check(out)
        assert report["admissible"] is True, report["problems"]

    def test_an_unstated_scope_still_satisfies_the_field_and_says_it_is_poor(
            self, estate):
        out = scanner.sweep([estate])
        assert ScannerContract(None).check(out)["admissible"] is True
        assert "Prefer --scope" in out["scope"]

    def test_it_ingests_into_a_real_register(self, db, registry, evidence,
                                             estate):
        from core.discovery.register import DiscoveryRegister
        from db import DiscoveryRepository
        register = DiscoveryRegister(DiscoveryRepository(db), registry,
                                     evidence)
        out = scanner.sweep([estate], scope="a test estate")
        result = ScannerContract(register).ingest(out, actor="scanner")
        assert len(result["added"]) >= 1
        assert result["scanner"] == "euc-sweep"

    def test_a_second_sweep_does_not_duplicate_the_queue(
            self, db, registry, evidence, estate):
        """The property that decides whether a monthly sweep is useful or is
        four thousand findings again."""
        from core.discovery.register import DiscoveryRegister
        from db import DiscoveryRepository
        register = DiscoveryRegister(DiscoveryRepository(db), registry,
                                     evidence)
        contract = ScannerContract(register)
        out = scanner.sweep([estate], scope="a test estate")
        first = contract.ingest(out, actor="scanner")
        again = contract.ingest(scanner.sweep([estate], scope="a test estate"),
                                actor="scanner")
        assert len(first["added"]) >= 1
        # The same content, found again, is the same candidate. Nothing new.
        assert again["added"] == []
        assert again["seen_again"] == len(first["added"])


class TestSubmitting:
    def test_a_non_http_target_is_refused(self):
        """`--submit file:///etc/passwd` would otherwise make this read a local
        file and call it a register — a small hole in a program whose whole job
        is reading files it was pointed at by a cron line somebody wrote a year
        ago."""
        with pytest.raises(SystemExit) as e:
            scanner.submit({}, "file:///etc/passwd")
        assert "http(s) URL" in str(e.value)

    def test_an_unreachable_register_is_not_a_refusal(self):
        with pytest.raises(SystemExit) as e:
            scanner.submit({}, "http://127.0.0.1:1", timeout=1.0)
        assert "this is not a refusal" in str(e.value)


class TestTheCommandLine:
    def test_it_writes_a_document(self, estate, tmp_path, capsys):
        out = tmp_path / "sweep.json"
        assert scanner.main([str(estate), "--out", str(out),
                             "--scope", "a test estate"]) == 0
        document = json.loads(out.read_text())
        assert document["scanner"] == "euc-sweep"
        assert ScannerContract(None).check(document)["admissible"] is True

    def test_the_floor_is_settable(self, estate, tmp_path):
        out = tmp_path / "s.json"
        scanner.main([str(estate), "--out", str(out), "--floor", "0.85"])
        assert json.loads(out.read_text())["confidence_floor"] == 0.85
