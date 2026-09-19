"""
Identity, access and namespaces: users, roles, groups, sessions, API keys,
namespaces and the ACL table (§3, §11, §12, Appendix A).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from maya.persistence.models.base import Base, Tracked
from maya.persistence.types import PortableJSON, PortableUUID, UTCDateTime

FK_USER = "users.id"


class User(Tracked, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(128), unique=True)
    email: Mapped[str | None] = mapped_column(String(256))
    display_name: Mapped[str | None] = mapped_column(String(256))
    auth_source: Mapped[str] = mapped_column(String(16), default="db")
    password_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    first_failed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    locked_until: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    password_changed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(Text)  # sealed by SecretBox
    mfa_last_step: Mapped[int | None] = mapped_column(BigInteger)  # replay guard
    external_subject: Mapped[str | None] = mapped_column(String(256), index=True)
    is_service: Mapped[bool] = mapped_column(Boolean, default=False)
    desk: Mapped[str | None] = mapped_column(String(128))


class Role(Tracked, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(FK_USER), primary_key=True)
    role_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("roles.id"), primary_key=True)


class Group(Tracked, Base):
    __tablename__ = "groups"
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    sso_claim: Mapped[str | None] = mapped_column(String(256))


class GroupMember(Base):
    __tablename__ = "group_members"
    group_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("groups.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(FK_USER), primary_key=True)


class GroupRole(Base):
    __tablename__ = "group_roles"
    group_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("groups.id"), primary_key=True)
    role_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("roles.id"), primary_key=True)


class Session(Tracked, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(FK_USER), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    channel: Mapped[str] = mapped_column(String(16), default="web")
    # ok · challenge (password accepted, TOTP outstanding) · enroll (MFA required, not set up)
    mfa_state: Mapped[str] = mapped_column(String(16), default="ok")
    auth_method: Mapped[str] = mapped_column(String(16), default="password")
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    absolute_expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    # SAML single logout: the IdP names the sessions to end by NameID and SessionIndex
    sso_name_id: Mapped[str | None] = mapped_column(String(512), index=True)
    sso_session_index: Mapped[str | None] = mapped_column(String(256))


class ApiKey(Tracked, Base):
    __tablename__ = "api_keys"
    key_id: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(FK_USER), index=True)
    name: Mapped[str] = mapped_column(String(128))
    env: Mapped[str] = mapped_column(String(8))
    secret_hash: Mapped[str] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    namespaces: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    actions: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    cidrs: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class Namespace(Tracked, Base):
    __tablename__ = "namespaces"
    name: Mapped[str] = mapped_column(String(128), unique=True)
    parent_id: Mapped[str | None] = mapped_column(PortableUUID, ForeignKey("namespaces.id"))
    description: Mapped[str | None] = mapped_column(Text)
    default_visibility: Mapped[str] = mapped_column(String(32), default="namespace_read")
    quota_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sod: Mapped[str] = mapped_column(String(16), default="strict")
    preset: Mapped[str] = mapped_column(String(16), default="standard")
    classification: Mapped[str] = mapped_column(String(16), default="internal")
    is_scratch: Mapped[bool] = mapped_column(Boolean, default=False)
    production: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[str | None] = mapped_column(PortableUUID, ForeignKey(FK_USER))
    materialize_policy: Mapped[str] = mapped_column(String(16), default="always")
    # What counts as a material shift when a change is replayed here (§29.2). A desk whose
    # numbers are basis points and one whose numbers are prices cannot share one threshold;
    # unset falls back to workspaces.shadow.materiality.
    shadow_materiality: Mapped[float | None] = mapped_column(Float)


class Grant(Tracked, Base):
    __tablename__ = "grants"
    __table_args__ = (Index("ix_grants_object", "object_type", "object_id"),)
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(64))
    principal_type: Mapped[str] = mapped_column(String(16))
    principal_id: Mapped[str] = mapped_column(String(128))
    level: Mapped[str] = mapped_column(String(16))
    deny: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    conditions: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    inert_reason: Mapped[str | None] = mapped_column(Text)


class SchemaMeta(Base):
    __tablename__ = "schema_meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Blob(Base):
    """Content-addressed upload store index (§5.2): one row per distinct byte string."""

    __tablename__ = "blobs"
    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str | None] = mapped_column(String(128))
    filename: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[str | None] = mapped_column(String(128))


class SqlConnection(Tracked, Base):
    """An administrator-managed source connection (§5.2). Never holds a password:
    ``password_env`` names the environment variable that does."""

    __tablename__ = "sql_connections"
    name: Mapped[str] = mapped_column(String(128), unique=True)
    url: Mapped[str] = mapped_column(String(1024))
    password_env: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    options: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class AuthChallenge(Tracked, Base):
    """A single-use, short-lived value MAYA issued and expects back: a SAML AuthnRequest
    id, a consumed SAML assertion id, or a WebAuthn challenge. ``consumed_at`` makes it
    single-use; ``handle`` is unique, so a replay is a lookup that finds it consumed."""

    __tablename__ = "auth_challenges"
    kind: Mapped[str] = mapped_column(String(32), index=True)
    handle: Mapped[str] = mapped_column(String(256), unique=True)
    user_id: Mapped[str | None] = mapped_column(PortableUUID, ForeignKey(FK_USER), index=True)
    session_id: Mapped[str | None] = mapped_column(PortableUUID)
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, index=True)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    detail: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class WebAuthnCredential(Tracked, Base):
    """A registered security key or passkey: a second factor for a password login."""

    __tablename__ = "webauthn_credentials"
    user_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey(FK_USER), index=True)
    credential_id: Mapped[str] = mapped_column(String(512), unique=True)  # base64url
    public_key: Mapped[str] = mapped_column(Text)  # base64url COSE
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    transports: Mapped[list[str]] = mapped_column(PortableJSON, default=list)
    name: Mapped[str] = mapped_column(String(128), default="security key")
    aaguid: Mapped[str | None] = mapped_column(String(64))
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
