"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary of telemetry.

Two streams, not one. A **score** is produced when the model runs; an **outcome**
is learned later, sometimes much later. Treating them as one stream is what makes
a performance monitor evaluate an immature cohort and report a number that means
nothing — which is exactly what the delayed-label discipline exists to prevent.
"""
from __future__ import annotations

from typing import Dict, Tuple

SCORES, OUTCOMES = "scores", "outcomes"
STREAMS: Tuple[str, ...] = (SCORES, OUTCOMES)

STREAM_MEANING: Dict[str, str] = {
    SCORES: "what the model produced, when it produced it",
    OUTCOMES: "what actually happened, learned afterwards",
}

# Every row in either stream carries these.
ENTITY = "entity_id"
SCORED_AT = "scored_at"
INGEST_TS = "ingest_ts"

# A scored row's payload.
SCORE = "score"
# An outcome row's payload, and when the outcome was true rather than learned.
LABEL = "label"
LABEL_TS = "label_ts"

REQUIRED: Dict[str, Tuple[str, ...]] = {
    SCORES: (ENTITY, SCORED_AT, SCORE),
    OUTCOMES: (ENTITY, LABEL, LABEL_TS),
}

# A batch larger than this is refused rather than accepted and truncated.
MAX_BATCH = 100_000


class TelemetryError(RuntimeError):
    """A telemetry operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
