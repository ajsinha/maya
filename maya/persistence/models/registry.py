"""
Models, parameter sets and warrants with their chain of custody (§8, §9,
§29.4, §29.5, Appendix A).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from maya.persistence.models.base import Base, Tracked
from maya.persistence.types import PortableJSON, PortableUUID, UTCDateTime

MV = "model_versions.id"


class Model(Tracked, Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("namespace_id", "name"),)
    namespace_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("namespaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16), default="formula")
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    vendor: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="draft")


class ModelVersion(Tracked, Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version_no"),)
    model_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("models.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="draft")
    maturity: Mapped[str] = mapped_column(String(16), default="experimental")
    formula_ir: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    input_contract: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    ir_hash: Mapped[str | None] = mapped_column(String(64))
    artifact_hash: Mapped[str | None] = mapped_column(String(64))
    artifact_report: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    spec_latex: Mapped[str | None] = mapped_column(Text)
    spec_state: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    definition_hash: Mapped[str | None] = mapped_column(String(64))
    opaque: Mapped[bool] = mapped_column(Boolean, default=False)
    # The shift in this model's own output that its owner calls material (§29.2). It is
    # declared here and not on the namespace because units belong to the model: a rate in
    # basis points, a price and a probability are material at three different numbers, and a
    # report that used the namespace's figure for all three would read "nothing moved".
    shadow_materiality: Mapped[float | None] = mapped_column(Float)
    successor_ref: Mapped[str | None] = mapped_column(String(512))
    force_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    submitted_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    needs_reapproval: Mapped[str | None] = mapped_column(Text)


class CompositeMember(Base):
    __tablename__ = "composite_members"
    __table_args__ = (UniqueConstraint("composite_version_id", "alias"),)
    id: Mapped[str] = mapped_column(PortableUUID, primary_key=True)
    composite_version_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(MV), index=True)
    alias: Mapped[str] = mapped_column(String(64))
    member_ref: Mapped[str] = mapped_column(String(512))
    binding: Mapped[str] = mapped_column(String(16), default="pinned")
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    borrowed_parameter_set_id: Mapped[str | None] = mapped_column(PortableUUID)
    order_no: Mapped[int] = mapped_column(Integer, default=0)


class ParameterSet(Tracked, Base):
    __tablename__ = "parameter_sets"
    model_version_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(MV), index=True)
    training_warrant_id: Mapped[str | None] = mapped_column(PortableUUID, index=True)
    name: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(24), default="draft")
    values: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    values_hash: Mapped[str] = mapped_column(String(64))
    param_schema: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    data_checksum: Mapped[str | None] = mapped_column(String(64))
    verified_data: Mapped[bool] = mapped_column(Boolean, default=False)
    unverified_justification: Mapped[str | None] = mapped_column(Text)
    member_alias: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    force_approved: Mapped[bool] = mapped_column(Boolean, default=False)


class TrainingWarrant(Tracked, Base):
    __tablename__ = "training_warrants"
    __table_args__ = (UniqueConstraint("namespace_id", "name", "version_no"),)
    namespace_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("namespaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(24), default="draft")
    owner_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("users.id"))
    model_version_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(MV))
    featureset_ref: Mapped[str] = mapped_column(String(512))
    feature_set_pin_id: Mapped[str | None] = mapped_column(PortableUUID)
    spec: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    contract_report: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    leakage_certificate: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    backends: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    sealed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    clone_of: Mapped[str | None] = mapped_column(PortableUUID)
    holdout_attempts: Mapped[int] = mapped_column(Integer, default=0)
    # The escrowed holdout, fixed when the warrant is drawn: the content hash of the test
    # partition and its row count. Scoring recomputes the partition and refuses to answer
    # if it no longer hashes the same, so "escrowed" means the numbers cannot move under a
    # warrant that has already been scored against them (§29.4).
    holdout_hash: Mapped[str | None] = mapped_column(String(64))
    holdout_rows: Mapped[int | None] = mapped_column(Integer)
    force_approved: Mapped[bool] = mapped_column(Boolean, default=False)


class ExecutionWarrant(Tracked, Base):
    __tablename__ = "execution_warrants"
    __table_args__ = (UniqueConstraint("namespace_id", "name", "version_no"),)
    namespace_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("namespaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(24), default="draft")
    owner_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("users.id"))
    training_warrant_id: Mapped[str | None] = mapped_column(PortableUUID)
    model_version_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(MV))
    parameter_set_id: Mapped[str | None] = mapped_column(PortableUUID)
    spec: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    manifest: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    backends: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    valid_from: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    valid_to: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    sealed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    suspended_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    suspend_reason: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    executions: Mapped[int] = mapped_column(Integer, default=0)
    force_approved: Mapped[bool] = mapped_column(Boolean, default=False)


class CustodyEvent(Tracked, Base):
    """Chain of custody (§9.3): who created, approved, sealed, downloaded, uploaded."""

    __tablename__ = "custody_events"
    warrant_type: Mapped[str] = mapped_column(String(16))
    warrant_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    event: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128))
    checksum: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class ExecutionReport(Tracked, Base):
    """An execution reported back by the SDK, with covenant evaluation (§29.5)."""

    __tablename__ = "execution_reports"
    execution_warrant_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    environment: Mapped[str] = mapped_column(String(16))
    rows: Mapped[int] = mapped_column(Integer, default=0)
    input_stats: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    output_stats: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    breaches: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)


class HoldoutScore(Tracked, Base):
    """One blind-scoring attempt against an escrowed holdout (§29.4)."""

    __tablename__ = "holdout_scores"
    training_warrant_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    parameter_set_id: Mapped[str | None] = mapped_column(PortableUUID)
    attempt_no: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class RestatementImpact(Tracked, Base):
    """What a restatement under a live model's training pin changed (§29.1, §29.4).

    The pin itself never moves; this records the difference between it and the same
    definition resolved with what is known now: rows changed, the holdout metrics both ways,
    and how far the live parameters' predictions moved."""

    __tablename__ = "restatement_impacts"
    execution_warrant_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    training_warrant_id: Mapped[str] = mapped_column(PortableUUID)
    feature_set_pin_id: Mapped[str] = mapped_column(PortableUUID)
    trigger: Mapped[str | None] = mapped_column(String(512))
    knowledge_time: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    sealed_hash: Mapped[str] = mapped_column(String(64))
    corrected_hash: Mapped[str] = mapped_column(String(64))
    rows: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    metrics_sealed: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    metrics_corrected: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    shift: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    state: Mapped[str] = mapped_column(String(16), default="open")
    acknowledged_by: Mapped[str | None] = mapped_column(String(128))
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    note: Mapped[str | None] = mapped_column(Text)
