"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Data classification, and what carries it downstream.

A feature has always been able to say it is confidential. Nothing read the
field. `Classification` makes it a lattice and propagates the join: a model is
at least as sensitive as the most sensitive thing it reads, and a document is at
least as sensitive as the most sensitive model it describes.
"""
from core.classification.common import (BOTTOM, DEFAULT, LEVELS, MEANING, RANK,
                                        ClassificationError, at_least, join,
                                        normalise)
from core.classification.propagation import Classification

__all__ = ["BOTTOM", "DEFAULT", "LEVELS", "MEANING", "RANK",
           "Classification", "ClassificationError", "at_least", "join",
           "normalise"]
