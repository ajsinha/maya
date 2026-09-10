"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model will be watched for, written down before it goes anywhere.

*A monitoring plan* and *a monitored model* are different statements, and the
gap between them is where estates actually fail. The plan is written at
development time, argued over in validation, approved — and then somebody else,
months later, creates whatever monitors seem reasonable at the time. Nothing
ever compares the two. Every party is doing their job and the model ends up
watched for something other than what was agreed.

So the plan is a row against a **version**, and `inherited_at` is the column
that carries the whole point: null means *this model has a monitoring plan and
is not monitored*, which is a sentence no institution wants to be able to say
about itself and almost every institution can.

**A plan starts from the class-aware defaults rather than from nothing.**
`MonitoringDefaults` already derives from the fibre what this class can be asked
and from the tier how often — so authoring a plan begins with that answer and
the author edits it. A blank form produces either a plan copied from the last
model or a plan with one monitor on it, and the two failure modes are equally
common.

**Inheritance is an act, not a trigger.** It is a separate call, performed by a
person, recorded with their name. Making approval silently create monitors would
be convenient and would mean nobody ever looked at the plan again — and the
whole reason this exists is that the plan and the monitors drift apart when
nobody is made to compare them.

**A plan may not be edited once inherited.** The version is immutable and the
plan describes it; changing what a model was *supposed* to be watched for, after
it has been watched, rewrites the thing a reviewer needs to read.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.monitoring.common import ADMISSIBLE_TESTS, KINDS, MonitorError


class MonitoringPlans:
    """Authors a plan at development time, and inherits it into production."""

    def __init__(self, repo, registry, monitors, evidence, defaults=None):
        self.repo, self.registry = repo, registry
        self.monitors, self.evidence = monitors, evidence
        self.defaults = defaults

    # ---------------------------------------------------------------- author
    def author(self, urn: str, semver: str, *,
               items: Optional[List[Dict[str, Any]]] = None,
               rationale: str = "", actor: str = "system") -> Dict[str, Any]:
        """Write the plan for one version.

        With no items, the class-aware defaults are used. That is not a
        convenience: a blank form produces either a plan copied from the last
        model or a plan with one monitor on it, and both are common.
        """
        model = self.registry.require(urn)
        version = self.registry.version_service.require(urn, semver)
        if self.repo.one(model_version_id=version["id"]):
            raise MonitorError(
                "plan_exists",
                f"{urn}@{semver} already has a monitoring plan",
                "a version is immutable and so is the plan describing it; "
                "author a plan against a new version")

        proposed = list(items or [])
        if not proposed and self.defaults is not None:
            proposed = [
                {k: p[k] for k in ("kind", "test_key", "threshold",
                                   "cadence_days", "label_delay_days",
                                   "breach_severity", "escalate_after")}
                for p in self.defaults.propose(urn, model["id"])["propose"]]
        for item in proposed:
            self._check(item)

        row = {"model_id": model["id"], "model_version_id": version["id"],
               "items": proposed, "rationale": rationale,
               "authored_by": actor, "authored_at": time.time(),
               "inherited_at": None, "inherited_by": None, "monitor_ids": []}
        with self.evidence.recording():
            stored = self.repo.add(row)
            self.evidence.append(
                "monitoring_plan_authored", "model_version", version["id"],
                {"items": len(proposed),
                 "kinds": sorted({i["kind"] for i in proposed})}, actor=actor)
        return stored

    @staticmethod
    def _check(item: Dict[str, Any]) -> None:
        """Refuse a plan item the platform could never create.

        Checked when the plan is AUTHORED rather than when it is inherited,
        because a plan that cannot be honoured is worse than no plan: it is
        reviewed, approved, and then fails silently at the one moment nobody is
        watching it.
        """
        kind, test = item.get("kind"), item.get("test_key")
        if kind not in KINDS:
            raise MonitorError(
                "unknown_kind", f"'{kind}' is not a monitor kind",
                f"expected one of {', '.join(KINDS)}")
        if test not in ADMISSIBLE_TESTS[kind]:
            raise MonitorError(
                "test_not_admissible",
                f"'{test}' cannot answer a '{kind}' question",
                f"for {kind} use one of {', '.join(ADMISSIBLE_TESTS[kind])}")

    # -------------------------------------------------------------- inherit
    def inherit(self, urn: str, semver: str, *, owner: str = "",
                actor: str = "system") -> Dict[str, Any]:
        """Turn the plan into the monitors it describes.

        A separate act performed by a person, rather than something approval
        does quietly. Making approval create monitors would be convenient and
        would mean nobody looked at the plan again — and the drift between the
        plan and the monitors is the whole reason this exists.
        """
        plan = self.require(urn, semver)
        if plan.get("inherited_at"):
            raise MonitorError(
                "already_inherited",
                f"this plan was already inherited at {plan['inherited_at']}",
                "the monitors it created are the ones in force; change them "
                "there, where the change is recorded against the monitor")
        model = self.registry.require(urn)
        created = []
        for item in plan["items"]:
            made = self.monitors.define(
                model["id"],
                name=f"{item['kind']} ({item['test_key']})",
                kind=item["kind"], test_key=item["test_key"],
                threshold=item.get("threshold") or {},
                owner=owner or model.get("owner") or actor,
                model_version_id=plan["model_version_id"],
                cadence_days=item.get("cadence_days", 1.0),
                label_delay_days=item.get("label_delay_days", 0.0),
                breach_severity=item.get("breach_severity", "Medium"),
                escalate_after=item.get("escalate_after", 3), actor=actor)
            created.append(made["id"])
        with self.evidence.recording():
            self.repo.set({"inherited_at": time.time(), "inherited_by": actor,
                           "monitor_ids": created}, id=plan["id"])
            self.evidence.append(
                "monitoring_plan_inherited", "model_version",
                plan["model_version_id"],
                {"monitors": len(created)}, actor=actor)
        return self.require(urn, semver)

    # ------------------------------------------------------------------ read
    def require(self, urn: str, semver: str) -> Dict[str, Any]:
        version = self.registry.version_service.require(urn, semver)
        row = self.repo.one(model_version_id=version["id"])
        if not row:
            raise MonitorError(
                "no_plan", f"{urn}@{semver} has no monitoring plan",
                "author one; what a model will be watched for is a development-"
                "time decision, not something to settle after it is live")
        return row

    def for_version(self, urn: str, semver: str) -> Dict[str, Any]:
        plan = self.require(urn, semver)
        return {**plan, **self._status(plan)}

    def outstanding(self) -> Dict[str, Any]:
        """Every plan authored and never inherited.

        The report this module exists for. *This model has a monitoring plan
        and is not monitored* is a sentence no institution wants to be able to
        say about itself, and almost every institution can.
        """
        rows = [r for r in self.repo.many() if not r.get("inherited_at")]
        out = []
        for row in rows:
            version = self.registry.version_by_id(row["model_version_id"]) or {}
            out.append({"urn": version.get("urn"),
                        "semver": version.get("semver"),
                        "items": len(row.get("items") or []),
                        "authored_by": row["authored_by"],
                        "authored_at": row["authored_at"]})
        out.sort(key=lambda r: r["authored_at"])
        return {
            "plans": out, "count": len(out),
            "detail": (f"{len(out)} version(s) have a monitoring plan and no "
                       f"monitors. A plan and a monitored model are different "
                       f"statements, and this is the gap between them"
                       if out else
                       "every authored monitoring plan has been inherited"),
        }

    @staticmethod
    def _status(plan: Dict[str, Any]) -> Dict[str, Any]:
        inherited = bool(plan.get("inherited_at"))
        return {
            "inherited": inherited,
            "detail": (f"{len(plan.get('monitor_ids') or [])} monitor(s) "
                       f"created from this plan"
                       if inherited else
                       f"{len(plan.get('items') or [])} monitor(s) planned and "
                       f"none created — this model has a monitoring plan and "
                       f"is not monitored"),
        }
