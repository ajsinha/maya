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
        with pytest.raises(RuntimeError):
            with db.transaction():
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
