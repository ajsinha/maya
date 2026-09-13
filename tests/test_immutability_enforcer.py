"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Immutability with an enforcer behind it.

`db/schema/tables.py` carried the sentence *"Versions are immutable. There is no
UPDATE path other than status"* — written where a reader expects a constraint
and enforced by nothing. `Repository.set()` is generic, `VersionRepository`
overrode nothing, and there were **zero** triggers and **zero** foreign keys in
either dialect across ninety-one tables. Adversarial review `§4.5` stated the
attack in one line: *I call `versions.set({"manifest_digest": ...}, id=...)`.
Nothing stops me.*

Something stops it now, and these tests are the proof rather than a second
comment. They also pin the shape of the refusal, because finding **C-3** was
raised against an enforcement mechanism that *silently discarded* the write and
returned success — design rule **E8**, silence is never an acceptable
enforcement mechanism for an integrity control.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from db.schema.immutable import APPEND_ONLY, IMMUTABLE_COLUMNS

REFUSED = (IntegrityError, OperationalError)


class TestAnApprovedVersionCannotBeRewritten:
    def test_the_attack_in_the_finding_is_refused(self, db, a_version):
        """§4.5 verbatim: `versions.set({"manifest_digest": ...})`."""
        with pytest.raises(REFUSED) as refusal:
            db.update("model_version", "id = :i", {"i": a_version},
                      {"manifest_digest": "sha256:" + "c" * 64})
        assert "manifest_digest is immutable" in str(refusal.value)

    def test_it_refuses_loudly_rather_than_discarding(self, db, a_version):
        """C-3's whole point. A rewrite that returned success and changed
        nothing would be the defect that finding was raised against."""
        with pytest.raises(REFUSED):
            db.update("model_version", "id = :i", {"i": a_version},
                      {"created_by": "somebody else"})
        held = db.query_one("SELECT created_by FROM model_version WHERE id = :i",
                            {"i": a_version})
        assert held["created_by"] == "t"

    def test_the_refusal_names_the_column_and_what_to_do(self, db, a_version):
        with pytest.raises(REFUSED) as refusal:
            db.update("model_version", "id = :i", {"i": a_version},
                      {"semver": "9.9.9"})
        message = str(refusal.value)
        assert "model_version.semver" in message
        assert "Create a new version" in message

    @pytest.mark.parametrize("column", IMMUTABLE_COLUMNS["model_version"])
    def test_every_declared_column_is_actually_guarded(self, db, a_version,
                                                       column):
        """Declared and rendered is not enforced. Each one is attacked."""
        with pytest.raises(REFUSED):
            db.update("model_version", "id = :i", {"i": a_version},
                      {column: "sha256:" + "d" * 64})

    def test_status_still_moves(self, db, a_version):
        """The one field the lifecycle changes, and the reason the guard is
        per-column rather than per-table."""
        assert db.update("model_version", "id = :i", {"i": a_version},
                         {"status": "approved"}) == 1
        assert "status" not in IMMUTABLE_COLUMNS["model_version"]


class TestTheEvidenceChainIsAppendOnly:
    def test_a_node_cannot_be_updated(self, db, evidence, a_model):
        evidence.append("thing_happened", "model", a_model["id"], {"a": 1})
        node = db.query_one("SELECT id FROM evidence_node LIMIT 1")
        with pytest.raises(REFUSED) as refusal:
            db.update("evidence_node", "id = :i", {"i": node["id"]},
                      {"recorded_by": "somebody else"})
        assert "append-only" in str(refusal.value)

    def test_a_node_cannot_be_deleted(self, db, evidence, a_model):
        """Detection is a report after the fact; C-4 asked for the other
        half."""
        evidence.append("thing_happened", "model", a_model["id"], {"a": 1})
        node = db.query_one("SELECT id FROM evidence_node LIMIT 1")
        with pytest.raises(REFUSED):
            db.execute("DELETE FROM evidence_node WHERE id = :i",
                       {"i": node["id"]})

    def test_appending_still_works(self, db, evidence, a_model):
        evidence.append("one", "model", a_model["id"], {})
        evidence.append("two", "model", a_model["id"], {})
        assert db.query_one("SELECT COUNT(*) AS n FROM evidence_node")["n"] >= 2

    def test_the_chain_still_verifies(self, db, evidence, a_model):
        evidence.append("one", "model", a_model["id"], {})
        assert evidence.verify_chain()["valid"]


class TestTheEnforcementIsAppliedAndNotOnlyRendered:
    def test_applying_the_schema_creates_the_triggers(self, db):
        """Rendered into the .sql files and never executed would be the exact
        defect this closes: `create_all` builds from the typed metadata and
        never reads those files."""
        rows = db.query(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'")
        names = {r["name"] for r in rows}
        assert any(n.startswith("immutable_model_version") for n in names)
        assert any(n.startswith("append_only_evidence_node") for n in names)

    def test_it_is_idempotent(self, db):
        before = db.query_one(
            "SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'trigger'")
        db._apply_enforcement()
        after = db.query_one(
            "SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'trigger'")
        assert before["n"] == after["n"]

    def test_both_dialects_are_generated(self):
        from db.schema.immutable import postgres_statements, sqlite_statements
        assert sqlite_statements() and postgres_statements()
        assert all("RAISE" in s for s in sqlite_statements())
        assert all("RAISE EXCEPTION" in s or "CREATE TRIGGER" in s
                   for s in postgres_statements())

    def test_the_append_only_list_is_the_chain(self):
        assert APPEND_ONLY == ("evidence_node",)


@pytest.fixture
def a_version(db):
    db.insert("model", {
        "id": "m1", "urn": "maya://model/x", "name": "n", "description": "",
        "model_class": "c", "domain": "d", "owner": "o", "legal_entity": "LE",
        "purpose": "p", "origin": "internal", "status": "draft",
        "designations": "[]", "attributes": "{}", "created_at": 1.0,
        "created_by": "t"})
    db.insert("model_version", {
        "id": "v1", "model_id": "m1", "semver": "1.0.0", "manifest": "{}",
        "manifest_digest": "sha256:" + "a" * 64, "trainability_class": "T2",
        "parameter_kind": "k", "fit_procedure": "estimate", "deterministic": 1,
        "input_schema": "[]", "parameter_schema": "[]", "output_schema": "[]",
        "artifact_digest": "sha256:" + "b" * 64, "status": "draft",
        "created_at": 1.0, "created_by": "t"})
    return "v1"


class TestANodeFlaggedForPersonalDataMustBeEmpty:
    """H-3, and the difference between a convention and a constraint.

    The review's disposition was *satisfied in the law, not in the mechanism*,
    and that was exact. Law L-18 discards the payload of a node flagged as
    containing personal data — not a pointer, not an encrypted blob, nothing to
    erase and nothing to leak — and the discarding happened in
    `EvidenceEngine._try` and **nowhere else**.

    So any other writer could set the flag and keep the content: a migration, a
    repair script, a test fixture, a future call site. The chain would hash it,
    verify it, and hold personal data in a table that is append-only — which is
    the one place a later erasure request could never be honoured.
    """

    def _node(self, db, flag, payload):
        db.execute(
            "INSERT INTO evidence_node (id, seq, kind, subject_type, "
            "subject_id, payload, parents, contains_personal_data, "
            "content_hash, prev_hash, chain_hash, trust, recorded_at, "
            "recorded_by) VALUES ('n-1', 1, 'k', 'model', 'm-1', :p, '[]', "
            ":f, 'h', '', 'c', 'asserted', 0, 'ana')",
            {"p": payload, "f": flag})

    def test_the_flag_with_content_is_refused(self, db):
        import json
        with pytest.raises(Exception) as refused:
            self._node(db, 1, json.dumps({"name": "Jane Doe",
                                          "nin": "AB123456C"}))
        assert "EMPTY payload" in str(refused.value)

    def test_the_refusal_says_why_a_pointer_would_not_do(self, db):
        with pytest.raises(Exception) as refused:
            self._node(db, 1, '{"x": 1}')
        assert "not stored behind a pointer" in str(refused.value)

    def test_the_flag_with_an_empty_payload_is_accepted(self, db):
        """The correct case, which the append path already produces. A guard
        that refused this would refuse every node the platform writes."""
        self._node(db, 1, "{}")
        assert db.query_one("SELECT id FROM evidence_node WHERE id = 'n-1'")

    def test_an_unflagged_node_may_carry_its_payload(self, db):
        """Most nodes do. The rule is about the flag, not about payloads."""
        self._node(db, 0, '{"urn": "urn:maya:model:pd", "tier": 1}')
        assert db.query_one("SELECT id FROM evidence_node WHERE id = 'n-1'")

    def test_both_dialects_carry_the_rule(self):
        """A guard on SQLite and not on PostgreSQL is a guard that vanishes in
        production, which is where it matters."""
        from db.schema.immutable import (postgres_statements,
                                         sqlite_statements)
        assert any("empty_when_flagged_evidence_node" in s
                   for s in sqlite_statements())
        assert any("maya_empty_when_flagged_evidence_node" in s
                   for s in postgres_statements())
