"""
MAYA — tests for replay from storage and Delta time travel.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The distinction under test is between a control somebody can run *against* you
and one you help perform. A replay that takes its data from the caller is the
second; one that fetches the snapshot the episode was pinned to is the first.
"""
from __future__ import annotations

import datetime as dt

import pytest

from core.features import FeatureError
from core.validation import ValidationError

TS = dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc).timestamp()
URN = "maya://model/credit.pd.smallbiz"


def _rows(n=8, offset=0.0):
    return [{"entity_id": f"B{i}", "event_ts": TS, "ingest_ts": TS,
             "dscr": 1.0 + i * 0.1 + offset, "turnover": 100000.0 + i * 1000}
            for i in range(n)]


@pytest.fixture
def view(full_features):
    f = full_features
    for name in ("dscr", "turnover"):
        f.define(name, "borrower_id", "numeric", name, "person/j.okafor")
    f.create_view("sb_credit", "borrower_id", "person/j.okafor",
                  ["dscr", "turnover"])
    f.materialise("sb_credit", _rows(), ["dscr", "turnover"])
    return f


# ============================================================== time travel
class TestAReadIsPinnedToAVersionNotAPath:
    def test_a_view_version_carries_the_delta_version_it_was_written_at(self, view):
        pin = view.pinned("sb_credit", 1)
        assert pin["namespace"].endswith("/v1")
        assert pin["delta_version"] >= 0
        assert pin["row_count"] == 8

    def test_a_version_that_was_never_materialised_is_refused(self, view):
        with pytest.raises(FeatureError, match="no version 9"):
            view.pinned("sb_credit", 9)

    def test_writing_to_a_namespace_again_is_reported_as_a_restatement(self, view):
        """Not automatically wrong — correcting a stale row is legitimate — but a
        reader who dropped the pin would now see something else."""
        before = view.restated("sb_credit", 1)
        assert not before["restated"]
        view.delta.write(before["namespace"], _rows(2, offset=5.0))
        after = view.restated("sb_credit", 1)
        assert after["restated"]
        assert after["current_delta_version"] > after["delta_version"]
        assert "written to since it was pinned" in after["detail"]

    def test_an_assembly_reads_what_it_pinned_not_what_is_current(self, view):
        """Without the pin, an assembly is reproducible only for as long as
        nobody writes to the view again."""
        spine = [{"entity_id": f"B{i}", "label_ts": TS + 1} for i in range(4)]
        first = view.build_training_set("sb-1", spine,
                                        [{"view": "sb_credit", "version": 1}],
                                        TS + 10)
        pin = view.pinned("sb_credit", 1)
        view.delta.write(pin["namespace"],
                         [{**r, "dscr": 99.0} for r in _rows(4)])
        again = view.build_training_set("sb-2", spine,
                                        [{"view": "sb_credit", "version": 1}],
                                        TS + 10)
        assert first["row_count"] == again["row_count"]
        rows = view.delta.read(again["delta_table"]).to_dict("records")
        assert all(r["dscr"] < 50 for r in rows), "the read escaped its pin"


class TestAFeaturesetVersionSaysWhetherTheGroundMoved:
    @pytest.fixture
    def pinned_set(self, view):
        view.define_featureset("sb_core", "borrower_id", "person/j.okafor",
                               {"dscr": "numeric", "turnover": "numeric"})
        return view.publish_featureset("sb_core",
                                       {"dscr": "dscr", "turnover": "turnover"})

    def test_a_binding_pins_the_delta_version_not_only_the_path(self, pinned_set):
        assert pinned_set["bindings"]["dscr"]["delta_version"] is not None

    def test_nothing_moved_is_said_plainly(self, view, pinned_set):
        assert view.restatements("sb_core", 1)["restated"] is False

    def test_a_write_underneath_is_reported_slot_by_slot(self, view, pinned_set):
        view.delta.write(view.pinned("sb_credit", 1)["namespace"], _rows(2))
        report = view.restatements("sb_core", 1)
        assert report["restated"]
        assert {s["slot"] for s in report["slots"]} == {"dscr", "turnover"}
        assert "still reads the bytes it pinned" in report["detail"]


# ========================================================== replay from storage
class TestReplayFetchesItsOwnData:
    @pytest.fixture
    def snapshot(self, view):
        spine = [{"entity_id": f"B{i}", "label_ts": TS + 1} for i in range(6)]
        return view.build_training_set("sb-replay", spine,
                                       [{"view": "sb_credit", "version": 1}],
                                       TS + 10)

    def test_it_describes_what_it_would_read(self, snapshot_provider, snapshot):
        described = snapshot_provider.describe(snapshot["id"])
        assert described["readable"]
        assert described["pinned_delta_version"] == snapshot["delta_version"]
        assert not described["restated"]
        assert "unchanged since the validation ran" in described["detail"]

    def test_it_reports_a_restatement_without_following_it(self, snapshot_provider,
                                                           snapshot, delta, view):
        """The snapshot table holds joined rows, so a restatement is written in
        that shape rather than in the feature view's."""
        joined = delta.read(snapshot["delta_table"]).to_dict("records")
        delta.write(snapshot["delta_table"],
                    [{**joined[0], "entity_id": "B99"}], mode="append")
        described = snapshot_provider.describe(snapshot["id"])
        assert described["restated"]
        assert described["current_delta_version"] > described["pinned_delta_version"]
        assert "the replay reads v" in described["detail"]
        frame = snapshot_provider.frame(snapshot["id"])
        assert len(frame) == 6, "the read followed the restatement"

    def test_a_snapshot_whose_table_is_gone_is_refused_not_guessed(
            self, snapshot_provider, snapshot, delta, tmp_path):
        import shutil
        shutil.rmtree(tmp_path / "delta" / snapshot["delta_table"])
        with pytest.raises(ValidationError, match="not in the store"):
            snapshot_provider.frame(snapshot["id"])

    def test_an_unknown_snapshot_is_refused(self, snapshot_provider):
        with pytest.raises(ValidationError, match="no dataset snapshot"):
            snapshot_provider.describe("nope")

    def test_a_slice_naming_a_column_that_is_absent_yields_nothing(
            self, snapshot_provider, snapshot):
        """A slice silently ignored is a replay of a different population."""
        frame = snapshot_provider.frame(snapshot["id"])
        assert snapshot_provider.series(frame, {"region": "NJ"}) is None


class TestTheReportDistinguishesCheckedFromUncheckable:
    def test_an_episode_with_no_snapshot_skips_every_test(
            self, stored_replayer, validation, approved_version, findings):
        episode = validation.open(URN, "3.2.1", "periodic", ["person/a.mehta"])
        report = stored_replayer.from_storage(episode["id"])
        assert report["source"] == "storage"
        assert report["reproducible"] is False
        assert report["data"]["readable"] is False
        assert "pins no dataset snapshot" in report["data"]["detail"]

    def test_a_replayer_without_storage_says_so_rather_than_failing_oddly(
            self, replayer, validation, approved_version):
        episode = validation.open(URN, "3.2.1", "periodic", ["person/a.mehta"])
        with pytest.raises(ValidationError, match="without a storage provider"):
            replayer.from_storage(episode["id"])

    def test_coverage_answers_what_a_second_line_asks(self, snapshot_provider,
                                                      validation,
                                                      approved_version):
        """Not whether replay works, but what fraction of what was concluded
        could be checked without asking whoever concluded it."""
        validation.open(URN, "3.2.1", "periodic", ["person/a.mehta"])
        report = snapshot_provider.replayable(validation.for_model(URN))
        assert report["episodes"] == 1 and report["with_snapshot"] == 0
        assert report["coverage"] == 0.0
        assert "without asking anyone for the data" in report["detail"]
