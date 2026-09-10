"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Things a scanner found that might be models.

**MAYA does not crawl the bank's drives, and should not.** A discovery agent
needs credentials to every repository, notebook server, shared drive and API
gateway in the institution — which is the broadest read access anybody in the
firm holds, granted to the system whose whole argument is that it holds no
standing power. What MAYA does is take delivery of what a scanner found, and be
the place the triage is recorded.

**The triage is the whole value, and the failure is not missing things.** Every
discovery programme that fails does so the same way: the sweep runs, four
thousand spreadsheets come back, nobody can look at four thousand spreadsheets,
and next month the same four thousand come back again. So a candidate carries a
**decision**, a dismissed one stays dismissed against its own fingerprint, and
the sweep is idempotent — the same artifact found again is the same candidate,
not a new one.

**A candidate is not a model.** Registering everything a scanner finds is how an
inventory becomes noise, and an inventory nobody trusts is worse than a short
one people do. So the outcomes are closed and one of them is *not a model at
all*: a firm needs somewhere to put a decision it has already made, or it will
make it again every month.

**And the number that decides whether to scale a scanner up is its precision.**
The requirement asks for exactly this and it is the part everybody skips: a
scanner running at thirty percent precision creates more work than it finds
risk, and the register is the only place that could ever know. Precision is
computed from triage outcomes — which means it is a real measurement of the
scanner rather than the scanner's own opinion of itself, and it only exists
because the dismissals were recorded too.

**An EUC is a real destination, not a lesser one.** SS1/23 1.1(b) asks that
end-user computing be found and governed proportionately; sending a spreadsheet
into the model register would put a tier-4 obligation set on something that
needs an owner and a review date. The outcome names it so the difference is
recorded rather than argued about later.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Sequence

from core.discovery.common import DiscoveryError
from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0

#: What a triage can conclude. Closed, and `not_a_model` is on it deliberately:
#: a firm needs somewhere to put a decision it has already made, or it will make
#: it again every month.
OUTCOMES: Dict[str, str] = {
    "registered": "it is a model and is now in the register",
    "euc": "it is end-user computing — an owner and a review date, not a "
           "tier-4 obligation set. SS1/23 1.1(b) asks for proportionate "
           "governance, and sending a spreadsheet into the model register is "
           "not that",
    "not_a_model": "it is not a model. Recorded rather than merely closed, "
                   "because a decision nobody wrote down is one the next sweep "
                   "makes again",
    "duplicate": "it is something already registered, found by another route",
    "deferred": "a real candidate nobody has had time for. Distinguished from "
                "dismissed on purpose: a backlog somebody is carrying is a "
                "different fact from a question somebody answered",
}

#: Outcomes that count as the scanner having been right. `deferred` is excluded
#: from both sides — an unanswered question tells you nothing about precision,
#: and counting it either way would flatter or punish a scanner for the
#: reviewer's backlog.
CORRECT = ("registered", "euc")
INCORRECT = ("not_a_model", "duplicate")

#: Below this many triaged candidates, a precision figure is noise.
MIN_FOR_PRECISION = 20

#: The precision below which scaling a scanner up costs more than it finds.
#: Not a refusal — the firm decides — but the number is reported against it,
#: because "62%" means nothing to a reader with nothing to compare it to.
USEFUL_PRECISION = 0.5


class DiscoveryRegister:
    """Takes delivery of scan output, records the triage, and grades the scanner."""

    def __init__(self, repo, registry, evidence, findings=None):
        self.repo, self.registry = repo, registry
        self.evidence, self.findings = evidence, findings

    # -------------------------------------------------------------- ingest
    def ingest(self, scanner: str, candidates: Sequence[Dict[str, Any]],
               *, now: Optional[float] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Take delivery of a sweep. Idempotent on the fingerprint.

        The same artifact found again is the same candidate, not a new one —
        which is what stops a monthly sweep re-raising four thousand
        spreadsheets nobody has time to look at twice.
        """
        if not (scanner or "").strip():
            raise DiscoveryError(
                "scanner_required",
                "a sweep with no scanner named cannot be graded, and a scanner "
                "nobody grades is one nobody should scale up",
                "name the scanner; its precision is computed per scanner")
        moment = now if now is not None else time.time()
        added, seen_again, skipped = [], [], []
        existing = len(self.repo.many())

        for candidate in candidates:
            fingerprint = str(candidate.get("fingerprint") or "").strip()
            if not fingerprint:
                skipped.append(candidate.get("location"))
                continue
            found = self.repo.one(scanner=scanner, fingerprint=fingerprint)
            if found:
                # Seen before. The `last_seen_at` moves and nothing else does:
                # a candidate somebody already dismissed must not come back as
                # open, or the triage was pointless.
                self.repo.set({"last_seen_at": moment}, id=found["id"])
                seen_again.append(found["reference"])
                continue
            existing += 1
            row = {
                "reference": f"DISC-{existing:04d}", "scanner": scanner.strip(),
                "source": str(candidate.get("source") or "unstated"),
                "fingerprint": fingerprint,
                "location": str(candidate.get("location") or ""),
                "evidence": candidate.get("evidence") or {},
                "proposed_as": str(candidate.get("proposed_as") or "model"),
                "confidence": candidate.get("confidence"),
                "state": "open", "outcome": None, "outcome_note": "",
                "registered_urn": None, "triaged_by": None, "triaged_at": None,
                "found_at": moment, "last_seen_at": moment,
            }
            self.repo.add(row)
            added.append(row["reference"])

        if self.evidence is not None and (added or seen_again):
            with self.evidence.recording():
                self.evidence.append(
                    "discovery_sweep_ingested", "scanner", scanner,
                    {"added": len(added), "seen_again": len(seen_again),
                     "skipped": len(skipped)}, actor=actor)
        logger.info("discovery sweep from %s: %d new, %d already known",
                    scanner, len(added), len(seen_again))
        return {
            "scanner": scanner, "added": added, "seen_again": len(seen_again),
            "without_a_fingerprint": skipped,
            "detail": self._ingest_detail(scanner, added, seen_again, skipped),
        }

    @staticmethod
    def _ingest_detail(scanner, added, seen_again, skipped) -> str:
        out = (f"{len(added)} new candidate(s) from {scanner}, "
               f"{len(seen_again)} already known")
        if seen_again:
            out += (" — those keep whatever triage decision they already have, "
                    "because a candidate somebody dismissed coming back as "
                    "open makes the triage pointless")
        if skipped:
            out += (f". {len(skipped)} had no fingerprint and were not taken: "
                    f"a path is not an identity, files move, and without one "
                    f"the next sweep would raise them all again")
        return out

    # -------------------------------------------------------------- triage
    def triage(self, reference: str, outcome: str, note: str, *,
               urn: Optional[str] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Decide what this is. The whole value of a discovery programme."""
        row = self.require(reference)
        if outcome not in OUTCOMES:
            raise DiscoveryError(
                "unknown_outcome", f"'{outcome}' is not a triage outcome",
                "one of " + "; ".join(f"{k} — {v}" for k, v in OUTCOMES.items()))
        if row["state"] != "open" and outcome != "deferred":
            raise DiscoveryError(
                "already_triaged",
                f"{reference} was triaged as '{row['outcome']}' by "
                f"{row['triaged_by']}",
                "re-open it deliberately if the decision was wrong; silently "
                "re-deciding would lose the record that somebody decided")
        if not (note or "").strip():
            raise DiscoveryError(
                "note_required",
                "a triage with no note records that somebody clicked. The note "
                "is what stops the same artifact being argued about again",
                "say why it is what you say it is")
        if outcome == "registered" and not urn:
            raise DiscoveryError(
                "urn_required",
                "concluding that a candidate IS a model without saying which "
                "one leaves the discovery record pointing at nothing",
                "register it first, then triage with its urn")

        fields = {"state": "triaged" if outcome != "deferred" else "open",
                  "outcome": outcome, "outcome_note": note.strip(),
                  "registered_urn": urn, "triaged_by": actor,
                  "triaged_at": time.time()}
        with self.evidence.recording():
            self.repo.set(fields, id=row["id"])
            self.evidence.append(
                "discovery_triaged", "scanner", row["scanner"],
                {"reference": reference, "outcome": outcome,
                 "location": row["location"], "urn": urn}, actor=actor)
        return self.require(reference)

    # ------------------------------------------------------------ precision
    def precision(self, scanner: str = "") -> Dict[str, Any]:
        """How often this scanner was right, from the triage outcomes.

        **The number that decides whether to scale a scanner up**, and the part
        every discovery programme skips. A scanner running at thirty percent
        precision creates more work than it finds risk, and the register is the
        only place that could ever know — because it is the only place the
        *dismissals* were recorded.
        """
        rows = [r for r in self.repo.many()
                if (not scanner or r["scanner"] == scanner)
                and r["outcome"] in CORRECT + INCORRECT]
        by_scanner: Dict[str, Dict[str, int]] = {}
        for row in rows:
            bucket = by_scanner.setdefault(row["scanner"],
                                           {"right": 0, "wrong": 0})
            bucket["right" if row["outcome"] in CORRECT else "wrong"] += 1

        out = []
        for name, counts in sorted(by_scanner.items()):
            judged = counts["right"] + counts["wrong"]
            precision = counts["right"] / judged if judged else None
            out.append({
                "scanner": name, "judged": judged, **counts,
                "precision": round(precision, 4) if precision is not None else None,
                "enough_to_read": judged >= MIN_FOR_PRECISION,
                "worth_scaling": (precision is not None
                                  and judged >= MIN_FOR_PRECISION
                                  and precision >= USEFUL_PRECISION),
            })
        out.sort(key=lambda r: -float(r["precision"] or 0.0))
        return {
            "scanners": out, "threshold": USEFUL_PRECISION,
            "minimum_judged": MIN_FOR_PRECISION,
            "detail": self._precision_detail(out),
        }

    @staticmethod
    def _precision_detail(rows) -> str:
        if not rows:
            return ("no candidate has been triaged either way, so no scanner "
                    "has a precision yet. Note that this is computed from "
                    "DISMISSALS as much as from registrations — a programme "
                    "that only records what it found can never grade the thing "
                    "that found it")
        thin = [r for r in rows if not r["enough_to_read"]]
        poor = [r for r in rows if r["enough_to_read"]
                and not r["worth_scaling"]]
        out = f"{len(rows)} scanner(s) with triaged output"
        if poor:
            out += (f". {', '.join(r['scanner'] for r in poor)} "
                    f"{'is' if len(poor) == 1 else 'are'} below "
                    f"{USEFUL_PRECISION:.0%}, which means scaling "
                    f"{'it' if len(poor) == 1 else 'them'} up creates more "
                    f"work than it finds risk")
        if thin:
            out += (f". {', '.join(r['scanner'] for r in thin)} "
                    f"{'has' if len(thin) == 1 else 'have'} fewer than "
                    f"{MIN_FOR_PRECISION} judged candidates, so the figure is "
                    f"noise rather than a measurement")
        return out

    # ------------------------------------------------------------------ read
    def require(self, reference: str) -> Dict[str, Any]:
        row = self.repo.one(reference=reference)
        if not row:
            raise DiscoveryError("no_candidate",
                                 f"no discovery candidate '{reference}'",
                                 "references look like DISC-0001")
        return row

    def outstanding(self, now: Optional[float] = None,
                    stale_days: float = 30.0) -> Dict[str, Any]:
        """What nobody has looked at, and for how long."""
        moment = now if now is not None else time.time()
        rows = []
        for row in self.repo.many(state="open"):
            rows.append({**row,
                         "days_open": round((moment - row["found_at"]) / DAY, 1),
                         "deferred": row["outcome"] == "deferred"})
        rows.sort(key=lambda r: -float(r["days_open"]))
        stale = [r for r in rows if r["days_open"] > stale_days]
        deferred = [r for r in rows if r["deferred"]]
        return {
            "open": rows, "count": len(rows), "stale": len(stale),
            "deferred": len(deferred),
            "detail": (
                f"{len(rows)} candidate(s) untriaged"
                + (f", {len(stale)} of them for more than {stale_days:.0f} "
                   f"days — which is what a discovery programme looks like "
                   f"just before everybody stops reading its output"
                   if stale else "")
                + (f". {len(deferred)} are deferred rather than unlooked-at, "
                   f"which is a backlog somebody is carrying rather than a "
                   f"question nobody answered" if deferred else "")
                if rows else
                "every candidate found so far has been triaged"),
        }

    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        rows = self.repo.many()
        by_outcome: Dict[str, int] = {}
        for row in rows:
            key = row["outcome"] or "untriaged"
            by_outcome[key] = by_outcome.get(key, 0) + 1
        return {
            "candidates": len(rows), "by_outcome": by_outcome,
            "outcomes": OUTCOMES,
            "outstanding": self.outstanding(moment),
            "precision": self.precision(),
            "detail": (
                f"{len(rows)} candidate(s) from discovery, "
                + ", ".join(f"{n} {k}" for k, n in sorted(by_outcome.items()))
                if rows else
                "nothing has been delivered by a scanner. MAYA does not crawl "
                "the bank's drives — a discovery agent needs the broadest read "
                "access anybody in the firm holds, granted to the system whose "
                "whole argument is that it holds no standing power — so this "
                "fills up when something else sweeps and posts here"),
        }
