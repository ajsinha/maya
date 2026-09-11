"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model version's contract actually depends on, and whether anything stops
it.

## The defect, which is a shape rather than a missing feature

Two requirements were marked *Partial* with almost the same sentence.

`FR-FEA-013` — tag protected characteristics and known proxies, and **prohibit
direct use** in in-scope credit models. `pii`, `sensitivity`, `protected_basis`
and `proxy_risk` are columns on every feature. *No policy enforces anything.*

`FR-FEA-014` — certification levels, **with policy tying production models to
certified features by tier**. `experimental`, `certified` and `deprecated` exist
as a lifecycle act with its own permission. *No policy keys on it.*

A `protected_basis` column that nothing reads is a control that exists in a
screenshot. It is worse than an absent column, because the absent one is
obviously absent: a tagged estate looks governed, and a reviewer who sees the
tag reasonably assumes something acts on it.

## What this adds, and what it refuses to decide

**It computes the facts and does not set the rule.**

`core/policy/` is where a firm's rules live, and the architecture there is
deliberate — a rule is a predicate over a closed vocabulary of *published
facts*, and policy may refuse but may never permit. What was missing was not a
rule. It was the facts: nothing in the gate vocabulary could see what a
version's contract binds, so no rule could be written about it however much a
firm wanted one.

So this walks contract → view version → features, and publishes four facts —
`binds_protected_basis`, `binds_proxy_risk`, `binds_uncertified`,
`lowest_certification`. A firm writes the rule.

**It will not ship a hardcoded refusal**, and the reason is the requirement's
own wording: *prohibit direct use in in-scope credit models while permitting
controlled use for fairness testing*. Which models are in scope, and what
counts as fairness testing, are facts about an institution's obligations under
its own regulator. A platform that refused on `protected_basis` alone would
refuse the fairness testing the same regulation requires.

## The part that matters most

**It reports the exposure whether or not a rule exists.**

That is the answer to the defect one level up. If MAYA only offered facts, a
firm that never wrote the rule would be exactly where it started — tagged and
unenforced — and would have no way to find out. So `across_the_estate` counts
the models binding a protected characteristic **and** says whether any active
rule refuses on it.

> *Nineteen approved models bind a protected characteristic, and no rule in
> force refuses one* is a sentence a second line can act on. It does not exist
> in a platform that only offers a vocabulary.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.features.catalogue import LEVELS
from core.features.common import FeatureError
from core.log import get_logger

logger = get_logger(__name__)

#: The facts this publishes into the gate vocabulary. Each is a property of
#: what a version's contract BINDS rather than of the version itself, which is
#: why nothing could see them before: a contract pins views, and the sensitivity
#: is on the features inside them.
FACTS: Tuple[Tuple[str, str], ...] = (
    ("binds_protected_basis",
     "the contract binds a feature tagged as a protected characteristic"),
    ("binds_proxy_risk",
     "the contract binds a feature tagged as a known proxy for one. Recorded "
     "separately because a proxy is the harder case: it is not obviously a "
     "protected characteristic, and a model built on one is discriminating "
     "without any column saying so"),
    ("binds_uncertified",
     "the contract binds a feature that is not `certified` — experimental or "
     "deprecated"),
    ("lowest_certification",
     "the weakest certification among everything the contract binds. A model "
     "is no better certified than its least certified input"),
    ("binds_pii",
     "the contract binds a feature carrying personal data"),
)

#: How certification orders, worst first. `deprecated` is worse than
#: `experimental` and not better: an experimental feature is one nobody has
#: vouched for yet, and a deprecated one is one somebody has vouched AGAINST.
WORST_FIRST: Tuple[str, ...] = ("deprecated", "experimental", "certified")


class ContractScreening:
    """What a version's contract binds, as facts a policy rule can read."""

    def __init__(self, contracts, views, view_versions, features,
                 registry=None, policies=None):
        self.contracts, self.views = contracts, views
        self.view_versions, self.features = view_versions, features
        self.registry, self.policies = registry, policies

    # --------------------------------------------------------------- posture
    @staticmethod
    def posture() -> Dict[str, Any]:
        """What this computes, and the decision it refuses to make."""
        return {
            "decides_anything": False,
            "facts": [{"fact": f, "means": m} for f, m in FACTS],
            "certification_order": list(WORST_FIRST),
            "why_no_default_rule": (
                "the requirement says *prohibit direct use in in-scope credit "
                "models while permitting controlled use for fairness "
                "testing*. Which models are in scope, and what counts as "
                "fairness testing, are facts about an institution's "
                "obligations under its own regulator. A platform refusing on "
                "`protected_basis` alone would refuse the fairness testing "
                "the same regulation requires"),
            "what_was_missing": (
                "not a rule — the FACTS. A rule here is a predicate over a "
                "closed vocabulary of published facts, and nothing in that "
                "vocabulary could see what a version's contract binds, so no "
                "rule could be written about it however much a firm wanted "
                "one"),
            "detail": (
                "a `protected_basis` column that nothing reads is a control "
                "that exists in a screenshot — and it is worse than an absent "
                "column, because the absent one is obviously absent. A tagged "
                "estate looks governed, and a reviewer who sees the tag "
                "reasonably assumes something acts on it"),
        }

    # ------------------------------------------------------------- the facts
    def facts_for(self, model_version_id: str) -> Dict[str, Any]:
        """The four facts, for one version. Empty-but-explicit when unbound.

        A version with no feature contract is normal rather than an error — a
        descriptor-only vendor model has none — so this answers `False` on
        every flag and says the contract is absent, which is a different thing
        from a contract that binds nothing sensitive.
        """
        contract = self.contracts.one(model_version_id=model_version_id)
        if contract is None:
            return {**_clear(), "has_contract": False,
                    "detail": ("this version binds no feature contract. Every "
                               "flag is false because there is nothing to "
                               "screen, which is NOT the same as a contract "
                               "that binds nothing sensitive")}
        bound = self.bound_features(contract)
        protected = [f["name"] for f in bound if f.get("protected_basis")]
        proxies = [f["name"] for f in bound
                   if (f.get("proxy_risk") or "none") != "none"]
        pii = [f["name"] for f in bound if f.get("pii")]
        uncertified = [f["name"] for f in bound
                       if (f.get("certification") or "experimental")
                       != "certified"]
        return {
            "has_contract": True,
            "features": len(bound),
            "binds_protected_basis": bool(protected),
            "binds_proxy_risk": bool(proxies),
            "binds_pii": bool(pii),
            "binds_uncertified": bool(uncertified),
            "lowest_certification": _lowest(bound),
            "protected": protected, "proxies": proxies,
            "pii": pii, "uncertified": uncertified,
            "detail": self._detail(bound, protected, proxies, uncertified),
        }

    def bound_features(self, contract: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Every feature reachable through this contract's pinned views.

        Walked at the **pinned version** rather than the view's current one. A
        view that gained a protected characteristic after this contract was
        bound has not changed what this version reads, and reporting it would
        be a finding about a model that never saw the column.
        """
        seen: Dict[str, Dict[str, Any]] = {}
        for item in contract.get("items") or []:
            for name in self._names_at(item):
                if name in seen:
                    continue
                row = self.features.one(name=name)
                if row is None:
                    logger.warning(
                        "contract binds '%s', which is not in the catalogue",
                        name)
                    continue
                seen[name] = row
        return list(seen.values())

    def _names_at(self, item: Dict[str, Any]) -> Sequence[str]:
        version = self.view_versions.one(
            feature_view_id=item.get("feature_view_id"),
            version=item.get("version"))
        return list((version or {}).get("features") or [])

    @staticmethod
    def _detail(bound: Sequence[Dict[str, Any]], protected: Sequence[str],
                proxies: Sequence[str], uncertified: Sequence[str]) -> str:
        out = f"{len(bound)} feature(s) reachable through this contract"
        if protected:
            out += (f". **Binds {len(protected)} protected characteristic(s)**: "
                    f"{', '.join(protected[:4])}")
        if proxies:
            out += (f". Binds {len(proxies)} known proxy/proxies: "
                    f"{', '.join(proxies[:4])} — the harder case, because a "
                    f"proxy is not obviously a protected characteristic and a "
                    f"model built on one is discriminating without any column "
                    f"saying so")
        if uncertified:
            out += (f". {len(uncertified)} are not certified: "
                    f"{', '.join(uncertified[:4])}")
        if not (protected or proxies or uncertified):
            out += ", none tagged sensitive and all certified"
        out += (". These are FACTS. Whether any of them refuses anything is a "
                "rule this firm writes")
        return out

    # ------------------------------------------------------ across the estate
    def across_the_estate(self) -> Dict[str, Any]:
        """How exposed this estate is, and whether any rule refuses on it.

        The second half is the point. A platform that published facts and left
        it there would leave a firm that never wrote the rule exactly where it
        started — tagged and unenforced — with no way to find out.
        """
        if self.registry is None:
            raise FeatureError("this service cannot see the estate; wire the "
                               "model registry")
        rows, protected, proxies, uncertified = [], [], [], []
        for model in self.registry.list():
            for version in self.registry.versions(model["urn"]):
                facts = self.facts_for(version["id"])
                if not facts["has_contract"]:
                    continue
                if not (facts["binds_protected_basis"]
                        or facts["binds_proxy_risk"]
                        or facts["binds_uncertified"]):
                    continue
                row = {"urn": model["urn"], "semver": version.get("semver"),
                       "status": version.get("status"),
                       "tier": model.get("tier"),
                       "protected": facts["protected"],
                       "proxies": facts["proxies"],
                       "uncertified": facts["uncertified"]}
                rows.append(row)
                if facts["binds_protected_basis"]:
                    protected.append(model["urn"])
                if facts["binds_proxy_risk"]:
                    proxies.append(model["urn"])
                if facts["binds_uncertified"]:
                    uncertified.append(model["urn"])
        enforced = self.enforced_by()
        return {
            "versions": rows, "count": len(rows),
            "binding_protected_basis": sorted(set(protected)),
            "binding_proxy_risk": sorted(set(proxies)),
            "binding_uncertified": sorted(set(uncertified)),
            "enforced_by": enforced,
            "detail": self._estate_detail(protected, proxies, uncertified,
                                          enforced),
        }

    #: The gates where a rule could act on these facts. `warrant:resolve` is
    #: deliberately absent: refusing a resolution for a feature the model was
    #: APPROVED with would take a model out of production for a decision
    #: somebody already made, at the worst possible moment.
    GATES: Tuple[str, ...] = ("version:approve", "alias:move")

    def enforced_by(self) -> Dict[str, List[str]]:
        """Which rules in force read these facts, per fact.

        Read from the rules actually in force rather than assumed. The answer
        *no rule reads this* is the one worth having, and it is only obtainable
        by looking — the whole defect being closed is a tag nobody reads.

        Matched on the rule's source text, which is a blunt instrument and the
        honest one available: the rule language has no reflection API, and a
        fact named in a rule that never evaluates would still be *read* in the
        sense that matters here — somebody wrote it down.
        """
        found: Dict[str, List[str]] = {f: [] for f, _ in FACTS}
        if self.policies is None:
            return found
        for gate in self.GATES:
            try:
                published = self.policies.in_force(gate)
            except Exception as exc:             # pragma: no cover - defensive
                logger.warning("could not read the rule in force for %s: %s",
                               gate, exc)
                continue
            if not published:
                continue
            source = str(published.get("rule") or "")
            for fact, _ in FACTS:
                if fact in source:
                    found[fact].append(gate)
        return found

    @staticmethod
    def _estate_detail(protected: Sequence[str], proxies: Sequence[str],
                       uncertified: Sequence[str],
                       enforced: Dict[str, List[str]]) -> str:
        unique = len(set(protected))
        out = (f"{unique} model(s) bind a protected characteristic, "
               f"{len(set(proxies))} bind a known proxy, and "
               f"{len(set(uncertified))} bind an uncertified feature")
        unenforced = [f for f, rules in enforced.items() if not rules]
        if unique and not enforced.get("binds_protected_basis"):
            out += (". **No rule in force refuses on `binds_protected_basis`**, "
                    "so the tag is recorded and nothing acts on it — which is "
                    "a control that exists in a screenshot, and worse than an "
                    "absent column because a tagged estate looks governed")
        elif unique:
            out += (f". Refused by {', '.join(enforced['binds_protected_basis'])}")
        if len(unenforced) == len(FACTS):
            out += (". None of these facts is read by any rule in force. They "
                    "are published so a rule CAN be written; writing it is "
                    "this firm's decision, and this sentence is how a second "
                    "line finds out it has not been")
        return out


def _clear() -> Dict[str, Any]:
    return {"features": 0, "binds_protected_basis": False,
            "binds_proxy_risk": False, "binds_pii": False,
            "binds_uncertified": False, "lowest_certification": None,
            "protected": [], "proxies": [], "pii": [], "uncertified": []}


def _lowest(bound: Sequence[Dict[str, Any]]) -> Optional[str]:
    """The weakest certification among everything bound.

    A model is no better certified than its least certified input, and the
    order puts `deprecated` below `experimental` deliberately: experimental is
    *nobody has vouched for this yet*, and deprecated is *somebody has vouched
    against it*.
    """
    if not bound:
        return None
    levels = {(f.get("certification") or "experimental") for f in bound}
    for level in WORST_FIRST:
        if level in levels:
            return level
    # A level outside the vocabulary. Reported rather than ranked, because
    # ranking an unknown would put it somewhere by accident.
    unknown = sorted(levels - set(LEVELS))
    logger.warning("features carry certification levels outside the "
                   "vocabulary: %s", unknown)
    return unknown[0] if unknown else None
