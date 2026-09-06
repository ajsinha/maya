"""
MAYA — contract–serving agreement, law L-17.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

`L-17` says: for every active warrant, the feature namespace **served** equals
the namespace **pinned** by its contract. Half of that has always existed —
`FeatureContracts.serving_namespaces` computes what a version's contract pins.
The other half was recorded as blocked on an online feature store.

It was blocked on the wrong thing. An online store is a component on the serving
path, at request latency, and [10 §7](../../docs/10-roadmap.md) says in as many
words that MAYA will not own that: *governance on the serving path makes it the
bank's single point of failure. MAYA authorises; an engine acts.* Building the
store to satisfy the law would have put the platform exactly where its own
design says it must never be.

The engine already knows which namespaces it read. So it says so, and MAYA
compares — which is the shape of every other claim here. The platform does not
perform the act; it holds whoever did to what they said they did.

That distinction is the whole of the law's honesty. An attestation is evidence
that somebody asserted something, not proof that it happened, and this module
says so wherever it reports. What it *does* prove is disagreement: a serving
namespace that does not match the contract is caught here and nowhere else, and
training–serving skew is exactly that disagreement.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.features.common import FeatureError
from core.log import get_logger

logger = get_logger(__name__)


class ServingRegister:
    """What engines say they served, against what the contracts pin."""

    def __init__(self, attestations, contracts, registry, evidence: EvidenceEngine):
        self.attestations = attestations
        self.contracts = contracts
        self.registry = registry
        self.evidence = evidence

    # ------------------------------------------------------------- attesting
    def attest(self, urn: str, semver: str, served: Dict[str, str],
               warrant_id: Optional[str] = None,
               descriptor_id: Optional[str] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Record what an engine read, and compare it with what was pinned.

        Recorded whether or not it agrees. A disagreement that raised without
        being written down would be a disagreement the platform could not be
        asked about afterwards, and *we served the wrong namespace and then said
        we had not* is precisely the event this exists to make impossible to
        lose. The refusal comes after the write.
        """
        version = self.registry.version(urn, semver)
        if not version:
            raise FeatureError(f"no version {semver} for {urn}")
        pinned = self.contracts.serving_namespaces(version["id"])

        divergence = self.divergence(pinned, served)
        row = {
            "model_version_id": version["id"],
            "warrant_id": warrant_id, "descriptor_id": descriptor_id,
            "served": dict(served), "pinned": dict(pinned),
            "agrees": int(not divergence),
            "divergence": divergence,
            "detail": self._detail(pinned, served, divergence),
            "attested_by": actor, "attested_at": time.time(),
        }
        self.attestations.add(row)
        self.evidence.append(
            "serving_attested", "version", version["id"],
            {"agrees": not divergence, "views": sorted(served),
             "divergence": divergence, "warrant_id": warrant_id}, actor=actor)
        if divergence:
            logger.error("L-17 violated for %s@%s: %s", urn, semver,
                         row["detail"])
        return self.attestations.one(id=row["id"])

    @staticmethod
    def divergence(pinned: Dict[str, str],
                   served: Dict[str, str]) -> List[Dict[str, Any]]:
        """Every way the two disagree, named.

        Three ways, and they are different failures. A view pinned and not
        served is a model running on less than its contract says it reads. A
        view served and not pinned is a model running on data nobody approved.
        A view served at the wrong namespace is training–serving skew, which is
        the one that produces a number that looks right and is not.
        """
        out: List[Dict[str, Any]] = []
        for view in sorted(set(pinned) - set(served)):
            out.append({"view": view, "how": "pinned_but_not_served",
                        "pinned": pinned[view], "served": None})
        for view in sorted(set(served) - set(pinned)):
            out.append({"view": view, "how": "served_but_not_pinned",
                        "pinned": None, "served": served[view]})
        for view in sorted(set(pinned) & set(served)):
            if pinned[view] != served[view]:
                out.append({"view": view, "how": "different_namespace",
                            "pinned": pinned[view], "served": served[view]})
        return out

    @staticmethod
    def _detail(pinned: Dict[str, str], served: Dict[str, str],
                divergence: List[Dict[str, Any]]) -> str:
        if not divergence:
            return (f"{len(pinned)} namespace(s) served exactly as the contract "
                    f"pins them")
        how = ", ".join(f"{d['view']} ({d['how'].replace('_', ' ')})"
                        for d in divergence)
        return f"{len(divergence)} of {len(set(pinned) | set(served))}: {how}"

    # ---------------------------------------------------------------- reading
    def for_version(self, urn: str, semver: str,
                    limit: int = 50) -> List[Dict[str, Any]]:
        version = self.registry.version(urn, semver)
        if not version:
            raise FeatureError(f"no version {semver} for {urn}")
        return self.attestations.many(model_version_id=version["id"])[-limit:]

    def agreement(self, urn: str, semver: str) -> Dict[str, Any]:
        """`L-17` for one version, and the honest word for never attested.

        Three states, not two. `agrees` and `disagrees` are answers; `unattested`
        is the absence of one, and reporting it as agreement would be the exact
        failure this platform is written against — a control reporting success
        because nothing contradicted it.
        """
        rows = self.for_version(urn, semver)
        if not rows:
            return {"urn": urn, "semver": semver, "state": "unattested",
                    "attestations": 0, "holds": None,
                    "detail": "no engine has said what it served for this "
                              "version, so the law has nothing to compare and "
                              "is neither satisfied nor violated here"}
        latest = rows[-1]
        disagreeing = [r for r in rows if not r["agrees"]]
        return {
            "urn": urn, "semver": semver,
            "state": "agrees" if not disagreeing else "disagrees",
            "holds": not disagreeing,
            "attestations": len(rows), "disagreeing": len(disagreeing),
            "latest": latest,
            "detail": (f"{len(rows)} attestation(s), all agreeing with the "
                       f"contract" if not disagreeing else
                       f"{len(disagreeing)} of {len(rows)} attestation(s) "
                       f"disagree with the contract"),
        }

    def estate(self, versions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """The law across an estate, with the unattested counted separately.

        A summary that folded `unattested` into `holds` would report an estate
        nobody has attested as fully compliant, which is the shape of every
        defect this codebase has a name for.
        """
        agreeing, disagreeing, silent = [], [], []
        for version in versions:
            rows = self.attestations.many(model_version_id=version["id"])
            if not rows:
                silent.append(version)
            elif any(not r["agrees"] for r in rows):
                disagreeing.append(version)
            else:
                agreeing.append(version)
        return {
            "versions": len(versions), "agreeing": len(agreeing),
            "disagreeing": len(disagreeing), "unattested": len(silent),
            "holds": not disagreeing,
            "detail": (f"{len(agreeing)} attested and agreeing, "
                       f"{len(disagreeing)} disagreeing, "
                       f"{len(silent)} never attested — the last of which is "
                       f"not agreement, it is silence"),
        }
