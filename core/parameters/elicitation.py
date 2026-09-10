"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A panel asked a question, and the disagreement that is the answer.

T7 parameters come out of expert judgement — a scenario weight, a climate
transition probability, an operational-risk severity. `elicit` has been a verb
and `elicited_weights` a parameter kind since the algebra was written, and what
the register held was the number the panel arrived at. That is the least
interesting thing an elicitation produces.

**The value of an elicitation is the spread.** *How much did they disagree* is
the first question a validator asks about a judgemental parameter, and a process
that stores only the final weight has destroyed the evidence that they disagreed
at all. So individual responses are recorded **per round, per panellist, and are
never overwritten**: a response revised in place erases the movement between
rounds, and the movement is the only thing convergence can be measured from.

**Convergence is measured and never asserted.** The spread across rounds is
arithmetic. What it means is not: a panel that converged because the most senior
person answered first is indistinguishable, in the numbers, from one that
converged on the evidence. So the report says the spread narrowed and says
explicitly that it cannot say why — and it names whether responses within a round
arrived in an order anybody could have seen, because that is the one structural
fact about anchoring that a register can hold.

**Dissent is part of the number.** A panellist who does not accept the conclusion
is recorded against it, and the dissent travels with the parameter set. A final
weight whose dissent nobody can find is a weight that looks unanimous, and the
firm that relies on it does not know it is relying on a majority.

**A panel of one is refused.** One expert's judgement is not an elicitation; it
is an assumption, and the assumption register is where an assumption belongs —
with a materiality, an owner and something watching it.

**Independence is recorded rather than required.** In a small firm the only
person who genuinely understands the model is often the person who built it, and
refusing their participation would push the elicitation off the platform
entirely. So a conflicted panellist is named, their weight in the aggregate is
visible, and the report says what share of the answer came from people who are
not independent.
"""
from __future__ import annotations

import time
from statistics import median, pstdev
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.parameters.common import ParameterError

logger = get_logger(__name__)

OPEN, CONCLUDED, ABANDONED = "open", "concluded", "abandoned"
STATES = (OPEN, CONCLUDED, ABANDONED)

#: Below this, it is not a panel. One expert's judgement is an assumption.
MINIMUM_PANEL = 3

#: How a round is run. Held as data because the method changes what the spread
#: means, and a report that did not say which was used is comparing two things.
METHODS: Dict[str, str] = {
    "delphi": "panellists answer independently, see the anonymised spread, and "
              "answer again. The classic protection against anchoring, and it "
              "only works if the first round really was independent",
    "nominal_group": "panellists answer independently, then discuss, then "
                     "answer again. Faster than Delphi and more exposed to "
                     "whoever speaks first",
    "workshop": "panellists answer in the room. Recorded as a method rather "
                "than refused, because it is what most firms actually do — and "
                "naming it is what stops its spread being read like a Delphi's",
}

#: Where a spread stops being a range and starts being a disagreement. Relative
#: to the median, so it means the same thing for a probability and a currency
#: amount.
WIDE_SPREAD = 0.5


class Elicitations:
    """Panels, rounds, responses, convergence and dissent."""

    def __init__(self, elicitations, responses, registry, evidence,
                 parameters=None):
        self.elicitations, self.responses = elicitations, responses
        self.registry, self.evidence = registry, evidence
        self.parameters = parameters

    # ------------------------------------------------------------------ open
    def open(self, reference: str, urn: str, *, question: str,
             panel: Sequence[str], facilitator: str, units: str = "",
             method: str = "delphi", semver: str = "",
             now: Optional[float] = None,
             actor: str = "system") -> Dict[str, Any]:
        """Convene a panel around one question."""
        model = self.registry.require(urn)
        if method not in METHODS:
            raise ParameterError(
                "unknown_method", f"'{method}' is not an elicitation method",
                f"the three are {', '.join(METHODS)} — the method changes what "
                f"a spread means, and a report that did not say which was used "
                f"would be comparing two different things")
        if not (question or "").strip():
            raise ParameterError(
                "question_required",
                "an elicitation needs the question as it was put to the panel. "
                "Two experts answering slightly different questions produce a "
                "spread that means nothing",
                "write the question down")
        members = sorted({p for p in panel if (p or "").strip()})
        if len(members) < MINIMUM_PANEL:
            raise ParameterError(
                "panel_too_small",
                f"{len(members)} panellist(s) is not a panel; "
                f"{MINIMUM_PANEL} is the floor",
                "one expert's judgement is not an elicitation, it is an "
                "assumption — and the assumption register is where an "
                "assumption belongs, with a materiality, an owner and "
                "something watching it")
        if facilitator in members:
            raise ParameterError(
                "facilitator_is_a_panellist",
                f"{facilitator} is running the elicitation and answering it",
                "the facilitator sets the question and sees the responses "
                "before the panel does; somebody in both roles can shape the "
                "spread they are about to report")
        if self.elicitations.one(reference=reference):
            raise ParameterError(
                "elicitation_already_open",
                f"'{reference}' already exists",
                "give this one its own reference")
        version = (self.registry.version(urn, semver) if semver else None)
        moment = now if now is not None else time.time()
        row = {"reference": reference, "model_id": model["id"],
               "model_version_id": (version or {}).get("id"),
               "question": question.strip(), "units": units,
               "panel": members, "facilitator": facilitator,
               "method": method, "round": 1, "state": OPEN,
               "final_value": None, "final_note": "", "concluded_by": None,
               "opened_at": moment, "concluded_at": None}
        with self.evidence.recording():
            self.elicitations.add(row)
            self.evidence.append(
                "elicitation_opened", "model", model["id"],
                {"reference": reference, "question": question.strip(),
                 "panel": members, "method": method,
                 "facilitator": facilitator}, actor=actor)
        logger.info("elicitation %s opened over %d panellist(s) by %s",
                    reference, len(members), facilitator)
        return self.read(reference)

    # ---------------------------------------------------------------- respond
    def respond(self, reference: str, panellist: str, *, value: float,
                confidence: str = "", reasoning: str = "",
                independent: bool = True, dissented: bool = False,
                now: Optional[float] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Record one answer in the current round. Never overwritten."""
        elicitation = self.require(reference)
        if elicitation["state"] != OPEN:
            raise ParameterError(
                "elicitation_closed",
                f"'{reference}' is {elicitation['state']}",
                "a response after the conclusion would change a spread already "
                "reported; open another round before concluding, or another "
                "elicitation after")
        if panellist not in elicitation["panel"]:
            raise ParameterError(
                "not_on_the_panel",
                f"{panellist} is not on this panel",
                "the panel is fixed when the elicitation opens: adding a "
                "member mid-round changes the denominator of a spread that has "
                "already been partly formed")
        held = self.responses.one(elicitation_id=elicitation["id"],
                                  round=elicitation["round"],
                                  panellist=panellist)
        if held:
            raise ParameterError(
                "already_answered",
                f"{panellist} has answered round {elicitation['round']}",
                "open the next round. A response revised in place erases the "
                "movement between rounds, and the movement is the only thing "
                "convergence can be measured from")
        moment = now if now is not None else time.time()
        row = {"elicitation_id": elicitation["id"],
               "round": elicitation["round"], "panellist": panellist,
               "value": float(value), "confidence": confidence,
               "reasoning": reasoning.strip(),
               "independent": bool(independent),
               "dissented": bool(dissented), "recorded_at": moment}
        self.responses.add(row)
        logger.info("%s answered round %d of %s%s", panellist,
                    elicitation["round"], reference,
                    " (not independent)" if not independent else "")
        return self.read(reference)

    def next_round(self, reference: str, actor: str = "system") -> Dict[str, Any]:
        """Open another round. The previous one stays exactly as it was."""
        elicitation = self.require(reference)
        if elicitation["state"] != OPEN:
            raise ParameterError("elicitation_closed",
                                 f"'{reference}' is {elicitation['state']}", "")
        answered = self.responses.many(elicitation_id=elicitation["id"],
                                       round=elicitation["round"])
        if not answered:
            raise ParameterError(
                "round_is_empty",
                f"nobody has answered round {elicitation['round']}",
                "an empty round advanced is a round that never happened, and "
                "the convergence series would carry a gap nothing explains")
        self.elicitations.set({"round": elicitation["round"] + 1},
                              id=elicitation["id"])
        logger.info("elicitation %s advanced to round %d", reference,
                    elicitation["round"] + 1)
        return self.read(reference)

    # --------------------------------------------------------------- conclude
    def conclude(self, reference: str, *, value: float, note: str,
                 actor: str = "system",
                 now: Optional[float] = None) -> Dict[str, Any]:
        """Record the number the panel arrived at, with its dissent attached."""
        elicitation = self.require(reference)
        if elicitation["state"] != OPEN:
            raise ParameterError("elicitation_closed",
                                 f"'{reference}' is {elicitation['state']}", "")
        rounds = self.rounds(reference)
        if not rounds:
            raise ParameterError(
                "nothing_to_conclude",
                "no panellist has answered anything",
                "a conclusion with no responses behind it is one person's "
                "number wearing a panel's name")
        if not (note or "").strip():
            raise ParameterError(
                "note_required",
                "a conclusion needs the reasoning. The number is the least "
                "interesting thing an elicitation produces, and a year later "
                "the note is the only part anybody can act on",
                "say how the panel got here")
        moment = now if now is not None else time.time()
        latest = rounds[-1]
        with self.evidence.recording():
            self.elicitations.set(
                {"state": CONCLUDED, "final_value": float(value),
                 "final_note": note.strip(), "concluded_by": actor,
                 "concluded_at": moment}, id=elicitation["id"])
            self.evidence.append(
                "elicitation_concluded", "model", elicitation["model_id"],
                {"reference": reference, "value": float(value),
                 "note": note.strip(), "rounds": len(rounds),
                 "panel": elicitation["panel"],
                 "spread": latest["spread"],
                 # Carried on the chain, not only in a column. A final weight
                 # whose dissent nobody can find is one that looks unanimous.
                 "dissent": latest["dissenters"],
                 "not_independent": latest["not_independent"]}, actor=actor)
        logger.info("elicitation %s concluded at %s by %s with %d dissent(s)",
                    reference, value, actor, len(latest["dissenters"]))
        return self.read(reference)

    # ------------------------------------------------------------------ read
    def rounds(self, reference: str) -> List[Dict[str, Any]]:
        """Every round, with its spread. The spread is the answer."""
        elicitation = self.require(reference)
        rows = self.responses.many(elicitation_id=elicitation["id"])
        by_round: Dict[int, List[Dict[str, Any]]] = {}
        for row in rows:
            by_round.setdefault(int(row["round"]), []).append(row)
        out = []
        for number in sorted(by_round):
            answers = by_round[number]
            values = [a["value"] for a in answers if a["value"] is not None]
            mid = median(values) if values else None
            spread = (max(values) - min(values)) if len(values) > 1 else 0.0
            out.append({
                "round": number, "responses": answers,
                "answered": len(answers),
                "of": len(elicitation["panel"]),
                "median": mid, "minimum": min(values) if values else None,
                "maximum": max(values) if values else None,
                "spread": round(spread, 6),
                "relative_spread": (round(spread / abs(mid), 4)
                                    if mid else None),
                "dispersion": (round(pstdev(values), 6)
                               if len(values) > 1 else 0.0),
                "dissenters": [a["panellist"] for a in answers
                               if a["dissented"]],
                "not_independent": [a["panellist"] for a in answers
                                    if not a["independent"]],
                # The one structural fact about anchoring a register can hold:
                # whether the answers arrived far enough apart that a later one
                # could have been shaped by an earlier.
                "answered_over_seconds": round(
                    max(a["recorded_at"] for a in answers)
                    - min(a["recorded_at"] for a in answers), 1),
            })
        return out

    def convergence(self, reference: str) -> Dict[str, Any]:
        """Whether the spread narrowed — and why that is all it can say."""
        rounds = self.rounds(reference)
        spreads = [r["relative_spread"] for r in rounds
                   if r["relative_spread"] is not None]
        narrowed = (len(spreads) >= 2 and spreads[-1] < spreads[0])
        wide = bool(spreads) and spreads[-1] is not None \
            and spreads[-1] > WIDE_SPREAD
        elicitation = self.require(reference)
        return {
            "reference": reference, "method": elicitation["method"],
            "rounds": len(rounds),
            "spreads": spreads, "narrowed": narrowed, "still_wide": wide,
            "explains_why": False,
            "detail": self._convergence_detail(elicitation, rounds, spreads,
                                               narrowed, wide),
        }

    @staticmethod
    def _convergence_detail(elicitation, rounds, spreads, narrowed, wide) -> str:
        if len(rounds) < 2:
            return ("one round, so there is nothing to converge from. A single "
                    "round is a snapshot of the panel's priors and is worth "
                    "reporting as one")
        out = (f"the relative spread moved from {spreads[0]:.2f} to "
               f"{spreads[-1]:.2f} over {len(rounds)} round(s)")
        out += (". It narrowed" if narrowed else ". It did not narrow")
        out += (f" — and this cannot say why. A panel that converged because "
                f"the most senior person answered first is indistinguishable, "
                f"in the numbers, from one that converged on the evidence. The "
                f"method was **{elicitation['method']}**, which is recorded "
                f"precisely so that a workshop's spread is not read like a "
                f"Delphi's")
        if wide:
            out += (f". The final spread is still above {WIDE_SPREAD:.0%} of "
                    f"the median, which is a disagreement rather than a range: "
                    f"a parameter set carrying it should carry the dissent too")
        gaps = [r["answered_over_seconds"] for r in rounds]
        if gaps and max(gaps) > 3600:
            out += (". Responses within a round arrived up to "
                    f"{max(gaps) / 3600:.1f} hours apart, so a later answer "
                    f"could have been shaped by an earlier — the one "
                    f"structural fact about anchoring this register can hold")
        return out

    def read(self, reference: str) -> Dict[str, Any]:
        elicitation = self.require(reference)
        rounds = self.rounds(reference)
        latest = rounds[-1] if rounds else None
        conflicted = (latest or {}).get("not_independent") or []
        return {
            **elicitation, "rounds": rounds,
            "convergence": self.convergence(reference),
            "dissent": (latest or {}).get("dissenters") or [],
            "not_independent": conflicted,
            "share_not_independent": (
                round(len(conflicted) / latest["answered"], 3)
                if latest and latest["answered"] else None),
            "detail": self._detail(elicitation, rounds, latest, conflicted),
        }

    @staticmethod
    def _detail(elicitation, rounds, latest, conflicted) -> str:
        if not rounds:
            return (f"{len(elicitation['panel'])} panellist(s) convened and "
                    f"nobody has answered yet")
        out = (f"round {elicitation['round']}, {latest['answered']} of "
               f"{latest['of']} answered, median {latest['median']}"
               + (f" {elicitation['units']}" if elicitation["units"] else "")
               + f", spread {latest['spread']}")
        if latest["dissenters"]:
            out += (f". {len(latest['dissenters'])} dissent(s) recorded and "
                    f"they travel with the number: a final weight whose dissent "
                    f"nobody can find is a weight that looks unanimous, and the "
                    f"firm relying on it does not know it is relying on a "
                    f"majority")
        if conflicted:
            out += (f". {len(conflicted)} panellist(s) are not independent of "
                    f"this model. Recorded rather than refused — in a small "
                    f"firm the only person who genuinely understands the model "
                    f"is often the person who built it, and refusing would push "
                    f"the elicitation off the platform entirely")
        if elicitation["state"] == CONCLUDED:
            out += (f". Concluded at {elicitation['final_value']} by "
                    f"{elicitation['concluded_by']}")
        return out

    def require(self, reference: str) -> Dict[str, Any]:
        row = self.elicitations.one(reference=reference)
        if not row:
            raise ParameterError("unknown_elicitation",
                                 f"no elicitation '{reference}'",
                                 "list the elicitations")
        return row

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every elicitation, widest disagreement first."""
        rows = [self.read(e["reference"]) for e in self.elicitations.many()]
        rows.sort(key=lambda r: -(r["convergence"]["spreads"][-1]
                                  if r["convergence"]["spreads"] else 0.0))
        with_dissent = [r["reference"] for r in rows if r["dissent"]]
        conflicted = [r["reference"] for r in rows if r["not_independent"]]
        wide = [r["reference"] for r in rows
                if r["convergence"]["still_wide"]]
        return {
            "elicitations": rows, "count": len(rows),
            "open": sum(1 for r in rows if r["state"] == OPEN),
            "with_dissent": with_dissent,
            "with_conflicted_panellists": conflicted,
            "still_wide": wide,
            "detail": (
                f"{len(rows)} elicitation(s)"
                + (f", {len(wide)} of which ended with the panel still "
                   f"disagreeing by more than {WIDE_SPREAD:.0%} of the median — "
                   f"which is a disagreement rather than a range" if wide else "")
                + (f". {len(with_dissent)} carry a recorded dissent"
                   if with_dissent else "")
                if rows else
                "no elicitation is recorded. A T7 parameter with no elicitation "
                "behind it is a number somebody chose, and the register cannot "
                "tell that from one a panel agreed"),
        }

    @staticmethod
    def methods() -> Dict[str, Any]:
        return {
            "methods": [{"method": k, "means": v} for k, v in METHODS.items()],
            "minimum_panel": MINIMUM_PANEL, "wide_spread": WIDE_SPREAD,
            "explains_convergence": False,
            "detail": ("the value of an elicitation is the spread, not the "
                       "number. Responses are recorded per round and never "
                       "overwritten, because a response revised in place erases "
                       "the movement between rounds and the movement is the "
                       "only thing convergence can be measured from"),
        }
