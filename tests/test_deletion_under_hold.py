"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A legal hold, and the one act it exists to stop.

`LegalHolds.held` has documented itself as **"the question a deleter asks"**
since it was written, and `applies` says a hold must be consulted *from inside*
a deletion rather than beside it, "because a hold a retention job can race is
not a hold". Both were true of the inference log and the retention schedule.
Neither was true of `LifecycleService.delete` — the only act in this platform
with no workflow, no reversal and no second signature.

So a model under an active hold could be destroyed, and the module that would
have refused it was sitting in the same process. Found by re-checking the
adversarial review's own dispositions against the source, which is the third
time this session that a control turned out to exist and not be consulted.
"""
from __future__ import annotations

import pytest

from core.lifecycle.common import LifecycleError
from core.retention.holds import LegalHolds
from db import LegalHoldRepository

ADMIN = {"username": "root", "roles": ["admin"]}


@pytest.fixture
def holds(db, evidence, registry):
    return LegalHolds(LegalHoldRepository(db), evidence, registry)


@pytest.fixture
def held(lifecycle, holds):
    lifecycle.holds = holds
    return lifecycle


class TestDeletionRefusesThroughAHold:
    def test_a_hold_over_the_model_refuses(self, held, holds, a_model):
        holds.place(matter="Regulator request 2026/14", owner="person/legal",
                    scope_kind="model", scope_id=a_model["id"])
        with pytest.raises(LifecycleError) as refusal:
            held.delete(a_model, ADMIN, "cleaning up")
        assert refusal.value.code == "under_legal_hold"
        assert "spoliation" in refusal.value.remediation

    def test_an_estate_wide_hold_refuses(self, held, holds, a_model):
        holds.place(matter="Regulator request 2026/14", owner="person/legal")
        with pytest.raises(LifecycleError):
            held.delete(a_model, ADMIN, "cleaning up")

    def test_the_refusal_names_the_matters(self, held, holds, a_model):
        placed = holds.place(matter="Regulator request 2026/14",
                             owner="person/legal")
        with pytest.raises(LifecycleError) as refusal:
            held.delete(a_model, ADMIN, "cleaning up")
        assert placed["reference"] in refusal.value.detail

    def test_there_is_no_override(self, held):
        """A hold a deletion could step over would not be a hold. Lifting one
        is a separate act, with a reason, on the record."""
        import inspect
        source = inspect.getsource(held.delete.__func__)
        assert "force" not in source

    def test_nothing_is_written_when_it_refuses(self, held, holds, evidence,
                                                a_model):
        """Asked BEFORE the evidence node, so a refused deletion leaves no
        `model_deleted` in the chain saying somebody destroyed a record they
        did not destroy."""
        holds.place(matter="Regulator request 2026/14", owner="person/legal")
        with pytest.raises(LifecycleError):
            held.delete(a_model, ADMIN, "cleaning up")
        assert "model_deleted" not in str(evidence.for_subject(a_model["id"]))

    def test_the_model_survives(self, held, holds, registry, a_model):
        holds.place(matter="Regulator request 2026/14", owner="person/legal")
        with pytest.raises(LifecycleError):
            held.delete(a_model, ADMIN, "cleaning up")
        assert registry.get(a_model["urn"]) is not None


class TestWhatStillDeletes:
    def test_with_no_hold_the_deletion_proceeds(self, held, a_model,
                                                registry):
        assert held.delete(a_model, ADMIN, "registered by mistake")["deleted"]
        assert registry.get(a_model["urn"]) is None

    def test_a_lifted_hold_no_longer_refuses(self, held, holds, a_model):
        placed = holds.place(matter="Regulator request 2026/14",
                             owner="person/legal")
        holds.lift(placed["reference"], "the matter closed",
                   actor="person/legal")
        assert held.delete(a_model, ADMIN, "registered by mistake")["deleted"]

    def test_a_hold_over_another_model_does_not_refuse(self, held, holds,
                                                       registry, a_model):
        registry.register("maya://model/other.one", "Other",
                          "credit.pd.scorecard", "credit", "person/j.okafor",
                          "LE-US-01", "p")
        other = registry.get("maya://model/other.one")
        holds.place(matter="Regulator request 2026/14", owner="person/legal",
                    scope_kind="model", scope_id=other["id"])
        assert held.delete(a_model, ADMIN, "registered by mistake")["deleted"]

    def test_a_lifecycle_with_no_holds_register_still_deletes(self, lifecycle,
                                                              a_model):
        """The collaborator is optional: a unit configuration without a holds
        register must not become one where nothing can be deleted."""
        assert lifecycle.holds is None
        assert lifecycle.delete(a_model, ADMIN, "no holds here")["deleted"]
