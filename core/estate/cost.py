"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What the estate costs, attributed to the people who own it.

## The finding, and the shape the answer has to take

**M-6**: *no FinOps model*. No cost, no budget, no chargeback. The only `COST`
in the tree was the tropical semiring for remediation planning, and the only
budget a per-process memory limit in the sandbox.

The obvious implementation is wrong here for the reason most obvious
implementations are wrong in this platform: **MAYA does not run models**, so it
cannot observe what one costs. A register that computed a cost figure would be
computing it from an assumption — a price per thousand tokens somebody typed in
last quarter, multiplied by a call count it also did not observe — and printing
the product as though it were a measurement.

So cost arrives the way monitoring observations arrive: **attested, from a named
source, with the period it covers**. MAYA attributes it, because attribution is
the half it *can* do from what it already holds — a model has an owner, a legal
entity and a domain, and those are the dimensions a showback report is cut by.

## The number this exists to produce

Not the total. A total is available from the cloud bill and nobody needs a
governance register to add it up.

What nobody has is **the share of the estate's cost nobody has attributed**, and
the share attributed to models the register does not know about. Both are
findings about the FinOps programme rather than about any model, and both are
invisible in a bill: a bill is complete by construction, so an unattributed cost
looks exactly like an attributed one until somebody asks who owns it.

## Budgets, and why a breach is a finding rather than a block

A budget here **stops nothing**. MAYA is not on the serving path and cannot
decline a model's next invocation, so a budget that claimed to enforce would be
claiming a control it has no way to exercise — the same objection that makes
`shadow` an attestation rather than a router.

What a breach does is raise a finding, with an owner, through the register that
already does that. That is weaker than a hard stop and it is what is true, and
the alternative — a budget nobody acts on because nothing happens when it is
exceeded — is the FinOps equivalent of a monitor nobody reads.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.estate.common import EstateError
from core.log import get_logger

logger = get_logger(__name__)

#: The dimensions a showback report is cut by. Each comes from the REGISTER
#: rather than from the cost record, which is the whole point: a cost attributed
#: by whoever produced the bill is attributed to whatever they thought the
#: ownership was, and the register is the place that knows.
DIMENSIONS: Tuple[str, ...] = ("owner", "legal_entity", "domain")

#: What a cost record must carry. `period_start` and `period_end` because a
#: figure with no period cannot be compared with anything — and comparison is
#: the only use a cost figure has.
REQUIRED: Tuple[Tuple[str, str], ...] = (
    ("amount", "the figure, in the currency stated"),
    ("currency", "stated rather than assumed. An estate spanning entities "
                 "spans currencies, and a total summed across them silently "
                 "is a number that is wrong by the exchange rate"),
    ("period_start", "when the period begins"),
    ("period_end", "when it ends. A figure with no period cannot be compared "
                   "with anything, and comparison is the only use a cost "
                   "figure has"),
    ("source", "the system that produced it. MAYA does not observe cost and "
               "will not compute one"),
)

#: How a cost reached here. `unattributed` is a first-class outcome rather than
#: an error: a bill line nobody can tie to a registered model is the finding,
#: and discarding it would delete the finding.
ATTRIBUTED, UNATTRIBUTED = "attributed", "unattributed"


class EstateCost:
    """Takes attested cost, attributes it from the register, and reports gaps."""

    def __init__(self, repo, registry=None, findings=None, evidence=None):
        self.repo, self.registry = repo, registry
        self.findings, self.evidence = findings, evidence

    # --------------------------------------------------------------- posture
    @staticmethod
    def posture() -> Dict[str, Any]:
        """What this computes, and the two things it will not claim."""
        return {
            "observes_cost": False,
            "enforces_a_budget": False,
            "dimensions": list(DIMENSIONS),
            "required": [{"field": f, "why": w} for f, w in REQUIRED],
            "why_not_observe": (
                "MAYA does not run models, so it cannot see what one costs. A "
                "register computing a figure would be multiplying a price "
                "somebody typed by a call count it also did not observe, and "
                "printing the product as a measurement"),
            "why_not_enforce": (
                "MAYA is not on the serving path and cannot decline a model's "
                "next invocation. A budget claiming to enforce would be "
                "claiming a control it has no way to exercise — the same "
                "objection that makes a shadow grant an attestation rather "
                "than a router. A breach raises a FINDING, with an owner"),
            "the_number_that_matters": (
                "not the total — a bill has that, and nobody needs a "
                "governance register to add it up. What nobody has is the "
                "share of the estate's cost NOBODY HAS ATTRIBUTED, and the "
                "share attributed to models the register does not know about. "
                "A bill is complete by construction, so an unattributed cost "
                "looks exactly like an attributed one until somebody asks who "
                "owns it"),
        }

    # ---------------------------------------------------------------- record
    def record(self, *, amount: float, currency: str, period_start: float,
               period_end: float, source: str, urn: str = "",
               reference: str = "", actor: str = "system",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Take one attested cost figure and attribute it.

        `urn` is optional and its absence is the interesting case: a bill line
        nobody can tie to a registered model lands `unattributed`, which is a
        finding rather than an error. Discarding it would delete the finding.
        """
        # Four literal raise sites rather than `f"cost_{field}_required"`. A
        # code built by interpolation is invisible to the scanner that checks
        # every refusal is mapped to a status — the same defect this codebase
        # has now fixed four times, and the reason a caller would have received
        # a bare 400 for a missing currency.
        why = dict(REQUIRED)
        if not str(currency).strip():
            raise EstateError("cost_currency_required",
                              "a cost record needs a currency",
                              why["currency"])
        if not period_start:
            raise EstateError("cost_period_start_required",
                              "a cost record needs a period start",
                              why["period_start"])
        if not period_end:
            raise EstateError("cost_period_end_required",
                              "a cost record needs a period end",
                              why["period_end"])
        if not str(source).strip():
            raise EstateError("cost_source_required",
                              "a cost record needs a source",
                              why["source"])
        if float(amount) < 0:
            raise EstateError(
                "cost_negative",
                f"a cost of {amount} is not a cost",
                "record a credit as its own line with its own source, rather "
                "than as a negative charge. Netting them here would hide a "
                "refund inside a period it did not belong to")
        if period_end <= period_start:
            raise EstateError(
                "cost_period_inverted",
                "the period ends before it begins",
                "check the extract. A period this way round makes every "
                "comparison against it meaningless in a direction nobody "
                "checks")
        moment = now if now is not None else time.time()
        model = self._model(urn)
        row = {
            "model_id": (model or {}).get("id"),
            "urn": (model or {}).get("urn") or urn,
            "amount": float(amount), "currency": str(currency).upper(),
            "period_start": float(period_start),
            "period_end": float(period_end),
            "source": str(source), "reference": str(reference),
            # Attribution comes from the REGISTER, not from the cost record. A
            # cost attributed by whoever produced the bill is attributed to
            # whatever they thought the ownership was.
            "owner": (model or {}).get("owner", ""),
            "legal_entity": (model or {}).get("legal_entity", ""),
            "domain": (model or {}).get("domain", ""),
            "state": ATTRIBUTED if model else UNATTRIBUTED,
            "recorded_by": actor, "recorded_at": moment,
        }
        self.repo.add(row)
        if self.evidence is not None and model:
            self.evidence.append("cost_attributed", "model", model["id"],
                                 {k: v for k, v in row.items()
                                  if k not in ("model_id",)}, actor=actor)
        logger.info("recorded %s %s for %s (%s)", row["amount"],
                    row["currency"], row["urn"] or "no model", row["state"])
        return {**row, "detail": self._record_detail(row, urn)}

    @staticmethod
    def _record_detail(row: Dict[str, Any], urn: str) -> str:
        if row["state"] == ATTRIBUTED:
            return (f"{row['amount']:,.2f} {row['currency']} attributed to "
                    f"{row['urn']}, owned by {row['owner']} in "
                    f"{row['legal_entity']}. The attribution comes from the "
                    f"register rather than from the cost record — a cost "
                    f"attributed by whoever produced the bill is attributed "
                    f"to whatever they thought the ownership was")
        return (f"{row['amount']:,.2f} {row['currency']} could not be "
                f"attributed" + (f": '{urn}' is not a registered model" if urn
                                 else ": no model was named")
                + ". Kept rather than refused, because a bill line nobody can "
                  "tie to a registered model IS the finding, and discarding it "
                  "would delete the finding")

    def _model(self, urn: str) -> Optional[Dict[str, Any]]:
        if not urn or self.registry is None:
            return None
        try:
            return self.registry.require(urn)
        except Exception:
            logger.info("cost line names '%s', which is not registered", urn)
            return None

    # -------------------------------------------------------------- showback
    def showback(self, by: str = "owner", *, since: Optional[float] = None,
                 until: Optional[float] = None) -> Dict[str, Any]:
        """The estate's attested cost, cut by a dimension the register knows.

        Cut by *the register's* view of ownership rather than the bill's, which
        is the only thing a governance platform adds here. Anybody can group a
        bill; only the register can say the grouping is the one the model is
        actually governed under.
        """
        if by not in DIMENSIONS:
            raise EstateError(
                "unknown_cost_dimension",
                f"'{by}' is not a dimension this cuts by",
                f"the dimensions are {', '.join(DIMENSIONS)}. Each comes from "
                f"the register rather than from the cost record")
        rows = self._in_window(self.repo.many(), since, until)
        buckets: Dict[str, Dict[str, Any]] = {}
        currencies = set()
        unattributed = 0.0
        for row in rows:
            currencies.add(row["currency"])
            if row["state"] != ATTRIBUTED:
                unattributed += row["amount"]
                continue
            key = row.get(by) or "(not recorded)"
            bucket = buckets.setdefault(key, {"key": key, "amount": 0.0,
                                              "models": set(), "lines": 0})
            bucket["amount"] += row["amount"]
            bucket["lines"] += 1
            bucket["models"].add(row["urn"])
        total = sum(b["amount"] for b in buckets.values()) + unattributed
        ordered = sorted(
            ({**b, "models": len(b["models"]),
              "share": round(b["amount"] / total, 4) if total else 0}
             for b in buckets.values()),
            key=lambda b: -b["amount"])
        return {
            "by": by, "buckets": ordered,
            "attributed": round(total - unattributed, 2),
            "unattributed": round(unattributed, 2),
            "unattributed_share": round(unattributed / total, 4) if total
            else 0,
            "currencies": sorted(currencies),
            "lines": len(rows),
            "detail": self._showback_detail(by, ordered, unattributed, total,
                                            currencies),
        }

    @staticmethod
    def _showback_detail(by: str, buckets: Sequence[Dict[str, Any]],
                         unattributed: float, total: float,
                         currencies: set) -> str:
        out = (f"{len(buckets)} {by}(s) carry "
               f"{round(total - unattributed, 2):,.2f} of attested cost")
        if len(currencies) > 1:
            out += (f". **{len(currencies)} currencies are present "
                    f"({', '.join(sorted(currencies))}) and these figures are "
                    f"NOT converted.** A total summed across currencies is "
                    f"wrong by the exchange rate, and MAYA holds no rate — "
                    f"reporting the mixture is the honest answer, and summing "
                    f"it would be a number somebody puts in a board pack")
        if unattributed:
            share = round(unattributed / total * 100, 1) if total else 0
            out += (f". **{unattributed:,.2f} could not be attributed to a "
                    f"registered model** — {share}% "
                    f"of the attested total. That is the number this exists "
                    f"to produce: a bill is complete by construction, so an "
                    f"unattributed cost looks exactly like an attributed one "
                    f"until somebody asks who owns it")
        else:
            out += (". Every attested line ties to a registered model, which "
                    "is the state a FinOps programme is trying to reach and "
                    "rarely reports on")
        return out

    @staticmethod
    def _in_window(rows: Sequence[Dict[str, Any]], since: Optional[float],
                   until: Optional[float]) -> List[Dict[str, Any]]:
        return [r for r in rows
                if (since is None or r["period_end"] >= since)
                and (until is None or r["period_start"] <= until)]

    # --------------------------------------------------------------- budgets
    def against_budget(self, budgets: Dict[str, float], by: str = "owner", *,
                       since: Optional[float] = None,
                       until: Optional[float] = None,
                       raise_findings: bool = False,
                       actor: str = "system") -> Dict[str, Any]:
        """Compare attested cost with declared budgets.

        A budget here **stops nothing**, and `posture()` says so. What a breach
        does is raise a finding with an owner, through the register that
        already does that — weaker than a hard stop, and what is true.
        """
        report = self.showback(by, since=since, until=until)
        spent = {b["key"]: b["amount"] for b in report["buckets"]}
        rows = []
        for key, budget in sorted(budgets.items()):
            used = spent.get(key, 0.0)
            over = used > budget
            rows.append({
                "key": key, "budget": budget, "spent": round(used, 2),
                "share": round(used / budget, 3) if budget else None,
                "over": over,
                "detail": (f"{used:,.2f} of {budget:,.2f}"
                           + (f" — OVER by {used - budget:,.2f}" if over
                              else f", {budget - used:,.2f} remaining")),
            })
        breaches = [r for r in rows if r["over"]]
        raised = []
        if raise_findings and breaches and self.findings is not None:
            raised = self._raise(breaches, by, actor)
        return {
            "by": by, "budgets": rows, "breaches": len(breaches),
            "findings_raised": raised,
            "enforces_anything": False,
            "detail": (
                f"{len(breaches)} of {len(rows)} budget(s) are exceeded"
                + (f", and {len(raised)} finding(s) were raised" if raised
                   else "")
                + ". **Nothing was blocked and nothing will be**: MAYA is not "
                  "on the serving path and cannot decline a model's next "
                  "invocation, so a budget claiming to enforce would be "
                  "claiming a control it has no way to exercise. A finding "
                  "with an owner is weaker than a hard stop and it is what is "
                  "true"),
        }

    def _raise(self, breaches: Sequence[Dict[str, Any]], by: str,
               actor: str) -> List[str]:
        raised = []
        for breach in breaches:
            try:
                finding = self.findings.raise_finding(
                    model_id=None, title=f"cost budget exceeded for "
                                         f"{by} {breach['key']}",
                    severity="Medium", source="cost",
                    detail=breach["detail"], actor=actor)
                raised.append(finding.get("id", ""))
            except Exception as exc:
                # A budget report that failed because a finding could not be
                # raised would lose the report as well as the finding.
                logger.warning("could not raise a cost finding for %s: %s",
                               breach["key"], exc)
        return raised
