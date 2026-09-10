"""How long things are kept, and what stops them being deleted.

A legal hold is the one control in this platform that overrides the platform's
own deletion — and it is therefore the one place where the usual rule about
unbounded windows is inverted.
"""
from __future__ import annotations


import pytest

from core.retention import (CLASSES, LegalHolds, RetentionError,
                            RetentionSchedule, backing_of, retention_of)
from core.retention.holds import SCOPES
from core.retention.schedule import EXTERNAL, FILESYSTEM, YEAR


@pytest.fixture
def holds(db, evidence):
    from db import LegalHoldRepository
    return LegalHolds(LegalHoldRepository(db), evidence)


class TestTheScheduleIsPerClass:
    def test_every_class_says_why_that_long(self):
        """A single estate-wide number satisfies whichever obligation is
        loudest and quietly breaks the others."""
        assert all(v["because"] and v["years"] for v in CLASSES.values())

    def test_personal_data_is_kept_for_the_shortest_time(self):
        shortest = min(CLASSES, key=lambda k: CLASSES[k]["years"])
        assert shortest == "inference"
        assert "personal data" in CLASSES["inference"]["because"]

    def test_the_chain_is_kept_the_longest(self):
        assert CLASSES["evidence_chain"]["years"] >= max(
            v["years"] for v in CLASSES.values())

    def test_retention_of_returns_seconds(self):
        assert retention_of("artifact") == pytest.approx(7.0 * YEAR)

    def test_an_unknown_class_takes_a_default_rather_than_zero(self):
        assert retention_of("something-else") > 0


class TestTheWormClaimIsAboutStorage:
    def test_an_unbacked_instance_reports_filesystem(self):
        assert RetentionSchedule().backing() == FILESYSTEM

    def test_a_class_requiring_worm_is_reported_as_unmet_on_a_filesystem(self):
        """A directory with the permission bit cleared is an honest limit and
        not WORM, because whoever can clear the bit can set it again."""
        out = RetentionSchedule().describe()
        assert "artifact" in out["requirements_not_met"]
        assert "evidence_chain" in out["requirements_not_met"]
        assert "worse than having no field at all" in out["detail"]

    def test_real_immutable_storage_meets_it(self):
        backed = RetentionSchedule(worm=type("W", (), {"backing": EXTERNAL})())
        out = backed.describe()
        assert out["requirements_not_met"] == []
        assert "meets every requirement" in out["detail"]

    def test_backing_of_states_the_requirement_not_the_reality(self):
        assert backing_of("artifact") is True
        assert backing_of("validation") is False

    def test_a_period_is_a_floor(self):
        """Confusing *may now be deleted* with *must now be deleted* is how a
        register loses the record that was about to be asked for."""
        assert "A period is a FLOOR" in RetentionSchedule().describe()["detail"]


class TestPlacingAHold:
    def test_a_hold_is_placed_over_the_estate(self, holds):
        row = holds.place(matter="Regulator request 2026-114",
                          owner="person/legal", actor="admin")
        assert row["reference"] == "HOLD-0001"
        assert row["scope_kind"] == "estate"

    def test_a_hold_has_no_end_date_and_that_is_correct(self, holds):
        """It ends when the matter ends, and when that is cannot be known when
        it is placed."""
        row = holds.place(matter="m", owner="o")
        assert "expires_at" not in row and "lifted_at" in row
        assert row["lifted_at"] is None
        assert "guessing at a litigation timetable" in (
            holds.across_the_estate()["detail"])

    def test_a_hold_with_no_matter_is_refused(self, holds):
        """Since a hold has no end date, the matter is the only thing that will
        ever end it."""
        with pytest.raises(RetentionError) as caught:
            holds.place(matter="  ", owner="o")
        assert caught.value.code == "matter_required"

    def test_a_hold_with_no_owner_is_refused(self, holds):
        with pytest.raises(RetentionError) as caught:
            holds.place(matter="m", owner=" ")
        assert caught.value.code == "owner_required"
        assert "nobody will lift" in caught.value.detail

    def test_a_narrow_hold_must_say_what_it_covers(self, holds):
        with pytest.raises(RetentionError) as caught:
            holds.place(matter="m", owner="o", scope_kind="model")
        assert caught.value.code == "scope_required"

    def test_an_unknown_scope_is_refused_naming_the_real_ones(self, holds):
        with pytest.raises(RetentionError) as caught:
            holds.place(matter="m", owner="o", scope_kind="everything")
        assert caught.value.code == "unknown_scope"
        assert set(SCOPES) == {"estate", "model", "legal_entity"}

    def test_it_lands_on_the_evidence_chain(self, holds, evidence):
        row = holds.place(matter="m", owner="o")
        kinds = [n["kind"] for n in evidence.for_subject(row["id"])]
        assert "legal_hold_placed" in kinds


class TestWhatAHoldCovers:
    def test_an_estate_hold_covers_everything(self, holds):
        holds.place(matter="m", owner="o")
        assert holds.held(artifact_class="inference", model_id="m-1")
        assert holds.held(artifact_class="artifact", model_id="m-2")

    def test_a_model_hold_covers_only_that_model(self, holds):
        holds.place(matter="m", owner="o", scope_kind="model",
                    scope_id="m-1")
        assert holds.held(model_id="m-1")
        assert not holds.held(model_id="m-2")

    def test_a_class_scoped_hold_covers_only_that_class(self, holds):
        holds.place(matter="m", owner="o", classes=["inference"])
        assert holds.held(artifact_class="inference")
        assert not holds.held(artifact_class="artifact")

    def test_a_lifted_hold_covers_nothing(self, holds):
        row = holds.place(matter="m", owner="o")
        holds.lift(row["reference"], "the matter closed", actor="admin")
        assert not holds.held(artifact_class="inference")


class TestLiftingIsTheActThatNeedsCeremony:
    def test_lifting_without_a_reason_is_refused(self, holds):
        """Placing keeps more than necessary, which is recoverable. Lifting
        resumes deletion on material somebody may be about to ask for."""
        row = holds.place(matter="m", owner="o")
        with pytest.raises(RetentionError) as caught:
            holds.lift(row["reference"], "  ")
        assert caught.value.code == "reason_required"

    def test_a_lifted_hold_is_kept_not_deleted(self, holds):
        """What was held, and when, answers both *why is this still here* and
        *why is this not*."""
        row = holds.place(matter="m", owner="o")
        holds.lift(row["reference"], "closed", actor="admin")
        after = holds.require(row["reference"])
        assert after["state"] == "lifted" and after["lift_reason"] == "closed"

    def test_it_is_lifted_once(self, holds):
        row = holds.place(matter="m", owner="o")
        holds.lift(row["reference"], "closed")
        with pytest.raises(RetentionError) as caught:
            holds.lift(row["reference"], "again")
        assert caught.value.code == "not_active"


class TestAHoldBeatsARetentionPeriod:
    """The one direction this platform lets a control be overridden."""

    def _log(self, db, registry, holds):
        from core.execution.inference import InferenceLog
        from db import InferenceRepository
        return InferenceLog(InferenceRepository(db), registry, key="k",
                            sampler=lambda: 0.0, holds=holds)

    def test_an_expired_record_under_hold_is_kept(self, db, registry, holds,
                                                  a_model):
        from tests.conftest import URN
        log = self._log(db, registry, holds)
        log.record(URN, principal="p", now=0.0)
        holds.place(matter="Regulator request", owner="person/legal")
        out = log.expire_due(now=10 * YEAR)
        assert out["dropped"] == 0
        assert out["withheld_under_legal_hold"] == 1
        assert "the only direction this platform lets a control be overridden" \
            in out["detail"]

    def test_without_a_hold_it_is_deleted(self, db, registry, holds, a_model):
        from tests.conftest import URN
        log = self._log(db, registry, holds)
        log.record(URN, principal="p", now=0.0)
        assert log.expire_due(now=10 * YEAR)["dropped"] == 1

    def test_a_hold_on_another_model_does_not_save_it(self, db, registry,
                                                      holds, a_model):
        from tests.conftest import URN
        log = self._log(db, registry, holds)
        log.record(URN, principal="p", now=0.0)
        holds.place(matter="m", owner="o", scope_kind="model",
                    scope_id="somebody-else")
        assert log.expire_due(now=10 * YEAR)["dropped"] == 1

    def test_lifting_the_hold_lets_deletion_resume(self, db, registry, holds,
                                                   a_model):
        from tests.conftest import URN
        log = self._log(db, registry, holds)
        log.record(URN, principal="p", now=0.0)
        row = holds.place(matter="m", owner="o")
        assert log.expire_due(now=10 * YEAR)["dropped"] == 0
        holds.lift(row["reference"], "matter closed")
        assert log.expire_due(now=10 * YEAR)["dropped"] == 1


class TestTheEstate:
    def test_nothing_held_says_the_periods_apply_as_written(self, holds):
        out = holds.across_the_estate()
        assert out["active"] == 0
        assert "applies as written" in out["detail"]

    def test_an_estate_wide_hold_reads_like_a_decision_with_a_cost(self, holds):
        holds.place(matter="m", owner="o")
        out = holds.across_the_estate()
        assert out["estate_wide"] == 1
        assert "a decision with a cost and should read like one" in out["detail"]

    def test_the_schedule_reports_active_holds(self, holds):
        holds.place(matter="m", owner="o")
        out = RetentionSchedule(holds=holds).describe()
        assert out["active_holds"] == 1
        assert "override every period above" in out["detail"]


class TestOverHttp:
    ADMIN = ("admin", "maya-admin-dev")

    def test_the_schedule_is_served_with_what_is_not_met(self, client,
                                                         people):
        r = client.get("/api/v1/retention", auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert "artifact" in body["requirements_not_met"]
        assert "worse than having no field at all" in body["detail"]

    def test_a_hold_is_placed_and_listed(self, client, people):
        made = client.post("/api/v1/legal-holds", auth=self.ADMIN,
                           json={"matter": "Regulator request 2026-114",
                                 "owner": "person/legal"})
        assert made.status_code == 201, made.text
        listed = client.get("/api/v1/legal-holds", auth=people["a.mehta"])
        assert listed.status_code == 200, listed.text
        assert listed.json()["estate_wide"] == 1

    def test_a_hold_with_no_matter_is_refused(self, client, people):
        r = client.post("/api/v1/legal-holds", auth=self.ADMIN,
                        json={"matter": "  ", "owner": "person/legal"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "matter_required"

    def test_lifting_without_a_reason_is_refused(self, client, people):
        made = client.post("/api/v1/legal-holds", auth=self.ADMIN,
                           json={"matter": "m", "owner": "o"})
        reference = made.json()["reference"]
        r = client.post(f"/api/v1/legal-holds/{reference}/lift",
                        auth=self.ADMIN, json={"reason": "  "})
        assert r.status_code >= 400, r.text
        assert r.json()["error"] == "reason_required"

    def test_the_screen_says_a_hold_has_no_end_date_on_purpose(self, client,
                                                               people):
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/classification"})
        body = client.get("/classification").text
        assert "no end date, and that is correct" in body
        assert "the tick is what stops" in body
