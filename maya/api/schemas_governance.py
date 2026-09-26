"""
Request bodies for model governance, champion/challenger, evidence and connectors.

Their own module because ``schemas`` reached the gate's limit on public names.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FindingIn(BaseModel):
    model: str
    title: str = Field(max_length=256)
    severity: str
    detail: str | None = None
    source: str = "validation"
    owner: str | None = None
    due_date: str | None = None
    version_no: int | None = None


class FindingMoveIn(BaseModel):
    action: str
    note: str | None = None


class GovernanceProfileIn(BaseModel):
    use: str | None = None
    exposure: float | None = None
    tier_override: int | None = None
    override_reason: str | None = None
    review_days: int | None = None
    answers: dict[str, str] | None = None


class ReviewIn(BaseModel):
    outcome: str
    note: str


class ChallengeIn(BaseModel):
    champion: str
    challenger: str
    metric: str = "rmse"
    champion_parameter_set_id: str | None = None
    challenger_parameter_set_id: str | None = None


class DecisionIn(BaseModel):
    decision: str
    rationale: str


class EvidenceIn(BaseModel):
    parameter_set_id: str | None = None
    segment: str | None = None
    importance: bool = True
    repeats: int = 5
    min_segment: int = 20


class MlflowImportIn(BaseModel):
    namespace: str
    name: str
    mlmodel: str
    estimates: str
    description: str = ""


class MlflowFetchIn(BaseModel):
    namespace: str
    name: str
    model_name: str
    version: str
    estimates: str
    description: str = ""


class SagemakerImportIn(BaseModel):
    namespace: str
    name: str
    package: dict[str, Any]
    estimates: str
    inputs: list[str] | None = None
    outputs: list[str] | None = None
