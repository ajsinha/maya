"""
Structured configuration files are YAML, read through the adopted DishtaYantra configurator.

``application.yaml`` has always been parsed by ``PropertiesConfigurator``. The structured
files beside it -- model profiles, the tiering questionnaire, the shipped workflow policies
-- are read through the same configurator (``Settings.load_yaml``), so their
``${VAR:default}`` placeholders resolve with the same precedence as every setting. The SDK's
profile file is YAML too, read by the SDK itself (it stands without the rest of MAYA) in the
same placeholder dialect.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys

import pytest

from maya.config import load_settings
from maya.core.errors import ConfigurationError, ValidationFailed
from maya.core.properties_configurator import PropertiesConfigurator

BASE = """
app:
  environment: dev
db:
  dialect: sqlite
  sqlite:
    path: "${storage.root}/maya.db"
storage:
  root: "%s"
auth:
  mode: db
llm:
  profiles_file: "%s"
"""


@pytest.fixture
def settings(tmp_path, monkeypatch):
    profiles = tmp_path / "llm_profiles.yaml"
    (tmp_path / "application.yaml").write_text(
        BASE % (tmp_path / "home", profiles), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["pytest"])
    monkeypatch.setenv("MAYA_HOME", str(tmp_path / "home"))
    s = load_settings(tmp_path / "application.yaml", fresh=True)
    yield s, tmp_path, profiles
    PropertiesConfigurator.reset_instance()


def test_a_structured_file_resolves_placeholders_through_the_configurator(settings, monkeypatch):
    s, tmp, _ = settings
    monkeypatch.setenv("GPU_BOX", "http://gpu-box:11434")
    doc = tmp / "any.yaml"
    doc.write_text(
        'a: "${GPU_BOX:http://localhost:11434}"\n'
        'b: "${NOT_SET_ANYWHERE:fallback}"\n'
        'c: "${db.dialect}"\n',
        encoding="utf-8",
    )
    assert s.load_yaml(doc) == {"a": "http://gpu-box:11434", "b": "fallback", "c": "sqlite"}
    doc.write_text("a: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="any.yaml"):
        s.load_yaml(doc)


def test_model_profiles_take_placeholders(settings, monkeypatch):
    from maya.llm import profiles as prof

    s, _, profiles = settings
    monkeypatch.setenv("LOCAL_LLM_URL", "http://10.0.0.7:11434")
    profiles.write_text(
        "default: local\nprofiles:\n  local:\n    provider: ollama\n    model: qwen\n"
        '    options: {base_url: "${LOCAL_LLM_URL:http://localhost:11434}"}\n',
        encoding="utf-8",
    )
    known, default = prof.load(s)
    assert default == "local"
    assert known["local"].options["base_url"] == "http://10.0.0.7:11434"


def test_the_shipped_policies_read_the_same_either_way(settings):
    from maya.workflow.policy import default_policies

    s, _, _ = settings
    assert default_policies(s) == default_policies()


def _home(monkeypatch, tmp_path):
    monkeypatch.delenv("MAYA_CONFIG", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".maya").mkdir(exist_ok=True)
    return tmp_path / ".maya"


def test_the_sdk_profile_file_is_yaml_with_placeholders(tmp_path, monkeypatch):
    from maya.sdk.client import _profile

    home = _home(monkeypatch, tmp_path)
    monkeypatch.setenv("PROD_HOST", "maya.example.com")
    (home / "config.yaml").write_text(
        'profiles:\n  prod:\n    base_url: "https://${PROD_HOST:localhost}"\n'
        "    api_key_env: MAYA_PROD_KEY\n",
        encoding="utf-8",
    )
    assert _profile("prod") == {
        "base_url": "https://maya.example.com",
        "api_key_env": "MAYA_PROD_KEY",
    }
    with pytest.raises(ValidationFailed, match="No profile 'uat'"):
        _profile("uat")


def test_an_older_toml_profile_file_still_works_with_a_warning(tmp_path, monkeypatch):
    from maya.sdk.client import _profile

    home = _home(monkeypatch, tmp_path)
    (home / "config.toml").write_text(
        '[profiles.prod]\nbase_url = "https://old.example.com"\n', encoding="utf-8"
    )
    with pytest.warns(DeprecationWarning, match="YAML now"):
        assert _profile("prod") == {"base_url": "https://old.example.com"}
    (tmp_path / ".maya" / "config.toml").unlink()
    with pytest.raises(ValidationFailed, match="config.yaml"):
        _profile("prod")
