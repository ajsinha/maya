"""
The assistant as a recorded challenger (§29.8): memos on every review.

When a feature, feature set or model version is submitted, a memo is queued in
the same transaction (so it exists only if the submission commits) and written
by a job: the deterministic findings always, and — with
``assistant.provider: claude`` — Claude's challenge on top. The memo is stored
beside the review, attributed to the provider and the exact model that wrote
it; the reviewer records whether they agreed, and that is audited.

The boundaries are structural, not promises. The memo lives in its own table;
nothing here updates the version or runs a workflow transition, and no check
reads a memo, so it cannot approve, block or edit anything. With the Claude
provider, the definitions, the specification and the formula are sent to
Anthropic's API — never data rows — which is why that provider is opt-in.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from maya.assistant import drafts, rules
from maya.core.errors import (
    CapabilityRefused,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from maya.core.clock import utcnow
from maya.security.authz import Principal
from maya.services import catalog, refs

TARGETS = {  # object_type -> (version table, fk, parent table, access kind)
    "feature_version": ("feature_versions", "feature_id", "features", "feature"),
    "featureset_version": ("feature_set_versions", "feature_set_id", "feature_sets", "featureset"),
    "model_version": ("model_versions", "model_id", "models", "model"),
}
STANCES = ("agree", "partly", "disagree")


class AssistantService:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        s = platform.settings
        self.enabled = s.bool("assistant.enabled", True)
        self.provider = (s.get("assistant.provider") or "rules").strip()
        if self.provider not in ("rules", "claude"):
            raise ValidationFailed("assistant.provider must be 'rules' or 'claude'")
        self.model = (s.get("assistant.claude.model") or "claude-opus-5").strip()
        self.effort = (s.get("assistant.claude.effort") or "high").strip()
        self.client: Any = None  # tests inject a Claude client

    # -- drafting (§29.8): a proposal, never a write ----------------------------------------
    def draft_feature(
        self, p: Principal, description: str, data: bytes | None = None, fmt: str = "csv"
    ) -> dict[str, Any]:
        """A proposed feature definition from a description and a sample file.

        Nothing is created: the draft comes back for a person to read, edit and submit
        through the ordinary path, so an assistant cannot put anything into the catalog.
        Only the sample's **structure** is used — column names, types and null counts — and
        with the Claude provider only that structure is sent, never a row of data.
        """
        if not self.enabled:
            raise CapabilityRefused("The assistant is switched off (assistant.enabled)")
        self.p.access.require_capability(p, "feature", "C")
        columns = _columns(data, fmt) if data else []
        draft = drafts.feature_definition(description, columns, fmt=fmt)
        errors = catalog.validate_feature_definition(draft["definition"])
        draft["errors"] = errors
        draft["valid"] = not errors
        draft["provider"] = self.provider
        with self.p.uow(p.username) as uow:
            uow.audit(
                "assistant.drafted",
                detail={"kind": "feature", "columns": len(columns), "valid": draft["valid"]},
            )
        return draft

    def draft_spec(self, p: Principal, ref: str, version_no: int) -> dict[str, Any]:
        """Drafts for the specification sections nobody has written yet."""
        if not self.enabled:
            raise CapabilityRefused("The assistant is switched off (assistant.enabled)")
        from maya.formula import specdoc

        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            version = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        latex = version["spec_latex"] or specdoc.TEMPLATE
        out = drafts.spec_sections(
            latex, version["formula_ir"] or {}, specdoc.section_completeness(latex)
        )
        out["provider"] = self.provider
        with self.p.uow(p.username) as uow:
            uow.audit(
                "assistant.drafted",
                object_type="model",
                object_ref=f"{ref}@v{version_no}",
                detail={"kind": "spec", "sections": out["missing"]},
            )
        return out

    # -- the dossier: exactly what the challenger may read ---------------------------------
    def _load(
        self, uow: Any, object_type: str, object_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if object_type not in TARGETS:
            raise ValidationFailed(f"No challenger for '{object_type}'", supported=sorted(TARGETS))
        table, fk, parent_table, _ = TARGETS[object_type]
        v = uow.repo(table).get(object_id)
        if v is None:
            raise NotFound(f"{object_type} '{object_id}' does not exist")
        parent = uow.repo(parent_table).require(v[fk])
        ns = uow.repo("namespaces").require(parent["namespace_id"])
        return v, parent, ns

    def _previous(
        self, uow: Any, object_type: str, v: dict[str, Any], parent: dict[str, Any]
    ) -> dict[str, Any] | None:
        table, fk, _, _ = TARGETS[object_type]
        earlier = [
            x
            for x in uow.repo(table).list(**{fk: parent["id"]}, order_by=["-version_no"])
            if x["version_no"] < v["version_no"] and x["state"] in catalog.APPROVED_STATES
        ]
        return earlier[0] if earlier else None

    def dossier(self, uow: Any, object_type: str, object_id: str) -> dict[str, Any]:
        v, parent, ns = self._load(uow, object_type, object_id)
        kind = TARGETS[object_type][3]
        ref = refs.version_ref(kind, ns["name"], parent["name"], v["version_no"])
        prev = self._previous(uow, object_type, v, parent)
        base = {
            "object_type": object_type,
            "ref": ref,
            "description": parent.get("description"),
            "version_no": v["version_no"],
            "state": v["state"],
            "previous_version_no": prev["version_no"] if prev else None,
        }
        if object_type == "feature_version":
            eff = catalog.effective_feature_definition(uow, v["definition"])
            before = catalog.effective_feature_definition(uow, prev["definition"]) if prev else None
            return {**base, "definition": eff, "previous": before}
        if object_type == "featureset_version":
            eff, inherited = self.p.featuresets.effective(uow, v["definition"])
            members = []
            for m in eff.get("members", []):
                try:
                    feat, _ = catalog.find_object(
                        uow, "features", "feature", refs.parse(m["ref"], "feature")
                    )
                    fv = catalog.version_of(
                        uow,
                        "feature_versions",
                        "feature_id",
                        feat,
                        refs.parse(m["ref"], "feature").version,
                    )
                    members.append(
                        {
                            **m,
                            "definition": catalog.effective_feature_definition(
                                uow, fv["definition"]
                            ),
                        }
                    )
                except Exception:  # noqa: BLE001 - a member the validator will refuse anyway
                    members.append(m)
            return {**base, "definition": eff, "inherited": inherited, "members": members}
        from maya.formula.diff import semantic_diff

        ir = v["formula_ir"] or {}
        return {
            **base,
            "formula_ir": ir,
            "ir_hash": v["ir_hash"],
            "maturity": v["maturity"],
            "spec_latex": v["spec_latex"],
            "spec_state": v["spec_state"],
            "input_contract": v["input_contract"],
            "diff": semantic_diff(prev["formula_ir"] or {}, ir) if prev else [],
        }

    # -- queueing ------------------------------------------------------------------------
    def _queue(
        self, uow: Any, object_type: str, object_id: str, ref: str, owner: str
    ) -> dict[str, Any]:
        memo = uow.repo("challenge_memos").add(
            {
                "object_type": object_type,
                "object_id": object_id,
                "object_ref": ref,
                "provider": self.provider,
                "model": self.model if self.provider == "claude" else "rules/1",
                "state": "pending",
            }
        )
        self.p.jobs.submit(uow, "assistant.challenge", {"memo_id": memo["id"]}, owner=owner)
        return memo

    def on_move(self, uow: Any, subject: Any, transition: str, to_state: str) -> None:
        """Workflow listener: every submission into review gets a memo (§29.8)."""
        if self.enabled and to_state == "in_review" and subject.object_type in TARGETS:
            self._queue(uow, subject.object_type, subject.id, subject.ref, "assistant")

    def request(self, p: Principal, object_type: str, object_id: str) -> dict[str, Any]:
        """A fresh memo on demand (e.g. after the draft changed)."""
        with self.p.uow(p.username) as uow:
            v, parent, ns = self._load(uow, object_type, object_id)
            self.p.access.require(uow, p, "read", TARGETS[object_type][3], parent)
            kind = TARGETS[object_type][3]
            ref = refs.version_ref(kind, ns["name"], parent["name"], v["version_no"])
            memo = self._queue(uow, object_type, object_id, ref, p.username)
            uow.audit(
                "assistant.requested",
                object_type=object_type,
                object_ref=ref,
                detail={"memo": memo["id"], "provider": self.provider},
            )
            return memo

    # -- writing the memo (a job) -----------------------------------------------------------
    def run_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        with self.p.uow() as uow:
            memo = uow.repo("challenge_memos").require(params["memo_id"])
            dossier = self.dossier(uow, memo["object_type"], memo["object_id"])
        digest = hashlib.sha256(
            json.dumps(dossier, sort_keys=True, default=str).encode()
        ).hexdigest()
        ctx.progress(20, "deterministic checks")
        result = rules.challenge(dossier)
        changes: dict[str, Any] = {
            "dossier_sha256": digest,
            "state": "ready",
            "summary": result["summary"],
            "findings": result["findings"],
        }
        if memo["provider"] == "claude":
            ctx.progress(40, f"asking {memo['model']}")
            from maya.assistant import claude

            try:
                client = self.client or claude.client_from(self.p.settings)
                llm = claude.challenge(
                    client, dossier, result, model=memo["model"], effort=self.effort
                )
                changes.update(
                    summary=llm["summary"],
                    model=llm["model"],
                    findings=result["findings"] + llm["findings"],
                )
            except claude.ChallengerUnavailable as exc:
                changes["error"] = f"{exc.message} — the memo holds the deterministic findings only"
        with self.p.uow("assistant") as uow:
            row = uow.repo("challenge_memos").update(memo["id"], changes)
            uow.audit(
                "assistant.memo_written",
                object_type=memo["object_type"],
                object_ref=memo["object_ref"],
                principal_type="system",
                detail={
                    "memo": memo["id"],
                    "provider": memo["provider"],
                    "model": row["model"],
                    "findings": len(row["findings"]),
                    "error": row["error"],
                },
            )
        return {"findings": len(row["findings"]), "error": row["error"]}

    # -- reading and responding --------------------------------------------------------------
    def memos(self, p: Principal, object_type: str, object_id: str) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            _, parent, _ = self._load(uow, object_type, object_id)
            self.p.access.require(uow, p, "read", TARGETS[object_type][3], parent)
            return uow.repo("challenge_memos").list(
                object_type=object_type, object_id=object_id, order_by=["-created_at"]
            )

    def respond(self, p: Principal, memo_id: str, stance: str, note: str = "") -> dict[str, Any]:
        """The reviewer records whether they agreed — a record, not a vote."""
        if stance not in STANCES:
            raise ValidationFailed(f"stance must be one of {', '.join(STANCES)}")
        if stance != "agree" and len(note.strip()) < 10:
            raise ValidationFailed(
                "Say why, in at least 10 characters, when you do not fully agree with the challenge"
            )
        with self.p.uow(p.username) as uow:
            memo = uow.repo("challenge_memos").require(memo_id)
            if memo["state"] != "ready":
                raise ValidationFailed("The memo is not written yet")
            v, parent, _ = self._load(uow, memo["object_type"], memo["object_id"])
            kind = TARGETS[memo["object_type"]][3]
            if not (p.is_admin or self.p.access.allowed(uow, p, "approve", kind, parent)):
                raise PermissionDenied(
                    "Only someone who may approve this object records a response to its challenge"
                )
            if v.get("submitted_by") == p.username:
                raise PermissionDenied(
                    "The author does not grade the challenge to their own work; a reviewer does"
                )
            row = uow.repo("challenge_memos").update(
                memo_id,
                {
                    "stance": stance,
                    "stance_by": p.username,
                    "stance_note": note.strip() or None,
                    "stance_at": utcnow(),
                },
            )
            uow.audit(
                "assistant.response_recorded",
                object_type=memo["object_type"],
                object_ref=memo["object_ref"],
                detail={"memo": memo_id, "stance": stance, "note": note.strip()},
            )
            return row


def _columns(data: bytes, fmt: str) -> list[dict[str, Any]]:
    """A sample file's structure: names, types and null counts. No rows are kept."""
    import io

    import pandas as pd

    if fmt == "csv":
        frame = pd.read_csv(io.BytesIO(data), nrows=5000)
    elif fmt == "parquet":
        frame = pd.read_parquet(io.BytesIO(data))
    elif fmt == "json":
        frame = pd.read_json(io.BytesIO(data))
    else:
        raise ValidationFailed(f"A sample may be csv, parquet or json, not '{fmt}'")
    out = []
    for name in frame.columns:
        column = frame[name]
        out.append(
            {
                "name": str(name),
                "type": _logical(column),
                "nulls": int(column.isna().sum()),
                "distinct": int(column.nunique(dropna=True)),
            }
        )
    return out


def _logical(column: Any) -> str:
    """The MAYA logical type a pandas column reads as."""
    import pandas as pd

    if pd.api.types.is_bool_dtype(column):
        return "bool"
    if pd.api.types.is_integer_dtype(column):
        return "int64"
    if pd.api.types.is_float_dtype(column):
        return "float64"
    if pd.api.types.is_datetime64_any_dtype(column):
        return "timestamp"
    parsed = pd.to_datetime(column.dropna().head(50), errors="coerce", format="ISO8601")
    if len(parsed) and parsed.notna().all():
        return "date" if (parsed.dt.normalize() == parsed).all() else "timestamp"
    return "string"
