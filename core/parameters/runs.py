"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The record of an activity somebody else executed, and the word that matters.

Every experiment tracker records runs, and every one of them records the run
**when it finishes**. That produces a register of successes. A fit that started,
consumed a warrant, read a snapshot of somebody's data and then vanished —
because the node was preempted, because the job was killed, because nobody was
watching — appears in none of them, and it is the run a supervisor asks about.

So a run here is **opened before it happens and closed after**, and an open run
past its own expected duration is `lost`. Lost is a state, not an absence.

**MAYA does not submit the job.** The requirement asks for orchestration against
a compute backend and this is the callee, always: it registers the authority
(the warrant), records what a run declared before it started, and takes delivery
of what it produced. A register that submitted jobs would be on the failure path
of the thing it exists to observe, and would need a client for every backend a
bank has.

**And it does not fetch the logs.** `log_uri` is recorded and never read.
Reading it would put the platform's readiness on somebody else's object store,
and the value of the field is that a person can find the logs — not that MAYA
can.

**A search is a parent with children, and the number nobody reports is the count
of children.** A hyperparameter search that tried four hundred configurations
and published the best one is a multiple-comparisons problem: the best of four
hundred draws from a null distribution looks excellent. Reporting only the
winner hides the four hundred, so the parent carries the count, the cost is
summed from the children, and selecting a child is explicitly **not** approving
it — a parameter set becomes usable by being approved, and a search cannot
approve its own output.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Sequence

from core.execution.grammar.vocabulary import VERBS as GRAMMAR_VERBS
from core.log import get_logger
from core.parameters.common import ParameterError

logger = get_logger(__name__)

DAY = 86400.0

OPEN, SUCCEEDED, FAILED, LOST, ABANDONED = (
    "open", "succeeded", "failed", "lost", "abandoned")
STATES = (OPEN, SUCCEEDED, FAILED, LOST, ABANDONED)
CLOSED_STATES = (SUCCEEDED, FAILED, ABANDONED)

#: The warrant grammar's own vocabulary, imported rather than
#: repeated: a run and the authority for it must not be able to
#: describe the same activity differently.
VERBS = tuple(GRAMMAR_VERBS)

#: How far past its own expected duration an open run has to be before it is
#: read as lost. Generous, because a slow run and a dead one look identical for
#: a while and calling a slow one dead would train people to ignore the state.
LOST_AFTER = 3.0

#: What a resource profile has to name. Not enforced as a schema — a firm's
#: backends differ — but the absences are reported, because a run whose
#: hardware nobody recorded cannot be costed or reproduced.
PROFILE_FIELDS = ("hardware", "replicas", "memory_gb", "backend")


class Runs:
    """Runs somebody else executed, declared before they ran."""

    def __init__(self, runs, registry, evidence, warrants=None,
                 parameters=None):
        self.runs, self.registry, self.evidence = runs, registry, evidence
        self.warrants, self.parameters = warrants, parameters

    # ------------------------------------------------------------------- open
    def open(self, reference: str, *, verb: str, urn: str = "",
             semver: str = "", warrant_id: str = "", parent: str = "",
             purpose: str = "", resource_profile: Optional[Dict] = None,
             environment: Optional[Dict] = None,
             inputs: Optional[Dict] = None,
             hyperparameters: Optional[Dict] = None,
             seeds: Optional[Dict] = None, log_uri: str = "",
             expected_seconds: Optional[float] = None,
             now: Optional[float] = None,
             actor: str = "system") -> Dict[str, Any]:
        """Declare a run before it happens."""
        if verb not in VERBS:
            raise ParameterError(
                "unknown_verb", f"'{verb}' is not one of the ten verbs",
                f"the grammar's vocabulary is {', '.join(VERBS)} — a run and "
                f"the warrant authorising it must not be able to describe the "
                f"same activity differently")
        if self.runs.one(reference=reference):
            raise ParameterError(
                "run_already_open",
                f"a run with reference '{reference}' already exists",
                "give this one its own reference; two runs under one name "
                "produce one lineage covering two activities")
        parent_row = None
        if parent:
            parent_row = self.require(parent)
            if parent_row["state"] != OPEN:
                raise ParameterError(
                    "parent_closed",
                    f"run '{parent}' is {parent_row['state']}, so a child "
                    f"starting now would be outside the search it belongs to",
                    "open a new parent")
            if parent_row.get("parent_id"):
                raise ParameterError(
                    "nesting_too_deep",
                    "a run may have children and grandchildren would make the "
                    "child count — the number that makes a "
                    "multiple-comparisons problem visible — depend on how "
                    "somebody chose to group them",
                    "open the child against the top-level search")
        model = self.registry.require(urn) if urn else None
        version = (self.registry.version(urn, semver)
                   if urn and semver else None)
        moment = now if now is not None else time.time()
        row = {
            "reference": reference, "model_id": (model or {}).get("id"),
            "model_version_id": (version or {}).get("id"), "verb": verb,
            "warrant_id": warrant_id or None,
            "parent_id": (parent_row or {}).get("id"),
            "purpose": purpose,
            "resource_profile": dict(resource_profile or {}),
            "environment": dict(environment or {}),
            "inputs": dict(inputs or {}),
            "hyperparameters": dict(hyperparameters or {}),
            "seeds": dict(seeds or {}), "log_uri": log_uri,
            "metrics": {}, "parameter_set_id": None, "state": OPEN,
            "outcome_note": "", "expected_seconds": expected_seconds,
            "cost": None, "opened_by": actor, "opened_at": moment,
            "closed_at": None, "closed_by": None,
        }
        with self.evidence.recording():
            self.runs.add(row)
            self.evidence.append(
                "run_opened", "model" if model else "run",
                (model or row)["id"],
                {"reference": reference, "verb": verb, "urn": urn,
                 "parent": parent or None, "warrant": warrant_id or None,
                 "expected_seconds": expected_seconds}, actor=actor)
        logger.info("run %s (%s) opened by %s%s", reference, verb, actor,
                    f" under {parent}" if parent else "")
        return self.read(reference, now=moment)

    # ------------------------------------------------------------------ close
    def close(self, reference: str, *, state: str,
              metrics: Optional[Dict] = None, parameter_set_id: str = "",
              cost: Optional[float] = None, note: str = "",
              now: Optional[float] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Take delivery of what a run produced."""
        run = self.require(reference)
        if run["state"] != OPEN:
            raise ParameterError(
                "run_closed",
                f"run '{reference}' is already {run['state']}",
                "a run closes once; a second activity is a second run")
        if state not in CLOSED_STATES:
            raise ParameterError(
                "unknown_outcome", f"'{state}' is not an outcome for a run",
                f"close with one of {', '.join(CLOSED_STATES)} — `lost` is "
                f"derived from the clock and is not something a caller may "
                f"assert, because a caller able to report a run lost could "
                f"close one it would rather nobody read")
        if state == FAILED and not (note or "").strip():
            raise ParameterError(
                "note_required",
                "a failed run needs a note. The failures are the part of a "
                "training record anybody ever reads twice, and a bare 'failed' "
                "six months on is indistinguishable from a run nobody looked at",
                "say what went wrong")
        moment = now if now is not None else time.time()
        with self.evidence.recording():
            self.runs.set({"state": state, "metrics": dict(metrics or {}),
                           "parameter_set_id": parameter_set_id or None,
                           "cost": cost, "outcome_note": note.strip(),
                           "closed_at": moment, "closed_by": actor},
                          id=run["id"])
            self.evidence.append(
                "run_closed", "model" if run["model_id"] else "run",
                run["model_id"] or run["id"],
                {"reference": reference, "verb": run["verb"], "state": state,
                 "seconds": round(moment - run["opened_at"], 1), "cost": cost,
                 "parameter_set": parameter_set_id or None,
                 "metrics": dict(metrics or {})}, actor=actor)
        logger.info("run %s closed %s after %.0fs", reference, state,
                    moment - run["opened_at"])
        return self.read(reference, now=moment)

    # ------------------------------------------------------------------- read
    def read(self, reference: str,
             now: Optional[float] = None) -> Dict[str, Any]:
        """One run, with its children if it has any."""
        run = self.require(reference)
        moment = now if now is not None else time.time()
        children = self.runs.many(parent_id=run["id"])
        state = self._state(run, moment)
        elapsed = ((run["closed_at"] or moment) - run["opened_at"])
        return {
            **run, "state": state,
            "children": children, "child_count": len(children),
            # Summed from the children, because a search's cost is what it
            # spent and not what its winner spent.
            "cost_including_children": _summed(run, children),
            "elapsed_seconds": round(elapsed, 1),
            "missing_from_profile": [f for f in PROFILE_FIELDS
                                     if not (run.get("resource_profile")
                                             or {}).get(f)],
            "logs_fetched": False,
            "detail": self._detail(run, state, children, elapsed, moment),
        }

    @staticmethod
    def _state(run: Dict[str, Any], moment: float) -> str:
        """`lost` is derived from the clock and never asserted."""
        if run["state"] != OPEN:
            return run["state"]
        expected = run.get("expected_seconds")
        if expected and moment - run["opened_at"] > LOST_AFTER * expected:
            return LOST
        return OPEN

    def _detail(self, run, state, children, elapsed, moment) -> str:
        # The profile note is appended to every state, not only to a closed
        # run. An incomplete profile is a fact about the DECLARATION, and the
        # moment it is worth knowing is while the run is still open and
        # somebody could still fix the next one.
        missing = [f for f in PROFILE_FIELDS
                   if not (run.get("resource_profile") or {}).get(f)]
        gap = (f". The resource profile names no {', '.join(missing)}, so this "
               f"run cannot be costed or reproduced from the record"
               if missing else "")
        return self._state_detail(run, state, children, elapsed) + gap

    @staticmethod
    def _state_detail(run, state, children, elapsed) -> str:
        if state == LOST:
            return (f"this run has been open {elapsed / 3600:.1f} hours against "
                    f"an expected {run['expected_seconds'] / 3600:.1f}, so it "
                    f"is read as lost. It consumed a warrant and read whatever "
                    f"its inputs named, and it is here because a tracker that "
                    f"writes its row on success would have no record of it at "
                    f"all")
        if state == OPEN:
            return (f"open for {elapsed / 60:.0f} minute(s). Declared before it "
                    f"ran, which is the whole point: a run recorded only on "
                    f"success is a register of successes")
        out = f"{state} after {elapsed / 60:.0f} minute(s)"
        if children:
            discarded = [c for c in children
                         if not c.get("parameter_set_id")]
            out += (f", over {len(children)} child run(s) of which "
                    f"{len(discarded)} produced no parameter set. That count is "
                    f"the number nobody reports: the best of {len(children)} "
                    f"draws from a null distribution looks excellent, and "
                    f"publishing only the winner hides the rest")
        if run.get("parameter_set_id"):
            out += (". It produced a parameter set, which is not an approved "
                    "one — a search cannot approve its own output")
        return out

    def require(self, reference: str) -> Dict[str, Any]:
        row = self.runs.one(reference=reference)
        if not row:
            raise ParameterError("unknown_run", f"no run '{reference}'",
                                 "list the runs")
        return row

    # ----------------------------------------------------------------- search
    def search(self, reference: str,
               now: Optional[float] = None) -> Dict[str, Any]:
        """A parent and its children, ranked — and what the ranking hides."""
        parent = self.read(reference, now=now)
        children = [self.read(c["reference"], now=now)
                    for c in parent["children"]]
        succeeded = [c for c in children if c["state"] == SUCCEEDED]
        return {
            "reference": reference, "verb": parent["verb"],
            "children": children, "tried": len(children),
            "succeeded": len(succeeded),
            "failed_or_lost": len(children) - len(succeeded),
            "cost": parent["cost_including_children"],
            "selects": None,
            "detail": (
                f"{len(children)} configuration(s) tried, {len(succeeded)} "
                f"succeeded, at a total cost of "
                f"{parent['cost_including_children'] or 0:.2f}. **The count is "
                f"the finding.** The best of {len(children)} draws from a null "
                f"distribution looks excellent, and a search that publishes "
                f"only its winner has hidden a multiple-comparisons problem "
                f"rather than solved one. MAYA does not select: choosing a "
                f"child is approving a parameter set, and that is an act with "
                f"a person's name on it"
                if children else
                "this run has no children, so it is not a search"),
        }

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every run, lost first."""
        moment = now if now is not None else time.time()
        rows = [self.read(r["reference"], now=moment)
                for r in self.runs.many() if not r.get("parent_id")]
        rows.sort(key=lambda r: (r["state"] != LOST, r["state"] != OPEN,
                                 -(r["opened_at"] or 0.0)))
        lost = [r for r in rows if r["state"] == LOST]
        by_state: Dict[str, int] = {}
        for row in rows:
            by_state[row["state"]] = by_state.get(row["state"], 0) + 1
        unprofiled = [r["reference"] for r in rows if r["missing_from_profile"]]
        return {
            "runs": rows, "count": len(rows), "by_state": by_state,
            "lost": [r["reference"] for r in lost],
            "without_a_resource_profile": unprofiled,
            "cost": round(sum(r["cost_including_children"] or 0.0
                              for r in rows), 2),
            "submits_jobs": False, "fetches_logs": False,
            "detail": self._estate_detail(rows, lost, by_state, unprofiled),
        }

    @staticmethod
    def _estate_detail(rows, lost, by_state, unprofiled) -> str:
        if not rows:
            return ("no run is recorded. MAYA does not submit jobs, so an empty "
                    "run register means nothing has declared itself rather than "
                    "that nothing has run — which is the honest reading and the "
                    "uncomfortable one")
        out = (f"{len(rows)} top-level run(s): "
               + ", ".join(f"{n} {s}" for s, n in sorted(by_state.items())))
        if lost:
            out += (f". {len(lost)} are lost — open well past their own "
                    f"expected duration. Each consumed a warrant and read "
                    f"whatever its inputs named, and a tracker writing its row "
                    f"on success would have no record of any of them")
        if unprofiled:
            out += (f". {len(unprofiled)} carry no complete resource profile "
                    f"and cannot be costed or reproduced from the record")
        return out

    @staticmethod
    def describe() -> Dict[str, Any]:
        return {
            "verbs": list(VERBS), "states": list(STATES),
            "profile_fields": list(PROFILE_FIELDS),
            "lost_after_multiple": LOST_AFTER,
            "submits_jobs": False, "fetches_logs": False,
            "detail": ("a run is opened BEFORE it happens and closed after, "
                       "because a run recorded only on success is a register "
                       "of successes — and the run a supervisor asks about is "
                       "the one that consumed a warrant, read a snapshot and "
                       "vanished. MAYA does not submit jobs and never reads "
                       "`log_uri`: fetching it would put the platform's "
                       "readiness on somebody else's object store and make it "
                       "a client of every backend a bank has"),
        }


def _summed(run: Dict[str, Any],
            children: Sequence[Dict[str, Any]]) -> Optional[float]:
    costs = [c["cost"] for c in children if c.get("cost") is not None]
    own = run.get("cost")
    if own is None and not costs:
        return None
    return round((own or 0.0) + sum(costs), 4)
