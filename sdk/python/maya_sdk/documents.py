"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Evidence: attaching it, compiling it, and taking it away.

Three registers, constantly mistaken for one another, answering three different
questions.

**Attachments** are the documents somebody *wrote* — a validation report in
Word, a vendor's manual a supervisor will ask for, a committee minute. MAYA
cannot generate them and must not ignore them: a register holding only what it
can compute quietly excludes most of the evidence anybody actually asks to see.
So they are stored by digest, filed against the thing they are *about*, and
accepted by somebody other than whoever filed them.

**Documents** are *compiled*, from the register and the evidence graph. Each
section names the evidence it rested on, which is what makes staleness a number
this platform computes rather than one somebody remembers — the property the
hand-written model development document in every bank cannot have.

**A package** is the whole of both, digested and zipped, for a reader who will
never be given a login. Its most important member is `gaps.md`. A pack that
omitted what it could not reach would look complete, and a document that looks
complete is worse than one that says where it is thin.

Nothing here decides anything. Which kinds exist, what a document may be filed
against, whether a subject is pinned, who may review what — every one of those
is asked for over the wire rather than carried, because a vocabulary copied into
a client goes stale silently, and it goes stale in the permissive direction.
"""
from __future__ import annotations

import mimetypes
import secrets
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from maya_sdk.models import short

#: What the upload endpoint falls back to when nothing better is known. Not a
#: guess dressed up as a fact: the register records that such a document was
#: stored but not indexed, rather than pretending its text was read.
OCTET_STREAM = "application/octet-stream"


def _form_value(value: Any) -> str:
    """A form field as the wire carries it. Booleans lowercase, nothing else."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _multipart(fields: Dict[str, Any], *, filename: str, data: bytes,
               media_type: str) -> tuple:
    """Encode one file and its fields as `multipart/form-data`.

    Written out by hand because the alternative is a dependency, and an SDK with
    a dependency tree moves the air-gap problem into the client's build rather
    than solving it. Returns the body and the content type that describes it —
    the boundary is generated per request, so it cannot collide with content
    that happens to contain the previous one.
    """
    if '"' in filename or "\r" in filename or "\n" in filename:
        raise ValueError(
            f"cannot send a filename containing a quote or a newline: {filename!r}; "
            "rename the file, or pass filename= explicitly — the alternative is "
            "silently renaming a document that is about to be filed as evidence")
    boundary = "maya" + secrets.token_hex(16)
    body = bytearray()
    for name, value in fields.items():
        if value is None:
            continue
        body += (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                 f"{_form_value(value)}\r\n").encode()
    body += (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="file"; '
             f'filename="{filename}"\r\n'
             f"Content-Type: {media_type}\r\n\r\n").encode()
    body += data
    body += f"\r\n--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


class Attachments:
    """The documents somebody wrote, filed against what they describe.

    **What a document may be about.** A document is filed against a *subject*,
    and the subject is what it is genuinely about rather than whatever was
    convenient to hang it on: the **model** (methodology, board papers — things
    true of every version), one **model version** (that kernel's specification,
    its validation report), one **parameter set** (the convergence study, the
    note explaining the morning a calibration went wrong), one **featureset
    version** (the data dictionary, the source-system agreement), one
    **feature**, or one **validation** episode. The third and fourth had nowhere
    to go before and are the two that matter most in practice — a calibrated
    model produces a parameter set every morning, and a featureset's
    documentation is read by every model fitted from it.

    A subject is always **pinned**: the featureset *version*, never the set. A
    document filed against the set would describe something that has since
    moved, which is the failure the vocabulary exists to prevent.

    Call `subjects()` for the list with its meanings rather than trusting this
    docstring to have stayed current — that is what the endpoint is for.

    Saying nothing files against the model's latest version. That is deliberate
    rather than a default worth changing: it is exactly what a caller who has
    never heard of subjects filed before subjects existed.
    """

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """What kinds of document may be filed, and what each one means.

        Read it before choosing: the kind decides who should review the document
        and what it is taken to evidence, so `other` is an honest answer and a
        mis-declared `validation_report` is not.
        """
        return self._maya.call("GET", "/attachment-kinds")

    def subjects(self) -> Dict[str, Any]:
        """What a document can be about, and which subjects are pinned.

        The same vocabulary `Documents.subjects()` publishes, offered here
        because this is where a caller has to choose one. Asked for rather than
        carried, so a subject added to the platform is reachable from an SDK
        nobody rebuilt.
        """
        return self._maya.call("GET", "/document-subjects")

    def attach(self, urn: str, path: Union[str, Path, None] = None, *,
               kind: str, title: str, content: Optional[bytes] = None,
               filename: Optional[str] = None,
               media_type: Optional[str] = None,
               semver: Optional[str] = None, note: str = "",
               supersedes: Optional[str] = None, model_level: bool = False,
               subject_type: Optional[str] = None,
               subject_id: Optional[str] = None) -> Dict[str, Any]:
        """File a document against what it is about.

        Either a `path`, or `content` bytes with a `filename`. The media type is
        guessed from the extension and the guess is a hint the caller may
        override — a `.txt` holding markdown is somebody's Tuesday. It matters
        because a format whose text can be read out is indexed for search and
        citation, and one that cannot is stored, served, and honestly recorded as
        unread.

        Version-level by default. `model_level` files against the model itself,
        and has to be asked for: a document floating free of the version it
        describes is how a bank ends up with an MDD for v2.1 filed against a
        model serving v2.4.

        `supersedes` names the attachment this replaces. It is the only way to
        change a filed document — the bytes are addressed by their digest, so an
        edit is a different document, which is a supersession somebody declares
        rather than a revision that happened quietly.

        Filing is not accepting. The document lands `attached`, and `review()`
        by somebody else moves it; this method cannot shorten that and does not
        try.
        """
        if (path is None) == (content is None):
            raise ValueError(
                "pass either a path or content bytes with a filename, not both "
                "and not neither")
        if path is not None:
            path = Path(path)
            content, filename = path.read_bytes(), filename or path.name
        if not filename:
            raise ValueError("content bytes need a filename to be filed under")
        media = media_type or mimetypes.guess_type(filename)[0] or OCTET_STREAM
        body, content_type = _multipart(
            {"urn": urn, "kind": kind, "title": title, "semver": semver,
             "note": note, "supersedes": supersedes,
             "model_level": model_level, "subject_type": subject_type,
             "subject_id": subject_id},
            filename=filename, data=content, media_type=media)
        return self._maya.call("POST", "/attachments", content=body,
                               headers={"Content-Type": content_type})

    def list(self, urn: str, *, history: bool = False) -> Dict[str, Any]:
        """What this model has on file, with the counts that say how thin it is.

        `history=True` adds the superseded and the rejected. Worth asking for
        during a review: the documents somebody tried to file and could not are
        often the more interesting set, and a register that shows only the
        current ones makes a review look cleaner than it was.

        There is no endpoint that lists attachments by *subject*. The question
        "what is filed about this parameter set" is answered by
        `Documents.dossier()`, which walks the graph on the platform — and the
        SDK does not answer it by filtering this listing, because a count that
        does not add up is how a document goes missing.
        """
        return self._maya.call("GET", "/attachments",
                               params={"urn": urn, "history": history})

    def get(self, attachment_id: str) -> Dict[str, Any]:
        """One attachment's record: its digest, its state, who reviewed it."""
        return self._maya.call("GET", f"/attachments/{attachment_id}")

    def content(self, attachment_id: str, into: Union[str, Path]) -> Path:
        """Fetch the bytes to a file. Returns the path.

        A path rather than the bytes, because a filed document is a scan of a
        two-hundred-page vendor manual as often as it is a paragraph. What comes
        back is verified against the digest that was reviewed, so this is the
        document somebody accepted rather than whatever is at that address now.
        """
        body = self._maya.call("GET", f"/attachments/{attachment_id}/content",
                               raw=True)
        destination = Path(into)
        destination.write_bytes(body)
        return destination

    def review(self, attachment_id: str, *, accept: bool,
               note: str = "") -> Dict[str, Any]:
        """Accept or reject. Never as whoever filed it.

        A rejection needs a reason and keeps its place in the register. Both are
        refusals the platform makes, not checks performed here: an owner filing
        their own validation report and marking it accepted is not a control,
        and the document being genuine does not make the process one.
        """
        return self._maya.call("POST", f"/attachments/{attachment_id}/review",
                               json={"accept": accept, "note": note})


class Documents:
    """Compiled documentation, and the graph that says what is about what."""

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """What can be compiled, and what each document is for.

        Four kinds compile from a model URN. The training record does not — it
        is about one fit rather than about a model, and it has its own call
        below for exactly that reason.
        """
        return self._maya.call("GET", "/document-kinds")

    def subjects(self) -> Dict[str, Any]:
        """The subject vocabulary, with which subjects are pinned."""
        return self._maya.call("GET", "/document-subjects")

    def list(self, urn: str) -> Dict[str, Any]:
        """Every compiled document for a model, each with its staleness.

        The staleness is computed against how far the evidence chain has moved
        since the document was cut, which is why it is in the listing rather than
        on request: a document nobody knows is stale is being relied on.
        """
        return self._maya.call("GET", "/documents", params={"urn": urn})

    def compile(self, urn: str, *, kind: str) -> Dict[str, Any]:
        """Compile a document from the register and the evidence graph.

        A section the evidence cannot support comes back as a gap naming what is
        missing, not as an empty heading. That is the whole difference between a
        compiled document and a written one, and it is why a thin model produces
        a document that says so.
        """
        return self._maya.call("POST", "/documents",
                               params={"urn": urn, "kind": kind})

    def get(self, document_id: str) -> Dict[str, Any]:
        """One document, with its staleness and whether its citations verify.

        Both are recomputed on the read rather than stored, so a document whose
        evidence has moved underneath it says so the next time anybody looks.
        """
        return self._maya.call("GET", f"/documents/{document_id}")

    def markdown(self, document_id: str) -> str:
        """The document as markdown — what a person reads, or exports."""
        return self._maya.call("GET", f"/documents/{document_id}/markdown")

    def dossier(self, urn: str) -> Dict[str, Any]:
        """Everything documented about a model, as a graph rather than a list.

        The shape carries the meaning: a training record hangs under the version
        whose fit produced it, and featureset documentation hangs under the
        featureset **version** that was read — not the set, which has since
        moved. A node with nothing filed against it is reported as a gap, so a
        reader can tell a thin model from a thin page.
        """
        return self._maya.call("GET", f"/dossiers/{short(urn)}")

    def training_record(self, parameter_set_id: str) -> Dict[str, Any]:
        """Compile the record of one fit. Authoring it is an act, and recorded.

        Every other document is about a model or a version. This one is about a
        parameter set — the moment that had no document at all. Two hundred and
        fifty calibrations a year, each a governed act with a warrant behind it,
        and none of them readable.
        """
        return self._maya.call("POST", f"/training-records/{parameter_set_id}")

    def preview_training_record(self, parameter_set_id: str) -> Dict[str, Any]:
        """What it would say, without authoring it.

        Separate from `training_record` because a dossier and an export pack want
        the content without performing the act — and a read that quietly wrote
        would make the register a record of who looked.
        """
        return self._maya.call(
            "GET", f"/training-records/{parameter_set_id}/preview")


class Packages:
    """The export pack: everything about one model, for somebody outside.

    The audience is a supervisor, an internal auditor or an acquirer's diligence
    team — somebody who will not be given a login, cannot query the platform, and
    will read it months from now. Everything about a pack follows from that. It
    is self-contained, every member is digested, the manifest is digested over
    the members, and it records the evidence chain head it was cut against, which
    is what turns *"has anything changed since?"* into a question with an answer.

    Cutting one is itself a governance act and is recorded as one: who took a
    complete copy of a model, and when, is the thing an auditor asks about later.
    """

    def __init__(self, maya):
        self._maya = maya

    def describe(self) -> Dict[str, Any]:
        """What a pack contains and what each part answers.

        Worth reading before the first one: a reader who does not know what a
        pack should contain cannot tell a thin model from a thin export.
        """
        return self._maya.call("GET", "/export-packs")

    def cut(self, urn: str, into: Union[str, Path], *,
            documents: Optional[Iterable[str]] = None,
            attachments: bool = True) -> Path:
        """Cut a pack and write the zip to a file. Returns the path.

        To a file and not into memory, deliberately: a pack carries every
        accepted attachment, and an SDK that returned the bytes to be convenient
        would be convenient until the first model with a scanned vendor manual
        in it.

        `documents` narrows which are compiled. Everything else is always
        included — a pack assembled to one caller's taste is a pack the next
        reader has to ask for again. A kind the compiler does not know becomes a
        line in `gaps.md` rather than a failed export.

        **Read `gaps.md` first.** It lists what could not be included and why. An
        absence is written down rather than omitted, because a pack that quietly
        left something out looks complete, and looking complete is the failure
        this file exists to prevent.
        """
        body = self._maya.call(
            "POST", f"/export-packs/{short(urn)}", raw=True,
            params={"documents": ",".join(documents) if documents else None,
                    "attachments": attachments})
        destination = Path(into)
        destination.write_bytes(body)
        return destination

    def manifest(self, urn: str, *, documents: Optional[Iterable[str]] = None,
                 attachments: bool = True) -> Dict[str, Any]:
        """The manifest without the bytes.

        Its own call because comparing `content_digest` against the last pack
        answers *has anything changed* without moving a hundred megabytes to find
        out that nothing has. The digest covers the members and excludes the
        manifest itself, so two packs of the same state compare equal even though
        one was cut on Tuesday.
        """
        return self._maya.call(
            "GET", f"/export-packs/{short(urn)}/manifest",
            params={"documents": ",".join(documents) if documents else None,
                    "attachments": attachments})
