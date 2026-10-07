"""
The one MAYA deck, as data, in ``story_part1`` to ``story_part4``, read in order.

It is told the way a briefing is. The opening answers a reader's questions first -- a
TL;DR, the question every model must answer, ten principles, what supervisors say, the
objects MAYA keeps, how it is built, one model's journey, what that buys -- and eight
parts follow: the vocabulary, the lifecycle, the platform, governance, models beyond
formulas, fifteen worked models, the formal core, and what is built, how it compares,
its limits and what comes next.

Every figure comes from the code, ``maya/core/version.py``, the README, ``docs/quality/BENCHMARKS.md``
or a case study's run against a MAYA built from nothing.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from story_part1 import SLIDES as PART1
from story_part2 import SLIDES as PART2
from story_part3 import SLIDES as PART3
from story_part4 import SLIDES as PART4

CHAPTER = "MAYA · Model & AI Lifecycle Assurance"
TITLE = "MAYA — Model & AI Lifecycle Assurance"
SUBJECT = "Why model governance fails, what MAYA does about it, and the evidence"

SLIDES = PART1 + PART2 + PART3 + PART4
