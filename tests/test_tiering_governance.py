"""Governing the model that decides how everything else is governed.

SS1/23 1.3(d) says the tiering approach is itself a model. A firm that governs
four hundred models and not the one that tiers them has left the most
consequential model in the estate outside the framework.
"""
from __future__ import annotations


import pytest

from core.risk.approvals import KINDS, NOTICE_DAYS, RegulatoryApprovals
from core.risk.tiering import RiskError
from core.risk.whatif import DOWN, TieringWhatIf
from tests.conftest import URN

DAY = 86400.0
NOW = 1_800_000_000.0


@pytest.fixture
def approvals(db, registry, evidence):
    from db import RegulatoryApprovalRepository
    return RegulatoryApprovals(RegulatoryApprovalRepository(db), registry,
                               evidence)


class FakeRisk:
    def __init__(self, rows):
        self._rows = rows

    def many(self, model_id):
        return self._rows.get(model_id, [])


class TestAnApprovalIsNotATier:
    def test_the_kinds_are_named_instruments(self):
        """A free-text kind would let *model approved* into a register that
        exists to stop exactly that."""
        assert set(KINDS) == {"irb", "ima", "ama_or_equivalent",
                              "internal_model_waiver", "no_objection"}
        assert all(v["granted_over"] and v["means"] for v in KINDS.values())

    def test_an_unknown_kind_is_refused(self, approvals):
        with pytest.raises(RiskError) as caught:
            approvals.record("approved", regulator="PRA", scope="everything",
                             granted_at=NOW)
        assert caught.value.code == "unknown_approval_kind"

    def test_an_approval_with_no_scope_is_refused(self, approvals):
        """It cannot answer the question it exists to answer: for what."""
        with pytest.raises(RiskError) as caught:
            approvals.record("irb", regulator="PRA", scope="  ",
                             granted_at=NOW)
        assert caught.value.code == "scope_required"
        assert "*for what*" in caught.value.detail

    def test_it_does_not_lower_the_tier_and_says_so(self, approvals, a_model):
        """The pull is constant and this is where somebody would look."""
        approvals.record("irb", regulator="PRA",
                         scope="UK retail mortgages", granted_at=NOW,
                         urn=URN)
        out = approvals.for_model(URN)
        assert "circular" in out["does_not_lower_the_tier"]

    def test_a_null_expiry_means_no_stated_end(self, approvals, a_model):
        """IRB permission is withdrawn rather than lapsing; a desk approval
        runs to a date. Those are different facts."""
        approvals.record("irb", regulator="PRA", scope="retail",
                         granted_at=NOW, urn=URN)
        row = approvals.for_model(URN, now=NOW + 1000 * DAY)["approvals"][0]
        assert row["no_stated_end"] is True
        assert row["effectively_in_force"] is True

    def test_a_dated_approval_lapses(self, approvals, a_model):
        approvals.record("ima", regulator="PRA", scope="Rates desk",
                         granted_at=NOW, expires_at=NOW + 30 * DAY, urn=URN)
        out = approvals.for_model(URN, now=NOW + 60 * DAY)
        assert out["approvals"][0]["lapsed"] is True
        assert "still reads as permitted" in out["detail"]

    def test_an_expiring_approval_is_named_early(self, approvals, a_model):
        """A re-permission is a programme rather than a form."""
        approvals.record("ima", regulator="PRA", scope="Rates desk",
                         granted_at=NOW,
                         expires_at=NOW + (NOTICE_DAYS - 10) * DAY, urn=URN)
        assert "a programme rather than a form" in (
            approvals.for_model(URN, now=NOW)["detail"])

    def test_withdrawal_keeps_the_row(self, approvals, a_model):
        """*We used to hold IRB permission and it was withdrawn in March* is the
        single most important sentence in a supervisory conversation."""
        row = approvals.record("irb", regulator="PRA", scope="retail",
                               granted_at=NOW, urn=URN)
        out = approvals.withdraw(row["reference"], "P&L attribution failed",
                                 actor="s.iqbal")
        assert out["state"] == "withdrawn"
        assert out["withdrawal_reason"] == "P&L attribution failed"

    def test_withdrawal_without_a_reason_is_refused(self, approvals, a_model):
        row = approvals.record("irb", regulator="PRA", scope="r",
                               granted_at=NOW, urn=URN)
        with pytest.raises(RiskError) as caught:
            approvals.withdraw(row["reference"], "  ")
        assert caught.value.code == "reason_required"

    def test_conditions_are_kept_as_written(self, approvals, a_model):
        """A paraphrase is what somebody will read in three years when the
        person who received the letter has left."""
        row = approvals.record(
            "internal_model_waiver", regulator="PRA", scope="LGD floor",
            granted_at=NOW, urn=URN,
            conditions="subject to quarterly reporting of realised LGD")
        assert "quarterly reporting" in row["conditions"]

    def test_the_batch_marks_what_lapsed(self, approvals, a_model):
        approvals.record("ima", regulator="PRA", scope="d", granted_at=NOW,
                         expires_at=NOW + DAY, urn=URN)
        out = approvals.expire_due(now=NOW + 10 * DAY)
        assert out["count"] == 1

    def test_an_empty_estate_distinguishes_two_facts(self, approvals):
        """A firm that holds none is a different fact from one that has not
        written them down."""
        out = approvals.across_the_estate()
        assert out["count"] == 0
        assert "has not written them down" in out["detail"]


class TestTheWhatIfIsAboutWhoMoves:
    def _estate(self, registry, tiers):
        rows = {}
        for i, (tier, exposure) in enumerate(tiers):
            urn = f"maya://model/m{i}"
            registry.register(urn, f"M{i}", "credit.pd.scorecard", "credit",
                              "person/o", "LE-US-01", "p", actor="j.okafor")
            model = registry.require(urn)
            registry.set_tier(model["id"], tier)
            rows[model["id"]] = [{"assessed_at": 1.0, "tier": tier,
                                  "facts": {"exposure": exposure}}]
        return FakeRisk(rows)

    def test_a_rule_that_changes_nothing_says_so(self, registry):
        risk = self._estate(registry, [(1, 1e9), (3, 1e6)])
        out = TieringWhatIf(None, registry, risk).simulate(
            lambda facts: 1 if facts["exposure"] >= 1e9 else 3)
        assert out["down"] == 0 and out["up"] == 0
        assert out["unchanged"] == 2

    def test_a_downgrade_is_counted_and_named_first(self, registry):
        """Lowering scrutiny is silent: it arrives as a spreadsheet with fewer
        red cells."""
        risk = self._estate(registry, [(1, 1e9), (1, 5e9)])
        out = TieringWhatIf(None, registry, risk).simulate(lambda facts: 3)
        assert out["down"] == 2 and out["up"] == 0
        assert out["moved"][0]["direction"] == DOWN
        assert "arrives as a spreadsheet with fewer red cells" in out["detail"]

    def test_the_exposure_moving_down_is_the_number_to_quote(self, registry):
        """*Three models moved down* and *three models carrying eleven billion
        moved down* are different sentences."""
        risk = self._estate(registry, [(1, 1e9), (1, 5e9)])
        out = TieringWhatIf(None, registry, risk).simulate(lambda facts: 4)
        assert out["exposure_moving_down"] == 6e9
        assert "which is the number to quote rather than the count" in (
            out["detail"])

    def test_an_upgrade_is_the_other_direction(self, registry):
        risk = self._estate(registry, [(4, 1e6)])
        out = TieringWhatIf(None, registry, risk).simulate(lambda facts: 1)
        assert out["up"] == 1 and out["down"] == 0

    def test_a_rule_that_fails_on_one_model_still_reports_the_rest(self,
                                                                   registry):
        """A rule that fails on one row and works on four hundred is worth
        seeing, and an exception would have hidden the four hundred."""
        risk = self._estate(registry, [(1, 1e9), (3, 1e6)])

        def brittle(facts):
            if facts["exposure"] < 1e8:
                raise ValueError("no rule for this")
            return 2

        out = TieringWhatIf(None, registry, risk).simulate(brittle)
        assert len(out["undecidable"]) == 1
        assert "a finding about the rule rather than about them" in (
            out["detail"])

    def test_an_unassessed_model_is_excluded_and_named(self, registry):
        registry.register("maya://model/new", "N", "credit.pd.scorecard",
                          "credit", "person/o", "LE-US-01", "p",
                          actor="j.okafor")
        out = TieringWhatIf(None, registry, FakeRisk({})).simulate(
            lambda facts: 1)
        assert out["unassessed"] == ["maya://model/new"]

    def test_a_non_callable_candidate_is_refused(self, registry):
        with pytest.raises(RiskError) as caught:
            TieringWhatIf(None, registry, FakeRisk({})).simulate({"tier": 1})
        assert caught.value.code == "candidate_not_callable"

    def test_nothing_is_applied(self, registry):
        """A what-if that could quietly become a what-is would be the fastest
        route to a silent downgrade."""
        risk = self._estate(registry, [(1, 1e9)])
        out = TieringWhatIf(None, registry, risk).simulate(lambda facts: 4)
        assert out["applied"] is False
        assert registry.require("maya://model/m0")["tier"] == 1
        assert "a separate act with a signature on it" in out["detail"]

    def test_a_downgrade_under_a_permission_is_a_different_conversation(
            self, registry, approvals):
        risk = self._estate(registry, [(1, 1e9)])
        approvals.record("irb", regulator="PRA", scope="retail",
                         granted_at=NOW, urn="maya://model/m0")
        out = TieringWhatIf(None, registry, risk,
                            approvals=approvals).simulate(lambda facts: 3)
        assert out["downgrades_under_regulatory_approval"]
        assert "a different conversation" in out["detail"]
