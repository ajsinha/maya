"""
LLM applications as governed objects: the application, its versions, the evaluation sets
it is judged on, and every evaluation run.

A version is what gets approved: the provider and model, the system prompt, the prompt
template, the sampling parameters and the guardrails, sealed together by a definition hash.
Change any of them and it is a different version, judged again.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from maya.persistence.models.base import Base, Tracked
from maya.persistence.types import PortableJSON, PortableUUID, UTCDateTime


class LlmApp(Tracked, Base):
    __tablename__ = "llm_apps"
    __table_args__ = (UniqueConstraint("namespace_id", "name"),)
    namespace_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("namespaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("users.id"))
    description: Mapped[str | None] = mapped_column(Text)
    use_case: Mapped[str | None] = mapped_column(Text)


class LlmAppVersion(Tracked, Base):
    __tablename__ = "llm_app_versions"
    __table_args__ = (UniqueConstraint("app_id", "version_no"),)
    app_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("llm_apps.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="draft")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    parameters: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    guardrails: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    definition_hash: Mapped[str] = mapped_column(String(64))
    submitted_by: Mapped[str | None] = mapped_column(String(128))
    submitted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    decision_note: Mapped[str | None] = mapped_column(Text)


class LlmEvalSet(Tracked, Base):
    __tablename__ = "llm_eval_sets"
    __table_args__ = (UniqueConstraint("app_id", "name"),)
    app_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("llm_apps.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    cases: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))


class LlmEvalRun(Tracked, Base):
    __tablename__ = "llm_eval_runs"
    __table_args__ = (Index("ix_llm_eval_runs_version", "version_id"),)
    version_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("llm_app_versions.id"))
    eval_set_id: Mapped[str] = mapped_column(PortableUUID, ForeignKey("llm_eval_sets.id"))
    eval_set_hash: Mapped[str] = mapped_column(String(64))
    definition_hash: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    cases: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    guardrail_violations: Mapped[int] = mapped_column(Integer, default=0)
    results: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
