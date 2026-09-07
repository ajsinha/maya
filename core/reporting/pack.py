"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The board pack.

What a committee asks is not *what is the number*. It is three questions in this
order: **are we inside the limits we set**, **what is outside them**, and **what
moved since we last met**. A pack that answers only the first is a dashboard, and
a dashboard is why nobody reads the pack.

So a pack is persisted. Movement needs a previous pack to move from, and a
committee minute referring to "the March pack" needs the March pack to still
exist as it was read — not as it would be recomputed today, which is a different
document with the same name.

**Slack is reported.** An appetite whose utilisation stays far below its limit,
pack after pack, is a limit doing no work — and a control that has never been
approached is indistinguishable from one that cannot fire. It is not a breach and
it is not an error; it is the thing a committee reviewing its own appetite should
be told and never is.

**No composite score.** Reported once, in the pack itself, so a reader who came
looking for one finds the reason instead of an absence.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.reporting.common import (AMBER, BREACH, BY_KEY, HIGHER_IS_BETTER,
                                   NO_APPETITE, SLACK_PACKS, SLACK_UTILISATION,
                                   STATUS_MEANING, WITHIN, ReportingError)
from core.reporting.indicators import IndicatorSet, within_scope
from db import BoardPackRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)

NO_COMPOSITE = (
    "This pack reports indicators and refuses to average them. A single "
    "model-risk figure requires the parts to compose, and they do not: two "
    "models fed by the same curve are not two independent risks, so any one "
    "number either double-counts the shared dependency or ignores it — and a "
    "committee cannot decompose it to find out which. The exceptions below are "
    "what to act on."
)


class BoardPackBuilder:
    """Assembles, compares and records the quarterly pack."""

    def __init__(self, repo: BoardPackRepository, indicators: IndicatorSet,
                 appetite, registry, evidence: EvidenceEngine):
        self.repo = repo
        self.indicators = indicators
        self.appetite = appetite
        self.registry = registry
        self.evidence = evidence

    # ------------------------------------------------------------------ build
    def build(self, *, period: str = "", scope: Optional[Dict[str, Any]] = None,
              models: Optional[Sequence[Dict[str, Any]]] = None,
              now: Optional[float] = None) -> Dict[str, Any]:
        """Compute a pack without recording it. `cut` is what records one."""
        moment = now if now is not None else time.time()
        scope = scope or {}
        estate = [m for m in (models if models is not None else self.registry.list())
                  if within_scope(m, scope)]
        computed = self.indicators.compute(estate, moment)

        limits = {self._key(a["metric"], a["scope"]): a
                  for a in self.appetite.in_force()}
        rows: List[Dict[str, Any]] = []
        for metric in BY_KEY.values():
            rows.append(self._row(metric, computed, limits, scope))

        previous = self.previous(scope)
        for row in rows:
            row["movement"] = self._movement(row, previous)
            row["slack"] = self._slack(row, scope)

        exceptions = [r for r in rows if r["status"] in (BREACH, AMBER)]
        unmeasured = computed["unmeasured"]
        return {
            "period": period, "scope": scope, "as_at": moment,
            "models": len(estate),
            "indicators": rows,
            "exceptions": exceptions,
            "unmeasured": unmeasured,
            "no_composite": NO_COMPOSITE,
            "previous": ({"id": previous["id"], "period": previous["period"],
                          "as_at": previous["as_at"]} if previous else None),
            "digest": canonical_digest(
                {"scope": scope,
                 "values": {r["metric"]: r["value"] for r in rows}}),
            "detail": self._headline(estate, exceptions, unmeasured),
        }

    def cut(self, *, period: str = "", scope: Optional[Dict[str, Any]] = None,
            note: str = "", actor: str = "system") -> Dict[str, Any]:
        """Record a pack. This is the one a committee refers to afterwards."""
        pack = self.build(period=period, scope=scope)
        row = {"period": period or time.strftime("%Y-Q%m", time.gmtime()),
               "scope": pack["scope"], "as_at": pack["as_at"],
               "models": pack["models"],
               "indicators": pack["indicators"],
               "exceptions": [e["metric"] for e in pack["exceptions"]],
               "unmeasured": pack["unmeasured"],
               "digest": pack["digest"], "note": note,
               "created_by": actor, "created_at": time.time()}
        with self.evidence.recording():
            self.repo.add(row)
            self.evidence.append(
                "board_pack_cut", "board_pack", row["id"],
                {"period": row["period"], "scope": pack["scope"],
                 "models": pack["models"],
                 "breaches": [e["metric"] for e in pack["exceptions"]
                              if e["status"] == BREACH],
                 "unmeasured": sorted(pack["unmeasured"]),
                 "digest": pack["digest"]}, actor=actor)
        logger.info("board pack %s: %d model(s), %d exception(s), %d unmeasured",
                    row["period"], pack["models"], len(pack["exceptions"]),
                    len(pack["unmeasured"]))
        return {**pack, "id": row["id"], "period": row["period"]}

    # ------------------------------------------------------------------- read
    def previous(self, scope: Optional[Dict[str, Any]] = None,
                 before: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """The last pack cut over the same scope."""
        key = self._scope_key(scope or {})
        earlier = [p for p in self.repo.many()
                   if self._scope_key(p["scope"] or {}) == key
                   and (before is None or p["as_at"] < before)]
        return max(earlier, key=lambda p: p["as_at"]) if earlier else None

    def history(self, scope: Optional[Dict[str, Any]] = None,
                limit: int = 12) -> List[Dict[str, Any]]:
        key = self._scope_key(scope or {})
        packs = [p for p in self.repo.many()
                 if self._scope_key(p["scope"] or {}) == key]
        return sorted(packs, key=lambda p: p["as_at"])[-limit:]

    def get(self, pack_id: str) -> Dict[str, Any]:
        row = self.repo.one(id=pack_id)
        if row is None:
            raise ReportingError(
                "no_board_pack", f"no board pack {pack_id}",
                "list the packs for this scope; a pack a minute refers to is "
                "kept as it was read, not recomputed")
        return row

    # ------------------------------------------------------------------ parts
    def _row(self, metric, computed: Dict[str, Any],
             limits: Dict[str, Dict[str, Any]],
             scope: Dict[str, Any]) -> Dict[str, Any]:
        value = computed["values"].get(metric.key)
        # The most specific declared limit wins: a Tier 1 limit beats the
        # estate-wide one for a Tier 1 pack. Same precedence as everywhere else
        # in the platform, rather than a fourth convention.
        appetite = (limits.get(self._key(metric.key, scope))
                    or limits.get(self._key(metric.key, {})))
        row: Dict[str, Any] = {
            "metric": metric.key, "means": metric.means,
            "matters": metric.matters,
            "direction": metric.direction, "unit": metric.unit,
            "value": value,
            "limit": None, "amber": None, "utilisation": None,
            "status": NO_APPETITE,
            "status_means": STATUS_MEANING[NO_APPETITE],
        }
        if value is None:
            row["status_means"] = (
                "not measured — " + computed["unmeasured"].get(metric.key, ""))
            return row
        if appetite is None:
            return row

        limit = appetite["limit_value"]
        amber = appetite["amber_value"]
        row.update({"limit": limit, "amber": amber,
                    "appetite_version": appetite["version"],
                    "rationale": appetite["rationale"],
                    "owner": appetite["owner"],
                    "review_at": appetite["review_at"],
                    "status": self._status(metric, value, limit, amber),
                    "utilisation": self._utilisation(metric, value, limit)})
        row["status_means"] = STATUS_MEANING[row["status"]]
        return row

    @staticmethod
    def _status(metric, value: float, limit: float,
                amber: Optional[float]) -> str:
        if metric.direction == HIGHER_IS_BETTER:
            if value < limit:
                return BREACH
            return AMBER if amber is not None and value < amber else WITHIN
        if value > limit:
            return BREACH
        return AMBER if amber is not None and value > amber else WITHIN

    @staticmethod
    def _utilisation(metric, value: float, limit: float) -> Optional[float]:
        """How much of the limit is used. Undefined where it would divide by zero.

        `None` rather than a sentinel: a limit of zero is a limit of zero, and a
        utilisation of infinity reported as a number is a number somebody plots.
        """
        if metric.direction == HIGHER_IS_BETTER:
            return None if not limit else round(value / limit, 4)
        return None if not limit else round(value / limit, 4)

    def _movement(self, row: Dict[str, Any],
                  previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """What this indicator did since the last pack over the same scope."""
        if previous is None:
            return {"since": None,
                    "detail": "no previous pack over this scope to move from"}
        was = next((i for i in (previous["indicators"] or [])
                    if i["metric"] == row["metric"]), None)
        if was is None or was.get("value") is None or row["value"] is None:
            return {"since": previous["as_at"],
                    "detail": "not comparable: one of the two packs did not "
                              "measure it"}
        change = round(row["value"] - was["value"], 4)
        improving = (change > 0 if row["direction"] == HIGHER_IS_BETTER
                     else change < 0)
        return {"since": previous["as_at"], "was": was["value"],
                "change": change,
                "improving": bool(change) and improving,
                "detail": ("unchanged" if not change else
                           f"{'improved' if improving else 'worsened'} by "
                           f"{abs(change):g}")}

    def _slack(self, row: Dict[str, Any],
               scope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Has this limit gone unapproached for long enough to be worth review?

        Not a breach and not an error. A limit never approached is a limit doing
        no work, and a control that has never fired is indistinguishable from one
        that cannot — which is exactly what a committee reviewing its own
        appetite needs to hear and never does.
        """
        if row["utilisation"] is None or row["utilisation"] >= SLACK_UTILISATION:
            return None
        recent = self.history(scope, limit=SLACK_PACKS)
        quiet = 0
        for pack in recent:
            was = next((i for i in (pack["indicators"] or [])
                        if i["metric"] == row["metric"]), None)
            if was and was.get("utilisation") is not None \
                    and was["utilisation"] < SLACK_UTILISATION:
                quiet += 1
        if quiet + 1 < SLACK_PACKS:
            return None
        return {"packs": quiet + 1, "utilisation": row["utilisation"],
                "detail": f"this limit has been under "
                          f"{int(SLACK_UTILISATION * 100)}% utilised for "
                          f"{quiet + 1} pack(s); a limit never approached is "
                          f"not constraining anything, and is worth reviewing "
                          f"as much as one that breached"}

    @staticmethod
    def _headline(estate, exceptions, unmeasured) -> str:
        breaches = [e for e in exceptions if e["status"] == BREACH]
        parts = [f"{len(estate)} model(s) in scope"]
        parts.append(f"{len(breaches)} breach(es)" if breaches
                     else "no limit breached")
        if exceptions and not breaches:
            parts.append(f"{len(exceptions)} at amber")
        if unmeasured:
            # Said out loud, because an unmeasured indicator reported as clean
            # is how a committee is told an estate is healthy when it is
            # unobserved.
            parts.append(f"{len(unmeasured)} indicator(s) NOT MEASURED")
        return "; ".join(parts)

    @staticmethod
    def _key(metric: str, scope: Dict[str, Any]) -> str:
        return f"{metric}|" + BoardPackBuilder._scope_key(scope)

    @staticmethod
    def _scope_key(scope: Dict[str, Any]) -> str:
        return "|".join(f"{k}={scope[k]}" for k in sorted(scope or {})) or "*"
