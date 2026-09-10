"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Every time a warrant was actually used, and how it went.

Resolutions were evidence nodes and invocations were not recorded at all, so the
register could say who was *entitled* to run a model and never who did. Three
questions had no answer, and the third is the one that matters most:

  * how much is this model actually used?
  * when was this standing authorisation last exercised?
  * **which grants has nobody used at all?**

The last is a security question rather than a reporting one. A grant nobody has
exercised in a year is an authorisation the estate is carrying for no reason,
and least privilege says to withdraw it — but nothing could name one, so nobody
ever did. That is how a service account accumulates the right to run forty
models and uses three.

**What is recorded is the shape of the call, not its content.** Who called,
under what declared use, against which version, how long it took, how it ended.
No feature values and no prediction: those are inference logging's business,
they carry personal data, and a table that quietly accumulated them would be a
retention problem nobody decided to take on. This one can be kept for years
without anybody having to think about it, which is what makes the
last-used question answerable at all.

**A refusal is an outcome, not an absence.** Refused calls are recorded with
their code, because a log holding only successes makes a model look healthier
the more often it is refused — and *this service has been refused four hundred
times this week* is the single most useful line in an access review.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

OK, REFUSED, ERROR = "ok", "refused", "error"
OUTCOMES = (OK, REFUSED, ERROR)

#: How long a standing grant may go unexercised before it is worth asking about.
#: Ninety days rather than a year: an authorisation nobody has used in a quarter
#: is one nobody would notice losing, which is the definition of one worth
#: withdrawing.
DEFAULT_IDLE_DAYS = 90
DAY = 86400.0


class InvocationLog:
    """Records invocations, and answers what they add up to."""

    def __init__(self, repo, registry=None, warrants=None,
                 idle_days: int = DEFAULT_IDLE_DAYS):
        self.repo, self.registry, self.warrants = repo, registry, warrants
        self.idle_days = idle_days

    # ----------------------------------------------------------------- write
    def record(self, *, warrant: Dict[str, Any], outcome: str,
               model_id: Optional[str] = None,
               latency_ms: Optional[float] = None,
               refusal_code: Optional[str] = None,
               boundary_ok: Optional[bool] = None,
               request_id: Optional[str] = None,
               cost: Optional[float] = None,
               at: Optional[float] = None) -> Dict[str, Any]:
        """One call, as it happened.

        Never raises on a bad shape: this is called on the way out of an
        execution, including a failing one, and a logger that could fail the
        call it is logging would be a worse defect than the missing log. What
        it cannot read, it leaves null.
        """
        subject = warrant.get("subject") or {}
        authority = warrant.get("authority") or {}
        return self.repo.add({
            "warrant_id": warrant.get("warrant_id") or "",
            # Resolved HERE rather than by the caller: the engine is a consumer
            # of the warrant contract and holds no register, so it hands over
            # what the warrant says and this looks up the rest.
            "model_id": model_id or self._model_id(subject.get("model_urn")),
            "model_version_id": subject.get("model_version_id"),
            "semver": subject.get("version"),
            "principal": authority.get("principal") or "",
            "declared_use": authority.get("declared_use") or "",
            # Null means "not reported" rather than "free". A cost budget over
            # a column that silently read zero would never be reached, which is
            # the failure worth designing against for a token-metered model.
            "cost": cost,
            "environment": authority.get("environment") or "",
            "verb": (warrant.get("operation") or {}).get("verb") or "score",
            "outcome": outcome if outcome in OUTCOMES else ERROR,
            "refusal_code": refusal_code,
            "latency_ms": latency_ms,
            "boundary_ok": boundary_ok,
            "request_id": request_id,
            "at": at if at is not None else time.time(),
        })

    def record_refusal(self, *, principal: str, declared_use: str,
                       environment: str, code: str,
                       model_id: Optional[str] = None,
                       verb: str = "score", urn: Optional[str] = None,
                       request_id: Optional[str] = None) -> Dict[str, Any]:
        """A call that never got a warrant.

        These are the ones an access review wants most and the ones a
        warrant-keyed log would miss entirely, because there is no warrant to
        key them to. `warrant_id` is empty and the row is still a fact about
        who tried what.
        """
        return self.repo.add({
            "warrant_id": "",
            "model_id": model_id or self._model_id(urn),
            "model_version_id": None,
            "semver": None, "principal": principal,
            "declared_use": declared_use, "environment": environment,
            "verb": verb, "outcome": REFUSED, "refusal_code": code,
            "latency_ms": None, "boundary_ok": None, "request_id": request_id,
            "at": time.time()})

    def _model_id(self, urn: Optional[str]) -> str:
        """A urn to the id rows carry, or an empty string.

        Empty rather than raising: an invocation of something the register has
        since forgotten is still a fact about who called what, and losing it
        because the lookup failed would be the wrong trade.
        """
        if not urn or self.registry is None:
            return ""
        found = self.registry.get(urn)
        return (found or {}).get("id") or ""

    # ------------------------------------------------------------------ read
    def for_model(self, model_id: str,
                  since: Optional[float] = None) -> Dict[str, Any]:
        rows = [r for r in self.repo.many(model_id=model_id)
                if since is None or (r.get("at") or 0) >= since]
        return {"invocations": rows, **self._summarise(rows)}

    def for_warrant(self, warrant_id: str) -> Dict[str, Any]:
        rows = list(self.repo.many(warrant_id=warrant_id))
        return {"warrant_id": warrant_id, "invocations": rows,
                **self._summarise(rows)}

    def catalogue(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every standing grant, what it points at, and whether anybody uses it.

        This is `FR-WARRANT-016`. The first three columns — what exists, who
        holds it, what it points at — were always answerable per model and never
        across the estate; the last three could not be answered at all without
        the log above.

        Sorted by idleness, worst first, because the reason to read this is to
        find the authorisations nobody needs.
        """
        moment = now if now is not None else time.time()
        grants = list(self.warrants.every_grant()) if self.warrants else []
        used: Dict[str, List[Dict[str, Any]]] = {}
        for row in self.repo.many():
            key = self._key(row.get("principal"), row.get("model_id"),
                            row.get("environment"))
            used.setdefault(key, []).append(row)

        entries = []
        for grant in grants:
            model = (self.registry.by_id(grant["model_id"])
                     if self.registry else None) or {}
            calls = used.get(self._key(grant.get("principal"),
                                       grant.get("model_id"),
                                       grant.get("environment")), [])
            successful = [c for c in calls if c["outcome"] == OK]
            last = max((c.get("at") or 0) for c in calls) if calls else None
            idle_days = None if last is None else (moment - last) / DAY
            entries.append({
                "grant_id": grant.get("id"),
                "principal": grant.get("principal"),
                "declared_use": grant.get("declared_use"),
                "environment": grant.get("environment"),
                "urn": model.get("urn"), "model_name": model.get("name"),
                "tier": model.get("tier"),
                "invocations": len(calls), "successful": len(successful),
                "refused": sum(1 for c in calls if c["outcome"] == REFUSED),
                "last_used": last,
                "idle_days": None if idle_days is None else round(idle_days, 1),
                # Never used at all is a stronger statement than idle, and the
                # two are told apart because they call for different actions:
                # one is a withdrawal, the other is a conversation.
                "never_used": not calls,
                "withdrawable": (not calls
                                 or (idle_days or 0) > self.idle_days),
            })
        # Never-used first, then longest-idle. A grant nobody has ever
        # exercised is the top of this list on any estate that has been running
        # for a while, and that is the correct place for it.
        entries.sort(key=lambda e: (not e["never_used"],
                                    -(e["idle_days"] or 0)))
        withdrawable = [e for e in entries if e["withdrawable"]]
        return {
            "grants": entries, "total": len(entries),
            "never_used": sum(1 for e in entries if e["never_used"]),
            "withdrawable": len(withdrawable),
            "idle_threshold_days": self.idle_days,
            "detail": self._catalogue_detail(entries, withdrawable),
        }

    # --------------------------------------------------------------- shaping
    @staticmethod
    def _key(principal: Optional[str], model_id: Optional[str],
             environment: Optional[str]) -> str:
        return f"{principal}|{model_id}|{environment}"

    @staticmethod
    def _summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {"total": 0, "ok": 0, "refused": 0, "errors": 0,
                    "last_used": None, "p50_latency_ms": None,
                    "detail": "never invoked"}
        latencies = sorted(float(r["latency_ms"]) for r in rows
                           if r.get("latency_ms") is not None)
        refused = sum(1 for r in rows if r["outcome"] == REFUSED)
        return {
            "total": len(rows),
            "ok": sum(1 for r in rows if r["outcome"] == OK),
            "refused": refused,
            "errors": sum(1 for r in rows if r["outcome"] == ERROR),
            "last_used": max(r.get("at") or 0 for r in rows),
            # The median rather than the mean: one cold start should not be
            # what a reader takes away about how this model behaves.
            "p50_latency_ms": (latencies[len(latencies) // 2]
                               if latencies else None),
            "by_refusal": {code: sum(1 for r in rows
                                     if r.get("refusal_code") == code)
                           for code in sorted({str(r["refusal_code"])
                                               for r in rows
                                               if r.get("refusal_code")})},
            "detail": (f"{len(rows)} invocation(s), {refused} refused"
                       + ("; a log holding only successes would make this "
                          "model look healthier the more often it was refused"
                          if refused else "")),
        }

    @staticmethod
    def _catalogue_detail(entries: List[Dict[str, Any]],
                          withdrawable: List[Dict[str, Any]]) -> str:
        if not entries:
            return "no standing grants exist"
        never = sum(1 for e in entries if e["never_used"])
        out = f"{len(entries)} standing grant(s)"
        if never:
            out += (f"; {never} have never been exercised at all, which is an "
                    f"authorisation the estate is carrying for no reason")
        if len(withdrawable) > never:
            out += (f"; {len(withdrawable) - never} more have gone idle past "
                    f"the threshold")
        if not withdrawable:
            out += "; every one of them is in use"
        return out
