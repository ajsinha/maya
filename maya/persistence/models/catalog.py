"""
The feature and feature-set catalog: definitions, versions, bitemporal
ingests, pin series, fragments, members, derivations and inheritance links
(§5, §6, §7, §29.1, §29.3, Appendix A).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from maya.persistence.models.base import Base, Tracked
from maya.persistence.types import PortableJSON, PortableUUID, UTCDateTime

NS = "namespaces.id"


class Feature(Tracked, Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("namespace_id", "name"),)
    namespace_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(NS), index=True)
    name: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("users.id"))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    index_spec: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    ungoverned: Mapped[bool] = mapped_column(Boolean, default=False)


class FeatureVersion(Tracked, Base):
    __tablename__ = "feature_versions"
    __table_args__ = (UniqueConstraint("feature_id", "version_no"),)
    feature_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("features.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="draft")
    definition: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    definition_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    change_class: Mapped[str | None] = mapped_column(String(16))
    non_causal: Mapped[bool] = mapped_column(Boolean, default=False)
    force_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    submitted_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    needs_reapproval: Mapped[str | None] = mapped_column(Text)


class FeatureIngest(Tracked, Base):
    """One bitemporal batch of raw source rows: a knowledge-time slice (§29.1)."""

    __tablename__ = "feature_ingests"
    feature_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("features.id"), index=True)
    blob_hash: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(16))
    knowledge_time: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    rows: Mapped[int] = mapped_column(BigInteger, default=0)
    lake_version: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    restatement: Mapped[bool] = mapped_column(Boolean, default=False)


class FeaturePin(Tracked, Base):
    """A pin series member (D-2): (feature, pin_name) is the series."""

    __tablename__ = "feature_pins"
    __table_args__ = (UniqueConstraint("feature_id", "pin_name", "as_of_date"),)
    feature_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("features.id"), index=True)
    feature_version_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("feature_versions.id"))
    pin_name: Mapped[str] = mapped_column(String(128))
    as_of_date: Mapped[dt.date] = mapped_column(Date)
    as_of_known: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    state: Mapped[str] = mapped_column(String(16), default="materializing")
    content_hash: Mapped[str | None] = mapped_column(String(64))
    schema_digest: Mapped[str | None] = mapped_column(String(64))
    fragments: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    lake_table: Mapped[str | None] = mapped_column(String(512))
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_total: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_new: Mapped[int] = mapped_column(BigInteger, default=0)
    fill_report: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    quality: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    provenance: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    sealed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    retired_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    retire_reason: Mapped[str | None] = mapped_column(Text)
    failure: Mapped[str | None] = mapped_column(Text)
    # Retention (§7.3): when this pin was last read, so cold ones can be named; and the
    # archive blob a retired pin was packed into, if it has been.
    last_read_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    archive_blob: Mapped[str | None] = mapped_column(String(64))
    archived_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class Fragment(Base):
    """The fragment index (§29.3): one row per distinct stored fragment."""

    __tablename__ = "fragments"
    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    lake_table: Mapped[str] = mapped_column(String(512), primary_key=True)
    rows: Mapped[int] = mapped_column(BigInteger)
    bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime)


class FeatureSet(Tracked, Base):
    __tablename__ = "feature_sets"
    __table_args__ = (UniqueConstraint("namespace_id", "name"),)
    namespace_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(NS), index=True)
    name: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("users.id"))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="draft")


class FeatureSetVersion(Tracked, Base):
    __tablename__ = "feature_set_versions"
    __table_args__ = (UniqueConstraint("feature_set_id", "version_no"),)
    feature_set_id: Mapped[str] = mapped_column(
        PortableUUID, ForeignKey("feature_sets.id"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="draft")
    definition: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    definition_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    change_class: Mapped[str | None] = mapped_column(String(16))
    non_causal: Mapped[bool] = mapped_column(Boolean, default=False)
    force_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    submitted_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    needs_reapproval: Mapped[str | None] = mapped_column(Text)


class FeatureSetMember(Base):
    __tablename__ = "feature_set_members"
    id: Mapped[str] = mapped_column(PortableUUID, primary_key=True)
    feature_set_version_id: Mapped[str] = mapped_column(
        PortableUUID, ForeignKey("feature_set_versions.id"), index=True
    )
    attr_name: Mapped[str] = mapped_column(String(128))
    ref_uri: Mapped[str] = mapped_column(String(512))
    source_attr: Mapped[str] = mapped_column(String(128))
    cast: Mapped[str | None] = mapped_column(String(64))
    overrides: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    order_no: Mapped[int] = mapped_column(Integer, default=0)


class FeatureSetPin(Tracked, Base):
    __tablename__ = "feature_set_pins"
    __table_args__ = (UniqueConstraint("feature_set_id", "pin_name", "as_of_date"),)
    feature_set_id: Mapped[str] = mapped_column(
        PortableUUID, ForeignKey("feature_sets.id"), index=True
    )
    feature_set_version_id: Mapped[str] = mapped_column(
        PortableUUID, ForeignKey("feature_set_versions.id")
    )
    pin_name: Mapped[str] = mapped_column(String(128))
    as_of_date: Mapped[dt.date] = mapped_column(Date)
    as_of_known: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    state: Mapped[str] = mapped_column(String(16), default="materializing")
    member_pin_ids: Mapped[dict[str, str]] = mapped_column(PortableJSON, default=dict)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    schema_digest: Mapped[str | None] = mapped_column(String(64))
    fragments: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    lake_table: Mapped[str | None] = mapped_column(String(512))
    manifest: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_total: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_new: Mapped[int] = mapped_column(BigInteger, default=0)
    provenance: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    sealed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    retired_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    retire_reason: Mapped[str | None] = mapped_column(Text)
    failure: Mapped[str | None] = mapped_column(Text)
    # Retention (§7.3): when this pin was last read, so cold ones can be named; and the
    # archive blob a retired pin was packed into, if it has been.
    last_read_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    archive_blob: Mapped[str | None] = mapped_column(String(64))
    archived_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class Derivation(Tracked, Base):
    """One algebra operation with its ordered operands (§5.8, §6.8)."""

    __tablename__ = "derivations"
    target_type: Mapped[str] = mapped_column(String(24))
    target_version_id: Mapped[str] = mapped_column(PortableUUID, index=True)
    operator: Mapped[str] = mapped_column(String(32))
    operand_refs: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    options: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class InheritanceLink(Tracked, Base):
    """Single parent enforced by the unique child_version_id (§5.8)."""

    __tablename__ = "inheritance_links"
    child_type: Mapped[str] = mapped_column(String(24))
    child_version_id: Mapped[str] = mapped_column(PortableUUID, unique=True)
    parent_ref: Mapped[str] = mapped_column(String(512))
    binding: Mapped[str] = mapped_column(String(16), default="pinned")
    override_diff: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
