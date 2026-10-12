"""
The tutorials: one format, every picture present, and every example run.

Each tutorial follows the same shape -- a title, the time it takes, what it needs, what you
will learn, numbered steps that each say what you should see, where to go next, and what
to do when something goes wrong -- so a reader always knows where they are. And each is
executed, not just read: a real MAYA is started with an empty estate and the tutorials are
followed in order, every ``python`` block in one namespace per tutorial and every ``bash``
block in a shell, exactly as a reader working through them would. ``console`` blocks are
commands a reader types by hand (starting the server) and ``text`` blocks are what they
should see; neither is run. A tutorial whose example stops working fails the build.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from maya.web.help_catalog import GUIDES
from tests.test_api_guide import server  # noqa: F401 - the real MAYA on a socket, reused

ROOT = Path(__file__).resolve().parents[1]
GUIDE_DIR = ROOT / "maya" / "web" / "guides"
STATIC = ROOT / "maya" / "web" / "static"
TUTORIALS = sorted(GUIDE_DIR.glob("tutorial-[0-9][0-9]-*.md"))
BLOCK = re.compile(r"^```(\w*)\n(.*?)^```", re.S | re.M)
TITLE = re.compile(r"^# Tutorial (\d+) · \S.*$", re.M)
SECTIONS = ("## Time to complete", "## Before you start", "## What you will learn")
CLOSING = ("## Next steps", "## If something goes wrong")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _steps(text: str) -> list[tuple[int, str]]:
    """``(number, body)`` for each ``## Step N · ...`` section."""
    parts = re.split(r"^## ", text, flags=re.M)
    out = []
    for part in parts:
        m = re.match(r"Step (\d+) · \S", part)
        if m:
            out.append((int(m.group(1)), part))
    return out


def test_there_are_tutorials_and_they_are_numbered_in_order():
    assert TUTORIALS, "no tutorials found"
    numbers = [int(p.name.split("-")[1]) for p in TUTORIALS]
    assert numbers == list(range(1, len(numbers) + 1)), numbers
    for path, n in zip(TUTORIALS, numbers):
        m = TITLE.search(_text(path))
        assert m and int(m.group(1)) == n, f"{path.name}: title must be '# Tutorial {n} · ...'"


@pytest.mark.parametrize("path", TUTORIALS, ids=[p.stem for p in TUTORIALS])
def test_each_tutorial_has_the_shape_a_reader_relies_on(path):
    text = _text(path)
    where = [text.find(s) for s in SECTIONS]
    assert all(i > 0 for i in where), f"{path.name} lacks one of {SECTIONS}"
    assert where == sorted(where), f"{path.name}: sections out of order"
    steps = _steps(text)
    assert len(steps) >= 4, f"{path.name}: at least four steps"
    assert [n for n, _ in steps] == list(range(1, len(steps) + 1)), f"{path.name}: step numbers"
    for n, body in steps:
        assert "You should see" in body, f"{path.name} step {n} never says what you should see"
    first_step = text.find("## Step 1 · ")
    assert where[-1] < first_step, f"{path.name}: the front matter comes before the steps"
    tail = [text.find(s) for s in CLOSING]
    assert all(i > first_step for i in tail) and tail == sorted(tail), (
        f"{path.name} must end with {CLOSING}, in that order"
    )


@pytest.mark.parametrize("path", TUTORIALS, ids=[p.stem for p in TUTORIALS])
def test_each_tutorial_is_catalogued_and_its_pictures_exist(path):
    entry = next((g for g in GUIDES if g["slug"] == path.stem), None)
    assert entry and entry["kind"] == "tutorial", f"{path.stem} is not in help_catalog.GUIDES"
    assert entry["title"] == TITLE.search(_text(path)).group(0)[2:], (
        f"{path.stem}: the catalogue title must match the file's"
    )
    for src in re.findall(r"!\[[^\]]*\]\(\.\./static/([^)]+)\)", _text(path)):
        assert (STATIC / src).is_file(), f"{path.name}: missing picture {src}"
    for leak in ("/tmp/", "maya-dev-admin2", "mk_live_", "Bearer ey"):
        assert leak not in _text(path), f"{path.name} leaks {leak!r}"


def test_the_catalogue_lists_no_tutorial_that_does_not_exist():
    on_disk = {p.stem for p in TUTORIALS}
    listed = {g["slug"] for g in GUIDES if g["kind"] == "tutorial"}
    assert listed == on_disk, (
        f"catalogue {sorted(listed - on_disk)} vs files {sorted(on_disk - listed)}"
    )


def _shell_env(url: str) -> dict[str, str]:
    """A reader's shell: MAYA's URL, the repository importable, and ``python`` meaning the
    interpreter MAYA is installed in, as it does once the virtual environment is active."""
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    return dict(os.environ, MAYA_URL=url, PYTHONPATH=str(ROOT), PATH=path)


def run_tutorial(path: Path, url: str, workdir: Path) -> dict:
    """Follow one tutorial: its python blocks in one namespace, its bash blocks in a shell."""
    namespace: dict = {"__name__": path.stem}
    for i, m in enumerate(BLOCK.finditer(_text(path)), start=1):
        lang, code = m.group(1), m.group(2)
        if lang == "python":
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                try:
                    exec(compile(code, f"{path.name} block {i}", "exec"), namespace)  # noqa: S102
                except Exception as exc:  # noqa: BLE001 - reported with the block
                    raise AssertionError(
                        f"{path.name}: python block {i} failed: {type(exc).__name__}: {exc}\n"
                        f"{code}\n--- output so far ---\n{out.getvalue()}"
                    ) from exc
        elif lang == "bash":
            r = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + code],
                env=_shell_env(url),
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            assert r.returncode == 0, (
                f"{path.name}: bash block {i} failed:\n{code}\n{r.stdout}\n{r.stderr}"
            )
    return namespace


def test_every_tutorial_runs_in_order_against_a_fresh_maya(server, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("MAYA_URL", server)
    monkeypatch.chdir(tmp_path)
    for path in TUTORIALS:
        run_tutorial(path, server, tmp_path)
