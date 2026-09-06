"""A screen must not render what its own API refuses.

Four of them did. `/features`, `/featuresets` and their detail pages rendered
for an operator, who does not hold `feature:read`; `/policies` rendered for a
model developer and for an owner, neither of whom holds `policy:read`. Every
panel on those pages then answered 403, which teaches a reader the product is
broken rather than that they lack a permission.

`/notifications` was worse than an offer that fails. It called
`history(None, 100)` — every delivery in the estate — for anybody signed in,
while `GET /notifications/history` requires `principal:read`. The screen was
serving what the endpoint withholds.
"""
from __future__ import annotations

import pytest

from tests.api_helpers import login as _login


@pytest.fixture
def cast(client):
    """One principal per role we need, created through the API."""
    made = {}
    for username, role, password in (
            ("op.singh", "operator", "op-pw"),
            ("dev.two", "model_developer", "dev2-pw"),
            ("mrm.two", "model_risk_manager", "mrm2-pw")):
        r = client.post("/api/v1/principals", json={
            "username": username, "display_name": username,
            "roles": [role], "password": password})
        assert r.status_code in (201, 409), r.text
        made[role] = (username, password)
    return made


class TestTheScreenRefusesWhatTheApiRefuses:

    @pytest.mark.parametrize("path", ["/features", "/featuresets",
                                      "/feature-views/anything",
                                      "/featureset/anything"])
    def test_an_operator_is_refused_the_feature_screens(self, client, cast, path):
        user, pw = cast["operator"]
        _login(client, user, pw)
        r = client.get(path)
        assert r.status_code == 403, f"{path} rendered for a principal the API refuses"
        assert "feature:read" in r.text, "name the permission that was missing"

    def test_a_developer_is_refused_the_policy_screen(self, client, cast):
        user, pw = cast["model_developer"]
        _login(client, user, pw)
        r = client.get("/policies")
        assert r.status_code == 403 and "policy:read" in r.text

    def test_the_risk_manager_still_gets_all_four(self, client, cast):
        """The gate must refuse the right people and nobody else."""
        user, pw = cast["model_risk_manager"]
        _login(client, user, pw)
        for path in ("/features", "/featuresets", "/policies"):
            assert client.get(path).status_code == 200, path


class TestNotificationHistoryIsNotServedPastTheApi:

    def test_a_developer_sees_only_their_own_deliveries(self, client, cast):
        user, pw = cast["model_developer"]
        _login(client, user, pw)
        body = client.get("/notifications").text
        assert "What has been sent to you" in body
        assert "principal:read" in body, "say why the rest is not shown"
        # And the endpoint agrees, which is the whole point.
        assert client.get("/api/v1/notifications/history",
                          auth=(user, pw)).status_code == 403

    def test_a_risk_manager_sees_the_estate(self, client, cast):
        user, pw = cast["model_risk_manager"]
        _login(client, user, pw)
        body = client.get("/notifications").text
        assert "What has been sent to you" not in body
        assert client.get("/api/v1/notifications/history",
                          auth=(user, pw)).status_code == 200
