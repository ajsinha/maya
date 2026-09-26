"""
SDK: model governance -- the findings register, materiality tiers and periodic review.

Its own module because ``resources.py`` is at the file-size gate's limit; the methods
register in the same ``ENDPOINTS`` table, and ``resources`` imports this module, so the
parity gates see them like any other.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.sdk.base import _nn, _Resource, endpoint
from maya.sdk.transport import seg


class Governance(_Resource):
    """Findings, materiality and periodic review for the models you can read."""

    @endpoint("GET", "/governance")
    def overview(self) -> Any:
        return self._c("GET", "/governance")

    @endpoint("GET", "/governance/inventory")
    def inventory(self, format: str = "csv", framework: str = "sr11-7") -> Any:
        """The model inventory as a file: ``{data, content_type, ...}``."""
        return self._c(
            "GET",
            "/governance/inventory",
            params={"format": format, "framework": framework},
            raw=True,
        )

    @endpoint("GET", "/governance/findings")
    def findings(self, model: str | None = None, state: str | None = None) -> Any:
        return self._c("GET", "/governance/findings", params={"model": model, "state": state})

    @endpoint("POST", "/governance/findings")
    def raise_finding(
        self,
        model: str,
        title: str,
        severity: str,
        *,
        detail: str | None = None,
        source: str = "validation",
        owner: str | None = None,
        due_date: str | None = None,
        version_no: int | None = None,
    ) -> Any:
        body = {
            "model": model,
            "title": title,
            "severity": severity,
            "detail": detail,
            "source": source,
            "owner": owner,
            "due_date": due_date,
            "version_no": version_no,
        }
        return self._c("POST", "/governance/findings", json_body=body)

    @endpoint("GET", "/governance/findings/{finding_id}")
    def finding(self, finding_id: str) -> Any:
        return self._c("GET", f"/governance/findings/{seg(finding_id)}")

    @endpoint("POST", "/governance/findings/{finding_id}/move")
    def move_finding(self, finding_id: str, action: str, note: str | None = None) -> Any:
        return self._c(
            "POST",
            f"/governance/findings/{seg(finding_id)}/move",
            json_body={"action": action, "note": note},
        )

    @endpoint("GET", "/governance/models/{namespace}/{name}")
    def profile(self, model: str) -> Any:
        return self._c("GET", f"/governance/models/{_nn(model, 'model')}")

    @endpoint("PUT", "/governance/models/{namespace}/{name}")
    def set_profile(
        self,
        model: str,
        *,
        use: str | None = None,
        exposure: float | None = None,
        tier_override: int | None = None,
        override_reason: str | None = None,
        review_days: int | None = None,
        answers: dict[str, str] | None = None,
    ) -> Any:
        body = {
            "answers": answers,
            "use": use,
            "exposure": exposure,
            "tier_override": tier_override,
            "override_reason": override_reason,
            "review_days": review_days,
        }
        return self._c("PUT", f"/governance/models/{_nn(model, 'model')}", json_body=body)

    @endpoint("POST", "/governance/models/{namespace}/{name}/reviews")
    def record_review(self, model: str, outcome: str, note: str) -> Any:
        return self._c(
            "POST",
            f"/governance/models/{_nn(model, 'model')}/reviews",
            json_body={"outcome": outcome, "note": note},
        )

    @endpoint("POST", "/governance/sweep")
    def sweep(self) -> Any:
        return self._c("POST", "/governance/sweep")


class Monitoring(_Resource):
    """Ongoing monitoring of live models, read from their reported executions."""

    @endpoint("GET", "/monitoring")
    def overview(self, days: int = 30) -> Any:
        return self._c("GET", "/monitoring", params={"days": days})

    @endpoint("GET", "/monitoring/warrants/{ew_id}")
    def warrant(self, ew_id: str, days: int = 90) -> Any:
        return self._c("GET", f"/monitoring/warrants/{seg(ew_id)}", params={"days": days})


class Challenges(_Resource):
    """Champion and challenger compared on the same escrowed holdout, and the decision."""

    @endpoint("GET", "/challenges")
    def list(self) -> Any:
        return self._c("GET", "/challenges")

    @endpoint("POST", "/challenges")
    def create(
        self,
        champion: str,
        challenger: str,
        *,
        metric: str = "rmse",
        champion_parameter_set_id: str | None = None,
        challenger_parameter_set_id: str | None = None,
    ) -> Any:
        body = {
            "champion": champion,
            "challenger": challenger,
            "metric": metric,
            "champion_parameter_set_id": champion_parameter_set_id,
            "challenger_parameter_set_id": challenger_parameter_set_id,
        }
        return self._c("POST", "/challenges", json_body=body)

    @endpoint("GET", "/challenges/{challenge_id}")
    def get(self, challenge_id: str) -> Any:
        return self._c("GET", f"/challenges/{seg(challenge_id)}")

    @endpoint("POST", "/challenges/{challenge_id}/decision")
    def decide(self, challenge_id: str, decision: str, rationale: str) -> Any:
        return self._c(
            "POST",
            f"/challenges/{seg(challenge_id)}/decision",
            json_body={"decision": decision, "rationale": rationale},
        )


class Evidence(_Resource):
    """Fairness and explainability evidence on a training warrant's escrowed holdout."""

    @endpoint("GET", "/warrants/training/{warrant_id}/evidence")
    def list(self, warrant_id: str) -> Any:
        return self._c("GET", f"/warrants/training/{seg(warrant_id)}/evidence")

    @endpoint("POST", "/warrants/training/{warrant_id}/evidence")
    def compute(
        self,
        warrant_id: str,
        *,
        parameter_set_id: str | None = None,
        segment: str | None = None,
        importance: bool = True,
        repeats: int = 5,
        min_segment: int = 20,
    ) -> Any:
        body = {
            "parameter_set_id": parameter_set_id,
            "segment": segment,
            "importance": importance,
            "repeats": repeats,
            "min_segment": min_segment,
        }
        return self._c("POST", f"/warrants/training/{seg(warrant_id)}/evidence", json_body=body)
