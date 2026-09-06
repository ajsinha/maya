"""
MAYA — aggregate risk is lax monoidal, law L-14.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

SR 26-2 asks that aggregate model risk "reflects interactions and dependencies
among models; reliance on common assumptions, data, or methodologies". Let `ρ`
assign each model a risk value in a lattice. If `ρ` were a **strict** monoidal
functor then `ρ(g ∘ f) = ρ(g) ⊔ ρ(f)` — aggregate risk would be the join of the
components, and a spreadsheet could compute it.

It is not. `ρ` is **lax**:

    ρ(g ∘ f)  ⊒  ρ(g) ⊔ ρ(f)

and the gap is the interaction term. That inequality is `L-14`, and it was for a
long time the only law in this codebase stated as a formula with nothing behind
it — which is a worse position than not having stated it, because a law nobody
computes cannot be violated and therefore prevents nothing.

## What ρ is, and what it deliberately is not

`ρ` here is **not a score**. The board pack refuses to produce a single
model-risk number and this module does not smuggle one in through a side door:
an aggregate that composed strictly would be a number wrong in a known
direction, and one that composed with an invented interaction coefficient would
be wrong in an unknown one.

`ρ` is an element of a small, explicit lattice — the **risk tier**, ordered by
materiality, with the interaction term expressed as a set of *named
obstructions* rather than as a magnitude. The join of two tiers is the more
material of the two. The composite's tier is that join, escalated by one step
for each kind of interaction the register can actually see, and floored at
tier 1 because there is nothing above it.

Every obstruction below is something MAYA holds. None is estimated:

* **a shared dependency** — a fault in a common input is not two independent
  faults, and `shared_dependencies` already computed exactly this;
* **an unchecked edge** — recorded before either end had a version, so nothing
  ever verified that what the source produces can stand in for what the target
  reads;
* **a boundary the wire does not settle** — the target assumes something the
  source speaks to and does not imply, which *looks* covered by the wiring;
* **contracts that cannot both hold** — the pair has no composite contract at
  all;
* **a tier inversion** — a material model fed by one carrying lighter controls,
  which is the case supervisors ask about by name.

The premium is a list because a number would have to be defended, and none of
these has an agreed magnitude. What can be defended is that each is present, and
that the composite is at least as risky as its parts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger

logger = get_logger(__name__)

#: Tier 1 is the most material. The lattice order is "at least as risky as", so
#: the JOIN of two tiers is the SMALLER number — which reads backwards until
#: said out loud, and is why it is a named function rather than `min` inline.
MOST_MATERIAL, LEAST_MATERIAL = 1, 4

#: What each obstruction is, in the words somebody would use to explain it.
OBSTRUCTIONS: Dict[str, str] = {
    "shared_dependency": "both ends rely on the same upstream model, so a fault "
                         "there is not two independent faults",
    "unchecked_edge": "the edge was recorded before either end had a version, so "
                      "nothing has verified that what the source produces can "
                      "stand in for what the target reads",
    "unsettled_boundary": "the source speaks to a boundary the target assumes "
                          "and does not imply it, so the wiring looks like it "
                          "covers the assumption and does not",
    "contracts_exclude": "the two contracts cannot both hold, so the pair has no "
                         "composite contract",
    "tier_inversion": "a more material model is fed by a less material one, "
                      "which carries lighter controls",
    "untiered_component": "a component has no tier, so its contribution to the "
                          "aggregate is unknown rather than small",
}


@dataclass(frozen=True)
class Obstruction:
    """One reason a composite is riskier than its parts, and the evidence."""
    kind: str
    detail: str
    subject: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "means": OBSTRUCTIONS.get(self.kind, ""),
                "detail": self.detail, "subject": self.subject}


@dataclass(frozen=True)
class Risk:
    """A value of `ρ`: a tier, and why it is where it is.

    Comparison is by tier alone. The obstructions travel with it because an
    aggregate a reader cannot open is an aggregate they cannot defend, which is
    the objection this module exists to answer.
    """
    tier: Optional[int]
    obstructions: Tuple[Obstruction, ...] = field(default_factory=tuple)

    def at_least_as_risky_as(self, other: "Risk") -> bool:
        """`self ⊒ other`.

        An unknown tier is the TOP of this lattice, not the bottom. A component
        nobody has assessed is not a safe component; treating `None` as least
        risky would make the aggregate of an untiered estate look excellent,
        which is the failure this whole codebase is named for.
        """
        if self.tier is None:
            return True
        if other.tier is None:
            return False
        return self.tier <= other.tier

    def as_dict(self) -> Dict[str, Any]:
        return {"tier": self.tier,
                "obstructions": [o.as_dict() for o in self.obstructions],
                "premium": len(self.obstructions)}


def join(*risks: Risk) -> Risk:
    """`ρ₁ ⊔ ρ₂` — the least element at least as risky as both.

    The more material tier wins, and an unknown tier wins over everything: the
    join of *tier 4* and *not assessed* is *not assessed*, because the pair is
    only as well understood as its least understood half.
    """
    present = [r for r in risks if r is not None]
    if not present:
        return Risk(tier=None)
    tiers = [r.tier for r in present]
    if any(t is None for t in tiers):
        return Risk(tier=None)
    # Narrowed for the type checker as well as for the reader: `min` over a
    # sequence that might hold `None` is exactly the mistake the guard above
    # prevents, and saying so in the types keeps the two in step.
    return Risk(tier=min(t for t in tiers if t is not None))


def escalate(tier: Optional[int], steps: int) -> Optional[int]:
    """Move `steps` towards the most material tier, and stop there.

    Floored rather than wrapped, and floored at 1 because there is nothing above
    tier 1 — a composite cannot be more than the most material thing the scale
    can express, and inventing a tier 0 would be inventing a control regime.
    """
    if tier is None:
        return None
    return max(MOST_MATERIAL, tier - max(0, steps))


class AggregateRisk:
    """`ρ` over the register, and the laxity that makes L-14 true."""

    def __init__(self, catalogue, composition, contracts=None):
        self.catalogue = catalogue
        self.composition = composition
        self.contracts = contracts

    # ------------------------------------------------------------ components
    def rho(self, urn: str) -> Risk:
        """`ρ` of one model: its recorded tier, and nothing invented."""
        model = self.catalogue.require(urn)
        tier = model.get("tier")
        if tier is None:
            return Risk(tier=None, obstructions=(
                Obstruction("untiered_component",
                            f"{urn} has no recorded tier", urn),))
        return Risk(tier=tier)

    # ------------------------------------------------------------- composites
    def obstructions(self, source: str, target: str) -> List[Obstruction]:
        """Everything the register can see that makes the pair interact.

        Each is read from something already stored. Nothing here is estimated,
        because an interaction premium with an invented coefficient is a number
        that has to be defended and cannot be.
        """
        found: List[Obstruction] = []

        shared = self.composition.shared_dependencies([source, target])
        for row in shared.get("shared", []):
            found.append(Obstruction(
                "shared_dependency",
                f"{row['urn']} is relied on by both ends", row["urn"] or ""))

        for edge in self.composition.edges_of(source)["downstream"]:
            if edge.get("urn") != target:
                continue
            if edge.get("kind") == "input_to" and not edge.get("type_checked"):
                found.append(Obstruction(
                    "unchecked_edge",
                    f"the {edge['kind']} edge was recorded without a type check",
                    f"{source} -> {target}"))

        composite = self._composite(source, target)
        contract = (composite or {}).get("contract") or {}
        if contract.get("stated") and not contract.get("holds", 1):
            found.append(Obstruction(
                "contracts_exclude", contract.get("detail", ""),
                f"{source} -> {target}"))
        for key in contract.get("spoken_to_but_not_settled", []):
            found.append(Obstruction(
                "unsettled_boundary",
                f"the source speaks to '{key}' and does not settle it", key))

        upstream, downstream = self.rho(source), self.rho(target)
        if (upstream.tier is not None and downstream.tier is not None
                and downstream.tier < upstream.tier):
            found.append(Obstruction(
                "tier_inversion",
                f"tier {downstream.tier} is fed by tier {upstream.tier}",
                f"{source} -> {target}"))
        for risk in (upstream, downstream):
            found.extend(risk.obstructions)
        return found

    def compose(self, source: str, target: str) -> Risk:
        """`ρ(g ∘ f)`. At least the join, escalated once per KIND of obstruction.

        Per kind rather than per instance, deliberately. Three shared
        dependencies are more interaction than one, but they are not three times
        the escalation — and a scale with four points cannot express "three
        times" honestly. What the scale can express is *this pair interacts in
        two distinct ways*, so that is what it says.
        """
        parts = join(self.rho(source), self.rho(target))
        found = self.obstructions(source, target)
        kinds = {o.kind for o in found}
        return Risk(tier=escalate(parts.tier, len(kinds)),
                    obstructions=tuple(found))

    def holds(self, source: str, target: str) -> Dict[str, Any]:
        """`L-14` for one composable pair, with the working shown."""
        parts = join(self.rho(source), self.rho(target))
        composite = self.compose(source, target)
        satisfied = composite.at_least_as_risky_as(parts)
        return {
            "law": "L-14", "source": source, "target": target,
            "components": parts.as_dict(), "composite": composite.as_dict(),
            "holds": satisfied,
            "strict": composite.tier == parts.tier,
            "detail": self._detail(parts, composite),
        }

    @staticmethod
    def _detail(parts: Risk, composite: Risk) -> str:
        if composite.tier == parts.tier:
            return ("the pair interacts in no way the register can see, so the "
                    "composite is exactly the join of its parts — which is "
                    "laxity holding with equality, not laxity being absent")
        kinds = sorted({o.kind for o in composite.obstructions})
        return (f"tier {parts.tier} for the parts, tier {composite.tier} for the "
                f"pair: {len(kinds)} kind(s) of interaction — {', '.join(kinds)}")

    def estate(self, urns: Sequence[str]) -> Dict[str, Any]:
        """Every composable pair in a set of models, and whether the law holds.

        No single number, because the board pack refuses to produce one and this
        would be the side door. What comes back is the pairs, the obstructions
        and the count — which is what somebody would have to look at anyway to
        act on the answer.
        """
        pairs, violations = [], []
        for source in urns:
            for edge in self.composition.edges_of(source)["downstream"]:
                target = edge.get("urn")
                if target not in urns:
                    continue
                answer = self.holds(source, target)
                pairs.append(answer)
                if not answer["holds"]:
                    violations.append(answer)
        return {
            "law": "L-14", "pairs": len(pairs), "violations": len(violations),
            "holds": not violations,
            "escalated": sum(1 for p in pairs if not p["strict"]),
            "results": pairs,
            "detail": (f"{len(pairs)} composable pair(s); "
                       f"{sum(1 for p in pairs if not p['strict'])} are riskier "
                       f"than the join of their parts, which is the interaction "
                       f"the guidance asks about"),
        }

    # ----------------------------------------------------------------- parts
    def _composite(self, source: str, target: str) -> Optional[Dict[str, Any]]:
        try:
            return self.composition.composite_schema(source, target)
        except Exception as exc:
            logger.debug("no composite schema for %s -> %s: %s", source, target, exc)
            return None
