"""
MAYA — tests for notification.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Delivery, not a queue. What is under test is mostly restraint: a digest rather
than a firehose, silence when nothing has changed, and a failed send that is
recorded rather than swallowed.
"""
from __future__ import annotations

import time

import pytest

from core.notify import EmailChannel, NotifyError, WebhookChannel

DAY = 86400.0
URN = "maya://model/credit.pd.smallbiz"


@pytest.fixture
def with_work(notifications, principals, registry, a_model, findings):
    """A model with something outstanding, and somebody who can act on it."""
    principals.create("s.iqbal", "S Iqbal", ["model_risk_manager"], "pw",
                      email="s.iqbal@bank.example")
    # Critical, so it is blocking: the worklist deliberately ignores a finding
    # that is neither blocking nor yet due, and a notification about one nobody
    # needs to act on is exactly the noise this service is built to avoid.
    findings.raise_finding(a_model["id"], "Critical", "Docs are stale",
                           "person/j.okafor",
                           description="the MDD predates the current version",
                           category="documentation")
    return notifications


class TestOneMessagePerPersonNotOnePerItem:
    def test_the_digest_summarises_rather_than_enumerates(self, with_work,
                                                          principals):
        digest = with_work.digest_for(principals.require("s.iqbal"))
        assert digest["count"] >= 1
        assert digest["summary"].startswith("s.iqbal:")
        assert len(digest["headlines"]) <= 5

    def test_somebody_with_nothing_outstanding_is_not_written_to(self,
                                                                 with_work,
                                                                 principals):
        """An auditor reads and does not act, so nothing is ever theirs to do.
        Writing to them anyway is how a person learns to filter the sender."""
        principals.create("a.udit", "A Udit", ["auditor"], "pw")
        out = with_work.run()
        assert "a.udit" not in [d["principal"] for d in out["deliveries"]]

    def test_a_developer_is_written_to_about_their_own_work(self, with_work,
                                                            principals):
        """The draft model is genuinely theirs to move on."""
        principals.create("d.raman", "D Raman", ["model_developer"], "pw")
        digest = with_work.digest_for(principals.require("d.raman"))
        assert digest["count"] >= 1
        assert all(i["permission"] != "finding:close" for i in digest["items"])

    def test_the_digest_carries_where_to_go(self, with_work, principals):
        digest = with_work.digest_for(principals.require("s.iqbal"))
        assert digest["footer"].endswith("/dashboard")

    def test_it_is_the_same_derivation_the_dashboard_uses(self, with_work,
                                                          principals, worklist,
                                                          authz, registry):
        """Two views of one derivation, not two derivations."""
        who = principals.require("s.iqbal")
        digest = with_work.digest_for(who)
        dashboard = worklist.mine(who, authz, registry.list())
        assert [i["title"] for i in digest["items"]] == \
            [i["title"] for i in dashboard["items"]]


class TestSilenceWhenNothingHasChanged:
    def test_the_first_run_sends(self, with_work):
        out = with_work.run()
        assert out["sent"] >= 1 and out["suppressed"] == 0

    def test_the_second_run_says_nothing_new(self, with_work):
        """A message that repeats yesterday's is a message somebody filters."""
        with_work.run()
        again = with_work.run()
        assert again["sent"] == 0 and again["suppressed"] >= 1
        assert "unchanged since the last message" in again["detail"]

    def test_it_speaks_again_once_the_quiet_period_has_passed(self, with_work):
        with_work.run()
        later = with_work.run(now=time.time() + 2 * DAY)
        assert later["sent"] >= 1

    def test_it_speaks_again_when_the_work_changes(self, with_work, findings,
                                                   a_model):
        with_work.run()
        findings.raise_finding(a_model["id"], "Critical", "AUC has fallen",
                               "person/j.okafor",
                               description="below the threshold",
                               category="performance", source="monitoring")
        assert with_work.run()["sent"] >= 1

    def test_the_digest_is_of_the_work_not_of_the_prose(self, with_work,
                                                        principals):
        who = principals.require("s.iqbal")
        first = with_work.digest_for(who)["digest"]
        assert with_work.digest_for(who)["digest"] == first


class TestAFailedDeliveryIsRecorded:
    def test_an_unreachable_webhook_is_recorded_not_raised(self, notifications,
                                                           with_work, repos):
        """Silence about a failed send is how somebody concludes they were never
        told, which is worse than not having sent."""
        notifications.channels["webhook"] = WebhookChannel(
            "http://127.0.0.1:9/nothing-listens-here", timeout=1.0)
        out = notifications.run(channel="webhook")
        assert out["failed"] >= 1 and out["sent"] == 0
        assert "could not be delivered" in out["detail"]
        assert "notification_failed" in [e["kind"] for e in repos["evidence"].many()]

    def test_one_unreachable_channel_does_not_stop_the_others(self,
                                                              notifications,
                                                              with_work):
        notifications.channels["webhook"] = WebhookChannel(
            "http://127.0.0.1:9/nothing", timeout=1.0)
        notifications.run(channel="webhook")
        assert notifications.run(channel="log")["sent"] >= 1

    def test_a_channel_with_nowhere_to_send_says_so_before_trying(self,
                                                                  notifications):
        notifications.channels["email"] = EmailChannel()
        with pytest.raises(NotifyError) as exc:
            notifications.run(channel="email")
        assert exc.value.code == "channel_unavailable"
        assert "always available" in exc.value.remediation

    def test_an_unknown_channel_is_refused_with_the_list(self, notifications):
        with pytest.raises(NotifyError) as exc:
            notifications.run(channel="carrier_pigeon")
        assert exc.value.code == "unknown_channel"

    def test_a_principal_with_no_address_cannot_be_emailed(self):
        channel = EmailChannel(host="localhost")
        ok, why = channel.send("j.okafor", "subject", {})
        assert not ok and "is not an address" in why


class TestEscalationIsByRoleNotHierarchy:
    def test_a_long_overdue_item_reaches_the_second_line(self, notifications,
                                                         principals, a_model,
                                                         findings):
        """MAYA does not know who reports to whom and should not pretend to."""
        principals.create("s.iqbal", "S Iqbal", ["model_risk_manager"], "pw")
        principals.create("d.raman", "D Raman", ["model_developer"], "pw")
        findings.raise_finding(a_model["id"], "Critical", "Long overdue",
                               "person/d.raman",
                               description="nobody has closed it",
                               due_at=time.time() - 30 * DAY)
        digest = notifications.digest_for(principals.require("s.iqbal"))
        assert digest["count"] >= 1

    def test_a_developer_gets_no_escalations(self, notifications, principals,
                                             a_model, findings):
        principals.create("d.raman", "D Raman", ["model_developer"], "pw")
        findings.raise_finding(a_model["id"], "Critical", "Long overdue",
                               "person/d.raman", description="y",
                               due_at=time.time() - 30 * DAY)
        assert notifications.digest_for(
            principals.require("d.raman"))["escalated"] == []


class TestTheServiceSaysWhetherAnythingIsReaching:
    def test_a_dry_run_sends_nothing_and_records_nothing(self, with_work):
        out = with_work.run(dry_run=True)
        assert out["sent"] == 0 and out["dry_run"]
        assert "would have sent" in out["detail"]
        assert with_work.history() == []

    def test_the_status_names_which_channels_work(self, notifications):
        notifications.channels["email"] = EmailChannel()
        status = notifications.status()
        by_channel = {c["channel"]: c for c in status["channels"]}
        assert by_channel["log"]["usable"]
        assert not by_channel["email"]["usable"]
        assert by_channel["email"]["unavailable_because"]

    def test_failures_are_what_the_status_leads_with(self, notifications,
                                                     with_work):
        notifications.channels["webhook"] = WebhookChannel(
            "http://127.0.0.1:9/nothing", timeout=1.0)
        notifications.run(channel="webhook")
        assert "supposed to be told and was not" in notifications.status()["detail"]

    def test_the_history_keeps_suppressions_too(self, with_work):
        with_work.run()
        with_work.run()
        states = {d["state"] for d in with_work.history()}
        assert states == {"sent", "suppressed"}
