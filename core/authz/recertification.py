"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Periodic access recertification, and the answer that must never be inferred.

## What was built, and the half that was not

`FR-SEC-005` asks for a segregation-of-duties rule engine **and** periodic access
recertification. The rule engine is built and enforced: incompatible role pairs
are refused at grant time, and `core/authz/segregation.py` refuses the act as
well as the grant. What it cannot catch is the access that was correct when it
was granted and stopped being correct afterwards — somebody moved desk, a
secondment ended, a project closed. Nothing about that changes a role, so nothing
in the rule engine ever fires.

Recertification is the control for exactly that, and it is a control about
**people rather than models**, which is why it sits here and not in the lifecycle.

## The one thing this gets right that access reviews usually get wrong

A review is opened over a population, each reviewer confirms or revokes, and then
the campaign closes. The question is what an item nobody answered means:

> Every access review tool in the world times out. Some close the item as
> confirmed; some close it silently. Both report a completed review, and the
> access nobody looked at is the access most likely to be wrong — the reviewer
> did not answer because they did not know who this person was.

So an unreviewed item **stays unreviewed**, closing a campaign does not decide
anything, and the headline number is the count of access nobody looked at.
`confirmed` and `unreviewed` are never added together, and there is no setting
that makes them.

## Three refusals

**A reviewer may not recertify their own access.** This is the whole failure mode
of an access review, and it is not hypothetical: a reviewer assigned their own
row confirms it, because there is nothing to think about.

**A revocation needs a reason.** A role removed with no reason cannot be
distinguished afterwards from an administrative mistake, and the person whose
access went is the one who will ask.

**A campaign cannot be opened over a population of nobody.** An empty review that
closes clean is a control reporting an all-clear over an estate it never saw.

## What it does not do

**It revokes nothing outside MAYA.** Revoking here removes roles in this
register — it does not touch a directory, a database grant, a VPN profile or
anybody's job. `revoked` is what MAYA did; whether the rest followed is somebody
else's record, and a platform reporting *access removed* would be reporting a
removal it cannot see.

**It does not decide who reviews whom.** A reviewer is named when the campaign is
opened. MAYA holds no reporting line, and inferring one from roles would put the
second line in charge of recertifying the first line's managers because that is
what the permissions happen to look like.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.authz.common import AuthzError
from core.authz.roles import conflicts
from core.log import get_logger

logger = get_logger(__name__)

#: How a reviewer may answer one person's access. There is no fourth value and
#: no timeout: `unreviewed` is the absence of an answer, and the absence of an
#: answer is the finding.
CONFIRMED, REVOKED, UNREVIEWED = "confirmed", "revoked", "unreviewed"
ANSWERS = (CONFIRMED, REVOKED)

#: Beyond this, an account that has never been used is worth a second look on
#: its own. Ninety days because that is a quarter, which is the cadence access
#: reviews actually run on — not because dormancy proves anything.
DORMANT_AFTER_DAYS = 90

#: The cadence a campaign is expected at. Reported, never enforced: MAYA does
#: not know a firm's policy, and a platform refusing to open a review because
#: one is not yet due would be enforcing a schedule it invented.
EXPECTED_EVERY_DAYS = 365


class Recertification:
    """Opens access reviews, records answers, and never infers one."""

    def __init__(self, campaigns, items, principals, evidence=None,
                 dormant_after_days: int = DORMANT_AFTER_DAYS):
        self.campaigns, self.items = campaigns, items
        self.principals, self.evidence = principals, evidence
        self.dormant_after = dormant_after_days * 86400.0

    # --------------------------------------------------------------- posture
    @staticmethod
    def posture() -> Dict[str, Any]:
        """What a recertification decides, and the four things it does not."""
        return {
            "answers": list(ANSWERS),
            "unanswered_is": UNREVIEWED,
            "times_out": False,
            "revokes_outside_maya": False,
            "decides_who_reviews_whom": False,
            "dormant_after_days": DORMANT_AFTER_DAYS,
            "expected_every_days": EXPECTED_EVERY_DAYS,
            "why_no_timeout": (
                "the access nobody looked at is the access most likely to be "
                "wrong — the reviewer did not answer because they did not know "
                "who this person was. An item nobody answered stays "
                "`unreviewed`, closing a campaign decides nothing, and "
                "`confirmed` and `unreviewed` are never added together"),
            "why_not_revoke_outside": (
                "revoking removes roles in THIS register. It does not touch a "
                "directory, a database grant, a VPN profile or anybody's job — "
                "and a platform reporting *access removed* would be reporting "
                "a removal it cannot see"),
            "why_not_choose_reviewers": (
                "MAYA holds no reporting line. Inferring one from roles would "
                "put the second line in charge of recertifying the first "
                "line's managers, because that is what the permissions happen "
                "to look like"),
        }

    # ------------------------------------------------------------------ open
    def open(self, reference: str, *, reviewer: str, title: str = "",
             population: Optional[Sequence[str]] = None,
             actor: str = "system", now: Optional[float] = None
             ) -> Dict[str, Any]:
        """Open a review over named accounts, or over everybody active."""
        moment = now if now is not None else time.time()
        reference = str(reference or "").strip()
        if not reference:
            raise AuthzError("reference_required",
                             "a recertification campaign needs a reference",
                             "it gets quoted in an audit finding; 'the review "
                             "we did in March' does not")
        if self.campaigns.one(reference=reference):
            raise AuthzError(
                "campaign_exists",
                f"a recertification called '{reference}' is already open",
                "close it before opening another under that reference")
        self.principals.require(reviewer)

        people = self._population(population)
        if not people:
            raise AuthzError(
                "empty_population",
                "this campaign would review nobody",
                "an empty review that closes clean is a control reporting an "
                "all-clear over an estate it never saw. Name accounts, or "
                "leave the population blank to review everybody active")

        row = {"reference": reference, "title": title or reference,
               "reviewer": reviewer, "status": "open",
               "opened_by": actor, "opened_at": moment, "closed_at": None}
        self.campaigns.add(row)
        for person in people:
            self.items.add({
                "campaign_reference": reference,
                "principal": person["username"],
                # What their access WAS when somebody looked. Copied rather
                # than joined, because the answer has to stay readable after
                # the roles change — which is the entire point of asking.
                "roles": list(person.get("roles") or []),
                "legal_entities": list(person.get("legal_entities") or []),
                "domains": list(person.get("domains") or []),
                "last_seen_at": person.get("last_seen_at"),
                "state": UNREVIEWED, "reason": "",
                "answered_by": "", "answered_at": None})
        if self.evidence is not None:
            self.evidence.append("recertification_opened", "platform",
                                 reference,
                                 {"reviewer": reviewer,
                                  "population": len(people)}, actor=actor)
        logger.info("opened recertification %s over %d account(s), reviewer %s",
                    reference, len(people), reviewer)
        return self.status(reference, now=moment)

    def _population(self, population: Optional[Sequence[str]]
                    ) -> List[Dict[str, Any]]:
        if population:
            return [self.principals.require(u) for u in population]
        return [p for p in self.principals.list()
                if p.get("status") == "active"]

    # ---------------------------------------------------------------- answer
    def answer(self, reference: str, principal: str, *, state: str,
               reason: str = "", actor: str = "system",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Confirm or revoke one person's access. There is no third answer."""
        moment = now if now is not None else time.time()
        campaign = self.require(reference)
        if campaign["status"] != "open":
            raise AuthzError(
                "campaign_closed",
                f"'{reference}' is already {campaign['status']}",
                "open a new campaign; reopening one would let an answer be "
                "changed after the review was reported")
        if state not in ANSWERS:
            raise AuthzError(
                "unknown_answer", f"'{state}' is not an answer",
                f"the answers are {' and '.join(ANSWERS)}. There is no "
                f"'unsure': an item nobody can answer stays `{UNREVIEWED}`, "
                f"which is reported rather than resolved")
        item = self.items.one(campaign_reference=reference, principal=principal)
        if item is None:
            raise AuthzError(
                "not_in_population",
                f"{principal} is not in this campaign",
                "review the accounts the campaign was opened over; adding one "
                "midway would change what the review covered after it started")
        if actor == principal:
            raise AuthzError(
                "self_recertification",
                f"{actor} may not recertify their own access",
                "this is the whole failure mode of an access review, and it is "
                "not hypothetical: a reviewer assigned their own row confirms "
                "it, because there is nothing to think about. Have somebody "
                "else answer this one")
        if state == REVOKED and not str(reason).strip():
            raise AuthzError(
                "reason_required", "a revocation needs a reason",
                "a role removed with no reason cannot be told apart "
                "afterwards from an administrative mistake, and the person "
                "whose access went is the one who will ask")

        removed: List[str] = []
        if state == REVOKED:
            removed = list(item.get("roles") or [])
            self.principals.set_roles(principal, [], actor=actor)
        self.items.set({"state": state, "reason": str(reason).strip(),
                        "answered_by": actor, "answered_at": moment},
                       id=item["id"])
        if self.evidence is not None:
            self.evidence.append(
                f"access_{state}", "platform", principal,
                {"campaign": reference, "roles": list(item.get("roles") or []),
                 "reason": str(reason).strip()}, actor=actor)
        logger.info("%s %s %s in %s", actor, state, principal, reference)
        return {"campaign": reference, "principal": principal, "state": state,
                "roles_removed_in_maya": removed,
                "detail": self._answer_detail(state, principal, removed)}

    @staticmethod
    def _answer_detail(state: str, principal: str,
                       removed: Sequence[str]) -> str:
        if state == CONFIRMED:
            return (f"{principal}'s access is confirmed as it stood when the "
                    f"campaign opened. A later change is not covered by this "
                    f"answer")
        return (f"{len(removed)} role(s) removed from {principal} IN THIS "
                f"REGISTER: {', '.join(removed) or 'none'}. MAYA does not "
                f"touch a directory, a database grant or anybody's job — "
                f"whether the rest followed is somebody else's record")

    # ----------------------------------------------------------------- close
    def close(self, reference: str, actor: str = "system",
              now: Optional[float] = None) -> Dict[str, Any]:
        """Close the campaign. This decides nothing about what was unreviewed."""
        moment = now if now is not None else time.time()
        campaign = self.require(reference)
        if campaign["status"] != "open":
            raise AuthzError("campaign_closed",
                             f"'{reference}' is already {campaign['status']}",
                             "")
        self.campaigns.set({"status": "closed", "closed_at": moment},
                           id=campaign["id"])
        out = self.status(reference, now=moment)
        if self.evidence is not None:
            self.evidence.append(
                "recertification_closed", "platform", reference,
                {"confirmed": out["confirmed"], "revoked": out["revoked"],
                 "unreviewed": out["unreviewed"]}, actor=actor)
        logger.info("closed recertification %s with %d unreviewed",
                    reference, out["unreviewed"])
        return out

    # ---------------------------------------------------------------- status
    def status(self, reference: str, now: Optional[float] = None
               ) -> Dict[str, Any]:
        """Where a campaign stands. `unreviewed` is a first-class number."""
        moment = now if now is not None else time.time()
        campaign = self.require(reference)
        items = list(self.items.many(campaign_reference=reference))
        counted = {s: len([i for i in items if i["state"] == s])
                   for s in (CONFIRMED, REVOKED, UNREVIEWED)}
        return {
            "reference": reference, "title": campaign["title"],
            "reviewer": campaign["reviewer"], "status": campaign["status"],
            "population": len(items), **counted,
            "unreviewed_accounts": sorted(i["principal"] for i in items
                                          if i["state"] == UNREVIEWED),
            "flagged": self._flagged(items, moment),
            "detail": self._detail(campaign, counted, len(items)),
        }

    def _flagged(self, items: Sequence[Dict[str, Any]],
                 moment: float) -> List[Dict[str, Any]]:
        """Accounts worth a second look, with the reason stated.

        Not a score and not a recommendation. A conflict is the rule engine's
        own answer, and dormancy is an observation — neither decides anything,
        because a reviewer handed a ranked list reviews the top of it.
        """
        out = []
        for item in items:
            why = list(conflicts(item.get("roles") or []))
            seen = item.get("last_seen_at")
            if not seen:
                why.append("this account has never signed in")
            elif moment - float(seen) > self.dormant_after:
                why.append(f"not seen for more than {DORMANT_AFTER_DAYS} days")
            if not item.get("roles"):
                why.append("holds no roles, so this account grants nothing")
            if why:
                out.append({"principal": item["principal"],
                            "state": item["state"], "why": why})
        return sorted(out, key=lambda r: r["principal"])

    @staticmethod
    def _detail(campaign: Dict[str, Any], counted: Dict[str, int],
                population: int) -> str:
        out = (f"{counted[CONFIRMED]} confirmed, {counted[REVOKED]} revoked, "
               f"**{counted[UNREVIEWED]} nobody looked at**, of {population}")
        if counted[UNREVIEWED]:
            out += (". An unreviewed item is not a confirmed one and never "
                    "becomes one: this campaign does not time out, because the "
                    "access nobody looked at is the access most likely to be "
                    "wrong")
        if campaign["status"] == "closed" and counted[UNREVIEWED]:
            out += (f". The campaign is closed with {counted[UNREVIEWED]} "
                    f"still unanswered — closing decided nothing about them")
        return out

    def of(self, principal: str) -> Dict[str, Any]:
        """When this person's access was last looked at, and by whom."""
        rows = [i for i in self.items.many(principal=principal)
                if i["state"] in ANSWERS]
        if not rows:
            return {"principal": principal, "recertified": False,
                    "detail": ("nobody has recertified this access. That is "
                               "not the same as it having been reviewed and "
                               "found correct")}
        latest = max(rows, key=lambda r: r.get("answered_at") or 0)
        return {"principal": principal, "recertified": True,
                "state": latest["state"], "by": latest["answered_by"],
                "at": latest["answered_at"],
                "campaign": latest["campaign_reference"],
                "roles_then": list(latest.get("roles") or []),
                "detail": (f"last answered in {latest['campaign_reference']} "
                           f"by {latest['answered_by']}. The roles recorded "
                           f"there are the roles as they stood then, which is "
                           f"the point of asking — a change since is not "
                           f"covered by that answer")}

    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Who has never been recertified, which is the number that matters."""
        moment = now if now is not None else time.time()
        active = [p for p in self.principals.list()
                  if p.get("status") == "active"]
        answered = {i["principal"] for i in self.items.many()
                    if i["state"] in ANSWERS}
        never = sorted(p["username"] for p in active
                       if p["username"] not in answered)
        campaigns = list(self.campaigns.many())
        recent = [c for c in campaigns
                  if moment - float(c.get("opened_at") or 0)
                  < EXPECTED_EVERY_DAYS * 86400]
        return {
            "accounts": len(active), "campaigns": len(campaigns),
            "campaigns_this_period": len(recent),
            "never_recertified": never,
            "open": [c["reference"] for c in campaigns
                     if c["status"] == "open"],
            "detail": (
                f"{len(never)} of {len(active)} active account(s) have never "
                f"been recertified"
                + (". A review nobody has run is not a review that found "
                   "nothing" if never else
                   ". Every active account has been looked at at least once")
                + (f". No campaign has been opened in the last "
                   f"{EXPECTED_EVERY_DAYS} days — MAYA reports the cadence "
                   f"and does not enforce it, because it does not know this "
                   f"firm's policy" if not recent else "")),
        }

    def require(self, reference: str) -> Dict[str, Any]:
        row = self.campaigns.one(reference=reference)
        if row is None:
            raise AuthzError("unknown_recertification",
                             f"no recertification called '{reference}'", "")
        return row
