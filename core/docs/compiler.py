"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The document compiler.

Three properties a written document cannot have, and this one does.

**Citations are checkable.** Each section records the evidence it rested on, and
citation soundness reduces to evaluating that set over the Boolean semiring —
which the evidence engine already does. "This document is supported" stops being
a claim about diligence and becomes a computation.

**Staleness is computed.** The compiler records how far the evidence chain had
got. If anything has since been recorded about this model, the document no longer
describes it, and the platform knows that without anyone remembering to check.

**Gaps are visible.** A lens that cannot fill its section says so, in the place
the content would have been. A validation heading that is blank and one that
reads "no validation has been recorded for this version" look identical to a
skim and are entirely different findings.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.docs.common import KINDS, PURPOSE, TITLES, DocumentError
from core.docs.templates import TEMPLATES
from core.evidence import EvidenceEngine
from core.log import get_logger
from db import DocumentRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)


class DocumentCompiler:
    """Compiles documents from the register and the evidence graph."""

    def __init__(self, documents: DocumentRepository, evidence: EvidenceEngine,
                 context_builder):
        self.documents, self.evidence = documents, evidence
        # A callable urn -> dict. Injected rather than imported so the compiler
        # depends on the SHAPE of the platform's state and not on nine services.
        self.build_context = context_builder

    # --------------------------------------------------------------- compile
    def compile(self, kind: str, urn: str, actor: str = "system") -> Dict[str, Any]:
        if kind not in KINDS:
            raise DocumentError("unknown_document_kind",
                                f"unknown document kind '{kind}'",
                                f"expected one of {', '.join(KINDS)}")
        ctx = self.build_context(urn)
        model = ctx["model"]

        sections: List[Dict[str, Any]] = []
        citations: List[str] = []
        missing_required: List[str] = []

        for lens in TEMPLATES[kind]:
            body, cited = lens.render(ctx)
            if body is None:
                sections.append({
                    "key": lens.key, "heading": lens.heading, "filled": False,
                    "required": lens.required,
                    "body": self._gap(lens.key, lens.required)})
                if lens.required:
                    missing_required.append(lens.key)
                continue
            sections.append({"key": lens.key, "heading": lens.heading,
                             "filled": True, "required": lens.required,
                             "body": body})
            citations.extend(cited)

        citations = sorted(set(citations))
        head, _ = self.evidence.head()
        row = {
            "model_id": model["id"],
            "model_version_id": (ctx.get("version") or {}).get("id"),
            "kind": kind, "title": f"{TITLES[kind]} — {model['name']}",
            "sections": sections, "citations": citations,
            "coverage": {
                "sections": len(sections),
                "filled": sum(1 for s in sections if s["filled"]),
                "missing_required": missing_required,
                "complete": not missing_required,
            },
            "digest": canonical_digest({"kind": kind, "urn": urn,
                                        "sections": sections}),
            "evidence_head": head, "status": "compiled",
            "compiled_at": time.time(), "compiled_by": actor,
        }
        self.documents.add(row)
        self.evidence.append("document_compiled", "model", model["id"],
                             {"document_id": row["id"], "kind": kind,
                              "citations": len(citations),
                              "complete": row["coverage"]["complete"]}, actor=actor)
        logger.info("compiled %s for %s: %d/%d sections, %d citations",
                    kind, urn, row["coverage"]["filled"], len(sections),
                    len(citations))
        return self.documents.one(id=row["id"])

    @staticmethod
    def _gap(key: str, required: bool) -> str:
        """Say what is absent, where the content would have been."""
        severity = "**This section is required and could not be filled.**" if required \
            else "*Not applicable to this model, or not yet recorded.*"
        return (f"{severity}\n\nNothing in the register supports a "
                f"`{key}` section for this model yet. That is a statement about "
                f"the model's evidence, not about this document.\n")

    # -------------------------------------------------------------- staleness
    def staleness(self, document_id: str) -> Dict[str, Any]:
        """Has anything happened to this model since the document was compiled?

        Computed from the evidence chain rather than remembered, so a document
        cannot be stale without the platform being able to say so.
        """
        doc = self.require(document_id)
        since = [n for n in self.evidence.for_subject(doc["model_id"])
                 if n["seq"] > doc["evidence_head"]
                 and n["kind"] != "document_compiled"]
        return {
            "document_id": document_id, "stale": bool(since),
            "compiled_at": doc["compiled_at"],
            "evidence_head_at_compile": doc["evidence_head"],
            "events_since": len(since),
            "kinds_since": sorted({n["kind"] for n in since}),
            "detail": (f"{len(since)} governance event(s) recorded since this "
                       f"document was compiled: "
                       f"{', '.join(sorted({n['kind'] for n in since}))}"
                       if since else "nothing has been recorded since it was compiled"),
        }

    # ------------------------------------------------------------- citations
    def verify_citations(self, document_id: str) -> Dict[str, Any]:
        """Citation soundness over the Boolean semiring: does every cited node exist?"""
        doc = self.require(document_id)
        present = {n["id"] for n in self.evidence.repo.many()}
        dangling = [c for c in doc["citations"] if c not in present]
        return {"document_id": document_id, "cited": len(doc["citations"]),
                "sound": not dangling, "dangling": dangling,
                "detail": ("every citation resolves to an evidence entry"
                           if not dangling else
                           f"{len(dangling)} citation(s) do not resolve")}

    # ----------------------------------------------------------------- render
    @staticmethod
    def markdown(doc: Dict[str, Any]) -> str:
        """The document as markdown — the form a person reads or exports."""
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(doc["compiled_at"]))
        out = [f"# {doc['title']}", "",
               f"*{PURPOSE.get(doc['kind'], '')}*", "",
               f"Compiled {when} by `{doc['compiled_by']}` · "
               f"digest `{doc['digest'][:24]}…` · "
               f"{len(doc['citations'])} citations", ""]
        for section in doc["sections"]:
            out += [f"## {section['heading']}", "", section["body"], ""]
        return "\n".join(out)

    # ------------------------------------------------------------------ query
    def get(self, document_id: str) -> Optional[Dict[str, Any]]:
        return self.documents.one(id=document_id)

    def require(self, document_id: str) -> Dict[str, Any]:
        row = self.get(document_id)
        if row is None:
            raise DocumentError("no_document", f"no document {document_id}", "")
        return row

    def for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return self.documents.many(model_id=model_id)

    def latest(self, model_id: str, kind: str) -> Optional[Dict[str, Any]]:
        rows = [d for d in self.for_model(model_id) if d["kind"] == kind]
        return rows[-1] if rows else None
