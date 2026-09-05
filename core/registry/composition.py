"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

How one model stands to another.

Features compose. Featuresets compose. Models did not, and the absence ran
deeper than a missing table: without model-to-model edges there is no blast
radius, no composite warrant, and no way to compute the one result the whole
account is proudest of — that aggregate risk cannot be compositional, with the
copy map as the obstruction. That theorem is *about* shared dependency, and
shared dependency was not representable.

**Two relations, deliberately distinct.**

  ``derives_from`` — B was built FROM A. A variant for another book, a
  challenger sharing A's shape, a recalibration for a different portfolio. B is
  its own model with its own versions and its own approvals; the edge records
  where it came from, and nothing propagates along it automatically.

  ``input_to`` — A's OUTPUT is read as an input by B. A discount curve into a
  pricer, a PD model into an ECL stack. This is the network edge, and it is the
  one that propagates: change A and B's answer changes.

  It was called ``feeds``, and that was a bad name in a bank. A *feed* here means
  a data feed — market data, a reference file, a nightly drop — so ``A feeds B``
  read as though MAYA consumed or produced one. **It does neither.** MAYA never
  moves data and never runs a model; the edge is a statement about two entries in
  the register, and the wire it describes is one somebody else's engine carries.
  ``feeds`` is still accepted on the way in and stored as ``input_to``.

Conflating them is the mistake this file exists to prevent. "What did we base
this on" and "what breaks if this changes" are different questions with
different answers, and a challenger counted as a dependency inflates every blast
radius it appears in.

**Edges are between MODELS, not versions.** A version-level graph would have to
be rebuilt on every release and would answer a question nobody asks. The estate
question is which models depend on this one, not which builds did.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.domain.lattice import refines
from core.domain.schemas import Field, Schema
from core.registry.common import RegistryError

logger = get_logger(__name__)

DERIVES_FROM = "derives_from"
INPUT_TO = "input_to"
CHALLENGER_OF = "challenger_of"
BENCHMARK_FOR = "benchmark_for"
CALIBRATED_BY = "calibrated_by"

KINDS: Tuple[str, ...] = (DERIVES_FROM, INPUT_TO, CHALLENGER_OF, BENCHMARK_FOR,
                          CALIBRATED_BY)

#: `feeds` was the original name and it was a bad one. In a bank a *feed* is a
#: data feed — market data, a reference file, a nightly drop — so `A feeds B`
#: reads as though MAYA consumed or produced one. It does neither: it never
#: moves data and never runs a model. What the edge records is that **A's
#: OUTPUT is an input to B**, which is what `input_to` says and what `feeds`
#: only implied.
#:
#: Accepted on the way in and stored as the new name, so an existing caller and
#: an existing row both keep working. Not published in `KINDS`: a vocabulary
#: that offers two words for one relation invites somebody to think they mean
#: different things.
ALIASES: Dict[str, str] = {"feeds": INPUT_TO}


def canonical(kind: str) -> str:
    """The stored name for a relation, resolving a legacy spelling."""
    return ALIASES.get(kind, kind)

KIND_MEANING: Dict[str, str] = {
    DERIVES_FROM: "built from it: a variant, a recalibration for another book, "
                  "a model that started as a copy. Lineage, not dependency",
    INPUT_TO: "its output is read as an input by that model. THIS is the one "
              "that propagates: change the source and the target's answer "
              "changes. It is a relation between two MODELS in the register — "
              "MAYA neither moves the data nor runs either end",
    CHALLENGER_OF: "built to argue with it. Deliberately not a dependency — a "
                   "challenger that counted as one would inflate every blast "
                   "radius it appeared in",
    BENCHMARK_FOR: "used as a reference point to judge it against",
    CALIBRATED_BY: "its parameters are solved by that model or procedure",
}

# Only this relation carries consequence downstream. The others record how
# somebody thinks about a model; this one records what a change does to it.
PROPAGATING: frozenset = frozenset({INPUT_TO, CALIBRATED_BY})

# Relations that are COMPOSITION rather than commentary. An `input_to` edge
# asserts that what one model produces arrives where another reads it, which is
# a claim about types and is checked as one. `calibrated_by` propagates but does
# not compose: a calibration procedure solves parameters rather than handing an
# output to an input, so there is no wire to type-check.
COMPOSING: frozenset = frozenset({INPUT_TO})

# A dependency graph deeper than this in a model estate is either wrong or is
# something nobody can reason about. Bounded so a cycle introduced by two edges
# added independently cannot make a traversal run forever.
MAX_DEPTH = 20


class ModelComposition:
    """The edges between models, and what they let you ask."""

    def __init__(self, edges, catalogue, evidence: EvidenceEngine,
                 versions=None):
        self.edges, self.catalogue, self.evidence = edges, catalogue, evidence
        # Optional so a register with no versions still records edges. Where it
        # is wired, an `input_to` edge is type-checked rather than believed.
        self.versions = versions

    # ----------------------------------------------------------------- relate
    def relate(self, from_urn: str, to_urn: str, kind: str, note: str = "",
               actor: str = "system") -> Dict[str, Any]:
        """Record that one model stands to another in this way.

        Refused rather than accepted-and-ignored in four cases, because each of
        them is somebody believing a relationship exists when it does not: a
        model related to itself, an unknown kind, either end unknown to the
        register, and a cycle in a propagating relation.
        """
        kind = canonical(kind)
        if kind not in KINDS:
            raise RegistryError(
                f"'{kind}' is not a relation between models; use one of "
                f"{', '.join(KINDS)}")
        source, target = self.catalogue.require(from_urn), self.catalogue.require(to_urn)
        if source["id"] == target["id"]:
            raise RegistryError(
                f"a model cannot stand in the '{kind}' relation to itself; the "
                f"edge would say nothing and "
                f"would make every traversal that reached it run forever")
        if self.edges.one(from_model=source["id"], to_model=target["id"],
                          kind=kind):
            raise RegistryError(
                f"{from_urn} is already recorded as '{kind}' {to_urn}; recording "
                f"it twice would "
                f"make a count of dependencies disagree with the graph")
        if kind in PROPAGATING and self._would_cycle(source["id"], target["id"]):
            raise RegistryError(
                f"{from_urn} as an input to {to_urn} would close a cycle: {to_urn} "
                f"already reaches {from_urn}. A model whose output is its own "
                f"input has no defined value, and a blast radius over it does "
                f"not terminate")

        # An `input_to` edge is a CLAIM ABOUT TYPES: whatever the source produces
        # arrives where the target reads. Recorded and never checked, it was a
        # drawing — a blast radius over edges nobody validated. Checked, it is
        # composition, and a composite has a derived schema rather than a
        # declared one.
        if kind in COMPOSING:
            self._check_composes(from_urn, to_urn, source, target)

        row = {"from_model": source["id"], "to_model": target["id"], "kind": kind,
               "note": note, "created_by": actor, "created_at": time.time()}
        self.edges.add(row)
        self.evidence.append("model_related", "model", target["id"],
                             {"from": source["urn"], "to": target["urn"],
                              "kind": kind, "note": note}, actor=actor)
        logger.info("recorded %s %s %s", from_urn, kind, to_urn)
        return {**row, "from_urn": source["urn"], "to_urn": target["urn"],
                "means": KIND_MEANING[kind]}

    # ------------------------------------------------------------ composition
    def _check_composes(self, from_urn: str, to_urn: str,
                        source: Dict[str, Any], target: Dict[str, Any]) -> None:
        """Refuse an `input_to` edge whose ends do not compose.

        The order is the platform's one order (`core.domain.lattice.refines`),
        the same comparison `L-12` makes at an alias move and `L-W10` makes at
        warrant issuance. What the source *provides* must stand in for what the
        target *reads*; extra outputs are fine and simply unread, a missing one
        is a wire to nowhere.

        Checked against the latest version at each end, and only where both ends
        have one. A model with no version yet is a model whose schema is not
        decided, and refusing an edge for a schema that does not exist would
        make the register harder to build than the estate is to describe.
        """
        if self.versions is None:
            return
        producing = self._latest(source["id"])
        consuming = self._latest(target["id"])
        if producing is None or consuming is None:
            logger.info("input_to %s -> %s recorded without a type check: %s has "
                        "no version yet", from_urn, to_urn,
                        from_urn if producing is None else to_urn)
            return

        outcome = refines(
            schema_of_fields(producing.get("output_schema") or []),
            schema_of_fields(consuming.get("input_schema") or []))
        if outcome.holds:
            return
        raise RegistryError(
            f"{from_urn} does not compose with {to_urn}: what it produces "
            f"{outcome.reason()}. An `input_to` edge asserts that the output arrives "
            f"where the input is read, and an edge that does not type-check is "
            f"a wire to nowhere — the blast radius would follow it and the "
            f"composite would have no defined schema")

    def _latest(self, model_id: str) -> Optional[Dict[str, Any]]:
        rows = self.versions.many(model_id=model_id)
        return rows[-1] if rows else None

    def composite_schema(self, from_urn: str, to_urn: str) -> Dict[str, Any]:
        """The type of `to ∘ from`: the source's inputs, the target's outputs.

        Derived rather than declared, which is the whole reason to type the edge
        — a composite whose schema somebody wrote down is a composite that can
        disagree with its parts.
        """
        source = self.catalogue.require(from_urn)
        target = self.catalogue.require(to_urn)
        producing, consuming = self._latest(source["id"]), self._latest(target["id"])
        if producing is None or consuming is None:
            raise RegistryError(
                "a composite has no schema until both ends have a version")
        return {"composite": f"{to_urn} ∘ {from_urn}",
                "input_schema": producing.get("input_schema") or [],
                "output_schema": consuming.get("output_schema") or [],
                "detail": "the source's inputs and the target's outputs; the "
                          "wire between them type-checks or the edge does not "
                          "exist"}

    def unrelate(self, from_urn: str, to_urn: str, kind: str,
                 reason: str, actor: str = "system") -> Dict[str, Any]:
        """Remove an edge, with a reason. An edge deleted silently is a
        dependency somebody stopped believing in without saying why."""
        if not reason:
            raise RegistryError(
                "removing a relation needs a reason: an edge that disappears "
                "without one is a dependency somebody stopped believing in and "
                "nobody can ask about")
        # Through the alias, like `relate`. Without it an edge created as
        # `feeds` — the spelling the alias exists to keep working — is stored as
        # `input_to` and cannot be removed by the name it was created with,
        # which is the worst possible shape for a compatibility alias.
        kind = canonical(kind)
        source, target = self.catalogue.require(from_urn), self.catalogue.require(to_urn)
        removed = self.edges.remove(from_model=source["id"],
                                    to_model=target["id"], kind=kind)
        if not removed:
            raise RegistryError(f"{from_urn} does not {kind} {to_urn}")
        self.evidence.append("model_unrelated", "model", target["id"],
                             {"from": source["urn"], "to": target["urn"],
                              "kind": kind, "reason": reason}, actor=actor)
        return {"removed": removed, "kind": kind, "reason": reason}

    # ------------------------------------------------------------------ reads
    def edges_of(self, urn: str) -> Dict[str, Any]:
        """Everything attached to this model, in both directions."""
        model = self.catalogue.require(urn)
        return {
            "urn": model["urn"],
            "upstream": [self._describe(e, "from_model")
                         for e in self.edges.many(to_model=model["id"])],
            "downstream": [self._describe(e, "to_model")
                           for e in self.edges.many(from_model=model["id"])],
        }

    def _describe(self, edge: Dict[str, Any], side: str) -> Dict[str, Any]:
        other = self.catalogue.by_id(edge[side]) or {}
        return {"kind": edge["kind"], "means": KIND_MEANING.get(edge["kind"], ""),
                "urn": other.get("urn"), "name": other.get("name"),
                "tier": other.get("tier"), "status": other.get("status"),
                "note": edge.get("note", ""), "propagates": edge["kind"] in PROPAGATING}

    def blast_radius(self, urn: str) -> Dict[str, Any]:
        """Every model a change here reaches, and how far away each one is.

        Only propagating relations are followed. A challenger is not downstream
        of the model it argues with, and counting it would inflate the answer
        precisely where the answer is used to decide how much care a change
        needs.
        """
        model = self.catalogue.require(urn)
        reached: Dict[str, int] = {}
        frontier, depth = [model["id"]], 0
        while frontier and depth < MAX_DEPTH:
            depth += 1
            nxt = []
            for node in frontier:
                for edge in self.edges.many(from_model=node):
                    if edge["kind"] not in PROPAGATING:
                        continue
                    other = edge["to_model"]
                    if other in reached or other == model["id"]:
                        continue
                    reached[other] = depth
                    nxt.append(other)
            frontier = nxt
        rows = []
        for model_id, distance in sorted(reached.items(), key=lambda kv: kv[1]):
            row = self.catalogue.by_id(model_id) or {}
            rows.append({"urn": row.get("urn"), "name": row.get("name"),
                         "tier": row.get("tier"), "status": row.get("status"),
                         "distance": distance})
        tiers = [r["tier"] for r in rows if r["tier"] is not None]
        return {
            "urn": model["urn"], "reaches": rows, "count": len(rows),
            "worst_tier": min(tiers) if tiers else None,
            "detail": self._radius_detail(model, rows, tiers),
        }

    @staticmethod
    def _radius_detail(model: Dict[str, Any], rows: List[Dict[str, Any]],
                       tiers: List[int]) -> str:
        if not rows:
            return ("nothing consumes this model's output, so a change to it "
                    "reaches only itself")
        worst = f", the most material at tier {min(tiers)}" if tiers else ""
        return (f"a change here reaches {len(rows)} model(s){worst}. that is "
                f"what the change process has to cover, and it is computed from "
                f"the graph rather than remembered")

    def upstream_of(self, urn: str) -> List[str]:
        """Every model this one depends on, transitively. The set a shared
        dependency is looked for in."""
        model = self.catalogue.require(urn)
        seen: Set[str] = set()
        frontier, depth = [model["id"]], 0
        while frontier and depth < MAX_DEPTH:
            depth += 1
            nxt = []
            for node in frontier:
                for edge in self.edges.many(to_model=node):
                    if edge["kind"] not in PROPAGATING:
                        continue
                    if edge["from_model"] in seen:
                        continue
                    seen.add(edge["from_model"])
                    nxt.append(edge["from_model"])
            frontier = nxt
        return sorted(seen)

    def shared_dependencies(self, urns: Sequence[str]) -> Dict[str, Any]:
        """What two or more of these models both depend on.

        This is the obstruction, made computable. Aggregate risk cannot be
        compositional because a network that *copies* a dependency is not the
        same as one that duplicates it, and the difference is exactly the set
        below. Supervisors ask about "common dependencies and shared
        assumptions" in prose; this is that question with an answer.
        """
        by_model = {urn: set(self.upstream_of(urn)) for urn in urns}
        counts: Dict[str, List[str]] = {}
        for urn, ups in by_model.items():
            for dependency in ups:
                counts.setdefault(dependency, []).append(urn)
        shared = []
        for model_id, dependents in counts.items():
            if len(dependents) < 2:
                continue
            row = self.catalogue.by_id(model_id) or {}
            shared.append({"urn": row.get("urn"), "name": row.get("name"),
                           "tier": row.get("tier"),
                           "relied_on_by": sorted(dependents),
                           "count": len(dependents)})
        shared.sort(key=lambda r: (-r["count"], r["urn"] or ""))
        return {
            "of": list(urns), "shared": shared,
            "detail": self._shared_detail(urns, shared),
        }

    @staticmethod
    def _shared_detail(urns: Sequence[str], shared: List[Dict[str, Any]]) -> str:
        if not shared:
            return (f"the {len(urns)} models named have no upstream in common, "
                    f"so their risks do not interact through a shared input")
        worst = shared[0]
        return (f"{len(shared)} shared dependenc(y/ies). {worst['urn']} is relied "
                f"on by {worst['count']} of them, so a fault there is not "
                f"{worst['count']} independent faults — which is the reason an "
                f"aggregate risk assignment cannot simply add up")

    # ------------------------------------------------------------------ parts
    def _would_cycle(self, source_id: str, target_id: str) -> bool:
        """Whether target already reaches source through propagating edges."""
        frontier, seen, depth = [target_id], {target_id}, 0
        while frontier and depth < MAX_DEPTH:
            depth += 1
            nxt = []
            for node in frontier:
                for edge in self.edges.many(from_model=node):
                    if edge["kind"] not in PROPAGATING:
                        continue
                    if edge["to_model"] == source_id:
                        return True
                    if edge["to_model"] not in seen:
                        seen.add(edge["to_model"])
                        nxt.append(edge["to_model"])
            frontier = nxt
        return False

    @staticmethod
    def describe() -> Dict[str, Any]:
        """The relations, what each means, and what MAYA does not do.

        The last part is published rather than assumed. `input_to` was once
        called `feeds`, and a reader in a bank hears *data feed* — so the
        vocabulary says out loud that MAYA moves no data and runs no model, and
        that an edge is a statement about two entries in the register.
        """
        return {
            "relations": [{"kind": k, "means": KIND_MEANING[k],
                           "propagates": k in PROPAGATING,
                           "composes": k in COMPOSING} for k in KINDS],
            "accepts": ALIASES,
            "detail": "these are relations between MODELS in the register. MAYA "
                      "neither consumes nor produces data feeds: it moves no "
                      "data and runs no model, and an `input_to` edge asserts "
                      "that one model's output is read as an input by another — "
                      "over a wire somebody else's engine carries",
        }


def schema_of_fields(fields) -> Schema:
    """A stored input/output schema list as a `Schema`, for the order."""
    return Schema(tuple(
        Field(f["name"], f.get("dtype", "numeric"), bool(f.get("nullable", False)),
              f.get("minimum"), f.get("maximum"))
        for f in fields or []))
