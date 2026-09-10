"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Watching a model that changes itself.

**A T4 model has no version bump for anything to notice, and that is the whole
problem.** Every other control in this platform fires on a version: a new version
is reviewed, approved, aliased, compared against its predecessor. An adaptive
model changes underneath a version nobody re-approved, so none of that machinery
sees it. What moves is the **parameter set** — a new point in `P` under the same
kernel — and the trajectory of those points is the only place the change is
visible at all.

**The alarm that matters is cumulative drift since somebody last looked, not the
size of any one step.** A model that re-fits nightly and moves a tenth of a
percent each time has moved three percent in a month, and every single step
passed a per-change threshold comfortably. That is how an adaptive model ends up
somewhere nobody approved without any individual act being wrong — and it is
invisible to exactly the check most firms write. So the cumulative figure is
measured from the **last human decision**: the most recent approval of a
parameter set, because that is the last moment somebody looked at where the model
was.

**Magnitude needs a metric, and the honest one depends on what the parameters
are.** A coefficient vector in the register can be compared numerically. An
opaque artifact can only say *it changed* — and reporting that as a magnitude of
1.0 would be a number pretending to be a measurement. So a step is `measured` or
`opaque`, said out loud, and a trajectory of opaque steps reports **how often**
without pretending to know how far.

**The trajectory is retained and never compacted.** The question asked after an
adaptive model goes wrong is *when did it start moving*, and a current-state view
cannot answer it. Parameter sets are already append-only for a different reason;
this reads them forwards.
"""
from __future__ import annotations

import time
from itertools import pairwise
from typing import Any, Dict, Optional, Sequence

DAY = 86400.0

#: How a step's size was arrived at. `opaque` is a real answer: a model whose
#: parameters are an artifact can say that it changed and cannot say how far,
#: and a platform that invented a number there would be inventing the control.
MEASURED, OPAQUE = "measured", "opaque"

#: Relative movement in a single step that is worth naming on its own.
STEP_EXCURSION = 0.10

#: Cumulative movement since the last human decision that is worth naming. Lower
#: than the step threshold on purpose — this is the one that catches the model
#: nobody noticed moving, and a bound above the step bound could never fire
#: first.
CUMULATIVE_EXCURSION = 0.25

#: How often a set of parameters may change before the frequency itself is the
#: finding. A model re-fitting more than this in a window is one whose change
#: process is running faster than anybody can review it.
CHANGES_PER_WINDOW = 30
WINDOW_DAYS = 30.0


class AdaptiveChange:
    """Reads the parameter trajectory of a self-changing model."""

    def __init__(self, parameters, registry, fibres=None, findings=None):
        self.parameters, self.registry = parameters, registry
        # Which classes change themselves. Read from the fibres rather than
        # hardcoded to T4: what a class IS decides which questions it can be
        # asked, and a second list here would disagree the first time either
        # moved.
        self.fibres, self.findings = fibres, findings

    # ---------------------------------------------------------------- steps
    def trajectory(self, urn: str, semver: str,
                   name: Optional[str] = None) -> Dict[str, Any]:
        """Every point this version's parameters have been, in order."""
        version = self.registry.version_service.require(urn, semver)
        rows = [r for r in self.parameters.parameters.many(
            model_version_id=version["id"])
            if name is None or r.get("name") == name]
        rows.sort(key=lambda r: (r.get("version") or 0, r.get("created_at") or 0))

        steps = []
        for older, newer in pairwise(rows):
            steps.append(self._step(older, newer))
        anchor = self._last_decision(rows)
        cumulative = self._cumulative(rows, anchor)
        return {
            "urn": urn, "semver": semver, "points": len(rows),
            "steps": steps,
            "measured_steps": sum(1 for s in steps if s["how"] == MEASURED),
            "opaque_steps": sum(1 for s in steps if s["how"] == OPAQUE),
            "since_last_decision": cumulative,
            "detail": self._detail(rows, steps, cumulative),
        }

    def _step(self, older: Dict[str, Any],
              newer: Dict[str, Any]) -> Dict[str, Any]:
        """How far the parameters moved between two consecutive points."""
        left = older.get("values_inline") or {}
        right = newer.get("values_inline") or {}
        base = {
            "from_version": older.get("version"),
            "to_version": newer.get("version"),
            "at": newer.get("created_at"),
            "provenance": newer.get("provenance"),
        }
        if not left or not right:
            # The parameters live in an artifact, so the register holds the
            # digest and nothing else. It changed; how far is not a question
            # this platform can answer, and saying 1.0 would invent the control.
            changed = older.get("digest") != newer.get("digest")
            return {**base, "how": OPAQUE, "magnitude": None,
                    "changed": changed,
                    "why": ("the parameters are not in the register, so this "
                            "can say that they changed and not how far. "
                            "Reporting a magnitude here would be a number "
                            "pretending to be a measurement")}
        magnitude = self._relative(left, right)
        return {**base, "how": MEASURED, "magnitude": magnitude,
                "changed": magnitude > 0.0,
                "excursion": magnitude >= STEP_EXCURSION,
                "why": (f"the largest relative move in any single coefficient "
                        f"was {magnitude:.2%}")}

    @staticmethod
    def _relative(left: Dict[str, Any], right: Dict[str, Any]) -> float:
        """The largest relative move in any one coefficient.

        The maximum rather than a norm, and deliberately: a single coefficient
        doubling is the thing somebody needs to know about, and an average over
        four hundred stable ones would bury it. A norm answers *how much did the
        model move overall*; this answers *did anything move a lot*, which is
        the question an excursion alarm is asking.
        """
        worst = 0.0
        for key in set(left) | set(right):
            a, b = left.get(key, 0.0), right.get(key, 0.0)
            # Filtered rather than caught. A coefficient set can carry a label
            # or a nested block beside its numbers, and skipping those in a
            # handler would mean a per-item log line for every one of four
            # hundred on every comparison — which is a control nobody reads
            # drowning the one they do.
            if not isinstance(a, (int, float)) or isinstance(a, bool):
                continue
            if not isinstance(b, (int, float)) or isinstance(b, bool):
                continue
            scale = max(abs(float(a)), abs(float(b)))
            if not scale:
                continue
            worst = max(worst, abs(float(a) - float(b)) / scale)
        return worst

    @staticmethod
    def _last_decision(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """The most recent parameter set a person approved.

        The anchor for cumulative drift, because that is the last moment
        somebody looked at where the model was. Measuring drift from the first
        point ever would make an old model permanently in excursion; measuring
        it from the previous point is the per-step check that misses the slow
        walk.
        """
        approved = [r for r in rows if r.get("state") == "approved"
                    or r.get("approved_at")]
        return approved[-1] if approved else (rows[0] if rows else None)

    def _cumulative(self, rows: Sequence[Dict[str, Any]],
                    anchor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """How far it has moved since somebody last looked.

        The figure that catches the model nobody noticed moving: a tenth of a
        percent a night is three percent a month, and every single step passed
        a per-change threshold comfortably.
        """
        if not rows or anchor is None or rows[-1] is anchor:
            return {"measurable": False, "magnitude": None, "steps": 0,
                    "why": ("the latest parameters are the ones somebody last "
                            "approved, so nothing has moved since anybody "
                            "looked")}
        latest = rows[-1]
        left = anchor.get("values_inline") or {}
        right = latest.get("values_inline") or {}
        # Located by identity rather than by `.index`, which compares by
        # equality: two parameter sets with the same values would match the
        # wrong one, and the step count would silently be off.
        index = next((i for i, row in enumerate(rows) if row is anchor), 0)
        steps = len(rows) - index - 1
        if not left or not right:
            return {"measurable": False, "magnitude": None, "steps": steps,
                    "anchor_version": anchor.get("version"),
                    "why": (f"the parameters are not in the register, so this "
                            f"can say the model has changed {steps} time(s) "
                            f"since it was last approved and not how far")}
        magnitude = self._relative(left, right)
        return {
            "measurable": True, "magnitude": magnitude, "steps": steps,
            "anchor_version": anchor.get("version"),
            "excursion": magnitude >= CUMULATIVE_EXCURSION,
            "why": (f"{magnitude:.2%} away from what was last approved, over "
                    f"{steps} autonomous change(s). This is the figure that "
                    f"catches the slow walk: a tenth of a percent a night is "
                    f"three percent a month, and every step passes a per-change "
                    f"threshold comfortably"),
        }

    @staticmethod
    def _detail(rows, steps, cumulative) -> str:
        if len(rows) < 2:
            return ("this version's parameters have been set once, so there is "
                    "no trajectory yet — which is what a model that does not "
                    "change itself looks like")
        out = f"{len(rows)} point(s) in P, {len(steps)} autonomous change(s)"
        if cumulative.get("excursion"):
            out += (f". It is {cumulative['magnitude']:.1%} away from what was "
                    f"last approved, which is past the bound")
        elif cumulative.get("measurable"):
            out += f". {cumulative['why']}"
        else:
            out += f". {cumulative['why']}"
        return out

    # ---------------------------------------------------------------- sweep
    def sweep(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every self-changing model, and whether it has wandered.

        The classes that change themselves are read from the fibres. A second
        list here would disagree with `L-15` the first time either moved, and
        the disagreement would be silent.
        """
        moment = now if now is not None else time.time()
        adaptive = self._adaptive_classes()
        rows = []
        for model in self.registry.list():
            for version in self.registry.versions(model["urn"]):
                if version.get("trainability_class") not in adaptive:
                    continue
                trail = self.trajectory(model["urn"], version["semver"])
                if trail["points"] < 2:
                    continue
                frequency = self._frequency(trail, moment)
                cumulative = trail["since_last_decision"]
                rows.append({
                    "urn": model["urn"], "semver": version["semver"],
                    "trainability_class": version["trainability_class"],
                    "tier": model.get("tier"), "owner": model.get("owner"),
                    "changes": len(trail["steps"]),
                    "changes_in_window": frequency["changes"],
                    "too_frequent": frequency["excursion"],
                    "cumulative": cumulative.get("magnitude"),
                    "measurable": cumulative.get("measurable", False),
                    "excursion": bool(cumulative.get("excursion")
                                      or frequency["excursion"]),
                })
        rows.sort(key=lambda r: (not r["excursion"], -(r["cumulative"] or 0.0)))
        excursions = [r for r in rows if r["excursion"]]
        opaque = [r for r in rows if not r["measurable"]]
        return {
            "models": rows, "count": len(rows),
            "excursions": len(excursions), "opaque": len(opaque),
            "step_bound": STEP_EXCURSION,
            "cumulative_bound": CUMULATIVE_EXCURSION,
            "changes_per_window": CHANGES_PER_WINDOW,
            "detail": (
                f"{len(rows)} adaptive version(s) with a trajectory, "
                f"{len(excursions)} past a bound"
                + (f"; {len(opaque)} keep their parameters outside the "
                   f"register, so this can say how OFTEN they change and not "
                   f"how far" if opaque else "")
                if rows else
                "no adaptive model on this estate has changed its parameters "
                "more than once, which is what a register with nothing "
                "self-changing in it looks like"),
        }

    def _adaptive_classes(self) -> set:
        """Which classes change themselves, from the fibres."""
        if self.fibres is None:
            return {"T4"}
        found = set()
        for trainability in self.fibres.classes():
            fibre = self.fibres.get(trainability)
            if fibre and "autonom" in (fibre.soundness or "").lower():
                found.add(trainability)
        return found or {"T4"}

    @staticmethod
    def _frequency(trail: Dict[str, Any], moment: float) -> Dict[str, Any]:
        """How often it has changed lately.

        A separate excursion from magnitude, because a model re-fitting faster
        than anybody can review it is a governance problem whatever the size of
        each move.
        """
        since = moment - WINDOW_DAYS * DAY
        recent = [s for s in trail["steps"] if (s.get("at") or 0) >= since]
        return {"changes": len(recent),
                "excursion": len(recent) > CHANGES_PER_WINDOW,
                "why": (f"{len(recent)} change(s) in {WINDOW_DAYS:.0f} days, "
                        f"against a bound of {CHANGES_PER_WINDOW}. A model "
                        f"re-fitting faster than anybody can review it is a "
                        f"governance problem whatever the size of each move")}
