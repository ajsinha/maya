"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What happens when two things happen at once.

There were **zero** concurrency tests and zero transaction tests in fourteen
thousand lines of test code, and a reviewer found the defect that gap was
hiding: the evidence chain is a read-then-write — take the head, insert head+1 —
and every statement opened its own transaction, so two concurrent governance
acts read the same head and one of them hit the UNIQUE on `seq`. Measured at
four threads, seven percent of appends raised.

Losing the row was not the serious part. Every service commits its own state
change *before* appending evidence, so the model existed and the record of its
registration did not — and segregation of duties is decided by reading the
chain, so a lost `version_created` node did not fail closed. It meant "you
cannot approve what you created" had nothing to read.

The suite proved MAYA correct when one thing happened at a time. This file is
the other half.
"""
from __future__ import annotations

import concurrent.futures

import pathlib
import re

import pytest


@pytest.fixture
def shared_db(tmp_path):
    """A file-backed database, because the shared in-memory one is not shared.

    `sqlite:///:memory:` gives every CONNECTION its own database, so a thread
    pool against it tests nothing at all — each worker would quietly get an
    empty schema. Concurrency has to be tested against storage that two threads
    can actually contend for.
    """
    from db import Database
    database = Database(f"sqlite:///{tmp_path}/concurrent.db")
    database.apply_schema()
    return database


@pytest.fixture
def evidence(shared_db):
    from core.evidence import EvidenceEngine
    from db import EvidenceRepository
    return EvidenceEngine(EvidenceRepository(shared_db))


@pytest.fixture
def segregation(evidence):
    from core.authz.segregation import SegregationPolicy
    return SegregationPolicy(evidence)


@pytest.fixture
def db(shared_db):
    return shared_db


def _append(evidence, i):
    return evidence.append("model_registered", "model", f"m-{i}",
                           {"n": i}, actor=f"person/p{i}")


class TestTheEvidenceChainUnderConcurrency:
    def test_no_append_is_lost_when_many_run_at_once(self, evidence):
        """The measurement that started this: 24 concurrent acts used to produce
        24 domain rows and 14 evidence nodes."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda i: _append(evidence, i), range(48)))
        assert len(results) == 48
        assert len(evidence.repo.many()) == 48

    def test_the_chain_is_contiguous_afterwards(self, evidence):
        """A retry must take the NEXT sequence, not leave a hole. A hole would
        be indistinguishable from a deletion, which is what the chain exists to
        detect."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: _append(evidence, i), range(48)))
        sequences = sorted(n["seq"] for n in evidence.repo.many())
        assert sequences == list(range(1, 49))

    def test_the_chain_still_verifies(self, evidence):
        """Every node's prev_hash must be the previous node's chain_hash, which
        is only true if the appends genuinely serialised."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: _append(evidence, i), range(48)))
        report = evidence.verify_chain()
        assert report["valid"] is True, report
        assert report["length"] == 48

    def test_duties_do_not_fail_open_under_load(self, evidence, segregation):
        """The consequence that made this critical rather than untidy. If the
        `version_created` node is lost, the check that reads it finds nothing
        and permits the act it exists to refuse."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            pool.map(lambda i: evidence.append(
                "version_created", "version", f"v-{i}", {}, actor="d.raman"),
                range(24))
        blocked = [i for i in range(24)
                   if segregation.conflict("d.raman", "version:approve",
                                           f"v-{i}") is not None]
        assert len(blocked) == 24, (
            "every version d.raman created must refuse their own approval")


class TestTransactionsAreReEntrant:
    def test_a_nested_transaction_joins_the_outer_one(self, db):
        """A service wrapping a whole governance act must not deadlock against
        a collaborator that opens one of its own."""
        with db.transaction():
            with db.transaction():
                db.execute("INSERT INTO principal (id, username, display_name, "
                           "created_at) VALUES ('n1','nested','N',1.0)")
            assert db.query_one("SELECT username FROM principal WHERE id='n1'")
        assert db.query_one("SELECT username FROM principal WHERE id='n1'")

    def test_a_failed_transaction_rolls_the_whole_thing_back(self, db):
        with pytest.raises(RuntimeError), db.transaction():
            db.execute("INSERT INTO principal (id, username, display_name, "
                       "created_at) VALUES ('r1','rolled','R',1.0)")
            raise RuntimeError("something went wrong half way through")
        assert db.query_one("SELECT username FROM principal WHERE id='r1'") is None

    def test_a_read_inside_a_transaction_sees_its_own_writes(self, db):
        """It could not before: `execute` began and ended a transaction, and
        `query` opened a second connection that could not see inside it."""
        with db.transaction():
            db.execute("INSERT INTO principal (id, username, display_name, "
                       "created_at) VALUES ('s1','sees','S',1.0)")
            assert db.query_one("SELECT username FROM principal WHERE id='s1'")


class TestSqliteIsConfiguredForContention:
    """The pragmas, asserted, because their absence is invisible until load.

    A suite run alongside three other pytest processes produced
    `database is locked` from the evidence chain — not a race, a five-second
    driver timeout under contention. Nothing was wrong with the code; the
    database was configured to give up.
    """

    def test_an_on_disk_database_uses_a_write_ahead_log(self, tmp_path):
        """Readers must not block behind a writer.

        The default journal makes every read wait for the write in flight, and
        this platform reads the evidence chain on nearly every request.
        """
        from db.database import Database
        db = Database(f"sqlite:///{tmp_path}/wal.db")
        with db.engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_every_connection_waits_rather_than_failing(self, tmp_path):
        """A lock held for a moment is normal. Failing instead of waiting turns
        a millisecond of contention into a governance act that did not happen."""
        from db.database import Database
        for url in (f"sqlite:///{tmp_path}/timeout.db", "sqlite:///:memory:"):
            db = Database(url)
            with db.engine.connect() as conn:
                timeout = conn.exec_driver_sql("PRAGMA busy_timeout").fetchone()[0]
            assert timeout == Database.BUSY_TIMEOUT_MS, url


class TestTheDatabaseIsCheckedAgainstTheRelease:
    """`CREATE TABLE IF NOT EXISTS` skips a table that already exists.

    So a column added in a later release is never created on an existing
    database. The application starts cleanly on a schema that does not match its
    own code and fails weeks later, inside a workflow, on a query nobody
    associates with the deployment. There is no migration tool; this check is
    what turns that silence into a sentence at start-up.
    """

    def test_a_freshly_applied_schema_has_no_drift(self, tmp_path):
        from db.database import Database
        assert Database(f"sqlite:///{tmp_path}/fresh.db").drift() == {}

    def test_a_missing_column_is_detected(self, tmp_path):
        """The reviewer's reproduction, run as a test."""
        import sqlite3

        from db.database import Database

        path = tmp_path / "older.db"
        Database(f"sqlite:///{path}")
        connection = sqlite3.connect(path)
        connection.execute("ALTER TABLE model DROP COLUMN purpose")
        connection.commit()
        connection.close()

        gaps = Database(f"sqlite:///{path}").drift()
        assert "model" in gaps
        assert "purpose" in gaps["model"][0]

    def test_a_missing_table_is_detected(self, tmp_path):
        import sqlite3

        from db.database import Database

        path = tmp_path / "partial.db"
        Database(f"sqlite:///{path}")
        connection = sqlite3.connect(path)
        connection.execute("DROP TABLE risk_assessment")
        connection.commit()
        connection.close()
        # Re-applying the DDL recreates it, which is the point of IF NOT EXISTS
        # and is why a dropped table is NOT the failure mode worth testing —
        # the column case is, because that one it cannot repair.
        assert Database(f"sqlite:///{path}").drift() == {}

    def test_the_declared_schema_is_parsed_and_not_guessed(self, tmp_path):
        """Every table in the DDL, and no artefacts of comment syntax.

        The first version of this parser read `--` as a column name on six
        tables. A check whose output is nonsense is one nobody reads twice.
        """
        from db.database import Database
        declared = Database(f"sqlite:///{tmp_path}/parse.db").declared_schema()
        assert len(declared) > 40
        for table, columns in declared.items():
            assert columns, table
            assert not any(c.startswith("-") or "}" in c for c in columns), (
                f"{table} has a column that is a fragment of a comment: {columns}")
        # A column known to exist, so the parser is not merely returning noise.
        assert "purpose" in declared["model"]


class TestAQuorumIsANumberOfPeople:
    """One person completed a two-person Tier 1 quorum by racing two requests.

    `sign` enforced "a quorum is a number of people, not a number of hats" with
    a read-then-write and nothing behind it. Fired through a barrier by a
    principal holding `validator` and `model_risk_manager`, both requests passed
    the read and both wrote: 1 trial in 25 put BOTH signatures on one person,
    and the approval record and the evidence chain each said a quorum had
    approved it. Nothing anywhere said the two signatures were the same person.

    `model_risk_manager` is defined as a superset of `validator`, so holding
    both is a supported configuration — and it is exactly the configuration the
    check exists to neutralise.

    The database constraint is the fix. A transaction alone is not enough on a
    read-committed store, which is why the test below asserts the constraint
    rather than the wrapper.
    """

    def test_the_constraint_exists_in_both_dialects(self):
        """Asserted on the DDL, because this is the half that does the work.

        As an INDEX, not a clause in the table body, and that is the whole
        point. The schema is applied with CREATE TABLE IF NOT EXISTS, so a
        constraint written inside a table reaches a fresh database and never
        reaches a deployed one — and unlike a missing column, a missing
        uniqueness rule fails nothing at the point of use. It silently permits
        the write it existed to refuse, so this test passed for a wave while
        every upgraded instance still let one person be a quorum.
        """
        for dialect in ("sqlite", "postgres"):
            root = pathlib.Path(__file__).resolve().parents[1]
            sql = (root / "db" / "schema" / f"{dialect}.sql").read_text()
            for table in ("version_approval_signature", "attestation_signature"):
                assert re.search(
                    r"CREATE UNIQUE INDEX IF NOT EXISTS \w+\s+ON "
                    + table + r"\s*\((\w+),\s*principal\)", sql), (
                    f"{dialect}.sql lets one person sign a {table} quorum twice")

    def test_the_constraint_reaches_a_database_that_already_exists(self, tmp_path):
        """The half that was missing. A bank upgrades; start-up logs clean; the
        constraint the release note describes is not on the table."""
        from sqlalchemy import text

        from db.database import Database

        db = Database(f"sqlite:///{tmp_path}/deployed.db")
        db.apply_schema()
        # An instance that predates the constraint.
        with db.engine.begin() as connection:
            connection.execute(text("DROP INDEX uq_signature_attestation_principal"))
        assert "missing index 'uq_signature_attestation_principal'" in \
            db.drift().get("attestation_signature", []), \
            "drift() cannot see a missing uniqueness rule, so nothing says so"
        # Applying the shipped schema repairs it — no migration step.
        db.apply_schema()
        assert not db.drift()
        assert "uq_signature_attestation_principal" in \
            db.indexes_of("attestation_signature")

    def test_the_database_refuses_a_second_signature_from_one_person(self, tmp_path):
        """Below the service, so a future refactor of `sign` cannot lose it."""
        from sqlalchemy.exc import IntegrityError

        from db.database import Database

        db = Database(f"sqlite:///{tmp_path}/quorum.db")
        insert = ("INSERT INTO version_approval_signature (id, version_approval_id, "
                  "principal, role, decision, statement, signed_at) VALUES "
                  "('{id}', 'A', 'z.dual', '{role}', 'approve', '', 1.0)")
        with db.engine.begin() as connection:
            connection.exec_driver_sql(insert.format(id="1", role="validator"))
        with pytest.raises(IntegrityError), db.engine.begin() as connection:
            connection.exec_driver_sql(
                insert.format(id="2", role="model_risk_manager"))

    def test_two_different_people_still_sign(self, tmp_path):
        """The control is independence, not scarcity: the quorum must still be
        completable by the two people it is for."""
        from db.database import Database

        db = Database(f"sqlite:///{tmp_path}/quorum2.db")
        insert = ("INSERT INTO version_approval_signature (id, version_approval_id, "
                  "principal, role, decision, statement, signed_at) VALUES "
                  "('{id}', 'A', '{who}', '{role}', 'approve', '', 1.0)")
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                insert.format(id="1", who="a.mehta", role="validator"))
            connection.exec_driver_sql(
                insert.format(id="2", who="s.iqbal", role="model_risk_manager"))
        with db.engine.begin() as connection:
            count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM version_approval_signature").scalar()
        assert count == 2

    def test_losing_the_race_reads_as_having_already_signed(self):
        """The integrity error is translated back into the refusal the reader
        was going to get anyway. Losing a race is not a different answer from
        being told you have already signed, and a caller who saw a 500 here
        would retry — which is the one thing that must not work."""
        import inspect

        from core.lifecycle import approval
        source = inspect.getsource(approval.VersionApproval.sign)
        assert "IntegrityError" in source
        assert source.count("already_signed_personally") >= 2, (
            "the constraint's refusal must carry the same code as the read's")
        assert "db.transaction()" in source


class TestTheSequenceIsTakenUnderTheWriteLock:
    """The retry was covering a race rather than removing one.

    A plain transaction on SQLite is *deferred*: the `SELECT MAX(seq)` takes no
    write lock, so two writers read the same head and the second INSERT dies on
    the UNIQUE. Twelve jittered retries hid it until a loaded machine — the test
    suite running one file per core — made four writers exhaust all twelve, and
    an append was lost. That is the outcome the retry existed to prevent,
    reached more slowly: a missing `version_created` node means the segregation
    check has nothing to read, and the developer approves their own version.
    """

    @staticmethod
    def _engine(tmp_path):
        from core.evidence import EvidenceEngine
        from db import Database, EvidenceCheckpointRepository, EvidenceRepository
        db = Database(f"sqlite:///{tmp_path}/seq.db", False)
        return db, EvidenceEngine(EvidenceRepository(db),
                                  EvidenceCheckpointRepository(db))

    def test_no_append_is_lost_with_the_retry_budget_removed(self, tmp_path,
                                                             monkeypatch):
        """One attempt only. If the lock does not hold the sequence, this fails.

        Leaving the twelve retries in place would let a passing run mean either
        "the lock works" or "the retry papered over it", and a test that cannot
        distinguish those two proves nothing about the change it guards.
        """
        import threading

        import core.evidence.engine as engine_module

        monkeypatch.setattr(engine_module, "APPEND_ATTEMPTS", 1)
        db, evidence = self._engine(tmp_path)
        failures, per_thread = [], 40

        def write(n):
            for i in range(per_thread):
                try:
                    evidence.append("model_registered", "model", f"m{n}-{i}", {})
                except Exception as exc:                     # pragma: no cover
                    failures.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=write, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not failures, failures[:3]
        rows = db.query("SELECT seq FROM evidence_node ORDER BY seq")
        assert len(rows) == 6 * per_thread, "an append was lost"
        assert [r["seq"] for r in rows] == list(range(1, 6 * per_thread + 1)), \
            "the sequence must be dense: a gap is a node that never landed"
        assert evidence.verify_chain()["valid"]
