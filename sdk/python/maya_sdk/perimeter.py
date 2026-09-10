"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The register's edges: what crosses them, and who says so.

Everything else in this SDK addresses the inside of the register — models,
versions, parameters, findings, all of it MAYA's own record. The five subjects
here are the places where that record touches something MAYA does not control,
and each of them exists because the honest answer at that boundary is narrower
than the one a platform is tempted to give.

**Timestamps.** MAYA hashes its own chain and anchors its own heads. Both are
arguments from its own clock. A token from an RFC 3161 authority is the first
statement about the chain that MAYA did not make — and it bounds the head from
*above only*: it proves a hash existed no later than a time, which is what stops
backdating, and it says nothing about deletion or about anything before the
first token.

**Plugins.** A firm's own package can add a test, a fibre, a report. What it
must not do is take effect because somebody bumped a dependency, so discovery
reads packaging metadata and imports nothing, and enabling requires
configuration to name the thing. Installed and enabled are two states, and the
gap between them is the control.

**Connectors.** MLflow, Unity Catalog and a git tree know a great deal about
models and nothing about governance. A connector parses an export and produces
*candidates for triage* — never registrations, because the five facts that make
a registration meaningful are not in the source and cannot be inferred from it.

**The scanner contract.** MAYA does not sweep drives. Somebody else's scanner
does, and this says what it has to send back: a fingerprint that survives a
re-scan, a confidence strictly below certainty, and a scope stated even when
recall is unknown. A sweep that misses the contract is refused whole.

**Shares.** A supervisor gets a pack without getting a login. The link is
time-boxed, points at a content digest rather than a path, and every read is
recorded — including the refused ones, because "the link had expired" is a fact
somebody will need in a year.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class ChainTimestamps:
    """A time somebody who is not this platform will attest to."""

    def __init__(self, maya: Any):
        self._maya = maya

    def posture(self) -> Dict[str, Any]:
        """What a timestamp proves, and the three things it does not.

        Worth reading once before wiring an authority: the control is narrower
        than the phrase *tamper-evident* suggests, and the readiness report
        says so in the same words.
        """
        return self._maya.call("GET", "/evidence/timestamps/posture")

    def coverage(self) -> Dict[str, Any]:
        """How much of the anchored chain carries a token, and from when.

        The first stamped sequence matters more than the count: nothing before
        it is covered, and a coverage figure that did not say so would read as
        a percentage of the whole chain.
        """
        return self._maya.call("GET", "/evidence/timestamps")

    def read(self, seq: int) -> Dict[str, Any]:
        """One anchored head's timestamp.

        Three states. `absent` means no token was ever taken; `unverified`
        means one is held and nothing here can check it; `verified` means a
        verifier the firm wired said so. `unverified` never collapses into
        either neighbour — a token nobody can check is not no token, and it is
        certainly not a verified one.
        """
        return self._maya.call("GET", "/evidence/timestamps",
                               params={"seq": seq})

    def stamp(self, seq: Optional[int] = None) -> Dict[str, Any]:
        """Ask the authority to attest to an anchored head. Latest by default.

        Refused when no authority is configured, rather than recording an
        untimestamped anchor as though it had been timed.
        """
        return self._maya.call("POST", "/evidence/timestamps",
                               params={"seq": seq})


class Plugins:
    """What a firm's own package declares, and whether it is switched on."""

    def __init__(self, maya: Any):
        self._maya = maya

    def contract(self) -> Dict[str, Any]:
        """The entry-point group, the axes open to extension, and the closed
        ones with the reason each is closed."""
        return self._maya.call("GET", "/plugins/contract")

    def discovered(self) -> Dict[str, Any]:
        """Everything installed under the group. Nothing is imported to find out.

        Read `state` on each row rather than the count. `seen` means installed
        and **not** enabled, which is the ordinary state and not a fault.
        """
        return self._maya.call("GET", "/plugins/discovered")

    def enable(self, axis: str, name: str) -> Dict[str, Any]:
        """Import and register one plugin, if configuration names it.

        Two refusals worth telling apart. `not_enabled` means it is installed
        and configuration does not name it — the safe state. `not_installed`
        means configuration names something that is not there, which is worse
        than it sounds: somebody believes a control is running.
        """
        return self._maya.call("POST", "/plugins/enable",
                               params={"axis": axis, "name": name})


class Connectors:
    """What another system exported, read as candidates rather than truth."""

    def __init__(self, maya: Any):
        self._maya = maya

    def describe(self) -> Dict[str, Any]:
        """Each source, what it can be read from, and — the part that matters —
        the governance facts no source holds."""
        return self._maya.call("GET", "/connectors")

    def read(self, source: str, document: Any) -> Dict[str, Any]:
        """Parse an export into candidates. Stores nothing, registers nothing.

        `document` is what the source's own CLI wrote — a dict or the JSON
        text. The connector never holds a credential and never calls the
        source's API, because a register that can read another system's
        production API on a schedule is a register that has to be trusted with
        one more thing than it needs.
        """
        return self._maya.call("POST", f"/connectors/{source}",
                               json={"document": document, "ingest": False})

    def ingest(self, source: str, document: Any) -> Dict[str, Any]:
        """Parse, then hand the candidates to the discovery register for triage.

        Still not registration: what lands is a queue of things somebody has to
        look at, each carrying what the source could not tell anyone.
        """
        return self._maya.call("POST", f"/connectors/{source}",
                               json={"document": document, "ingest": True})


class ScannerContract:
    """What a discovery scanner has to send, and what MAYA does with a sweep."""

    def __init__(self, maya: Any):
        self._maya = maya

    def contract(self) -> Dict[str, Any]:
        """The required fields, the confidence ceiling, and why MAYA does not
        run a scanner itself."""
        return self._maya.call("GET", "/scanner-contract")

    def check(self, sweep: Dict[str, Any]) -> Dict[str, Any]:
        """Everything wrong with this sweep, before anything is stored.

        Every problem, not the first — a scanner author fixing one field per
        round is re-running over forty thousand files each time.
        """
        return self._maya.call("POST", "/scanner-contract/check", json=sweep)

    def ingest(self, sweep: Dict[str, Any]) -> Dict[str, Any]:
        """Check, then hand the whole sweep to the discovery register.

        Refused as a whole or accepted as a whole. Dropping the bad rows and
        keeping the rest would mean the precision figure somebody later reads
        grades something other than the scanner that produced it.
        """
        return self._maya.call("POST", "/scanner-contract/ingest", json=sweep)

    def grade(self, scanner: str = "") -> Dict[str, Any]:
        """What the triage record says about a scanner's output.

        Precision is computable — of what it found, how much was real.
        **Recall is not**, and the answer says so: nothing here can see what a
        scanner missed, and a scanner grading itself on what it found is the
        oldest way to look good.
        """
        return self._maya.call("GET", "/scanner-contract/grade",
                               params={"scanner": scanner})


class ExportShares:
    """A time-boxed link to a sealed pack, for a reader with no login."""

    def __init__(self, maya: Any):
        self._maya = maya

    def posture(self) -> Dict[str, Any]:
        """What a share is, and the examiner portal it deliberately is not."""
        return self._maya.call("GET", "/export-shares/posture")

    def share(self, urn: str, *, recipient: str, purpose: str,
              content_digest: str, days: float = 30.0,
              max_reads: Optional[int] = None, pack_digest: str = "",
              filename: str = "") -> Dict[str, Any]:
        """Create one.

        `content_digest` is required and is the whole design: a share pointing
        at a path would serve whatever is at that path later, which is how a
        supervisor ends up reading a document nobody meant to send them.

        `recipient` and `purpose` are required too, and neither is decoration —
        in a year the question will be *who had this and why*, and a free-text
        answer written at the time beats one reconstructed afterwards.
        """
        return self._maya.call("POST", "/export-shares", json={
            "urn": urn, "recipient": recipient, "purpose": purpose,
            "content_digest": content_digest, "days": days,
            "max_reads": max_reads, "pack_digest": pack_digest,
            "filename": filename})

    def status(self, reference: str) -> Dict[str, Any]:
        """One share: its state, what it served, and what it refused."""
        return self._maya.call("GET", "/export-shares",
                               params={"reference": reference})

    def across_the_estate(self) -> Dict[str, Any]:
        """Every share, live ones first. The answer to *what is out there*."""
        return self._maya.call("GET", "/export-shares")

    def revoke(self, reference: str, reason: str = "") -> Dict[str, Any]:
        """Stop it serving.

        Keeps every read it already served. Revocation ends access; it does not
        unsend a document, and the record does not pretend otherwise.
        """
        return self._maya.call("POST", f"/export-shares/{reference}/revoke",
                               params={"reason": reason})


class DocumentRendering:
    """A compiled document as typesetting source, with the citations intact."""

    def __init__(self, maya: Any):
        self._maya = maya

    def formats(self) -> Dict[str, Any]:
        """What is emitted, and each refused format with the reason."""
        return self._maya.call("GET", "/document-rendering/formats")

    def render(self, document_id: str, fmt: str = "latex") -> Dict[str, Any]:
        """Emit the source. MAYA does not run a typesetter.

        The citation is the point. A section of a compiled document names the
        evidence nodes it rested on, and a PDF produced by flattening that away
        is a document whose claims can no longer be traced — which is the state
        every hand-written model document in every bank is already in.

        Coverage gaps are written *into* the output under a heading of their
        own. A rendering that dropped them would produce something that looks
        complete, and looking complete is the failure mode.
        """
        return self._maya.call("GET", f"/document-rendering/{document_id}",
                               params={"format": fmt})


__all__ = ["ChainTimestamps", "Connectors", "DocumentRendering",
           "ExportShares", "Plugins", "ScannerContract"]
