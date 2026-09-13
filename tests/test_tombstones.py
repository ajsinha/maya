"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Deleting a model, and the identity that must not come back.

The attack these exist for is not a failed deletion. It is a *successful* one
followed by a registration: delete `pd-retail`, register a new model called
`pd-retail`, and every evidence node naming that URN now reads as though it
described the new model. `verify_chain` passes throughout, because the chain is
intact — it is simply about something else.
"""
from __future__ import annotations

import time

import pytest

from core.retention.cascade import BLOCKS, CASCADE, GOES, STAYS, Cascade
from core.retention.common import RetentionError
from core.retention.tombstones import Tombstones
import db.schema.tables  # noqa: F401 — registers every table on METADATA
from db import ModelTombstoneRepository
from db.schema.metadata import METADATA


@pytest.fixture()
def stones(db):
    return Tombstones(ModelTombstoneRepository(db))


def _row(db, table, **values):
    """Insert a row, filling whatever else the schema insists on.

    The point of these tests is the disposition, not the column list of eight
    unrelated tables, and hand-writing those made the test fail three times on
    NOT NULL columns that have nothing to do with what is being asserted.
    """
    row = dict(values)
    for col in METADATA.tables[table].columns:
        if col.name in row or col.nullable or col.server_default is not None:
            continue
        row[col.name] = 0.0 if str(col.type).upper().startswith(
            ("DOUBLE", "FLOAT", "INTEGER")) else f"{col.name}-x"
    cols = ", ".join(row)
    binds = ", ".join(f":{c}" for c in row)
    db.execute(f"INSERT INTO {table} ({cols}) VALUES ({binds})", row)


def _model(**kw):
    row = {"id": "m-1", "urn": "urn:maya:model:pd-retail", "name": "pd-retail",
           "model_class": "logistic", "domain": "credit", "owner": "ana",
           "legal_entity": "UK", "status": "retired", "tier": 2,
           "created_at": time.time() - 86400}
    row.update(kw)
    return row


class TestTheMarkerItself:
    def test_it_records_the_state_the_model_was_deleted_from(self, stones):
        """Deleting a draft is housekeeping. Deleting a retired model that made
        decisions for six years is a regulatory act, and nothing else survives
        to say which one happened."""
        stones.mark(_model(status="draft"), reason="never used", actor="ana")
        assert stones.of("urn:maya:model:pd-retail")["status"] == "draft"

    def test_it_keeps_the_count_of_what_went(self, stones):
        """After the cascade there is nothing left to count."""
        stones.mark(_model(), reason="r", actor="ana",
                    destroyed={"risk_assessment": 3, "attachment": 11})
        assert stones.of("urn:maya:model:pd-retail")["destroyed"] == {
            "risk_assessment": 3, "attachment": 11}

    def test_storage_is_not_reclaimed_by_the_deletion(self, stones):
        stones.mark(_model(), reason="r", actor="ana")
        assert stones.of("urn:maya:model:pd-retail")["compacted_at"] is None


class TestAHoleWithAShape:
    def test_a_deleted_urn_does_not_resolve_to_nothing(self, stones):
        """`None` is the answer for a name somebody mistyped. The true answer
        is *there was one, and here is what happened to it* — and every
        historical reference the cascade deliberately kept depends on it."""
        stones.mark(_model(), reason="duplicate record", actor="ana")
        got = stones.resolve("urn:maya:model:pd-retail")
        assert got["deleted"] is True
        assert got["status_when_deleted"] == "retired"
        assert got["deleted_by"] == "ana"
        assert "duplicate record" in got["reason"]

    def test_a_urn_that_never_existed_still_resolves_to_nothing(self, stones):
        assert stones.resolve("urn:maya:model:never") is None


class TestTheIdentityDoesNotComeBack:
    def test_registering_over_a_tombstone_is_refused(self, stones):
        stones.mark(_model(), reason="r", actor="ana")
        with pytest.raises(RetentionError) as e:
            stones.refuse_reuse("urn:maya:model:pd-retail")
        assert e.value.code == "urn_was_deleted"

    def test_the_refusal_says_when_and_by_whom(self, stones):
        """Somebody told *no* picks another name. Somebody told *this belonged
        to a model Ana destroyed in March* knows whether that is a problem."""
        stones.mark(_model(), reason="merged into pd-retail-v2", actor="ana")
        with pytest.raises(RetentionError) as e:
            stones.refuse_reuse("urn:maya:model:pd-retail")
        assert "ana" in e.value.detail
        assert "merged into pd-retail-v2" in e.value.detail

    def test_an_unused_urn_is_not_refused(self, stones):
        stones.refuse_reuse("urn:maya:model:brand-new")

    def test_there_is_no_override(self):
        """A URN a register can hand out twice is not an identity."""
        import inspect
        src = inspect.getsource(Tombstones.refuse_reuse)
        assert "force" not in src and "override" not in src.split("no override")[0]


class TestTheCascadeDeclaration:
    def test_every_table_carrying_a_model_id_has_a_disposition(self):
        """The defect this whole module came from.

        `ReferenceIndex._to_model` asked twenty of the thirty-eight tables
        carrying a `model_id`. It did not fail on the other eighteen — a
        reference check that misses a table *approves*. Adding a table must
        force the decision rather than default to silently unchecked.
        """
        from db.schema.metadata import METADATA
        import db.schema.tables  # noqa: F401
        carry = {t.name for t in METADATA.tables.values()
                 if "model_id" in {c.name for c in t.columns}}
        declared = {d.table for d in CASCADE}
        assert not carry - declared, (
            f"no disposition declared for {sorted(carry - declared)} — decide "
            f"whether a row blocks the deletion, goes with the model, or "
            f"stays as the record that something happened")
        assert not declared - carry, (
            f"declared for tables that do not carry a model_id: "
            f"{sorted(declared - carry)}")

    def test_every_blocking_predicate_executes(self, db):
        """A predicate naming a column that is not there raises. A predicate
        naming a *value* that is never used matches nothing and fails silently
        open — which is why the state names are imported, not retyped."""
        for d in CASCADE:
            sql = (d.blocking_sql() if d.kind == BLOCKS
                   else f"SELECT id FROM {d.table} WHERE model_id = :m")
            db.query(sql, {"m": "nobody"})

    def test_every_disposition_is_one_of_the_three(self):
        assert {d.kind for d in CASCADE} <= {BLOCKS, GOES, STAYS}

    def test_every_declaration_says_what_the_row_is(self):
        """`why` is shown to the person who is told they may not delete."""
        assert all(len(d.why) > 20 for d in CASCADE)


class TestTheCascadeRuns:
    def test_a_blocking_row_is_reported_with_its_reason(self, db):
        _row(db, "campaign_item", id="ci-1", model_id="m-1",
             state="outstanding")
        blocking = Cascade(db).blocking("m-1")
        assert [b["table"] for b in blocking] == ["campaign_item"]
        assert "can never be" in blocking[0]["why"]

    def test_an_answered_campaign_item_does_not_block(self, db):
        _row(db, "campaign_item", id="ci-1", model_id="m-1", state="answered")
        assert Cascade(db).blocking("m-1") == []

    def test_dependent_rows_go_and_are_counted(self, db):
        for n in ("l-1", "l-2"):
            _row(db, "model_limitation", id=n, model_id="m-1", reference=n)
        counts = Cascade(db).destroy("m-1")
        assert counts["model_limitation"] == 2
        assert db.query("SELECT id FROM model_limitation "
                        "WHERE model_id = 'm-1'") == []

    def test_the_record_of_what_happened_stays_and_is_counted(self, db):
        """An inference is a decision the model actually made and somebody
        relied on. A deletion must not be able to erase that."""
        _row(db, "warrant_invocation", id="i-1", model_id="m-1")
        counts = Cascade(db).destroy("m-1")
        assert counts["warrant_invocation (kept)"] == 1
        assert len(db.query("SELECT id FROM warrant_invocation "
                            "WHERE model_id = 'm-1'")) == 1

    def test_a_cascade_over_a_model_with_nothing_attached_counts_nothing(self, db):
        assert Cascade(db).destroy("m-nothing") == {}
