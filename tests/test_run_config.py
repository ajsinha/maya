"""
MAYA — where the server starts from.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The configuration path was hard-coded, so a second instance — a demonstration
estate, a training environment, a copy of production to reproduce something
against — could only be started by editing a tracked file. Whoever did that was
one `git commit -a` away from shipping it.
"""

import sys

import pytest

from run_maya_web import config_path


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("MAYA_CONFIG", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_maya_web.py"])


def test_the_repository_config_is_the_default():
    assert config_path().endswith("config/application.yaml")


def test_an_environment_variable_wins_over_the_default(monkeypatch):
    monkeypatch.setenv("MAYA_CONFIG", "/somewhere/else.yaml")
    assert config_path() == "/somewhere/else.yaml"


@pytest.mark.parametrize("argv", [
    ["run_maya_web.py", "--config", "/on/the/command/line.yaml"],
    ["run_maya_web.py", "--config=/on/the/command/line.yaml"],
])
def test_the_command_line_wins_over_everything(monkeypatch, argv):
    """Both spellings, because a reader who tries one and gets the default
    silently has no way to tell that the flag was ignored."""
    monkeypatch.setenv("MAYA_CONFIG", "/somewhere/else.yaml")
    monkeypatch.setattr(sys, "argv", argv)
    assert config_path() == "/on/the/command/line.yaml"


def test_a_trailing_config_flag_with_no_path_falls_through(monkeypatch):
    """Rather than raising IndexError on the argument that is not there."""
    monkeypatch.setattr(sys, "argv", ["run_maya_web.py", "--config"])
    assert config_path().endswith("config/application.yaml")
