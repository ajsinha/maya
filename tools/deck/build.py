"""
Build the decks.

    python tools/deck/build.py                 # all four, into docs/
    python tools/deck/build.py design          # one of: executive, design, capabilities, concepts
    python tools/deck/audit.py docs/<deck>.pptx

The deck is a list of slide specs across four modules; ``layouts`` draws them
with the ``theme``. The document properties are set explicitly: python-pptx's
default template carries a comment naming the library, and a deck's metadata
should say who wrote it and nothing else.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1]))

import layouts  # noqa: E402
import maya_deck  # noqa: E402
import theme  # noqa: E402

DOCS = HERE.parents[1] / "docs" / "publications"
# One deck. Four was four places to keep one story current, and the story is one: what a
# model is, what follows from that, and what MAYA does about it.
DECKS = {
    "maya": ("MAYA-Model-Management-Formalism-and-System-Design", maya_deck),
}
AUTHOR = "Ashutosh Sinha"


def build(key: str, out_dir: Path = DOCS) -> tuple[Path, int]:
    name, module = DECKS[key]
    prs = theme.new_deck(module.CHAPTER)
    layouts.render(module.SLIDES)
    props = prs.core_properties
    props.title = module.TITLE
    props.subject = module.SUBJECT
    props.author = AUTHOR
    props.last_modified_by = AUTHOR
    props.comments = "Copyright (c) 2026 Ashutosh Sinha. All rights reserved."
    props.keywords = "MAYA; model risk; governance"
    props.category = ""
    props.revision = 1
    stamp = dt.datetime(2026, 9, 19, 12, 0, 0)
    props.created = stamp
    props.modified = stamp
    out = out_dir / f"{name}.pptx"
    prs.save(str(out))
    return out, len(prs.slides)


def main(argv: list[str]) -> int:
    keys = argv[1:] or list(DECKS)
    for key in keys:
        out, n = build(key)
        print(f"{n:3d} slides -> {out.relative_to(HERE.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
