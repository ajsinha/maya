"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Validation and findings.

Split by responsibility: statistics (the measurements, written from their
definitions), catalogue (registered tests and threshold judgement), service
(episodes — plan, measure, conclude), findings (the register that blocks),
workflow (what happens to a finding between being raised and being closed),
ageing (everything derived from that: age, escalation, the committee profile),
replay (reproducibility), common (the shared vocabulary).
"""
from core.validation import ageing
from core.validation.catalogue import TestCatalogue, TestDefinition, TestOutcome
from core.validation.common import (ACTS, ACT_MEANING, BLOCKING_BY_DEFAULT,
                                    DEFAULT_ACKNOWLEDGE_DAYS, DEFAULT_ESCALATE_DAYS,
                                    DEFAULT_EXTENSION_LIMIT, ESCALATION_ROLE, KINDS,
                                    OUTCOMES, SEVERITIES, SOURCES,
                                    FindingWorkflowError, ValidationError,
                                    same_person, severity_rank, worst)
from core.validation.findings import FindingRegister
from core.validation.replay import Replayer
from core.validation.storage import SnapshotProvider
from core.validation.service import ValidationService
from core.validation.workflow import FindingWorkflow

__all__ = ["ValidationService", "FindingRegister", "FindingWorkflow",
           "FindingWorkflowError", "ageing", "TestCatalogue", "TestDefinition",
           "TestOutcome", "Replayer", "SnapshotProvider", "ValidationError", "SEVERITIES", "OUTCOMES",
           "KINDS", "SOURCES", "ACTS", "ACT_MEANING", "ESCALATION_ROLE",
           "DEFAULT_ACKNOWLEDGE_DAYS", "DEFAULT_ESCALATE_DAYS",
           "DEFAULT_EXTENSION_LIMIT", "BLOCKING_BY_DEFAULT", "same_person",
           "severity_rank", "worst"]
