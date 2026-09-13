"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A clock that is not a number stops every point-in-time read of its view.

`_check_clocks` asserted both clocks were **present** and never that they were
**comparable**, and comparability is the entire job:

    r[VALID_TIME] <= label_ts and r[INGEST_TIME] <= knowable_by

So `event_ts: "2026-01-01T00:00:00Z"` was accepted — 201, a recorded version,
a pinned Delta table — and then every assembly over that view answered 500
with `'<=' not supported between instances of 'str' and 'float'`. Not the one
row: the whole view, for every entity, because the comparison walks all
candidates before choosing one.

One malformed row from one loader ends the point-in-time story for a view
until somebody finds it, and the place it surfaces is a 500 on a read rather
than a refusal on the write that caused it.
"""
from __future__ import annotations

import pytest

from core.features.common import FeatureError


class TestBothClocksMustBeNumbers:
    def test_an_iso_string_in_the_valid_clock_is_refused(self, features):
        with pytest.raises(FeatureError) as refused:
            features.views._check_clocks([
                {"entity_id": "b1", "event_ts": "2026-01-01T00:00:00Z",
                 "ingest_ts": 100.0}])
        assert "not a number" in str(refused.value)

    def test_an_iso_string_in_the_ingest_clock_is_refused(self, features):
        with pytest.raises(FeatureError):
            features.views._check_clocks([
                {"entity_id": "b1", "event_ts": 100.0,
                 "ingest_ts": "2026-01-01T00:00:00Z"}])

    def test_none_is_refused(self, features):
        with pytest.raises(FeatureError):
            features.views._check_clocks([
                {"entity_id": "b1", "event_ts": None, "ingest_ts": 100.0}])

    def test_a_boolean_is_refused(self, features):
        """`True <= 100.0` is legal Python and meaningless as a timestamp, so
        a plain comparability check would let it through to sort as 1."""
        with pytest.raises(FeatureError) as refused:
            features.views._check_clocks([
                {"entity_id": "b1", "event_ts": True, "ingest_ts": 100.0}])
        assert "bool" in str(refused.value)

    def test_the_refusal_names_the_row_and_the_clock(self, features):
        """Two hundred rows arrive at once. "A clock is wrong" sends somebody
        to read all of them."""
        with pytest.raises(FeatureError) as refused:
            features.views._check_clocks([
                {"entity_id": "b1", "event_ts": 100.0, "ingest_ts": 100.0},
                {"entity_id": "b2", "event_ts": "nope", "ingest_ts": 100.0}])
        said = str(refused.value)
        assert "row 1" in said and "event_ts" in said

    def test_integers_and_floats_both_pass(self, features):
        features.views._check_clocks([
            {"entity_id": "b1", "event_ts": 100, "ingest_ts": 100.5}])
