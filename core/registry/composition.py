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

  ``feeds`` — A's OUTPUT is an input to B. A discount curve into a pricer, a PD
  model into an ECL stack. This is the network edge, and it is the one that
  propagates: change A and B's answer changes.

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
from core.registry.common import RegistryError

logger = get_logger(__name__)

DERIVES_FROM = "derives_from"
FEEDS = "feeds"
CHALLENGER_OF = "challenger_of"
BENCHMARK_FOR = "benchmark_for"
CALIBRATED_BY = "calibrated_by"

KINDS: Tuple[str, ...] = (DERIVES_FROM, FEEDS, CHALLENGER_OF, BENCHMARK_FOR,
                          CALIBRATED_BY)

KIND_MEANING: Dict[str, str] = {
    DERIVES_FROM: "built from it: a variant, a recalibration for another book, "
                  "a model that started as a copy. Lineage, not dependency",
    FEEDS: "its output is an input here. THIS is the one that propagates: "
           "change the source and this model's answer changes",
    CHALLENGER_OF: "built to argue with it. Deliberately not a dependency — a "
                   "challenger that counted as one would inflate every blast "
                   "radius it appeared in",
    BENCHMARK_FOR: "used as a reference point to judge it against",
    CALIBRATED_BY: "its parameters are solved by that model or procedure",
}

# Only this relation carries consequence downstream. The others record how
# somebody thinks about a model; this one records what a change does to it.
PROPAGATING: frozenset = frozenset({FEEDS, CALIBRATED_BY})

# A dependency graph deeper than this in a model estate is either wrong or is
# something nobody can reason about. Bounded so a cycle introduced by two edges
# added independently cannot make a traversal run forever.
MAX_DEPTH = 20


class ModelComposition:
    """The edges between models, and what they let you ask."""

    def __init__(self, edges, catalogue, evidence: EvidenceEngine):
        self.edges, self.catalogue, self.evidence = edges, catalogue, evidence

    # ----------------------------------------------------------------- relate
    def relate(self, from_urn: str, to_urn: str, kind: str, note: str = "",
               actor: str = "system") -> Dict[str, Any]:
        """Record that one model stands to another in this way.

        Refused rather than accepted-and-ignored in four cases, because each of
        them is somebody believing a relationship exists when it does not: a
        model related to itself, an unknown kind, either end unknown to the
        register, and a cycle in a propagating relation.
        """
        if kind not in KINDS:
            raise RegistryError(
                f"'{kind}' is not a relation between models; use one of "
                f"{', '.join(KINDS)}")
        source, target = self.catalogue.require(from_urn), self.catalogue.require(to_urn)
        if source["id"] == target["id"]:
            raise RegistryError(
                f"a model cannot {kind} itself; the edge would say nothing and "
                f"would make every traversal that reached it run forever")
        if self.edges.one(from_model=source["id"], to_model=target["id"],
                          kind=kind):
            raise RegistryError(
                f"{from_urn} already {kind} {to_urn}; recording it twice would "
                f"make a count of dependencies disagree with the graph")
        if kind in PROPAGATING and self._would_cycle(source["id"], target["id"]):
            raise RegistryError(
                f"{from_urn} feeding {to_urn} would close a cycle: {to_urn} "
                f"already reaches {from_urn}. A model whose output is its own "
                f"input has no defined value, and a blast radius over it does "
                f"not terminate")

        row = {"from_model": source["id"], "to_model": target["id"], "kind": kind,
               "note": note, "created_by": actor, "created_at": time.time()}
        self.edges.add(row)
        self.evidence.append("model_related", "model", target["id"],
                             {"from": source["urn"], "to": target["urn"],
                              "kind": kind, "note": note}, actor=actor)
        logger.info("recorded %s %s %s", from_urn, kind, to_urn)
        return {**row, "from_urn": source["urn"], "to_urn": target["urn"],
                "means": KIND_MEANING[kind]}

    def unrelate(self, from_urn: str, to_urn: str, kind: str,
                 reason: str, actor: str = "system") -> Dict[str, Any]:
        """Remove an edge, with a reason. An edge deleted silently is a
        dependency somebody stopped believing in without saying why."""
        if not reason:
            raise RegistryError(
                "removing a relation needs a reason: an edge that disappears "
                "without one is a dependency somebody stopped believing in and "
                "nobody can ask about")
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
    def describe() -> List[Dict[str, str]]:
        """The relations and what each one means."""
        return [{"kind": k, "means": KIND_MEANING[k],
                 "propagates": k in PROPAGATING} for k in KINDS]
