"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Handing a pack to somebody with no login, and the portal this deliberately is not.

The export pack is already the artefact: self-contained, content-addressed, with
its gaps named inside it. What was missing was a place to hand it to somebody.
The obvious answer --- an examiner portal --- is the wrong one, and the reason is
worth stating before the code.

**An examiner portal authenticates a third party into the register.** Whatever
that session can reach, they can reach: the estate view, other models, the
evidence chain, whatever gets added next year by somebody who did not think
about the portal. The blast radius of a governance platform's login is the whole
governance platform, and a supervisor asking for one model's record does not
need one.

So this is the other shape. **A share is a read of one sealed archive, not a
view of a live estate.**

  * **It points at a content digest, never a path.** A share pointing at a
    location would serve whatever is at that location later, which is how a
    document a firm handed over becomes a document nobody can reproduce.
  * **It expires, mandatorily and boundedly.** Same rule as every other window
    here: a share with no end is a standing grant of a bank's model record to
    somebody outside it, and standing grants are what least privilege is about.
  * **It may be read-capped**, because *how many times was this opened* and
    *by how many people* are different questions and only one of them has an
    answer without a login.
  * **Every read is recorded --- including the refused ones.** An expired share
    somebody tried three times is a more interesting record than one nobody
    opened, and a log holding only successes cannot tell them apart.
  * **Revocation is immediate and keeps the record.** Nothing is deleted; the
    share stops serving and the history of what it served does not.

**What this cannot do, and does not claim.** It cannot tell you *who* read ---
there is no identity behind the link, by design, because establishing one means
issuing a credential to somebody outside the firm. It records that the link was
used, from where the transport says, and it says plainly that this is weaker
than authentication. A firm that needs to know *which examiner* opened it should
send the pack by a channel that already knows.
"""
from __future__ import annotations

import secrets
import time
from typing import Any, Dict, List, Optional

from core.export.common import ExportError
from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0

OPEN, EXPIRED, REVOKED, EXHAUSTED = "open", "expired", "revoked", "exhausted"
STATES = (OPEN, EXPIRED, REVOKED, EXHAUSTED)

SERVED, REFUSED = "served", "refused"

#: The longest a share may run. A supervisory request has a response date and a
#: share should not outlive it; where one genuinely needs longer, renewing is a
#: decision somebody takes again rather than one nobody took.
MAX_DAYS = 90.0

#: Enough entropy that the link is the credential. Not a secret in the sense
#: the platform's keys are — it is a bearer token for one archive, which is
#: what makes the expiry and the cap load-bearing rather than decorative.
TOKEN_BYTES = 32


class ExportSharing:
    """Time-boxed links to sealed packs. Never a session in the register."""

    def __init__(self, shares, reads, registry, evidence, packer=None):
        self.shares, self.reads = shares, reads
        self.registry, self.evidence = registry, evidence
        self.packer = packer

    # ------------------------------------------------------------------ open
    def share(self, urn: str, *, recipient: str, purpose: str,
              days: float = 30.0, max_reads: Optional[int] = None,
              content_digest: str = "", pack_digest: str = "",
              filename: str = "", now: Optional[float] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Create a link to one pack, for one recipient, until one date."""
        model = self.registry.require(urn)
        if not (recipient or "").strip():
            raise ExportError(
                "recipient_required",
                "a share must name who it is for. A link with no named "
                "recipient is one nobody can revoke on the right grounds, and "
                "*who did we give this to* is the first question asked when it "
                "turns up somewhere unexpected",
                "name the supervisor, the firm or the person")
        if not (purpose or "").strip():
            raise ExportError(
                "purpose_required",
                "a share must say what it is for — the request it answers, the "
                "examination it belongs to",
                "a year later the purpose is the only part that explains why a "
                "model record left the building")
        if days <= 0 or days > MAX_DAYS:
            raise ExportError(
                "window_out_of_range",
                f"a share may run at most {MAX_DAYS:.0f} days, and this asks "
                f"for {days:.0f}",
                "a supervisory request has a response date and a share should "
                "not outlive it. Where one genuinely needs longer, renew it — "
                "which is a decision somebody takes again")
        if not (content_digest or "").strip():
            raise ExportError(
                "content_digest_required",
                "a share points at a pack **by content**, not by path",
                "cut the pack first and share its content digest. A share "
                "pointing at a location would serve whatever is at that "
                "location later, which is how a document a firm handed over "
                "becomes one nobody can reproduce")

        moment = now if now is not None else time.time()
        row = {
            "reference": secrets.token_urlsafe(TOKEN_BYTES),
            "model_id": model["id"], "urn": model["urn"],
            "content_digest": content_digest.strip(),
            "pack_digest": (pack_digest or content_digest).strip(),
            "filename": filename, "recipient": recipient.strip(),
            "purpose": purpose.strip(),
            "expires_at": moment + days * DAY,
            "max_reads": int(max_reads) if max_reads else None,
            "reads": 0, "status": OPEN,
            "created_by": actor, "created_at": moment,
            "revoked_at": None, "revoked_by": None, "revoke_reason": "",
        }
        with self.evidence.recording():
            self.shares.add(row)
            self.evidence.append(
                "export_shared", "model", model["id"],
                {"urn": model["urn"], "recipient": recipient.strip(),
                 "purpose": purpose.strip(),
                 "content_digest": content_digest.strip(),
                 "expires_at": row["expires_at"],
                 "max_reads": row["max_reads"]}, actor=actor)
        logger.info("%s shared %s with %s until %s", actor, model["urn"],
                    recipient, _when(row["expires_at"]))
        return self.status(row["reference"], now=moment)

    # ------------------------------------------------------------------ read
    def open_share(self, reference: str, *, seen_from: str = "",
                   now: Optional[float] = None) -> Dict[str, Any]:
        """Serve the pack, or refuse — and record which, either way.

        A refused read is recorded too. An expired share somebody tried three
        times is a more interesting record than one nobody opened, and a log
        holding only successes cannot tell those apart.
        """
        share = self.require(reference)
        moment = now if now is not None else time.time()
        state = self._state(share, moment)
        if state != OPEN:
            self._record_read(share, REFUSED, state, moment)
            # Three literal raise sites rather than `f"share_{state}"`. A code
            # built by interpolation is invisible to the scanner that checks
            # every refusal is mapped to a status — the same defect this
            # codebase has fixed twice before, and the reason a caller would
            # have received a 500 for an expired link.
            kept = ("ask for a new one. The record of what this share served "
                    "is kept either way, because nothing here is deleted")
            if state == EXPIRED:
                raise ExportError(
                    "share_expired",
                    f"this share ended {_when(share['expires_at'])}", kept)
            if state == REVOKED:
                raise ExportError(
                    "share_revoked",
                    f"this share was revoked: {share.get('revoke_reason') or ''}"
                    .strip(), kept)
            raise ExportError(
                "share_exhausted",
                f"this share has been read its {share.get('max_reads')} "
                f"permitted time(s)", kept)
        self._record_read(share, SERVED, f"read from {seen_from or 'unstated'}",
                          moment)
        self.shares.set({"reads": share["reads"] + 1}, id=share["id"])
        logger.info("share %s served for %s (read %d)", reference[:12],
                    share["urn"], share["reads"] + 1)
        return {
            "urn": share["urn"], "content_digest": share["content_digest"],
            "pack_digest": share["pack_digest"],
            "filename": share["filename"],
            "recipient": share["recipient"], "purpose": share["purpose"],
            "reads": share["reads"] + 1,
            "identity_established": False,
            "detail": ("this is a read of a sealed archive and not a session "
                       "in the register. Nothing here establishes WHO opened "
                       "it — there is no identity behind the link, by design, "
                       "because establishing one means issuing a credential to "
                       "somebody outside the firm. A firm that needs to know "
                       "which examiner opened it should send the pack by a "
                       "channel that already knows"),
        }

    def _record_read(self, share: Dict[str, Any], outcome: str, detail: str,
                     moment: float) -> None:
        self.reads.add({"share_id": share["id"], "at": moment,
                        "outcome": outcome, "detail": detail})

    # ---------------------------------------------------------------- revoke
    def revoke(self, reference: str, reason: str, actor: str = "system",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Stop it serving. Keeps everything it served."""
        share = self.require(reference)
        if share["status"] == REVOKED:
            raise ExportError("already_revoked", "this share is already revoked",
                              "")
        moment = now if now is not None else time.time()
        with self.evidence.recording():
            self.shares.set({"status": REVOKED, "revoked_at": moment,
                             "revoked_by": actor,
                             "revoke_reason": reason.strip()},
                            id=share["id"])
            self.evidence.append(
                "export_share_revoked", "model", share["model_id"],
                {"urn": share["urn"], "recipient": share["recipient"],
                 "reason": reason.strip(), "reads": share["reads"]},
                actor=actor)
        return self.status(reference, now=moment)

    # ---------------------------------------------------------------- status
    def status(self, reference: str,
               now: Optional[float] = None) -> Dict[str, Any]:
        share = self.require(reference)
        moment = now if now is not None else time.time()
        history = self.reads.many(share_id=share["id"])
        state = self._state(share, moment)
        return {
            **share, "state": state,
            "history": history,
            "served": sum(1 for r in history if r["outcome"] == SERVED),
            "refused": sum(1 for r in history if r["outcome"] == REFUSED),
            "days_left": round((share["expires_at"] - moment) / DAY, 1),
            "identity_established": False,
            "detail": self._detail(share, state, history, moment),
        }

    @staticmethod
    def _state(share: Dict[str, Any], moment: float) -> str:
        if share["status"] == REVOKED:
            return REVOKED
        if moment > share["expires_at"]:
            return EXPIRED
        if share.get("max_reads") and share["reads"] >= share["max_reads"]:
            return EXHAUSTED
        return OPEN

    @staticmethod
    def _detail(share, state, history, moment) -> str:
        served = sum(1 for r in history if r["outcome"] == SERVED)
        refused = sum(1 for r in history if r["outcome"] == REFUSED)
        out = (f"a share of {share['urn']} with {share['recipient']}, "
               f"{state}, read {served} time(s)")
        if refused:
            out += (f" and refused {refused} — an expired share somebody tried "
                    f"repeatedly is a more interesting record than one nobody "
                    f"opened, which is why the refused reads are kept too")
        if state == OPEN:
            out += (f", ending {_when(share['expires_at'])}. It serves one "
                    f"content digest and never a path, so what the reader sees "
                    f"cannot drift from what was cut")
        return out

    def require(self, reference: str) -> Dict[str, Any]:
        row = self.shares.one(reference=reference)
        if not row:
            raise ExportError(
                "unknown_share", "no share with that reference",
                "a wrong or guessed link reads exactly like an expired one "
                "from outside, which is the correct behaviour and the reason "
                "this message says nothing about what does exist")
        return row

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every share, open first — because those are the ones still live."""
        moment = now if now is not None else time.time()
        rows: List[Dict[str, Any]] = []
        for share in self.shares.many():
            state = self._state(share, moment)
            history = self.reads.many(share_id=share["id"])
            rows.append({
                "reference": share["reference"][:12] + "…",
                "urn": share["urn"], "recipient": share["recipient"],
                "purpose": share["purpose"], "state": state,
                "reads": share["reads"],
                "refused": sum(1 for r in history if r["outcome"] == REFUSED),
                "expires_at": share["expires_at"],
                "created_by": share["created_by"],
            })
        rows.sort(key=lambda r: (r["state"] != OPEN, r["expires_at"]))
        live = [r for r in rows if r["state"] == OPEN]
        never = [r for r in rows if r["reads"] == 0 and r["state"] != OPEN]
        return {
            "shares": rows, "count": len(rows), "open": len(live),
            "never_opened": [r["reference"] for r in never],
            "is_a_portal": False,
            "detail": (
                f"{len(live)} share(s) are live and can be read right now"
                + (f", the earliest ending {_when(live[0]['expires_at'])}"
                   if live else "")
                + (f". {len(never)} expired without ever being opened, which "
                   f"is worth a look: a pack nobody read is either a request "
                   f"that went away or a link that never arrived"
                   if never else "")
                if rows else
                "nothing has been shared. Packs are being produced and handed "
                "over some other way, which is the workflow this replaces"),
        }

    @staticmethod
    def posture() -> Dict[str, Any]:
        return {
            "states": list(STATES), "max_days": MAX_DAYS,
            "is_a_portal": False, "establishes_identity": False,
            "serves": "one content-addressed archive",
            "detail": ("an examiner portal authenticates a third party INTO "
                       "the register, and whatever that session can reach they "
                       "can reach. This is the other shape: a time-boxed, "
                       "scope-limited read of one sealed archive. It cannot "
                       "tell you who read — there is no identity behind the "
                       "link, because establishing one means issuing a "
                       "credential to somebody outside the firm — and it says "
                       "so rather than implying otherwise"),
        }


def _when(stamp: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(stamp)) if stamp else "unknown"
