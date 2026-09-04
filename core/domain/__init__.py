"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The domain algebra. Pure: no I/O, no web framework, no database.
"""
from core.domain.algebra import (FitProcedure, OutputKind, ParameterKind, ParameterObject,
                                 ParametricKernel)
from core.domain.contracts import Bound, Contract, RefinementResult
from core.domain.identity import EquivalenceResult, Probe, pi_equivalent
from core.domain.schemas import (Field, Schema, VarianceResult, explain,
                                 substitutable)

__all__ = ["FitProcedure", "OutputKind", "ParameterKind", "ParameterObject",
           "ParametricKernel", "Bound", "Contract", "RefinementResult",
           "EquivalenceResult", "Probe", "pi_equivalent", "Field", "Schema",
           "VarianceResult", "substitutable", "explain"]
