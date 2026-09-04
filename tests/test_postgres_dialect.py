"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The second dialect, actually run.

`db/schema/postgres.sql` is not documentation. It is one of the two files that
ARE the schema, because there are no migrations here — and until now nothing had
ever executed it. Adversarial review found fourteen columns declared BOOLEAN
against a repository layer that coerces every boolean to `int`, which PostgreSQL
will not implicitly cast: every insert touching one of those tables would have
failed, including the query behind the blocking-findings gate. The dialect was
unusable and 1,780 passing tests could not see it, because every one of them ran
on SQLite.

**Skipped unless a database is reachable.** Set `MAYA_TEST_POSTGRES` to a URL,
or run the container the repository ships with:

    docker run -d --rm --name maya-pg -e POSTGRES_PASSWORD=maya \\
        -e POSTGRES_DB=maya -p 55432:5432 postgres:16-alpine
    MAYA_TEST_POSTGRES=postgresql+psycopg://postgres:maya@127.0.0.1:55432/maya \\
        .venv/bin/python -m pytest tests/test_postgres_dialect.py

Skipping is honest rather than convenient: a test that silently passes when it
did not run is the failure mode this file exists to end. It should run in CI.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest

URL = os.environ.get("MAYA_TEST_POSTGRES")
pytestmark = pytest.mark.skipif(
    not URL, reason="set MAYA_TEST_POSTGRES to a reachable PostgreSQL to run these")


@pytest.fixture
def pg():
    from db.database import Database
    database = Database(URL)
    database.apply_schema()
    return database


@pytest.fixture
def wired(pg):
    """The registry and finding register, on PostgreSQL rather than SQLite."""
    from core.evidence import EvidenceEngine
    from core.registry import ModelRegistry
    from core.validation import FindingRegister
    from db import (AliasHistoryRepository, AliasRepository, EvidenceRepository,
                    FindingRepository, ModelRepository, VersionRepository)

    evidence = EvidenceEngine(EvidenceRepository(pg))
    registry = ModelRegistry(ModelRepository(pg), VersionRepository(pg),
                             AliasRepository(pg), AliasHistoryRepository(pg),
                             evidence)
    findings = FindingRepository(pg)
    return {"db": pg, "evidence": evidence, "registry": registry,
            "findings_repo": findings,
            "findings": FindingRegister(findings, evidence)}


def _a_model(wired):
    urn = f"maya://model/pg.{uuid.uuid4().hex[:10]}"
    wired["registry"].register(urn, "PG", "credit.pd", "credit", "person/o",
                               "LE-1", "purpose", actor="person/o")
    return wired["registry"].get(urn)


def test_the_schema_applies_at_all(pg):
    """It had never been executed. This is the whole point of the file."""
    assert pg.dialect.startswith("postgres")


def test_a_model_can_be_registered(wired):
    assert _a_model(wired)["urn"].startswith("maya://model/pg.")


def test_the_blocking_findings_gate_runs(wired):
    """The query that could not have executed against a BOOLEAN column: it binds
    an integer against `blocking = :b`. Everything in the platform that refuses
    to serve a model which failed challenge goes through here."""
    model = _a_model(wired)
    wired["findings"].raise_finding(model["id"], "Critical", "leakage",
                                    "person/o", source="validation",
                                    actor="person/s.iqbal")
    blocking = wired["findings_repo"].open_for(model["id"], blocking=True)
    assert len(blocking) == 1


def test_a_truth_value_round_trips_as_a_bool(wired):
    """Stored as integer 0/1 in both dialects; a caller gets a bool either way,
    so nothing downstream has to know how one is persisted."""
    model = _a_model(wired)
    wired["findings"].raise_finding(model["id"], "Critical", "leakage",
                                    "person/o", source="validation",
                                    actor="person/s.iqbal")
    row = wired["findings_repo"].open_for(model["id"], blocking=True)[0]
    assert bool(row["blocking"]) is True


def test_the_evidence_chain_verifies_on_postgres(wired):
    model = _a_model(wired)
    wired["evidence"].append("tier_assigned", "model", model["id"], {"tier": 1},
                             actor="person/s.iqbal")
    report = wired["evidence"].verify_chain()
    assert report["valid"] is True and report["length"] >= 2


def test_a_tampered_payload_breaks_the_chain_on_postgres_too(wired):
    """The control has to hold on both dialects, not on the one that gets run."""
    from db import EvidenceRepository
    model = _a_model(wired)
    node = wired["evidence"].append("risk_assessed", "model", model["id"],
                                    {"tier": 3}, actor="person/s.iqbal")
    EvidenceRepository(wired["db"]).set({"payload": {"tier": 1}}, seq=node["seq"])
    assert wired["evidence"].verify_chain()["valid"] is False
