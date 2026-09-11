"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Where a tiering fact came from, and the difference between a claim and a
measurement.

## The finding, and why it is the most consequential one open

**H-8**: *tier gaming through input manipulation*. `exposure` is a float on the
assessment request, and the tier is a monotone function of it. So the number
that decides how many signatures an approval needs, how often the model is
reviewed, and whether it can be aliased into production at all — is typed in by
the person the controls apply to.

Nothing about that is hypothetical or adversarial-only. The common case is
ordinary and worse: somebody registering a model does not know the exposure,
puts in a plausible figure to get past the form, and the platform derives a tier
from it with a rationale that reads exactly like one derived from a measurement.

The audit half already worked — the fact snapshot is stored with every
assessment, so *what was claimed* is on the record. What was missing is the
distinction between a claim and a measurement, and a register that cannot make
that distinction is presenting both with the same confidence.

## What this adds, and what it deliberately does not

**It does not fetch anything.** MAYA holds no connection to a finance system, a
risk data mart or a CMDB, and acquiring one would be the same standing-access
objection the connectors answer: a governance register with read credentials to
the general ledger is a register that has to be trusted with one more thing than
it needs. A source is *named and attested*, the same shape as everything else at
a boundary in this platform.

**It does not refuse an unsourced fact.** Refusing would stop registration, and
a register that cannot admit a model until somebody produces a ledger extract is
a register people work around — which produces an *unregistered* model, which is
strictly worse than a tiered-from-a-guess one. So an unsourced fact is admitted
and **marked**, and the mark travels: onto the assessment, onto the tier, into
the estate view and into the board pack.

**What it does instead is make the difference visible and countable.** `SOURCED`
against `ASSERTED` against `STALE`, per fact. An estate where sixty percent of
exposures are asserted is a real finding about the *tiering programme*, and it
is invisible the moment a claim and a measurement print identically.

## Peer-cohort outliers, and why they are a question rather than an alarm

The finding also asks for outlier detection. A model whose stated exposure sits
far below its cohort — same model class, same domain, same purpose — is worth
somebody asking about. It is *not* worth raising a finding automatically: a
cohort of four is not a distribution, business lines genuinely differ by orders
of magnitude, and a control that cries wolf at every small book is one somebody
switches off, taking the real signal with it.

So this reports the comparison and the cohort size beside it, and says plainly
when the cohort is too small to mean anything. `AT_LEAST_A_COHORT` is five —
small, and stated, because a threshold chosen silently is a threshold nobody can
argue with.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger
from core.risk.tiering import RiskError

logger = get_logger(__name__)

#: How a fact reached the register.
SOURCED, ASSERTED, STALE = "sourced", "asserted", "stale"

#: Facts worth sourcing. Each is an input to `tau` and each is supplied by the
#: caller — so each is a place where the tier can be chosen rather than derived.
#:
#: `feature_count` and `interpretable` are here and `trainability_class` is
#: NOT: the class is derived from how the parameter object is inhabited and
#: cannot be asserted at all, which is the shape the rest of these would like
#: to be and cannot, because no ledger lives in this platform.
SOURCEABLE: Tuple[Tuple[str, str], ...] = (
    ("exposure", "what rides on this model, in currency. The single most "
                 "consequential number in the register: the tier is a "
                 "monotone function of it, and the tier decides how many "
                 "signatures an approval needs"),
    ("purpose_class", "what the model is used FOR. Not gameable by arithmetic "
                      "but very gameable by wording — 'commercial' and "
                      "'regulatory_capital' are two tiers apart"),
    ("feature_count", "how many inputs. Crosses a complexity band at 50"),
    ("uses_alternative_data", "whether it uses data the subject did not "
                              "provide for this purpose"),
    ("interpretable", "whether a person can follow the reasoning"),
)

#: How long a sourced fact stays sourced. A twelve-month-old ledger extract is
#: not a measurement of today's exposure, and treating it as one is how a
#: source becomes a formality somebody satisfied once.
FRESH_FOR_DAYS = 400.0

#: Below this, a cohort is not a distribution. Small and stated: a threshold
#: chosen silently is a threshold nobody can argue with.
AT_LEAST_A_COHORT = 5

#: How far below the cohort's median is worth asking about. Not a finding —
#: see the module note on crying wolf.
WORTH_ASKING_BELOW = 0.1


class FactSourcing:
    """Records where a tiering fact came from, and reports what is asserted."""

    def __init__(self, repo, registry=None, evidence=None):
        self.repo, self.registry, self.evidence = repo, registry, evidence

    # --------------------------------------------------------------- posture
    @staticmethod
    def posture() -> Dict[str, Any]:
        """What this is, and the two things it refuses to be."""
        return {
            "fetches_anything": False,
            "refuses_an_unsourced_fact": False,
            "sourceable": [{"fact": f, "why": w} for f, w in SOURCEABLE],
            "states": [SOURCED, ASSERTED, STALE],
            "fresh_for_days": FRESH_FOR_DAYS,
            "why_not_fetch": (
                "a governance register holding read credentials to the "
                "general ledger is a register that has to be trusted with one "
                "more thing than it needs. A source is named and attested, "
                "the same shape as everything else at a boundary here"),
            "why_not_refuse": (
                "refusing would stop registration, and a register that cannot "
                "admit a model until somebody produces a ledger extract is "
                "one people work around — which produces an UNREGISTERED "
                "model, strictly worse than a tiered-from-a-guess one. So an "
                "unsourced fact is admitted and MARKED, and the mark travels "
                "onto the assessment, the tier, the estate view and the board "
                "pack"),
            "detail": (
                "the audit half already worked: what was claimed is on the "
                "record. What was missing is the difference between a claim "
                "and a measurement — and a register that cannot make that "
                "distinction presents both with the same confidence"),
        }

    # ---------------------------------------------------------------- record
    def record(self, model_id: str, fact: str, *, source: str,
               reference: str = "", value: Any = None, as_at: float = 0.0,
               actor: str = "system", now: Optional[float] = None
               ) -> Dict[str, Any]:
        """Attest that a fact came from a named system of record.

        `source` and `reference` are both required and neither is paperwork.
        A source with no reference is unfalsifiable — *finance said so* cannot
        be checked by the person who has to rely on it a year later — and the
        whole value of this is that somebody can go and look.
        """
        known = {f for f, _ in SOURCEABLE}
        if fact not in known:
            raise RiskError(
                "not_a_sourceable_fact",
                f"'{fact}' is not a tiering fact this records a source for",
                f"the facts are {', '.join(sorted(known))}. The trainability "
                f"class is deliberately absent: it is DERIVED from how the "
                f"parameter object is inhabited and cannot be asserted at all")
        if not str(source).strip():
            raise RiskError(
                "source_required", "no system of record was named",
                "name the system the number came from. An unnamed source is "
                "the same as no source, recorded with more confidence")
        if not str(reference).strip():
            raise RiskError(
                "reference_required",
                f"'{source}' was named with nothing to look the figure up by",
                "give the extract id, the report reference, the ticket — "
                "whatever somebody would use to go and check. A source with "
                "no reference is unfalsifiable, and the whole value of this "
                "is that somebody can go and look")
        moment = now if now is not None else time.time()
        row = {
            "model_id": model_id, "fact": fact, "source": str(source).strip(),
            "reference": str(reference).strip(),
            "value": "" if value is None else str(value),
            "as_at": as_at or moment,
            "recorded_by": actor, "recorded_at": moment,
        }
        self.repo.add(row)
        if self.evidence is not None:
            self.evidence.append("tiering_fact_sourced", "model", model_id,
                                 {k: v for k, v in row.items()
                                  if k != "model_id"}, actor=actor)
        logger.info("tiering fact %s for %s sourced from %s", fact, model_id,
                    source)
        return {**row, "state": SOURCED,
                "detail": (f"'{fact}' is attested to {source} "
                           f"({row['reference']}). MAYA did not fetch it and "
                           f"does not check it — what changes is that a "
                           f"reader can tell this from a number somebody "
                           f"typed, and can go and look")}

    # ------------------------------------------------------------------ read
    def of(self, model_id: str, facts: Optional[Dict[str, Any]] = None,
           now: Optional[float] = None) -> Dict[str, Any]:
        """Which of this model's tiering facts are sourced, and which are not."""
        moment = now if now is not None else time.time()
        rows = self.repo.many(model_id=model_id)
        latest: Dict[str, Dict[str, Any]] = {}
        for row in sorted(rows, key=lambda r: r.get("recorded_at") or 0):
            latest[row["fact"]] = row
        out = []
        for fact, why in SOURCEABLE:
            row = latest.get(fact)
            state = self._state(row, moment)
            out.append({
                "fact": fact, "why": why, "state": state,
                "source": (row or {}).get("source"),
                "reference": (row or {}).get("reference"),
                "as_at": (row or {}).get("as_at"),
                "stated_value": (facts or {}).get(fact),
                "age_days": (round((moment - row["as_at"]) / 86400.0, 1)
                             if row and row.get("as_at") else None),
            })
        sourced = sum(1 for f in out if f["state"] == SOURCED)
        return {
            "model_id": model_id, "facts": out,
            "sourced": sourced, "of": len(out),
            "asserted": [f["fact"] for f in out if f["state"] == ASSERTED],
            "stale": [f["fact"] for f in out if f["state"] == STALE],
            "detail": self._detail(out, sourced),
        }

    @staticmethod
    def _state(row: Optional[Dict[str, Any]], now: float) -> str:
        if row is None:
            return ASSERTED
        as_at = row.get("as_at") or 0
        if now - as_at > FRESH_FOR_DAYS * 86400.0:
            # Stale is its own state, not a demotion to asserted. A figure that
            # WAS measured and has aged is a different thing from one nobody
            # ever measured, and the remedy is different too: refresh the
            # extract, rather than go and find out.
            return STALE
        return SOURCED

    @staticmethod
    def _detail(facts: Sequence[Dict[str, Any]], sourced: int) -> str:
        total = len(facts)
        asserted = [f["fact"] for f in facts if f["state"] == ASSERTED]
        stale = [f["fact"] for f in facts if f["state"] == STALE]
        if sourced == total:
            return (f"all {total} tiering facts are attested to a named system "
                    f"of record. MAYA did not fetch any of them and does not "
                    f"check them — what this buys is that a reader can tell "
                    f"them from numbers somebody typed")
        out = f"{sourced} of {total} tiering facts are sourced"
        if asserted:
            out += (f". {', '.join(asserted)} " +
                    ("is" if len(asserted) == 1 else "are") +
                    " asserted — supplied by the caller with no system of "
                    "record behind " +
                    ("it" if len(asserted) == 1 else "them") + ". That is "
                    "admitted rather than refused, because a register nobody "
                    "can register into produces unregistered models")
        if stale:
            out += (f". {', '.join(stale)} " +
                    ("was" if len(stale) == 1 else "were") +
                    f" measured more than {FRESH_FOR_DAYS:.0f} days ago. A "
                    f"figure that WAS measured and has aged is a different "
                    f"thing from one nobody measured, and the remedy is "
                    f"different: refresh the extract")
        if "exposure" in asserted:
            out += (". **Exposure is one of them**, which is the one that "
                    "matters: the tier is a monotone function of it, and the "
                    "tier decides how many signatures an approval needs")
        return out

    # --------------------------------------------------------- across the estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """How much of this estate's tiering rests on somebody's word.

        The number this exists to produce. An estate where sixty percent of
        exposures are asserted is a real finding about the *tiering programme*,
        and it is invisible the moment a claim and a measurement print
        identically.
        """
        if self.registry is None:
            raise RiskError(
                "no_registry", "this service cannot see the estate",
                "wire the model registry")
        moment = now if now is not None else time.time()
        models = self.registry.list()
        by_state: Dict[str, int] = {SOURCED: 0, ASSERTED: 0, STALE: 0}
        unsourced_exposure: List[str] = []
        for model in models:
            answer = self.of(model["id"], model, moment)
            for fact in answer["facts"]:
                by_state[fact["state"]] = by_state.get(fact["state"], 0) + 1
                if fact["fact"] == "exposure" and fact["state"] != SOURCED:
                    unsourced_exposure.append(model["urn"])
        total = sum(by_state.values())
        return {
            "models": len(models), "facts": total, "by_state": by_state,
            "sourced_share": round(by_state[SOURCED] / total, 3) if total else 0,
            "exposure_unsourced": unsourced_exposure,
            "detail": (
                f"{by_state[SOURCED]} of {total} tiering facts across "
                f"{len(models)} model(s) are attested to a system of record"
                + (f". **{len(unsourced_exposure)} model(s) have an exposure "
                   f"nobody sourced**, and exposure is the number the tier is "
                   f"a monotone function of — so those tiers rest on what "
                   f"somebody typed into a form. This is a finding about the "
                   f"tiering PROGRAMME rather than about any one model"
                   if unsourced_exposure else
                   ". Every exposure is sourced, which is the one that "
                   "matters")),
        }

    # ------------------------------------------------------------- the cohort
    def outliers(self, urn: str, now: Optional[float] = None
                 ) -> Dict[str, Any]:
        """How this model's stated exposure compares with its peers.

        A **question**, not an alarm. A cohort of four is not a distribution,
        business lines genuinely differ by orders of magnitude, and a control
        that cries wolf at every small book is one somebody switches off —
        taking the real signal with it. So this reports the comparison and the
        cohort size beside it, and says plainly when the cohort is too small to
        mean anything.
        """
        if self.registry is None:
            raise RiskError("no_registry", "this service cannot see the estate",
                            "wire the model registry")
        model = self.registry.require(urn)
        cohort = [m for m in self.registry.list()
                  if m["id"] != model["id"]
                  and m.get("model_class") == model.get("model_class")
                  and m.get("domain") == model.get("domain")]
        exposures = sorted(float(m.get("exposure") or 0) for m in cohort
                           if m.get("exposure"))
        mine = float(model.get("exposure") or 0)
        if len(exposures) < AT_LEAST_A_COHORT:
            return {
                "urn": urn, "exposure": mine, "cohort": len(exposures),
                "worth_asking": False, "median": None,
                "detail": (
                    f"{len(exposures)} peer(s) share this model's class and "
                    f"domain, and {AT_LEAST_A_COHORT} is the fewest this will "
                    f"compare against. A cohort of four is not a distribution, "
                    f"and an outlier call over one is a number that will be "
                    f"argued with and should be"),
            }
        median = exposures[len(exposures) // 2]
        ratio = (mine / median) if median else 0.0
        worth_asking = bool(median) and ratio < WORTH_ASKING_BELOW
        return {
            "urn": urn, "exposure": mine, "cohort": len(exposures),
            "median": median, "ratio": round(ratio, 4),
            "worth_asking": worth_asking,
            "raises_a_finding": False,
            "detail": (
                f"this model's stated exposure is {ratio:.1%} of the median "
                f"across {len(exposures)} peer(s) in the same class and domain"
                + (". That is far enough below to be worth somebody asking "
                   "about, and it deliberately raises NO finding: business "
                   "lines genuinely differ by orders of magnitude, and a "
                   "control that cried wolf at every small book would be "
                   "switched off — taking the real signal with it"
                   if worth_asking else
                   ", which is within the band this does not ask about")),
        }
