"""
MAYA — configuration tests.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import os
import sys

import pytest

from core.properties_configurator import ConfigError, PropertiesConfigurator, config

BASE = """
app:
  name: MAYA
  version: "0.1.0"
server:
  host: 0.0.0.0
  port: 8080
  debug: true
  ratio: 0.75
tags: [alpha, beta, gamma]
nested:
  deep:
    value: found
"""


class TestFlattening:
    def test_nested_keys_become_dotted(self, write_yaml):
        c = PropertiesConfigurator(write_yaml("a.yaml", BASE), reload_interval=0)
        assert c.get("app.name") == "MAYA"
        assert c.get("nested.deep.value") == "found"

    def test_lists_become_comma_joined(self, write_yaml):
        c = PropertiesConfigurator(write_yaml("a.yaml", BASE), reload_interval=0)
        assert c.get_list("tags") == ["alpha", "beta", "gamma"]

    def test_missing_key_returns_default(self, write_yaml):
        c = PropertiesConfigurator(write_yaml("a.yaml", BASE), reload_interval=0)
        assert c.get("nope", "fallback") == "fallback"
        assert c.get("nope") is None

    def test_absent_file_is_not_fatal(self, tmp_path):
        c = PropertiesConfigurator(str(tmp_path / "ghost.yaml"), reload_interval=0)
        assert c.get("anything") is None

    def test_malformed_yaml_raises(self, write_yaml):
        path = write_yaml("bad.yaml", "app:\n  name: [unclosed\n")
        with pytest.raises(ConfigError):
            PropertiesConfigurator(path, reload_interval=0)


class TestTypedAccessors:
    @pytest.fixture
    def cfg(self, write_yaml):
        return PropertiesConfigurator(write_yaml("a.yaml", BASE), reload_interval=0)

    def test_get_int(self, cfg):
        assert cfg.get_int("server.port") == 8080

    def test_get_int_falls_back_when_not_numeric(self, cfg):
        assert cfg.get_int("app.name", 42) == 42

    def test_get_float(self, cfg):
        assert cfg.get_float("server.ratio") == 0.75

    def test_get_float_default(self, cfg):
        assert cfg.get_float("absent", 1.5) == 1.5

    @pytest.mark.parametrize("raw", ["true", "True", "YES", "on", "1", "y", "t"])
    def test_truthy_spellings(self, write_yaml, raw):
        c = PropertiesConfigurator(write_yaml("b.yaml", f"flag: '{raw}'"), reload_interval=0)
        assert c.get_bool("flag") is True

    @pytest.mark.parametrize("raw", ["false", "no", "off", "0", "", "maybe"])
    def test_falsy_spellings(self, write_yaml, raw):
        c = PropertiesConfigurator(write_yaml("b.yaml", f"flag: '{raw}'"), reload_interval=0)
        assert c.get_bool("flag") is False

    def test_get_bool_default_when_absent(self, cfg):
        assert cfg.get_bool("absent", True) is True

    def test_get_list_default_when_absent(self, cfg):
        assert cfg.get_list("absent", ["x"]) == ["x"]

    def test_require_returns_value(self, cfg):
        assert cfg.require("app.name") == "MAYA"

    def test_require_raises_when_missing(self, cfg):
        with pytest.raises(ConfigError, match="required configuration key"):
            cfg.require("app.secret")


class TestResolution:
    def test_simple_reference(self, write_yaml):
        c = PropertiesConfigurator(
            write_yaml("a.yaml", "base: /var/maya\ndir: ${base}/data"), reload_interval=0)
        assert c.get("dir") == "/var/maya/data"

    def test_nested_reference(self, write_yaml):
        c = PropertiesConfigurator(
            write_yaml("a.yaml", "a: one\nb: ${a}-two\nc: ${b}-three"), reload_interval=0)
        assert c.get("c") == "one-two-three"

    def test_default_used_when_target_absent(self, write_yaml):
        c = PropertiesConfigurator(write_yaml("a.yaml", "port: ${MISSING:9999}"), reload_interval=0)
        assert c.get_int("port") == 9999

    def test_environment_satisfies_reference(self, write_yaml, monkeypatch):
        monkeypatch.setenv("SOME_HOST", "db.internal")
        c = PropertiesConfigurator(write_yaml("a.yaml", "host: ${SOME_HOST:localhost}"), reload_interval=0)
        assert c.get("host") == "db.internal"

    def test_unresolvable_reference_is_left_verbatim(self, write_yaml):
        c = PropertiesConfigurator(write_yaml("a.yaml", "x: ${nothing_here}"), reload_interval=0)
        assert c.get("x") == "${nothing_here}"

    def test_cycle_terminates(self, write_yaml):
        """A self-referential value must not hang or recurse without bound."""
        c = PropertiesConfigurator(write_yaml("a.yaml", "a: ${b}\nb: ${a}"), reload_interval=0)
        assert "${" in c.get("a")


class TestPrecedence:
    def test_rightmost_file_wins(self, write_yaml):
        one = write_yaml("one.yaml", "app:\n  name: FIRST\n  keep: retained")
        two = write_yaml("two.yaml", "app:\n  name: SECOND")
        c = PropertiesConfigurator([one, two], reload_interval=0)
        assert c.get("app.name") == "SECOND"
        assert c.get("app.keep") == "retained", "keys not overridden must survive"

    def test_environment_beats_file(self, write_yaml, monkeypatch):
        monkeypatch.setenv("MAYA_APP_NAME", "FROM_ENV")
        c = PropertiesConfigurator(write_yaml("a.yaml", BASE), reload_interval=0)
        assert c.get("app.name") == "FROM_ENV"
        assert c.source_of("app.name") == "env"

    def test_commandline_beats_environment(self, write_yaml, monkeypatch):
        monkeypatch.setenv("MAYA_APP_NAME", "FROM_ENV")
        monkeypatch.setattr(sys, "argv", ["prog", "--app.name=FROM_CLI"])
        c = PropertiesConfigurator(write_yaml("a.yaml", BASE), reload_interval=0)
        assert c.get("app.name") == "FROM_CLI"
        assert c.source_of("app.name") == "commandline"

    def test_source_reported_for_file_values(self, write_yaml):
        path = write_yaml("a.yaml", BASE)
        c = PropertiesConfigurator(path, reload_interval=0)
        assert c.source_of("app.name") == f"file:{path}"

    def test_config_file_env_override_wins_over_argument(self, write_yaml, monkeypatch):
        pointed = write_yaml("pointed.yaml", "app:\n  name: POINTED")
        ignored = write_yaml("ignored.yaml", "app:\n  name: IGNORED")
        monkeypatch.setenv("MAYA_CONFIG_FILE", pointed)
        c = PropertiesConfigurator(ignored, reload_interval=0)
        assert c.get("app.name") == "POINTED"


class TestYamlCoercionGotchas:
    """YAML 1.1 coerces some bare words before we ever see them. Pinned here so
    the behaviour is deliberate rather than discovered in production."""

    @pytest.mark.parametrize("bare,becomes", [("yes", "True"), ("no", "False"),
                                              ("on", "True"), ("off", "False")])
    def test_bare_booleans_are_coerced_by_the_yaml_parser(self, write_yaml, bare, becomes):
        c = PropertiesConfigurator(write_yaml("a.yaml", f"flag: {bare}"), reload_interval=0)
        assert c.get("flag") == becomes

    def test_quoting_preserves_the_literal_word(self, write_yaml):
        """The fix, for the country code NO or a column named 'on'."""
        c = PropertiesConfigurator(write_yaml("a.yaml", "country: 'no'"), reload_interval=0)
        assert c.get("country") == "no"

    def test_coerced_booleans_still_read_correctly_as_bool(self, write_yaml):
        c = PropertiesConfigurator(write_yaml("a.yaml", "flag: yes"), reload_interval=0)
        assert c.get_bool("flag") is True


class TestLocalOverlay:
    def test_overlay_is_applied_after_base(self, tmp_path):
        (tmp_path / "app.yaml").write_text("app:\n  name: BASE\n  port: 1\n")
        (tmp_path / "app.local.yaml").write_text("app:\n  name: OVERLAID\n")
        c = PropertiesConfigurator(str(tmp_path / "app.yaml"), reload_interval=0)
        assert c.get("app.name") == "OVERLAID"
        assert c.get("app.port") == "1", "the overlay sets only what it names"

    def test_absent_overlay_is_a_no_op(self, tmp_path):
        (tmp_path / "app.yaml").write_text("app:\n  name: BASE\n")
        c = PropertiesConfigurator(str(tmp_path / "app.yaml"), reload_interval=0)
        assert c.get("app.name") == "BASE"


class TestSingletonAndReload:
    def test_singleton_returns_same_instance(self, write_yaml):
        path = write_yaml("a.yaml", BASE)
        assert PropertiesConfigurator(path, reload_interval=0) is PropertiesConfigurator()

    def test_module_accessor_returns_singleton(self, write_yaml):
        c = PropertiesConfigurator(write_yaml("a.yaml", BASE), reload_interval=0)
        assert config() is c

    def test_reset_clears_the_singleton(self, write_yaml):
        first = PropertiesConfigurator(write_yaml("a.yaml", BASE), reload_interval=0)
        PropertiesConfigurator.reset()
        assert PropertiesConfigurator(write_yaml("b.yaml", "app:\n  name: OTHER"),
                                      reload_interval=0) is not first

    def test_reload_picks_up_edits(self, tmp_path):
        p = tmp_path / "a.yaml"
        p.write_text("app:\n  name: ONE\n")
        c = PropertiesConfigurator(str(p), reload_interval=0)
        assert c.get("app.name") == "ONE"
        p.write_text("app:\n  name: TWO\n")
        c.reload()
        assert c.get("app.name") == "TWO"

    def test_as_dict_resolves_references(self, write_yaml):
        c = PropertiesConfigurator(write_yaml("a.yaml", "a: x\nb: ${a}y"), reload_interval=0)
        assert c.as_dict()["b"] == "xy"


class TestShippedConfiguration:
    """The configuration this repository actually ships must load and be sane."""

    def test_application_yaml_loads(self):
        c = PropertiesConfigurator("config/application.yaml", reload_interval=0)
        assert c.get("app.name") == "MAYA"
        assert c.get("app.slogan") == "Evidence, not assertion."
        assert c.get("app.author.email") == "ajsinha@gmail.com"

    def test_tier_one_hook_grace_is_zero(self):
        """Grace extends authorisation currency, never revocation ignorance."""
        c = PropertiesConfigurator("config/application.yaml", reload_interval=0)
        assert c.get_int("hooks.grace_seconds.1") == 0
        assert c.get_int("hooks.ttl_seconds.1") == 60

    def test_captive_engine_is_configurable(self):
        c = PropertiesConfigurator("config/application.yaml", reload_interval=0)
        assert c.get_bool("execution.captive.enabled") is True
