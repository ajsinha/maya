"""
Typed configuration (§22.2, §24.2): the declared schema is the only place a
default lives, an undeclared key in a configuration file stops startup, and a
value of the wrong type or out of range stops it too.

The last test here is the one that keeps the schema honest as the code grows: it
walks every ``settings.get/int/bool(key, default)`` call in the tree and fails
if the key is not declared, or if the call site's default differs from the
schema's. Without it "no silent config defaults" is a sentence in a
specification rather than a property of the code.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from maya.config import Settings, load_settings, schema
from maya.core.errors import ConfigurationError
from maya.core.properties_configurator import PropertiesConfigurator

ROOT = Path(__file__).resolve().parents[1]
TRACKED = ROOT / "config" / "application.yaml"
TOP_LEVELS = {s.key.split(".")[0] for s in schema.SETTINGS}
ACCESSORS = {"get", "int", "bool", "get_int", "get_bool", "require"}
RECEIVERS = {"settings", "props", "s", "cfg"}


def _settings(tmp_path, body: str, argv: list[str] | None = None) -> Settings:
    """Settings over a written configuration file, with nothing else in the layers."""
    import os
    import sys

    path = tmp_path / "application.yaml"
    path.write_text(body, encoding="utf-8")
    old_argv, old_home = sys.argv, os.environ.get("MAYA_HOME")
    sys.argv = ["pytest"] + (argv or [])
    os.environ["MAYA_HOME"] = str(tmp_path / "home")
    try:
        return load_settings(path, fresh=True)
    finally:
        sys.argv = old_argv
        PropertiesConfigurator.reset_instance()
        if old_home is not None:
            os.environ["MAYA_HOME"] = old_home


MINIMAL = """
app:
  environment: dev
db:
  dialect: sqlite
  sqlite:
    path: "${storage.root}/maya.db"
storage:
  root: "${MAYA_HOME:data}"
auth:
  mode: db
"""


def test_a_minimal_file_is_enough_and_every_default_comes_from_the_schema(tmp_path):
    s = _settings(tmp_path, MINIMAL)
    assert s.environment == "dev" and s.dialect == "sqlite" and s.auth_mode == "db"
    # nothing below is in the file: the values are the schema's, not a call site's
    assert s.int("jobs.workers", 99) == 2
    assert s.int("auth.lockout.attempts", 99) == 5
    assert s.bool("workflow.allow_self_approval", True) is False
    assert s.get("lake.backend", "native") == "auto"
    assert s.get("sandbox.min_tier", "minimal") == "strong"


def test_an_undeclared_key_in_a_file_refuses_startup_and_names_the_nearest(tmp_path):
    with pytest.raises(ConfigurationError) as exc:
        _settings(tmp_path, MINIMAL + "\ndb:\n  dialct: postgresql\n")
    assert "db.dialct" in exc.value.message
    assert "did you mean 'db.dialect'" in exc.value.message
    assert "configuration schema" in exc.value.message


def test_an_undeclared_command_line_override_is_reported_not_refused(tmp_path):
    """The argument list belongs to whatever launched the process: ``pytest --cov=maya``
    reaches sys.argv exactly as ``--db.dialect=`` does, so MAYA reports rather than dies."""
    s = _settings(tmp_path, MINIMAL, ["--cov=maya", "--jobs.workers=3"])
    assert s.unknown_overrides == ["cov"]
    assert s.int("jobs.workers", 2) == 3


def test_a_value_of_the_wrong_type_or_out_of_range_refuses_startup(tmp_path):
    for body, needle in (
        ("\nserver:\n  port: not-a-number\n", "a whole number"),
        ("\nserver:\n  port: 99999\n", "at most 65535"),
        ("\nlogging:\n  format: xml\n", "one of text, json"),
        ("\ndb:\n  echo: maybe\n", "a boolean"),
        ("\njobs:\n  workers: -1\n", "at least 0"),
    ):
        with pytest.raises(ConfigurationError, match=needle):
            _settings(tmp_path, MINIMAL + body)


def test_a_required_setting_with_no_value_refuses_startup_naming_it(tmp_path):
    with pytest.raises(ConfigurationError) as exc:
        _settings(tmp_path, MINIMAL.replace("  mode: db", "  mode: ''"))
    assert "auth.mode" in exc.value.message
    assert set(schema.required_keys()) == {
        "app.environment",
        "db.dialect",
        "auth.mode",
        "storage.root",
    }


def test_the_tracked_file_declares_only_known_keys_and_carries_no_undeclared_default():
    """Every key in the file MAYA ships is declared, and the declaration is documented."""
    import os
    import sys

    old = sys.argv
    sys.argv = ["pytest"]
    os.environ.setdefault("MAYA_HOME", "data")
    try:
        PropertiesConfigurator.reset_instance()
        props = PropertiesConfigurator([str(TRACKED)])
        keys = list(props.get_all_properties())
    finally:
        sys.argv = old
        PropertiesConfigurator.reset_instance()
    assert schema.unknown_keys(keys) == []
    assert all(s.description.strip().endswith((".", ")")) for s in schema.SETTINGS)
    assert all(s.kind in schema.KINDS for s in schema.SETTINGS)


def test_the_effective_configuration_names_every_declared_setting_and_its_source(tmp_path):
    s = _settings(tmp_path, MINIMAL)
    rows = {r["key"]: r for r in s.effective()}
    assert rows["db.dialect"]["source"] == "file"
    assert rows["jobs.workers"]["source"] == "default" and rows["jobs.workers"]["value"] == "2"
    assert rows["db.dialect"]["description"].startswith("sqlite or postgresql")
    assert all(r["kind"] != "undeclared" for r in s.effective())


def _accessor_calls() -> list[tuple[str, int, str, str, ast.expr | None]]:
    """Every ``<settings-ish>.<accessor>("dotted.key"[, default])`` in the tree."""
    found = []
    files = [ROOT / "run_maya_web.py"]
    for pkg in ("maya", "maya_delta", "tools"):
        # a gate test's temporary ``_planted*`` file may appear and vanish mid-scan
        files += sorted(p for p in (ROOT / pkg).rglob("*.py") if not p.name.startswith("_planted"))
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ACCESSORS or not node.args:
                continue
            key = node.args[0]
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            if key.value.split(".")[0] not in TOP_LEVELS or "." not in key.value:
                continue
            if not _is_settings(node.func.value):
                continue
            default = node.args[1] if len(node.args) > 1 else None
            rel = str(path.relative_to(ROOT))
            found.append((rel, node.lineno, node.func.attr, key.value, default))
    return found


def _is_settings(expr: ast.expr) -> bool:
    if isinstance(expr, ast.Name):
        return expr.id in RECEIVERS
    if isinstance(expr, ast.Attribute):
        return expr.attr in RECEIVERS
    return False


def test_no_call_site_invents_a_default_the_schema_does_not_declare():
    """§22.2 "no silent config defaults". A key read by code must be declared, and the
    default written at the call site must be the declared one — otherwise two places
    disagree about what MAYA does when the setting is absent, and only one of them is
    documented on the configuration page."""
    calls = _accessor_calls()
    assert len(calls) > 40, "the scanner found almost nothing; it has stopped working"
    undeclared, drifted = [], []
    for rel, line, accessor, key, default in calls:
        setting = schema.find(key)
        if setting is None:
            undeclared.append(f"{rel}:{line} reads undeclared '{key}'")
            continue
        if default is None or not isinstance(default, ast.Constant):
            continue
        written, declared = default.value, setting.default
        if isinstance(written, bool):
            same = declared is not None and (declared.strip().lower() in ("1", "true")) == written
        elif isinstance(written, (int, float)):
            same = declared is not None and float(declared) == float(written)
        else:
            same = str(written) == str(declared)
        if not same:
            drifted.append(
                f"{rel}:{line} '{key}' defaults to {written!r}, schema says {declared!r}"
            )
    assert undeclared == [], "\n".join(undeclared)
    assert drifted == [], "\n".join(drifted)
