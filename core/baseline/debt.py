"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The compliance debt register.

Debt is a tracked, reportable, burning-down quantity. It is not a breach, and
keeping those two apart is the entire reason this exists: a platform that shows
1,200 imported models as 1,200 breaches on day one is a platform the model risk
office stops believing in within a month, and the programme dies in month seven.

Two behaviours make debt real rather than decorative.

**It closes by itself.** A debt item is a claim that something is missing, and
the register can tell whether it still is. When the evidence arrives the item
closes without anybody remembering to close it — which means the burn-down chart
is a measurement rather than a self-report.

**It expires into a breach.** Past its board-approved date, debt stops being
debt. At that point it raises a finding, and a finding can block.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.baseline.common import DAY, DEFAULT_EXPIRY_MONTHS, BaselineError
from core.baseline.gaps import BY_KEY
from core.evidence import EvidenceEngine
from core.log import get_logger
from db import DebtRepository

logger = get_logger(__name__)


class DebtRegister:
    """Records what a baselined model is missing, and watches it close."""

    def __init__(self, debts: DebtRepository, evidence: EvidenceEngine,
                 findings=None, expiry_months: Optional[Dict[int, int]] = None):
        self.debts, self.evidence, self.findings = debts, evidence, findings
        self.expiry_months = expiry_months or dict(DEFAULT_EXPIRY_MONTHS)

    # -------------------------------------------------------------- record
    def raise_debt(self, model_id: str, gap_key: str, owner: str,
                   tier: Optional[int] = None, import_id: Optional[str] = None,
                   plan: str = "", actor: str = "system") -> Dict[str, Any]:
        gap = BY_KEY.get(gap_key)
        if gap is None:
            raise BaselineError("unknown_gap", f"unknown gap '{gap_key}'",
                                f"known gaps are {', '.join(sorted(BY_KEY))}")
        if self.debts.one(model_id=model_id, gap_key=gap_key, status="open"):
            raise BaselineError("already_recorded",
                                f"'{gap_key}' is already open against this model", "")
        now = time.time()
        months = self.expiry_months.get(tier or 4, 36)
        row = {"model_id": model_id, "import_id": import_id, "gap_key": gap_key,
               "description": gap.description, "materiality": gap.materiality,
               "tier": tier, "status": "open", "plan": plan, "owner": owner,
               "finding_id": None, "raised_at": now,
               "expires_at": now + months * 30 * DAY,
               "closed_at": None, "closed_by": None}
        self.debts.add(row)
        self.evidence.append("compliance_debt_raised", "model", model_id,
                             {"debt_id": row["id"], "gap": gap_key,
                              "materiality": gap.materiality,
                              "expires_in_months": months}, actor=actor)
        return self.debts.one(id=row["id"])

    # ------------------------------------------------------------ burn down
    def reconcile(self, model_id: str, state: Dict[str, Any],
                  actor: str = "system") -> Dict[str, Any]:
        """Close debt whose gap has been filled, and expire debt that is overdue.

        The burn-down is a measurement, not a self-report: an item closes because
        the evidence is there, not because somebody said it was.
        """
        closed, breached = [], []
        for item in self.debts.open_for(model_id):
            gap = BY_KEY.get(item["gap_key"])
            if gap and not gap.missing_from(state):
                closed.append(self._close(item, actor))
            elif item["expires_at"] < time.time():
                breached.append(self._breach(item, actor))
        return {"model_id": model_id, "closed": closed, "breached": breached,
                "remaining": len(self.debts.open_for(model_id)),
                "detail": (f"{len(closed)} item(s) closed because the evidence "
                           f"arrived; {len(breached)} passed their expiry and are "
                           f"now breaches")}

    def _close(self, item: Dict[str, Any], actor: str) -> Dict[str, Any]:
        self.debts.set({"status": "closed", "closed_at": time.time(),
                        "closed_by": actor}, id=item["id"])
        self.evidence.append("compliance_debt_closed", "model", item["model_id"],
                             {"debt_id": item["id"], "gap": item["gap_key"]},
                             actor=actor)
        logger.info("compliance debt %s closed: the evidence arrived", item["gap_key"])
        return self.debts.one(id=item["id"])

    def _breach(self, item: Dict[str, Any], actor: str) -> Dict[str, Any]:
        """Past its date, debt stops being debt."""
        finding_id = None
        if self.findings:
            finding = self.findings.raise_finding(
                item["model_id"], item["materiality"],
                title=f"Baseline debt expired: {item['gap_key']}",
                owner=item["owner"],
                description=(f"{item['description']}. This was accepted as baseline "
                             "debt at import and has passed its board-approved "
                             "expiry, so it is now a breach rather than debt."),
                category="compliance_debt", source="self_identified", actor=actor)
            finding_id = finding["id"]
        self.debts.set({"status": "breached", "finding_id": finding_id},
                       id=item["id"])
        self.evidence.append("compliance_debt_breached", "model", item["model_id"],
                             {"debt_id": item["id"], "gap": item["gap_key"],
                              "finding_id": finding_id}, actor=actor)
        logger.warning("compliance debt %s for model %s expired into a breach",
                       item["gap_key"], item["model_id"])
        return self.debts.one(id=item["id"])

    def plan_for(self, debt_id: str, plan: str, actor: str = "system") -> Dict[str, Any]:
        """Record how and when this gap will be closed."""
        item = self.require(debt_id)
        if not plan.strip():
            raise BaselineError("plan_required",
                                "a debt item needs a dated plan to close it", "")
        self.debts.set({"plan": plan}, id=debt_id)
        self.evidence.append("compliance_debt_planned", "model", item["model_id"],
                             {"debt_id": debt_id, "plan": plan}, actor=actor)
        return self.debts.one(id=debt_id)

    # ----------------------------------------------------------------- query
    def get(self, debt_id: str) -> Optional[Dict[str, Any]]:
        return self.debts.one(id=debt_id)

    def require(self, debt_id: str) -> Dict[str, Any]:
        row = self.get(debt_id)
        if row is None:
            raise BaselineError("no_debt", f"no debt item {debt_id}", "")
        return row

    def open_for(self, model_id: str) -> List[Dict[str, Any]]:
        return self.debts.open_for(model_id)

    def status(self, model_id: str, now: Optional[float] = None) -> Dict[str, Any]:
        """Debt on this model, kept separate from breach on every view."""
        moment = now if now is not None else time.time()
        items = self.debts.many(model_id=model_id)
        open_items = [d for d in items if d["status"] == "open"]
        breached = [d for d in items if d["status"] == "breached"]
        overdue = [d for d in open_items if d["expires_at"] < moment]
        by_materiality: Dict[str, int] = {}
        for d in open_items:
            by_materiality[d["materiality"]] = by_materiality.get(d["materiality"], 0) + 1
        return {
            "baselined": bool(items),
            "debt_open": len(open_items), "debt_closed":
                sum(1 for d in items if d["status"] == "closed"),
            "breached": len(breached), "overdue": len(overdue),
            "by_materiality": by_materiality,
            "unplanned": sum(1 for d in open_items if not d["plan"]),
            "next_expiry": min((d["expires_at"] for d in open_items), default=None),
            "detail": (f"{len(open_items)} open debt item(s), "
                       f"{len(breached)} expired into breaches"
                       if items else "not a baselined model"),
        }
