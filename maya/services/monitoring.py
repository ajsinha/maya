"""
Ongoing monitoring: what the reported executions of a live model say over time.

Every attested run already reports its row count and per-attribute statistics, and the
covenants are evaluated on each report as it arrives (§29.5). What nothing did was look at
them *together*: a null rate creeping up across fifty runs breaches no covenant until the
fifty-first, and a population stability index of 0.2 is not a breach at all, only the thing
a monitoring function wants to see before it becomes one.

So this module reads the reports as series. Per warrant: volume per day, each input's and
output's null rate, mean and range per run with the covenant's bounds beside them, the PSI
against the baseline the covenant was drawn with, and the breaches on the same time axis.
Across warrants: a health grade --

* ``breach``: suspended, or a covenant breached in the last seven days;
* ``watch``: a PSI in the conventional 0.10 to 0.25 band, or an input's latest null rate at
  least double its median, or a live warrant that has reported nothing for thirty days --
  silence from a model that is supposed to be running is itself a finding;
* ``ok``: none of those.

Nothing here writes. It is a reading of evidence already held, which is why it cannot drift
from what the covenants decided.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import datetime as dt
import statistics
from typing import Any

from maya.core.clock import utcnow
from maya.security.authz import Principal
from maya.services import refs
from maya.services.execution import PSI_DEFAULT_MAX, psi

PSI_WATCH = 0.10
QUIET_DAYS = 30
RECENT_BREACH_DAYS = 7
MAX_REPORTS = 2000


def _bounds(covenants: builtins.list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """What each attribute is held to, keyed by attribute, for drawing beside its series."""
    out: dict[str, dict[str, Any]] = {}
    for c in covenants:
        attr = c.get("attr")
        if not attr:
            continue
        b = out.setdefault(attr, {})
        kind = c.get("kind")
        if kind == "input_null_rate":
            b["null_max"] = c.get("max")
        elif kind in ("input_range", "output_range"):
            b["lo"], b["hi"] = c.get("min"), c.get("max")
        elif kind == "input_psi":
            base = c.get("baseline") or {}
            b["psi_max"] = float(c.get("max", PSI_DEFAULT_MAX))
            b["psi_baseline"] = base.get("counts") if isinstance(base, dict) else base
    return out


def _point(stats: dict[str, Any], bound: dict[str, Any]) -> dict[str, Any]:
    point = {k: stats.get(k) for k in ("null_rate", "mean", "min", "max")}
    hist, base = stats.get("histogram"), bound.get("psi_baseline")
    point["psi"] = None
    if hist and base and len(hist) == len(base):
        point["psi"] = round(psi(hist, base), 4)
    return point


class MonitoringService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def _model_ref(self, uow: Any, ew: dict[str, Any]) -> str | None:
        mv = uow.repo("model_versions").get(ew["model_version_id"])
        model = uow.repo("models").get(mv["model_id"]) if mv else None
        if not model:
            return None
        ns = uow.repo("namespaces").get(model["namespace_id"])
        return refs.version_ref("model", ns["name"], model["name"], mv["version_no"])

    def warrant(self, p: Principal, ew_id: str, days: int = 90) -> dict[str, Any]:
        """One warrant's reports read as series over the last ``days``."""
        days = max(1, min(int(days), 3650))
        since = utcnow() - dt.timedelta(days=days)
        with self.p.uow() as uow:
            ew, ns = self.p.execution._load(uow, ew_id)
            self.p.access.require(uow, p, "read", "execution_warrant", ew)
            reports = uow.repo("execution_reports").list(
                execution_warrant_id=ew_id,
                created_at__ge=since,
                order_by=["created_at"],
                limit=MAX_REPORTS,
            )
            model_ref = self._model_ref(uow, ew)
        bounds = _bounds(ew["spec"].get("covenants") or [])
        inputs: dict[str, builtins.list[dict[str, Any]]] = {}
        outputs: dict[str, builtins.list[dict[str, Any]]] = {}
        breaches: builtins.list[dict[str, Any]] = []
        daily: dict[dt.date, dict[str, Any]] = {}
        for r in reports:
            at = r["created_at"]
            for side, stats in ((inputs, r["input_stats"]), (outputs, r["output_stats"])):
                for attr, s in (stats or {}).items():
                    if isinstance(s, dict):
                        side.setdefault(attr, []).append(
                            {"at": at, **_point(s, bounds.get(attr, {}))}
                        )
            for b in r["breaches"] or []:
                breaches.append({"at": at, "kind": b.get("kind"), "detail": b.get("detail")})
            day = daily.setdefault(at.date(), {"date": at.date(), "runs": 0, "rows": 0})
            day["runs"] += 1
            day["rows"] += int(r["rows"] or 0)
        series = {"inputs": inputs, "outputs": outputs}
        return {
            "id": ew_id,
            "name": ew["name"],
            "version_no": ew["version_no"],
            "namespace": ns["name"],
            "uri": self.p.execution.uri(ew, ns),
            "model_ref": model_ref,
            "status": self.p.execution.status(ew),
            "days": days,
            "bounds": bounds,
            "series": series,
            "daily": sorted(daily.values(), key=lambda d: d["date"]),
            "breaches": breaches,
            "signals": self._signals(ew, reports, series, bounds),
            "runs": len(reports),
            "rows": sum(int(r["rows"] or 0) for r in reports),
            "last_run": reports[-1]["created_at"] if reports else None,
            "truncated": len(reports) >= MAX_REPORTS,
        }

    def _signals(
        self,
        ew: dict[str, Any],
        reports: builtins.list[dict[str, Any]],
        series: dict[str, Any],
        bounds: dict[str, Any],
    ) -> builtins.list[dict[str, Any]]:
        """What a monitoring analyst should look at, each with the level and the reason."""
        now, out = utcnow(), []
        status = self.p.execution.status(ew)
        if status == "suspended":
            out.append({"level": "breach", "what": "warrant", "why": ew.get("suspend_reason")})
        recent = now - dt.timedelta(days=RECENT_BREACH_DAYS)
        n_recent = sum(len(r["breaches"] or []) for r in reports if r["created_at"] >= recent)
        if n_recent:
            out.append(
                {
                    "level": "breach",
                    "what": "covenants",
                    "why": f"{n_recent} breach(es) in the last {RECENT_BREACH_DAYS} days",
                }
            )
        last = reports[-1]["created_at"] if reports else None
        if status == "live" and (last is None or last < now - dt.timedelta(days=QUIET_DAYS)):
            out.append(
                {
                    "level": "watch",
                    "what": "volume",
                    "why": f"live, and nothing reported for {QUIET_DAYS} days",
                }
            )
        for side in ("inputs", "outputs"):
            for attr, points in series[side].items():
                latest = points[-1]
                if latest["psi"] is not None:
                    limit = bounds.get(attr, {}).get("psi_max", PSI_DEFAULT_MAX)
                    if latest["psi"] > limit:
                        level = "breach"
                    elif latest["psi"] > PSI_WATCH:
                        level = "watch"
                    else:
                        level = None
                    if level:
                        out.append(
                            {
                                "level": level,
                                "what": attr,
                                "why": f"PSI {latest['psi']:.3f} against the fitted population "
                                f"(watch above {PSI_WATCH}, covenant {limit})",
                            }
                        )
                rates = [q["null_rate"] for q in points if q["null_rate"] is not None]
                if len(rates) >= 5:
                    median = statistics.median(rates[:-1])
                    if rates[-1] > 0 and rates[-1] >= 2 * median and rates[-1] > median:
                        out.append(
                            {
                                "level": "watch",
                                "what": attr,
                                "why": f"null rate {rates[-1]:.3f}, at least double its median "
                                f"{median:.3f} over the window",
                            }
                        )
        return out

    def overview(self, p: Principal, days: int = 30) -> dict[str, Any]:
        """Every sealed execution warrant the caller may read, graded."""
        rows = []
        with self.p.uow() as uow:
            warrants = [
                w
                for w in uow.repo("execution_warrants").list(sealed_at__isnull=False)
                if self.p.access.allowed(uow, p, "read", "execution_warrant", w)
            ]
            ids = [w["id"] for w in warrants]
        for w in warrants:
            m = self.warrant(p, w["id"], days)
            levels = {s["level"] for s in m["signals"]}
            health = "breach" if "breach" in levels else "watch" if "watch" in levels else "ok"
            psis = [
                pts[-1]["psi"]
                for side in ("inputs", "outputs")
                for pts in m["series"][side].values()
                if pts and pts[-1]["psi"] is not None
            ]
            rows.append(
                {
                    "id": w["id"],
                    "name": m["name"],
                    "version_no": m["version_no"],
                    "namespace": m["namespace"],
                    "model_ref": m["model_ref"],
                    "status": m["status"],
                    "health": health,
                    "runs": m["runs"],
                    "rows": m["rows"],
                    "breaches": len(m["breaches"]),
                    "worst_psi": max(psis) if psis else None,
                    "last_run": m["last_run"],
                    "signals": m["signals"],
                }
            )
        order = {"breach": 0, "watch": 1, "ok": 2}
        rows.sort(key=lambda r: (order[r["health"]], r["namespace"], r["name"]))
        return {
            "days": days,
            "warrants": rows,
            "counts": {h: sum(r["health"] == h for r in rows) for h in order},
            "total": len(ids),
        }
