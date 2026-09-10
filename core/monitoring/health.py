"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

One number for a model, and the six that made it.

Every model risk function is eventually asked for a health score, and every
health score is eventually mistrusted, for two reasons that are worth naming
before writing one.

**The first is that a mean dilutes.** A model with an excellent AUC, no drift
and a validation that expired eighteen months ago averages to a comfortable
number, and the comfortable number is what goes on the slide. So the judgement
here is not the arithmetic. The score is a weighted mean over what could be
measured; the **band** is that mean *capped* by conditions that no amount of
good news anywhere else may outweigh — an expired validation, an overdue
Critical finding, an unmeasured overlay carrying the model's answer. The number
and the verdict are reported separately and the verdict wins. When they
disagree, the disagreement is the finding.

**The second is that an unmeasured component scores as a good one.** A model
with no monitors, no validation and no findings has nothing bad to say about
it, and a naive composite reads that as health. Absent components are therefore
excluded from the denominator and named, and `coverage` — the share of the
weight that was actually measurable — travels with the score everywhere it
goes. A score of 92 at 30% coverage is not a healthy model; it is a model
nobody has looked at, and the two must not print the same.

Nothing here is stored. Every component is read from a register that already
holds it, so the score cannot drift away from its own inputs: a health score
that is written down is a health score that is stale, and staleness is exactly
the condition it exists to detect.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0

GOOD, WATCH, POOR = "good", "watch", "poor"
BANDS: Tuple[str, ...] = (GOOD, WATCH, POOR)
_RANK = {GOOD: 0, WATCH: 1, POOR: 2}

# Where the mean falls into a band, when nothing caps it.
GOOD_AT = 0.80
WATCH_AT = 0.55

# What goes into the score, what it weighs, and what it is asking. Held as data
# so the derivation can be rendered rather than described: a composite whose
# weights live in a conditional is a composite nobody can check.
COMPONENTS: Tuple[Dict[str, Any], ...] = (
    {"key": "performance", "weight": 0.25,
     "asks": "do the label-dependent monitors on this model pass",
     "absent_when": "no performance or calibration monitor has an observation "
                    "yet — which for a model whose outcomes take a year is the "
                    "ordinary state for a year"},
    {"key": "drift", "weight": 0.15,
     "asks": "do the input and score drift monitors pass",
     "absent_when": "no drift monitor has been evaluated, which is a different "
                    "fact from a drift monitor passing"},
    {"key": "data_quality", "weight": 0.15,
     "asks": "are the feeds under this model behaving like themselves",
     "absent_when": "no view under this model has enough history to be judged "
                    "against its own past"},
    {"key": "overlay_reliance", "weight": 0.15,
     "asks": "how much of this model's answer is the model, and how much is us",
     "absent_when": "this model carries no overlay, which scores full marks "
                    "rather than absent: nothing is being adjusted"},
    {"key": "validation_currency", "weight": 0.20,
     "asks": "is the validation that stands behind this model still standing",
     "absent_when": "this model's tier carries no elapsed-time trigger at all, "
                    "so there is no window for a validation to fall outside"},
    {"key": "open_findings", "weight": 0.10,
     "asks": "what is open against this model, and how late is it",
     "absent_when": "never — a model with no findings has none open, which is "
                    "a measurement and not a gap"},
)
WEIGHTS: Dict[str, float] = {c["key"]: float(c["weight"]) for c in COMPONENTS}


class ModelHealth:
    """Derives one model's health from six registers that already hold it."""

    def __init__(self, registry, monitoring=None, findings=None, overlays=None,
                 plans=None, pipeline_health=None, catalogue=None):
        self.registry = registry
        # All optional, and each absence shows up as a named absence in the
        # answer rather than as a component quietly scoring well.
        self.monitoring, self.findings, self.overlays = monitoring, findings, overlays
        self.plans, self.pipeline_health = plans, pipeline_health
        self.catalogue = catalogue

    # ------------------------------------------------------------------ score
    def of_model(self, urn: str, now: Optional[float] = None) -> Dict[str, Any]:
        """The score, the band, the six components and the caps."""
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        parts = [self._performance(model, moment), self._drift(model),
                 self._data_quality(model), self._overlays(model, moment),
                 self._validation(model, moment), self._findings(model, moment)]

        measured = [p for p in parts if p["measured"]]
        weight = sum(p["weight"] for p in measured)
        score = (sum(p["score"] * p["weight"] for p in measured) / weight
                 if weight else None)
        coverage = weight / sum(WEIGHTS.values())

        caps = [c for p in parts for c in p.get("caps", [])]
        arithmetic = self._band(score)
        band = self._worst([arithmetic] + [c["band"] for c in caps]) \
            if arithmetic else None

        return {
            "urn": urn, "tier": model.get("tier"),
            "score": round(score * 100, 1) if score is not None else None,
            "band": band, "arithmetic_band": arithmetic,
            "coverage": round(coverage, 3),
            "derivable": score is not None,
            "components": parts,
            "measured": [p["component"] for p in measured],
            "not_measured": [p["component"] for p in parts if not p["measured"]],
            "caps": caps,
            "detail": self._detail(score, band, arithmetic, coverage, caps, parts),
        }

    @staticmethod
    def _band(score: Optional[float]) -> Optional[str]:
        if score is None:
            return None
        return GOOD if score >= GOOD_AT else WATCH if score >= WATCH_AT else POOR

    @staticmethod
    def _worst(bands: Sequence[Optional[str]]) -> Optional[str]:
        present = [b for b in bands if b]
        return max(present, key=lambda b: _RANK[b]) if present else None

    @staticmethod
    def _detail(score, band, arithmetic, coverage, caps, parts) -> str:
        if score is None:
            return ("nothing about this model is measurable yet: no monitor has "
                    "been evaluated, no feed judged, no validation concluded. "
                    "That is a score of nothing, not a score of zero, and "
                    "printing a number here would be inventing one")
        out = (f"{score * 100:.0f} over {len([p for p in parts if p['measured']])} "
               f"of {len(parts)} components, which is {coverage:.0%} of the weight")
        if caps:
            out += (f". The band is {band} rather than {arithmetic} because "
                    + "; ".join(c["why"] for c in caps)
                    + " — and no amount of good news elsewhere outweighs that")
        else:
            out += f", and nothing caps it, so the band is {band}"
        if coverage < 0.5:
            out += (". Under half the weight was measurable, so this number "
                    "says more about how little is known than about the model")
        return out

    # ------------------------------------------------------------- components
    def _observations(self, model: Dict[str, Any],
                      kinds: Sequence[str]) -> List[Dict[str, Any]]:
        """The latest observation of every active monitor of these kinds."""
        if self.monitoring is None:
            return []
        out = []
        for monitor in self.monitoring.registry.for_model(model["id"]):
            if monitor["kind"] not in kinds or monitor["status"] != "active":
                continue
            history = self.monitoring.history(monitor["id"])
            if history:
                out.append({"monitor": monitor, "observation": history[-1]})
        return out

    def _from_monitors(self, model, kinds, key, absent) -> Dict[str, Any]:
        latest = self._observations(model, kinds)
        if not latest:
            return self._absent(key, absent)
        passing = sum(1 for row in latest if row["observation"]["passed"])
        stale = [row for row in latest if row["observation"].get("source") == "external"]
        return self._measured(
            key, passing / len(latest),
            f"{passing} of {len(latest)} monitor(s) passing"
            + (f", {len(stale)} of them on a number MAYA did not compute"
               if stale else ""),
            evidence=[{"monitor": r["monitor"]["name"],
                       "test": r["monitor"]["test_key"],
                       "value": r["observation"]["value"],
                       "passed": r["observation"]["passed"],
                       "source": r["observation"].get("source", "maya")}
                      for r in latest])

    def _performance(self, model: Dict[str, Any], now: float) -> Dict[str, Any]:
        return self._from_monitors(model, ("performance", "calibration"),
                                   "performance", _absent_text("performance"))

    def _drift(self, model: Dict[str, Any]) -> Dict[str, Any]:
        return self._from_monitors(model, ("input_drift", "score_drift"),
                                   "drift", _absent_text("drift"))

    def _data_quality(self, model: Dict[str, Any]) -> Dict[str, Any]:
        if self.pipeline_health is None or self.pipeline_health.models_using is None:
            return self._absent("data_quality", _absent_text("data_quality"))
        views = self._views_under(model)
        judged = [self.pipeline_health.for_view(v) for v in views]
        judged = [j for j in judged if j.get("judged")]
        if not judged:
            return self._absent("data_quality", _absent_text("data_quality"))
        healthy = sum(1 for j in judged if j["healthy"])
        return self._measured(
            "data_quality", healthy / len(judged),
            f"{healthy} of {len(judged)} feed(s) behaving like themselves",
            evidence=[{"view": j["view"], "healthy": j["healthy"],
                       "problems": len(j.get("problems") or [])} for j in judged])

    def _views_under(self, model: Dict[str, Any]) -> List[str]:
        """Which materialised views this model reads. Best effort, and it says so."""
        using = self.pipeline_health.models_using
        try:
            return sorted({v for v, models in using().items()
                           if model["urn"] in models})
        except Exception:                       # pragma: no cover - shape varies
            logger.debug("models_using did not yield a view map for %s",
                         model["urn"])
            return []

    def _overlays(self, model: Dict[str, Any], now: float) -> Dict[str, Any]:
        if self.overlays is None:
            return self._absent("overlay_reliance", _absent_text("overlay_reliance"))
        status = self.overlays.status(model["id"], now)
        active = status.get("active", 0)
        if not active:
            # Not absent. A model carrying no overlay is a measured fact and a
            # good one: nothing is being adjusted, so nothing is being relied on.
            return self._measured("overlay_reliance", 1.0,
                                  "no active overlay: none of this model's "
                                  "answer is an adjustment")
        persistent = status.get("persistent", 0)
        unmeasured = status.get("unmeasured", 0)
        expired = status.get("expired_but_open", 0)
        bad = min(active, persistent + unmeasured + expired)
        caps = []
        if unmeasured:
            caps.append({"band": WATCH, "component": "overlay_reliance",
                         "why": (f"{unmeasured} active overlay(s) have never "
                                 f"been measured, so the size of the adjustment "
                                 f"standing between this model and its answer "
                                 f"is not known")})
        return self._measured(
            "overlay_reliance", 1.0 - (bad / active),
            f"{active} active overlay(s), {persistent} past their renewal "
            f"limit, {unmeasured} never measured, {expired} expired but open",
            evidence=[{"aggregate_magnitude": status.get("aggregate_magnitude")}],
            caps=caps)

    def _validation(self, model: Dict[str, Any], now: float) -> Dict[str, Any]:
        if self.plans is None:
            return self._absent("validation_currency", _absent_text("validation_currency"))
        due = self.plans.due(model["urn"], now)
        elapsed = next((t for t in due["triggers"] if t["trigger"] == "elapsed"), None)
        if elapsed is None or "window_days" not in elapsed:
            if elapsed is not None and elapsed.get("fired"):
                # Never validated. That is not an absence of a window; it is a
                # model standing on nothing.
                return self._measured(
                    "validation_currency", 0.0,
                    "this model has never been validated",
                    caps=[{"band": POOR, "component": "validation_currency",
                           "why": "this model has never been validated"}])
            return self._absent("validation_currency",
                                _absent_text("validation_currency"))
        age, window = elapsed["observed_days"], elapsed["window_days"]
        fraction = max(0.0, 1.0 - (age / window))
        caps = []
        if elapsed["fired"]:
            caps.append({"band": POOR, "component": "validation_currency",
                         "why": (f"the validation behind this model is "
                                 f"{age:.0f} days old against a {window:.0f}-day "
                                 f"window and has lapsed")})
        return self._measured(
            "validation_currency", fraction,
            f"validated {age:.0f} days ago against a {window:.0f}-day window",
            evidence=[{"trigger": t["trigger"], "fired": t.get("fired")}
                      for t in due["triggers"]],
            caps=caps)

    def _findings(self, model: Dict[str, Any], now: float) -> Dict[str, Any]:
        if self.findings is None:
            return self._absent("open_findings", _absent_text("open_findings"))
        summary = self.findings.summary(model["id"], now)
        overdue = self.findings.overdue(model["id"], now)
        by_severity = summary.get("by_severity") or {}
        # Weighted by severity, because five Observations and one Critical are
        # not the same estate and must not divide to the same number.
        penalty = (by_severity.get("Critical", 0) * 1.0
                   + by_severity.get("High", 0) * 0.5
                   + by_severity.get("Medium", 0) * 0.2
                   + by_severity.get("Low", 0) * 0.05)
        caps = []
        severe_overdue = [f for f in overdue if f["severity"] in ("Critical", "High")]
        if severe_overdue:
            caps.append({"band": POOR, "component": "open_findings",
                         "why": (f"{len(severe_overdue)} Critical or High "
                                 f"finding(s) are past their remediation date")})
        elif summary.get("blocking"):
            caps.append({"band": WATCH, "component": "open_findings",
                         "why": f"{summary['blocking']} open finding(s) block "
                                f"this model's progression"})
        return self._measured(
            "open_findings", max(0.0, 1.0 - min(1.0, penalty)),
            f"{summary['open']} open, {summary['overdue']} overdue"
            + (f", worst {summary['worst_severity']}"
               if summary.get("worst_severity") else ""),
            evidence=[{"severity": s, "count": n} for s, n in by_severity.items()],
            caps=caps)

    # ------------------------------------------------------------- assembling
    @staticmethod
    def _spec(key: str) -> Dict[str, Any]:
        return next(c for c in COMPONENTS if c["key"] == key)

    def _measured(self, key: str, score: float, detail: str,
                  evidence: Optional[List[Dict[str, Any]]] = None,
                  caps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        spec = self._spec(key)
        return {"component": key, "measured": True,
                "score": round(max(0.0, min(1.0, score)), 4),
                "weight": spec["weight"], "asks": spec["asks"],
                "detail": detail, "evidence": evidence or [],
                "caps": caps or []}

    def _absent(self, key: str, why: str) -> Dict[str, Any]:
        spec = self._spec(key)
        return {"component": key, "measured": False, "score": None,
                "weight": spec["weight"], "asks": spec["asks"],
                "detail": why, "absent_when": spec["absent_when"],
                "evidence": [], "caps": []}

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, urns: Optional[Sequence[str]] = None,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """Every model's health, worst first, with coverage beside the score."""
        subjects = list(urns) if urns is not None else \
            [m["urn"] for m in self.registry.list()]
        rows = [self.of_model(urn, now) for urn in subjects]
        rows.sort(key=lambda r: (-_RANK.get(r["band"] or GOOD, 0),
                                 float(r["score"] if r["score"] is not None else 101.0)))
        by_band: Dict[str, int] = {}
        for row in rows:
            key = row["band"] or "not_derivable"
            by_band[key] = by_band.get(key, 0) + 1
        thin = [r["urn"] for r in rows if r["coverage"] < 0.5]
        capped = [r["urn"] for r in rows if r["caps"]]
        return {
            "models": rows, "count": len(rows), "by_band": by_band,
            "thin_coverage": thin, "capped": capped,
            "detail": (
                f"{len(rows)} model(s): "
                + ", ".join(f"{n} {band}" for band, n in sorted(by_band.items()))
                + (f". {len(capped)} carry a band worse than their arithmetic, "
                   f"which is the point of the caps"
                   if capped else "")
                + (f". {len(thin)} scored on under half the weight and are "
                   f"reporting how little is known about them rather than how "
                   f"well they are doing" if thin else "")),
        }


def _absent_text(key: str) -> str:
    return next(c["absent_when"] for c in COMPONENTS if c["key"] == key)
