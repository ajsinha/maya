"""
MAYA — the published API, locked.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

No test in this suite notices a renamed route or a body that gains a required
key, because every test calls the API the way the code currently spells it. The
lock is the only thing standing between a breaking change and a client finding
out about it.
"""

import json
from pathlib import Path

import pytest

from tools.ci.spec_lock import LOCK, differences

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def locked():
    assert LOCK.exists(), "openapi.lock.json is missing; run spec_lock.py --update"
    return json.loads(LOCK.read_text())


class TestTheLockDescribesSomething:
    def test_it_covers_the_api(self, locked):
        paths = locked["paths"]
        assert len(paths) > 200, f"only {len(paths)} paths locked"
        assert "/api/v1/models" in paths

    def test_it_records_requiredness_and_not_only_names(self, locked):
        """`!` on a required field. A field moving into the required list is a
        breaking change that a name-only lock would miss."""
        bodies = [f for methods in locked["paths"].values()
                  for op in methods.values() for f in op["body"]]
        assert any(f.endswith("!") for f in bodies)

    def test_it_does_not_lock_prose(self, locked):
        """Descriptions, summaries and examples are deliberately absent.

        Locking them would make a reworded docstring an interface change, and a
        gate that fires on prose is one people learn to run with `--update`
        reflexively — at which point it stops catching the renamed route it
        exists for.

        Asserted on the STRUCTURE rather than by searching the text: several
        request bodies have a field genuinely called `description`, and a
        substring check confuses a domain field with OpenAPI prose.
        """
        for path, methods in locked["paths"].items():
            for method, operation in methods.items():
                assert set(operation) == {"parameters", "body", "responses"}, (
                    f"{method.upper()} {path} locks more than the shape: "
                    f"{sorted(operation)}")


class TestItDetectsWhatItIsFor:
    def test_a_removed_path_is_reported_as_removed(self):
        was = {"paths": {"/a": {"get": {"parameters": [], "body": [],
                                        "responses": ["200"]}}}}
        assert any("REMOVED  /a" in line for line in differences(was, {"paths": {}}))

    def test_a_new_required_field_is_reported(self):
        was = {"paths": {"/a": {"post": {"parameters": [], "body": ["x"],
                                         "responses": ["201"]}}}}
        now = {"paths": {"/a": {"post": {"parameters": [], "body": ["x", "y!"],
                                         "responses": ["201"]}}}}
        lines = differences(was, now)
        assert any("y!" in line for line in lines)

    def test_a_removed_response_code_is_reported(self):
        was = {"paths": {"/a": {"get": {"parameters": [], "body": [],
                                        "responses": ["200", "409"]}}}}
        now = {"paths": {"/a": {"get": {"parameters": [], "body": [],
                                        "responses": ["200"]}}}}
        assert any("409" in line for line in differences(was, now))

    def test_an_identical_shape_reports_nothing(self, locked):
        assert differences(locked, locked) == []
