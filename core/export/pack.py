"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Building an export pack.

The gathering is not reimplemented here. The document compiler already needs
every part of a model's state to fill its lenses, and it gets that from one
context builder — so this uses the same one. Two gatherers would be two answers
to *"what is true about this model"*, and the second would drift from the first
in exactly the places nobody looks.

Three properties are worth stating, because each is a decision rather than an
implementation detail.

**The content digest excludes the manifest.** The manifest carries the time the
pack was cut, so including it would make every pack differ from every other pack
and destroy the one comparison a reader actually wants: *has anything changed
since the last one?* Digesting the content alone makes that a one-line check.

The same reasoning decides where the *act* of cutting a pack is recorded. It is
evidence — handing a complete record of a model to somebody outside is a
governance act, and who took a copy is what an auditor asks about later — but it
is recorded against the **pack**, whose identity is its content digest, and not
against the model. Recorded against the model it would land inside the next
pack's own evidence segment, and every pack would then differ from the one
before it for no reason except that somebody had taken one.

**Personal data is not re-materialised.** An evidence node flagged as carrying
personal data holds an erasable pointer rather than the data (L-18), and the pack
carries the pointer. A pack that helpfully resolved it would put personal data
into a zip on somebody's laptop, where an erasure request cannot reach it — and
the export would have quietly defeated the control the whole chain was built to
respect.

**A gap is written down.** Everything the pack could not gather appears in
`gaps.md` with the reason. A pack that silently omits what it could not reach
reads as complete, and the reader has no way to tell a thin model from a thin
export.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.export.common import (CONTENTS, DEFAULT_DOCUMENTS, FIXED_TIMESTAMP,
                                GAPS, MANIFEST, MAX_BYTES, PACK_VERSION, README,
                                ExportError)
from core.log import get_logger
from db.database import digest as canonical_digest
from hashlib import sha256

logger = get_logger(__name__)


def sha256_of(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


class ExportPacker:
    """Cuts a self-contained, digested pack for one model."""

    def __init__(self, context_builder, compiler, attachments=None,
                 evidence=None, registry=None, dossier=None):
        # The same context builder the document compiler uses. One gatherer,
        # two consumers — see the module docstring.
        self.build_context = context_builder
        self.compiler = compiler
        self.attachments = attachments
        self.evidence = evidence
        self.registry = registry
        self.dossier = dossier

    # ------------------------------------------------------------------ build
    def build(self, urn: str, *, documents: Sequence[str] = DEFAULT_DOCUMENTS,
              include_attachments: bool = True,
              actor: str = "system") -> Dict[str, Any]:
        """Gather, digest and zip. Returns the manifest and the bytes."""
        started = time.time()
        ctx = self.build_context(urn)
        model = ctx["model"]
        gaps: List[Dict[str, str]] = []
        members: Dict[str, bytes] = {}

        members["model.json"] = self._json({
            "model": model,
            "assessment": ctx.get("assessment"),
            "lifecycle": ctx.get("lifecycle"),
            "alias_history": ctx.get("alias_history"),
        })
        members["versions.json"] = self._json({"versions": ctx.get("versions") or []})
        members["validations.json"] = self._json({
            "validations": ctx.get("validations") or [],
            "results": ctx.get("results_by_validation") or {}})
        members["findings.json"] = self._json({"findings": ctx.get("findings") or []})
        members["monitoring.json"] = self._json(ctx.get("monitoring") or {})
        members["overlays.json"] = self._json(ctx.get("overlays") or {})
        members["warrants.json"] = self._json({"grants": ctx.get("warrants") or []})
        members["evidence/chain.json"] = self._json(self._evidence(ctx, gaps))
        self._add_dossier(members, gaps, urn)

        for kind in documents:
            self._add_document(members, gaps, kind, urn, actor)

        if include_attachments:
            self._add_attachments(members, gaps, ctx)

        for note in (ctx.get("_gaps") or []):
            gaps.append({"what": "context", "why": str(note)})

        members[GAPS] = self._gaps_markdown(gaps).encode()
        members[README] = self._readme(model, urn).encode()

        # Over the content only, and deliberately: the manifest carries the time
        # this was cut, so including it would make every pack differ from every
        # other one and destroy the comparison a reader actually wants.
        content_digest = canonical_digest(
            [[name, sha256_of(body)] for name, body in sorted(members.items())])

        head_seq, head_hash = self._head()
        manifest = {
            "pack_version": PACK_VERSION,
            "urn": urn,
            "model": {"name": model.get("name"), "tier": model.get("tier"),
                      "status": model.get("status"),
                      "legal_entity": model.get("legal_entity")},
            "built_at": started,
            "built_by": actor,
            "chain": {"head_seq": head_seq, "head_hash": head_hash,
                      "verified": (ctx.get("chain") or {}).get("valid")},
            "content_digest": content_digest,
            "files": [{"name": name, "bytes": len(body),
                       "digest": sha256_of(body)}
                      for name, body in sorted(members.items())],
            "gaps": len(gaps),
            "contents": CONTENTS,
        }
        members[MANIFEST] = self._json(manifest)

        archive = self._zip(members)
        if len(archive) > MAX_BYTES:
            raise ExportError(
                "pack_too_large",
                f"the pack is {len(archive) / 1e9:.1f}GB, over the "
                f"{MAX_BYTES / 1e9:.0f}GB limit",
                "narrow it — exclude attachments, or ask for fewer documents; "
                "an export nobody can open is not an export")

        logger.info("export pack for %s: %d file(s), %.1f MB, %d gap(s), "
                    "content %s", urn, len(members), len(archive) / 1e6,
                    len(gaps), content_digest[:23])
        return {"manifest": manifest, "bytes": archive,
                "digest": sha256_of(archive),
                "filename": self._filename(urn, started),
                "detail": (f"{len(members)} file(s), {len(archive) / 1e6:.1f} MB"
                           + (f", {len(gaps)} gap(s) recorded" if gaps
                              else ", nothing missing"))}

    # ------------------------------------------------------------------ parts
    def _add_document(self, members: Dict[str, bytes], gaps: List[Dict[str, str]],
                      kind: str, urn: str, actor: str) -> None:
        try:
            # RENDER, not compile. Compiling is an act — it authors a document
            # and records that it was authored — and cutting a pack monthly
            # should not silently author four documents a month. A pack whose
            # own production changed the record would also differ from the last
            # one for no reason but that somebody had asked for it.
            document = self.compiler.render(kind, urn)
        except Exception as exc:                             # noqa: BLE001
            # Never swallowed. A document that would not compile is exactly the
            # thing a supervisor should see recorded, and a pack that dropped it
            # silently would read as though the document did not apply.
            logger.warning("could not compile %s for %s: %s", kind, urn, exc)
            gaps.append({"what": f"documents/{kind}.md",
                         "why": f"the document did not compile: {exc}"})
            return
        members[f"documents/{kind}.md"] = self._markdown(document).encode()
        members[f"documents/{kind}.json"] = self._json(document)
        coverage = document.get("coverage") or {}
        for key in coverage.get("missing_required") or []:
            gaps.append({"what": f"documents/{kind}.md § {key}",
                         "why": "a required section had no evidence to fill it"})

    def _add_attachments(self, members: Dict[str, bytes],
                         gaps: List[Dict[str, str]], ctx: Dict[str, Any]) -> None:
        if self.attachments is None:
            gaps.append({"what": "attachments/",
                         "why": "this instance has no attachment register wired"})
            return
        index = []
        for row in ctx.get("attachments") or []:
            entry = {k: row.get(k) for k in
                     ("id", "kind", "title", "filename", "digest", "state",
                      "reviewed_by", "reviewed_at", "created_by", "created_at")}
            index.append(entry)
            try:
                body = self.attachments.content(row["id"])
            except Exception as exc:                         # noqa: BLE001
                logger.warning("attachment %s could not be read: %s",
                               row.get("id"), exc)
                gaps.append({"what": f"attachments/{row.get('filename')}",
                             "why": f"the stored bytes could not be read: {exc}"})
                continue
            # Named by digest as well as filename, because two models may file
            # documents with the same name and a pack that collided would
            # silently lose one of them.
            short = str(row.get("digest", ""))[7:15]
            members[f"attachments/{short}-{row.get('filename', 'document')}"] = body
        members["attachments/index.json"] = self._json({"attachments": index})

    def _add_dossier(self, members: Dict[str, bytes],
                     gaps: List[Dict[str, str]], urn: str) -> None:
        """The documentation graph, carried whole.

        The pack already holds each document; what it did not hold was *how they
        relate* — which training record belongs to which fit, and which
        featureset version a fit read. A reader outside the platform cannot walk
        the register, so the walk travels with them.
        """
        if self.dossier is None:
            gaps.append({"what": "documentation/dossier.json",
                         "why": "this instance has no dossier wired"})
            return
        try:
            graph = self.dossier.of(urn)
        except Exception as exc:                             # noqa: BLE001
            logger.warning("could not build the dossier for %s: %s", urn, exc)
            gaps.append({"what": "documentation/dossier.json",
                         "why": f"the documentation graph could not be built: {exc}"})
            return
        members["documentation/dossier.json"] = self._json(graph)
        for gap in graph.get("gaps") or []:
            gaps.append({"what": f"documentation/{gap['what']}",
                         "why": gap["why"]})

    def _evidence(self, ctx: Dict[str, Any],
                  gaps: List[Dict[str, str]]) -> Dict[str, Any]:
        """The chain segment, with personal data left as a pointer.

        The node already stores an erasable pointer rather than the data — this
        is not a redaction performed here, it is the platform's own storage
        being carried across unchanged. It is stated because an export is where
        somebody would be tempted to resolve it.
        """
        nodes = ctx.get("evidence") or []
        redacted = 0
        out = []
        for node in nodes:
            entry = dict(node)
            if entry.get("contains_personal_data"):
                redacted += 1
                entry["payload"] = {
                    "redacted": True,
                    "note": "this node carries an erasable pointer rather than "
                            "personal data (L-18); the pack carries the pointer"}
            out.append(entry)
        if redacted:
            gaps.append({
                "what": "evidence/chain.json",
                "why": f"{redacted} node(s) reference personal data and carry a "
                       f"pointer rather than the data, so the pack does too — "
                       f"resolving it here would put personal data somewhere an "
                       f"erasure request cannot reach"})
        chain = ctx.get("chain") or {}
        return {
            "nodes": out,
            # Validity only. The chain HEAD and its length are properties of the
            # moment the pack was cut, not of the model, so they live in the
            # manifest — which the content digest excludes. Putting them here
            # would make every pack differ from the last whenever anything
            # happened anywhere in the platform, which is precisely the noise
            # the content digest exists to filter out.
            "verification": {"valid": chain.get("valid"),
                             "scope": chain.get("scope")},
            "note": "verification re-derives each node's content hash from its "
                    "own fields before checking the links; where the chain stood "
                    "when this pack was cut is in manifest.json"}

    def _head(self) -> Tuple[Optional[int], Optional[str]]:
        if self.evidence is None:
            return None, None
        try:
            seq, node_hash = self.evidence.head()
            return seq, node_hash
        except Exception as exc:                             # noqa: BLE001
            logger.warning("could not read the evidence head: %s", exc)
            return None, None

    # ----------------------------------------------------------- presentation
    @staticmethod
    def _json(payload: Any) -> bytes:
        return (json.dumps(payload, indent=2, sort_keys=True, default=str)
                + "\n").encode()

    @staticmethod
    def _markdown(document: Dict[str, Any]) -> str:
        lines = [f"# {document.get('title', 'Document')}", ""]
        coverage = document.get("coverage") or {}
        lines.append(f"*{coverage.get('filled', 0)} of "
                     f"{coverage.get('sections', 0)} sections filled; "
                     f"{len(document.get('citations') or [])} citation(s); "
                     f"digest `{document.get('digest', '')[:23]}`*")
        lines.append("")
        for section in document.get("sections") or []:
            lines.append(f"## {section.get('heading', section.get('key'))}")
            lines.append("")
            lines.append(str(section.get("body", "")).strip())
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _gaps_markdown(gaps: List[Dict[str, str]]) -> str:
        if not gaps:
            return ("# Gaps\n\nNone. Every part of this pack was gathered, and "
                    "every required section of every document was filled.\n")
        lines = ["# Gaps", "",
                 "What this pack could not include, and why. An absence is "
                 "recorded rather than omitted: a pack that silently dropped "
                 "what it could not reach would read as complete, and a reader "
                 "would have no way to tell a thin model from a thin export.",
                 "", "| What | Why |", "|---|---|"]
        for gap in gaps:
            what = str(gap.get("what", "")).replace("|", "\\|")
            why = str(gap.get("why", "")).replace("|", "\\|")
            lines.append(f"| `{what}` | {why} |")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _readme(model: Dict[str, Any], urn: str) -> str:
        return f"""# Export pack — {model.get('name', urn)}

`{urn}`

This is a self-contained record of one model, cut from MAYA at a stated moment.
Everything in it was gathered from the register and the evidence chain; nothing
was written for this pack.

## How to verify it

`manifest.json` lists every file with its SHA-256. Re-hash each one and compare.

The manifest also carries a **content digest** over every file except the
manifest itself. That is the number to compare between two packs: it is the same
for two packs of the same state even though they were cut at different moments,
so *"has anything changed since the last pack?"* is one comparison rather than a
diff of a hundred files.

`chain.head_seq` and `chain.head_hash` record where the evidence chain stood.
A later pack with a higher `head_seq` means the record moved; the same head means
it did not.

## What is here

Read `gaps.md` first. It lists everything this pack could **not** include and
why — an absence is recorded rather than omitted, because a pack that quietly
dropped what it could not reach reads as complete.

Then `documents/` for the compiled documents, `evidence/chain.json` for what
supports them, and the remaining JSON files for the register state each document
was compiled from.

## What is deliberately not here

Nodes that reference **personal data** carry an erasable pointer rather than the
data, in the pack exactly as in the platform. Resolving it here would put
personal data into a file an erasure request cannot reach, which would defeat the
control rather than export it.
"""

    @staticmethod
    def _filename(urn: str, when: float) -> str:
        name = urn.split("/")[-1].replace("#", "-").replace("@", "-")
        stamp = time.strftime("%Y%m%d", time.gmtime(when))
        return f"maya-export-{name}-{stamp}.zip"

    @staticmethod
    def _zip(members: Dict[str, bytes]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            # Sorted, with a fixed timestamp: two packs of the same content
            # should differ only where their content differs, and a member order
            # that follows a dict's insertion order is a diff nobody can read.
            for name, body in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, body)
        return buffer.getvalue()
