"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The domain algebra. Pure: no I/O, no web framework, no database.
"""
from core.domain.algebra import (FitProcedure, OutputKind, ParameterKind, ParameterObject,
                                 ParametricKernel)
from core.domain.contracts import (Bound, Composition, Contract, ContractError,
                                   RefinementResult)
from core.domain.identity import EquivalenceResult, Probe, pi_equivalent
from core.domain.schemas import (Field, Schema, VarianceResult, explain,
                                 substitutable)

__all__ = [
                                 "Bound",
                                 "Composition",
                                 "Contract",
                                 "ContractError",
                                 "EquivalenceResult",
                                 "Field",
                                 "FitProcedure",
                                 "OutputKind",
                                 "ParameterKind",
                                 "ParameterObject",
                                 "ParametricKernel",
                                 "Probe",
                                 "RefinementResult",
                                 "Schema",
                                 "VarianceResult",
                                 "explain",
                                 "pi_equivalent",
                                 "substitutable",
]
