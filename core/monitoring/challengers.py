"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Champion and challenger, and the two words people use interchangeably.

A challenger beats a champion when it is **better**, and "better" is two
separate claims that a single number hides:

  * **Significant** — the difference is larger than the noise in the windows it
    was measured over. With enough windows, any difference is significant,
    including one nobody would act on.
  * **Material** — the difference is large enough to be worth the cost of a
    revalidation, a redeployment and a change of the thing the bank uses to
    decide. That threshold is a business judgement and is declared, never
    computed.

Both are reported, and neither is collapsed into the other. A challenger that
is significant and immaterial is the ordinary result of a long comparison and
the ordinary reason to leave the champion alone.

**The comparison is paired.** The two versions are compared window by window on
the same monitor definition — same kind, same test, same slice — and the test
is over the *differences*, not over the two series of levels. Comparing the mean
AUC of one version against the mean AUC of another ignores that both moved
together when the population moved, which is most of what they did.

**The significance test is exact where exactness is affordable.** Under the null
hypothesis that the two versions are the same, the sign of each paired
difference is exchangeable, so enumerating all 2^n sign flips gives the exact
two-sided p-value. That is done up to `EXACT_UP_TO` windows; above it a normal
approximation is used and **the answer says which**, because a p-value whose
method is unstated is a p-value nobody can reproduce.

**The recommendation is never to promote.** MAYA is a register: it does not run
models, and it does not decide which one the bank uses. A monitoring module that
recommended promotion would be a first line marking its own work, and the
promotion of a version already requires a second-line approval that this must
not pre-empt. What a comparison recommends is that somebody *look* — that a
validation be opened — and the strongest thing it will ever say is that the
evidence for looking is strong.
"""
from __future__ import annotations

import math
import time
from itertools import product
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger
from core.monitoring.common import MonitorError

logger = get_logger(__name__)

# Below this many paired windows, no test is run. Three windows agreeing is a
# coin landing the same way three times, and reporting a p-value for it lends
# arithmetic authority to a coincidence.
MINIMUM_PAIRS = 5

# Where exact enumeration stops being affordable. 2^14 is 16,384 sign flips,
# which is instant; 2^20 is a million and would not be.
EXACT_UP_TO = 14

# Two-sided significance level. Declared here rather than passed, so that
# nobody chooses it after seeing the number.
ALPHA = 0.05

# How much better a challenger has to be, in the units of the test itself,
# before the difference is worth a revalidation. Overridable per comparison,
# because 0.01 of AUC and 0.01 of RMSE are not the same size of news.
MATERIAL_BY_DEFAULT = 0.01

INSUFFICIENT = "insufficient_evidence"
NO_DIFFERENCE = "no_material_difference"
CHALLENGER_AHEAD = "challenger_ahead"
CHAMPION_AHEAD = "champion_ahead"
RECOMMENDATIONS: Tuple[str, ...] = (INSUFFICIENT, NO_DIFFERENCE,
                                    CHALLENGER_AHEAD, CHAMPION_AHEAD)

EXACT, APPROXIMATE = "exact_sign_flip", "normal_approximation"


class ChampionChallenger:
    """Compares two versions on the monitors they share, over the same windows."""

    def __init__(self, registry, monitoring, catalogue, aliases=None,
                 material=MATERIAL_BY_DEFAULT):
        self.registry, self.monitoring = registry, monitoring
        self.catalogue = catalogue
        # Optional: with it, "which one is the champion" is read from the alias
        # the bank actually serves rather than from whoever called this.
        self.aliases = aliases
        self.material = float(material)

    # ------------------------------------------------------------------ pairs
    def compare(self, urn: str, champion: str, challenger: str,
                material: Optional[float] = None,
                now: Optional[float] = None) -> Dict[str, Any]:
        """Every monitor the two versions share, tested pairwise."""
        model = self.registry.require(urn)
        if champion == challenger:
            raise MonitorError(
                "same_version",
                f"{champion} cannot be compared against itself",
                "name two different versions of this model")
        left = self._monitors(model, urn, champion)
        right = self._monitors(model, urn, challenger)
        shared = sorted(set(left) & set(right))
        if not shared:
            raise MonitorError(
                "no_shared_monitor",
                f"{champion} and {challenger} share no monitor definition, so "
                f"there is nothing they have both been asked",
                "define the same monitor — same kind, same test, same slice — "
                "against both versions; a comparison across different questions "
                "is not a comparison")

        tests = [self._one(key, left[key], right[key],
                           self.material if material is None else float(material))
                 for key in shared]
        return {
            "urn": urn, "champion": champion, "challenger": challenger,
            "compared_at": now if now is not None else time.time(),
            "serving": self._serving(urn),
            "tests": tests,
            "recommendation": self._recommend(tests),
            "unshared": {"champion_only": sorted(set(left) - set(right)),
                         "challenger_only": sorted(set(right) - set(left))},
        }

    def _monitors(self, model: Dict[str, Any], urn: str,
                  semver: str) -> Dict[Tuple, Dict[str, Any]]:
        """This version's monitors, keyed by the question they ask.

        The key is kind, test and slice — never the monitor's name. Two teams
        naming the same question differently is the ordinary case, and a
        comparison that matched on name would silently find nothing.
        """
        version = self.registry.version(urn, semver)
        if version is None:
            raise MonitorError("unknown_version",
                               f"{urn} has no version {semver}",
                               "check the semver")
        out: Dict[Tuple, Dict[str, Any]] = {}
        for monitor in self.monitoring.registry.for_model(model["id"]):
            if monitor.get("model_version_id") != version["id"]:
                continue
            key = (monitor["kind"], monitor["test_key"],
                   _canonical(monitor.get("slice") or {}))
            out[key] = monitor
        return out

    def _serving(self, urn: str) -> Optional[str]:
        if self.aliases is None:
            return None
        row = self.aliases.resolve(urn, "production", "champion")
        return row.get("semver") if row else None

    # ------------------------------------------------------------------- test
    def _one(self, key: Tuple, champion: Dict[str, Any],
             challenger: Dict[str, Any], material: float) -> Dict[str, Any]:
        kind, test_key, slice_ = key
        direction = self.catalogue.definition(test_key).direction
        pairs = self._pair(champion, challenger)
        header = {"kind": kind, "test": test_key, "slice": slice_,
                  "direction": direction, "pairs": len(pairs),
                  "material_threshold": material}

        if len(pairs) < MINIMUM_PAIRS:
            return {**header, "tested": False,
                    "recommendation": INSUFFICIENT,
                    "detail": (
                        f"{len(pairs)} overlapping window(s); a paired test "
                        f"needs {MINIMUM_PAIRS}. {len(pairs)} windows agreeing "
                        f"is a coin landing the same way {len(pairs)} times, and "
                        f"a p-value for it would lend arithmetic authority to a "
                        f"coincidence")}

        # Positive means the challenger is better, whichever way the test runs.
        sign = 1.0 if direction == "higher_is_better" else -1.0
        diffs = [sign * (b - a) for a, b in pairs]
        mean = sum(diffs) / len(diffs)
        p, method = _sign_flip_p(diffs)
        significant = p < ALPHA
        is_material = abs(mean) >= material

        return {**header, "tested": True,
                "mean_difference": round(mean, 6),
                "champion_mean": round(sum(a for a, _ in pairs) / len(pairs), 6),
                "challenger_mean": round(sum(b for _, b in pairs) / len(pairs), 6),
                "p_value": round(p, 6), "method": method, "alpha": ALPHA,
                "significant": significant, "material": is_material,
                "recommendation": _verdict(significant, is_material, mean),
                "detail": _test_detail(mean, p, method, significant, is_material,
                                       material, len(pairs), direction)}

    def _pair(self, champion: Dict[str, Any],
              challenger: Dict[str, Any]) -> List[Tuple[float, float]]:
        """Observations of the two monitors that cover the same window.

        Matched on the window the observation names, not on the order it was
        written. Two monitors evaluated on different schedules produce
        interleaved histories, and zipping them would pair last quarter against
        this one.
        """
        left = self._by_window(champion)
        right = self._by_window(challenger)
        return [(left[w], right[w]) for w in sorted(set(left) & set(right))]

    def _by_window(self, monitor: Dict[str, Any]) -> Dict[Tuple, float]:
        out: Dict[Tuple, float] = {}
        for row in self.monitoring.history(monitor["id"]):
            if row.get("value") is None:
                continue
            window = (row.get("window_start"), row.get("window_end"))
            if window == (None, None):
                continue
            out[window] = float(row["value"])
        return out

    # --------------------------------------------------------- recommendation
    @staticmethod
    def _recommend(tests: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """One verdict over several tests, and what it asks somebody to do.

        Never 'promote'. MAYA does not decide which model the bank uses, and a
        promotion needs a second-line approval this must not pre-empt. The
        strongest thing available here is that the evidence for *looking* is
        strong.
        """
        tested = [t for t in tests if t["tested"]]
        if not tested:
            return {"verdict": INSUFFICIENT, "action": "no action",
                    "detail": ("no test had enough paired windows to run, so "
                               "this comparison has not compared anything yet")}
        ahead = [t for t in tested if t["recommendation"] == CHALLENGER_AHEAD]
        behind = [t for t in tested if t["recommendation"] == CHAMPION_AHEAD]
        if ahead and not behind:
            return {"verdict": CHALLENGER_AHEAD,
                    "action": "open a validation of the challenger",
                    "detail": (f"the challenger is significantly and materially "
                               f"ahead on {len(ahead)} of {len(tested)} test(s) "
                               f"and behind on none. That is a reason to look, "
                               f"not a decision to switch: promotion is a "
                               f"second-line approval and this is a measurement")}
        if behind and not ahead:
            return {"verdict": CHAMPION_AHEAD, "action": "no action",
                    "detail": (f"the champion is ahead on {len(behind)} of "
                               f"{len(tested)} test(s); the challenger has not "
                               f"made its case")}
        if ahead and behind:
            return {"verdict": NO_DIFFERENCE,
                    "action": "open a validation of the challenger",
                    "detail": (f"the challenger is ahead on {len(ahead)} test(s) "
                               f"and behind on {len(behind)}. A model that is "
                               f"better at one thing and worse at another is a "
                               f"trade-off, and a trade-off is a judgement "
                               f"somebody has to make rather than a number")}
        return {"verdict": NO_DIFFERENCE, "action": "no action",
                "detail": (f"across {len(tested)} test(s) nothing is both "
                           f"significant and material. With enough windows any "
                           f"difference becomes significant, which is why "
                           f"materiality is asked separately and why the answer "
                           f"here is to leave the champion alone")}

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every model where a challenger is being run beside a champion."""
        rows: List[Dict[str, Any]] = []
        for model in self.registry.list():
            urn = model["urn"]
            served = self._serving(urn)
            if served is None:
                continue
            champion = self._monitors(model, urn, served)
            for version in self.registry.versions(urn):
                candidate = version["semver"]
                if candidate == served:
                    continue
                # Sharing no monitor is the ordinary case for most pairs of
                # versions, so the sweep skips them rather than catching the
                # refusal `compare` raises. The difference is deliberate: a
                # caller who named two versions meant those two and is owed an
                # explanation, and a sweep that named nobody is not.
                if not (set(champion) & set(self._monitors(model, urn, candidate))):
                    continue
                rows.append(self.compare(urn, served, candidate, now=now))
        rows.sort(key=lambda r: r["recommendation"]["verdict"] != CHALLENGER_AHEAD)
        ahead = [r for r in rows
                 if r["recommendation"]["verdict"] == CHALLENGER_AHEAD]
        return {"comparisons": rows, "count": len(rows), "challengers_ahead": len(ahead),
                "detail": (f"{len(rows)} champion/challenger pair(s) share a "
                           f"monitor definition; {len(ahead)} have a challenger "
                           f"materially ahead and worth opening a validation on"
                           if rows else
                           "no two versions of any model are being asked the "
                           "same monitored question, so nothing is being "
                           "compared — which is the usual reason a "
                           "champion/challenger programme reports nothing")}


def _verdict(significant: bool, material: bool, mean: float) -> str:
    if not (significant and material):
        return NO_DIFFERENCE
    return CHALLENGER_AHEAD if mean > 0 else CHAMPION_AHEAD


def _test_detail(mean, p, method, significant, material, threshold, n,
                 direction) -> str:
    who = "challenger" if mean > 0 else "champion"
    out = (f"over {n} paired window(s) the {who} is ahead by "
           f"{abs(mean):.4g} ({direction.replace('_', ' ')}), p={p:.4g} by "
           f"{method.replace('_', ' ')}")
    if significant and material:
        return out + (f" — significant at {ALPHA} and above the materiality "
                      f"threshold of {threshold:.4g}")
    if significant and not material:
        return out + (f" — significant, but below the materiality threshold of "
                      f"{threshold:.4g}. With enough windows any difference is "
                      f"significant, and this one is not worth a redeployment")
    if material and not significant:
        return out + (f" — above the materiality threshold of {threshold:.4g}, "
                      f"but the windows disagree enough that it could be noise")
    return out + " — neither significant nor material"


def _sign_flip_p(diffs: Sequence[float]) -> Tuple[float, str]:
    """Two-sided p-value for the mean of paired differences.

    Under the null that the two versions are the same, the sign of each paired
    difference is exchangeable — so the exact null distribution of the mean is
    the set of all sign flips. That is enumerable up to `EXACT_UP_TO` and is
    enumerated; beyond it a normal approximation stands in and the caller is
    told so, because a p-value whose method is unstated is one nobody can
    reproduce.
    """
    n = len(diffs)
    observed = abs(sum(diffs))
    if n <= EXACT_UP_TO:
        at_least = sum(1 for signs in product((1, -1), repeat=n)
                       if abs(sum(s * d for s, d in zip(signs, diffs))) >= observed
                       - 1e-12)
        return at_least / (2 ** n), EXACT
    mean = sum(diffs) / n
    variance = sum((d - mean) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
    if variance <= 0:
        # Every window agrees exactly. That is either a real and perfectly
        # consistent difference or the same number recorded twice, and the
        # p-value cannot tell them apart, so it does not pretend to.
        return (0.0 if mean else 1.0), APPROXIMATE
    z = mean / math.sqrt(variance / n)
    return math.erfc(abs(z) / math.sqrt(2.0)), APPROXIMATE


def _canonical(slice_: Dict[str, Any]) -> Tuple:
    return tuple(sorted((str(k), str(v)) for k, v in (slice_ or {}).items()))
