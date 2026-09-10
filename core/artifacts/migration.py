"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A model converted from one format to another, and the claim that it is the same
model.

Format migration is real work a bank has to do — a pickle that no supported
runtime will load, a vendor artifact in a format the firm's grammar does not
admit, a framework going out of support. The requirement asks for an *agent*
that converts the artifact and verifies equivalence.

**MAYA does not convert it.** Converting means loading a model and running it,
and this platform does neither: it is a register. A register that converted
artifacts would be producing the thing it exists to make claims about, and the
claim *this artifact is equivalent to that one* would then rest on the word of
the party that produced both.

What MAYA does is the half a register is *for*: it holds the equivalence claim
to a standard, and it **refuses**.

  * A migration names two artifacts by digest, a probe set, and the results
    somebody else obtained by running both. MAYA never sees a model.
  * The probe set is graded against the version's **declared domain**
    (`FR-AI-008`). A migration verified over an interior-only probe set is
    verified over exactly the region where two implementations agree, and its
    pass tells you nothing — so a thin probe set makes the claim
    `unsubstantiated` rather than `passed`.
  * **Tolerance is declared before the results are read.** A tolerance chosen
    after seeing the divergences is not a tolerance, it is a description of the
    divergences, and it will be exactly wide enough.
  * A probe present in the set and **missing from the results** fails the
    migration. The commonest way an equivalence report passes is by quietly
    omitting the probes that did not.

And the claim, once recorded, is what an alias move can be refused against:
promoting a converted artifact whose equivalence was never demonstrated is the
outcome all of this exists to prevent.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Sequence

from core.artifacts.common import ArtifactError
from core.log import get_logger

logger = get_logger(__name__)

PASSED, FAILED, UNSUBSTANTIATED = "passed", "failed", "unsubstantiated"
OUTCOMES = (PASSED, FAILED, UNSUBSTANTIATED)

#: Below this share of declared constraints exercised, a passing comparison is
#: not evidence. Shared with the probe module deliberately: two thresholds for
#: one idea diverge, and the one that moves is the one nobody is reading.
from core.assist.probes import THIN_BELOW

#: A default that is small and stated. Any real migration declares its own —
#: what counts as the same answer is a property of the decision the model
#: feeds, not of the arithmetic.
DEFAULT_TOLERANCE = 1e-6


class FormatMigration:
    """Holds an equivalence claim to a standard. Converts nothing."""

    def __init__(self, registry, probes, evidence=None):
        self.registry, self.probes, self.evidence = registry, probes, evidence

    # -------------------------------------------------------------- verify
    def verify(self, urn: str, semver: str, *, from_digest: str,
               to_digest: str, to_format: str,
               probes: Sequence[Dict[str, Any]],
               results: Sequence[Dict[str, Any]],
               tolerance: Optional[float] = None,
               ran_by: str = "", now: Optional[float] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Judge an equivalence claim somebody else measured."""
        version = self.registry.version(urn, semver)
        if version is None:
            raise ArtifactError("unknown_version",
                                f"{urn} has no version {semver}",
                                "check the semver")
        if from_digest == to_digest:
            raise ArtifactError(
                "same_artifact",
                "the two digests are identical, so there is no conversion to "
                "verify", "name the artifact the conversion produced")
        if not (ran_by or "").strip():
            raise ArtifactError(
                "ran_by_required",
                "an equivalence claim must name who ran the probes — MAYA did "
                "not, and a measurement of unknown origin in the register is "
                "worse than none because it looks like one MAYA stands behind",
                "name the system or team that executed both artifacts")
        if tolerance is None:
            raise ArtifactError(
                "tolerance_required",
                "the tolerance must be declared with the claim and not chosen "
                "after the divergences are known — a tolerance picked from the "
                "results is not a tolerance, it is a description of them, and "
                "it will be exactly wide enough",
                f"declare one; {DEFAULT_TOLERANCE:g} is a starting point and "
                f"what counts as the same answer is a property of the decision "
                f"this model feeds")

        moment = now if now is not None else time.time()
        graded = self.probes.grade(urn, semver, probes)
        compared = self._compare(probes, results, float(tolerance))
        outcome = self._outcome(graded, compared)
        claim = {
            "urn": urn, "semver": semver,
            "from_digest": from_digest, "to_digest": to_digest,
            "to_format": to_format, "tolerance": float(tolerance),
            "ran_by": ran_by.strip(), "verified_at": moment,
            "converted_by_maya": False,
            "outcome": outcome,
            "coverage": graded["coverage"],
            "unexercised": graded["unexercised"],
            "probes": len(probes), "compared": compared["compared"],
            "missing_results": compared["missing"],
            "divergences": compared["divergences"],
            "worst_divergence": compared["worst"],
            "detail": self._detail(outcome, graded, compared, tolerance),
        }
        if self.evidence is not None:
            self.evidence.append(
                "migration_equivalence_claimed", "model_version",
                version.get("id") or f"{urn}@{semver}",
                {k: claim[k] for k in
                 ("from_digest", "to_digest", "to_format", "outcome",
                  "tolerance", "coverage", "ran_by", "probes")}, actor=actor)
        logger.info("migration %s -> %s for %s@%s: %s (coverage %.0f%%)",
                    from_digest[:16], to_digest[:16], urn, semver, outcome,
                    100 * graded["coverage"])
        return claim

    @staticmethod
    def _compare(probes: Sequence[Dict[str, Any]],
                 results: Sequence[Dict[str, Any]],
                 tolerance: float) -> Dict[str, Any]:
        """Pair each probe with its result and measure the gap.

        A probe with no result **fails**, and is not skipped. The commonest way
        an equivalence report passes is by quietly omitting the probes that did
        not — a report over 40 of 50 probes and a report over 50 look the same
        at the bottom of the page.
        """
        by_index = {r.get("probe"): r for r in results if "probe" in r}
        divergences, missing = [], []
        worst = 0.0
        for index, probe in enumerate(probes):
            result = by_index.get(index)
            if result is None:
                missing.append(index)
                continue
            left, right = result.get("from"), result.get("to")
            if left is None and right is None:
                # Both refused. That IS agreement, and about the most
                # informative kind: the boundary behaves the same way in both.
                continue
            if left is None or right is None:
                divergences.append({
                    "probe": index, "field": probe.get("field"),
                    "kind": probe.get("kind"), "gap": None,
                    "why": "one artifact answered and the other refused, which "
                           "is a divergence no tolerance covers"})
                worst = float("inf")
                continue
            if not (_is_number(left) and _is_number(right)):
                # A categorical answer. There is no such thing as nearly the
                # same category, so this is equality — and a NaN gap would have
                # compared as agreement, since every comparison with NaN is
                # false and `nan > tolerance` reads as "within tolerance".
                if str(left) != str(right):
                    divergences.append({
                        "probe": index, "field": probe.get("field"),
                        "kind": probe.get("kind"), "gap": None,
                        "why": f"answered {left!r} and {right!r}; there is no "
                               f"such thing as nearly the same category, so no "
                               f"tolerance covers this"})
                continue
            gap = abs(float(left) - float(right))
            worst = max(worst, gap)
            if gap > tolerance:
                divergences.append({
                    "probe": index, "field": probe.get("field"),
                    "kind": probe.get("kind"), "gap": gap,
                    "why": f"differs by {gap:.6g}, outside the declared "
                           f"tolerance of {tolerance:g}"})
        return {"compared": len(probes) - len(missing), "missing": missing,
                "divergences": divergences,
                "worst": worst if worst != float("inf") else None}

    @staticmethod
    def _outcome(graded: Dict[str, Any], compared: Dict[str, Any]) -> str:
        if compared["divergences"] or compared["missing"]:
            return FAILED
        if graded["thin"]:
            return UNSUBSTANTIATED
        return PASSED

    @staticmethod
    def _detail(outcome, graded, compared, tolerance) -> str:
        if outcome == FAILED and compared["missing"]:
            return (f"{len(compared['missing'])} probe(s) in the set have no "
                    f"result. A missing result fails the migration and is not "
                    f"skipped: the commonest way an equivalence report passes "
                    f"is by quietly omitting the probes that did not, and a "
                    f"report over 40 of 50 probes looks exactly like a report "
                    f"over 50 at the bottom of the page")
        if outcome == FAILED:
            return (f"{len(compared['divergences'])} probe(s) diverge beyond "
                    f"the declared tolerance of {tolerance:g}. The conversion "
                    f"produced a different model, which is the answer this "
                    f"check exists to be able to give")
        if outcome == UNSUBSTANTIATED:
            return (f"every compared probe agrees, and the probe set exercises "
                    f"only {graded['coverage']:.0%} of the declared domain — "
                    f"below the {THIN_BELOW:.0%} at which agreement is "
                    f"evidence. Two implementations agree in the interior by "
                    f"construction; they come apart at the boundary, and this "
                    f"set does not reach it. **This is not a pass**, and "
                    f"recording it as one is the failure the whole check is "
                    f"arranged against")
        return (f"every one of {compared['compared']} probe(s) agrees within "
                f"{tolerance:g}, over a set exercising {graded['coverage']:.0%} "
                f"of the declared domain. MAYA did not convert the artifact and "
                f"did not run the probes: this is the register holding somebody "
                f"else's measurement to a standard, which is the half a "
                f"register is for")

    # ------------------------------------------------------------------ what
    @staticmethod
    def describe() -> Dict[str, Any]:
        return {
            "outcomes": [
                {"outcome": PASSED,
                 "means": "every probe agrees within the declared tolerance, "
                          "over a set that reaches the boundary"},
                {"outcome": FAILED,
                 "means": "a probe diverged, or a probe has no result — a "
                          "missing result fails and is never skipped"},
                {"outcome": UNSUBSTANTIATED,
                 "means": "everything compared agrees and the probe set is too "
                          "thin for that to be evidence. Not a pass"},
            ],
            "converts": False, "runs_probes": False,
            "thin_below": THIN_BELOW,
            "detail": ("MAYA does not convert artifacts and does not run "
                       "probes: converting means loading and running a model, "
                       "and a register that produced both the artifact and the "
                       "claim about it would be the only witness to its own "
                       "work. What it does is hold the equivalence claim to a "
                       "standard, and refuse"),
        }


def _is_number(value: Any) -> bool:
    """Whether two answers can be compared by distance at all."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)
