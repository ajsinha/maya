"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Monitoring.

Split by responsibility: the vocabulary and which tests can answer which
question, delayed-label bookkeeping, monitor definitions, the breach register
that turns a breach into a finding, and the service that evaluates.
"""
from core.monitoring.breaches import BreachRegister
from core.monitoring.common import (ADMISSIBLE_TESTS, CALIBRATION, INPUT_DRIFT, KINDS,
                                    LABEL_DEPENDENT, PERFORMANCE, SCORE_DRIFT,
                                    MonitorError)
from core.monitoring.definitions import MonitorRegistry
from core.monitoring.defaults import MonitoringDefaults
from core.monitoring.plans import MonitoringPlans
from core.monitoring.labels import OutcomeWindow, labelled
from core.monitoring.service import MonitoringService

__all__ = [
                                    "ADMISSIBLE_TESTS",
                                    "CALIBRATION",
                                    "INPUT_DRIFT",
                                    "KINDS",
                                    "LABEL_DEPENDENT",
                                    "PERFORMANCE",
                                    "SCORE_DRIFT",
                                    "BreachRegister",
                                    "MonitorError",
                                    "MonitorRegistry",
                                    "MonitoringDefaults",
                                    "MonitoringPlans",
                                    "MonitoringService",
                                    "OutcomeWindow",
                                    "labelled",
]
