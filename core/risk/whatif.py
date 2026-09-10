"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a change to the tiering rules would do to the estate you already have.

**The tiering approach is itself a model, and SS1/23 1.3(d) says so.** It takes
inputs — exposure, purpose, complexity, interpretability — applies a rule, and
produces a number that decides how much scrutiny everything else gets. A firm
that governs four hundred models and not the one that tiers them has left the
most consequential model in the estate outside the framework.

Which makes the change to it the interesting act. Two things follow.

**A tiering change is measured by who moves, not by whether the rule is
better.** Nobody can look at a rule and say what it does; everybody can look at
*eleven models leave tier 1* and have an opinion. So the simulator re-runs the
candidate over the models that exist and reports the **diff**, per model, in both
directions — because the two directions are not the same event.

**A model moving DOWN is the one to look at.** A tiering change that raises
scrutiny costs money and annoys people, and somebody will notice. One that lowers
it is silent, arrives as a spreadsheet with fewer red cells, and is the single
easiest way to reduce a firm's model risk on paper without touching a model. So
downgrades are counted, listed and named first, and the summary says how much
exposure moved out of each tier — because *three models moved down* and *three
models carrying eleven billion moved down* are different sentences.

**Nothing is applied.** The simulator computes and returns; adopting a ruleset is
a separate act with a signature on it. A what-if that could quietly become a
what-is would be the fastest route to the outcome above.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.risk.tiering import RiskError

logger = get_logger(__name__)

#: A change that raises scrutiny, and one that lowers it. Named because the
#: summary is about the second and a signed integer would bury it.
UP, DOWN, SAME = "up", "down", "same"


class TieringWhatIf:
    """Re-runs a candidate tiering rule across the estate and diffs it."""

    def __init__(self, engine, registry, risk_repo, approvals=None):
        self.engine, self.registry = engine, registry
        self.risk = risk_repo
        # Regulatory permissions, so the summary can say when a downgrade lands
        # on a model held under one. Optional: without it that sentence is
        # simply absent rather than wrong.
        self.approvals = approvals

    # -------------------------------------------------------------- simulate
    def simulate(self, candidate,
                 models: Optional[Sequence[Dict[str, Any]]] = None
                 ) -> Dict[str, Any]:
        """Apply a candidate rule to every model that has been assessed.

        `candidate` is anything callable on a fact dictionary returning a tier.
        Passing the rule rather than a configuration is deliberate: a rule
        expressed as data would need a language, and a language for this would
        be a second policy engine beside the one that already exists.
        """
        if not callable(candidate):
            raise RiskError(
                "candidate_not_callable",
                "the candidate rule must be callable on a fact dictionary",
                "pass a function of the assessment's own facts; the current "
                "engine's `assess` is one")
        rows = list(models if models is not None else self.registry.list())
        moved, unassessed = [], []
        for model in rows:
            assessments = self.risk.many(model_id=model["id"])
            if not assessments:
                unassessed.append(model.get("urn"))
                continue
            latest = max(assessments, key=lambda a: a.get("assessed_at") or 0)
            facts = latest.get("facts") or {}
            was = latest.get("tier")
            try:
                now = int(candidate(facts))
            except Exception as failure:
                # A candidate that cannot decide about a model is a finding
                # about the CANDIDATE. Recorded per model rather than aborting:
                # a rule that fails on one row and works on four hundred is
                # worth seeing, and an exception would have hidden the four
                # hundred.
                logger.info("candidate tiering rule could not decide about "
                            "%s: %s", model.get("urn"),
                            type(failure).__name__)
                moved.append({"urn": model.get("urn"), "was": was,
                              "now": None, "direction": "undecidable",
                              "why": str(failure)[:200]})
                continue
            direction = (SAME if now == was
                         # A LOWER number is a HIGHER tier here: tier 1 is the
                         # most material. So a rule producing a bigger number
                         # has lowered the scrutiny.
                         else DOWN if (was is not None and now > was)
                         else UP)
            moved.append({
                "urn": model.get("urn"), "was": was, "now": now,
                "direction": direction,
                "exposure": (facts or {}).get("exposure"),
                "held_under_approval": self._held(model),
            })
        return self._summarise(moved, unassessed, rows)

    def _held(self, model: Dict[str, Any]) -> List[str]:
        """Regulatory permissions on this model, if any.

        A downgrade on a model held under IRB permission is a different
        conversation from a downgrade on one that is not, and it is the sentence
        somebody will want when the change is presented.
        """
        if self.approvals is None:
            return []
        try:
            out = self.approvals.for_model(model["urn"])
        except Exception:
            # A model whose approvals cannot be read is reported without the
            # sentence about them rather than not reported at all: a simulation
            # that went blank because one lookup failed would hide the
            # downgrades, which are the whole point.
            logger.warning("could not read regulatory approvals for %s; the "
                           "simulation reports it without them",
                           model.get("urn"), exc_info=True)
            return []
        return [a["kind"] for a in out["approvals"]
                if a.get("effectively_in_force")]

    @staticmethod
    def _summarise(moved, unassessed, rows) -> Dict[str, Any]:
        down = [m for m in moved if m["direction"] == DOWN]
        up = [m for m in moved if m["direction"] == UP]
        undecidable = [m for m in moved if m["direction"] == "undecidable"]
        exposure_down = sum(m.get("exposure") or 0.0 for m in down)
        under_approval = [m for m in down if m.get("held_under_approval")]
        # Downgrades first, and within them the largest exposure first: the
        # summary is about what got quieter, and an alphabetical list buries it.
        moved.sort(key=lambda m: (m["direction"] != DOWN,
                                  -(m.get("exposure") or 0.0)))
        return {
            "models": len(rows), "compared": len(moved),
            "moved": [m for m in moved if m["direction"] != SAME],
            "unchanged": sum(1 for m in moved if m["direction"] == SAME),
            "up": len(up), "down": len(down),
            "undecidable": undecidable,
            "unassessed": unassessed,
            "exposure_moving_down": exposure_down,
            "downgrades_under_regulatory_approval": [
                {"urn": m["urn"], "approvals": m["held_under_approval"]}
                for m in under_approval],
            "applied": False,
            "detail": TieringWhatIf._detail(rows, moved, up, down, undecidable,
                                            unassessed, exposure_down,
                                            under_approval),
        }

    @staticmethod
    def _detail(rows, moved, up, down, undecidable, unassessed,
                exposure_down, under_approval) -> str:
        if not moved:
            return ("no model on this estate has been assessed, so a candidate "
                    "rule has nothing to be compared against — which is a fact "
                    "about the estate rather than about the rule")
        out = (f"{len(down)} model(s) move DOWN and {len(up)} move up, out of "
               f"{len(moved)} compared")
        if down:
            out += (". The downgrades are what to look at: raising scrutiny "
                    "costs money and somebody notices, and lowering it is "
                    "silent — it arrives as a spreadsheet with fewer red "
                    "cells and is the easiest way to reduce a firm's model "
                    "risk on paper without touching a model")
            if exposure_down:
                out += (f". They carry {exposure_down:,.0f} of exposure "
                        f"between them, which is the number to quote rather "
                        f"than the count")
        if under_approval:
            out += (f". {len(under_approval)} of the downgrades land on models "
                    f"held under a regulatory permission, which is a different "
                    f"conversation")
        if undecidable:
            out += (f". The candidate could not decide about "
                    f"{len(undecidable)} model(s) — a finding about the rule "
                    f"rather than about them")
        if unassessed:
            out += (f". {len(unassessed)} model(s) have never been assessed "
                    f"and are not in the comparison")
        out += ". Nothing has been applied: adopting a ruleset is a separate " \
               "act with a signature on it"
        return out
