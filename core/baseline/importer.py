"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Baseline import: getting a bank's existing estate into the register.

Adversarial review found this to be the single most likely cause of total
failure. On import day, 1,200 models arrive with no evidence graph, no feature
contracts and documentation in Word files. Every gate fails, every dashboard is
red, the model risk office concludes the platform is broken, and the programme
dies in month seven.

The answer is not to lower the gates. It is to be **honest about what the register
does not know**. A baselined model is in the inventory and governed *going
forward*, and it carries explicit, dated debt for everything it does not have.

The important line is the one about the future: **existing use is not blocked;
change is**. A baselined model can keep running, because stopping it was never
going to happen and pretending otherwise makes the platform something people
route around. But its next material change goes through the full path.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Sequence

from core.baseline.common import BaselineError
from core.baseline.debt import DebtRegister
from core.baseline import gaps
from core.evidence import EvidenceEngine
from core.log import get_logger
from db import ImportRepository

logger = get_logger(__name__)

# The lifecycle owns this state; naming it here would let the two drift.
from core.lifecycle import BASELINED


class BaselineImporter:
    """Imports existing models, computing their debt rather than accepting it."""

    def __init__(self, imports: ImportRepository, debts: DebtRegister,
                 registry, evidence: EvidenceEngine, state_for: Callable):
        self.imports, self.debts = imports, debts
        self.registry, self.evidence = registry, evidence
        # urn -> the same state dictionary the document compiler reads, so gap
        # detection and documentation agree about what a model has.
        self.state_for = state_for

    def import_models(self, source: str, models: Sequence[Dict[str, Any]],
                      actor: str = "system", note: str = "") -> Dict[str, Any]:
        """Register a batch, mark it baselined, and compute each model's debt."""
        if not models:
            raise BaselineError("nothing_to_import",
                                "the batch contains no models", "")
        row = {"reference": f"IMP-{len(self.imports.many()) + 1:03d}",
               "source": source, "note": note, "models": 0, "debt_items": 0,
               "imported_by": actor, "imported_at": time.time()}
        self.imports.add(row)

        imported, total_debt, failures = [], 0, []
        for spec in models:
            try:
                result = self._one(spec, row["id"], actor)
            except Exception as exc:                 # one bad row must not stop 1,199
                logger.warning("baseline import skipped %s: %s",
                               spec.get("urn"), exc)
                failures.append({"urn": spec.get("urn"), "reason": str(exc)})
                continue
            imported.append(result)
            total_debt += len(result["debt"])

        with self.evidence.recording():
            self.imports.set({"models": len(imported), "debt_items": total_debt},
                             id=row["id"])
            self.evidence.append("baseline_imported", "import", row["id"],
                                 {"reference": row["reference"], "source": source,
                                  "models": len(imported), "debt_items": total_debt,
                                  "skipped": len(failures)}, actor=actor)
        logger.info("baseline import %s: %d models, %d debt items, %d skipped",
                    row["reference"], len(imported), total_debt, len(failures))
        return {**self.imports.one(id=row["id"]), "imported": imported,
                "skipped": failures,
                "detail": (f"{len(imported)} model(s) baselined carrying "
                           f"{total_debt} debt item(s). These are governed going "
                           f"forward: existing use is not blocked, the next "
                           f"material change is.")}

    def _one(self, spec: Dict[str, Any], import_id: str,
             actor: str) -> Dict[str, Any]:
        urn = spec["urn"]
        if self.registry.get(urn):
            raise BaselineError("already_registered",
                                f"{urn} is already in the register", "")
        model = self.registry.register(
            urn, spec.get("name") or urn.rsplit("/", 1)[-1],
            spec.get("model_class", "unclassified"),
            spec.get("domain", "unassigned"), spec.get("owner", ""),
            spec.get("legal_entity", ""), spec.get("purpose", ""),
            spec.get("description", ""), spec.get("origin", "internal"),
            actor=actor)
        # Baselined, not draft: the register must never imply that historical
        # evidence was asserted when it was not.
        self.registry.catalogue.models.set({"status": BASELINED}, id=model["id"])
        if spec.get("tier") is not None:
            self.registry.set_tier(model["id"], spec["tier"])

        state = self.state_for(urn)
        found = gaps.find(state)
        owner = spec.get("owner") or "unassigned"
        debt = [self.debts.raise_debt(model["id"], g.key, owner, spec.get("tier"),
                                      import_id, actor=actor) for g in found]
        return {"urn": urn, "model_id": model["id"], "tier": spec.get("tier"),
                "debt": [d["gap_key"] for d in debt]}

    # ----------------------------------------------------------------- query
    def batches(self) -> List[Dict[str, Any]]:
        return self.imports.many()

    def portfolio(self) -> Dict[str, Any]:
        """The burn-down, across everything that was baselined.

        The number a programme is actually judged on: not how many models are
        compliant, but whether the debt is going down.
        """
        batches = self.batches()
        models = sum(b["models"] for b in batches)
        raised = sum(b["debt_items"] for b in batches)
        rows = self.debts.debts.many()
        open_items = sum(1 for d in rows if d["status"] == "open")
        closed = sum(1 for d in rows if d["status"] == "closed")
        breached = sum(1 for d in rows if d["status"] == "breached")
        return {
            "batches": len(batches), "models_baselined": models,
            "debt_raised": raised, "debt_open": open_items,
            "debt_closed": closed, "debt_breached": breached,
            "burn_down": round(closed / raised, 4) if raised else 0.0,
            "detail": (f"{closed} of {raised} baseline debt items closed "
                       f"({(closed / raised * 100) if raised else 0:.0f}%); "
                       f"{breached} expired into breaches"
                       if raised else "nothing has been baselined"),
        }
