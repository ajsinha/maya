"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two implementations of one model, and the shape of their disagreement.

Independent recode is the strongest form of validation there is and the only one
that catches a specification the code does not implement: a validator reads the
documentation, writes their own version from it, and the two are run on the same
inputs. `core.validation.replay` already re-runs a *stored test* and is a
different thing — that establishes reproducibility of a result, not
independence of an implementation.

**The distribution is the whole contribution.** A recode that agrees to twelve
decimal places on 9,997 rows and disagrees wildly on three is a completely
different finding from one that is off by 1e-9 everywhere, and a pass rate
reports them identically. The first is a branch nobody tested — a boundary
condition, a missing case in a piecewise function, a tie-break — and it is
exactly what independent recode exists to find. The second is float ordering and
means the two implementations agree.

So this reports the quantiles, and it says which of those two shapes it is
looking at. **The number that matters is not how many rows matched.** It is
whether the ones that did not are a rounding tail or a cliff.

**What it does not do is run the validator's code.** MAYA takes two sets of
outputs. Executing a validator's implementation would put arbitrary code in the
control plane, and the platform's whole position on artifacts is that loading
one is a decision — a validation harness is not the place to make it quietly.
Where the outputs came from is recorded rather than assumed.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Sequence, Tuple

#: Below this, two floats are the same number computed twice. Above it, they
#: are two different answers. The default is loose enough that summation order
#: does not register and tight enough that a real difference does.
DEFAULT_TOLERANCE = 1e-9

#: How much bigger the worst disagreement has to be than the typical one before
#: the shape is a cliff rather than a tail. Three orders of magnitude, because
#: that is the gap between float noise and a wrong branch, and anything smaller
#: would call ordinary numerical drift a cliff.
CLIFF_RATIO = 1000.0

#: A relative difference below this is a hair, whatever the absolute
#: tolerance says. Used to tell a too-tight tolerance from a real
#: disagreement when everything differs.
NEGLIGIBLE_RELATIVE = 1e-6


class RecodeHarness:
    """Compares two implementations and reports the shape of the difference."""

    def __init__(self, validations=None, evidence=None):
        self.validations, self.evidence = validations, evidence

    # --------------------------------------------------------------- compare
    def compare(self, model: Dict[str, float], recode: Dict[str, float], *,
                tolerance: float = DEFAULT_TOLERANCE,
                model_source: str = "unstated",
                recode_source: str = "unstated") -> Dict[str, Any]:
        """Two sets of outputs, keyed by the input they came from."""
        from core.validation.common import ValidationError

        if not model or not recode:
            raise ValidationError(
                "an independent recode needs outputs from both "
                "implementations; one side alone establishes nothing")
        shared = sorted(set(model) & set(recode))
        if not shared:
            raise ValidationError(
                "the two sets of outputs share no input at all, so there is "
                "nothing to compare. The keys have to be the inputs each side "
                "was given, or this is two unrelated lists")

        only_model = sorted(set(model) - set(recode))
        only_recode = sorted(set(recode) - set(model))

        diffs: List[Tuple[str, float, float]] = []
        for key in shared:
            a, b = float(model[key]), float(recode[key])
            absolute = abs(a - b)
            scale = max(abs(a), abs(b))
            relative = absolute / scale if scale else 0.0
            diffs.append((key, absolute, relative))

        agreed = [d for d in diffs if d[1] <= tolerance]
        disagreed = [d for d in diffs if d[1] > tolerance]
        disagreed.sort(key=lambda d: -d[1])

        return {
            "compared": len(shared),
            "agreed": len(agreed), "disagreed": len(disagreed),
            "tolerance": tolerance,
            "only_in_model": only_model, "only_in_recode": only_recode,
            "distribution": self._distribution([d[1] for d in diffs]),
            "relative_distribution": self._distribution([d[2] for d in diffs]),
            # Named individually, because in the shape this is looking for
            # there are only a handful of them and each one is a bug report.
            "worst": [{"input": k, "model": model[k], "recode": recode[k],
                       "absolute": a, "relative": r}
                      for k, a, r in disagreed[:10]],
            "shape": self._shape(diffs, disagreed, tolerance),
            "sources": {"model": model_source, "recode": recode_source},
        }

    @staticmethod
    def _distribution(values: Sequence[float]) -> Dict[str, Any]:
        """Quantiles rather than a mean. A mean over a bimodal difference is a
        number that describes neither mode."""
        if not values:
            return {}
        ordered = sorted(values)

        def q(p: float) -> float:
            return ordered[min(len(ordered) - 1, int(p * len(ordered)))]

        return {"min": ordered[0], "p50": q(0.5), "p90": q(0.9),
                "p99": q(0.99), "max": ordered[-1],
                "mean": statistics.fmean(ordered)}

    @staticmethod
    def _shape(diffs: List[Tuple[str, float, float]],
               disagreed: List[Tuple[str, float, float]],
               tolerance: float) -> Dict[str, Any]:
        """A tail or a cliff, and why it matters which.

        This is the reading a pass rate cannot give. Nearly-everything-agrees
        with a handful of wild outliers means a branch nobody tested; a uniform
        smear of tiny differences means the two implementations agree and the
        arithmetic was done in a different order.
        """
        if not disagreed:
            return {"kind": "agreement",
                    "detail": (f"every compared output agrees within "
                               f"{tolerance:g}. Two implementations written "
                               f"from the same specification produced the same "
                               f"answers, which is what independent recode is "
                               f"for")}
        absolutes = sorted(d[1] for d in diffs)
        typical = statistics.median(absolutes)
        worst = absolutes[-1]
        share = len(disagreed) / len(diffs)
        cliff = (worst > max(typical, tolerance) * CLIFF_RATIO and share < 0.05)
        if cliff:
            return {
                "kind": "cliff", "disagreeing_share": round(share, 4),
                "detail": (f"{len(disagreed)} of {len(diffs)} outputs disagree, "
                           f"and the worst is {worst:.3g} against a typical "
                           f"{typical:.3g}. That shape is a branch nobody "
                           f"tested — a boundary condition, a missing case in a "
                           f"piecewise function, a tie-break — and it is "
                           f"exactly what independent recode exists to find. "
                           f"The named outputs below are each a bug report"),
            }
        if share > 0.5:
            # Two readings, and telling them apart is worth the extra line.
            # Everything differing by a hair is a tolerance set tighter than
            # the arithmetic warrants; everything differing MATERIALLY is two
            # implementations computing different things. Calling the first
            # "systematic" would send a validator to re-read a specification
            # that is fine.
            relative = sorted(d[2] for d in disagreed)
            typical_relative = relative[len(relative) // 2]
            if typical_relative < NEGLIGIBLE_RELATIVE:
                return {
                    "kind": "tolerance", "disagreeing_share": round(share, 4),
                    "typical_relative": typical_relative,
                    "detail": (f"{share:.0%} of outputs exceed the absolute "
                               f"tolerance of {tolerance:g}, but the typical "
                               f"RELATIVE difference is {typical_relative:.2g} "
                               f"— a hair. This is a tolerance set tighter than "
                               f"the arithmetic warrants rather than two "
                               f"implementations disagreeing; raise it, or "
                               f"compare relatively")}
            return {
                "kind": "systematic", "disagreeing_share": round(share, 4),
                "typical_relative": typical_relative,
                "detail": (f"{share:.0%} of outputs disagree, by a typical "
                           f"{typical_relative:.2%} of their own magnitude. "
                           f"That is not a numerical artefact: the two "
                           f"implementations are computing different things, "
                           f"and the specification is where to look first")}
        return {
            "kind": "tail", "disagreeing_share": round(share, 4),
            "detail": (f"{len(disagreed)} of {len(diffs)} outputs differ by "
                       f"more than {tolerance:g}, with no outlier far from the "
                       f"rest. This reads as arithmetic done in a different "
                       f"order rather than a different calculation — but the "
                       f"tolerance is a choice, and a tighter one would say "
                       f"more")}

    # ---------------------------------------------------------------- record
    def record(self, validation_id: str, comparison: Dict[str, Any],
               actor: str = "system") -> Dict[str, Any]:
        """Put the comparison on the episode and on the evidence chain.

        The shape goes in the payload, not just the counts: *this recode found
        a cliff at three inputs* is the sentence a reader needs two years later,
        and a stored pass rate cannot be turned back into it.
        """
        if self.evidence is None:
            return comparison
        with self.evidence.recording():
            self.evidence.append(
                "independent_recode_compared", "validation", validation_id,
                {"compared": comparison["compared"],
                 "agreed": comparison["agreed"],
                 "disagreed": comparison["disagreed"],
                 "shape": comparison["shape"]["kind"],
                 "max_absolute": comparison["distribution"].get("max"),
                 "worst_inputs": [w["input"] for w in comparison["worst"][:5]],
                 "sources": comparison["sources"]}, actor=actor)
        return comparison
