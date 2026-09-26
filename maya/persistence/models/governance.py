"""
Model governance: findings and their remediation, materiality, and periodic review.

These are the records a model risk function keeps about a model rather than in it. A
finding is a defect somebody found and somebody else has to fix; a governance profile says
how much the model matters and how often it has to be looked at again; a review is the
dated, signed act of looking. They sit beside the registry, not inside a model version,
because they outlive versions: a finding raised against v3 is still open when v4 ships
unless somebody closes it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from maya.persistence.models.base import Base, Tracked
from maya.persistence.types import PortableJSON, PortableUUID, UTCDateTime


class Finding(Tracked, Base):
    """One defect in a model, from being raised to being closed or knowingly accepted."""

    __tablename__ = "findings"
    __table_args__ = (Index("ix_findings_model_state", "model_id", "state"),)
    model_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("models.id"))
    version_no: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(256))
    detail: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(24), default="validation")
    state: Mapped[str] = mapped_column(String(16), default="open")
    raised_by: Mapped[str] = mapped_column(String(128))
    owner: Mapped[str | None] = mapped_column(String(128))
    due_date: Mapped[dt.date | None] = mapped_column(Date)
    remediated_by: Mapped[str | None] = mapped_column(String(128))
    closed_by: Mapped[str | None] = mapped_column(String(128))
    closed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    resolution: Mapped[str | None] = mapped_column(Text)
    history: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)


class ModelGovernance(Tracked, Base):
    """How much a model matters, what that was derived from, and when it is next reviewed."""

    __tablename__ = "model_governance"
    model_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("models.id"), unique=True)
    use: Mapped[str | None] = mapped_column(String(32))
    exposure: Mapped[float | None] = mapped_column(Float)
    tier_override: Mapped[int | None] = mapped_column(Integer)
    override_reason: Mapped[str | None] = mapped_column(Text)
    review_days: Mapped[int | None] = mapped_column(Integer)
    last_reviewed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    last_reviewed_by: Mapped[str | None] = mapped_column(String(128))


class ModelReview(Tracked, Base):
    """One periodic review: who looked, when, and what they concluded."""

    __tablename__ = "model_reviews"
    __table_args__ = (Index("ix_model_reviews_model", "model_id"),)
    model_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("models.id"))
    reviewer: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(Integer)
    next_due: Mapped[dt.date | None] = mapped_column(Date)


class Challenge(Tracked, Base):
    """A champion and a challenger scored on the same escrowed holdout, and the decision."""

    __tablename__ = "challenges"
    champion_warrant_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    challenger_warrant_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    champion_parameter_set_id: Mapped[str | None] = mapped_column(PortableUUID)
    challenger_parameter_set_id: Mapped[str | None] = mapped_column(PortableUUID)
    metric: Mapped[str] = mapped_column(String(16))
    holdout_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    state: Mapped[str] = mapped_column(String(16), default="scored")
    raised_by: Mapped[str] = mapped_column(String(128))
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    rationale: Mapped[str | None] = mapped_column(Text)
