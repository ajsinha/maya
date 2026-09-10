"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reviewing a compiled document, and the one thing a reviewer cannot do to it.

The requirement asks for collaborative narrative editing: comments, suggestions,
review states, history. Three of those four are here. The fourth is refused, and
the refusal is the design.

**A compiled document cannot be edited.** Every sentence in one is assembled
from the evidence chain and cites a node; editing the prose would break the
citation without changing the record it cites, producing a document that reads
correctly and is no longer traceable to anything. That is worse than a wrong
sentence, because a wrong sentence can be found.

So **the fix for a wrong sentence in a compiled document is a fix to the record
it was compiled from**, and recompiling. A reviewer's job here is to say which
section is wrong and what about it — and the comment carries what they are
asking for, from a closed list, because *please look at this* and *this is
factually wrong* are different obligations and a free-text field makes them the
same one.

**Comments attach to a digest, not to a document id.** A document is recompiled;
the question a reviewer answered was about the version they read. Carrying a
comment forward onto a recompilation would be a remark about text that may no
longer be there — and worse, one that looks answered. So a recompiled document
starts with no open comments and the previous round is reported as *raised
against an earlier version*, which is the honest state and the one that prompts
somebody to check.

**A resolution that changed the record says which node.** A comment closed with
"fixed" and nothing else is indistinguishable a year later from one closed
because the reviewer gave up, and the difference is the entire value of a review
history.

The narrative sections a firm authors itself — the ones no evidence produces —
are attachments, and attachments already carry versions. This does not build a
second editor for them.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.docs.common import DocumentError
from core.log import get_logger

logger = get_logger(__name__)

OPEN, RESOLVED, WITHDRAWN, SUPERSEDED = (
    "open", "resolved", "withdrawn", "superseded")
STATES = (OPEN, RESOLVED, WITHDRAWN, SUPERSEDED)

#: What a comment is asking for. A closed list, because the obligations differ.
ASKS: Dict[str, str] = {
    "comment": "a remark. Nothing is owed in reply, and it is here so that a "
               "reader a year later sees what a reviewer noticed",
    "clarification": "the section is unclear. The fix is usually to the "
                     "narrative source, not to the record",
    "factual": "the section says something the register does not support. This "
               "is the one that matters: the fix is to the RECORD, and the "
               "document is recompiled",
    "omission": "something that should be here is not. Almost always a missing "
                "piece of evidence rather than a missing paragraph",
    "objection": "the reviewer does not accept the section. Recorded as a "
                 "standing disagreement rather than resolved by whoever is "
                 "compiling",
}

#: Asks that must not be closed by the person who raised them. An objection
#: somebody withdraws themselves is a disagreement that never happened.
NEEDS_SOMEBODY_ELSE = ("factual", "objection")


class DocumentReview:
    """Comments on a compiled document. Never edits one."""

    def __init__(self, comments, documents, evidence, registry=None):
        self.comments, self.documents = comments, documents
        self.evidence, self.registry = evidence, registry

    # ----------------------------------------------------------------- raise
    def comment(self, document_id: str, *, section: str, body: str,
                asks_for: str = "comment", quote: str = "",
                now: Optional[float] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Say which section is wrong and what about it."""
        document = self._document(document_id)
        if asks_for not in ASKS:
            raise DocumentError(
                "unknown_ask",
                f"'{asks_for}' is not something a comment can ask for",
                f"the five are {', '.join(ASKS)} — *please look at this* and "
                f"*this is factually wrong* are different obligations, and a "
                f"free-text field makes them the same one")
        if not (body or "").strip():
            raise DocumentError(
                "body_required",
                "a comment with no body is a mark on a page",
                "say what is wrong with the section")
        sections = {s.get("key") or s.get("title")
                    for s in (document.get("sections") or [])
                    if isinstance(s, dict)}
        if sections and section not in sections:
            raise DocumentError(
                "unknown_section",
                f"'{section}' is not a section of this document",
                f"it has {', '.join(sorted(str(s) for s in sections if s))} — "
                f"a comment on a section that is not there cannot be resolved "
                f"by changing anything")
        moment = now if now is not None else time.time()
        row = {"document_id": document_id,
               # By digest. A document is recompiled, and the question this
               # reviewer answered was about the version they read.
               "document_digest": document.get("digest") or "",
               "section": section, "quote": quote.strip(),
               "body": body.strip(), "asks_for": asks_for,
               "raised_by": actor, "raised_at": moment, "state": OPEN,
               "resolution": "", "resolved_by": None, "resolved_at": None,
               "evidence_id": None}
        with self.evidence.recording():
            self.comments.add(row)
            self.evidence.append(
                "document_commented",
                "model" if document.get("model_id") else "document",
                document.get("model_id") or document_id,
                {"document": document_id, "section": section,
                 "asks_for": asks_for, "body": body.strip()}, actor=actor)
        logger.info("%s raised a %s comment on %s/%s", actor, asks_for,
                    document_id, section)
        return self.read(document_id)

    # --------------------------------------------------------------- resolve
    def resolve(self, comment_id: str, resolution: str, *,
                evidence_id: str = "", now: Optional[float] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Close a comment, saying what was done — and which node if any.

        A comment closed with "fixed" and nothing else is indistinguishable a
        year later from one closed because the reviewer gave up, and the
        difference is the entire value of a review history.
        """
        comment = self.require(comment_id)
        if comment["state"] != OPEN:
            raise DocumentError(
                "comment_closed",
                f"this comment is {comment['state']}",
                "raise another against the current document")
        if not (resolution or "").strip():
            raise DocumentError(
                "resolution_required",
                "closing a comment needs a sentence about what was done",
                "say what changed, or say that nothing did and why — the "
                "second is a legitimate resolution and an invisible one if it "
                "is not written down")
        if comment["asks_for"] in NEEDS_SOMEBODY_ELSE \
                and comment["raised_by"] == actor:
            raise DocumentError(
                "raiser_may_not_close",
                f"a '{comment['asks_for']}' comment may not be closed by the "
                f"person who raised it",
                "an objection somebody withdraws themselves is a disagreement "
                "that never happened; withdraw it explicitly instead, which is "
                "recorded as what it is")
        moment = now if now is not None else time.time()
        with self.evidence.recording():
            self.comments.set({"state": RESOLVED,
                               "resolution": resolution.strip(),
                               "resolved_by": actor, "resolved_at": moment,
                               "evidence_id": evidence_id or None},
                              id=comment_id)
            self.evidence.append(
                "document_comment_resolved", "document",
                comment["document_id"],
                {"comment": comment_id, "section": comment["section"],
                 "asks_for": comment["asks_for"],
                 "resolution": resolution.strip(),
                 "changed_the_record": bool(evidence_id),
                 "raised_by": comment["raised_by"]}, actor=actor)
        logger.info("%s resolved comment %s%s", actor, comment_id,
                    " by changing the record" if evidence_id else "")
        return self.read(comment["document_id"])

    def withdraw(self, comment_id: str, reason: str, actor: str = "system",
                 now: Optional[float] = None) -> Dict[str, Any]:
        """Take a comment back. Recorded as what it is, never deleted."""
        comment = self.require(comment_id)
        if comment["raised_by"] != actor:
            raise DocumentError(
                "not_your_comment",
                f"this comment is {comment['raised_by']}'s",
                "only the person who raised a comment may withdraw it; "
                "anybody else closing it is resolving it, and the two read "
                "very differently in a review history")
        moment = now if now is not None else time.time()
        with self.evidence.recording():
            self.comments.set({"state": WITHDRAWN,
                               "resolution": reason.strip(),
                               "resolved_by": actor, "resolved_at": moment},
                              id=comment_id)
            self.evidence.append(
                "document_comment_withdrawn", "document",
                comment["document_id"],
                {"comment": comment_id, "reason": reason.strip()}, actor=actor)
        return self.read(comment["document_id"])

    # ------------------------------------------------------------------ read
    def read(self, document_id: str,
             now: Optional[float] = None) -> Dict[str, Any]:
        """A document's review state, against the version it was raised on."""
        document = self._document(document_id)
        digest = document.get("digest") or ""
        rows = self.comments.many(document_id=document_id)
        current = [r for r in rows if r["document_digest"] == digest]
        earlier = [r for r in rows if r["document_digest"] != digest]
        opened = [r for r in current if r["state"] == OPEN]
        blocking = [r for r in opened
                    if r["asks_for"] in NEEDS_SOMEBODY_ELSE]
        by_section: Dict[str, int] = {}
        for row in opened:
            by_section[row["section"]] = by_section.get(row["section"], 0) + 1
        return {
            "document_id": document_id, "digest": digest,
            "kind": document.get("kind"), "title": document.get("title"),
            "comments": current, "open": len(opened),
            "raised_against_an_earlier_version": len(earlier),
            "unresolved_factual_or_objection": [r["id"] for r in blocking],
            "by_section": by_section,
            "editable": False,
            "detail": self._detail(current, opened, blocking, earlier),
        }

    @staticmethod
    def _detail(current, opened, blocking, earlier) -> str:
        if not current and not earlier:
            return ("nobody has commented on this version. A compiled document "
                    "cannot be edited — every sentence cites a node, and "
                    "editing the prose would break the citation without "
                    "changing the record, producing something that reads "
                    "correctly and is no longer traceable to anything")
        out = (f"{len(opened)} open of {len(current)} comment(s) on this "
               f"version")
        if blocking:
            out += (f", {len(blocking)} of them factual or an objection — the "
                    f"fix for those is to the **record**, not to the prose, and "
                    f"then a recompilation")
        if earlier:
            out += (f". {len(earlier)} comment(s) were raised against an "
                    f"earlier compilation of this document and are not carried "
                    f"forward: a comment moved onto a recompilation is a remark "
                    f"about text that may no longer be there, and worse, one "
                    f"that looks answered")
        return out

    def require(self, comment_id: str) -> Dict[str, Any]:
        row = self.comments.one(id=comment_id)
        if not row:
            raise DocumentError("unknown_comment",
                                f"no comment '{comment_id}'", "")
        return row

    def _document(self, document_id: str) -> Dict[str, Any]:
        row = self.documents.one(id=document_id)
        if not row:
            raise DocumentError("unknown_document",
                                f"no document '{document_id}'",
                                "compile one first")
        return row

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every document under review, most contested first."""
        moment = now if now is not None else time.time()
        seen = {c["document_id"] for c in self.comments.many()}
        rows = [self.read(d, now=moment) for d in sorted(seen)]
        rows.sort(key=lambda r: (-len(r["unresolved_factual_or_objection"]),
                                 -r["open"]))
        contested = [r for r in rows if r["unresolved_factual_or_objection"]]
        stale = [r for r in rows if r["raised_against_an_earlier_version"]]
        return {
            "documents": rows, "count": len(rows),
            "open": sum(r["open"] for r in rows),
            "contested": [r["document_id"] for r in contested],
            "with_comments_on_an_earlier_version":
                [r["document_id"] for r in stale],
            "editable": False,
            "detail": (
                f"{sum(r['open'] for r in rows)} open comment(s) across "
                f"{len(rows)} document(s)"
                + (f", {len(contested)} of which carry an unresolved factual "
                   f"comment or objection — a compiled document with one "
                   f"outstanding is one whose record somebody says is wrong"
                   if contested else "")
                if rows else
                "no document carries a comment. Worth reading as a fact about "
                "how documents are reviewed here rather than about their "
                "quality: a review that happens in email leaves the register "
                "exactly this empty"),
        }

    @staticmethod
    def asks() -> Dict[str, Any]:
        return {
            "asks": [{"asks_for": k, "means": v} for k, v in ASKS.items()],
            "needs_somebody_else": list(NEEDS_SOMEBODY_ELSE),
            "states": list(STATES), "editable": False,
            "detail": ("a compiled document cannot be edited: every sentence "
                       "cites a node, and editing the prose would break the "
                       "citation without changing the record it cites. The fix "
                       "for a wrong sentence is a fix to the RECORD, and a "
                       "recompilation"),
        }
