"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Validation and findings.

Split by responsibility: statistics (the measurements, written from their
definitions), catalogue (registered tests and threshold judgement), service
(episodes — plan, measure, conclude), findings (the register that blocks),
replay (reproducibility), common (the shared vocabulary).
"""
from core.validation.catalogue import TestCatalogue, TestDefinition, TestOutcome
from core.validation.common import (BLOCKING_BY_DEFAULT, KINDS, OUTCOMES, SEVERITIES,
                                    SOURCES, ValidationError, severity_rank, worst)
from core.validation.findings import FindingRegister
from core.validation.replay import Replayer
from core.validation.service import ValidationService

__all__ = ["ValidationService", "FindingRegister", "TestCatalogue", "TestDefinition",
           "TestOutcome", "Replayer", "ValidationError", "SEVERITIES", "OUTCOMES",
           "KINDS", "SOURCES", "BLOCKING_BY_DEFAULT", "severity_rank", "worst"]
