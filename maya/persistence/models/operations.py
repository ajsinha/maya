"""
Workflow, jobs, audit, lineage, comments and notifications (§10, §15, §19).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (BigInteger, Boolean, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from maya.persistence.models.base import Base, Tracked
from maya.persistence.types import PortableJSON, PortableUUID, UTCDateTime


class WorkflowPolicy(Tracked, Base):
    """A versioned policy record — the authority; YAML is its projection (§10.6)."""

    __tablename__ = "workflow_policies"
    __table_args__ = (UniqueConstraint("object_type", "scope", "version_no"),)
    object_type: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(128), default="*")
    version_no: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="draft")
    policy: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    activated_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class WorkflowEvent(Tracked, Base):
    """Every transition taken, in order — the instance history (§10.6)."""

    __tablename__ = "workflow_events"
    __table_args__ = (Index("ix_workflow_events_object", "object_type", "object_id"),)
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(64))
    object_ref: Mapped[str | None] = mapped_column(String(512))
    transition: Mapped[str] = mapped_column(String(32))
    from_state: Mapped[str] = mapped_column(String(24))
    to_state: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(128))
    rationale: Mapped[str | None] = mapped_column(Text)
    forced: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_id: Mapped[str | None] = mapped_column(PortableUUID)
    checks: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)


class Approval(Tracked, Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_object", "object_type", "object_id"),)
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(64))
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    approver: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str | None] = mapped_column(Text)


class Comment(Tracked, Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_object", "object_type", "object_id"),)
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(64))
    author: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    anchor: Mapped[str | None] = mapped_column(String(256))


class Notification(Tracked, Base):
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    object_ref: Mapped[str | None] = mapped_column(String(512))
    read_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class Campaign(Tracked, Base):
    __tablename__ = "campaigns"
    name: Mapped[str] = mapped_column(String(128))
    transition: Mapped[str] = mapped_column(String(32))
    items: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    state: Mapped[str] = mapped_column(String(16), default="open")
    results: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    rationale: Mapped[str | None] = mapped_column(Text)


class Job(Tracked, Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_state_run_after", "state", "run_after"),)
    job_type: Mapped[str] = mapped_column(String(48))
    owner: Mapped[str] = mapped_column(String(128), index=True)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    params: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    params_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    trace_id: Mapped[str] = mapped_column(String(32))
    logs: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    worker: Mapped[str | None] = mapped_column(String(128))


class AuditEvent(Base):
    """Append-only, hash-chained (§19). Insert-only is enforced in the DDL."""

    __tablename__ = "audit_events"
    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"),
                                     primary_key=True, autoincrement=True)
    at: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    actor: Mapped[str] = mapped_column(String(128), index=True)
    principal_type: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str | None] = mapped_column(String(32))
    object_ref: Mapped[str | None] = mapped_column(String(512), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class LineageEdge(Tracked, Base):
    __tablename__ = "lineage_edges"
    __table_args__ = (UniqueConstraint("src_ref", "dst_ref", "edge_type"),)
    src_ref: Mapped[str] = mapped_column(String(512), index=True)
    dst_ref: Mapped[str] = mapped_column(String(512), index=True)
    edge_type: Mapped[str] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(String(256))


class Subscription(Tracked, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "object_ref"),)
    user_id: Mapped[str] = mapped_column(PortableUUID)
    object_ref: Mapped[str] = mapped_column(String(512))


class Workspace(Tracked, Base):
    """A copy-on-write branch of the catalog where a change is rehearsed (§28.3)."""

    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), default="open")
    replay: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    submitted_versions: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    merged_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class WorkspaceChange(Tracked, Base):
    """One staged definition: nothing is copied until a change is written (§28.3)."""

    __tablename__ = "workspace_changes"
    __table_args__ = (UniqueConstraint("workspace_id", "object_kind", "object_id"),)
    workspace_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    object_kind: Mapped[str] = mapped_column(String(16))          # feature | featureset
    object_id: Mapped[str] = mapped_column(PortableUUID)
    object_ref: Mapped[str] = mapped_column(String(512))
    base_version_id: Mapped[str] = mapped_column(PortableUUID)
    base_version_no: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text)


class Event(Base):
    """One entry of the durable event stream, written with its audit entry (§18.1)."""

    __tablename__ = "events"
    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"),
                                     primary_key=True, autoincrement=True)
    at: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    type: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str | None] = mapped_column(String(32))
    object_ref: Mapped[str | None] = mapped_column(String(512))
    actor: Mapped[str] = mapped_column(String(128))
    trace_id: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class Webhook(Tracked, Base):
    """A subscriber. The signing secret is sealed at rest and shown once at creation."""

    __tablename__ = "webhooks"
    name: Mapped[str] = mapped_column(String(128), unique=True)
    url: Mapped[str] = mapped_column(String(1024))
    secret_sealed: Mapped[str] = mapped_column(Text)
    event_types: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)


class WebhookDelivery(Tracked, Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_deliveries_due", "state", "next_attempt_at"),)
    webhook_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    event_seq: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    last_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
