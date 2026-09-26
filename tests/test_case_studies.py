"""
Every case study runs, end to end, from nothing.

A case study is a demonstration somebody will give in front of people, so one that has
rotted is worse than none. Each is run here as a reader would run it -- ``run.py``, in its
own process -- against its own throwaway estate (``--storage.root`` and ``--lake.root`` in a
temporary directory), so the studies cannot see each other or the project's own ``data/``.

They take a minute or two, so they run when ``MAYA_TEST_CASE_STUDIES=1`` is set, which
``python tools/ci/gates.py --tests`` does, and whenever a study is being changed:

    MAYA_TEST_CASE_STUDIES=1 python -m pytest tests/test_case_studies.py -n 4

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUDIES = sorted(p.parent.name for p in (ROOT / "case_studies").glob("[0-9]*/run.py"))


@pytest.mark.skipif(
    os.environ.get("MAYA_TEST_CASE_STUDIES") != "1",
    reason="set MAYA_TEST_CASE_STUDIES=1 to run every case study (gates.py --tests does)",
)
@pytest.mark.parametrize("study", STUDIES)
def test_the_case_study_runs_from_nothing(study, tmp_path):
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "case_studies" / study / "run.py"),
            "--quiet",
            f"--storage.root={tmp_path}",
            f"--lake.root={tmp_path}/lake",
        ],
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT)),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert r.returncode == 0, f"{study} failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}"
    assert "done in" in r.stdout, r.stdout[-2000:]


def test_every_study_folder_is_listed_in_the_readme():
    readme = (ROOT / "case_studies" / "README.md").read_text(encoding="utf-8")
    missing = [s for s in STUDIES if f"({s}/)" not in readme]
    assert not missing, f"studies with a run.py but no row in case_studies/README.md: {missing}"
