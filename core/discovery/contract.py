"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a scanner has to send, and why MAYA still does not run one.

The triage register exists: candidates arrive, somebody dismisses or registers
each one, and the scanner's precision is computed from the dismissals. What has
been missing is the other end --- a published contract, so a firm can point
whatever it already has at the register instead of waiting for MAYA to grow a
crawler.

**And MAYA will not grow one.** A sweep for unregistered models means reading
shared drives, notebook servers, repositories and gateways --- which means
credentials to all of them, and a governance platform holding read access to
every file store in a bank is a far larger thing than the register it protects.
It is the same boundary as connectors, artifact conversion and log fetching: the
scan runs where the files are, under the access somebody already has, and MAYA
takes delivery of what it found.

**The hard part of discovery is not finding spreadsheets.** It is not finding
all of them. A scanner returning forty thousand candidates has produced a queue
nobody triages, and an untriaged queue is worse than no scan --- the estate now
believes it has a discovery programme, and what it has is a table filling up.
So the contract requires two things most scanners do not send:

  * **A confidence, and it must not be 1.0.** A scanner found a file with a
    regression in it. That is evidence somebody built something, not evidence
    that it is a model, and a scanner asserting certainty is making a
    determination that belongs to triage.
  * **A stated recall, or an admission that recall is unknown.** Precision the
    register computes for itself from the dismissals. Recall it cannot: it has
    no idea what the scanner did not look at. A scanner that says *I swept these
    four drives and not the other two* is worth ten that say nothing, because
    the sentence a supervisor asks for is about coverage and not about hits.

**The fingerprint must survive the artifact moving.** A path is not an identity:
a spreadsheet that moves folders arrives as a new candidate and the dismissal
somebody already recorded is lost, which is how a monthly sweep re-raises four
thousand rows nobody has time to look at twice.

**And a scanner is graded before it is scaled.** A scanner running at thirty
percent precision creates more work than it finds risk, and the register is the
only place that could ever know --- because it is the only place that recorded
what was dismissed.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.discovery.common import DiscoveryError
from core.log import get_logger

logger = get_logger(__name__)

#: A confidence at or above this is refused. Not a tuning parameter: a scanner
#: asserting certainty is making triage's determination for it.
CERTAINTY = 1.0

#: Below this precision, scaling a scanner up costs more triage than the risk it
#: surfaces. Published so the judgement is arguable rather than implicit.
POOR_PRECISION = 0.30

#: What every candidate must carry, and why. This is the contract.
REQUIRED: Tuple[Tuple[str, str], ...] = (
    ("fingerprint",
     "something intrinsic that survives the artifact moving. A path is not an "
     "identity: a spreadsheet that changes folder arrives as a new candidate "
     "and the dismissal somebody recorded is lost"),
    ("location",
     "where a person goes to look. The fingerprint identifies it and the "
     "location finds it, and a candidate with only the first is untriageable"),
    ("source",
     "which store it came from — a drive, a notebook server, a repository. "
     "Precision differs sharply by source and a scanner graded in aggregate "
     "hides that"),
    ("confidence",
     "how sure the scanner is, strictly below 1.0. It found a file with a "
     "regression in it; whether that is a model is triage's determination"),
    ("evidence",
     "what it saw — the matched pattern, the surrounding text, the sheet name. "
     "A triage decision made without it is a guess with a reference number"),
)

#: What a sweep must carry about itself, as opposed to about its candidates.
SWEEP_REQUIRED: Tuple[Tuple[str, str], ...] = (
    ("scanner",
     "a stable name. Precision is computed per scanner, and a scanner that "
     "renames itself between sweeps has no history"),
    ("scope",
     "what was swept. The register computes precision and cannot compute "
     "recall — it has no idea what was not looked at, and *I swept these four "
     "drives and not the other two* is the sentence a supervisor asks for"),
    ("recall_known",
     "whether the scanner can state its own recall. Almost always false, and "
     "saying so is worth more than a figure nobody can support"),
)


class ScannerContract:
    """Checks a sweep against the published contract before it is ingested."""

    def __init__(self, discovery):
        self.discovery = discovery

    # ----------------------------------------------------------------- check
    def check(self, sweep: Dict[str, Any]) -> Dict[str, Any]:
        """What is wrong with this sweep, all of it, before anything is stored.

        Every problem at once rather than the first: a scanner author told about
        one field fixes it, re-runs a sweep over forty thousand files, and is
        told about the next.
        """
        problems: List[Dict[str, str]] = []
        for field, why in SWEEP_REQUIRED:
            if field == "recall_known":
                if "recall_known" not in sweep:
                    problems.append({"what": "sweep.recall_known", "why": why})
                continue
            if not str(sweep.get(field) or "").strip():
                problems.append({"what": f"sweep.{field}", "why": why})

        candidates = sweep.get("candidates") or []
        for index, candidate in enumerate(candidates):
            problems += self._check_candidate(index, candidate)

        return {
            "scanner": sweep.get("scanner"),
            "candidates": len(candidates),
            "problems": problems, "admissible": not problems,
            "detail": self._detail(sweep, candidates, problems),
        }

    @staticmethod
    def _check_candidate(index: int,
                         candidate: Dict[str, Any]) -> List[Dict[str, str]]:
        out = []
        for field, why in REQUIRED:
            value = candidate.get(field)
            if field == "confidence":
                if value is None:
                    out.append({"what": f"candidate[{index}].confidence",
                                "why": why})
                elif float(value) >= CERTAINTY:
                    out.append({
                        "what": f"candidate[{index}].confidence",
                        "why": (f"a confidence of {value} asserts certainty. "
                                f"The scanner found a file; whether it is a "
                                f"model is triage's determination, and a "
                                f"scanner making it produces a register nobody "
                                f"reviewed")})
                continue
            if field == "evidence":
                if not isinstance(value, dict) or not value:
                    out.append({"what": f"candidate[{index}].evidence",
                                "why": why})
                continue
            if not str(value or "").strip():
                out.append({"what": f"candidate[{index}].{field}", "why": why})
        return out

    @staticmethod
    def _detail(sweep, candidates, problems) -> str:
        if not problems:
            out = (f"{len(candidates)} candidate(s) from "
                   f"'{sweep.get('scanner')}' meet the contract")
            if sweep.get("recall_known") is False:
                out += (". Recall is stated as unknown, which is the honest "
                        "answer and worth more than a figure nobody can "
                        "support — the register computes precision from the "
                        "dismissals and has no idea what was not looked at")
            if len(candidates) > 1000:
                out += (f". {len(candidates)} is a large sweep: a queue nobody "
                        f"triages is worse than no scan, because the estate "
                        f"then believes it has a discovery programme and what "
                        f"it has is a table filling up")
            return out
        return (f"{len(problems)} problem(s) with this sweep, all of them "
                f"reported rather than the first — a scanner author told about "
                f"one field fixes it, re-runs over forty thousand files, and "
                f"is told about the next")

    # ---------------------------------------------------------------- ingest
    def ingest(self, sweep: Dict[str, Any], *,
               actor: str = "system") -> Dict[str, Any]:
        """Check, then hand to the register. Refused as a whole or not at all."""
        checked = self.check(sweep)
        if not checked["admissible"]:
            raise DiscoveryError(
                "sweep_does_not_meet_the_contract",
                f"{len(checked['problems'])} problem(s): "
                + "; ".join(p["what"] for p in checked["problems"][:6])
                + (f" and {len(checked['problems']) - 6} more"
                   if len(checked["problems"]) > 6 else ""),
                "the whole sweep is refused rather than the bad rows dropped: "
                "a partial ingest gives a scanner a precision computed over "
                "the candidates that happened to parse, which is a grade for "
                "something other than the scanner")
        out = self.discovery.ingest(sweep["scanner"], sweep["candidates"],
                                    actor=actor)
        logger.info("sweep from %s accepted: %d candidate(s), recall_known=%s",
                    sweep["scanner"], checked["candidates"],
                    sweep.get("recall_known"))
        return {**out, "scope": sweep.get("scope"),
                "recall_known": sweep.get("recall_known"),
                "detail": out.get("detail", "") + ". Scope: "
                + str(sweep.get("scope"))
                + (". Recall is unknown and stated as such"
                   if sweep.get("recall_known") is False else "")}

    # ------------------------------------------------------------------ what
    @staticmethod
    def contract() -> Dict[str, Any]:
        """The contract, published so a firm can point its own scanner here."""
        return {
            "candidate_fields": [{"field": f, "why": w} for f, w in REQUIRED],
            "sweep_fields": [{"field": f, "why": w} for f, w in SWEEP_REQUIRED],
            "max_confidence": CERTAINTY,
            "poor_precision_below": POOR_PRECISION,
            "maya_runs_a_scanner": False,
            "detail": ("MAYA does not sweep. A scan means credentials to every "
                       "file store, notebook server and repository in the "
                       "bank, which is a far larger thing than the register it "
                       "would protect — so the scan runs where the files are, "
                       "under access somebody already has, and the register "
                       "takes delivery and grades the scanner. Precision it "
                       "computes for itself from the dismissals; recall it "
                       "cannot, and a scanner that states its scope is worth "
                       "ten that do not"),
        }

    # ------------------------------------------------------------------ grade
    def grade(self, scanner: str = "") -> Dict[str, Any]:
        """What the register knows about a scanner, and what it cannot know."""
        measured = self.discovery.precision(scanner)
        rows = measured.get("scanners") or []
        poor = [r for r in rows
                if r.get("precision") is not None
                and r["precision"] < POOR_PRECISION]
        return {
            **measured, "poor": [r.get("scanner") for r in poor],
            "recall_is_computable": False,
            "detail": (measured.get("detail", "")
                       + (f". {len(poor)} scanner(s) are running below "
                          f"{POOR_PRECISION:.0%} precision, which creates more "
                          f"triage than the risk it surfaces — and this "
                          f"register is the only place that could know, "
                          f"because it is the only place that recorded what "
                          f"was dismissed" if poor else "")
                       + ". Recall is not computable here at all: nothing in "
                         "the register knows what a scanner did not look at, "
                         "which is why the contract asks the scanner to say"),
        }
