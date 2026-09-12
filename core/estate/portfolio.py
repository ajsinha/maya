"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The register cut by the dimensions somebody actually asks about.

SR 26-2 VI asks for an inventory sufficient to understand individual **and
aggregate** risk, and filters on a list only ever answer the first. *How many
models does credit own* is a question a list answers by making somebody count.

**A heatmap is a cross-tabulation with an opinion about what is bad, and the
opinion has to come from somewhere real.** A grid coloured by *count* tells you
where the models are, which nobody needed a grid to learn. What is worth seeing
is where the models are **and something is owed on them** — so every cell carries
its count and its **owed**, and the shading is the second. A cell with forty
healthy tier 4 models and a cell with one tier 1 model missing its validation are
not the same cell, and a count-coloured grid draws them identically.

**Trend is the one thing that cannot be faked from current state**, and it is the
one every register gets wrong: a snapshot table written nightly, which starts on
the day somebody remembered to add it and is wrong for every day before that.
MAYA already folds the evidence chain into the register as it stood at a moment
(`core/registry/asat.py`), so a trend here is a **series of those folds** — true
for every date the chain covers, back to the first act, and carrying the chain
hash that makes each point verifiable rather than asserted. Nothing new is
stored, and nothing can drift.

**The aggregate question is not how many.** SR 26-2 VI is about how much rides on
the models that are not right, so the headline is weighted by exposure where the
register knows it and says how much of the estate that covers — a weighted figure
over a third of the estate presented as *the* answer would be worse than the
count it replaced.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Sequence

DAY = 86400.0

#: The dimensions a portfolio is cut by, and where each is read from. Named as
#: data because the API, the screen and the heatmap all have to agree, and three
#: copies of a dimension list is how a filter silently stops matching a facet.
DIMENSIONS: Dict[str, str] = {
    "domain": "the business the model serves",
    "tier": "what rides on it being right",
    "status": "where its record stands in the lifecycle",
    "owner": "who answers for it",
    "legal_entity": "which entity it is used in",
    "model_class": "what kind of model it is",
    "trainability_class": "how its parameters were arrived at — derived from "
                          "the latest version, never declared",
}

#: How many points a trend returns by default. Twelve, because the question is
#: nearly always *over the last year* and a chart with three hundred points is
#: one nobody reads.
DEFAULT_POINTS = 12
DEFAULT_SPAN_DAYS = 365.0


class Portfolio:
    """Cuts the register by dimension, and folds the chain for the trend."""

    def __init__(self, registry, worklist=None, as_at=None, risk=None):
        self.registry, self.worklist = registry, worklist
        # The as-at projection, which is where the trend comes from. Optional:
        # without it the cuts still work and the trend says it cannot be
        # computed, rather than returning a flat line that looks like an answer.
        self.as_at, self.risk = as_at, risk

    # ------------------------------------------------------------------ cuts
    def by(self, dimension: str,
           models: Optional[Sequence[Dict[str, Any]]] = None,
           now: Optional[float] = None) -> Dict[str, Any]:
        """The register grouped by one dimension, with what is owed in each."""
        from core.estate.common import EstateError

        if dimension not in DIMENSIONS:
            raise EstateError(
                "unknown_dimension",
                f"'{dimension}' is not a dimension this register is cut by",
                "one of " + ", ".join(f"{k} ({v})"
                                      for k, v in DIMENSIONS.items()))
        moment = now if now is not None else time.time()
        rows = list(models if models is not None else self.registry.list())
        buckets: Dict[str, Dict[str, Any]] = {}
        # One index per table for the whole cut rather than nine round trips
        # per model. `_owed` and `_exposure` are unchanged — what changes is
        # where their reads come from. See `core/estate/worklist.py::FOLDED`.
        with self._folding():
            for model in rows:
                key = self._value(model, dimension)
                bucket = buckets.setdefault(key, {
                    "value": key, "models": 0, "owed": 0, "urns": [],
                    "exposure": 0.0, "exposure_known": 0})
                bucket["models"] += 1
                bucket["urns"].append(model.get("urn"))
                owed = self._owed(model, moment)
                bucket["owed"] += owed
                exposure = self._exposure(model)
                if exposure is not None:
                    bucket["exposure"] += exposure
                    bucket["exposure_known"] += 1

        cells = sorted(buckets.values(), key=lambda b: (-b["owed"], b["value"]))
        return {
            "dimension": dimension, "means": DIMENSIONS[dimension],
            "cells": cells, "models": len(rows),
            "owed": sum(c["owed"] for c in cells),
            "detail": self._cut_detail(dimension, cells, rows),
        }

    def _folding(self):
        """The database the cut's reads go through, if there is one.

        Taken from the risk repository because that is the collaborator the
        portfolio always has when it has any; a `Portfolio` built without one
        folds with nothing and still works, which is how the unit tests use it.
        """
        from core.estate.worklist import FOLDED, _NoFold
        db = getattr(self.risk, "db", None)
        if db is not None and hasattr(db, "folding"):
            return db.folding(FOLDED)
        return _NoFold.folding(FOLDED)

    def heatmap(self, rows: str = "domain", columns: str = "tier",
                now: Optional[float] = None) -> Dict[str, Any]:
        """A cross-tabulation, shaded by what is owed rather than by count.

        A grid coloured by count tells you where the models are, which nobody
        needed a grid to learn. What is worth seeing is where the models are
        *and* something is owed on them.
        """
        from core.estate.common import EstateError

        for name in (rows, columns):
            if name not in DIMENSIONS:
                raise EstateError(
                    "unknown_dimension",
                    f"'{name}' is not a dimension this register is cut by",
                    "one of " + ", ".join(DIMENSIONS))
        if rows == columns:
            raise EstateError(
                "same_dimension",
                f"a heatmap of {rows} against itself is a list with extra "
                f"steps",
                "choose two different dimensions")

        moment = now if now is not None else time.time()
        models = self.registry.list()
        grid: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for model in models:
            r, c = self._value(model, rows), self._value(model, columns)
            cell = grid.setdefault(r, {}).setdefault(
                c, {"models": 0, "owed": 0, "urns": []})
            cell["models"] += 1
            cell["owed"] += self._owed(model, moment)
            cell["urns"].append(model.get("urn"))

        worst = max((cell["owed"] for row in grid.values()
                     for cell in row.values()), default=0)
        return {
            "rows": rows, "columns": columns,
            "row_values": sorted(grid),
            "column_values": sorted({c for row in grid.values() for c in row}),
            "grid": grid, "worst_cell": worst, "models": len(models),
            "detail": (
                f"{len(models)} model(s) across {len(grid)} {rows} and "
                f"{len({c for row in grid.values() for c in row})} {columns}. "
                f"Shaded by what is OWED and not by count: a cell with forty "
                f"healthy models and a cell with one that is missing its "
                f"validation are not the same cell, and a count-coloured grid "
                f"draws them identically"),
        }

    # ----------------------------------------------------------------- trend
    def trend(self, points: int = DEFAULT_POINTS,
              span_days: float = DEFAULT_SPAN_DAYS,
              now: Optional[float] = None) -> Dict[str, Any]:
        """The register as it stood, at intervals, folded from the chain.

        The one thing that cannot be faked from current state — and the one
        every register gets wrong, by writing a nightly snapshot table that
        starts on the day somebody remembered to add it and is wrong for every
        day before that. This folds the evidence chain instead, so it is true
        for every date the chain covers and each point carries the chain hash
        that makes it verifiable rather than asserted.
        """
        moment = now if now is not None else time.time()
        if self.as_at is None:
            return {
                "points": [], "count": 0, "available": False,
                "detail": ("no as-at projection is wired into this instance, "
                           "so the trend cannot be computed. That is reported "
                           "rather than returned as a flat line, which would "
                           "look like an answer"),
            }
        step = span_days * DAY / max(1, points - 1)
        series = []
        for i in range(points):
            at = moment - (points - 1 - i) * step
            projection = self.as_at.register(at)
            by_status: Dict[str, int] = {}
            by_tier: Dict[str, int] = {}
            for model in projection["models"]:
                status = model.get("status") or "unknown"
                by_status[status] = by_status.get(status, 0) + 1
                tier = str(model.get("tier") or "untiered")
                by_tier[tier] = by_tier.get(tier, 0) + 1
            series.append({
                "at": at, "models": projection["count"],
                "by_status": by_status, "by_tier": by_tier,
                # The reason to fold the chain rather than keep a snapshot
                # table: a point somebody could have rewritten is not evidence.
                "chain_seq": projection["chain_seq"],
                "chain_hash": projection["chain_hash"],
            })
        first, last = series[0], series[-1]
        return {
            "points": series, "count": len(series), "available": True,
            "span_days": span_days,
            "grew_by": last["models"] - first["models"],
            "detail": (
                f"{len(series)} point(s) over {span_days:.0f} days, each one a "
                f"fold of the evidence chain rather than a stored snapshot — so "
                f"it is true for every date the chain covers, back to the first "
                f"act, and each point carries the chain hash that makes it "
                f"verifiable. The estate went from {first['models']} to "
                f"{last['models']} model(s)"),
        }

    # -------------------------------------------------------------- headline
    def aggregate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """How much rides on the models that are not right.

        SR 26-2 VI is about aggregate risk, and the aggregate question is not
        *how many*. Weighted by exposure where the register knows it — and
        saying how much of the estate that covers, because a weighted figure
        over a third of the estate presented as *the* answer would be worse
        than the count it replaced.
        """
        moment = now if now is not None else time.time()
        models = self.registry.list()
        owing = [m for m in models if self._owed(m, moment)]
        known = [m for m in models if self._exposure(m) is not None]
        exposure_owing = sum(self._exposure(m) or 0.0 for m in owing
                             if self._exposure(m) is not None)
        exposure_all = sum(self._exposure(m) or 0.0 for m in known)
        coverage = len(known) / len(models) if models else 0.0
        return {
            "models": len(models), "with_something_owed": len(owing),
            "exposure_known_for": len(known),
            "exposure_coverage": round(coverage, 4),
            "exposure_total": exposure_all,
            "exposure_with_something_owed": exposure_owing,
            "share_of_exposure_owing": (
                round(exposure_owing / exposure_all, 4) if exposure_all else None),
            "detail": self._aggregate_detail(models, owing, known, coverage,
                                             exposure_all, exposure_owing),
        }

    @staticmethod
    def _aggregate_detail(models, owing, known, coverage, total, owing_amount):
        if not models:
            return "the register is empty"
        head = (f"{len(owing)} of {len(models)} model(s) have something "
                f"outstanding")
        if not known:
            return (head + ". No model on this estate records an exposure, so "
                    "the aggregate question SR 26-2 VI asks — how much rides "
                    "on the ones that are not right — has no answer here yet")
        share = owing_amount / total if total else 0.0
        return (f"{head}, carrying {share:.0%} of the exposure the register "
                f"knows about. That figure covers {coverage:.0%} of the "
                f"estate: exposure is recorded for {len(known)} of "
                f"{len(models)} models, and a weighted answer over a third of "
                f"an estate presented as THE answer would be worse than the "
                f"count it replaced")

    # --------------------------------------------------------------- shaping
    def _owed(self, model: Dict[str, Any], now: float) -> int:
        """How many things this model owes. The number the shading encodes.

        Zero is the answer for a model in good order, and it is why a heatmap
        shaded by this says something a count cannot.
        """
        if self.worklist is None:
            return 0
        try:
            return len(self.worklist.for_model(model, now=now))
        except Exception:
            # A worklist source that raises must not take the whole portfolio
            # view with it: a governance dashboard that goes blank when one
            # model is malformed is a dashboard nobody trusts.
            from core.log import get_logger
            get_logger(__name__).warning(
                "could not compute what %s owes; it counts as nothing owed in "
                "this view, which understates rather than overstates",
                model.get("urn"), exc_info=True)
            return 0

    def _exposure(self, model: Dict[str, Any]) -> Optional[float]:
        """What this model decides on, if the register was told.

        `None` rather than zero when nobody said, because a model with no
        recorded exposure and a model with none are different facts and only
        one of them should shrink a weighted average.
        """
        if self.risk is None:
            return None
        rows = self.risk.many(model_id=model["id"])
        if not rows:
            return None
        latest = max(rows, key=lambda r: r.get("assessed_at") or 0)
        # From `facts`, where the assessment recorded what it was told, rather
        # than from a column of its own. The assessment's facts ARE the record
        # of what the tier was decided on, and a second copy would be a second
        # number that could disagree with the one the tier came from.
        value = (latest.get("facts") or {}).get("exposure")
        return float(value) if value is not None else None

    def _value(self, model: Dict[str, Any], dimension: str) -> str:
        if dimension == "tier":
            return str(model.get("tier") or "untiered")
        if dimension == "trainability_class":
            versions = self.registry.versions(model["urn"])
            return (versions[-1].get("trainability_class") if versions
                    else "no version")
        return str(model.get(dimension) or "unstated")

    @staticmethod
    def _cut_detail(dimension, cells, rows) -> str:
        if not rows:
            return "the register is empty"
        worst = cells[0]
        if not worst["owed"]:
            return (f"{len(rows)} model(s) across {len(cells)} {dimension}(s), "
                    f"and nothing is outstanding anywhere")
        return (f"{len(rows)} model(s) across {len(cells)} {dimension}(s). "
                f"'{worst['value']}' carries the most outstanding work — "
                f"{worst['owed']} item(s) across {worst['models']} model(s) — "
                f"which is the ordering, because a cut sorted alphabetically "
                f"buries whatever needs doing")
