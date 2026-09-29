"""
Documents generated from a model's record: model cards, validation reports and model
documentation, each from a template a firm can replace (``maya.documents.render``).

**Facts, then prose.** A document is built from a *snapshot* of what MAYA holds about one
model version -- its mathematics and contract, its code checks, its warrants, certificate,
blind scores, fairness evidence, challengers, findings, reviews, covenants and monitoring --
gathered through the same services, and the same read permissions, as every screen. The
snapshot is hashed, and the hash is stored with the document, so "which facts was this
written from" has an answer.

**Drafted, never concluded.** A template asks for prose with ``ai()``; each request goes to
the AI gateway under a named model profile, with the facts and an instruction that forbids
inventing anything the facts do not say. What comes back is labelled on the page as drafted
by that provider and model, and as not reviewed, until someone other than the person who
generated the document approves it. A conclusion -- *is this model fit for use* -- is not a
section a template can draft: the built-in validation report leaves it to the validator.

**Without a model, still a document.** With drafting off, or no provider configured, each
``ai()`` section is marked as not drafted and the rest of the document renders in full.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import hashlib
import json
from typing import Any

from maya.core import djson
from maya.core.errors import NotFound, PermissionDenied, ValidationFailed
from maya.core.version import VERSION
from maya.documents import KINDS
from maya.documents import render as R
from maya.llm.base import LlmUnavailable
from maya.security.authz import Principal
from maya.services import refs

JOB = "documents.generate"
FACTS_LIMIT = 60_000  # characters of facts handed to a model per section
SYSTEM = (
    "You write sections of model risk management documents for a bank. Use only the facts "
    "you are given, as JSON. Never invent a number, a name, a date, a result or a judgement "
    "the facts do not contain; where they do not say, write 'not recorded'. Do not conclude "
    "whether the model is fit for use: that is the validator's decision. Write plain "
    "Markdown prose (lists are fine), no headings, in the length you are asked for."
)


def _clean(value: Any) -> Any:
    """JSON-able, with timestamps as ISO strings."""
    return json.loads(djson.dumps(value))


class DocumentService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- templates ------------------------------------------------------------------------
    def library(self) -> R.Library:
        from pathlib import Path

        from maya.config import project_root

        raw = self.p.settings.get("documents.template_dir", "config/templates/documents") or ""
        path = Path(raw) if Path(raw).is_absolute() else project_root() / raw
        return R.Library(path)

    def templates(self, p: Principal | None = None) -> builtins.list[dict[str, Any]]:
        return [t.as_row() for t in self.library().templates()]

    # -- facts ----------------------------------------------------------------------------
    def facts(self, p: Principal, ref: str, version_no: int | None = None) -> dict[str, Any]:
        """The snapshot a document is written from, gathered under the caller's permissions."""
        model = self.p.models.get(p, ref)
        versions = sorted(model["versions"], key=lambda v: v["version_no"])
        if not versions:
            raise ValidationFailed(f"{ref} has no version to document")
        version = next((v for v in versions if v["version_no"] == version_no), versions[-1])
        ir = version.get("formula_ir") or {}
        report = version.get("artifact_report") or {}
        with self.p.uow() as uow:
            owner = (uow.repo("users").get(model["owner_id"]) or {}).get("username")
            trains = uow.repo("training_warrants").list(model_version_id=version["id"])
            execs = uow.repo("execution_warrants").list(model_version_id=version["id"])
        training = [self._training(p, t["id"]) for t in trains]
        train_ids = {t["id"] for t in trains}
        challenges = [
            self._challenge(c)
            for c in self.p.challenges.list(p)
            if c.get("champion_warrant_id") in train_ids
            or c.get("challenger_warrant_id") in train_ids
        ]
        rows, _ = self.p.inventory.rows(p)
        facts = {
            "generated_at": __import__("datetime")
            .datetime.now(__import__("datetime").timezone.utc)
            .isoformat(),
            "maya_version": VERSION,
            "model": {
                "name": model["name"],
                "namespace": model["namespace"],
                "ref": model["ref"],
                "kind": model["kind"],
                "description": model.get("description") or "",
                "tags": model.get("tags") or [],
                "owner": owner,
                "status": model.get("status"),
                "vendor": model.get("vendor") or None,
            },
            "version": {
                "number": version["version_no"],
                "state": version["state"],
                "maturity": version.get("maturity"),
                "approved_by": version.get("approved_by"),
                "approved_at": version.get("approved_at"),
                "definition_hash": version.get("definition_hash"),
                "latex": version.get("latex") or ir.get("latex") or "",
                "opaque": bool(version.get("opaque")),
                "inputs": [
                    {"name": c["name"], "type": c.get("type"), "role": c.get("role", "feature")}
                    for c in version.get("input_contract") or []
                ],
                "parameters": [
                    {"name": i["name"], "type": i.get("type"), "bounds": i.get("bounds")}
                    for i in ir.get("inputs", [])
                    if i.get("role") == "parameter"
                ],
                "constraints": [{"why": c.get("why", "")} for c in ir.get("constraints") or []],
                "outputs": ir.get("outputs") or [],
                "black_box": ir.get("black_box"),
                "artifact": (
                    {
                        "hash": version.get("artifact_hash"),
                        "passed": report.get("passed"),
                        "tier": report.get("tier"),
                        "rungs": [
                            {
                                "rung": r["rung"],
                                "name": r["name"],
                                "passed": r["passed"],
                                "detail": r["detail"],
                            }
                            for r in report.get("rungs", [])
                        ],
                    }
                    if version.get("artifact_hash")
                    else None
                ),
                "conformance": report.get("conformance"),
                "spec_document": {
                    "present": bool(version.get("spec_latex")),
                    "state": version.get("spec_state"),
                },
            },
            "versions": [
                {
                    "number": v["version_no"],
                    "state": v["state"],
                    "maturity": v.get("maturity"),
                    "approved_at": v.get("approved_at"),
                }
                for v in versions
            ],
            "governance": self._governance(p, ref),
            "training": training,
            "execution": [self._execution(p, e["id"]) for e in execs],
            "challenges": challenges,
            "inventory": next((r for r in rows if r.get("model_ref") == model["ref"]), {}),
        }
        return _clean(facts)

    def _governance(self, p: Principal, ref: str) -> dict[str, Any]:
        g = self.p.governance.profile(p, ref)
        return {
            "tier": g.get("tier"),
            "derived_tier": g.get("derived_tier"),
            "override_reason": g.get("override_reason"),
            "use": g.get("use"),
            "exposure": g.get("exposure"),
            "drivers": g.get("drivers") or [],
            "review_days": g.get("review_days"),
            "last_reviewed_at": g.get("last_reviewed_at"),
            "next_review_due": g.get("next_review_due"),
            "review_overdue": g.get("review_overdue"),
            "reviews": g.get("reviews") or [],
            "findings": [
                {
                    k: f.get(k)
                    for k in (
                        "title",
                        "detail",
                        "severity",
                        "state",
                        "owner",
                        "raised_by",
                        "due_date",
                        "closed_by",
                        "resolution",
                        "overdue",
                    )
                }
                for f in g.get("findings") or []
            ],
        }

    def _training(self, p: Principal, warrant_id: str) -> dict[str, Any]:
        w = self.p.warrants.get(p, warrant_id)
        cert = w.get("leakage_certificate") or {}
        spec = w.get("spec") or {}
        evidence = []
        for e in self.p.evidence.list(p, warrant_id):
            result = e.get("result") or {}
            segs = (result.get("segments") or {}).get("segments") or []
            evidence.append(
                {
                    "kind": e["kind"],
                    "segment_column": (result.get("segments") or {}).get("column"),
                    "flagged": [s["segment"] for s in segs if s.get("flagged")],
                    "systematic": [s["segment"] for s in segs if s.get("systematic")],
                    "segments": [
                        {k: s.get(k) for k in ("segment", "rows", "mae", "bias", "suppressed")}
                        for s in segs
                    ],
                    "importance": (result.get("importance") or [])[:5]
                    if isinstance(result.get("importance"), list)
                    else result.get("importance"),
                    "agrees": result.get("agrees"),
                    "rmse": result.get("rmse"),
                }
            )
        return {
            "name": w["name"],
            "uri": w["uri"],
            "state": w["state"],
            "status": w.get("status"),
            "featureset": w.get("featureset_ref"),
            "target": spec.get("target"),
            "seed": spec.get("seed"),
            "shape": spec.get("shape", "tabular"),
            "split": spec.get("split"),
            "certificate": {k: cert.get(k) for k in ("status", "rule", "rows_examined")}
            | {
                "exceptions": [
                    {k: x.get(k) for k in ("rule", "rows", "justification")}
                    for x in cert.get("exceptions") or []
                ]
            },
            "holdout_rows": w.get("holdout_rows"),
            "holdout_attempts": w.get("holdout_attempts"),
            "scores": [
                {
                    "attempt": s.get("attempt_no"),
                    "parameter_set_id": s.get("parameter_set_id"),
                    **(s.get("metrics") or {}),
                }
                for s in w.get("holdout_scores") or []
            ],
            "parameter_sets": [
                {k: ps.get(k) for k in ("id", "state", "values", "verified_data", "created_by")}
                for ps in w.get("parameter_sets") or []
            ],
            "evidence": evidence,
            "sealed_at": w.get("sealed_at"),
        }

    def _execution(self, p: Principal, ew_id: str) -> dict[str, Any]:
        e = self.p.execution.get(p, ew_id)
        spec = e.get("spec") or {}
        try:
            monitoring = self.p.monitoring.warrant(p, ew_id).get("status")
        except Exception:  # noqa: BLE001 - monitoring is a reading; its absence is not an error
            monitoring = None
        reports = e.get("reports") or []
        return {
            "name": e["name"],
            "uri": e["uri"],
            "state": e["state"],
            "status": e.get("status"),
            "environments": spec.get("environments") or [],
            "contact": spec.get("contact"),
            "valid_from": e.get("valid_from"),
            "valid_to": e.get("valid_to"),
            "covenants": [
                {k: c.get(k) for k in ("kind", "attr", "min", "max")}
                for c in spec.get("covenants") or []
            ],
            "limits": spec.get("limits") or {},
            "executions": e.get("executions"),
            "reports": len(reports),
            "breaches": sum(len(r.get("breaches") or []) for r in reports),
            "suspend_reason": e.get("suspend_reason"),
            "monitoring": monitoring,
        }

    @staticmethod
    def _challenge(c: dict[str, Any]) -> dict[str, Any]:
        result = c.get("result") or {}
        return {
            "champion": (c.get("champion") or {}).get("model"),
            "challenger": (c.get("challenger") or {}).get("model"),
            "metric": result.get("metric") or c.get("metric"),
            "champion_score": result.get("champion"),
            "challenger_score": result.get("challenger"),
            "difference": result.get("difference"),
            "interval": result.get("interval"),
            "challenger_wins": result.get("challenger_wins"),
            "rows": result.get("rows"),
            "verdict": result.get("verdict"),
            "state": c.get("state"),
            "rationale": c.get("rationale"),
            "decided_by": c.get("decided_by"),
        }

    # -- generating -----------------------------------------------------------------------
    def submit(
        self,
        p: Principal,
        ref: str,
        version_no: int | None,
        *,
        kind: str,
        template: str | None = None,
        use_ai: bool = True,
        profile: str | None = None,
    ) -> dict[str, Any]:
        """Queue a document; checked now, so a refusal comes back at once."""
        if kind not in KINDS:
            raise ValidationFailed(f"kind must be one of {', '.join(KINDS)}")
        chosen = self.library().get(template or kind)
        if chosen.kind != kind:
            raise ValidationFailed(f"The template '{chosen.name}' is a {chosen.kind}, not a {kind}")
        model = self.p.models.get(p, ref)  # read access, and the model exists
        with self.p.uow(p.username) as uow:
            return self.p.jobs.submit(
                uow,
                JOB,
                {
                    "ref": model["ref"],
                    "version_no": version_no,
                    "kind": kind,
                    "template": chosen.name,
                    "use_ai": bool(use_ai),
                    "profile": profile,
                    "user_id": p.user_id,
                },
                owner=p.username,
            )

    def run_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        with self.p.uow() as uow:
            p = self.p.auth.build_principal(uow, params["user_id"])
        ctx.progress(10, "gathering the facts")
        facts = self.facts(p, params["ref"], params.get("version_no"))
        # the hash says which facts, so the moment of generation is not part of it
        facts_json = json.dumps(
            {k: v for k, v in facts.items() if k != "generated_at"}, sort_keys=True
        )
        library = self.library()
        template = library.get(params["template"])
        rendered = library.render(template, facts)
        ctx.progress(30, f"{len(rendered.requests)} section(s) to draft")
        drafts, sections, used = self._draft(ctx, p, rendered.requests, facts, params)
        markdown = R.fill(rendered, drafts)
        with self.p.uow(p.username) as uow:
            mv = next(
                v
                for v in uow.repo("model_versions").list(
                    model_id=self._model_id(uow, params["ref"])
                )
                if v["version_no"] == facts["version"]["number"]
            )
            row = uow.repo("model_documents").add(
                {
                    "model_id": mv["model_id"],
                    "model_version_id": mv["id"],
                    "kind": params["kind"],
                    "template_name": template.name,
                    "template_sha256": template.sha256,
                    "facts_sha256": hashlib.sha256(facts_json.encode()).hexdigest(),
                    "provider": used.get("provider"),
                    "llm_model": used.get("model"),
                    "ai_sections": sections,
                    "markdown": markdown,
                    "content_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
                    "state": "draft",
                }
            )
            uow.audit(
                "document.generated",
                object_type="model",
                object_ref=params["ref"],
                detail={
                    "document": row["id"],
                    "kind": params["kind"],
                    "template": template.name,
                    "sections_drafted": sum(1 for s in sections if s.get("drafted")),
                    **used,
                },
            )
        return {"document_id": row["id"], "kind": params["kind"], "sections": len(sections)}

    def _draft(
        self,
        ctx: Any,
        p: Principal,
        requests: builtins.list[R.AiRequest],
        facts: dict[str, Any],
        params: dict[str, Any],
    ) -> tuple[dict[str, str], builtins.list[dict[str, Any]], dict[str, Any]]:
        drafts: dict[str, str] = {}
        sections: builtins.list[dict[str, Any]] = []
        used: dict[str, Any] = {}
        facts_json = djson.dumps(facts, indent=1)[:FACTS_LIMIT]
        for i, req in enumerate(requests, 1):
            record: dict[str, Any] = {
                "key": req.key,
                "instruction": req.instruction,
                "drafted": False,
            }
            if not params.get("use_ai"):
                drafts[req.key] = (
                    "*Not drafted: this document was generated without a language model.*"
                )
                record["reason"] = "drafting off"
            else:
                prompt = f"Task: {req.instruction}\nSection: {req.key}\nLength: at most {req.words} words.\n\nFacts (JSON):\n{facts_json}"
                try:
                    out = self.p.ai.complete(
                        p,
                        purpose=f"document:{params['kind']}:{req.key}",
                        system=SYSTEM,
                        prompt=prompt,
                        profile=req.profile or params.get("profile"),
                        object_ref=params["ref"],
                    )
                    drafts[req.key] = (
                        out.text.strip() or "*The model returned nothing for this section.*"
                    )
                    record.update(
                        drafted=True, **out.usage(), profile=req.profile or params.get("profile")
                    )
                    used = {"provider": out.provider, "model": out.model}
                except LlmUnavailable as exc:
                    drafts[req.key] = f"*Not drafted: {exc.message}*"
                    record["reason"] = exc.message
            sections.append(record)
            ctx.progress(30 + int(60 * i / max(1, len(requests))), f"drafted {req.key}")
        return drafts, sections, used

    @staticmethod
    def _model_id(uow: Any, ref: str) -> str:
        from maya.services import catalog

        model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
        return str(model["id"])

    # -- reading ----------------------------------------------------------------------------
    def list(self, p: Principal, ref: str) -> builtins.list[dict[str, Any]]:
        model = self.p.models.get(p, ref)
        with self.p.uow() as uow:
            rows = uow.repo("model_documents").list(model_id=model["id"], order_by=["-created_at"])
            numbers = {
                v["id"]: v["version_no"]
                for v in uow.repo("model_versions").list(model_id=model["id"])
            }
        return [
            {k: r[k] for k in r if k != "markdown"}
            | {"version_no": numbers.get(r["model_version_id"])}
            for r in rows
        ]

    def get(self, p: Principal, doc_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            row = uow.repo("model_documents").get(doc_id)
            if row is None:
                raise NotFound(f"No document {doc_id}")
            model = uow.repo("models").require(row["model_id"])
            self.p.access.require(uow, p, "read", "model", model)
        return dict(row)

    def labelled_markdown(self, row: dict[str, Any]) -> str:
        sections = {s["key"]: s for s in row.get("ai_sections") or []}

        def label(key: str) -> str:
            s = sections.get(key, {})
            if not s.get("drafted"):
                return "Not drafted by a language model."
            who = f"{s.get('provider')} · {s.get('model')}"
            if row.get("state") == "approved":
                return f"Drafted by {who} from the recorded facts; reviewed and approved by {row.get('approved_by')} on {str(row.get('approved_at'))[:10]}."
            return f"Drafted by {who} from the recorded facts. Not yet reviewed by a person."

        return R.labelled(row["markdown"], label)

    def render(self, p: Principal, doc_id: str, fmt: str = "md") -> dict[str, Any]:
        row = self.get(p, doc_id)
        text = self.labelled_markdown(row)
        title = f"{row['kind'].replace('_', ' ').capitalize()} — {row['template_name']}"
        stem = f"{row['kind']}-{doc_id[:8]}"
        if fmt == "md":
            return {
                "data": text.encode(),
                "content_type": "text/markdown",
                "filename": f"{stem}.md",
            }
        if fmt == "html":
            return {
                "data": R.to_html(text, title).encode(),
                "content_type": "text/html",
                "filename": f"{stem}.html",
            }
        if fmt == "pdf":
            from maya.services import typesetting

            latex = R.to_latex(text, title)
            try:
                pdf, meta = typesetting.render(self.p.settings, latex)
            except ValidationFailed as exc:
                # A LaTeX build can fail for reasons that are the host's, not the document's
                # (a font the offline build cannot fetch); the draft renderer still prints it,
                # and the result says which renderer made it and why.
                pdf, meta = typesetting.render(self.p.settings, latex, force_draft=True)
                meta = {**meta, "build_error": exc.message}
            return {
                "data": pdf,
                "content_type": "application/pdf",
                "filename": f"{stem}.pdf",
                "draft_render": meta.get("draft_render"),
                "build_error": meta.get("build_error"),
            }
        raise ValidationFailed("format must be md, html or pdf")

    def delete(self, p: Principal, doc_id: str) -> dict[str, Any]:
        """Remove a draft: whoever generated it, or anyone who may update the model. An
        approved document is part of the record and is never deleted."""
        row = self.get(p, doc_id)
        if row["state"] != "draft":
            raise ValidationFailed(
                "Only a draft document can be deleted; an approved one is part of the record"
            )
        with self.p.uow(p.username) as uow:
            model = uow.repo("models").require(row["model_id"])
            if row["created_by"] != p.username:
                self.p.access.require(uow, p, "update", "model", model)
            uow.repo("model_documents").delete(doc_id)
            ns = uow.repo("namespaces").require(model["namespace_id"])["name"]
            uow.audit(
                "document.deleted",
                object_type="model",
                object_ref=f"maya://model/{ns}/{model['name']}",
                detail={
                    "document": doc_id,
                    "kind": row["kind"],
                    "generated_by": row["created_by"],
                    "content_sha256": row["content_sha256"],
                },
            )
        return {"deleted": doc_id}

    def approve(self, p: Principal, doc_id: str) -> dict[str, Any]:
        """A person other than the one who generated it approves it, drafted sections and all."""
        row = self.get(p, doc_id)
        if row["state"] == "approved":
            raise ValidationFailed("This document is already approved")
        if row["created_by"] == p.username:
            raise PermissionDenied(
                "A document is approved by someone other than the person who generated it"
            )
        with self.p.uow(p.username) as uow:
            model = uow.repo("models").require(row["model_id"])
            self.p.access.require(uow, p, "approve", "model", model)
            from maya.core.clock import utcnow

            out = uow.repo("model_documents").update(
                doc_id, {"state": "approved", "approved_by": p.username, "approved_at": utcnow()}
            )
            ns = uow.repo("namespaces").require(model["namespace_id"])["name"]
            uow.audit(
                "document.approved",
                object_type="model",
                object_ref=f"maya://model/{ns}/{model['name']}",
                detail={
                    "document": doc_id,
                    "kind": row["kind"],
                    "content_sha256": row["content_sha256"],
                },
            )
        return {k: v for k, v in out.items() if k != "markdown"}
