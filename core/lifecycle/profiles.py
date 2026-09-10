"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model of this class, at this tier, owes before each lifecycle move.

The requirement asks for configurable state machines per model class. What is
built here is deliberately narrower, and the narrowing is the design rather than
a shortfall, so it is stated plainly rather than left to be discovered:

**The states and transitions stay one machine.** Every law this platform rests
on is a statement about that graph — `L-1` is a reachability proof over exactly
two initial states, mutability is a property of the state set, and the
immutability of an attested record is the reason amendments exist at all. Nine
graphs would mean nine reachability proofs, nine answers to *can this be
changed*, and a supervisor who has to ask which machine a model is on before
reading its status. A register whose vocabulary varies by model is a register
nobody can read across.

**What genuinely varies is what each move COSTS.** Nobody wants a different
state graph for a T0 pricer; they want *a T3 model needs an independent review
on file before it can be attested, and a T0 does not*. That is a guard on a
transition, not a different transition — and the fibres already declare it,
because `L-15` makes each class say which evidence kinds it owes.

Which is the second thing this module is for. `Fibre.evidence` has been
declared for all nine classes since the fibres were written and, until now, had
**no consumer anywhere in the platform** — nine classes each stating what they
owe, and nothing that ever read the statement. Attachments were checked for
existence and never against the obligation of the class that needed them.

So a profile is the join of three things the register already holds: the
**class** says which evidence kinds must be on file, the **tier** says how many
signatures a move takes and how long it may sit before somebody should ask, and
the shared machine says which moves exist at all.

**The SLA half is the one nothing else does.** A record that has been
`submitted` for four months is not blocked by any control here — submission
succeeded, every gate passed, and nothing is watching the clock. That is how a
governance queue becomes a place where things go to wait, and the only reason
it is invisible is that no state carries an expected duration. Note where the
duration is measured from: the **evidence chain**, not a `status_changed_at`
column. The chain already records every transition with a timestamp, and a
column would be a second copy of that which drifts from it the first time
anything writes a status without recording why.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.log import get_logger
from core.lifecycle.states import BY_NAME, STATES, TRANSITIONS, allowed_from
#: The evidence kinds that record a lifecycle move. Imported by name rather
#: than reconstructed, so this fold and the as-at projection cannot disagree
#: about what counts as a transition.
from core.registry.asat import LIFECYCLE_KINDS

logger = get_logger(__name__)

DAY = 86400.0

#: How many signatures a move takes, by tier. The same shape as everywhere else
#: in this platform: what a model IS decides the questions, and what rides on it
#: decides how many people have to agree on the answers.
SIGNATURES: Dict[int, int] = {1: 2, 2: 2, 3: 1, 4: 1}

#: The moves a signature count applies to. Returning a record and opening an
#: amendment are one person's act by design — requiring a quorum to send
#: something BACK is how a review queue seizes up.
SIGNED_MOVES: Tuple[str, ...] = ("approve", "attest")

#: How long a record may sit mid-move before somebody should ask, by tier. Not
#: a refusal — a governance queue is allowed to have a queue — but a number,
#: because a queue with no expected duration is one nobody can tell is stuck.
#: Only the transient states appear: `attested` and `retired` are where a record
#: is supposed to rest, and putting a clock on them would report every model in
#: force as overdue.
SLA_DAYS: Dict[str, Dict[int, float]] = {
    "submitted": {1: 10.0, 2: 20.0, 3: 30.0, 4: 45.0},
    "approved": {1: 5.0, 2: 10.0, 3: 20.0, 4: 30.0},
    "amending": {1: 30.0, 2: 45.0, 3: 60.0, 4: 90.0},
}

#: The transitions whose guard is evidence rather than authority. Attesting is
#: the moment a record becomes immutable and in force, so it is the moment the
#: evidence has to be there. Checking earlier would block a draft for lacking a
#: validation report nobody could have written yet — and a control that fires
#: before it can be satisfied teaches everybody to route around it.
EVIDENCE_GUARDED: Tuple[str, ...] = ("attest",)


class LifecycleProfiles:
    """The reference lifecycle for each class, and what a move costs."""

    def __init__(self, registry, fibres, attachments=None, evidence=None):
        self.registry, self.fibres = registry, fibres
        # Optional, both of them. Without attachments a profile still says what
        # a class owes and simply cannot say whether this model holds it;
        # without the chain the SLA cannot say when a record entered its state.
        # Each degrades to silence rather than to a confident wrong answer.
        self.attachments, self.evidence = attachments, evidence

    # --------------------------------------------------------------- profile
    def for_class(self, trainability: str,
                  tier: Optional[int] = None) -> Dict[str, Any]:
        """The reference lifecycle for one class — `FR-LC-002`, T0 through T8."""
        from core.lifecycle.common import LifecycleError

        fibre = self.fibres.get(trainability)
        if fibre is None:
            raise LifecycleError(
                "no_fibre",
                f"no fibre is registered for class {trainability!r}, so nothing "
                f"can say what its lifecycle owes",
                "a class with no fibre cannot state its obligations; see L-15")
        rank = self._rank(tier)
        moves = []
        for rule in TRANSITIONS:
            guarded = rule.name in EVIDENCE_GUARDED
            moves.append({
                "transition": rule.name,
                "from": list(rule.sources), "to": rule.target,
                "permission": rule.permission,
                "signatures": (SIGNATURES.get(rank, 1)
                               if rule.name in SIGNED_MOVES else 1),
                "required_evidence": list(fibre.evidence) if guarded else [],
                "note": rule.note,
            })
        return {
            "trainability_class": trainability, "class_name": fibre.label,
            "tier": tier,
            # The states this class may occupy, from the fibre. Every class
            # admits every state today, and that is reported as an invariant
            # rather than hidden as an absence — a class that could not be
            # retired would be a real difference and `L-15` has room for it.
            "states": list(fibre.lifecycle),
            "shares_the_state_graph": list(fibre.lifecycle) == list(STATES),
            "transitions": moves,
            "sla_days": {state: table.get(rank)
                         for state, table in SLA_DAYS.items()},
            "detail": (
                f"{trainability} ({fibre.label})"
                + (f" at tier {tier}" if tier is not None else
                   " at no stated tier, so the lightest quorum is shown")
                + f": the same state graph as every other class, with "
                  f"{len(fibre.evidence)} evidence kind(s) required before it "
                  f"can be attested and {SIGNATURES.get(rank, 1)} signature(s) "
                  f"on approval and attestation"),
        }

    def reference(self) -> Dict[str, Any]:
        """Every class's reference lifecycle, side by side — `FR-LC-002`."""
        out = []
        for trainability in sorted(self.fibres.classes()):
            profile = self.for_class(trainability)
            out.append({
                "trainability_class": trainability,
                "class_name": profile["class_name"],
                "states": profile["states"],
                "required_before_attesting": next(
                    (m["required_evidence"] for m in profile["transitions"]
                     if m["transition"] == "attest"), []),
            })
        varies = len({tuple(r["required_before_attesting"]) for r in out})
        return {
            "lifecycles": out, "count": len(out),
            "distinct_evidence_sets": varies,
            "detail": (f"one state graph and {varies} distinct sets of "
                       f"obligations across {len(out)} classes. Nine graphs "
                       f"would mean nine reachability proofs, nine answers to "
                       f"*can this be changed*, and a supervisor who has to ask "
                       f"which machine a model is on before reading its status"),
        }

    # ----------------------------------------------------------------- check
    def check(self, urn: str, transition: str) -> Dict[str, Any]:
        """Whether this model can make this move, and what is missing if not."""
        from core.lifecycle.common import LifecycleError

        model = self.registry.require(urn)
        trainability = self._class_of(urn)
        if not trainability:
            raise LifecycleError(
                "no_class",
                "this model has no version, so it has no trainability class "
                "and nothing can say what its lifecycle owes",
                "register a version first — the class is derived from it")
        if transition not in BY_NAME:
            raise LifecycleError(
                "unknown_transition",
                f"'{transition}' is not a transition on this machine",
                f"one of {', '.join(sorted(BY_NAME))}")

        profile = self.for_class(trainability, model.get("tier"))
        move = next(m for m in profile["transitions"]
                    if m["transition"] == transition)
        required = move["required_evidence"]
        accepted, on_file = self._held(model["id"])

        missing = [k for k in required if k not in on_file]
        # Present but nobody has reviewed it. A distinct answer from missing:
        # the document exists and the obligation is not yet discharged, and
        # collapsing the two sends somebody to write a report that is already
        # written and sitting in a queue.
        unreviewed = [k for k in required
                      if k in on_file and k not in accepted]
        return {
            "urn": urn, "transition": transition,
            "trainability_class": trainability, "tier": model.get("tier"),
            "status": model.get("status"),
            "legal_from_here": transition in self.moves_from(
                model.get("status") or ""),
            "required_evidence": required,
            "on_file": sorted(on_file), "accepted": sorted(accepted),
            "missing_evidence": missing, "awaiting_review": unreviewed,
            "signatures_required": move["signatures"],
            "ready": not missing and not unreviewed,
            "detail": self._check_detail(transition, trainability, required,
                                         missing, unreviewed),
        }

    @staticmethod
    def _check_detail(transition: str, trainability: str,
                      required: List[str], missing: List[str],
                      unreviewed: List[str]) -> str:
        if not required:
            return (f"'{transition}' carries no evidence guard — what it takes "
                    f"is authority, not documents")
        if missing:
            return (f"'{transition}' needs {', '.join(missing)}, which a "
                    f"{trainability} model owes and this one does not hold")
        if unreviewed:
            return (f"{', '.join(unreviewed)} is on file but nobody has "
                    f"accepted it. The obligation is not discharged by a "
                    f"document arriving — that is what review is for")
        return (f"every evidence kind a {trainability} model owes is on file "
                f"and accepted")

    def _held(self, model_id: str) -> Tuple[set, set]:
        """Kinds accepted, and kinds on file at all."""
        if self.attachments is None:
            return set(), set()
        rows = self.attachments.for_model(model_id)
        on_file = {r.get("kind") for r in rows}
        accepted = {r.get("kind") for r in rows if r.get("state") == "accepted"}
        return accepted, on_file

    def _class_of(self, urn: str) -> Optional[str]:
        versions = self.registry.versions(urn)
        return versions[-1].get("trainability_class") if versions else None

    # ------------------------------------------------------------------- sla
    def entered_state_at(self, model: Dict[str, Any]) -> Optional[float]:
        """When this record entered the state it is in, from the chain.

        Not from a column. The chain already records every transition with a
        timestamp and a `to`, and a `status_changed_at` column would be a second
        copy of that — one which drifts from the chain the first time anything
        writes a status without recording why it changed.
        """
        if self.evidence is None:
            return None
        status = model.get("status")
        moves = [n for n in self.evidence.for_subject(model["id"])
                 if n.get("kind") in LIFECYCLE_KINDS]
        for node in reversed(moves):
            if (node.get("payload") or {}).get("to") == status:
                return node.get("recorded_at")
        # A record in a state the chain never moved it into: a `draft` that has
        # never gone anywhere, or an import that began `baselined`. Registration
        # is when it entered, and neither has an SLA anyway.
        return None

    def stalled(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Records that have been mid-move longer than their tier allows.

        The half nothing else does. A record `submitted` for four months is not
        blocked by any control here — submission succeeded, every gate passed,
        and nothing watches the clock. That is how a governance queue becomes a
        place things go to wait, and the only reason it is invisible is that no
        state carries an expected duration.
        """
        moment = now if now is not None else time.time()
        out, unknown = [], []
        for model in self.registry.list():
            status = model.get("status")
            table = SLA_DAYS.get(status or "")
            if not table:
                continue
            since = self.entered_state_at(model)
            if since is None:
                unknown.append({"urn": model.get("urn"), "status": status})
                continue
            limit = table.get(self._rank(model.get("tier")))
            days = (moment - since) / DAY
            if limit is None or days <= limit:
                continue
            out.append({"urn": model.get("urn"), "status": status,
                        "tier": model.get("tier"), "owner": model.get("owner"),
                        "entered_state_at": since,
                        "days_in_state": round(days, 1), "limit_days": limit,
                        "days_over": round(days - limit, 1)})
        out.sort(key=lambda r: -r["days_over"])
        return {
            "stalled": out, "count": len(out),
            # Named rather than silently skipped: a record whose entry into its
            # own state is not on the chain is a gap in the chain, and reporting
            # zero stalled records while some could not be measured would be a
            # clean number covering an unclean one.
            "not_measurable": unknown,
            "detail": self._stalled_detail(out, unknown),
        }

    @staticmethod
    def _stalled_detail(out: List[Dict[str, Any]],
                        unknown: List[Dict[str, Any]]) -> str:
        if out:
            head = (f"{len(out)} record(s) have been mid-move longer than their "
                    f"tier allows, the worst by {out[0]['days_over']:.0f} days. "
                    f"None of this is refused — a governance queue is allowed "
                    f"to have a queue — but a queue with no expected duration "
                    f"is one nobody can tell is stuck")
        else:
            head = ("no record is sitting mid-move longer than its tier allows")
        if unknown:
            head += (f"; {len(unknown)} could not be measured, because nothing "
                     f"on the chain records them entering the state they are in")
        return head

    # --------------------------------------------------------------- shaping
    @staticmethod
    def _rank(tier: Optional[Any]) -> int:
        """A tier, or the lightest one. An untiered model is not a tier 1 model
        and saying so here would put a two-signature quorum on a record nobody
        has assessed — the tiering gate is what refuses that, not this."""
        if tier is None:
            return max(SIGNATURES)
        try:
            return int(tier)
        except (TypeError, ValueError):
            # A tier that is not a number is a register row somebody wrote
            # around the tiering engine, and the quiet fallback below would
            # hide it. Logged, because the profile it produces is the lightest
            # one and that is the wrong answer if the tier was meant to be 1.
            logger.warning("model carries a non-numeric tier %r; showing the "
                           "lightest quorum, which is not what a tier 1 record "
                           "owes", tier)
            return max(SIGNATURES)

    @staticmethod
    def moves_from(state: str) -> List[str]:
        """Every legal move out of a state, for a reader or a screen."""
        return [t.name for t in allowed_from(state)]
