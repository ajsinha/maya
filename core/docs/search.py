"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Finding the sentence in the document nobody remembered filing.

`attachment.text_indexed` has been on the row since attachments were written. It
was set at upload, read by one status count, and **nothing ever searched
anything** — the third instance tonight of a field that describes an obligation
and reaches no decision. A register that can serve a document and cannot find one
is a filing cabinet with a URL.

**Retrieval here is exact, and that is a decision rather than a shortfall.** The
requirement says *full-text and semantic search*, and semantic search means an
embedding model: something that runs, that has a version, that drifts, and that
would have to be registered under the very rules this platform enforces — a
MAYA that shipped an unregistered model to search its own registry would be
ridiculous. More practically, the question a supervisor asks is *show me where
you wrote that*, and an approximate answer to that question is worse than none,
because the reader cannot tell a miss from an absence. So: exact terms, ranked,
with the **line quoted**, and the semantic half named as a deliberate absence
with what it would take.

**A document nobody can read is reported as unread, not skipped.** A PDF filed
against a model and never extracted is invisible to a search, and invisible is
exactly how it looks to somebody who searched and found nothing. Every answer
carries how many documents could not be read, because a clean empty result over
an unindexed corpus is the most misleading answer this could give.

**Results are scoped like everything else.** A search that ignored who is asking
would be a way to read the contents of models a reader cannot see, one grep at a
time — which is the same leak the model page's scope check exists to prevent,
arriving through a search box.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

#: How much of the matching line to quote. Enough to read, short enough that a
#: result list is not a way to reconstruct the whole document a term at a time.
QUOTE = 200

#: How many results one query returns.
DEFAULT_LIMIT = 25
MAX_LIMIT = 200

#: Words too common to rank on. Deliberately tiny: a long stop list is a way to
#: make a search quietly not find things, and in a corpus of validation reports
#: "model" and "risk" are in every document without being noise in any query
#: somebody actually types.
STOP = frozenset(("the", "a", "an", "of", "and", "or", "to", "in", "is",
                  "it", "for", "on", "that", "this", "with", "as", "by"))


def terms(query: str) -> List[str]:
    """The words a query is actually about."""
    found = [w for w in re.findall(r"[\w.-]+", (query or "").lower())
             if w not in STOP and len(w) > 1]
    return found


class DocumentSearch:
    """Searches the text of filed documents, and says what it could not read."""

    def __init__(self, attachments, registry, authz=None):
        self.attachments, self.registry = attachments, registry
        # Who may see which model. Optional, and its absence is REPORTED rather
        # than treated as everybody-may-see-everything: a search that ignored
        # scope would be a way to read models a reader cannot see, one query at
        # a time.
        self.authz = authz

    # ---------------------------------------------------------------- search
    def search(self, query: str, *, principal: Optional[Dict[str, Any]] = None,
               urn: str = "", kind: str = "",
               limit: int = DEFAULT_LIMIT) -> Dict[str, Any]:
        """Every filed document containing these terms, best match first."""
        from core.docs.common import DocumentError

        wanted = terms(query)
        if not wanted:
            raise DocumentError(
                "empty_query",
                "a search with no terms in it would return the whole corpus, "
                "which is not a search",
                "give a word or two; very common words are ignored, so a query "
                "of only those counts as none")
        if limit < 1 or limit > MAX_LIMIT:
            raise DocumentError(
                "limit_out_of_range",
                f"{limit} is not a page size; the bound is 1 to {MAX_LIMIT}")

        visible = self._visible(principal, urn)
        hits, unread, searched = [], [], 0
        for row in self._candidates(visible, kind):
            body = self._text(row)
            if body is None:
                unread.append({"attachment_id": row["id"],
                               "title": row.get("title"),
                               "media_type": row.get("media_type"),
                               "urn": visible.get(row["model_id"])})
                continue
            searched += 1
            match = self._match(body, wanted)
            if match["score"]:
                hits.append({
                    "attachment_id": row["id"], "title": row.get("title"),
                    "kind": row.get("kind"), "filename": row.get("filename"),
                    "urn": visible.get(row["model_id"]),
                    "state": row.get("state"), **match})
        hits.sort(key=lambda h: (-h["score"], h["title"] or ""))
        page = hits[:limit]
        return {
            "query": query, "terms": wanted, "results": page,
            "matches": len(hits), "documents_searched": searched,
            "could_not_be_read": unread,
            "scoped": self.authz is not None,
            "detail": self._detail(page, hits, searched, unread),
        }

    def _candidates(self, visible: Dict[str, str],
                    kind: str) -> Iterable[Dict[str, Any]]:
        for model_id in visible:
            for row in self.attachments.for_model(model_id):
                if kind and row.get("kind") != kind:
                    continue
                yield row

    def _visible(self, principal: Optional[Dict[str, Any]],
                 urn: str) -> Dict[str, str]:
        """model id -> urn, for the models this reader may see."""
        models = self.registry.list()
        if urn:
            models = [m for m in models if m.get("urn") == urn]
        if self.authz is not None and principal is not None:
            models = self.authz.visible(principal, models)
        return {m["id"]: m.get("urn") for m in models}

    def _text(self, row: Dict[str, Any]) -> Optional[str]:
        """The document's text, or `None` where it was never extracted."""
        if not row.get("text_indexed"):
            return None
        return self.attachments.text(row["id"])

    @staticmethod
    def _match(body: str, wanted: Sequence[str]) -> Dict[str, Any]:
        """How well this document answers the query, and where.

        Scored on how many of the query's terms appear at all, then on how
        often — that ordering matters, because a document mentioning every term
        once is a better answer to a two-word question than one mentioning the
        first term forty times and the second never.
        """
        lowered = body.lower()
        present = [w for w in wanted if w in lowered]
        if not present:
            return {"score": 0.0, "quote": "", "line": None,
                    "terms_found": []}
        occurrences = sum(lowered.count(w) for w in present)
        score = len(present) * 1000 + min(occurrences, 999)

        quote, line_no = "", None
        for i, line in enumerate(body.splitlines(), start=1):
            if any(w in line.lower() for w in present):
                quote, line_no = line.strip()[:QUOTE], i
                break
        return {"score": float(score), "quote": quote, "line": line_no,
                "terms_found": present,
                "terms_missing": [w for w in wanted if w not in present]}

    @staticmethod
    def _detail(page, hits, searched, unread) -> str:
        out = (f"{len(hits)} document(s) match, out of {searched} searched"
               if hits else
               f"nothing matches, out of {searched} document(s) searched")
        if unread:
            out += (f". {len(unread)} filed document(s) could NOT be read and "
                    f"were not searched — a PDF filed and never extracted is "
                    f"invisible to a search, and invisible is exactly how it "
                    f"looks to somebody who searched and found nothing")
        out += (". Retrieval here is exact rather than semantic: the question "
                "a supervisor asks is *show me where you wrote that*, and an "
                "approximate answer to it is worse than none, because the "
                "reader cannot tell a miss from an absence")
        return out

    # -------------------------------------------------------------- coverage
    def coverage(self, principal: Optional[Dict[str, Any]] = None
                 ) -> Dict[str, Any]:
        """How much of the corpus a search can actually see.

        The figure to read before any result. A search over a corpus that is
        forty percent unextracted is a search whose empty answers mean nothing.
        """
        visible = self._visible(principal, "")
        readable, unread = 0, 0
        by_type: Dict[str, int] = {}
        for model_id in visible:
            for row in self.attachments.for_model(model_id):
                if row.get("text_indexed"):
                    readable += 1
                else:
                    unread += 1
                    media = row.get("media_type") or "unknown"
                    by_type[media] = by_type.get(media, 0) + 1
        total = readable + unread
        return {
            "documents": total, "readable": readable, "unread": unread,
            "unread_by_media_type": by_type,
            "coverage": round(readable / total, 4) if total else 0.0,
            "semantic_search": self.semantic(),
            "detail": (
                f"{readable} of {total} filed document(s) can be searched"
                + (f". The other {unread} are formats this platform stores and "
                   f"serves but has never read — mostly "
                   f"{self._commonest(by_type)} "
                   f"— and a search whose empty answers come from an "
                   f"unextracted corpus means nothing"
                   if unread else ", which is all of them")
                if total else
                "no document has been filed against any model you can see"),
        }

    @staticmethod
    def _commonest(by_type: Dict[str, int]) -> str:
        """The format most of the unread corpus is in, for the detail line."""
        if not by_type:
            return "unknown"
        return sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    @staticmethod
    def semantic() -> Dict[str, Any]:
        """Why there is no semantic search, and what it would take.

        Named rather than omitted. An absence somebody has to discover is
        indistinguishable from an oversight.
        """
        return {
            "available": False,
            "why_not": (
                "semantic search means an embedding model: something that "
                "runs, that has a version, that drifts, and that would have to "
                "be registered under the very rules this platform enforces. A "
                "MAYA that shipped an unregistered model to search its own "
                "registry would be ridiculous"),
            "what_it_would_take": (
                "register the embedding model like any other — a version, a "
                "trainability class, a warrant to run it — and treat the index "
                "as a parameter set that goes stale when the model moves. The "
                "canary machinery in core/assist/canaries.py already watches "
                "for exactly that kind of movement"),
            "meanwhile": (
                "exact retrieval answers the question a supervisor actually "
                "asks, which is *show me where you wrote that*"),
        }
