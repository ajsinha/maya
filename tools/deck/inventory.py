"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What is actually in the deck: an inventory, and where each concept is explained.

Written because "the deck should not have duplicated content" is not a question
a person can answer by paging through 155 slides. Textual duplication turned out
not to be the problem at all — no two slides are near-copies, and no long
sentence appears three times. The problem is **conceptual**: a concept
re-explained in a chapter that should have referenced it.

That shows up as *cluster count*. A concept appearing in two or three runs of
adjacent slides is being used; one appearing in fourteen separate places across
the deck is being re-introduced, and each re-introduction is slides the reader
did not need.

This is deliberately a **separate** tool from `audit.py`, which checks slide
*geometry* — whether anything overflows its box or covers something else.
Geometry is a shipping gate; this is an editorial one, and merging them would
mean a content question could break the gate that stops a slide rendering wrong.

Run:  .venv/bin/python tools/deck/inventory.py [path.pptx]
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

DEFAULT = (pathlib.Path(__file__).resolve().parents[2]
           / "docs" / "MAYA-Model-and-Feature-Management.pptx")

#: The load-bearing vocabulary. A reader meeting one of these for the first time
#: on slide 90 has been failed by the deck, and meeting it for the ninth time
#: has been bored by it.
CONCEPTS = {
    "P / parameter object": r"parameter object|\bP\b",
    "trainability T0-T8": r"\bT[0-8]\b|trainability",
    "warrant": r"warrant",
    "refusal": r"refus",
    "two clocks / PIT": r"ingest_ts|event_ts|two clocks|point.in.time",
    "semiring": r"semiring",
    "lattice / refines": r"lattice|refines|⊑",
    "risk tiering": r"\btier",
    "evidence chain": r"evidence chain|hash chain|chain_hash",
    "featureset": r"featureset",
    "laws": r"\bL-\d|\bL-W\d",
    "fibration": r"fibr",
    "composition": r"input_to|composes|composition",
    "documentation": r"\blens|dossier|model card",
    "separation of duties": r"quorum|segregation|self.approv",
}


def read(path: pathlib.Path):
    from pptx import Presentation
    out = []
    for index, slide in enumerate(Presentation(str(path)).slides, 1):
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
            if shape.has_table:
                for row in shape.table.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
        out.append((index, "\n".join(parts)))
    return out


def clusters(hits, gap=3):
    """Runs of nearby slides. Two runs is a concept used twice; fourteen is a
    concept explained fourteen times."""
    if not hits:
        return []
    runs, current = [], [hits[0]]
    for hit in hits[1:]:
        if hit - current[-1] <= gap:
            current.append(hit)
        else:
            runs.append(current)
            current = [hit]
    runs.append(current)
    return runs


def main(path: pathlib.Path) -> None:
    slides = read(path)
    words = [(i, len(t.split())) for i, t in slides]
    total = sum(w for _, w in words)
    print(f"{len(slides)} slides, {total:,} words, "
          f"{total / max(len(slides), 1):.0f} words per slide average\n")

    print("=== the heaviest slides (a reader stops reading around 110) ===")
    for i, w in sorted(words, key=lambda kv: -kv[1])[:15]:
        head = slides[i - 1][1].splitlines()
        title = head[1] if len(head) > 1 else (head[0] if head else "")
        print(f"  {w:>4} words  slide {i:>3}  {title[:62]}")

    print("\n=== where each concept is explained ===")
    print(f"  {'concept':<24}{'slides':>7}{'clusters':>10}   first appears")
    for name, pattern in CONCEPTS.items():
        hits = [i for i, t in slides if re.search(pattern, t, re.I)]
        runs = clusters(hits)
        flag = "  <-- re-explained" if len(runs) >= 6 else ""
        print(f"  {name:<24}{len(hits):>7}{len(runs):>10}   slide {hits[0] if hits else '-'}{flag}")

    # Shingles, not character similarity.
    #
    # This compared whole slides with `difflib.SequenceMatcher` at a 0.5
    # threshold and reported "no near-duplicates" for a deck in which slides 13
    # and 132 share twenty-six twelve-word runs including a verbatim sentence.
    # Two slides that repeat one paragraph out of six are barely similar
    # character-for-character and are exactly the duplication worth finding, so
    # the measure was answering a different question from the one asked — and
    # answering it confidently.
    #
    # Twelve-word shingles find shared *passages* regardless of what surrounds
    # them, which is what "the same content in two places" actually means.
    print("\n=== shared passages (12-word runs appearing on 2+ slides) ===")
    shingles = collections.defaultdict(set)
    for i, text in slides:
        words = re.sub(r"\s+", " ", text.lower()).split()
        for n in range(len(words) - 11):
            shingles[" ".join(words[n:n + 12])].add(i)

    pairs = collections.Counter()
    for where in shingles.values():
        for a in sorted(where):
            for b in sorted(where):
                if a < b:
                    pairs[(a, b)] += 1
    if not pairs:
        print("  none")
    for (a, b), n in pairs.most_common(20):
        print(f"  {n:>3} shared runs   slides {a:>3} and {b:>3}")

    print("\n=== the longest passage appearing on more than one slide ===")
    repeated = {s: w for s, w in shingles.items() if len(w) > 1}
    for s, where in sorted(repeated.items(), key=lambda kv: -len(kv[0]))[:6]:
        print(f"  {sorted(where)}: {s[:96]}")
    print(f"  {len(repeated)} repeated runs in total" if repeated else "  none")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
