"""
Foundation: configuration (DishtaYantra's configurator, dialect switching,
no silent defaults), the generated schema files, the Type B seams (canonical
bytes, chunker locality), the KDF seam's recorded algorithm and rehash, the
crypto refusal, and the authorization function.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path

import pytest

from maya.core import canonical, kdf
from maya.core.backends import Backends
from maya.core.chunker import ChunkParams, boundaries
from maya.core.errors import CapabilityRefused, ConfigurationError
from maya.persistence import schema
from maya.security.authz import Principal, can, merge_capabilities
from maya.security.roles import MATRIX

ROOT = Path(__file__).resolve().parents[1]


# -- configuration -------------------------------------------------------------------
def _settings(tmp_path, *argv, text=None):
    from maya.config import load_settings
    cfg = tmp_path / "application.yaml"
    cfg.write_text(text or (ROOT / "config" / "application.yaml").read_text())
    sys.argv = ["x", *argv]
    return load_settings(cfg, fresh=True)


def test_dialect_switches_by_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("MAYA_HOME", str(tmp_path))
    s = _settings(tmp_path)
    assert s.dialect == "sqlite" and s.database_url().startswith("sqlite:///")
    s = _settings(tmp_path, "--db.dialect=postgresql")
    assert s.dialect == "postgresql"
    assert s.database_url().startswith("postgresql+psycopg://maya@localhost:5432/maya")
    assert s.props.get_source("db.dialect") == "commandline"


def test_local_overlay_wins_and_no_silent_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("MAYA_HOME", str(tmp_path))
    (tmp_path / "application.local.yaml").write_text("db:\n  dialect: postgresql\n")
    assert _settings(tmp_path).dialect == "postgresql"
    (tmp_path / "application.local.yaml").unlink()
    with pytest.raises(ConfigurationError, match="db.dialect"):
        _settings(tmp_path, "--db.dialect=oracle")
    with pytest.raises(ConfigurationError, match="SQLite"):
        _settings(tmp_path, "--app.environment=prod")


def test_tracked_config_carries_no_secret():
    sys.path.insert(0, str(ROOT / "tools" / "ci"))
    import no_secrets
    assert no_secrets.main() == 0


# -- schema ------------------------------------------------------------------------------
def test_shipped_schema_files_match_the_metadata():
    assert schema.drift() == {"sqlite": False, "postgresql": False}


def test_hand_edit_is_detected(tmp_path, monkeypatch):
    fake = tmp_path / "schema"
    fake.mkdir()
    for d in ("sqlite", "postgresql"):
        (fake / f"{d}.sql").write_text(schema.render(d) + "-- hand edit\n")
    monkeypatch.setattr(schema, "SCHEMA_DIR", fake)
    assert schema.drift() == {"sqlite": True, "postgresql": True}


def test_postgres_ddl_uses_native_types():
    ddl = schema.render("postgresql")
    assert "JSONB" in ddl and "UUID" in ddl and "TIMESTAMP WITH TIME ZONE" in ddl
    assert "maya_audit_append_only" in ddl
    assert "CREATE TRIGGER audit_events_no_update" in schema.render("sqlite")


# -- Type B seams ----------------------------------------------------------------------------
def test_canonical_bytes_are_fixed():
    """The pure encoder is the specification: these bytes are the fixture."""
    row = [1, 1.5, "a", None, dt.date(2026, 1, 2), True, [1.0, 2.0]]
    digest = hashlib.sha256(canonical.encode_row(row)).hexdigest()
    assert digest == "8982262821fa5adcf6e0fceac43a607a387e5839fd979e8196da282b2c64ca0e"
    assert canonical.encode_value(dt.date(2026, 1, 2)) == b"D\x00\x00O\xe7"   # day 20455
    assert canonical.encode_value(-0.0) == canonical.encode_value(0.0)
    assert canonical.encode_value(float("nan")) == canonical.encode_value(float("-nan"))


def test_chunker_is_content_defined():
    digests = [hashlib.sha256(str(i).encode()).digest() for i in range(5000)]
    params = ChunkParams(target=128, minimum=8, maximum=4096)
    before = boundaries(digests, params)
    inserted = digests[:2500] + [hashlib.sha256(b"new").digest()] + digests[2500:]
    after = boundaries(inserted, params)
    same_prefix = [b for b in before if b[1] <= 2400]
    assert after[:len(same_prefix)] == same_prefix, "an insert must not move earlier cuts"
    tail_before = [(s - 2500, e - 2500) for s, e in before if s >= 2700]
    tail_after = [(s - 2501, e - 2501) for s, e in after if s >= 2701]
    assert tail_before[-5:] == tail_after[-5:], "cuts after the insert re-synchronise"


# -- KDF and crypto seams ------------------------------------------------------------------------
def test_kdf_records_its_algorithm_and_rehashes_upward():
    Backends.resolve({"kdf": "scrypt"})
    try:
        stored = kdf.hash_password("Correct-horse-9")
        assert kdf.algorithm_of(stored) == "scrypt"
        assert kdf.verify_password("Correct-horse-9", stored)
        assert not kdf.verify_password("wrong", stored)
    finally:
        Backends.resolve({})
    assert kdf.verify_password("Correct-horse-9", stored), "old hashes verify after a change"
    assert kdf.needs_rehash(stored), "a login upgrades to the strongest available"


def test_crypto_refuses_rather_than_downgrading(tmp_path):
    Backends.resolve({})
    Backends.choices()["crypto"].available = False
    try:
        from maya.core.crypto import Signer
        with pytest.raises(CapabilityRefused, match="cryptography"):
            Signer(tmp_path)
    finally:
        Backends.resolve({})


# -- authorization ---------------------------------------------------------------------------------
def _p(*roles, uid="u1"):
    return Principal(uid, uid, list(roles), merge_capabilities([MATRIX[r] for r in roles]))


NS = {"name": "eq", "default_visibility": "namespace_read"}


@pytest.mark.parametrize("role", sorted(MATRIX))
@pytest.mark.parametrize("action", ["read", "update", "approve", "pin", "grant"])
def test_role_ceiling_is_never_exceeded(role, action):
    """Even an 'admin'-level grant cannot give what the role lacks (SC-7)."""
    p = _p(role)
    grant = [{"principal_type": "user", "principal_id": "u1", "level": "admin"}]
    obj = {"type": "feature", "id": "f1", "owner_id": "someone"}
    letter = {"read": "R", "update": "U", "approve": "A", "pin": "P", "grant": "G"}[action]
    decision = can(p, action, obj, grant, NS)
    if letter not in MATRIX[role].get("feature", ""):
        assert not decision, f"{role} {action} allowed without capability"
    else:
        assert decision


def test_acl_resolution_order():
    p = _p("feature_designer")
    obj = {"type": "feature", "id": "f1", "owner_id": "other"}
    assert can(p, "read", obj, [], NS)
    assert not can(p, "update", obj, [], NS), "namespace default is read-only"
    assert not can(p, "read", obj, [], {"default_visibility": "private"})
    deny = [{"principal_type": "user", "principal_id": "u1", "level": "read", "deny": True},
            {"principal_type": "everyone", "principal_id": "*", "level": "own"}]
    assert not can(p, "read", obj, deny, NS), "deny wins"
    rw = [{"principal_type": "role", "principal_id": "feature_designer", "level": "read_write"}]
    assert can(p, "update", obj, rw, NS)
    assert can(p, "update", {**obj, "owner_id": "u1"}, [], NS), "owner edits"
    assert not can(p, "update", {**obj, "owner_id": "u1", "state": "sealed"}, [], NS)
    assert not can(_p("admin"), "update", {**obj, "state": "sealed"}, [], NS)
    scratch = {"name": "scratch.x", "is_scratch": True, "owner_id": "x",
               "default_visibility": "private"}
    assert not can(p, "read", obj, [], scratch)
    key = _p("feature_designer")
    key.principal_type, key.key_actions = "api_key", ["read"]
    assert not can(key, "update", {**obj, "owner_id": "u1"}, [], NS)

