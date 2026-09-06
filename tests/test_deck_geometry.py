"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The decks, checked by the same tool that claims to check them.

`tools/deck/GUIDE.md` presents the geometry audit as the shipping gate — "must
report no geometry issues before the deck ships" — and it was wired into no
test. It was also wrong, in the same direction, twice.

The second time it was wrong about tables. `GraphicFrame` has no text frame, so
the loop that measures everything skipped every table before it measured
anything, and excluded them as collision *targets* too. The three decks hold
twelve, sixty-two and twenty-eight tables, and seven real collisions were
sitting behind that one `continue` — three of them an opaque shape drawn over a
table, which does not crowd the reader but DELETES a row from the page. The
slides looked clean until somebody went looking for content that was not there.

A gate that is green on seven critical defects is worse than no gate, so it is
now a test.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools" / "deck" / "audit.py"

DECKS = [
    ("Models-as-Parametric-Kernels", 27),
    # The practitioner deck was merged in as chapters 9-14 rather than kept
    # beside this one: two decks meant two places to keep current, and the
    # engineering material is the same system described one level down.
    # Renamed and restructured: the deck is not only a system design, it is
    # the philosophy, the foundations, the concepts and the worked examples
    # as well — five parts, twenty-five chapters.
    # 152, down from 155. The count is asserted so that a chapter accidentally
    # dropped from the build is caught — `design_slides.py` executes whatever
    # `.py` files it finds, so a rename or a syntax error removes slides
    # silently and the deck still builds.
    ("MAYA-Model-and-Feature-Management", 110),
]


def _audit(deck: str) -> str:
    result = subprocess.run(
        [sys.executable, str(AUDIT), str(ROOT / "docs" / f"{deck}.pptx")],
        capture_output=True, text=True, cwd=ROOT)
    return result.stdout.strip()


@pytest.mark.parametrize("deck,slides", DECKS, ids=[d for d, _ in DECKS])
def test_the_deck_has_no_geometry_issues(deck, slides):
    report = _audit(deck)
    assert "no geometry issues detected" in report, (
        f"{deck}.pptx:\n{report}\n\n"
        "Rebuild with the generator and fix the call site the report names. The "
        "usual cause is a caller discarding the height `theme.table()` returns "
        "and hard-coding the next y — and `row_h` is a FLOOR, not a height, so "
        "the author's mental rows x row_h is always short.")


@pytest.mark.parametrize("deck,slides", DECKS, ids=[d for d, _ in DECKS])
def test_the_deck_has_the_slides_the_documents_claim(deck, slides):
    from pptx import Presentation
    actual = len(Presentation(ROOT / "docs" / f"{deck}.pptx").slides)
    assert actual == slides, (
        f"{deck}.pptx has {actual} slides; the README and the docs say {slides}")


def test_the_audit_can_see_tables_at_all():
    """A guard on the gate. If a change makes the audit skip graphic frames
    again, every check above goes quietly green on a deck full of collisions —
    which is exactly what happened."""
    source = AUDIT.read_text(encoding="utf-8")
    assert "has_table" in source, "the audit must measure tables"
    assert "table_height" in source, "a table's frame height is a floor, not a height"
    assert "is_opaque" in source, "an opaque shape drawn over content hides it"
