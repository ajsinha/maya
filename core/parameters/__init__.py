"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Inhabitants of the parameter object.

Training does not change the kernel; it picks a point in P. So this package holds
what a fit produced, what a calibration solved, and what a person declared — each
with different evidence behind it, and each governed to a different depth.
"""
from core.parameters.common import (CALIBRATED, DECLARED, FITTED,
                                    PROVENANCE, PROVENANCE_MEANING, STATES,
                                    ParameterError)
from core.parameters.fitting import FittingService
from core.parameters.register import ParameterRegister

__all__ = ["ParameterRegister", "FittingService", "ParameterError", "PROVENANCE",
           "PROVENANCE_MEANING", "STATES", "FITTED", "CALIBRATED", "DECLARED"]
