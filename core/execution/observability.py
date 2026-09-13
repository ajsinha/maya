"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What the register can observe about execution it cannot observe.

## The finding this answers, and the part of it that is not answerable

**C-6** said `descriptor_only` warrants make governance dependent on client
honesty. It was accepted with five mitigations, and
[§4.7](../../docs/11-adversarial-review.md) found four of them unbuilt. The
attack it describes is real and stays real: *I am an opaque engine, I resolve a
descriptor and then ignore the operating boundary, cache the artifact past
expiry, and send no telemetry.* MAYA does not run models, so nothing here
detects that engine misbehaving. **That limitation is not repaired by this
module and is not repairable by any module** — it is what ADR-014 means by
*attested, not observed*.

What this module does is narrower and was genuinely missing: **MAYA can observe
the gap between what it authorised and what came back.** That is a fact about
its own records, not about anybody's engine, and it was sitting in two places
that nothing read.

## Two columns nobody selected

`warrant.flavour` is written at issue, defaults to `descriptor_only`, and — as
§4.7 put it — *is read by nothing*. So the estate could be governed entirely by
warrants over engines the platform cannot see into, and no screen, job or
report said so or could be made to say so. The quantity was not high; it was
absent.

`TelemetryCollector.estate()` classifies every version as `silent`, `never` or
`sending`, and no scheduler job consumed it. A principal that resolves warrants
weekly and has never reported a single score raised nothing — which is the one
symptom of the C-6 attack that MAYA *is* positioned to notice, because both
halves of it are in MAYA's own log.

## Why silence is a finding and not an alarm

Silence has an innocent explanation: the model is authorised and nobody has
used it. That is why this raises against the **combination** — a live warrant,
resolved, and nothing coming back — and why the finding says what it cannot
distinguish rather than asserting misbehaviour. A control that cried
"unreported execution" at every unused warrant would be turned off within a
week, and then the one case that mattered would be inside the noise it taught
people to ignore.

## What is deliberately not built

**Certification as an input to tiering** was C-6's third mitigation and it is
refused here rather than left open. Tiering is exposure × purpose; who runs a
model is not a property of the model's risk, it is a property of the
arrangement. Folding it in would make the same model tier differently on two
engines, which would make the tier unusable as the thing controls hang off —
and the honest place for the fact is here, beside the warrant, where it does
not move the lattice.

**Signed telemetry** stays unbuilt for the reason recorded in
[10 §2.1](../../docs/10-what-is-not-built.md): a per-engine HMAC key already
confines a compromised engine to forging its own reports, and signing buys
non-repudiation to a third party, which nobody has asked for.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger

logger = get_logger(__name__)

#: The flavour that means "MAYA holds the governance; somebody else holds the
#: model, and MAYA cannot see what they do with it".
UNOBSERVED = "descriptor_only"

#: Tiers at which unobserved execution is worth a finding rather than a number.
#:
#: Not every tier: a Tier 4 model on an opaque engine is a normal arrangement,
#: and raising it would bury the Tier 1 case. The threshold is where the
#: platform's own controls stop being advisory.
ESCALATE_AT_OR_ABOVE = 2


class ExecutionObservability:
    """How much of the estate is authorised on engines nobody can see."""

    def __init__(self, db, registry, telemetry=None):
        self.db, self.registry, self.telemetry = db, registry, telemetry

    # ----------------------------------------------------------------- report
    def posture(self, models: Optional[Sequence[Dict[str, Any]]] = None,
                now: Optional[float] = None) -> Dict[str, Any]:
        """Live authorisation, split by whether MAYA can see the engine.

        The number `warrant.flavour` was written for and never asked to give.
        """
        rows = self.db.query(
            "SELECT model_id, principal, environment, flavour "
            "FROM warrant WHERE revoked = 0")
        estate = {m["id"]: m for m in (models if models is not None
                                       else self.registry.list())}
        by_flavour: Dict[str, int] = {}
        unobserved: List[Dict[str, Any]] = []
        for row in rows:
            flavour = row.get("flavour") or UNOBSERVED
            by_flavour[flavour] = by_flavour.get(flavour, 0) + 1
            if flavour != UNOBSERVED:
                continue
            model = estate.get(row["model_id"])
            if model is None:
                continue
            unobserved.append({
                "urn": model["urn"], "name": model.get("name"),
                "tier": model.get("tier"),
                "principal": row["principal"],
                "environment": row["environment"],
            })
        escalating = [u for u in unobserved
                      if u["tier"] is not None
                      and u["tier"] <= ESCALATE_AT_OR_ABOVE]
        total = sum(by_flavour.values())
        return {
            "live_warrants": total,
            "by_flavour": by_flavour,
            "unobserved": len(unobserved),
            "unobserved_at_tier": escalating,
            "share_unobserved": (round(len(unobserved) / total, 3)
                                 if total else 0.0),
            "escalate_at_or_above": ESCALATE_AT_OR_ABOVE,
            "detail": self._detail(total, len(unobserved), len(escalating)),
            "does_not_prove": (
                "that any engine behaved. MAYA does not run models, so nothing "
                "here observes an engine honouring or ignoring the operating "
                "boundary it was given — this counts how much of the estate is "
                "governed by a document rather than by an observation"),
        }

    def authorised_and_silent(
            self, models: Optional[Sequence[Dict[str, Any]]] = None,
            now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Live warrants whose models have reported nothing back.

        The one symptom of C-6's attack that MAYA is positioned to see, because
        both halves are in its own records: it issued the warrant, and it
        received no telemetry.

        Returned with `explanation_absent` rather than a verdict. A model that
        is authorised and unused looks identical from here, and saying
        otherwise would be the platform inferring misbehaviour from its own
        silence.
        """
        if self.telemetry is None:
            return []
        estate = list(models if models is not None else self.registry.list())
        report = self.telemetry.estate(estate, now=now)
        quiet = {(r["model"], r.get("semver")) for r in report["versions"]
                 if r["never"] or r["silent"]}
        if not quiet:
            return []
        by_id = {m["id"]: m for m in estate}
        out: List[Dict[str, Any]] = []
        for row in self.db.query(
                "SELECT model_id, principal, environment, flavour "
                "FROM warrant WHERE revoked = 0"):
            model = by_id.get(row["model_id"])
            if model is None:
                continue
            silent = [q for q in quiet if q[0] == model["urn"]]
            if not silent:
                continue
            out.append({
                "urn": model["urn"], "name": model.get("name"),
                "tier": model.get("tier"),
                "principal": row["principal"],
                "environment": row["environment"],
                "flavour": row.get("flavour") or UNOBSERVED,
                "versions": sorted(v for _, v in silent if v),
                "explanation_absent": (
                    "authorised and reporting nothing. This is equally "
                    "consistent with an engine that is ignoring its telemetry "
                    "obligation and with a warrant nobody has used, and MAYA "
                    "cannot tell those apart from here"),
            })
        return out

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _detail(total: int, unobserved: int, escalating: int) -> str:
        if not total:
            return ("no live warrants, so nothing is being executed under this "
                    "register's authority")
        if not unobserved:
            return (f"all {total} live warrant(s) carry a runtime the platform "
                    f"can locate; none is descriptor-only")
        parts = [f"{unobserved} of {total} live warrant(s) are "
                 f"descriptor-only — MAYA holds the governance and somebody "
                 f"else holds the model"]
        if escalating:
            parts.append(f"{escalating} of those are at tier "
                         f"{ESCALATE_AT_OR_ABOVE} or above, where this "
                         f"platform's controls stop being advisory")
        return "; ".join(parts)
