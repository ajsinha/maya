"""
MAYA — test fixtures.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.properties_configurator import PropertiesConfigurator  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Every test gets a clean configurator; the singleton must not leak."""
    PropertiesConfigurator.reset()
    yield
    PropertiesConfigurator.reset()


@pytest.fixture
def write_yaml(tmp_path):
    def _write(name: str, body: str) -> str:
        p = tmp_path / name
        p.write_text(body)
        return str(p)
    return _write
