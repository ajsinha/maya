"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A challenger running beside the champion, and what that can honestly tell you.

SS1/23 3.3(c) asks for parallel outcomes analysis when a dynamic model changes,
and the reason it asks is sound: the only way to know what a new version does to
real decisions is to let it see the real decisions without acting on them.

**MAYA runs neither model.** It registers that a parallel run is happening, takes
delivery of what both produced, and reports the shape of the disagreement — the
same position it takes on every other execution. What it contributes is the
arithmetic and, more importantly, the distinction below.

**The distinction the whole thing turns on: agreement is knowable now, and
correctness is not.** Two models disagreeing on ten thousand cases is a fact
available the moment both have answered. Which of them was *right* needs the
outcome — the default, the claim, the loss — and that arrives months later or
never. Nearly every shadow-mode dashboard conflates them, reports a
disagreement rate, and lets a reader conclude something about quality that the
data cannot support. So this reports two things that are never mixed:
**divergence**, which is available immediately and says nothing about quality;
and **outcomes analysis**, which is available only for the observations whose
label has arrived and says how much of the run that covers.

**A parallel run whose champion and challenger were not asked the same question
is not a parallel run.** It is two unrelated series printed side by side. So
every observation is keyed on the input, both answers are recorded against that
key, and an observation with only one side is reported as unpaired rather than
quietly dropped — because a challenger that silently failed on the hard cases
would otherwise look like the better model.

**The shape of a disagreement matters more than its size**, and
`core/validation/recode.py` already knows how to read one: a handful of wild
outliers is a branch nobody tested, and a uniform smear is arithmetic done
differently. That reading is reused rather than reimplemented, because two
implementations of one judgement eventually disagree.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.lifecycle.common import LifecycleError
from core.log import get_logger

logger = get_logger(__name__)

STATES = ("running", "concluded")

#: What a parallel run can end in. Closed, because *we looked at it* is not a
#: conclusion and a run with no verdict reads exactly like one nobody finished.
CONCLUSIONS: Dict[str, str] = {
    "promote": "the challenger should take over the alias",
    "reject": "the challenger should not, and the run says why",
    "inconclusive": "the run did not answer the question — usually too few "
                    "outcomes, which is an honest end and a common one",
}

#: Below this many paired observations, a divergence rate is noise.
MIN_PAIRED = 30

#: Below this share of observations having an outcome, an outcomes analysis is
#: reported as too thin to conclude on rather than as a result with a caveat.
MIN_OUTCOME_COVERAGE = 0.1


class ParallelRuns:
    """Registers a shadow deployment and reports what it can honestly say."""

    def __init__(self, runs, observations, registry, evidence, recode=None):
        self.runs, self.observations = runs, observations
        self.registry, self.evidence = registry, evidence
        # The harness that reads the SHAPE of a disagreement. Reused rather
        # than reimplemented: two implementations of one judgement eventually
        # disagree, and this one already distinguishes a cliff from a tail.
        self.recode = recode

    # -------------------------------------------------------------- opening
    def open(self, urn: str, *, champion: str, challenger: str, purpose: str,
             tolerance: float = 1e-9, actor: str = "system") -> Dict[str, Any]:
        """Declare that a challenger is running beside the champion."""
        model = self.registry.require(urn)
        if champion == challenger:
            raise LifecycleError(
                "same_version",
                f"{champion} cannot run in parallel with itself",
                "name the version being challenged and the one challenging it")
        if not (purpose or "").strip():
            raise LifecycleError(
                "purpose_required",
                "a parallel run with no stated purpose is one nobody can "
                "conclude, because nothing records what it was meant to answer",
                "say what question this run is being kept open to settle")
        left = self.registry.version_service.require(urn, champion)
        right = self.registry.version_service.require(urn, challenger)
        open_already = [r for r in self.runs.many(model_id=model["id"])
                        if r["state"] == "running"]
        if open_already:
            raise LifecycleError(
                "run_already_open",
                f"{open_already[0]['reference']} is already running on this "
                f"model. Two shadow runs at once means neither can be read: an "
                f"observation belongs to one of them and nothing says which",
                "conclude the open one first")

        rows = self.runs.many()
        row = {
            "reference": f"PAR-{len(rows) + 1:04d}", "model_id": model["id"],
            "champion_version_id": left["id"],
            "challenger_version_id": right["id"],
            "champion_semver": champion, "challenger_semver": challenger,
            "purpose": purpose.strip(), "tolerance": float(tolerance),
            "state": "running", "opened_by": actor, "opened_at": time.time(),
            "closed_at": None, "closed_by": None, "conclusion": None,
            "close_note": "",
        }
        with self.evidence.recording():
            stored = self.runs.add(row)
            self.evidence.append(
                "parallel_run_opened", "model", model["id"],
                {"reference": row["reference"], "champion": champion,
                 "challenger": challenger, "purpose": purpose}, actor=actor)
        logger.info("parallel run %s opened on %s: %s against %s",
                    row["reference"], urn, champion, challenger)
        return stored

    # ---------------------------------------------------------- observations
    def observe(self, reference: str, *, input_key: str,
                champion: Optional[float] = None,
                challenger: Optional[float] = None,
                at: Optional[float] = None) -> Dict[str, Any]:
        """Record what one or both models answered for one input.

        Either side may arrive first and separately, because in a real shadow
        deployment they do: the champion answers in the request path and the
        challenger answers out of band. An observation with only one side is
        kept and reported as unpaired rather than dropped — a challenger that
        silently failed on the hard cases would otherwise look like the better
        model.
        """
        run = self.require(reference)
        if run["state"] != "running":
            raise LifecycleError(
                "run_concluded",
                f"{reference} was concluded, and an observation arriving "
                f"afterwards would change a comparison somebody has already "
                f"acted on",
                "open a new run")
        if not (input_key or "").strip():
            raise LifecycleError(
                "input_key_required",
                "an observation with no input key cannot be paired, and a "
                "parallel run whose two sides were not asked the same question "
                "is two unrelated series printed side by side",
                "key it on whatever identifies the case both models saw")

        existing = self.observations.one(run_id=run["id"],
                                         input_key=input_key.strip())
        moment = at if at is not None else time.time()
        if existing:
            fields = {}
            if champion is not None:
                fields["champion"] = float(champion)
            if challenger is not None:
                fields["challenger"] = float(challenger)
            if fields:
                self.observations.set(fields, id=existing["id"])
            return self.observations.one(id=existing["id"])
        return self.observations.add({
            "run_id": run["id"], "input_key": input_key.strip(),
            "champion": float(champion) if champion is not None else None,
            "challenger": float(challenger) if challenger is not None else None,
            "outcome": None, "outcome_at": None, "at": moment})

    def record_outcome(self, reference: str, input_key: str, outcome: float,
                       at: Optional[float] = None) -> Dict[str, Any]:
        """The label, when it arrives — which is the part that takes months."""
        run = self.require(reference)
        row = self.observations.one(run_id=run["id"], input_key=input_key)
        if not row:
            raise LifecycleError(
                "no_observation",
                f"{reference} has no observation for '{input_key}', so there "
                f"is nothing for this outcome to be the outcome OF",
                "record what the models answered first")
        self.observations.set(
            {"outcome": float(outcome),
             "outcome_at": at if at is not None else time.time()},
            id=row["id"])
        return self.observations.one(id=row["id"])

    # ------------------------------------------------------------- readings
    def divergence(self, reference: str) -> Dict[str, Any]:
        """How often and how far the two disagree. Says nothing about quality.

        Available the moment both have answered, and that is exactly why it is
        reported apart from the outcomes analysis: a reader given a single
        number cannot tell which question it answers.
        """
        run = self.require(reference)
        rows = self.observations.many(run_id=run["id"])
        paired = [r for r in rows
                  if r.get("champion") is not None
                  and r.get("challenger") is not None]
        unpaired = [r for r in rows if r not in paired]

        shape = None
        if paired and self.recode is not None:
            shape = self.recode.compare(
                {r["input_key"]: r["champion"] for r in paired},
                {r["input_key"]: r["challenger"] for r in paired},
                tolerance=run["tolerance"],
                model_source=f"champion {run['champion_semver']}",
                recode_source=f"challenger {run['challenger_semver']}")
        return {
            "reference": reference, "observations": len(rows),
            "paired": len(paired), "unpaired": len(unpaired),
            "unpaired_keys": sorted(r["input_key"] for r in unpaired)[:20],
            "comparison": shape,
            "enough_to_read": len(paired) >= MIN_PAIRED,
            "detail": self._divergence_detail(run, paired, unpaired, shape),
        }

    @staticmethod
    def _divergence_detail(run, paired, unpaired, shape) -> str:
        if not paired:
            return ("nothing has been paired yet, so there is nothing to "
                    "compare. This says nothing about either model")
        out = (f"{len(paired)} paired observation(s)"
               + (f", {shape['disagreed']} of which disagree beyond "
                  f"{run['tolerance']:g} — {shape['shape']['kind']}"
                  if shape else ""))
        if len(paired) < MIN_PAIRED:
            out += (f". Fewer than {MIN_PAIRED} pairs, so a rate over them is "
                    f"noise rather than a measurement")
        if unpaired:
            out += (f". {len(unpaired)} observation(s) have only one side and "
                    f"are NOT in the comparison — a challenger that silently "
                    f"failed on the hard cases would otherwise look like the "
                    f"better model")
        out += (". None of this says which model is better; that needs the "
                "outcome, and the outcome arrives later")
        return out

    def outcomes(self, reference: str) -> Dict[str, Any]:
        """Which model was closer to what actually happened.

        The question the requirement is really about, and the one that cannot
        be answered until labels arrive. Reported with its **coverage**, because
        an outcomes analysis over 4% of a run is not a result with a caveat, it
        is not a result.
        """
        run = self.require(reference)
        rows = self.observations.many(run_id=run["id"])
        labelled = [r for r in rows
                    if r.get("outcome") is not None
                    and r.get("champion") is not None
                    and r.get("challenger") is not None]
        coverage = len(labelled) / len(rows) if rows else 0.0
        if not labelled:
            return {
                "reference": reference, "observations": len(rows),
                "with_an_outcome": 0, "coverage": 0.0,
                "conclusive": False,
                "detail": ("no outcome has arrived for any observation. That "
                           "is the ordinary state of a parallel run for most "
                           "of its life, and it is why divergence and outcomes "
                           "are reported apart: one is available now and the "
                           "other is not"),
            }
        champion_error = sum(abs(r["champion"] - r["outcome"])
                             for r in labelled) / len(labelled)
        challenger_error = sum(abs(r["challenger"] - r["outcome"])
                               for r in labelled) / len(labelled)
        conclusive = (coverage >= MIN_OUTCOME_COVERAGE
                      and len(labelled) >= MIN_PAIRED)
        better = ("challenger" if challenger_error < champion_error
                  else "champion" if champion_error < challenger_error
                  else "neither")
        return {
            "reference": reference, "observations": len(rows),
            "with_an_outcome": len(labelled), "coverage": round(coverage, 4),
            "champion_mean_absolute_error": champion_error,
            "challenger_mean_absolute_error": challenger_error,
            "closer": better, "conclusive": conclusive,
            "detail": self._outcome_detail(better, champion_error,
                                           challenger_error, labelled, rows,
                                           coverage, conclusive),
        }

    @staticmethod
    def _outcome_detail(better, champion_error, challenger_error, labelled,
                        rows, coverage, conclusive) -> str:
        head = (f"over {len(labelled)} labelled observation(s) the {better} is "
                f"closer to what happened — {champion_error:.4g} against "
                f"{challenger_error:.4g} mean absolute error"
                if better != "neither" else
                f"over {len(labelled)} labelled observation(s) the two are "
                f"equally close to what happened")
        if not conclusive:
            return (head + f". That covers {coverage:.0%} of the run, which is "
                    f"too thin to conclude on: an outcomes analysis over a "
                    f"fraction of a run is not a result with a caveat, it is "
                    f"not a result")
        return head + f", over {coverage:.0%} of the run"

    def report(self, reference: str) -> Dict[str, Any]:
        """Both readings, never mixed."""
        run = self.require(reference)
        return {
            "run": run, "divergence": self.divergence(reference),
            "outcomes": self.outcomes(reference),
            "conclusions": CONCLUSIONS,
            "detail": (
                "divergence is available now and says nothing about quality; "
                "outcomes analysis says which model was right and is available "
                "only for the observations whose label has arrived. Nearly "
                "every shadow-mode dashboard reports the first and lets a "
                "reader conclude the second"),
        }

    # ------------------------------------------------------------- conclude
    def conclude(self, reference: str, conclusion: str, note: str,
                 actor: str = "system") -> Dict[str, Any]:
        """End the run with a verdict."""
        run = self.require(reference)
        if run["state"] != "running":
            raise LifecycleError("run_concluded", f"{reference} is concluded",
                                 "a run is concluded once")
        if conclusion not in CONCLUSIONS:
            raise LifecycleError(
                "unknown_conclusion", f"'{conclusion}' is not a conclusion",
                "one of " + "; ".join(f"{k} — {v}"
                                      for k, v in CONCLUSIONS.items()))
        if not (note or "").strip():
            raise LifecycleError(
                "note_required",
                "a conclusion with no note records a verdict and not the "
                "reasoning, and the reasoning is what somebody will be asked "
                "about",
                "say what the run showed")
        # Promoting on a run that could not answer the question is the failure
        # this refusal exists for: a shadow run is expensive, and the pressure
        # at the end of one is to conclude something rather than nothing.
        if conclusion == "promote" and not self.outcomes(reference)["conclusive"]:
            raise LifecycleError(
                "not_conclusive",
                f"{reference} has too few outcomes to support promotion. "
                f"Divergence alone says the two models differ; it does not say "
                f"the challenger is better, and promoting on it is promoting "
                f"on a number that answers a different question",
                "wait for outcomes, or conclude 'inconclusive', which is an "
                "honest end and a common one")
        with self.evidence.recording():
            self.runs.set({"state": "concluded", "closed_at": time.time(),
                           "closed_by": actor, "conclusion": conclusion,
                           "close_note": note.strip()}, id=run["id"])
            self.evidence.append(
                "parallel_run_concluded", "model", run["model_id"],
                {"reference": reference, "conclusion": conclusion,
                 "note": note}, actor=actor)
        return self.require(reference)

    # ------------------------------------------------------------------ read
    def require(self, reference: str) -> Dict[str, Any]:
        row = self.runs.one(reference=reference)
        if not row:
            raise LifecycleError("no_run", f"no parallel run '{reference}'",
                                 "references look like PAR-0001")
        return row

    def for_model(self, urn: str) -> List[Dict[str, Any]]:
        model = self.registry.require(urn)
        return self.runs.many(model_id=model["id"])

    def across_the_estate(self) -> Dict[str, Any]:
        rows = []
        for run in self.runs.many(state="running"):
            model = self.registry.by_id(run["model_id"]) or {}
            divergence = self.divergence(run["reference"])
            outcomes = self.outcomes(run["reference"])
            rows.append({
                "reference": run["reference"], "urn": model.get("urn"),
                "champion": run["champion_semver"],
                "challenger": run["challenger_semver"],
                "purpose": run["purpose"],
                "paired": divergence["paired"],
                "unpaired": divergence["unpaired"],
                "coverage": outcomes["coverage"],
                "conclusive": outcomes["conclusive"],
                "opened_at": run["opened_at"],
            })
        rows.sort(key=lambda r: r["opened_at"])
        waiting = [r for r in rows if not r["conclusive"]]
        return {
            "runs": rows, "count": len(rows),
            "waiting_on_outcomes": len(waiting),
            "detail": (
                f"{len(rows)} parallel run(s) open, {len(waiting)} of them "
                f"without enough outcomes to conclude on — which is the "
                f"ordinary state for most of a run's life, and is why a "
                f"divergence figure must never be read as a verdict"
                if rows else
                "no parallel run is open on this estate"),
        }
