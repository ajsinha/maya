"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Risk appetite: the limits a committee set, held where they can be checked.

An appetite statement in most banks is a sentence in a document. That is not a
control — nobody can compute against a sentence, so the number in the quarterly
pack is prepared by hand, and whether it is inside the limit is somebody's
judgement rather than an evaluation.

Here a limit is a **declared threshold over a metric the platform computes**, so
utilisation is arithmetic and a breach is a fact. Three consequences follow, and
each is a refusal rather than a convention:

  * A metric the platform cannot compute is refused **when the limit is
    written**. A limit that failed at the moment a committee was reading it
    would fail at the worst possible time, and its author is long gone by then.
  * A limit with no **rationale** is refused. A number nobody can explain is a
    number nobody will ever change, so it will be either ignored or obeyed
    without thought, and both are worse than not having it.
  * An **amber** threshold on the far side of the limit is refused. A warning
    that can only fire after the thing it warns about has happened is not a
    warning.

Versions accumulate; nothing is edited. A limit that can be changed without a
record is a limit that can be **relaxed** without one, and the relaxation is
exactly the event a reader six months later needs to find.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.reporting.common import (BY_KEY, HIGHER_IS_BETTER, LOWER_IS_BETTER,
                                   MAX_RATIONALE, METRICS, SCOPES,
                                   ReportingError)
from db import RiskAppetiteRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)


class AppetiteRegister:
    """Declared limits, versioned, with the reason each was set."""

    def __init__(self, repo: RiskAppetiteRepository, evidence: EvidenceEngine):
        self.repo, self.evidence = repo, evidence

    # ---------------------------------------------------------------- declare
    def declare(self, *, metric: str, limit: float, rationale: str,
                amber: Optional[float] = None,
                scope: Optional[Dict[str, Any]] = None,
                owner: str = "", review_at: Optional[float] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Set or replace a limit. The previous version stays in the register."""
        definition = self._metric(metric)
        scope = self._scope(scope or {})
        rationale = (rationale or "").strip()
        if not rationale:
            raise ReportingError(
                "rationale_required",
                f"the limit on '{metric}' carries no rationale",
                "say what the number is FOR. A limit nobody can explain is one "
                "nobody will change, so it gets ignored or obeyed without "
                "thought, and both are worse than not having it")
        if len(rationale) > MAX_RATIONALE:
            raise ReportingError(
                "rationale_too_long",
                f"the rationale is {len(rationale)} characters, over "
                f"{MAX_RATIONALE}",
                "a rationale a committee will not read is not a rationale; "
                "attach the paper and summarise it here")
        self._check_amber(definition, limit, amber)

        key = self._key(metric, scope)
        row = {"metric": metric, "scope_key": key, "scope": scope,
               "version": self.repo.next_version(metric, key),
               "limit_value": float(limit),
               "amber_value": None if amber is None else float(amber),
               "direction": definition.direction,
               "unit": definition.unit,
               "rationale": rationale, "owner": owner,
               "review_at": review_at, "retired": 0,
               "digest": canonical_digest({"metric": metric, "scope": scope,
                                           "limit": limit, "amber": amber}),
               "created_by": actor, "created_at": time.time()}
        self.repo.add(row)

        prior = self._prior(metric, key, row["version"])
        self.evidence.append(
            "risk_appetite_declared", "risk_appetite", row["id"],
            {"metric": metric, "scope": scope, "version": row["version"],
             "limit": row["limit_value"], "amber": row["amber_value"],
             # Whether this loosened the limit is computed rather than left to
             # a reader to work out from two numbers in two rows. A relaxation
             # is the event somebody looks for later, so it is named here.
             "relaxed": self._relaxes(definition, prior, row),
             "rationale": rationale}, actor=actor)
        logger.info("risk appetite %s%s v%s: %s %s %s", metric,
                    f" {scope}" if scope else "", row["version"],
                    definition.direction, "limit", row["limit_value"])
        return row

    def retire(self, metric: str, *, scope: Optional[Dict[str, Any]] = None,
               reason: str = "", actor: str = "system") -> Dict[str, Any]:
        """Stop holding the estate to a limit. The versions stay."""
        current = self.current(metric, scope)
        if current is None:
            raise ReportingError(
                "no_appetite", f"no limit is declared for '{metric}'",
                "declare one, or ask for the indicator without an appetite — it "
                "is still measured, it is simply not held to anything")
        self.repo.set({"retired": 1, "retired_at": time.time(),
                       "retired_by": actor}, id=current["id"])
        self.evidence.append("risk_appetite_retired", "risk_appetite",
                             current["id"],
                             {"metric": metric, "reason": reason}, actor=actor)
        return self.repo.one(id=current["id"])

    # ------------------------------------------------------------------- read
    def current(self, metric: str,
                scope: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        key = self._key(metric, self._scope(scope or {}))
        live = [r for r in self.repo.many(metric=metric, scope_key=key)
                if not r["retired"]]
        return max(live, key=lambda r: r["version"]) if live else None

    def in_force(self) -> List[Dict[str, Any]]:
        """Every live limit, most specific scope last.

        Ordered so a caller folding them applies the general before the
        particular — the same left-to-right rule featuresets and warrant
        profiles use, rather than a third convention.
        """
        live: Dict[str, Dict[str, Any]] = {}
        for row in self.repo.many():
            if row["retired"]:
                continue
            key = f"{row['metric']}|{row['scope_key']}"
            held = live.get(key)
            if held is None or row["version"] > held["version"]:
                live[key] = row
        return sorted(live.values(),
                      key=lambda r: (len(r["scope"] or {}), r["metric"]))

    def history(self, metric: str,
                scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        key = self._key(metric, self._scope(scope or {}))
        return sorted(self.repo.many(metric=metric, scope_key=key),
                      key=lambda r: r["version"])

    @staticmethod
    def vocabulary() -> Dict[str, Any]:
        """What may be held to a limit, and what each indicator is for."""
        return {"metrics": [{"key": m.key, "means": m.means,
                             "direction": m.direction, "unit": m.unit,
                             "matters": m.matters} for m in METRICS],
                "scopes": list(SCOPES),
                "detail": "direction belongs to the metric, not to whoever sets "
                          "the limit: whether more is worse is a property of the "
                          "thing being counted"}

    # ------------------------------------------------------------------ parts
    @staticmethod
    def _metric(metric: str):
        if metric not in BY_KEY:
            raise ReportingError(
                "unknown_metric",
                f"'{metric}' is not a metric this platform computes",
                "hold a limit against something the register can evaluate — "
                + ", ".join(sorted(BY_KEY))
                + ". A limit over a number nobody computes fails at the moment a "
                  "committee is reading it, which is the worst possible time")
        return BY_KEY[metric]

    @staticmethod
    def _scope(scope: Dict[str, Any]) -> Dict[str, Any]:
        for dimension in scope:
            if dimension not in SCOPES:
                raise ReportingError(
                    "unknown_scope",
                    f"'{dimension}' is not a dimension a limit may be scoped to",
                    f"use one of {', '.join(SCOPES)}; a scope the platform "
                    f"cannot filter on is a limit that silently applies to "
                    f"everything")
        return {k: scope[k] for k in sorted(scope)}

    @staticmethod
    def _check_amber(definition, limit: float, amber: Optional[float]) -> None:
        if amber is None:
            return
        wrong = (definition.direction == LOWER_IS_BETTER and amber >= limit) or \
                (definition.direction == HIGHER_IS_BETTER and amber <= limit)
        if wrong:
            side = "below" if definition.direction == LOWER_IS_BETTER else "above"
            raise ReportingError(
                "amber_beyond_limit",
                f"the amber threshold {amber} is on the far side of the limit "
                f"{limit} for a '{definition.direction}' metric",
                f"put amber {side} the limit; a warning that can only fire "
                f"after the thing it warns about has happened is not a warning")

    @staticmethod
    def _key(metric: str, scope: Dict[str, Any]) -> str:
        """One string identifying a metric-and-scope, so versions accumulate per
        scope rather than a tier-1 limit superseding the estate-wide one."""
        return "|".join(f"{k}={scope[k]}" for k in sorted(scope)) or "*"

    def _prior(self, metric: str, key: str,
               version: int) -> Optional[Dict[str, Any]]:
        earlier = [r for r in self.repo.many(metric=metric, scope_key=key)
                   if r["version"] < version]
        return max(earlier, key=lambda r: r["version"]) if earlier else None

    @staticmethod
    def _relaxes(definition, prior: Optional[Dict[str, Any]],
                 row: Dict[str, Any]) -> bool:
        """Did this version make the limit easier to satisfy?

        Allowed, and never quiet — the same posture the policy register takes
        toward a weakened gate. A committee raising a limit because the estate
        grew is doing something reasonable; a committee raising it because the
        estate breached it is doing something else, and only the record can tell
        the two apart.
        """
        if prior is None:
            return False
        if definition.direction == LOWER_IS_BETTER:
            return row["limit_value"] > prior["limit_value"]
        return row["limit_value"] < prior["limit_value"]
