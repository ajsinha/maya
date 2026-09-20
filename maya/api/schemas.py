"""
Request bodies for the public API (Pydantic v2). Response bodies are the
service dictionaries, serialized by MAYA's JSON seam.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


class ApiKeyIn(BaseModel):
    name: str
    roles: list[str] = Field(default_factory=list)
    namespaces: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    cidrs: list[str] = Field(default_factory=list)
    days: int = 90


class UserIn(BaseModel):
    username: str
    password: str | None = None
    email: str = ""
    display_name: str = ""
    roles: list[str] = Field(default_factory=list)
    is_service: bool = False
    desk: str | None = None


class RolesIn(BaseModel):
    roles: list[str]


class ResetIn(BaseModel):
    new_password: str


class RoleIn(BaseModel):
    name: str
    description: str = ""
    capabilities: dict[str, str]


class GroupIn(BaseModel):
    name: str
    description: str = ""
    roles: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)


class NamespaceIn(BaseModel):
    name: str
    description: str = ""
    parent: str | None = None
    preset: str = "standard"
    default_visibility: str = "namespace_read"
    production: bool = False
    classification: str = "internal"
    quota_bytes: int | None = None


class RestoreDrillIn(BaseModel):
    dialect: str | None = None
    pins: int | None = 0
    drift: int | None = 0
    duration_seconds: float | None = 0.0
    outcome: str | None = "passed"
    chain_ok: bool | None = True
    anchors_ok: bool | None = True
    backup_taken_at: str | None = None
    notes: str | None = None


class LogLevelIn(BaseModel):
    module: str
    level: str


class ForkIn(BaseModel):
    name: str
    namespace: str | None = None
    version_no: int | None = None
    description: str = ""


class GrantIn(BaseModel):
    kind: str
    object_ref: str
    principal_type: str
    principal_id: str
    level: str
    days: int | None = 90
    deny: bool = False
    conditions: dict[str, Any] = Field(default_factory=dict)


class DefinitionIn(BaseModel):
    namespace: str
    name: str
    definition: dict[str, Any]
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class DraftIn(BaseModel):
    definition: dict[str, Any]
    expected_version: int | None = None
    description: str | None = None
    tags: list[str] | None = None


class CloneIn(BaseModel):
    name: str
    namespace: str | None = None
    extend: bool = False


class TransitionIn(BaseModel):
    rationale: str | None = None
    force: bool = False
    successor: str | None = None
    justification: str | None = None


class PinIn(BaseModel):
    version_no: int
    pin_name: str
    as_of: str
    as_of_known: str | None = None
    cascade: bool = False


class ModelIn(BaseModel):
    namespace: str
    name: str
    kind: str = "formula"
    description: str = ""
    formula: str | None = None
    roles: dict[str, str] = Field(default_factory=dict)
    ir: dict[str, Any] | None = None
    python_source: str | None = None
    vendor: dict[str, Any] = Field(default_factory=dict)


class ModelDraftIn(BaseModel):
    formula: str | None = None
    roles: dict[str, str] = Field(default_factory=dict)
    ir: dict[str, Any] | None = None
    python_source: str | None = None
    spec_latex: str | None = None
    maturity: str | None = None
    shadow_materiality: float | None = None
    expected_version: int | None = None


class ArtifactIn(BaseModel):
    source: str
    sample: dict[str, list[Any]] | None = None
    params: dict[str, Any] | None = None


class TrainingWarrantIn(BaseModel):
    namespace: str
    name: str
    model: str
    featureset: str
    spec: dict[str, Any] = Field(default_factory=dict)


class ParametersIn(BaseModel):
    values: dict[str, Any]
    metrics: dict[str, Any] = Field(default_factory=dict)
    data_checksum: str | None = None
    name: str | None = None
    notes: str = ""
    member_alias: str | None = None


class ReasonIn(BaseModel):
    reason: str


class ScoreIn(BaseModel):
    parameter_set_id: str | None = None
    values: dict[str, Any] | None = None


class ExecutionWarrantIn(BaseModel):
    namespace: str
    name: str
    training_warrant_id: str | None = None
    model: str | None = None
    parameter_set_id: str | None = None
    spec: dict[str, Any] = Field(default_factory=dict)


class ReportIn(BaseModel):
    environment: str
    rows: int
    input_stats: dict[str, Any] = Field(default_factory=dict)
    output_stats: dict[str, Any] = Field(default_factory=dict)


class PolicyIn(BaseModel):
    object_type: str
    policy: dict[str, Any]
    scope: str = "*"
    note: str = ""


class PolicyYamlIn(BaseModel):
    object_type: str
    yaml: str
    scope: str = "*"


class CommentIn(BaseModel):
    object_type: str
    object_id: str
    body: str
    blocking: bool = False
    anchor: str | None = None


class GenericTransitionIn(BaseModel):
    object_type: str
    object_id: str
    transition: str
    rationale: str | None = None
    force: bool = False


class CampaignIn(BaseModel):
    name: str
    transition: str
    items: list[dict[str, Any]]
    rationale: str = ""


class ReadIn(BaseModel):
    ids: list[str] | None = None


class SsoCallbackIn(BaseModel):
    code: str
    code_verifier: str
    nonce: str


class CodeIn(BaseModel):
    code: str


class SamlStartIn(BaseModel):
    relay_state: str = ""


class SamlAcsIn(BaseModel):
    saml_response: str


class SamlSlsIn(BaseModel):
    query_string: str  # exactly as the IdP's redirect carried it (signatures)


class WebAuthnRegisterIn(BaseModel):
    credential: dict[str, Any]
    name: str = "security key"


class WebAuthnVerifyIn(BaseModel):
    credential: dict[str, Any]


class WorkspaceIn(BaseModel):
    name: str
    description: str = ""


class StageIn(BaseModel):
    kind: str
    ref: str
    definition: dict[str, Any]
    note: str = ""


class ConnectionIn(BaseModel):
    name: str
    url: str
    password_env: str | None = None
    description: str = ""


class PullIn(BaseModel):
    knowledge_time: str | None = None


class WebhookIn(BaseModel):
    name: str
    url: str
    event_types: list[str] = Field(default_factory=list)
    description: str = ""


class DelegationIn(BaseModel):
    to: str
    starts_on: str
    ends_on: str
    object_types: list[str] = Field(default_factory=list)
    reason: str = ""


class PinPreviewIn(BaseModel):
    version_no: int
    as_of: str
    as_of_known: str | None = None
    pin_name: str = ""


class SubscriptionIn(BaseModel):
    object_ref: str


class AccessRequestIn(BaseModel):
    kind: str
    ref: str
    level: str = "read"
    reason: str = ""
    days: int = 90


class AccessDecisionIn(BaseModel):
    approve: bool
    note: str = ""
    days: int | None = None
