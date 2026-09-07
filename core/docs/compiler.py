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
from core.docs.subjects import MODEL, MODEL_VERSION
from core.docs.templates import TEMPLATES

# Which object each compiled kind is ABOUT. A model card describes the
# model to an outside reader and outlives any one version; the rest
# describe the kernel that actually runs.
SUBJECT_OF = {"model_card": MODEL}
from core.evidence import EvidenceEngine
from core.log import get_logger
from db import DocumentRepository
from db.database import digest as canonical_digest
from core.registry.versions import latest_version

logger = get_logger(__name__)


class DocumentCompiler:
    """Compiles documents from the register and the evidence graph."""

    def __init__(self, documents: DocumentRepository, evidence: EvidenceEngine,
                 context_builder):
        self.documents, self.evidence = documents, evidence
        # A callable urn -> dict. Injected rather than imported so the compiler
        # depends on the SHAPE of the platform's state and not on nine services.
        self.build_context = context_builder

    # ---------------------------------------------------------------- render
    def render(self, kind: str, urn: str) -> Dict[str, Any]:
        """What this document would say. Writes nothing, records nothing.

        Separated from `compile` because compiling is an ACT — it authors a
        document and records that it was authored — and there are readers who
        want the content without performing the act. An export pack is the
        clearest case: cutting a pack monthly should not silently author four
        documents a month, and a pack whose own production changed the record
        would differ from the last one for no reason but that somebody had asked
        for it.

        Deliberately carries no `compiled_at`. A rendering has no moment of its
        own; the document's digest is over its kind, its subject and its
        sections, so two renderings of unchanged state are identical.
        """
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
        return {
            "model_id": model["id"],
            "model_version_id": (ctx.get("version") or {}).get("id"),
            # What this document is ABOUT, so the dossier can find it from the
            # thing it describes rather than only from the model.
            "subject_type": SUBJECT_OF.get(kind, MODEL_VERSION),
            "subject_id": ((ctx.get("version") or {}).get("id")
                           if SUBJECT_OF.get(kind, MODEL_VERSION) == MODEL_VERSION
                           else model["id"]),
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
            # The subjects this document was built from, so staleness can be
            # measured against the same set rather than against the model alone.
            "subjects": [model["id"], *(v["id"] for v in ctx.get("versions") or [])],
        }

    # --------------------------------------------------------------- compile
    def compile(self, kind: str, urn: str, actor: str = "system") -> Dict[str, Any]:
        """Render it, then author it: persisted, and recorded as having happened."""
        row = self.render(kind, urn)
        head, _ = self.evidence.head()
        row.update({"evidence_head": head, "status": "compiled",
                    "compiled_at": time.time(), "compiled_by": actor})
        with self.evidence.recording():
            self.documents.add(row)
            self.evidence.append("document_compiled", "model", row["model_id"],
                                 {"document_id": row["id"], "kind": kind,
                                  "citations": len(row["citations"]),
                                  "complete": row["coverage"]["complete"]}, actor=actor)
        logger.info("compiled %s for %s: %d/%d sections, %d citations",
                    kind, urn, row["coverage"]["filled"],
                    row["coverage"]["sections"], len(row["citations"]))
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
        # Across the model and its versions, for the same reason the compiler
        # gathers them: staleness read the model's id alone, so creating a new
        # version and taking it through a full quorum approval left the document
        # reporting "nothing has been recorded since it was compiled". The
        # worklist derives the stale-document item from this, so the item never
        # appeared on anybody's dashboard either.
        subjects = doc.get("subjects") or [doc["model_id"]]
        since = [n for n in self.evidence.for_subjects(subjects)
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
        return latest_version(rows)
