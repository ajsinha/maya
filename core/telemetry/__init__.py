"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Telemetry: what the model produced, and what actually happened.

Two streams because they arrive at different times, and the gap between them is
the thing a performance monitor has to reason about rather than ignore.
"""
from core.telemetry.collector import TelemetryCollector
from core.telemetry.common import (LABEL, OUTCOMES, SCORE, SCORES, STREAMS,
                                   STREAM_MEANING, TelemetryError)

__all__ = [
                                   "LABEL",
                                   "OUTCOMES",
                                   "SCORE",
                                   "SCORES",
                                   "STREAMS",
                                   "STREAM_MEANING",
                                   "TelemetryCollector",
                                   "TelemetryError",
]
