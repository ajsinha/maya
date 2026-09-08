"""
MAYA — closing a schema drift.

`drift()` has always reported precisely what is missing and then said "apply the
difference by hand". That sentence is the reason a development database with
months of evidence in it gets deleted rather than fixed, and a governance
platform whose answer to "your record does not match the code" is "start again"
is not one anybody keeps a record in.

`repair()` closes the loop without becoming a migration framework. These tests
hold the four things that distinction rests on: it adds what the shipped DDL
declares and nothing else; it cannot lose a row; it REFUSES rather than guesses
where an existing row would need a value nobody chose; and it never runs by
itself.
"""
from __future__ import annotations

import inspect

import pytest

from db.database import Database


def _behind(tmp_path, rows: bool):
    """A database whose `featureset` table is many columns behind the DDL.

    Empty or populated on purpose: the two cases are genuinely different, and
    the difference IS the design. A column the DDL declares `NOT NULL` with no
    default can be added to an empty table and cannot be added to one holding
    rows, because there is no value to put in them.
    """
    db = Database(f"sqlite:///{tmp_path}/maya.db")
    db.execute("DROP TABLE IF EXISTS featureset")
    db.execute("CREATE TABLE featureset (id TEXT PRIMARY KEY, name TEXT)")
    if rows:
        db.execute("INSERT INTO featureset (id, name) VALUES ('fs-1', 'kept')")
    return db


@pytest.fixture
def drifted(tmp_path):
    """Behind the DDL, and holding a row somebody would mind losing."""
    return _behind(tmp_path, rows=True)


@pytest.fixture
def drifted_empty(tmp_path):
    return _behind(tmp_path, rows=False)


class TestItAddsWhatTheSchemaDeclares:
    def test_the_drift_is_closed_completely_on_an_empty_table(self, drifted_empty):
        assert drifted_empty.drift(), "the fixture is drifted to begin with"
        drifted_empty.repair(dry_run=False)
        assert "featureset" not in str(drifted_empty.drift())

    def test_a_populated_table_is_closed_as_far_as_it_safely_can_be(self, drifted):
        """The columns that can be added ARE added; the ones that would need a
        value for the existing rows stay in the drift report, which is exactly
        where somebody looking for what is left will look."""
        before = set(drifted.drift()["featureset"])
        drifted.repair(dry_run=False)
        after = set(drifted.drift().get("featureset", []))
        assert after < before, "some columns were added"
        assert after, "and the ones needing a decision are still reported"
        assert all("NOT NULL" in drifted.declared_columns()["featureset"][
            entry.split("'")[1]].upper() for entry in after)

    def test_the_row_survives(self, drifted):
        """ALTER TABLE ADD COLUMN cannot lose a row, and the whole argument for
        repairing rather than recreating is that the rows are the point."""
        drifted.repair(dry_run=False)
        assert drifted.query_one("SELECT name FROM featureset WHERE id='fs-1'"
                                 )["name"] == "kept"

    def test_a_dry_run_changes_nothing(self, drifted):
        plan = drifted.repair()
        assert plan["planned"] and not plan["applied"]
        assert drifted.drift(), "still drifted; nothing was applied"

    def test_the_plan_is_the_statement_that_will_run(self, drifted):
        """Naming the SQL rather than the column: an operator who has to
        approve a change to a production schema is approving the statement."""
        plan = drifted.repair()
        for step in plan["planned"]:
            assert step["sql"].startswith(f"ALTER TABLE {step['table']} ADD COLUMN")
            assert step["column"] in step["sql"]

    def test_it_adds_nothing_the_ddl_does_not_declare(self, drifted):
        declared = drifted.declared_columns()["featureset"]
        for step in drifted.repair()["planned"]:
            assert step["column"] in declared

    def test_a_matching_database_has_nothing_to_do(self, tmp_path):
        db = Database(f"sqlite:///{tmp_path}/fresh.db")
        plan = db.repair()
        assert not plan["planned"] and not plan["refused"]
        assert plan["detail"] == "nothing to repair"


class TestItRefusesRatherThanGuesses:
    def test_a_not_null_column_with_no_default_is_reported(self, tmp_path):
        """There is no value to put in the existing rows that anybody has
        chosen. Guessing is how a governance register acquires a column full of
        zeros nobody decided on — so it is named, with its declaration, and
        left."""
        db = Database(f"sqlite:///{tmp_path}/maya.db")
        db.execute("DROP TABLE IF EXISTS scratch_repair")
        db.execute("CREATE TABLE scratch_repair (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO scratch_repair (id) VALUES ('one')")

        # Stand in for the shipped DDL: one column that cannot be added to a
        # populated table, and one that can.
        original = db.declared_columns
        db.declared_columns = lambda: {"scratch_repair": {
            "id": "id TEXT PRIMARY KEY",
            "owner": "owner TEXT NOT NULL",
            "note": "note TEXT NOT NULL DEFAULT ''"}}
        try:
            plan = db.repair()
        finally:
            db.declared_columns = original

        refused = {step["column"] for step in plan["refused"]}
        planned = {step["column"] for step in plan["planned"]}
        assert refused == {"owner"} and planned == {"note"}
        why = plan["refused"][0]["why"]
        assert "NOT NULL" in why and "1 row" in why
        assert plan["refused"][0]["declaration"] == "owner TEXT NOT NULL"

    def test_an_empty_table_takes_it_happily(self, tmp_path):
        """The refusal is about the ROWS, not about the column. With nothing in
        the table there is nothing to invent a value for."""
        db = Database(f"sqlite:///{tmp_path}/maya.db")
        db.execute("DROP TABLE IF EXISTS scratch_repair")
        db.execute("CREATE TABLE scratch_repair (id TEXT PRIMARY KEY)")
        db.declared_columns = lambda: {"scratch_repair": {
            "id": "id TEXT PRIMARY KEY", "owner": "owner TEXT NOT NULL"}}
        plan = db.repair()
        assert not plan["refused"]
        assert [step["column"] for step in plan["planned"]] == ["owner"]

    def test_a_table_that_is_absent_is_left_to_the_ddl(self, tmp_path):
        """`CREATE TABLE IF NOT EXISTS` makes missing tables at start-up. A
        repair that also tried would be a second way to create one, and two
        ways to make a table is one too many."""
        db = Database(f"sqlite:///{tmp_path}/maya.db")
        db.declared_columns = lambda: {"never_declared_anywhere": {
            "id": "id TEXT PRIMARY KEY"}}
        assert db.repair()["planned"] == []


class TestItDoesNotRunByItself:
    def test_starting_the_server_does_not_repair(self):
        """A process that alters the schema every time somebody starts it is
        one nobody can reason about — and the point of the drift report is that
        a PERSON decides."""
        import run_maya_web

        assert "repair" not in inspect.getsource(run_maya_web.create_app)

    def test_the_flags_exist_and_check_is_the_safe_one(self):
        import run_maya_web

        source = inspect.getsource(run_maya_web.main)
        assert "--check-schema" in source and "--repair-schema" in source
        repair = inspect.getsource(run_maya_web._repair_schema)
        assert 'apply="--repair-schema" in sys.argv' in source, \
            "only the explicit flag applies anything"
        assert "dry_run=not apply" in repair

    def test_it_reports_the_drift_that_remains(self):
        """A repair that said '29 columns added' and left a drift nobody
        mentioned would be this codebase's own recurring defect: a control that
        reports success while answering a narrower question than the reader
        believes it answered."""
        import run_maya_web

        assert "drift after" in inspect.getsource(run_maya_web._repair_schema)


class TestTheDeclarationIsParsedWhole:
    """`declared_schema()` returns column NAMES, which is all a drift check
    needs. An ALTER has to reproduce the type, the default and the NOT NULL."""

    def test_the_type_and_default_come_through(self, tmp_path):
        db = Database(f"sqlite:///{tmp_path}/maya.db")
        feature = db.declared_columns()["feature"]
        assert feature["ephemeral"] == "ephemeral INTEGER NOT NULL DEFAULT 0"
        assert feature["retired_at"] == "retired_at REAL"

    def test_a_table_constraint_is_not_mistaken_for_a_column(self, tmp_path):
        db = Database(f"sqlite:///{tmp_path}/maya.db")
        for table, columns in db.declared_columns().items():
            for name in columns:
                assert name.upper() not in {"PRIMARY", "UNIQUE", "FOREIGN",
                                            "CHECK", "CONSTRAINT"}, table

    def test_every_declared_column_is_named_by_both_readers(self, tmp_path):
        """The two parsers must agree, or a drift is reported that a repair
        then cannot see."""
        db = Database(f"sqlite:///{tmp_path}/maya.db")
        names = db.declared_schema()
        full = db.declared_columns()
        assert set(names) == set(full)
        for table in names:
            assert set(names[table]) == set(full[table]), table
