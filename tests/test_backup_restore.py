"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Backup and restore, and the question neither `cp -r` nor `pg_basebackup` answers.

`docs/10 §2.3` files backup and restore under *the operating* — things that
belong to whoever runs the platform. That is right about **storage** and wrong
about **verification**. A filesystem snapshot copies bytes correctly and cannot
tell you the thing a model risk function needs to know:

> Did the evidence chain survive, and is it the one we backed up?

Two questions. A chain that verifies against *itself* at a different head is a
restore of a different backup, or of a database somebody wrote to in between —
and nothing about the filesystem would say so.

**These tools caught their own worst bug on their first round trip**, which is
the argument for them in one line. The emptiness probe opened a connection,
which created the target database and its write-ahead log; replacing `maya.db`
underneath that handle and reading through a new one produced a chain at **seq
0** — every byte correct, the digest matching, and the audit trail apparently
empty. A stale WAL replayed over a restored database is the quietest way there
is to lose a chain, and a restore reporting success while doing it is exactly
what this file exists to stop.
"""
from __future__ import annotations

import pathlib
import sqlite3

import pytest

from tools.ops import backup, restore
from tools.ops.common import read_manifest

CONFIG = """\
app: {{name: MAYA, version: "0.1.0", tagline: t, slogan: s, principle: p}}
server: {{host: 127.0.0.1, port: 5199}}
database: {{url: "sqlite:///{root}/data/sqlite/maya.db"}}
data: {{dir: "{root}/data", artifacts: "{root}/data/artifacts",
       attachments: "{root}/data/attachments", worm: "{root}/data/worm",
       delta: {{dir: "{root}/data/delta", features: "{root}/data/delta/features",
               snapshots: "{root}/data/delta/snapshots",
               telemetry: "{root}/data/delta/telemetry",
               monitoring: "{root}/data/delta/monitoring"}}}}
risk:
  exposure_bands: {{negligible: 0, low: 1000000, moderate: 50000000,
                   material: 500000000, critical: 5000000000}}
  purpose_ranks: {{commercial: 1, regulatory_capital: 4}}
  review_months: {{1: 12, 2: 18, 3: 24, 4: 36}}
warrants: {{jitter_pct: 0, signing_key: test-secret,
         ttl_seconds: {{1: 3600, 2: 3600, 3: 3600, 4: 3600}},
         grace_seconds: {{1: 900, 2: 900, 3: 900, 4: 900}}}}
execution: {{captive: {{enabled: false}}}}
logging: {{level: ERROR}}
"""


@pytest.fixture
def instance(tmp_path):
    """A real instance with a real chain, built through the real app."""
    from fastapi.testclient import TestClient

    from core.config import PropertiesConfigurator
    root = tmp_path / "inst"
    root.mkdir()
    config = root / "application.yaml"
    config.write_text(CONFIG.format(root=root), encoding="utf-8")
    PropertiesConfigurator.reset()
    from run_maya_web import create_app
    app = create_app(PropertiesConfigurator(str(config), reload_interval=0))
    client = TestClient(app)
    client.__enter__()
    client.auth = ("admin", "maya-admin-dev")
    client.post("/api/v1/models", json={
        "urn": "maya://model/bk.one", "name": "BK", "model_class": "c",
        "domain": "credit", "owner": "person/j.okafor",
        "legal_entity": "LE-1", "purpose": "p"})
    head = app.state.ctx["evidence"].head()
    client.__exit__(None, None, None)
    # The app holds the database open; a restore into this same instance needs
    # it let go, and leaving it is how a fixture produces "database is locked"
    # in a test about something else entirely.
    app.state.ctx["db"].engine.dispose()
    return {"config": str(config), "root": root, "head": head}


@pytest.fixture
def elsewhere(tmp_path):
    root = tmp_path / "restored"
    root.mkdir()
    config = root / "application.yaml"
    config.write_text(CONFIG.format(root=root), encoding="utf-8")
    return str(config)


class TestARoundTrip:
    def test_the_chain_comes_back_at_the_head_it_left_at(self, instance,
                                                         elsewhere, tmp_path):
        backup.run(instance["config"], str(tmp_path / "copy"))
        out = restore.run(str(tmp_path / "copy"), elsewhere)
        assert out["chain"]["verifies"]
        assert out["chain"]["head_agrees"]
        assert out["chain"]["seq"] == instance["head"][0]
        assert "the audit trail is the one that was backed up" in \
            out["detail"].lower()

    def test_a_stale_write_ahead_log_cannot_empty_the_chain(self, instance,
                                                            elsewhere,
                                                            tmp_path):
        """The bug these tools found in themselves. Every byte correct, the
        digest matching, and the chain at seq 0."""
        backup.run(instance["config"], str(tmp_path / "copy"))
        out = restore.run(str(tmp_path / "copy"), elsewhere)
        assert out["chain"]["seq"] > 0, "the restored chain is empty"
        assert out["database_digest_matches"]

    def test_every_store_digest_is_checked_not_just_the_database(
            self, instance, elsewhere, tmp_path):
        backup.run(instance["config"], str(tmp_path / "copy"))
        out = restore.run(str(tmp_path / "copy"), elsewhere)
        present = [s for s in out["stores"].values() if s.get("present")]
        assert present and all(s["matches"] for s in present)


class TestTheManifestIsTheLink:
    def test_it_records_the_head_and_that_it_verified(self, instance,
                                                      tmp_path):
        backup.run(instance["config"], str(tmp_path / "copy"))
        held = read_manifest(tmp_path / "copy")
        assert held["chain"]["seq"] == instance["head"][0]
        assert held["chain"]["chain_hash"] == instance["head"][1]
        assert held["chain"]["verifies"] is True

    def test_it_says_what_it_does_not_cover(self, instance, tmp_path):
        """A backup is read by somebody who did not take it, and a list of what
        it holds is not a list of what an instance needs."""
        backup.run(instance["config"], str(tmp_path / "copy"))
        blob = " ".join(read_manifest(tmp_path / "copy")["does_not_cover"])
        for absent in ("configuration file", "signing key", "encryption"):
            assert absent in blob

    def test_a_directory_without_one_is_not_a_backup(self, tmp_path):
        (tmp_path / "not-a-backup").mkdir()
        with pytest.raises(SystemExit, match="not a MAYA backup"):
            restore.run(str(tmp_path / "not-a-backup"), "unused")

    def test_an_absent_store_is_recorded_rather_than_skipped(self, instance,
                                                             tmp_path):
        backup.run(instance["config"], str(tmp_path / "copy"))
        stores = read_manifest(tmp_path / "copy")["stores"]
        assert "attachments" in stores
        assert stores["attachments"]["present"] is False


class TestWhatItRefuses:
    def test_a_chain_that_does_not_verify_refuses_the_backup(self, instance,
                                                              tmp_path):
        _tamper(instance["root"])
        with pytest.raises(SystemExit) as refusal:
            backup.run(instance["config"], str(tmp_path / "copy"))
        assert "does not verify" in str(refusal.value)
        assert "investigation starts on the wrong day" in str(refusal.value)

    def test_the_refusal_names_where_it_broke(self, instance, tmp_path):
        """A refusal nobody can act on is most of the way to no refusal — the
        first version printed a blank where the reason belonged, because it
        read a key the verifier does not emit."""
        _tamper(instance["root"])
        with pytest.raises(SystemExit) as refusal:
            backup.run(instance["config"], str(tmp_path / "copy"))
        assert "broken at seq" in str(refusal.value)
        assert "content_hash mismatch" in str(refusal.value)

    def test_a_forensic_copy_is_allowed_and_says_so(self, instance, tmp_path):
        """A broken chain is sometimes exactly what you need to preserve."""
        _tamper(instance["root"])
        out = backup.run(instance["config"], str(tmp_path / "copy"),
                         even_if_broken=True)
        assert out["chain"]["verifies"] is False
        assert "content_hash mismatch" in out["chain_reason"]

    def test_it_will_not_write_into_a_directory_with_anything_in_it(
            self, instance, tmp_path):
        (tmp_path / "copy").mkdir()
        (tmp_path / "copy" / "something").write_text("x")
        with pytest.raises(SystemExit, match="not empty"):
            backup.run(instance["config"], str(tmp_path / "copy"))

    def test_it_will_not_restore_over_a_chain(self, instance, tmp_path):
        """Two chains do not interleave, so there is no merge and the act is
        irreversible."""
        backup.run(instance["config"], str(tmp_path / "copy"))
        with pytest.raises(SystemExit) as refusal:
            restore.run(str(tmp_path / "copy"), instance["config"])
        assert "do not interleave" in str(refusal.value)

    def test_force_is_the_only_way_past_that(self, instance, tmp_path):
        backup.run(instance["config"], str(tmp_path / "copy"))
        out = restore.run(str(tmp_path / "copy"), instance["config"],
                          force=True)
        assert out["chain"]["head_agrees"]


class TestItDoesNotPretendToDoPostgres:
    def test_backup_refuses_and_names_the_command(self, tmp_path):
        config = tmp_path / "pg.yaml"
        config.write_text(
            CONFIG.format(root=tmp_path).replace(
                f'sqlite:///{tmp_path}/data/sqlite/maya.db',
                # No credentials: the refusal is about the DIALECT, and a URL carrying
                # a user and password would trip the secret scanner for nothing.
                "postgresql://localhost:1/nothing"), encoding="utf-8")
        with pytest.raises(SystemExit) as refusal:
            backup.run(str(config), str(tmp_path / "copy"))
        message = str(refusal.value)
        assert "pg_dump" in message and "pg_basebackup" in message
        assert "better than anything here" in message


def _tamper(root: pathlib.Path) -> None:
    """Break the chain the way somebody with the database would.

    The append-only trigger is dropped first, for the reason
    `tests/conftest.py::without_append_only` gives: it is defence in depth, not
    the control, and a row can arrive mutated by a path it does not cover.
    """
    conn = sqlite3.connect(root / "data" / "sqlite" / "maya.db")
    conn.execute("DROP TRIGGER IF EXISTS append_only_evidence_node_update")
    conn.execute("UPDATE evidence_node SET recorded_by = 'forged' WHERE seq = 2")
    conn.commit()
    conn.close()


class TestEveryRemediationNamesSomethingThatExists:
    """A refusal that tells you to run a command nobody can run.

    Both of these tools sent a PostgreSQL operator to
    `python -m tools.ops.verify`, which has never existed in this tree. The
    remediation is the third of the three parts a MAYA refusal carries, and one
    naming a phantom is worse than none: it costs the reader the time to find
    out, and it reads as though somebody checked.
    """

    OPS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ops"

    def test_no_tools_module_is_named_that_is_not_importable(self):
        import importlib.util
        import re
        root = self.OPS.parents[1]
        named = set()
        for source in sorted(root.glob("tools/**/*.py")):
            named |= set(re.findall(r"python -m ([a-z_][a-z0-9_.]*)",
                                    source.read_text(encoding="utf-8")))
        phantom = sorted(m for m in named
                         if importlib.util.find_spec(m) is None)
        assert not phantom, (
            "these refusals name a module nothing can run:\n    "
            + "\n    ".join(phantom))

    def test_the_postgres_refusals_still_say_what_to_do(self, instance, tmp_path,
                                                        monkeypatch):
        """Removing the phantom must not remove the remediation with it."""
        for source in ("backup", "restore"):
            body = (self.OPS / f"{source}.py").read_text(encoding="utf-8")
            assert "pg_dump" in body or "pg_restore" in body
            assert "chain" in body
