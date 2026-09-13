"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A board pack indicator that reads a key nothing publishes.

Two of them did, and both reported **zero on every estate**:

`attestations_lapsed` read `state["attestation_lapsed"]` and `state["lapsed"]`;
`LifecycleService.state` publishes `attestation_expired`. `baseline_debt` read
`portfolio()["open_debt"]`; the key is `debt_open`, transposed.

The failure is silent by construction. `.get("wrong_key", 0)` returns 0, 0 is a
perfectly good count, and a pack saying *no lapsed attestations* is the answer
a healthy estate gives — so the indicator looked right in exactly the case
where it mattered most that it was not. Two wrong names side by side even read
as thoroughness.

QA found these by predicting them: a case that said *"expected a positive
count; suspect 0"*. This is what would have found them without the prediction.
"""
from __future__ import annotations

import inspect
import re

from core.baseline.importer import BaselineImporter
from core.lifecycle.service import LifecycleService
from core.reporting import indicators


def _keys_returned(fn) -> set:
    """The literal string keys a function puts into the dict it returns."""
    return set(re.findall(r'"([a-z_]+)"\s*:', inspect.getsource(fn)))


class TestAnIndicatorOnlyReadsKeysThatExist:
    def test_the_lapsed_attestation_indicator_reads_a_published_key(self):
        published = _keys_returned(LifecycleService.state)
        read = set(re.findall(
            r'state\.get\("([a-z_]+)"',
            inspect.getsource(indicators)))
        assert read, "the scan found no state key; check the pattern"
        assert read <= published, (
            f"the board pack reads {sorted(read - published)} off "
            f"LifecycleService.state, which publishes "
            f"{sorted(published)[:6]}… — a `.get` on a key nobody writes "
            f"returns the default forever, and for a count the default is a "
            f"clean bill of health")

    def test_the_baseline_debt_indicator_reads_a_published_key(self):
        published = _keys_returned(BaselineImporter.portfolio)
        read = set(re.findall(
            r'portfolio\(\)\s*or\s*\{\}\)\.get\("([a-z_]+)"',
            inspect.getsource(indicators)))
        assert read, "the scan found no portfolio key; check the pattern"
        assert read <= published, (
            f"the board pack reads {sorted(read - published)} off "
            f"portfolio(), which publishes {sorted(published)}")

    def test_the_indicators_are_not_all_reading_from_nothing(self):
        """A guard on the guard.

        Both assertions above pass trivially if the regex finds nothing, and a
        scan that silently matches zero keys is how the original defect
        survived — a check that looks at nothing agrees with everything.
        """
        source = inspect.getsource(indicators)
        assert source.count(".get(") >= 2
