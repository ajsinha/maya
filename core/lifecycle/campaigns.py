"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Periodic activities across a population, and the number that moves on its own.

An attestation round, an annual inventory certification, a *confirm your model's
limitations are still accurate* exercise: these are the work a model risk
function actually does most of, and they are run out of spreadsheets because a
register that holds models does not obviously hold *rounds of asking about
models*.

**The population is derived at launch and then frozen, and the derivation is
kept beside it.** That is the whole design, and the reason is a number nobody
watches. A campaign whose population is a live query silently changes size: a
model retired in week three turns 47 of 50 into 47 of 49, and the completion
figure **goes up without anybody having done anything**. Completion is the one
number a campaign exists to produce, and a live population is a completion
figure that improves on its own.

So there are two numbers, and they are not the same:

  * **completion** — against the population as it stood when the campaign
    opened. This is the number that goes to a committee, and it can only move
    when somebody responds.
  * **coverage** — against re-running the derivation now. Models that have
    entered the population since are *drift*, and they are reported rather than
    quietly added, because adding them mid-round would move the denominator.

**Assignment is derived, never typed.** Each item goes to the model's own owner
at launch. A campaign with typed assignees is one that ends up assigned to people
who left, and reassignment is recorded as an act rather than an edit — *who was
this originally for* is the question asked about the ones that were not done.

**A campaign cannot be closed with items outstanding without saying so.** It can
be closed — a round has to end — but the closure records how many were never
answered, because a campaign that ends quietly and reports 100% is worse than
one that reports 84% and stops.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.lifecycle.common import LifecycleError

logger = get_logger(__name__)

DAY = 86400.0

OUTSTANDING, ANSWERED, DECLINED, NOT_APPLICABLE = (
    "outstanding", "answered", "declined", "not_applicable")
ITEM_STATES = (OUTSTANDING, ANSWERED, DECLINED, NOT_APPLICABLE)

OPEN, CLOSED = "open", "closed"

#: What a round is for. Held as data because the instruction sent to an owner
#: depends on it, and a campaign whose kind is free text is one nobody can
#: report on across years.
KINDS: Dict[str, str] = {
    "attestation": "confirm the model record is accurate and complete",
    "inventory_certification": "confirm this model is still in use, and by whom",
    "limitation_review": "confirm the recorded limitations still hold",
    "assumption_review": "confirm the recorded assumptions still hold",
    "owner_confirmation": "confirm you are still the accountable owner",
    "use_confirmation": "confirm the approved uses are the uses being made",
}


class Campaigns:
    """Rounds of asking, over a population fixed at the moment of asking."""

    def __init__(self, campaigns, items, registry, semantics, evidence,
                 notifications=None):
        self.campaigns, self.items = campaigns, items
        self.registry, self.semantics = registry, semantics
        self.evidence, self.notifications = evidence, notifications

    # ------------------------------------------------------------------ open
    def open(self, reference: str, *, kind: str, title: str,
             where: Optional[Sequence[Dict[str, Any]]] = None,
             instruction: str = "", due_at: Optional[float] = None,
             now: Optional[float] = None,
             actor: str = "system") -> Dict[str, Any]:
        """Fix a population and assign it. The derivation is kept."""
        if kind not in KINDS:
            raise LifecycleError(
                "unknown_campaign_kind",
                f"'{kind}' is not a kind of campaign",
                f"the six are {', '.join(KINDS)} — the list is closed so that "
                f"two rounds run three years apart can be compared")
        if self.campaigns.one(reference=reference):
            raise LifecycleError(
                "campaign_already_open",
                f"a campaign with reference '{reference}' already exists",
                "give this round its own reference; two rounds under one name "
                "produce one completion figure covering two populations")
        moment = now if now is not None else time.time()
        derivation = {"entity": "model", "where": list(where or [])}
        population = self._derive(derivation)
        if not population:
            raise LifecycleError(
                "empty_population",
                "this derivation selects no model, so there is nobody to ask",
                "widen the filter — a campaign over nothing reports 100% "
                "complete on the day it opens, which is the most misleading "
                "number this module could produce")

        row = {"reference": reference, "kind": kind, "title": title,
               "instruction": instruction or KINDS[kind],
               "derivation": derivation, "opened_by": actor,
               "opened_at": moment, "due_at": due_at, "status": OPEN,
               "closed_at": None, "closed_by": None}
        with self.evidence.recording():
            self.campaigns.add(row)
            self._assign(row, population, moment, actor)
        logger.info("campaign %s (%s) opened over %d model(s) by %s", reference,
                    kind, len(population), actor)
        return self.status(reference, now=moment)

    def _assign(self, row: Dict[str, Any], population: Sequence[Dict[str, Any]],
                moment: float, actor: str) -> None:
        """One item per model, assigned to the model's own owner."""
        for model in population:
            self.items.add({
                "campaign_id": row["id"], "model_id": model["id"],
                "urn": model["urn"],
                # Derived, never typed. A typed assignee is one who left.
                "assignee": model.get("owner") or actor,
                "assigned_at": moment, "state": OUTSTANDING,
                "response": "", "responded_by": None, "responded_at": None})
        self.evidence.append(
            "campaign_opened", "campaign", row["id"],
            {"reference": row["reference"], "kind": row["kind"],
             "population": len(population), "derivation": row["derivation"],
             "due_at": row["due_at"]}, actor=actor)

    def _derive(self, derivation: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The population, through the semantic layer rather than a private query.

        Deliberately the same layer `/query` uses: a campaign's population and
        the estate report about it should not be able to disagree about what
        `in_force` means.
        """
        result = self.semantics.query(
            derivation.get("entity") or "model",
            select=["urn"], where=derivation.get("where") or [],
            limit=10_000)
        return [self.registry.require(row["urn"]) for row in result["rows"]]

    # ------------------------------------------------------------------ respond
    def respond(self, reference: str, urn: str, *, state: str,
                response: str = "", actor: str = "system",
                now: Optional[float] = None) -> Dict[str, Any]:
        """Answer one item."""
        campaign = self.require(reference)
        if campaign["status"] == CLOSED:
            raise LifecycleError(
                "campaign_closed",
                f"campaign '{reference}' closed "
                f"{_when(campaign['closed_at'])}, so an answer now would change "
                f"a figure already reported",
                "open a new round")
        if state not in ITEM_STATES or state == OUTSTANDING:
            raise LifecycleError(
                "unknown_response",
                f"'{state}' is not an answer to a campaign item",
                f"answer with one of "
                f"{', '.join(s for s in ITEM_STATES if s != OUTSTANDING)}")
        item = self.items.one(campaign_id=campaign["id"], urn=urn)
        if not item:
            raise LifecycleError(
                "not_in_this_campaign",
                f"{urn} is not in the population of '{reference}'",
                "the population was fixed when the round opened; a model that "
                "has entered since is reported as drift and is not added, "
                "because adding it would move the denominator")
        if state in (DECLINED, NOT_APPLICABLE) and not (response or "").strip():
            raise LifecycleError(
                "reason_required",
                f"answering '{state}' needs a reason — it is the sentence a "
                f"reviewer reads when the round is summarised, and writing it "
                f"now is easier than reconstructing it in a year",
                "say why")
        moment = now if now is not None else time.time()
        with self.evidence.recording():
            self.items.set({"state": state, "response": response.strip(),
                            "responded_by": actor, "responded_at": moment},
                           id=item["id"])
            self.evidence.append(
                "campaign_item_answered", "model", item["model_id"],
                {"campaign": reference, "kind": campaign["kind"],
                 "state": state, "response": response.strip(),
                 "assignee": item["assignee"]}, actor=actor)
        logger.info("%s answered %s in campaign %s as %s", actor, urn,
                    reference, state)
        return self.status(reference, now=moment)

    def reassign(self, reference: str, urn: str, to: str, reason: str,
                 actor: str = "system",
                 now: Optional[float] = None) -> Dict[str, Any]:
        """Move an item to somebody else, on the record.

        An act rather than an edit: *who was this originally for* is the
        question asked about the items that were not done, and an edit erases
        the answer.
        """
        campaign = self.require(reference)
        item = self.items.one(campaign_id=campaign["id"], urn=urn)
        if not item:
            raise LifecycleError("not_in_this_campaign",
                                f"{urn} is not in '{reference}'", "")
        if not (reason or "").strip():
            raise LifecycleError(
                "reason_required",
                "reassignment needs a reason: an item that moved twice and "
                "was never done is a story, and the reasons are the story",
                "say why")
        moment = now if now is not None else time.time()
        with self.evidence.recording():
            self.items.set({"assignee": to, "assigned_at": moment},
                           id=item["id"])
            self.evidence.append(
                "campaign_item_reassigned", "model", item["model_id"],
                {"campaign": reference, "from": item["assignee"], "to": to,
                 "reason": reason.strip()}, actor=actor)
        return self.status(reference, now=moment)

    # ------------------------------------------------------------------ close
    def close(self, reference: str, actor: str = "system",
              now: Optional[float] = None) -> Dict[str, Any]:
        """End a round, recording what was never answered.

        Closing over outstanding items is allowed — a round has to end — and the
        count goes on the record, because a campaign that ends quietly and
        reports 100% is worse than one that reports 84% and stops.
        """
        campaign = self.require(reference)
        if campaign["status"] == CLOSED:
            raise LifecycleError("campaign_closed",
                                f"'{reference}' is already closed", "")
        moment = now if now is not None else time.time()
        state = self.status(reference, now=moment)
        with self.evidence.recording():
            self.campaigns.set({"status": CLOSED, "closed_at": moment,
                                "closed_by": actor}, id=campaign["id"])
            self.evidence.append(
                "campaign_closed", "campaign", campaign["id"],
                {"reference": reference, "population": state["population"],
                 "answered": state["answered"],
                 "never_answered": state["outstanding"],
                 "completion": state["completion"],
                 "drift_since_opening": len(state["drift"])}, actor=actor)
        logger.info("campaign %s closed by %s at %.0f%% with %d never answered",
                    reference, actor, 100 * state["completion"],
                    state["outstanding"])
        return self.status(reference, now=moment)

    # ----------------------------------------------------------------- status
    def status(self, reference: str,
               now: Optional[float] = None) -> Dict[str, Any]:
        """Completion against the frozen population, coverage against today's."""
        campaign = self.require(reference)
        moment = now if now is not None else time.time()
        items = self.items.many(campaign_id=campaign["id"])
        by_state = {s: [i for i in items if i["state"] == s] for s in ITEM_STATES}
        answered = len(items) - len(by_state[OUTSTANDING])
        live = {m["urn"] for m in self._derive(campaign["derivation"])}
        frozen = {i["urn"] for i in items}
        drift = sorted(live - frozen)
        gone = sorted(frozen - live)
        by_assignee: Dict[str, Dict[str, int]] = {}
        for item in items:
            row = by_assignee.setdefault(item["assignee"],
                                         {"outstanding": 0, "answered": 0})
            row["outstanding" if item["state"] == OUTSTANDING
                else "answered"] += 1
        return {
            **campaign, "items": items,
            "population": len(items), "answered": answered,
            "outstanding": len(by_state[OUTSTANDING]),
            "by_state": {s: len(v) for s, v in by_state.items() if v},
            "completion": round(answered / len(items), 3) if items else 0.0,
            "by_assignee": by_assignee,
            "drift": drift, "left_the_population": gone,
            "overdue": bool(campaign.get("due_at")
                            and moment > campaign["due_at"]
                            and by_state[OUTSTANDING]),
            "detail": self._detail(campaign, items, answered, by_state, drift,
                                   gone, moment),
        }

    @staticmethod
    def _detail(campaign, items, answered, by_state, drift, gone, moment) -> str:
        out = (f"{answered} of {len(items)} answered "
               f"({answered / len(items):.0%} complete) against the population "
               f"as it stood when this round opened"
               if items else "this round has no items")
        if drift or gone:
            out += (". Re-deriving now returns "
                    + (f"{len(drift)} model(s) that have entered the population "
                       f"since" if drift else "")
                    + (" and " if drift and gone else "")
                    + (f"{len(gone)} that have left it" if gone else "")
                    + ". They are reported and not folded in: a live population "
                      "is a completion figure that improves on its own, because "
                      "a model retired in week three turns 47 of 50 into 47 of "
                      "49 without anybody doing anything")
        if by_state.get(DECLINED):
            out += (f". {len(by_state[DECLINED])} declined, each with a reason "
                    f"on the record")
        if campaign.get("due_at") and moment > campaign["due_at"] \
                and by_state[OUTSTANDING]:
            out += (f". Past its date with {len(by_state[OUTSTANDING])} "
                    f"outstanding")
        return out

    def require(self, reference: str) -> Dict[str, Any]:
        row = self.campaigns.one(reference=reference)
        if not row:
            raise LifecycleError("unknown_campaign",
                                f"no campaign '{reference}'",
                                "list the campaigns")
        return row

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every round, least complete first."""
        moment = now if now is not None else time.time()
        rows = [self.status(c["reference"], now=moment)
                for c in self.campaigns.many()]
        rows.sort(key=lambda r: (r["status"] != OPEN, r["completion"]))
        open_rows = [r for r in rows if r["status"] == OPEN]
        return {
            "campaigns": rows, "count": len(rows), "open": len(open_rows),
            "outstanding": sum(r["outstanding"] for r in open_rows),
            "overdue": [r["reference"] for r in open_rows if r["overdue"]],
            "drifted": [r["reference"] for r in open_rows if r["drift"]],
            "detail": (
                f"{len(open_rows)} open round(s) with "
                f"{sum(r['outstanding'] for r in open_rows)} item(s) "
                f"outstanding"
                + (f", {sum(1 for r in open_rows if r['overdue'])} past their "
                   f"date" if any(r["overdue"] for r in open_rows) else "")
                if open_rows else
                "no round is open. Every campaign here is closed, and each "
                "recorded how many of its items were never answered — a "
                "campaign that ends quietly and reports 100% is worse than one "
                "that reports 84% and stops"),
        }

    @staticmethod
    def kinds() -> Dict[str, Any]:
        return {"kinds": [{"kind": k, "asks": v} for k, v in KINDS.items()],
                "states": list(ITEM_STATES),
                "detail": ("the population is derived at launch and frozen, and "
                           "the derivation is kept beside it. Completion is "
                           "measured against the frozen population and coverage "
                           "against re-running the derivation; a live "
                           "population is a completion figure that improves on "
                           "its own")}


def _when(stamp: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(stamp)) if stamp else "unknown"
