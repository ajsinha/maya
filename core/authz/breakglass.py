"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Emergency elevation, with a second signature, an end, and somebody reading it
afterwards.

The `admin` role is *described* as break-glass and is exempt from the
incompatible-roles check. That is not break-glass. It is a standing account that
happens to be powerful — and a standing powerful account is precisely the thing
break-glass exists to replace. Break-glass is defined by being **closed by
default**: asked for, agreed to by somebody else, ending on its own, and read
afterwards by a person who was not in the incident.

**The detection insight, and the reason this is worth building rather than
policing.** You cannot find break-glass abuse by watching break-glass — anybody
misusing it would simply not open one. What finds it is watching what happened
**without** one: privileged acts by an administrator during no open grant. That
number is on the chain already, it is derived rather than reported by the person
being examined, and it is the one figure on this screen that an examiner should
read first.

**A unilateral grant is allowed, and marked.** Dual authorisation means the
second person cannot be the first, and at three in the morning there may be only
one person awake. Refusing outright is how institutions end up with a shared
password in a safe, which is worse in every respect: no name, no reason, no
window and no review. So a single-person grant opens, gets a **shorter window**,
is flagged `unilateral` and its review is not optional.

**Expiry is derived, never a flag somebody clears.** A grant that is only closed
when a batch runs is a grant that is open whenever the batch is not running, and
that is exactly when it matters. Every read computes it from the window.

**The review is mandatory in the only sense that means anything: an unreviewed
grant refuses the next one.** Otherwise "mandatory post-hoc review" is a to-do
list, and a to-do list is what every unread break-glass log in the world already
is.

**What was done under it is derived, not logged twice.** The evidence chain
already records every act with its actor and its time, so *what happened under
this grant* is a fold of the chain over the window by that principal. A second
log would be a second thing to keep in step, and the first time they disagreed
nobody would know which was true.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.authz.common import AuthzError
from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0
HOUR = 3600.0

STATES = ("requested", "open", "expired", "closed")

#: How long a grant lasts when a second person authorised it. Four hours is long
#: enough to work through an incident and short enough that nobody treats it as
#: a working arrangement.
WINDOW_HOURS = 4.0

#: How long a unilateral grant lasts. Shorter on purpose: it is the weaker form
#: and should cost more to keep using. Somebody who needs longer can get a
#: second signature by then.
UNILATERAL_WINDOW_HOURS = 1.0

#: How long after it closes before the review is overdue.
REVIEW_DAYS = 5.0

#: What a reviewer may conclude. Closed, because *looked at it* is not a
#: conclusion and a review with no verdict reads exactly like one nobody did.
OUTCOMES: Dict[str, str] = {
    "appropriate": "the elevation was warranted and what was done under it "
                   "matches the reason given",
    "excessive": "the elevation was warranted and more was done under it than "
                 "the reason covers",
    "unwarranted": "the elevation should not have been granted",
}


class BreakGlass:
    """Requests, authorises, expires and reviews emergency elevation."""

    def __init__(self, repo, principals, evidence, findings=None):
        self.repo, self.principals = repo, principals
        self.evidence, self.findings = evidence, findings

    # -------------------------------------------------------------- request
    def request(self, principal: str, reason: str,
                actor: str = "system") -> Dict[str, Any]:
        """Ask for elevation. Nothing is granted by asking."""
        if not (reason or "").strip():
            raise AuthzError(
                "reason_required",
                "a break-glass request with no reason is a request nobody can "
                "review, which is the whole of what makes it break-glass "
                "rather than an account",
                "say what is broken and what you intend to do about it")
        self.principals.require(principal)

        # The teeth on the review. Checked at REQUEST time rather than at open,
        # so the answer arrives before somebody is mid-incident.
        if overdue := self.unreviewed(principal):
            raise AuthzError(
                "review_outstanding",
                f"{principal} has {len(overdue)} closed break-glass grant(s) "
                f"nobody has reviewed ({', '.join(r['reference'] for r in overdue)}). "
                f"A review that can be skipped is a to-do list",
                "review the earlier grant first; that is what makes the "
                "mandatory review mandatory")

        rows = self.repo.many()
        row = {"reference": f"BG-{len(rows) + 1:04d}", "principal": principal,
               "requested_by": actor, "reason": reason.strip(),
               "authorised_by": None, "unilateral": False,
               "opened_at": None, "expires_at": None,
               "closed_at": None, "closed_by": None, "close_reason": "",
               "review_due": None, "reviewed_at": None, "reviewed_by": None,
               "review_outcome": None, "review_note": "",
               "state": "requested"}
        with self.evidence.recording():
            stored = self.repo.add(row)
            self.evidence.append(
                "break_glass_requested", "principal", principal,
                {"reference": row["reference"], "reason": reason,
                 "requested_by": actor}, actor=actor)
        logger.warning("break-glass %s requested for %s by %s: %s",
                       row["reference"], principal, actor, reason)
        return stored

    # ------------------------------------------------------------ authorise
    def authorise(self, reference: str, actor: str,
                  unilateral: bool = False) -> Dict[str, Any]:
        """The second signature. It cannot be the first.

        `unilateral` opens it anyway, with a shorter window and a flag. That is
        not a loophole: refusing outright at three in the morning is how an
        institution ends up with a shared password in a safe, which has no name,
        no reason, no window and no review.
        """
        row = self.require(reference)
        if row["state"] != "requested":
            raise AuthzError(
                "not_requested",
                f"{reference} is {row['state']}, not awaiting authorisation",
                "a grant is authorised once")
        if actor == row["requested_by"] and not unilateral:
            raise AuthzError(
                "same_person",
                f"{actor} asked for this elevation and cannot also authorise "
                f"it. Dual authorisation with one person is one person",
                "have somebody else authorise it, or open it unilaterally — "
                "which is allowed, gets a shorter window, and is flagged")
        if actor != row["requested_by"] and unilateral:
            raise AuthzError(
                "not_unilateral",
                "a second person is authorising this, so it is not unilateral",
                "drop the flag: this is the ordinary dual-authorised path")

        now = time.time()
        window = (UNILATERAL_WINDOW_HOURS if unilateral else WINDOW_HOURS)
        fields = {"authorised_by": None if unilateral else actor,
                  "unilateral": unilateral, "opened_at": now,
                  "expires_at": now + window * HOUR, "state": "open"}
        with self.evidence.recording():
            self.repo.set(fields, id=row["id"])
            self.evidence.append(
                "break_glass_opened", "principal", row["principal"],
                {"reference": reference, "authorised_by": fields["authorised_by"],
                 "unilateral": unilateral, "expires_at": fields["expires_at"],
                 "window_hours": window}, actor=actor)
        logger.warning("break-glass %s OPEN for %s until %.0f (%s)", reference,
                       row["principal"], fields["expires_at"],
                       "unilateral" if unilateral else f"authorised by {actor}")
        return self.read(reference)

    # ---------------------------------------------------------------- close
    def close(self, reference: str, reason: str = "",
              actor: str = "system") -> Dict[str, Any]:
        """End it early. It would have ended anyway."""
        row = self.require(reference)
        if row["state"] not in ("open", "requested"):
            raise AuthzError("not_open", f"{reference} is {row['state']}",
                             "a grant is closed once")
        now = time.time()
        with self.evidence.recording():
            self.repo.set({"state": "closed", "closed_at": now,
                           "closed_by": actor, "close_reason": reason,
                           "review_due": now + REVIEW_DAYS * DAY},
                          id=row["id"])
            self.evidence.append(
                "break_glass_closed", "principal", row["principal"],
                {"reference": reference, "reason": reason}, actor=actor)
        return self.read(reference)

    def expire_due(self, now: Optional[float] = None,
                   actor: str = "scheduler") -> Dict[str, Any]:
        """Close every grant whose window has ended.

        Housekeeping, not the control. `is_open` derives expiry from the window
        on every read, so a grant is closed to the platform the instant its
        window ends whether or not this has run — a grant that is only closed
        when a batch runs is open whenever the batch is not, which is exactly
        when it would matter.
        """
        moment = now if now is not None else time.time()
        expired = []
        for row in self.repo.many(state="open"):
            if (row.get("expires_at") or 0) > moment:
                continue
            with self.evidence.recording():
                self.repo.set({"state": "expired", "closed_at": moment,
                               "closed_by": actor,
                               "close_reason": "window elapsed",
                               "review_due": moment + REVIEW_DAYS * DAY},
                              id=row["id"])
                self.evidence.append(
                    "break_glass_expired", "principal", row["principal"],
                    {"reference": row["reference"]}, actor=actor)
            expired.append(row["reference"])
        return {"expired": expired, "count": len(expired),
                "detail": (f"{len(expired)} grant(s) reached the end of their "
                           f"window" if expired else
                           "no grant reached the end of its window")}

    # --------------------------------------------------------------- review
    def review(self, reference: str, outcome: str, note: str,
               actor: str) -> Dict[str, Any]:
        """Somebody reads what was done under it. Not the person who used it."""
        row = self.require(reference)
        if row["state"] not in ("closed", "expired"):
            raise AuthzError(
                "still_open", f"{reference} is still open",
                "a review of an elevation somebody is still using is a review "
                "of an unfinished thing")
        if row.get("reviewed_at"):
            raise AuthzError("already_reviewed",
                             f"{reference} was reviewed by {row['reviewed_by']}",
                             "a review happens once")
        if outcome not in OUTCOMES:
            raise AuthzError(
                "unknown_outcome", f"'{outcome}' is not a review outcome",
                "one of " + ", ".join(f"{k} ({v})" for k, v in OUTCOMES.items()))
        if actor == row["principal"]:
            raise AuthzError(
                "reviewed_by_the_user",
                f"{actor} used this elevation and cannot review it",
                "a post-hoc review by the person being reviewed is the record "
                "of an opinion, not a control")
        if not (note or "").strip():
            raise AuthzError(
                "note_required",
                "a review with no note records that somebody clicked",
                "say what was done under it and whether it matches the reason")

        with self.evidence.recording():
            self.repo.set({"reviewed_at": time.time(), "reviewed_by": actor,
                           "review_outcome": outcome,
                           "review_note": note.strip()}, id=row["id"])
            self.evidence.append(
                "break_glass_reviewed", "principal", row["principal"],
                {"reference": reference, "outcome": outcome,
                 "reviewed_by": actor}, actor=actor)
        if outcome != "appropriate" and self.findings is not None:
            logger.warning("break-glass %s reviewed as %s", reference, outcome)
        return self.read(reference)

    # ----------------------------------------------------------------- read
    def get(self, reference: str) -> Optional[Dict[str, Any]]:
        row = self.repo.one(reference=reference)
        return self._annotate(row) if row else None

    def read(self, reference: str) -> Dict[str, Any]:
        """The annotated row, or the refusal. What every act returns."""
        return self._annotate(self.require(reference))

    def require(self, reference: str) -> Dict[str, Any]:
        row = self.repo.one(reference=reference)
        if not row:
            raise AuthzError("no_grant", f"no break-glass grant '{reference}'",
                             "references look like BG-0001")
        return row

    def is_open(self, principal: str,
                now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """The grant this principal is acting under, if any.

        Expiry is computed here rather than trusted from the state column, so a
        grant is closed to the platform the instant its window ends.
        """
        moment = now if now is not None else time.time()
        for row in self.repo.many(principal=principal, state="open"):
            if (row.get("expires_at") or 0) > moment:
                return self._annotate(row, moment)
        return None

    def unreviewed(self, principal: Optional[str] = None,
                   now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Closed grants nobody has read."""
        moment = now if now is not None else time.time()
        out = []
        for row in self.repo.many():
            if row.get("reviewed_at") or row["state"] not in ("closed", "expired"):
                continue
            if principal and row["principal"] != principal:
                continue
            out.append({**self._annotate(row, moment),
                        "overdue": (row.get("review_due") or 0) <= moment})
        return out

    def under(self, reference: str) -> Dict[str, Any]:
        """What was done under this grant, folded from the evidence chain.

        Derived, never logged twice. The chain already records every act with
        its actor and its time, and a second log would be a second thing to keep
        in step — the first time they disagreed nobody would know which was
        true.
        """
        row = self.require(reference)
        start = row.get("opened_at") or 0
        end = row.get("closed_at") or row.get("expires_at") or time.time()
        acts = [n for n in self.evidence.repo.many()
                if n.get("recorded_by") == row["principal"]
                and start <= (n.get("recorded_at") or 0) <= end
                and not str(n.get("kind", "")).startswith("break_glass_")]
        kinds: Dict[str, int] = {}
        for node in acts:
            kinds[node["kind"]] = kinds.get(node["kind"], 0) + 1
        return {
            "reference": reference, "principal": row["principal"],
            "opened_at": start, "ended_at": end,
            "acts": len(acts), "by_kind": kinds,
            "detail": (f"{len(acts)} act(s) by {row['principal']} inside the "
                       f"window: {', '.join(sorted(kinds))}" if acts else
                       f"nothing was done under {reference}, which is worth "
                       f"noticing on its own — an elevation somebody asked "
                       f"for and did not use is either a false alarm or a "
                       f"habit"),
        }

    # -------------------------------------------------- the number that counts
    def unglassed(self, now: Optional[float] = None,
                  window_days: float = 90.0) -> Dict[str, Any]:
        """Privileged acts by an administrator during no open grant.

        **The figure an examiner should read first.** You cannot find
        break-glass abuse by watching break-glass: anybody misusing it would
        simply not open one. What finds it is what happened *without* one — and
        this is derived from the chain rather than reported by the people it is
        about.
        """
        moment = now if now is not None else time.time()
        since = moment - window_days * DAY
        admins = {p["username"] for p in self.principals.list()
                  if "admin" in (p.get("roles") or ())}
        if not admins:
            return {"acts": 0, "principals": [], "window_days": window_days,
                    "detail": "no principal holds the admin role"}

        windows: Dict[str, List[tuple]] = {}
        for row in self.repo.many():
            if not row.get("opened_at"):
                continue
            windows.setdefault(row["principal"], []).append(
                (row["opened_at"],
                 row.get("closed_at") or row.get("expires_at") or moment))

        by_principal: Dict[str, int] = {}
        for node in self.evidence.repo.many():
            actor = node.get("recorded_by")
            at = node.get("recorded_at") or 0
            if actor not in admins or at < since:
                continue
            if str(node.get("kind", "")).startswith("break_glass_"):
                continue
            if any(start <= at <= end for start, end in windows.get(actor, ())):
                continue
            by_principal[actor] = by_principal.get(actor, 0) + 1

        total = sum(by_principal.values())
        return {
            "acts": total, "by_principal": by_principal,
            "principals": sorted(by_principal),
            "window_days": window_days,
            "detail": (
                f"{total} act(s) by an administrator in the last "
                f"{window_days:.0f} days happened under no break-glass grant. "
                f"That is the figure worth reading first: nobody misusing "
                f"emergency access opens a grant for it, so the abuse is never "
                f"in the break-glass log — it is in what is missing from it"
                if total else
                f"every administrator act in the last {window_days:.0f} days "
                f"happened inside an open grant"),
        }

    # -------------------------------------------------------------- shaping
    @staticmethod
    def _annotate(row: Dict[str, Any],
                  now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        expires = row.get("expires_at")
        return {**row,
                "effectively_open": (row["state"] == "open"
                                     and (expires or 0) > moment),
                "seconds_left": max(0.0, (expires or moment) - moment)
                if row["state"] == "open" else 0.0,
                "awaiting_review": (row["state"] in ("closed", "expired")
                                    and not row.get("reviewed_at"))}

    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        rows = [self._annotate(r, moment) for r in self.repo.many()]
        rows.sort(key=lambda r: -(r.get("opened_at") or 0))
        return {
            "grants": rows, "count": len(rows),
            "open": sum(1 for r in rows if r["effectively_open"]),
            "unilateral": sum(1 for r in rows if r.get("unilateral")),
            "awaiting_review": sum(1 for r in rows if r["awaiting_review"]),
            "outcomes": {k: sum(1 for r in rows if r.get("review_outcome") == k)
                         for k in OUTCOMES},
            "unglassed": self.unglassed(moment),
            "detail": (
                f"{len(rows)} grant(s), {sum(1 for r in rows if r['effectively_open'])} "
                f"open now, {sum(1 for r in rows if r['awaiting_review'])} "
                f"awaiting a review that the next request will be refused "
                f"without"),
        }
