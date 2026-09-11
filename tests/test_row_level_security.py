"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

H-5, the oldest open finding, and the negative test it actually asked for.

The attack, in the review's own words: a validator scoped to one legal entity
looks for a listing endpoint whose author forgot `Scope.filter`. The disposition
said *not built*, and gave a reason that was true — *there is one connection
identity, so RLS would have nothing to distinguish anyway*. That reason is what
`routes/base.py::_identify` now removes: the acting principal's entity scope goes
onto the connection the request is using, and a PostgreSQL policy reads it.

**These tests run against a real PostgreSQL when one is reachable, and skip
loudly when it is not.** That is deliberate and it is the whole point of the
finding: *untested isolation is assumed isolation.* Asserting the policy text is
not a test of the policy, and a green suite that never ran a cross-entity read
would be exactly the assurance H-5 objected to. So the policy assertions below
are marked for what they are — checks on the DDL — and the isolation assertions
need a database.

What the Postgres run establishes, and what was found by running it rather than
by reasoning about it: with `FORCE` in place and the session variable unset, a
non-superuser owner reads **zero rows**. A **superuser reads everything**,
`FORCE` or not. So a deployment can apply every statement here perfectly, connect
as `postgres`, and have a backstop that does nothing while looking correct.
"""
from __future__ import annotations

import os

import pytest

from core.security.rls import (ESTATE_WIDE, GUC, SCOPED_TABLES,
                               RowLevelSecurity, policy_statements)

#: Set to a PostgreSQL URL to run the isolation tests. Without it they skip,
#: and the skip is the finding: untested isolation is assumed isolation.
PG_URL = os.environ.get("MAYA_TEST_POSTGRES", "")

psycopg = pytest.importorskip("psycopg", reason="no PostgreSQL driver")


class TestTheStatementsSayWhatTheyMust:
    """Checks on the DDL. Not a test of the isolation — see the module note."""

    def test_every_scoped_table_is_forced_not_merely_enabled(self):
        """Enabled-without-forced is the configuration that looks right in a
        screenshot and lets the table owner read everything."""
        sql = "\n".join(policy_statements())
        for table, _ in SCOPED_TABLES:
            assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql
            assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in sql

    def test_it_creates_a_role_that_owns_nothing(self):
        sql = "\n".join(policy_statements("some_app"))
        assert "CREATE ROLE some_app NOLOGIN" in sql
        assert "OWNS NOTHING" in sql

    def test_the_policy_reads_a_session_variable(self):
        sql = "\n".join(policy_statements())
        assert f"current_setting('{GUC}', true)" in sql

    def test_it_is_idempotent(self):
        """A deployment applies these on every release without tracking
        whether it already did."""
        sql = "\n".join(policy_statements())
        assert "DROP POLICY IF EXISTS" in sql
        assert "IF NOT EXISTS (SELECT 1 FROM pg_roles" in sql

    def test_the_statements_are_published_not_executed(self):
        """Creating a role in a bank's cluster is a decision about a database
        MAYA does not operate."""
        assert "MAYA does not run these itself" in policy_statements.__doc__


class TestOnSqliteItSaysThereIsNoBackstop:
    def test_it_reports_unavailable_rather_than_silent(self, db):
        """A development deployment believing it has a backstop is worse off
        than one that knows it does not."""
        out = RowLevelSecurity(db).in_force()
        assert out["available"] is False
        assert "cannot be" in out["detail"]

    def test_applying_a_scope_is_a_no_op_and_still_returns_it(self, db):
        assert RowLevelSecurity(db).apply(["LE-US-01"]) == "LE-US-01"
        assert RowLevelSecurity(db).apply(None) == ESTATE_WIDE

    def test_the_posture_says_it_is_not_the_control(self, db):
        out = RowLevelSecurity(db).posture()
        assert out["is_the_control"] is False
        assert "indistinguishable from 'there is nothing'" in \
            out["why_not_the_control"]

    def test_it_names_what_it_does_not_reach(self, db):
        """Only rows that CARRY an entity can be filtered by one."""
        assert "subquery per row" in RowLevelSecurity(db).posture()[
            "does_not_reach"]


@pytest.mark.skipif(not PG_URL, reason=(
    "no PostgreSQL. Set MAYA_TEST_POSTGRES to run the cross-entity read that "
    "H-5 actually asked for — and note that skipping IS the finding: untested "
    "isolation is assumed isolation"))
class TestTheCrossEntityReadReturnsZeroRows:
    """The negative test the finding named. Needs a real database."""

    @pytest.fixture
    def estate(self):
        owner = psycopg.connect(PG_URL, autocommit=True)
        owner.execute("DROP TABLE IF EXISTS model CASCADE")
        owner.execute("DROP TABLE IF EXISTS risk_appetite_limit CASCADE")
        owner.execute("CREATE TABLE model (id text primary key, "
                      "legal_entity text not null)")
        owner.execute("CREATE TABLE risk_appetite_limit (id text primary key, "
                      "legal_entity text not null)")
        owner.execute("INSERT INTO model VALUES ('1','LE-US-01'),"
                      "('2','LE-UK-01'),('3','LE-US-01')")
        owner.execute("\n".join(policy_statements("maya_app")))
        owner.execute("DROP ROLE IF EXISTS maya_app_login")
        owner.execute("CREATE ROLE maya_app_login LOGIN PASSWORD 'apppw' "
                      "IN ROLE maya_app")
        owner.execute("GRANT USAGE ON SCHEMA public TO maya_app")
        app_url = PG_URL.replace("postgres:", "maya_app_login:", 1) \
            if "postgres:" in PG_URL else PG_URL
        yield owner, psycopg.connect(app_url)
        owner.close()

    @staticmethod
    def _rows(app, entities):
        with app.transaction():
            if entities is not None:
                app.execute("SELECT set_config(%s,%s,true)", (GUC, entities))
            return sorted(r[0] for r in
                          app.execute("SELECT id FROM model").fetchall())

    def test_a_validator_scoped_to_one_entity_cannot_read_another(self, estate):
        """The finding, executed."""
        _, app = estate
        assert self._rows(app, "LE-UK-01") == ["2"]
        assert self._rows(app, "LE-US-01") == ["1", "3"]

    def test_an_unset_scope_admits_nothing(self, estate):
        """Default deny. A policy that failed open on a missing setting would
        do nothing the moment a pooled connection is recycled without one —
        exactly when it is needed."""
        _, app = estate
        assert self._rows(app, None) == []

    def test_the_estate_wide_marker_admits_everything(self, estate):
        _, app = estate
        assert self._rows(app, ESTATE_WIDE) == ["1", "2", "3"]

    def test_several_entities_are_carried(self, estate):
        _, app = estate
        assert self._rows(app, "LE-UK-01,LE-US-01") == ["1", "2", "3"]

    def test_a_superuser_bypasses_all_of_it(self, estate):
        """Found by running this rather than by reasoning about it, and it is
        the most important line in the file: a deployment can apply every
        statement perfectly, connect as `postgres`, and have a backstop that
        does nothing while looking correct."""
        owner, _ = estate
        assert len(owner.execute("SELECT id FROM model").fetchall()) == 3
        assert owner.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone()[0] is True

    def test_the_platform_reports_that_exemption(self, estate):
        owner, _ = estate

        class _Db:
            dialect = "postgresql"

            @staticmethod
            def query(sql, params=None):
                names = (params or {}).get("names")
                sql = sql.replace(":names", "%s")
                return [dict(zip(("table_name", "enabled", "forced"), r))
                        for r in owner.execute(sql, (names,)).fetchall()]

            @staticmethod
            def query_one(sql, params=None):
                row = owner.execute(sql).fetchone()
                return dict(zip(("role", "is_superuser", "bypasses"), row)) \
                    if row else None

        out = RowLevelSecurity(_Db()).in_force()
        assert out["connecting_role_is_exempt"] is True
        assert "exempt from row-level security entirely" in out["detail"]
        assert out["forced"] == len(SCOPED_TABLES)
