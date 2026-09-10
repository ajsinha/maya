"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Who is downstream of a feature, and the only answer that is actionable.

Before a feature changes or is deprecated, somebody has to know what it reaches.
The reference index already answers a version of this and stops at the model:
*eleven versions and two featuresets refer to this*. That answer looks complete
and cannot be acted on.

**A count of models is not an impact assessment.** *Eleven models* tells a
feature owner nothing they can take to anybody. What they need is the other end
of the chain:

    feature -> view -> featureset version -> parameter set -> model version
            -> grant -> DECLARED USE

**The declared use is where the sentence becomes a decision.** *This feature
feeds the origination decision for retail mortgages, under three live grants
held by two services, one of which is tier 1* is a sentence a person can act
on. It names who has to be told, what they will not be able to do, and how
urgent it is. The eleven-models answer names none of that.

**And a live grant is different from a version.** A version referring to a
feature is a historical fact; a live grant is somebody who will call tomorrow
and get a different answer. The two are reported apart, because the first is a
migration and the second is an outage.

**Restatement is the same traversal, entered from the other end.** The platform
already detects that a view has been written to since a version pinned it ---
`restated()` compares the pin against current and `restatements()` names which
slots moved. What it did not do was walk forward: *which models were fitted from
this, and which decisions were made under them*. A restatement whose blast
radius nobody computed is a correction that quietly invalidates a year of
output, and BCBS 239 asks for exactly this traversal by another name.

**What this cannot reach, and says so.** It reaches the *decision-making
authority* --- the grant and the use --- and not the decisions. Whether the
model was actually called under that grant is invocation telemetry, and whether
the answer reached a customer is outside the register entirely. Reporting a
count of affected decisions would be reporting a number MAYA does not have.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.log import get_logger

logger = get_logger(__name__)

#: What a downstream consumer is, in increasing order of urgency. A version is
#: history; a grant is somebody who will call tomorrow.
HISTORICAL, LIVE = "historical", "live"


class FeatureImpact:
    """Walks a feature forward to the uses that rest on it."""

    def __init__(self, features, registry, parameters=None, warrants=None,
                 uses=None, invocations=None):
        self.features, self.registry = features, registry
        self.parameters, self.warrants = parameters, warrants
        self.uses, self.invocations = uses, invocations

    # ---------------------------------------------------------------- feature
    def of_feature(self, name: str,
                   now: Optional[float] = None) -> Dict[str, Any]:
        """Everything downstream of one feature, ending at the declared use."""
        moment = now if now is not None else time.time()
        self.features.catalogue.require(name)
        views = self._views_holding(name)
        chains = []
        for version in self._featureset_versions_binding(name):
            chains += self._forward(version, moment)
        return self._shape(name, "feature", views, chains, moment)

    # ------------------------------------------------------------------- view
    def of_view(self, view_name: str,
                now: Optional[float] = None) -> Dict[str, Any]:
        """Everything downstream of one materialised view."""
        moment = now if now is not None else time.time()
        chains = []
        for version in self._featureset_versions_on_view(view_name):
            chains += self._forward(version, moment)
        return self._shape(view_name, "feature_view", [view_name], chains,
                           moment)

    # ------------------------------------------------------------ restatement
    def of_restatement(self, view_name: str, version: int,
                       now: Optional[float] = None) -> Dict[str, Any]:
        """What a restatement of this view version reaches.

        The detection half already existed. This is the walk forward that did
        not: a correction to a stale row is a legitimate act, and a correction
        nobody traced is one that quietly invalidates every parameter set fitted
        from it and every authority resting on those.
        """
        moment = now if now is not None else time.time()
        moved = self.features.views.restated(view_name, version)
        downstream = self.of_view(view_name, now=moment)
        return {
            **downstream,
            "view": view_name, "pinned_version": version,
            "restated": bool(moved.get("restated")),
            "movement": moved,
            "detail": (
                (f"this view has been written to since version {version} was "
                 f"pinned. " if moved.get("restated") else
                 f"version {version} of this view is still what it was when it "
                 f"was pinned, so nothing below is affected yet — the walk is "
                 f"here so the question can be asked before the correction "
                 f"rather than after. ")
                + downstream["detail"]),
        }

    # -------------------------------------------------------------- traversal
    def _views_holding(self, feature: str) -> List[str]:
        out = []
        for view in self.features.views.views.many():
            if feature in (view.get("features") or []):
                out.append(view["name"])
        return sorted(out)

    def _featureset_versions(self) -> List[Dict]:
        """Every featureset version, or none where no registry is wired.

        Guarded rather than assumed: an instance built without the featureset
        registry can still answer *which views hold this feature*, and half an
        answer with the missing half named is better than an AttributeError
        from inside a governance report.
        """
        sets = getattr(self.features, "sets", None)
        return list(sets.versions.many()) if sets is not None else []

    def _featureset_versions_binding(self, feature: str) -> List[Dict]:
        out = []
        for row in self._featureset_versions():
            for binding in (row.get("bindings") or {}).values():
                bound = (binding.get("feature") if isinstance(binding, dict)
                         else binding)
                if bound == feature:
                    out.append(row)
                    break
        return out

    def _featureset_versions_on_view(self, view_name: str) -> List[Dict]:
        out = []
        for row in self._featureset_versions():
            for binding in (row.get("bindings") or {}).values():
                if isinstance(binding, dict) and binding.get("view") == view_name:
                    out.append(row)
                    break
        return out

    def _forward(self, featureset_version: Dict[str, Any],
                 moment: float) -> List[Dict[str, Any]]:
        """From a featureset version to every use resting on it."""
        if self.parameters is None:
            return []
        out = []
        for point in self.parameters.parameters.many(
                featureset_version_id=featureset_version["id"]):
            model = self.registry.catalogue.by_id(point.get("model_id"))
            if not model:
                continue
            version = (self.registry.version_by_id(point["model_version_id"])
                       if point.get("model_version_id") else None)
            out.append({
                "featureset_version": featureset_version["id"],
                "parameter_set": point["id"],
                "parameter_state": point.get("state"),
                "urn": model["urn"], "name": model.get("name"),
                "tier": model.get("tier"),
                "semver": (version or {}).get("semver"),
                "grants": self._grants(model, moment),
            })
        return out

    def _grants(self, model: Dict[str, Any],
                moment: float) -> List[Dict[str, Any]]:
        """The authorities resting on this model, and what each is FOR."""
        if self.warrants is None:
            return []
        out = []
        for grant in self.warrants.grants.of_model(model["urn"]):
            out.append({
                "grant": grant["id"],
                "principal": grant.get("principal"),
                "environment": grant.get("environment"),
                "declared_use": grant.get("declared_use"),
                "state": HISTORICAL if grant.get("revoked") else LIVE,
            })
        return out

    # ---------------------------------------------------------------- shaping
    def _shape(self, subject: str, kind: str, views: List[str],
               chains: List[Dict[str, Any]], moment: float) -> Dict[str, Any]:
        models = sorted({c["urn"] for c in chains})
        live = [g for c in chains for g in c["grants"] if g["state"] == LIVE]
        historical = [g for c in chains for g in c["grants"]
                      if g["state"] == HISTORICAL]
        uses = sorted({g["declared_use"] for g in live if g["declared_use"]})
        tiers = [c["tier"] for c in chains if c["tier"] is not None]
        worst = min(tiers) if tiers else None
        return {
            "subject": subject, "kind": kind,
            "views": views,
            "chains": chains,
            "models": models, "model_count": len(models),
            "live_grants": live, "historical_grants": historical,
            "declared_uses": uses,
            "worst_tier": worst,
            "blocking": bool(live),
            # Named on every answer. The traversal reaches the AUTHORITY to
            # decide, and stops there.
            "reaches_decisions": False,
            "checked_at": moment,
            "detail": self._detail(subject, models, live, historical, uses,
                                   worst),
        }

    @staticmethod
    def _detail(subject, models, live, historical, uses, worst) -> str:
        if not models:
            return (f"nothing downstream of {subject} is bound through a "
                    f"parameter set. That is not the same as nothing using it: "
                    f"a feature read by a model that never pinned a featureset "
                    f"version is invisible to this walk, and the honest answer "
                    f"is that the binding is what makes the chain traceable")
        out = (f"{len(models)} model(s) rest on {subject}")
        if worst is not None:
            out += f", the highest-risk at tier {worst}"
        if uses:
            out += (f". **{len(live)} live grant(s) across "
                    f"{len(uses)} declared use(s)**: {', '.join(uses[:4])}"
                    + (f" and {len(uses) - 4} more" if len(uses) > 4 else "")
                    + " — and this is the half that is actionable. A count of "
                      "models tells a feature owner nothing they can take to "
                      "anybody; a named use tells them who has to be told and "
                      "what will stop working")
        elif live:
            out += (f". {len(live)} live grant(s), none of which names a "
                    f"declared use — so what will stop working is not "
                    f"answerable from the register")
        else:
            out += (". No live grant rests on it, so a change here is a "
                    "migration and not an outage")
        if historical:
            out += (f". A further {len(historical)} grant(s) are revoked and "
                    f"are reported apart: a revoked grant is a historical fact "
                    f"and a live one is somebody who will call tomorrow")
        out += (". The walk reaches the AUTHORITY to decide and stops there — "
                "whether the model was actually called is invocation "
                "telemetry, and whether an answer reached a customer is "
                "outside the register. A count of affected decisions would be "
                "a number MAYA does not have")
        return out

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every feature with a live grant behind it, most exposed first."""
        moment = now if now is not None else time.time()
        rows = []
        for feature in self.features.catalogue.features.many():
            out = self.of_feature(feature["name"], now=moment)
            if out["model_count"]:
                rows.append(out)
        rows.sort(key=lambda r: (r["worst_tier"] if r["worst_tier"] is not None
                                 else 9, -len(r["live_grants"])))
        blocking = [r["subject"] for r in rows if r["blocking"]]
        return {
            "features": rows, "count": len(rows),
            "with_live_grants": blocking,
            "detail": (
                f"{len(rows)} feature(s) have a model bound to them through a "
                f"parameter set, and {len(blocking)} carry a live grant — which "
                f"is the list a feature owner needs before deprecating "
                f"anything"
                if rows else
                "no feature is bound through a parameter set anywhere. Read "
                "against the bindings rather than as an idle catalogue: an "
                "unbound feature is one this walk cannot follow"),
        }
