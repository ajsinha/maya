"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

No source file grows past the point where somebody will read it.

The rule has been written down since the first milestone -- no Python file over
1,500 code lines -- and until now it was enforced by nobody noticing. It failed
in the ordinary way such rules fail: not by anybody deciding to break it, but by
a suite that everything was appended to because appending is where the fixtures
already were, one class at a time, none of them the one that made it too long.

Measured as CODE lines: blank lines, comments and docstrings do not count. That
is deliberate, because the alternative punishes the thing this codebase wants
more of. A file that explains why it does what it does should not be closer to
a refactor than one that says nothing.
"""
from __future__ import annotations

import ast
import pathlib

LIMIT = 1500
ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP = {".venv", ".claude", "__pycache__", "build", "dist", ".git"}

# The hard limit applies to everything. The *headroom* check below does not,
# because these grow by adding prose to a slide rather than by adding branches
# to a function: the deck generators are flat scripts whose length is content,
# and the remedy when one gets long is a chapter split, which is an editorial
# decision about the deck rather than a structural one about the code. Holding
# them to a warning threshold would mean restructuring a presentation to satisfy
# a number. They are still bounded -- just at the real limit and not before it.
PRESENTATION = ("tools/deck/",)


def _code_lines(path: pathlib.Path) -> int:
    """Lines that are neither blank, nor comment, nor inside a docstring."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    documented = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            documented.update(
                range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return sum(1 for i, line in enumerate(source.splitlines(), 1)
               if line.strip()
               and not line.strip().startswith("#")
               and i not in documented)


def _sources():
    for path in sorted(ROOT.rglob("*.py")):
        if not SKIP.intersection(path.parts):
            yield path


def test_no_source_file_is_longer_than_anybody_will_read():
    oversized = [(p.relative_to(ROOT), n) for p in _sources()
                 if (n := _code_lines(p)) > LIMIT]
    assert not oversized, (
        f"these files exceed {LIMIT:,} code lines:\n    "
        + "\n    ".join(f"{p} — {n:,}" for p, n in oversized)
        + "\nSplit by subject rather than by line count: a file cut at the "
          "1,500th line is two files nobody can name.")


def test_the_largest_file_leaves_room_to_grow():
    """A suite sitting at 1,499 passes and is one commit from failing, which
    turns the rule into a tripwire on whoever happens to add the next test.
    Fail earlier, while a split is still a choice rather than a chore."""
    candidates = [(p.relative_to(ROOT), _code_lines(p)) for p in _sources()
                  if not str(p.relative_to(ROOT)).startswith(PRESENTATION)]
    largest = max(candidates, key=lambda row: row[1])
    assert largest[1] <= LIMIT * 0.9, (
        f"{largest[0]} is at {largest[1]:,} code lines, within 10% of the "
        f"{LIMIT:,} limit. Split it now, by subject, while there is still a "
        f"seam to split on.")


def test_no_configuration_key_is_defined_twice():
    """A repeated mapping key in YAML keeps only the last, silently.

    `config/application.yaml` had two top-level `auth:` keys. The first held the
    bootstrap password and the session-signing secret; the second held the SSO
    block. YAML discarded the first, so MAYA_AUTH_PASSWORD and
    MAYA_SESSION_SECRET had no effect at all -- while the comments beside them
    told a deployer to set exactly those to secure the instance.

    Nothing raised, nothing warned, and the file parsed cleanly. The only way to
    see it is to read the source rather than the parsed document, which is what
    this does.
    """
    import re

    text = (ROOT / "config" / "application.yaml").read_text(encoding="utf-8")
    seen, duplicated, stack = {}, [], []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^(\s*)([A-Za-z_][\w.-]*):", line)
        if not match:
            continue
        indent, key = len(match.group(1)), match.group(2)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([k for _, k in stack] + [key])
        if path in seen:
            duplicated.append(f"{path} (lines {seen[path]} and {number})")
        seen[path] = number
        stack.append((indent, key))
    assert not duplicated, (
        "these configuration keys are defined more than once, so only the last "
        "definition is in force and every setting under the earlier one is "
        "silently discarded:\n    " + "\n    ".join(duplicated))
