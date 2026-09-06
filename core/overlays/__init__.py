"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Post-model adjustments.

The register, and the reading of it. The question worth answering is not what
overlays exist but which have stopped being temporary — so persistence,
materiality and trend are computed, and a persistent overlay raises a finding
because at that point it is an unversioned model change.
"""
from core.overlays import analysis
from core.overlays.common import (DIRECTIONS, KIND_MEANING, KINDS, STATUSES,
                                  OverlayError)
from core.overlays.register import OverlayRegister

__all__ = [
                                  "DIRECTIONS",
                                  "KINDS",
                                  "KIND_MEANING",
                                  "STATUSES",
                                  "OverlayError",
                                  "OverlayRegister",
                                  "analysis",
]
