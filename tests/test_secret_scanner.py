"""
MAYA — the secret scanner, which must actually scan.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

This file exists because the scanner shipped with

    if any(part in SKIP_DIRS or relative.startswith(part) for part in SKIP_DIRS)

which asks whether each member of a set is in that set — True for every file.
It reported "no secrets found in 551 tracked files" having read none of them: a
control reporting success while doing nothing, inside the tool written to catch
a different one. It was caught by planting a private key and watching it pass,
which is the only way that class of defect is ever caught.
"""

import pytest

from tools.ci.scan_secrets import PATTERNS, scan


class TestItFindsWhatItIsFor:
    @pytest.mark.parametrize("line,name", [
        ("-----BEGIN RSA PRIVATE KEY-----", "private key"),
        ("key = 'AKIAIOSFODNN7EXAMPLE'", "aws access key"),
        ("token = 'ghp_" + "a" * 36 + "'", "github token"),
        ("db = 'postgresql://user:hunter2@db.internal/maya'", "credentials in a url"),
        ("t = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijkl'", "jwt"),
    ])
    def test_each_pattern_matches_its_own_example(self, line, name):
        matched = [n for n, _what, pattern in PATTERNS if pattern.search(line)]
        assert name in matched, f"{name} did not match its own example"

    def test_it_reads_the_files_rather_than_skipping_all_of_them(self, tmp_path,
                                                                 monkeypatch):
        """The specific defect. A planted key must be found."""
        import tools.ci.scan_secrets as scanner

        planted = tmp_path / "core" / "leaked.py"
        planted.parent.mkdir(parents=True)
        planted.write_text("KEY = '-----BEGIN RSA PRIVATE KEY-----'\n")
        monkeypatch.setattr(scanner, "ROOT", tmp_path)
        monkeypatch.setattr(scanner, "tracked", lambda: [planted])

        hits = scanner.scan()
        assert hits and "leaked.py" in hits[0]

    def test_a_skipped_directory_is_still_skipped(self, tmp_path, monkeypatch):
        """The fix must not have removed the skipping along with the bug."""
        import tools.ci.scan_secrets as scanner

        vendored = tmp_path / "web" / "static" / "vendor" / "lib.js"
        vendored.parent.mkdir(parents=True)
        vendored.write_text("var k = '-----BEGIN RSA PRIVATE KEY-----';\n")
        monkeypatch.setattr(scanner, "ROOT", tmp_path)
        monkeypatch.setattr(scanner, "tracked", lambda: [vendored])
        assert scanner.scan() == []


class TestTheRepositoryIsClean:
    def test_nothing_is_committed_that_should_not_be(self):
        """Run against the real tree, so this is the gate and not a rehearsal."""
        assert scan() == []
