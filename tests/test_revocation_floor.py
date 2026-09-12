"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The revocation floor: what it refuses offline, and what it does not claim.

Finding C-1 said a revoked warrant must be refused by an engine that cannot
reach MAYA, and three documents described a locally persisted list that did it.
`docs/11 §4.2` found the list inert. Two of its three complaints have since been
fixed quietly — `note_revocation` keys on the model URN, which survives a
re-resolve, and the epoch is seeded from the register rather than from zero — and
the third was still true: **the epoch was stamped on every descriptor and
compared by nothing.**

A field stamped on every warrant and read by nobody is the defect this platform
names as its own worst kind, so the comparison now happens. These tests pin both
halves of it: what it refuses, and — at least as important — what it is not
allowed to claim.
"""
from __future__ import annotations

import pytest

from core.execution.errors import WarrantError


class TestADescriptorOlderThanARevocationIsRefused:
    def test_a_lower_epoch_than_one_already_seen_refuses(self, engine):
        """The whole offline content of the floor. An engine shown epoch 7
        knows authority was withdrawn seven times; a descriptor stamped 5 was
        minted before the sixth."""
        engine._seen_epoch = 7
        with pytest.raises(WarrantError) as refusal:
            engine._refuse_stale_epoch(_descriptor(5))
        assert refusal.value.code == "revoked_epoch"
        assert "predates at least one withdrawal" in refusal.value.detail

    def test_the_same_epoch_passes(self, engine):
        engine._seen_epoch = 7
        engine._refuse_stale_epoch(_descriptor(7))

    def test_a_newer_epoch_passes_and_raises_the_floor(self, engine):
        engine._refuse_stale_epoch(_descriptor(4))
        assert engine._seen_epoch == 4
        with pytest.raises(WarrantError):
            engine._refuse_stale_epoch(_descriptor(3))

    def test_the_floor_never_falls(self, engine):
        for epoch in (2, 9, 5, 9):
            try:
                engine._refuse_stale_epoch(_descriptor(epoch))
            except WarrantError:
                pass
        assert engine._seen_epoch == 9

    def test_a_descriptor_with_no_epoch_is_not_refused(self, engine):
        """Absence is not a stale epoch. A descriptor minted before the field
        existed is not evidence of a revocation."""
        engine._seen_epoch = 7
        engine._refuse_stale_epoch({"authority": {}})

    def test_it_needs_nothing_but_what_the_engine_was_shown(self, engine):
        """Offline is the point: an engine that could ask MAYA would not need a
        floor, because asking MAYA is what a partition prevents."""
        engine.warrants = None            # nothing to reach
        engine._seen_epoch = 3
        with pytest.raises(WarrantError):
            engine._refuse_stale_epoch(_descriptor(1))


class TestWhatTheFloorDoesNotClaim:
    def test_the_descriptor_says_monotonic_rather_than_required(self):
        """`check: required` was a claim the platform could not back — it does
        not run engines and cannot push a withdrawal to one."""
        from core.execution import builder
        source = _source(builder)
        assert '"check": "monotonic"' in source
        assert '"check": "required"' not in source

    def test_the_code_says_maya_cannot_push_a_revocation(self):
        from core.execution import engine as engine_module
        doc = engine_module.CaptiveEngine._refuse_stale_epoch.__doc__
        assert "MAYA does not tell it" in " ".join(doc.split())
        assert "does not run engines" in doc

    def test_it_names_the_ttl_as_the_bound_on_the_residual(self):
        """The severity-scaled TTL is the honest whole answer to what this
        cannot see, not a footnote to it. A Tier 1 descriptor lives sixty
        seconds with no grace."""
        from core.execution.engine import CaptiveEngine
        from core.execution.grants import DEFAULT_GRACE, DEFAULT_TTL
        assert DEFAULT_TTL[1] == 60 and DEFAULT_GRACE[1] == 0
        assert "severity-scaled TTL" in \
            CaptiveEngine._refuse_stale_epoch.__doc__

    def test_the_persisted_list_c1_described_is_not_claimed(self):
        from core.execution.engine import CaptiveEngine
        assert "is not built and is not claimed" in \
            CaptiveEngine._refuse_stale_epoch.__doc__


def _descriptor(epoch):
    return {"authority": {"revocation": {"epoch": epoch,
                                         "check": "monotonic"}}}


def _source(module):
    import inspect
    return inspect.getsource(module)


@pytest.fixture
def engine():
    """The engine object alone. These tests are about one comparison, and
    standing an executable estate up around it would test everything else."""
    from core.execution.engine import CaptiveEngine
    made = CaptiveEngine.__new__(CaptiveEngine)
    made._revoked_locally = set()
    made._seen_epoch = 0
    return made
