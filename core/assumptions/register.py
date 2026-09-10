"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model relies on being true, stated where it can be counted.

The sibling of `core.limitations`, and the distinction between them is not
pedantry — it decides where a row belongs and what question it answers.

A **limitation** is a boundary of competence: *LGD is a flat haircut and is not
modelled*. It is what the model **is**, and it cannot stop being true.

An **assumption** is a claim about the world the model reads: *the sector mix is
stable*, *borrowers prepay when it is rational to*, *the temperature at serving
time is as accurate as the temperature it was fitted on*. And the property that
matters to a supervisor is that **an assumption can stop being true while the
model is running.**

So the counting question is different. The limitation register counts what is
*enforced* against what is only *written down*. This one counts what is
**monitored** against what is **merely believed** — `monitor_id` names the
monitor that tests whether the assumption still holds, and *null* is the value
worth having, because it is the count of things the platform believes on
nobody's authority and would not notice becoming false.

That is the SS1/23 1.2(c)(ii) question asked the way a register can answer it.
An assumption in a PDF is a sentence; an assumption with a monitor is a control;
and an assumption with neither is the one that ends up in the post-mortem.

Three things this deliberately does not do. It does not parse the statement —
an assumption is prose, and a check that passed on nonsense would be worse than
no check. It does not refuse a version for holding unmonitored assumptions,
because most assumptions genuinely cannot be monitored and a control people
route around by writing none down is strictly worse than a register nobody
queries. And it does not invent the monitor: naming one that does not exist is
refused, for the same reason a limitation may not claim a contract clause that
is not there — a false claim of coverage reads as the safe case.

Assumptions attach to a **version**, because that is the immutable thing they
are about. An assumption recorded against "the model" would survive the version
that stopped depending on it.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.registry.common import RegistryError

#: The five kinds, which are the five places an assumption comes from. Closed,
#: because an open list becomes a free-text field with extra steps — the same
#: reasoning as the limitation register's four, and a different five because
#: they answer a different question.
KINDS: tuple = ("data", "behavioural", "market", "structural", "operational")

KIND_MEANING: Dict[str, str] = {
    "data": "that the process generating the data goes on looking like the "
            "sample — a mix, a definition, a collection practice",
    "behavioural": "that the people in the model go on acting as they did — "
                   "prepaying, drawing, defaulting, complaining",
    "market": "about the structure of the prices, rates or liquidity the model "
              "reads — a curve that is arbitrage-free, a spread that is "
              "observable, a market that clears",
    "structural": "about the model's own form — a distribution, a functional "
                  "shape, an independence, a stationarity",
    # The one most often missing, and the one case study 13 is about: a model
    # backtested on observed weather and served a forecast is relying on
    # something nobody wrote down.
    "operational": "about the conditions it runs in rather than the world it "
                   "describes — that an input at serving time is what it was "
                   "at fitting time, that a feed arrives, that a lag holds",
}

#: How hard this one is to be wrong about. Ordered, because the estate view
#: sorts on it and a supervisor reads the top of that list first.
MATERIALITIES: tuple = ("low", "moderate", "material", "critical")


class AssumptionRegister:
    """Records, withdraws and counts what a version relies on being true."""

    def __init__(self, repo, registry, evidence: EvidenceEngine,
                 monitors=None, findings=None, overlays=None):
        self.repo, self.registry, self.evidence = repo, registry, evidence
        # Three repositories, passed rather than imported so that this module
        # does not depend on the subsystems it points at — the same discipline
        # `core.monitoring` applies to the fibres it reads.
        #
        # All three exist for one reason: every id this register accepts names
        # something in another subsystem, and an id nobody checks is a link
        # that silently does not exist. A row saying it is watched by a monitor,
        # tracked by a finding and compensated by an overlay, all three of them
        # dangling, reads as the best-governed assumption on the estate.
        self.monitors, self.findings, self.overlays = monitors, findings, overlays

    # ------------------------------------------------------------------ write
    def record(self, urn: str, semver: str, kind: str, statement: str,
               *, basis: str = "", monitor_id: Optional[str] = None,
               owner: str = "", materiality: str = "moderate",
               mitigation: str = "", review_due: Optional[float] = None,
               finding_id: Optional[str] = None,
               overlay_id: Optional[str] = None,
               actor: str = "system") -> Dict[str, Any]:
        """State an assumption against one version.

        `monitor_id` is checked against the monitors that actually exist on
        this model rather than accepted: an assumption claiming to be watched by
        a monitor that is not there is the worst of the three states, because it
        reads as the safe one.
        """
        if kind not in KINDS:
            raise RegistryError(
                f"'{kind}' is not a kind of assumption; the five are "
                f"{', '.join(KINDS)} — which are the five places one comes "
                f"from, and the list is closed because an open one becomes a "
                f"free-text field with extra steps")
        if not (statement or "").strip():
            raise RegistryError(
                "an assumption with no statement records that something is "
                "being relied on and not what")
        if materiality not in MATERIALITIES:
            raise RegistryError(
                f"'{materiality}' is not a materiality; the four are "
                f"{', '.join(MATERIALITIES)}")

        model = self.registry.require(urn)
        version = self.registry.version_service.require(urn, semver)

        if monitor_id:
            self._require_monitor_on(model["id"], monitor_id, urn)
        if finding_id:
            self._require_link(self.findings, finding_id, model["id"], urn,
                               "finding", "tracked by")
        if overlay_id:
            self._require_link(self.overlays, overlay_id, model["id"], urn,
                               "overlay", "compensated by")

        existing = self.repo.many(model_version_id=version["id"])
        row = {"model_id": model["id"], "model_version_id": version["id"],
               "reference": f"ASM-{len(existing) + 1:04d}",
               "kind": kind, "statement": statement.strip(),
               "monitor_id": monitor_id, "basis": basis,
               "owner": owner or actor, "materiality": materiality,
               "mitigation": mitigation, "review_due": review_due,
               "finding_id": finding_id, "overlay_id": overlay_id,
               "raised_by": actor, "created_at": time.time()}
        with self.evidence.recording():
            stored = self.repo.add(row)
            self.evidence.append("assumption_recorded", "model_version",
                                 version["id"],
                                 {"reference": row["reference"], "kind": kind,
                                  "monitored": int(bool(monitor_id)),
                                  "materiality": materiality,
                                  "statement": statement.strip()},
                                 actor=actor)
        return stored

    def _require_monitor_on(self, model_id: str, monitor_id: str,
                            urn: str) -> None:
        """The monitor must exist, and must be on THIS model.

        Both halves matter. A monitor that does not exist is the obvious error;
        a monitor that exists on a different model is the one that would
        otherwise pass, and it would leave an assumption reporting itself as
        watched by something looking at somebody else's scores.
        """
        if self.monitors is None:
            return                      # not wired: no opinion rather than a wrong one
        found = self.monitors.one(id=monitor_id)
        if not found:
            raise RegistryError(
                f"this assumption says it is tested by monitor '{monitor_id}', "
                f"and no such monitor exists. An assumption claiming a watch "
                f"that is not there is worse than one claiming none, because "
                f"it reads as the safe case")
        if found.get("model_id") != model_id:
            raise RegistryError(
                f"monitor '{monitor_id}' is defined on another model, so it "
                f"cannot be what tests an assumption of {urn}. An assumption "
                f"watched by somebody else's monitor is unwatched, and reads "
                f"as watched")

    def _require_link(self, repo, row_id: str, model_id: str, urn: str,
                      what: str, verb: str) -> None:
        """A named finding or overlay must exist, and be on THIS model.

        Same shape as the monitor check and for the same reason: the failure
        that matters is not the dangling id, which is obvious, but the id that
        resolves to another model's row — an assumption `compensated by`
        somebody else's overlay is uncompensated, and reads as covered.
        """
        if repo is None:
            return                      # not wired: no opinion rather than a wrong one
        found = repo.one(id=row_id)
        if not found:
            raise RegistryError(
                f"this assumption says it is {verb} {what} '{row_id}', and no "
                f"such {what} exists. A link that resolves to nothing reads as "
                f"coverage and is not")
        if found.get("model_id") != model_id:
            raise RegistryError(
                f"{what} '{row_id}' is on another model, so it cannot be what "
                f"{verb.split()[0]}s an assumption of {urn}. An assumption "
                f"{verb} somebody else's {what} is uncovered, and reads as "
                f"covered")

    def withdraw(self, assumption_id: str, reason: str,
                 actor: str = "system") -> Dict[str, Any]:
        """An assumption no longer relied on is withdrawn, never deleted.

        The version it describes is immutable, so the assumption's history is
        part of what that version was understood to be — and *we used to believe
        the sector mix was stable* is exactly the sentence a post-mortem needs
        to find.
        """
        row = self.require(assumption_id)
        if row.get("withdrawn_at"):
            raise RegistryError(
                f"{row['reference']} was already withdrawn; withdrawing it "
                f"again would record a second decision nobody made")
        if not (reason or "").strip():
            raise RegistryError(
                "withdrawing an assumption needs a reason: it was stated "
                "against an immutable version, so removing it without one "
                "leaves the register saying less than it did with no record of "
                "why")
        with self.evidence.recording():
            self.repo.set({"withdrawn_at": time.time(), "withdrawn_by": actor,
                           "withdrawal_reason": reason.strip()},
                          id=assumption_id)
            self.evidence.append("assumption_withdrawn", "model_version",
                                 row["model_version_id"],
                                 {"reference": row["reference"],
                                  "reason": reason}, actor=actor)
        return self.require(assumption_id)

    # ------------------------------------------------------------------- read
    def require(self, assumption_id: str) -> Dict[str, Any]:
        row = self.repo.one(id=assumption_id)
        if not row:
            raise RegistryError(f"no assumption '{assumption_id}'")
        return row

    def for_version(self, urn: str, semver: str) -> Dict[str, Any]:
        """Every assumption on one version, and the count that matters."""
        version = self.registry.version_service.require(urn, semver)
        rows = list(self.repo.many(model_version_id=version["id"]))
        standing = [r for r in rows if not r.get("withdrawn_at")]
        return {"urn": urn, "semver": semver, "assumptions": rows,
                **self._counts(standing)}

    def across_the_estate(self) -> Dict[str, Any]:
        """Every standing assumption on every model, and how much is watched.

        Sorted worst-first, and 'worst' is deliberately not 'most'. A version
        with four assumptions nobody monitors is a worse read than one with
        twelve that are all watched, and a *material* unmonitored assumption is
        worse than a low one — so the sort is unmonitored-material first.
        """
        rows = [r for r in self.repo.many() if not r.get("withdrawn_at")]
        by_version: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            by_version.setdefault(row["model_version_id"], []).append(row)

        versions = []
        for version_id, found in by_version.items():
            versions.append({**self._describe_version(version_id),
                             "assumptions": found, **self._counts(found)})
        versions.sort(key=lambda v: (-v["unmonitored_material"],
                                     -v["unmonitored"], -v["standing"],
                                     v.get("urn") or ""))
        return {"versions": versions,
                "models": len({v.get("urn") for v in versions}),
                **self._counts(rows)}

    # ---------------------------------------------------------------- shaping
    def _counts(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        monitored = [r for r in rows if r.get("monitor_id")]
        believed = [r for r in rows if not r.get("monitor_id")]
        #: The number this register exists to surface: an assumption that is
        #: material or worse AND that nothing is watching.
        grave = [r for r in believed
                 if r.get("materiality") in ("material", "critical")]
        return {
            "standing": len(rows),
            "monitored": len(monitored),
            "unmonitored": len(believed),
            "unmonitored_material": len(grave),
            "by_kind": {k: sum(1 for r in rows if r["kind"] == k)
                        for k in KINDS if any(r["kind"] == k for r in rows)},
            "by_materiality": {m: sum(1 for r in rows
                                      if r.get("materiality") == m)
                               for m in MATERIALITIES
                               if any(r.get("materiality") == m for r in rows)},
            "unmitigated": sum(1 for r in grave
                               if not (r.get("mitigation") or "").strip()),
            "detail": self._detail(len(rows), len(monitored), len(believed),
                                   len(grave)),
        }

    def _describe_version(self, version_id: str) -> Dict[str, Any]:
        """The urn and semver an assumption hangs off, for a reader."""
        version = self.registry.version_by_id(version_id)
        if not version:
            return {"model_version_id": version_id, "urn": None, "semver": None}
        return {"model_version_id": version_id, "urn": version.get("urn"),
                "semver": version.get("semver")}

    @staticmethod
    def _detail(standing: int, monitored: int, believed: int,
                grave: int) -> str:
        if not standing:
            return ("no assumptions recorded — which is a claim about the "
                    "model, not an absence of one")
        head = (f"{standing} standing: {monitored} tested by a monitor, "
                f"{believed} believed and unwatched")
        if grave:
            return (f"{head}. {grave} of the unwatched "
                    f"{'is' if grave == 1 else 'are'} material or worse, "
                    f"which is the count worth acting on")
        return head
