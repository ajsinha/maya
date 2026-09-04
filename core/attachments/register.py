"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The attachment register: documents somebody wrote, filed against what they describe.

Three rules, each the same rule that governs everything else here.

**Review is segregated.** Whoever attached a document cannot accept it. A model
owner filing their own validation report and marking it accepted is not a
control, and the fact that the document is genuine does not make the process one.

**An accepted document is immutable.** Replacing it is a supersession that names
what it replaces, so the chain of "which MDD was in force when" survives. That is
the same reasoning behind immutable versions and amendments.

**Rejection is a first-class outcome, with a reason.** A rejected document stays
in the register. The set of documents somebody tried to file and could not is
often the more interesting one, and deleting it makes a review look cleaner than
it was.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.attachments.common import KINDS, TEXT_MEDIA, AttachmentError
from core.attachments.store import DocumentStore
from core.evidence import EvidenceEngine
from core.authz.common import same_person
from core.log import get_logger
from db import AttachmentRepository

logger = get_logger(__name__)


class AttachmentRegister:
    """Attaches, reviews and supersedes documents against models and versions."""

    def __init__(self, attachments: AttachmentRepository, store: DocumentStore,
                 registry, evidence: EvidenceEngine):
        self.attachments, self.store = attachments, store
        self.registry, self.evidence = registry, evidence

    # ----------------------------------------------------------------- attach
    def attach(self, urn: str, kind: str, title: str, filename: str, data: bytes,
               media_type: str = "application/octet-stream",
               semver: Optional[str] = None, note: str = "",
               supersedes: Optional[str] = None,
               model_level: bool = False, actor: str = "system") -> Dict[str, Any]:
        """File a document against a version, or — if asked for — against the model."""
        if kind not in KINDS:
            raise AttachmentError("unknown_kind", f"unknown document kind '{kind}'",
                                  f"expected one of {', '.join(KINDS)}")
        if not title.strip():
            raise AttachmentError(
                "title_required",
                "a document needs a title somebody can find it by",
                "a filename is not a title; say what the document is")

        model = self.registry.require(urn)
        version_id = self._version_for(urn, semver, model_level)
        digest, size = self.store.put(data)

        if existing := self._same_document(model["id"], version_id, digest):
            raise AttachmentError(
                "already_attached",
                f"this exact document is already attached as '{existing['title']}'",
                "supersede that attachment if this is a replacement, or attach the "
                "revised document, which will have a different digest")

        superseded = self._resolve_supersession(supersedes, model["id"], actor)
        row = {"model_id": model["id"], "model_version_id": version_id,
               "kind": kind, "title": title.strip(), "filename": filename,
               "media_type": media_type, "digest": digest, "size_bytes": size,
               "text_indexed": int(media_type in TEXT_MEDIA),
               "state": "attached", "note": note, "attached_by": actor,
               "attached_at": time.time(), "reviewed_by": None, "reviewed_at": None,
               "review_note": "", "supersedes": superseded, "superseded_by": None}
        self.attachments.add(row)
        if superseded:
            self.attachments.set({"state": "superseded", "superseded_by": row["id"]},
                                 id=superseded)
        self.evidence.append("document_attached", "model", model["id"],
                             {"attachment_id": row["id"], "kind": kind,
                              "title": title, "digest": digest,
                              "model_version_id": version_id,
                              "supersedes": superseded}, actor=actor)
        logger.info("attached %s '%s' to %s", kind, title, urn)
        return self.attachments.one(id=row["id"])

    def _version_for(self, urn: str, semver: Optional[str],
                     model_level: bool) -> Optional[str]:
        """Version-level by default; model-level has to be asked for.

        A document filed at model level floats free of what it describes, which
        is how an MDD for v2.1 ends up against a model serving v2.4.
        """
        if model_level:
            return None
        if semver:
            version = self.registry.version(urn, semver)
            if not version:
                raise AttachmentError("no_version_for_document",
                                      f"no version {semver} for {urn}",
                                      "attach to a version that exists")
            return version["id"]
        versions = self.registry.versions(urn)
        if not versions:
            raise AttachmentError(
                "no_version_to_attach_to",
                f"{urn} has no versions, and a document filed at model level has "
                "to say so",
                "create a version first, or pass model_level to file this against "
                "the model itself")
        return versions[-1]["id"]

    def _same_document(self, model_id: str, version_id: Optional[str],
                       digest: str) -> Optional[Dict[str, Any]]:
        for row in self.attachments.current_for_model(model_id):
            if row["digest"] == digest and row["model_version_id"] == version_id:
                return row
        return None

    def _resolve_supersession(self, supersedes: Optional[str], model_id: str,
                              actor: str) -> Optional[str]:
        if not supersedes:
            return None
        prior = self.attachments.one(id=supersedes)
        if prior is None or prior["model_id"] != model_id:
            raise AttachmentError("no_such_attachment",
                                  f"no attachment {supersedes} on this model", "")
        if prior["state"] == "superseded":
            raise AttachmentError("already_superseded",
                                  f"'{prior['title']}' has already been superseded",
                                  "supersede the current document instead")
        return supersedes

    # ----------------------------------------------------------------- review
    def review(self, attachment_id: str, accept: bool, actor: str,
               note: str = "") -> Dict[str, Any]:
        """Accept or reject. Never by whoever attached it."""
        row = self.require(attachment_id)
        if row["state"] != "attached":
            raise AttachmentError("already_reviewed",
                                  f"this document is already '{row['state']}'",
                                  "supersede it if it needs replacing")
        if same_person(actor, row["attached_by"]):
            raise AttachmentError(
                "self_review",
                f"{actor} attached this document and cannot also accept it",
                "review must be by somebody other than whoever filed it; a genuine "
                "document filed and approved by one person is still not a control")
        if not accept and not note.strip():
            raise AttachmentError(
                "reason_required",
                "rejecting a document requires a reason",
                "say what is wrong with it; the rejection stays in the register")

        state = "accepted" if accept else "rejected"
        self.attachments.set({"state": state, "reviewed_by": actor,
                              "reviewed_at": time.time(), "review_note": note},
                             id=attachment_id)
        self.evidence.append(f"document_{state}", "model", row["model_id"],
                             {"attachment_id": attachment_id, "kind": row["kind"],
                              "title": row["title"], "note": note}, actor=actor)
        return self.attachments.one(id=attachment_id)

    # ------------------------------------------------------------------ read
    def content(self, attachment_id: str) -> bytes:
        """The bytes, verified against the digest that was reviewed."""
        row = self.require(attachment_id)
        return self.store.get(row["digest"])

    def text(self, attachment_id: str) -> Optional[str]:
        """The document as text, where the format allows it to be read.

        Formats that cannot be read out are stored and served but not indexed,
        and this returns None rather than a guess. Machine review and retrieval
        will need this; saying honestly that a PDF has not been read is better
        than pretending it has.
        """
        row = self.require(attachment_id)
        if not row["text_indexed"]:
            return None
        return self.store.get(row["digest"]).decode("utf-8", errors="replace")

    # ----------------------------------------------------------------- query
    def get(self, attachment_id: str) -> Optional[Dict[str, Any]]:
        return self.attachments.one(id=attachment_id)

    def require(self, attachment_id: str) -> Dict[str, Any]:
        row = self.get(attachment_id)
        if row is None:
            raise AttachmentError("no_attachment", f"no attachment {attachment_id}", "")
        return row

    def for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return self.attachments.current_for_model(model_id)

    def for_version(self, version_id: str) -> List[Dict[str, Any]]:
        return self.attachments.for_version(version_id)

    def history(self, model_id: str) -> List[Dict[str, Any]]:
        """Everything, superseded and rejected included.

        The documents somebody tried to file and could not are often the more
        interesting set, and a register that hides them makes a review look
        cleaner than it was.
        """
        return self.attachments.many(model_id=model_id)

    def status(self, model_id: str) -> Dict[str, Any]:
        """What documentation this model actually has on file."""
        current = self.for_model(model_id)
        by_kind: Dict[str, int] = {}
        for row in current:
            by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
        accepted = [r for r in current if r["state"] == "accepted"]
        awaiting = [r for r in current if r["state"] == "attached"]
        rejected = [r for r in self.history(model_id) if r["state"] == "rejected"]
        return {
            "attached": len(current), "accepted": len(accepted),
            "awaiting_review": len(awaiting), "rejected": len(rejected),
            "by_kind": by_kind,
            "kinds_present": sorted(by_kind),
            "unindexed": sum(1 for r in current if not r["text_indexed"]),
            "detail": (f"{len(accepted)} accepted, {len(awaiting)} awaiting review"
                       + (f", {len(rejected)} rejected" if rejected else "")
                       if current else "no documents attached"),
        }
