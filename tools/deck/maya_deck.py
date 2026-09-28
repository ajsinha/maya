"""
The one MAYA deck, as data: the title slide here, and the nine parts in order in
``deck_part1`` to ``deck_part4``.

It is written for the people who have to trust a model's number -- a head of model risk,
a validator, a supervisor, an engineer asked to integrate -- and it answers their
questions in the order they ask them: why the usual register fails, what MAYA is, the
vocabulary it needs, the lifecycle end to end, the governance a model risk function works
in, models that are not formulas, the formal core that makes the facts derivable, how it
runs, fifteen worked models, and what is measured and what is not done.

Every figure comes from the code, ``maya/core/version.py``, the README, ``docs/BENCHMARKS.md``
or a case study's run against a MAYA built from nothing.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from deck_part1 import SLIDES as PART1
from deck_part2 import SLIDES as PART2
from deck_part3 import SLIDES as PART3
from deck_part4 import SLIDES as PART4

from maya.core.version import VERSION

CHAPTER = "MAYA · Model Management"
TITLE = "MAYA — Model Management Formalism and System Design"
SUBJECT = "Why model governance fails, what MAYA does about it, and the evidence"

OPENING = [
    {
        "kind": "title",
        "kicker": "",
        "title": ["MAYA : Model Management", "& System Design"],
        "sub": "Evidence, not assertion.",
        "version": f"MAYA {VERSION} · specification revision 2.8",
        "agenda": [
            "Why model governance fails",
            "The vocabulary, from nothing",
            "The lifecycle, end to end",
            "Governance a model risk function works in",
            "Beyond formulas",
            "The formal core",
            "How it runs",
            "Fourteen models, carried the whole way",
            "What is measured, and what MAYA does not do",
        ],
    },
]

SLIDES = OPENING + PART1 + PART2 + PART3 + PART4
