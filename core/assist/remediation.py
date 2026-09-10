"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The shortest way to a model being in force, and why the shortest way is a trap.

*What do I still have to do* is the question every model owner asks, and every
register answers it with a checklist — which is wrong in a specific way: a
checklist is a conjunction, and the real structure is a **disjunction of
conjunctions**. There is usually more than one route to a model being in force,
and the routes cost different amounts.

That makes this a shortest-path problem, and the semirings have been able to
solve it since the evidence engine was written. **The plan is computed, not
proposed.** `COST` — the tropical semiring, (min, +) — evaluated over the
derivation DAG *is* the cheapest total; `WHY` over the same DAG gives the
minimal sets of facts that would establish the claim. Nothing here asks a
language model what to do next, and nothing could: the answer is arithmetic,
and an arithmetic answer produced by a model is a worse version of the same
number.

**The cheapest path is very often the wrong advice**, and that is the finding
this module exists to make. A validation is expensive. A waiver of the
validation requirement is cheap. Both make the compliance predicate true, and a
shortest-path solver with no opinion about *kind* will recommend the waiver
every time — correctly, and disastrously. So every act is typed:

  * `produces_evidence` — the model becomes safer and the claim becomes true
  * `removes_the_requirement` — the claim becomes true and nothing about the
    model changes

**The plan is computed over the first kind only.** The second kind is computed
too, and reported beside it under its own heading, because a firm should be able
to see what the cheap route was and decide to take it deliberately rather than
find it by accident.

**Costs are declared, and how much of a total is defaulted is reported.** A
shortest path over guessed weights is a confident answer to a question nobody
asked, and the confidence is the dangerous part.

**Nothing is executed.** The requirement asks for an agent that executes the
plan; each step here names the route a person calls, and no capability in this
platform holds a credential permitting a governance transition (`FR-AI-002`).
An assistant that could conclude a validation to close out its own plan would
be the whole control structure defeated in one method.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.evidence.engine import Derivation
from core.evidence.semirings import COST, WHY
from core.log import get_logger

logger = get_logger(__name__)

PRODUCES, REMOVES = "produces_evidence", "removes_the_requirement"

#: A unit of effort, not a currency. Declared so that two plans are comparable
#: and so that nobody reads a total as a budget. Overridable from config,
#: because how expensive a validation is relative to a document is a fact about
#: a firm rather than about a platform.
DEFAULT_COSTS: Dict[str, float] = {
    "register_owner": 1.0,
    "create_version": 5.0,
    "assess_tier": 2.0,
    "conclude_validation": 40.0,
    "approve_version": 3.0,
    "define_monitor": 4.0,
    "compile_documentation": 8.0,
    "close_blocking_findings": 20.0,
    "attest": 2.0,
    # The cheap routes. Priced honestly — a waiver really is cheaper — and
    # excluded from the plan by KIND rather than by price, because pricing them
    # high would be lying about what they cost to make the arithmetic come out
    # right, and the next person to read the table would correct the lie.
    "waive_validation": 3.0,
    "waive_monitoring": 3.0,
    "retire_the_model": 1.0,
}

#: Every act: what it establishes, what it costs, what kind it is, and where it
#: is performed. Held as data so a plan can be read back against it.
ACTS: Dict[str, Dict[str, Any]] = {
    "register_owner": {
        "establishes": "owned", "kind": PRODUCES,
        "route": "POST /api/v1/models",
        "means": "name an accountable owner for the model"},
    "create_version": {
        "establishes": "has_version", "kind": PRODUCES,
        "route": "POST /api/v1/models/{name}/versions",
        "means": "register an immutable version with its kernel and contract"},
    "assess_tier": {
        "establishes": "tiered", "kind": PRODUCES,
        "route": "POST /api/v1/models/{name}/risk-assessment",
        "means": "record the risk assessment the tier is derived from"},
    "conclude_validation": {
        "establishes": "challenged", "kind": PRODUCES,
        "route": "POST /api/v1/validations/{id}/conclude",
        "means": "complete an independent validation and conclude it"},
    "approve_version": {
        # `signed_off` and not `approved`. Approval is an ACT with
        # preconditions, and collapsing the two made the act invisible to the
        # solver: `approved` had a derivation, so it was never a leaf, so
        # nothing ever costed the signature — and the plan omitted the one step
        # that cannot be delegated.
        "establishes": "signed_off", "kind": PRODUCES,
        "route": "POST /api/v1/models/{name}/versions/{semver}/approve",
        "means": "second-line approval of the version"},
    "define_monitor": {
        "establishes": "monitored", "kind": PRODUCES,
        "route": "POST /api/v1/monitors",
        "means": "define at least one active monitor on the model"},
    "compile_documentation": {
        "establishes": "documented", "kind": PRODUCES,
        "route": "POST /api/v1/documents",
        "means": "compile the model development document"},
    "close_blocking_findings": {
        "establishes": "unblocked", "kind": PRODUCES,
        "route": "POST /api/v1/findings/{id}/close",
        "means": "close every finding that refuses warrant resolution"},
    "attest": {
        "establishes": "attested", "kind": PRODUCES,
        "route": "POST /api/v1/models/{name}/attest",
        "means": "both halves of the attestation signed"},
    "waive_validation": {
        "establishes": "challenged", "kind": REMOVES,
        "route": "POST /api/v1/waivers",
        "means": "a waiver of the validation requirement, approved by the "
                 "second line and time-limited"},
    "waive_monitoring": {
        "establishes": "monitored", "kind": REMOVES,
        "route": "POST /api/v1/waivers",
        "means": "a waiver of the monitoring requirement"},
    "retire_the_model": {
        "establishes": "in_force", "kind": REMOVES,
        "route": "POST /api/v1/models/{name}/retire",
        "means": "retire it. The claim becomes vacuously satisfiable and the "
                 "model stops being used, which is sometimes the right answer "
                 "and never the one a plan should reach for first"},
}

#: The claim, as a disjunction of conjunctions. Published, because a plan
#: nobody can check against the structure it was computed over is a plan
#: nobody can argue with.
DERIVATIONS: Dict[str, Tuple[Tuple[str, ...], ...]] = {
    "in_force": (("approved", "unblocked", "monitored", "documented",
                  "attested"),),
    "approved": (("has_version", "challenged", "tiered", "owned",
                  "signed_off"),),
}

#: Facts with no derivation are leaves: something must be done to establish
#: them, and the act that does it is the one whose `establishes` names them.
LEAVES: Tuple[str, ...] = ("owned", "has_version", "tiered", "challenged",
                           "signed_off", "monitored", "documented",
                           "unblocked", "attested")


class RemediationPlanner:
    """Computes the cheapest route to a model being in force, over acts that help."""

    def __init__(self, registry, findings=None, validation=None,
                 monitoring=None, documents=None, lifecycle=None,
                 costs: Optional[Dict[str, float]] = None):
        self.registry, self.findings = registry, findings
        self.validation, self.monitoring = validation, monitoring
        self.documents, self.lifecycle = documents, lifecycle
        self.costs = {**DEFAULT_COSTS, **(costs or {})}
        self.declared = set(costs or {})

    # ------------------------------------------------------------------- plan
    def plan(self, urn: str, now: Optional[float] = None) -> Dict[str, Any]:
        """The shortest route, and the shorter one that would not help."""
        model = self.registry.require(urn)
        state = self.state(model, now)
        if state["in_force"]:
            return {"urn": urn, "state": state, "steps": [], "cost": 0.0,
                    "cheaper_but_hollow": self._hollow(state),
                    "defaulted_share": 0.0,
                    "detail": ("this model is already in force, so the plan is "
                               "empty. The cheap routes below exist anyway and "
                               "are worth knowing about")}

        honest = self._solve(state, kinds=(PRODUCES,))
        anything = self._solve(state, kinds=(PRODUCES, REMOVES))
        defaulted = sum(self.costs[s["act"]] for s in honest["steps"]
                        if s["act"] not in self.declared)
        logger.info("computed a %d-step plan for %s costing %.1f", 
                    len(honest["steps"]), urn, honest["cost"])
        return {
            "urn": urn, "state": state,
            "steps": honest["steps"], "cost": honest["cost"],
            "reachable": honest["reachable"],
            "cheaper_but_hollow": self._hollow(state),
            "cheapest_of_any_kind": anything["cost"],
            "defaulted_share": (round(defaulted / honest["cost"], 3)
                                if honest["cost"] else 0.0),
            "detail": self._detail(honest, anything, state, defaulted),
        }

    def _solve(self, state: Dict[str, Any],
               kinds: Sequence[str]) -> Dict[str, Any]:
        """Evaluate the DAG in the tropical semiring, over acts of these kinds."""
        acts = {k: a for k, a in ACTS.items() if a["kind"] in kinds}
        by_fact = _cheapest_act_per_fact(acts, self.costs)
        derivations = {k: Derivation(k, alts)
                       for k, alts in DERIVATIONS.items()}

        def valuation(fact: str) -> float:
            if state.get(fact):
                return COST.one                    # 0.0: already established
            act = by_fact.get(fact)
            return self.costs[act] if act else COST.zero   # inf: unreachable

        total = _evaluate("in_force", derivations, COST, valuation)
        support = _evaluate("in_force", derivations, WHY,
                            lambda fact: (WHY.one if state.get(fact)
                                          else {frozenset({fact})}))
        needed = _cheapest_support(support, state, by_fact, self.costs)
        return {
            "cost": total if total != COST.zero else None,
            "reachable": total != COST.zero,
            "steps": [{"act": by_fact[f], "establishes": f,
                       "cost": self.costs[by_fact[f]],
                       "cost_is_declared": by_fact[f] in self.declared,
                       **{k: v for k, v in ACTS[by_fact[f]].items()
                          if k in ("means", "route", "kind")}}
                      for f in needed if f in by_fact],
        }

    def _hollow(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Acts that would make the claim true and the model no safer."""
        return [{"act": key, "establishes": act["establishes"],
                 "cost": self.costs[key], "means": act["means"],
                 "route": act["route"],
                 "why_excluded": (
                     f"this makes '{act['establishes']}' true without anything "
                     f"about the model changing. It is genuinely cheaper, and a "
                     f"shortest-path solver with no opinion about kind would "
                     f"recommend it every time — correctly, and disastrously")}
                for key, act in ACTS.items()
                if act["kind"] == REMOVES and not state.get(act["establishes"])]

    def _detail(self, honest, anything, state, defaulted) -> str:
        if not honest["reachable"]:
            missing = [f for f in LEAVES if not state.get(f)]
            return (f"no route to this model being in force can be computed: "
                    f"{', '.join(missing)} cannot be established by any act "
                    f"this planner knows. That is a gap in the act table rather "
                    f"than a fact about the model, and it is said rather than "
                    f"returned as an empty plan")
        out = (f"{len(honest['steps'])} act(s) at a total of "
               f"{honest['cost']:.0f} units — computed in the tropical "
               f"semiring over the published derivation, not proposed. The "
               f"answer is arithmetic, and an arithmetic answer produced by a "
               f"language model is a worse version of the same number")
        if anything["cost"] is not None and anything["cost"] < honest["cost"]:
            out += (f". A cheaper route exists at {anything['cost']:.0f} units "
                    f"and is excluded, because it makes the claim true without "
                    f"making the model safer — the cheap routes are listed so a "
                    f"firm can take one deliberately rather than find it by "
                    f"accident")
        if defaulted:
            out += (f". {defaulted / honest['cost']:.0%} of this total is "
                    f"platform defaults rather than this firm's own costs: a "
                    f"shortest path over guessed weights is a confident answer "
                    f"to a question nobody asked, and the confidence is the "
                    f"dangerous part")
        out += (". Nothing here is executed. Each step names the route a person "
                "calls, because no capability in this platform holds a "
                "credential permitting a governance transition")
        return out

    # ------------------------------------------------------------------ state
    def state(self, model: Dict[str, Any],
              now: Optional[float] = None) -> Dict[str, Any]:
        """What the register already establishes about this model."""
        versions = self.registry.versions(model["urn"])
        approved = [v for v in versions if v.get("status") == "approved"]
        opened = (self.findings.open_for(model["id"]) if self.findings else [])
        episodes = ([e for e in self.validation.for_model(model["urn"])
                     if e.get("completed_at")] if self.validation else [])
        monitors = (self.monitoring.registry.for_model(model["id"])
                    if self.monitoring else [])
        documents = (self.documents.about("model", model["id"])
                     if self.documents else [])
        facts = {
            "owned": bool(model.get("owner")),
            "has_version": bool(versions),
            "tiered": model.get("tier") is not None,
            "challenged": bool(episodes),
            "signed_off": bool(approved),
            "monitored": any(m["status"] == "active" for m in monitors),
            "documented": bool(documents),
            "unblocked": not any(f["blocking"] for f in opened),
            "attested": bool(model.get("status") in ("in_force", "attested")),
        }
        facts["approved"] = all(facts[f] for f in
                                ("has_version", "challenged", "tiered",
                                 "owned", "signed_off"))
        facts["in_force"] = all(facts[f] for f in
                                ("approved", "unblocked", "monitored",
                                 "documented", "attested"))
        return facts

    # ------------------------------------------------------------------- what
    def describe(self) -> Dict[str, Any]:
        """The acts, the costs and the derivation, published before any plan."""
        return {
            "acts": [{"act": k, **v, "cost": self.costs[k],
                      "cost_is_declared": k in self.declared}
                     for k, v in ACTS.items()],
            "derivation": {k: [list(alt) for alt in alts]
                           for k, alts in DERIVATIONS.items()},
            "leaves": list(LEAVES),
            "executes": False,
            "detail": ("the plan is computed in the tropical semiring over this "
                       "derivation, and only over acts of kind "
                       f"'{PRODUCES}'. Acts of kind '{REMOVES}' make the claim "
                       "true without making the model safer, are genuinely "
                       "cheaper, and are excluded by kind rather than by price "
                       "— pricing them high would be lying about what they cost "
                       "to make the arithmetic come out right, and the next "
                       "person to read the table would correct the lie"),
        }


# ------------------------------------------------------------------ solving
def _cheapest_act_per_fact(acts: Dict[str, Dict[str, Any]],
                           costs: Dict[str, float]) -> Dict[str, str]:
    """One act per fact: the cheapest that establishes it."""
    best: Dict[str, str] = {}
    for key, act in acts.items():
        fact = act["establishes"]
        if fact not in best or costs[key] < costs[best[fact]]:
            best[fact] = key
    return best


def _evaluate(claim: str, derivations: Dict[str, Derivation], semiring,
              valuation: Callable[[str], Any]) -> Any:
    """Bottom-up over the DAG. The same traversal the evidence engine runs."""
    memo: Dict[str, Any] = {}

    def go(key: str, seen: frozenset) -> Any:
        if key in memo:
            return memo[key]
        if key in seen:
            return semiring.zero
        node = derivations.get(key)
        if node is None or node.is_leaf:
            return valuation(key)
        total = semiring.zero
        for alt in node.alternatives:
            term = semiring.one
            for dep in alt:
                term = semiring.times(term, go(dep, seen | {key}))
            total = semiring.plus(total, term)
        memo[key] = total
        return total

    return go(claim, frozenset())


def _cheapest_support(support, state: Dict[str, Any],
                      by_fact: Dict[str, str],
                      costs: Dict[str, float]) -> List[str]:
    """The minimal support set that costs least, ordered by cost.

    `WHY` returns every minimal set of facts that would establish the claim;
    the tropical evaluation returns the cheapest *total*. This picks the set
    that total belongs to, so the plan and the number agree — two answers to one
    question that were computed separately would eventually disagree, and the
    disagreement would be silent.
    """
    if not support or support == WHY.one:
        return []

    def price(facts) -> float:
        return sum(costs[by_fact[f]] for f in facts if f in by_fact) \
            if all(f in by_fact or state.get(f) for f in facts) \
            else float("inf")

    best = min(support, key=price)
    return sorted((f for f in best if not state.get(f)),
                  key=lambda f: costs.get(by_fact.get(f, ""), 0.0))
