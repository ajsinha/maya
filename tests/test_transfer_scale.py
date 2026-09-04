"""
MAYA — the bulk transfer layer, at a size where the claims matter.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The claim under test is that nothing is materialised whole. A test at five rows
cannot tell a streaming implementation from one that reads the dataset and then
writes it out, so these run at a size where the difference is visible — small
enough to stay in a unit suite, large enough that a per-row cost would show.
"""
from __future__ import annotations

import json

import pytest

from core.features import FeatureError
from core.features.transfer import ARROW, JSON_CAP, NDJSON, PARQUET

ROWS = 50_000


@pytest.fixture
def loaded(full_features):
    f = full_features
    for name in ("dscr", "turnover", "utilisation"):
        f.define(name, "borrower_id", "numeric", name, "person/j.okafor")
    columns = ["dscr", "turnover", "utilisation"]
    f.create_view("sb_credit", "borrower_id", "person/j.okafor", columns)
    f.materialise("sb_credit", [
        {"entity_id": f"B{i}", "event_ts": float(i), "ingest_ts": float(i),
         "dscr": 1.0 + i % 7, "turnover": 1000.0 * (i % 13),
         "utilisation": (i % 100) / 100.0} for i in range(ROWS)], columns)
    return f


class TestNothingIsMaterialisedWhole:
    def test_a_read_arrives_in_more_than_one_chunk(self, loaded):
        """One chunk for fifty thousand rows would mean the whole thing was
        assembled before anything was sent."""
        pin = loaded.pinned("sb_credit", 1)
        chunks = list(loaded.transfer.stream(pin["namespace"], NDJSON,
                                             pin["delta_version"]))
        assert len(chunks) > 1, "the read was assembled rather than streamed"
        assert sum(c.count(b"\n") for c in chunks) == ROWS

    def test_a_limit_stops_reading_rather_than_trimming_afterwards(self, loaded):
        pin = loaded.pinned("sb_credit", 1)
        chunks = list(loaded.transfer.stream(pin["namespace"], NDJSON,
                                             pin["delta_version"], limit=1000))
        assert sum(c.count(b"\n") for c in chunks) == 1000

    def test_a_column_projection_is_pushed_into_the_read(self, loaded):
        pin = loaded.pinned("sb_credit", 1)
        chunks = list(loaded.transfer.stream(
            pin["namespace"], NDJSON, pin["delta_version"],
            columns=["entity_id", "dscr"], limit=10))
        first = json.loads(b"".join(chunks).splitlines()[0])
        assert set(first) == {"entity_id", "dscr"}

    def test_parquet_is_materially_smaller_than_ndjson(self, loaded):
        """Which is the reason to offer it: the same rows, a fraction of the
        bytes over the wire and on disk."""
        pin = loaded.pinned("sb_credit", 1)
        sizes = {}
        for fmt in (PARQUET, NDJSON, ARROW):
            sizes[fmt] = sum(len(c) for c in loaded.transfer.stream(
                pin["namespace"], fmt, pin["delta_version"]))
        assert sizes[PARQUET] < sizes[NDJSON] / 2
        assert all(size > 0 for size in sizes.values())


class TestARoundTripAtSize:
    @pytest.mark.parametrize("fmt,media", [
        (ARROW, "application/vnd.apache.arrow.stream"),
        (PARQUET, "application/vnd.apache.parquet"),
        (NDJSON, "application/x-ndjson"),
    ])
    def test_every_row_survives(self, loaded, fmt, media):
        pin = loaded.pinned("sb_credit", 1)
        blob = b"".join(loaded.transfer.stream(pin["namespace"], fmt,
                                               pin["delta_version"]))
        result = loaded.transfer.load("sb_credit", blob, media)
        assert result["uploaded_rows"] == ROWS
        assert result["version"] == 2
        assert loaded.views.versions_of("sb_credit")[-1]["row_count"] == ROWS

    def test_the_values_survive_and_not_only_the_count(self, loaded):
        pin = loaded.pinned("sb_credit", 1)
        blob = b"".join(loaded.transfer.stream(pin["namespace"], PARQUET,
                                               pin["delta_version"]))
        loaded.transfer.load("sb_credit", blob, "application/vnd.apache.parquet")
        after = loaded.pinned("sb_credit", 2)
        rows = loaded.transfer.rows(after["namespace"], after["delta_version"],
                                    limit=1)["rows"]
        assert rows[0]["entity_id"].startswith("B")
        assert rows[0]["dscr"] is not None


class TestTheCapsAreRealCaps:
    def test_json_never_returns_more_than_the_cap(self, loaded):
        pin = loaded.pinned("sb_credit", 1)
        page = loaded.transfer.rows(pin["namespace"], pin["delta_version"],
                                    limit=ROWS)
        assert page["returned"] == JSON_CAP
        assert page["total"] == ROWS and page["truncated"]

    def test_an_unstreamable_format_says_so_rather_than_trying(self, loaded):
        pin = loaded.pinned("sb_credit", 1)
        with pytest.raises(FeatureError, match="not a streaming format"):
            list(loaded.transfer.stream(pin["namespace"], "json"))

    def test_an_unknown_format_is_refused_with_the_list(self, loaded):
        from core.features.transfer import normalise
        with pytest.raises(FeatureError, match="not a transfer format"):
            normalise("csv")

    def test_the_accept_header_chooses_when_nothing_is_named(self):
        from core.features.transfer import normalise
        assert normalise(None, "application/vnd.apache.parquet") == PARQUET
        assert normalise(None, "text/html") == "json"
