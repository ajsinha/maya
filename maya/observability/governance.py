"""
Scrape-time gauges for model governance: the state of the inventory, not of the machine.

The platform metrics say whether MAYA is healthy. These say whether the models it governs
are: how many execution warrants are live, suspended or about to expire; how many versions
are waiting for a reviewer; how many models are past their periodic review; which findings
are open and how severe; how many restatements under live models nobody has acknowledged,
and for how long; how many documents are waiting for a second person. Each is a number a
model risk function would otherwise learn about from a page nobody opens, so each has an
alert in ``config/prometheus/maya-governance.rules.yml``.

They walk catalogue tables, so ``Collectors`` holds them for
``observability.metrics.cache_seconds`` like the lake gauges. No label carries a model or
warrant name: the counts are by state, kind, tier or severity, so the series stay bounded
however large the inventory grows, and a metric scraper learns nothing it may not read.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from maya.core.clock import utcnow

Sample = tuple[str, dict[str, Any], float]

WARRANT_STATUSES = ("draft", "in_review", "approved", "live", "suspended", "expired", "revoked")
VERSION_STATES = ("draft", "in_review", "approved", "published", "deprecated", "retired")
EXPIRY_WINDOWS = (7, 30)
VERSIONS = (
    ("feature", "feature_versions"),
    ("featureset", "feature_set_versions"),
    ("model", "model_versions"),
)


def collect(platform: Any) -> list[Sample]:
    out: list[Sample] = []
    with platform.uow() as uow:
        out += _warrants(platform, uow)
        out += _versions(uow)
        out += _reviews(platform, uow)
        out += _findings(uow)
        out += _restatements(uow)
        out += _documents(uow)
    return out


def _warrants(platform: Any, uow: Any) -> list[Sample]:
    rows = uow.repo("execution_warrants").list()
    counts = dict.fromkeys(WARRANT_STATUSES, 0)
    expiring = dict.fromkeys(EXPIRY_WINDOWS, 0)
    now = utcnow()
    for ew in rows:
        status = platform.execution.status(ew)
        counts[status] = counts.get(status, 0) + 1
        if status == "live" and ew.get("valid_to"):
            for days in EXPIRY_WINDOWS:
                if ew["valid_to"] <= now + dt.timedelta(days=days):
                    expiring[days] += 1
    out: list[Sample] = [
        ("maya_execution_warrants", {"status": s}, float(n)) for s, n in sorted(counts.items())
    ]
    out += [
        ("maya_execution_warrants_expiring", {"within_days": str(d)}, float(n))
        for d, n in expiring.items()
    ]
    for state in ("draft", "in_review", "approved", "sealed", "revoked"):
        n = (
            uow.repo("training_warrants").count(sealed_at__isnull=False, revoked_at__isnull=True)
            if state == "sealed"
            else uow.repo("training_warrants").count(revoked_at__isnull=False)
            if state == "revoked"
            else uow.repo("training_warrants").count(state=state, sealed_at__isnull=True)
        )
        out.append(("maya_training_warrants", {"state": state}, float(n)))
    return out


def _versions(uow: Any) -> list[Sample]:
    return [
        ("maya_versions", {"kind": kind, "state": state}, float(uow.repo(table).count(state=state)))
        for kind, table in VERSIONS
        for state in VERSION_STATES
    ]


def _reviews(platform: Any, uow: Any) -> list[Sample]:
    """Models past their periodic review, by tier: the sweep suspends their live warrants."""
    overdue: dict[str, int] = {}
    for model in uow.repo("models").list():
        prof = platform.governance._profile(uow, model)
        if prof["review_overdue"]:
            tier = str(prof["tier"])
            overdue[tier] = overdue.get(tier, 0) + 1
    tiers = sorted(set(overdue) | {"1", "2", "3"})
    return [("maya_models_review_overdue", {"tier": t}, float(overdue.get(t, 0))) for t in tiers]


def _findings(uow: Any) -> list[Sample]:
    counts: dict[str, int] = {}
    for f in uow.repo("findings").list(state__in=["open", "remediating", "remediated"]):
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    from maya.services.governance import SEVERITIES

    return [
        ("maya_findings_open", {"severity": s}, float(counts.get(s, 0)))
        for s in sorted(set(SEVERITIES) | set(counts))
    ]


def _restatements(uow: Any) -> list[Sample]:
    repo = uow.repo("restatement_impacts")
    open_rows = repo.list(state="open")
    oldest = min((r["created_at"] for r in open_rows), default=None)
    return [
        ("maya_restatement_impacts", {"state": "open"}, float(len(open_rows))),
        (
            "maya_restatement_impacts",
            {"state": "acknowledged"},
            float(repo.count(state="acknowledged")),
        ),
        (
            "maya_restatement_oldest_open_seconds",
            {},
            (utcnow() - oldest).total_seconds() if oldest else 0.0,
        ),
    ]


def _documents(uow: Any) -> list[Sample]:
    return [
        ("maya_documents", {"state": s}, float(uow.repo("model_documents").count(state=s)))
        for s in ("draft", "approved")
    ]
