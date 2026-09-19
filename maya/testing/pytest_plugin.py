"""
pytest fixtures for testing against a throwaway MAYA (``maya.testing``).

Load it once, in your ``conftest.py``::

    pytest_plugins = ["maya.testing.pytest_plugin"]

Fixtures:

* ``maya_test`` — a started ``Maya`` shared by every test in a module (it takes
  about two seconds to build), closed after the module. Tests in one module
  therefore see each other's objects: give them distinct names.
* ``maya_factory`` — a function ``maya_factory(**kwargs) -> Maya`` taking the
  arguments of ``Maya.start``, for a test that needs its own platform or its own
  settings; every Maya it made is closed when the test ends.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any, Callable, Iterator

import pytest

from maya.testing.kit import Maya


@pytest.fixture(scope="module")
def maya_test() -> Iterator[Maya]:
    """One seeded, in-process MAYA per test module."""
    with Maya.start() as maya:
        yield maya


@pytest.fixture
def maya_factory() -> Iterator[Callable[..., Maya]]:
    """Start Mayas with your own arguments; all are closed after the test."""
    made: list[Maya] = []

    def factory(**kwargs: Any) -> Maya:
        maya = Maya.start(**kwargs)
        made.append(maya)
        return maya

    yield factory
    for maya in made:
        maya.close()
