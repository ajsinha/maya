"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Who may approve this, and what an amount MAYA does not have counts as.

## What was already built, and what it was missing

Version approval is a **quorum whose depth follows the tier** (`core/lifecycle/
approval.py`, law `L-5`). That is the right spine and it is enforced. `FR-LC-005`
asks for three things on top of it, and they are not decoration:

| | What it asks | Why a tier alone does not answer it |
|---|---|---|
| **by amount** | a $2bn Tier 2 book and a $4m Tier 2 book are not the same decision | the tier grades the *model*; the amount grades the *consequence of it being wrong* |
| **by legal entity** | a US broker-dealer and a Luxembourg fund have different boards | authority is granted by an entity's board, and it does not travel |
| **sequential approvers** | the second line challenges what the first line produced | a quorum collected in any order lets the challenge be signed before there is anything to challenge |

## The band, and the thing that turned out to matter

A **band** is a row of the matrix: a tier, a floor amount, optionally an entity,
and the roles that must sign — in stages, where a stage does not open until the
one before it has closed. Bands are matched most-specific-first, so a firm adds
a row for one entity without restating the estate.

**The amount comes from the sourced exposure fact and nowhere else.** That is
`H-8`: a figure attested to a named system of record, with a reference somebody
can pull. The register holds no standing exposure column, and the figure the
tiering assessment was made from is a figure typed into a form — using it here
would let the amount that decides the approval depth be chosen by the person
seeking the approval.

**So most models have no amount, and that is the whole design problem.** The
natural implementation falls back to the shallowest band, because an unknown
amount compares as less than every floor. That is exactly backwards, and
invisible: every approval succeeds, nobody is refused, and the matrix reports
itself as enforced.

> **An amount MAYA does not have is not a small amount.** Where the exposure is
> not sourced, the band is the **deepest the tier admits**, and the answer says
> the band was reached by absence rather than by measurement.

That is the same move as everywhere else at an edge: widen the type rather than
add a caveat. The escape is to source the exposure, which is one call and leaves
a reference behind.

## Delegations, and the thing this cannot check

A **delegation** is what one named person may approve: an amount ceiling, for an
entity, until a date, **traceable to an instrument** — a board resolution, a
committee charter, a delegation letter. An instrument is required at record
time, because a delegation nobody can trace to a decision is the precise thing
an authority matrix exists to prevent.

What MAYA cannot check is whether the instrument says what the row claims. It
holds a reference, not the resolution. So delegations **expire**, an expired one
grants nothing, and `across_the_estate()` reports how much of the estate is
approvable under authority that has not been re-attested — because a matrix
enforced confidently from a register nobody has revisited is worse than no
matrix, which at least does not tell you it is working.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.lifecycle.common import LifecycleError
from core.log import get_logger, swallowed

logger = get_logger(__name__)

#: How long a delegation may stand before it has to be re-attested. A year,
#: because that is the cadence a board actually reviews delegated authority on,
#: and a ceiling with no expiry is a ceiling nobody will ever revisit.
STANDS_FOR_DAYS = 366

#: The band that applies where the amount is unknown: the deepest this tier
#: admits. Named rather than computed inline so the reason survives — an amount
#: MAYA does not have is NOT a small amount, and the shallowest band is what
#: every natural implementation of this falls to.
BY_ABSENCE = "deepest_band_because_the_amount_is_unknown"

#: What a delegation must carry. `instrument` is the one that gets left out, and
#: it is the one the matrix exists for.
REQUIRED: Tuple[Tuple[str, str], ...] = (
    ("principal", "whose authority this is. A delegation to a role rather than "
                  "a person is a job description, not a delegation"),
    ("ceiling", "the largest amount they may approve, in one currency"),
    ("instrument", "the board resolution, charter or letter that granted it. "
                   "A delegation nobody can trace to a decision is what an "
                   "authority matrix exists to prevent"),
)

#: The matrix as shipped: the tier quorum that is already enforced, restated as
#: bands with no amount floor and no entity. Deliberately identical in effect to
#: `approval.DEFAULT_QUORUM` on day one — a feature that silently deepens every
#: approval in the estate the moment it is deployed is a feature that gets
#: switched off before anybody reads what it does.
DEFAULT_BANDS: Tuple[Dict[str, Any], ...] = (
    {"name": "tier-1", "tier": 1, "at_or_above": 0.0, "legal_entity": None,
     "stages": (("model_risk_manager",), ("validator",)),
     "note": "second line and an independent validator, in that order"},
    {"name": "tier-2", "tier": 2, "at_or_above": 0.0, "legal_entity": None,
     "stages": (("model_risk_manager", "validator"),),
     "note": "two signatures, either order"},
)


class AuthorityMatrix:
    """The band an approval falls in, and whether the signer's writ reaches it."""

    def __init__(self, bands, delegations, registry, sourcing=None,
                 evidence=None, stands_for_days: int = STANDS_FOR_DAYS):
        self.bands, self.delegations = bands, delegations
        self.registry, self.sourcing = registry, sourcing
        self.evidence = evidence
        self.stands_for = stands_for_days * 86400.0

    # --------------------------------------------------------------- posture
    @staticmethod
    def posture() -> Dict[str, Any]:
        """What the matrix decides, and the one thing it cannot check."""
        return {
            "dimensions": ["tier", "amount", "legal_entity"],
            "amount_comes_from": (
                "the sourced exposure fact (`H-8`) and nowhere else — a figure "
                "attested to a named system of record. The figure the tiering "
                "assessment was made from is a number typed into a form, and "
                "using it would let the amount that decides the approval depth "
                "be chosen by whoever wants the approval"),
            "when_the_amount_is_unknown": (
                "the band is the DEEPEST the tier admits, and the answer says "
                "so. An amount MAYA does not have is not a small amount — but "
                "it compares as less than every floor, so the natural "
                "implementation of this quietly approves everything"),
            "sequencing": (
                "stages. A stage does not open until the one before it has "
                "closed, so a second-line challenge cannot be signed before "
                "there is anything to challenge"),
            "delegations_expire_after_days": STANDS_FOR_DAYS,
            "cannot_check": (
                "whether the instrument says what the delegation claims. MAYA "
                "holds a reference, not the resolution — so delegations expire "
                "and the estate view reports how much of it rests on authority "
                "nobody has re-attested"),
            "required": [{"field": f, "why": w} for f, w in REQUIRED],
        }

    # ----------------------------------------------------------- the matrix
    def publish(self, band: Dict[str, Any], actor: str = "system"
                ) -> Dict[str, Any]:
        """Add a band to the matrix."""
        name = str(band.get("name") or "").strip()
        if not name:
            raise LifecycleError(
                "band_name_required", "a band needs a name",
                "name it after the authority it encodes — the row gets quoted "
                "in a committee paper, and 'row 4' quotes badly")
        stages = [tuple(s) for s in (band.get("stages") or ()) if s]
        if not stages:
            raise LifecycleError(
                "stages_required",
                "a band with no stages requires no signatures",
                "give it at least one stage: a list of roles that sign "
                "together. Several stages sign in order")
        tier = band.get("tier")
        if tier is not None and int(tier) not in (1, 2, 3, 4):
            raise LifecycleError(
                "unknown_tier", f"tier {tier} is not one this platform has",
                "the tiers are 1 to 4; a band with no tier applies to all of "
                "them")
        floor = float(band.get("at_or_above") or 0.0)
        if floor < 0:
            raise LifecycleError(
                "negative_floor", "an amount floor below zero matches nothing",
                "use 0 for a band with no floor")
        if self.bands.one(name=name):
            raise LifecycleError(
                "band_exists", f"a band called '{name}' is already published",
                "withdraw it before publishing another under that name; two "
                "rows with one name is how a matrix stops being readable")
        row = {"name": name,
               "tier": int(tier) if tier is not None else None,
               "at_or_above": floor,
               "legal_entity": (band.get("legal_entity") or None),
               "stages": [list(s) for s in stages],
               "note": str(band.get("note") or ""),
               "published_by": actor, "published_at": time.time()}
        self._record(row, "authority_band_published", actor)
        logger.info("published authority band %s: tier=%s floor=%s entity=%s",
                    name, row["tier"], floor, row["legal_entity"])
        return self.bands.one(name=name)

    def withdraw(self, name: str, actor: str = "system") -> Dict[str, Any]:
        row = self.bands.one(name=name)
        if row is None:
            raise LifecycleError("unknown_band",
                                 f"no band called '{name}' is published", "")
        self.bands.remove(id=row["id"])
        logger.info("withdrew authority band %s", name)
        return {"withdrawn": name, "by": actor,
                "detail": ("approvals already open keep the band they were "
                           "opened under; a matrix that re-decided closed "
                           "questions would be a matrix nobody could rely on")}

    def published(self) -> bool:
        """Whether a firm has published a matrix of its own.

        Version approval consults this before anything else: until a matrix is
        published the tier quorum stands exactly as it always has. A feature
        that deepens every approval in the estate the moment it is deployed is
        a feature switched off before anybody reads what it does — and there
        would then be two sources of truth for the same question, which is the
        defect this module was written to remove.
        """
        return bool(self.bands.many())

    def matrix(self) -> List[Dict[str, Any]]:
        """The whole matrix, most-specific first, so nobody reads config."""
        published = list(self.bands.many())
        rows = published or [dict(b) for b in DEFAULT_BANDS]
        return sorted(rows, key=self._specificity, reverse=True)

    @staticmethod
    def _specificity(band: Dict[str, Any]) -> Tuple[int, int, float]:
        """Entity beats amount beats tier. Ties broken by the higher floor.

        An entity row is the most specific because it is the one a firm adds
        for a reason it can name — a board that granted something different —
        and a general row silently overriding it would be the matrix failing at
        exactly the point somebody took the trouble to be precise.
        """
        return (1 if band.get("legal_entity") else 0,
                1 if band.get("tier") is not None else 0,
                float(band.get("at_or_above") or 0.0))

    # ------------------------------------------------------------ the answer
    def required_for(self, urn: str) -> Dict[str, Any]:
        """Which signatures this model's version approval needs, and why.

        The three inputs are the tier, the sourced amount and the entity. Two
        of them the register holds; the amount it usually does not, and that
        case is the one worth reading.
        """
        model = self.registry.require(urn)
        tier = model.get("tier")
        entity = model.get("legal_entity")
        amount = self.amount_for(model)
        candidates = [b for b in self.matrix()
                      if self._applies(b, tier, entity)]
        by_absence = amount is None and any(
            float(b.get("at_or_above") or 0.0) > 0 for b in candidates)

        if amount is None:
            # The deepest band this tier admits, NOT the shallowest. See the
            # module docstring: an unknown amount compares as less than every
            # floor, so the natural implementation approves everything.
            band = max(candidates, key=self._depth, default=None)
        else:
            band = next((b for b in candidates
                         if amount["value"] >= float(b.get("at_or_above")
                                                     or 0.0)), None)

        stages = [list(s) for s in (band or {}).get("stages") or ()]
        return {
            "urn": model["urn"], "tier": tier, "legal_entity": entity,
            "amount": amount["value"] if amount else None,
            "amount_source": amount["source"] if amount else None,
            "band": (band or {}).get("name"),
            "stages": stages,
            "required_roles": [r for stage in stages for r in stage],
            "sequenced": len(stages) > 1,
            "reached_by": BY_ABSENCE if by_absence else "match",
            "detail": self._why(model, tier, entity, amount, band, by_absence),
        }

    @staticmethod
    def _applies(band: Dict[str, Any], tier: Optional[int],
                 entity: Optional[str]) -> bool:
        if band.get("tier") is not None and band["tier"] != tier:
            return False
        return not (band.get("legal_entity")
                    and band["legal_entity"] != entity)

    @staticmethod
    def _depth(band: Dict[str, Any]) -> Tuple[int, int]:
        """How much ceremony a band demands: signatures first, then stages."""
        stages = band.get("stages") or ()
        return (sum(len(s) for s in stages), len(stages))

    def _why(self, model, tier, entity, amount, band, by_absence) -> str:
        if band is None:
            return (f"no band in the matrix reaches a tier {tier} model at "
                    f"{entity}, so its versions are approved by one authorised "
                    f"person — which is what tiers 3 and 4 have always been")
        if amount is None:
            return (
                f"'{band['name']}' applies. **MAYA holds no sourced exposure "
                f"for {model['urn']}**, so the band is the deepest a tier "
                f"{tier} model admits rather than the shallowest — an amount "
                f"this register does not have is not a small amount, and it "
                f"compares as less than every floor. Source the exposure "
                f"(`POST /fact-sourcing/model`) and the band is decided by "
                f"measurement instead" if by_absence else
                f"'{band['name']}' applies to every tier {tier} model "
                f"regardless of amount")
        return (f"'{band['name']}' applies: a tier {tier} model at {entity} "
                f"with {amount['value']:,.0f} attested from "
                f"{amount['source']} ({amount['reference']})")

    def amount_for(self, model: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The sourced exposure, or nothing. Never the assessment's own figure."""
        if self.sourcing is None:
            return None
        try:
            rows = [r for r in self.sourcing.repo.many(model_id=model["id"])
                    if r.get("fact") == "exposure"]
        except Exception as exc:                 # pragma: no cover - defensive
            logger.warning("could not read fact sourcing for %s: %s",
                           model.get("urn"), exc)
            return None
        if not rows:
            return None
        latest = max(rows, key=lambda r: r.get("as_at") or 0)
        try:
            value = float(latest.get("value"))
        except (TypeError, ValueError) as exc:
            # Not silent. An exposure that will not parse means the band
            # becomes the deepest the tier admits, which looks from the
            # outside exactly like a model nobody sourced — and the two want
            # different fixing.
            swallowed(logger, exc,
                      f"read the sourced exposure for {model.get('urn')}",
                      detail=f"the attested value is {latest.get('value')!r}, "
                             f"which is not a number; this model's approval "
                             f"band is now decided by absence")
            return None
        return {"value": value, "source": latest.get("source"),
                "reference": latest.get("reference"),
                "as_at": latest.get("as_at")}

    # --------------------------------------------------------- the sequence
    def stage_open(self, urn: str, signed_roles: Sequence[str]) -> Dict[str, Any]:
        """Which stage is open, given what has been signed.

        Sequencing is the half of `FR-LC-005` that a set of required roles
        cannot express: a quorum collected in any order lets the second line
        sign its challenge before the first line has filed anything.
        """
        need = self.required_for(urn)
        done = set(signed_roles or ())
        for index, stage in enumerate(need["stages"]):
            if not set(stage) <= done:
                return {**need, "stage": index, "stage_roles": list(stage),
                        "outstanding": sorted(set(stage) - done),
                        "complete": False}
        return {**need, "stage": len(need["stages"]), "stage_roles": [],
                "outstanding": [], "complete": True}

    def refuse_out_of_sequence(self, urn: str, role: str,
                               signed_roles: Sequence[str]) -> None:
        """Raises where this role's stage has not opened yet."""
        state = self.stage_open(urn, signed_roles)
        if state["complete"] or not state["sequenced"]:
            return
        if role in state["stage_roles"]:
            return
        later = any(role in stage
                    for stage in state["stages"][state["stage"] + 1:])
        if not later:
            return
        raise LifecycleError(
            "out_of_sequence",
            f"'{role}' signs after {', '.join(state['stage_roles'])} on band "
            f"'{state['band']}', and {', '.join(state['outstanding'])} have "
            f"not signed yet",
            "the order is the control: a challenge signed before the thing it "
            "challenges was filed is a signature about nothing. Have the "
            "outstanding roles sign first")

    # ---------------------------------------------------------- delegations
    def delegate(self, principal: str, *, ceiling: float, instrument: str,
                 currency: str = "USD", legal_entity: Optional[str] = None,
                 actor: str = "system", now: Optional[float] = None
                 ) -> Dict[str, Any]:
        """Record what one named person may approve, and until when."""
        moment = now if now is not None else time.time()
        why = dict(REQUIRED)
        who = str(principal or "").strip()
        if not who:
            raise LifecycleError("principal_required",
                                 "a delegation needs a person", why["principal"])
        if not str(instrument or "").strip():
            raise LifecycleError(
                "instrument_required",
                "no instrument was named for this delegation",
                why["instrument"] + ". Name the resolution, charter or letter "
                "— MAYA cannot read it, and holding the reference is the "
                "difference between a delegation and somebody's recollection")
        try:
            limit = float(ceiling)
        except (TypeError, ValueError) as exc:
            swallowed(logger, exc, f"read '{ceiling}' as a ceiling",
                      detail="refused back to the caller as "
                             "`ceiling_required`")
            raise LifecycleError("ceiling_required",
                                 f"'{ceiling}' is not an amount",
                                 why["ceiling"]) from exc
        if limit <= 0:
            raise LifecycleError(
                "ceiling_required", "a ceiling of zero delegates nothing",
                why["ceiling"] + ". A person with no authority does not need a "
                "row; withdraw the delegation instead")
        row = {"principal": who, "ceiling": limit,
               "currency": str(currency or "USD").upper(),
               "legal_entity": legal_entity or None,
               "instrument": str(instrument).strip(),
               "granted_by": actor, "granted_at": moment,
               "expires_at": moment + self.stands_for}
        self._record(row, "authority_delegated", actor)
        logger.info("delegated %s %.0f %s at %s until %s", who, limit,
                    row["currency"], legal_entity or "any entity",
                    row["expires_at"])
        return {**row, "detail": (
            f"{who} may approve up to {limit:,.0f} {row['currency']} at "
            f"{legal_entity or 'any entity'} under {row['instrument']}. MAYA "
            f"holds the reference, not the resolution — this stands for "
            f"{STANDS_FOR_DAYS} days and then grants nothing until it is "
            f"re-attested")}

    def held_by(self, principal: str, now: Optional[float] = None
                ) -> List[Dict[str, Any]]:
        """The live delegations a person holds. An expired one is not one."""
        moment = now if now is not None else time.time()
        return [r for r in self.delegations.many(principal=principal)
                if (r.get("expires_at") or 0) > moment]

    def refuse_beyond_delegation(self, urn: str, principal: Dict[str, Any],
                                 now: Optional[float] = None) -> None:
        """Raises where the signer's writ does not reach this approval.

        Silent where no delegation has ever been recorded for anybody: a
        control that refuses the whole estate the day it is switched on is a
        control that gets switched off the same day, and the estate view is
        where the absence is reported instead.
        """
        if not self.delegations.many():
            return
        model = self.registry.require(urn)
        amount = self.amount_for(model)
        username = principal.get("username", "")
        live = self.held_by(username, now)
        if not live:
            raise LifecycleError(
                "no_delegated_authority",
                f"{username} holds no live delegated authority",
                "a delegation is recorded against a named instrument and "
                "stands for a year. An expired one grants nothing — that is "
                "the point of it expiring, because MAYA cannot check whether "
                "the resolution behind it still says what it said")
        entity = model.get("legal_entity")
        reaching = [d for d in live
                    if not d.get("legal_entity") or d["legal_entity"] == entity]
        if not reaching:
            raise LifecycleError(
                "entity_out_of_delegation",
                f"{username}'s authority does not reach {entity}",
                "authority is granted by an entity's board and it does not "
                "travel. Record a delegation for this entity, or have "
                "somebody whose writ reaches it sign")
        if amount is None:
            # No amount to test a ceiling against. Reported, not refused: the
            # deepening already happened in `required_for`, and refusing twice
            # for one absence teaches that the matrix is arbitrary.
            logger.info("%s signs for %s with no sourced amount to test "
                        "against a ceiling", username, model["urn"])
            return
        highest = max(d["ceiling"] for d in reaching)
        if amount["value"] > highest:
            raise LifecycleError(
                "beyond_delegated_authority",
                f"{username} may approve up to {highest:,.0f} and this model's "
                f"attested exposure is {amount['value']:,.0f}",
                f"the figure is attested from {amount['source']} "
                f"({amount['reference']}), so the disagreement is between the "
                f"delegation and the system of record rather than between two "
                f"opinions. Escalate to somebody whose ceiling reaches it, or "
                f"correct the exposure at its source")

    # ---------------------------------------------------------- the estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """How much of the estate rests on authority nobody has re-attested."""
        moment = now if now is not None else time.time()
        rows = list(self.delegations.many())
        live = [r for r in rows if (r.get("expires_at") or 0) > moment]
        expired = [r for r in rows if (r.get("expires_at") or 0) <= moment]
        models = list(self.registry.list())
        unsourced = [m["urn"] for m in models if self.amount_for(m) is None]
        return {
            "bands": len(self.matrix()),
            "published": self.published(),
            "delegations": len(rows), "live": len(live),
            "expired": sorted({r["principal"] for r in expired}),
            "models": len(models),
            "without_a_sourced_amount": len(unsourced),
            "examples": sorted(unsourced)[:5],
            "detail": (
                f"{len(unsourced)} of {len(models)} model(s) have no attested "
                f"exposure, so their approval band is the deepest their tier "
                f"admits rather than one decided by measurement. That is the "
                f"safe direction and it is not the useful one"
                + (f". {len(expired)} delegation(s) have expired and grant "
                   f"nothing until they are re-attested"
                   if expired else
                   ". Every delegation on file is live")
                + (". No matrix is published, so the tier quorum shipped as "
                   "the default is what is enforced" if not self.published()
                   else "")),
        }

    # ----------------------------------------------------------------- plumb
    def _record(self, row: Dict[str, Any], event: str, actor: str) -> None:
        repo = self.bands if "stages" in row else self.delegations
        if self.evidence is None:
            repo.add(row)
            return
        with self.evidence.recording():
            repo.add(row)
            self.evidence.append(
                event, "platform", row.get("name") or row.get("principal"),
                {k: v for k, v in row.items() if k != "id"}, actor=actor)
