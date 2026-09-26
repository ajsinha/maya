"""
``maya.testing``: the throwaway MAYA SDK users test against — seeded users whose
clients see what their roles allow, helpers that yield approved objects visible
through the SDK, the pytest plugin's fixtures, and a clean exit (directory gone,
``sys.argv`` and the environment untouched).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

from maya.core.errors import MayaError, PermissionDenied
from maya.testing import DEFAULT_USERS, Maya, infer_definition

pytest_plugins = ["maya.testing.pytest_plugin"]

PX = b"date,symbol,close\n2026-01-02,AAA,10.5\n2026-01-02,BBB,20.0\n2026-01-05,AAA,11.0\n"


def test_seeded_users_log_in_and_see_what_their_role_allows(maya_test):
    admin = maya_test.client()
    users = {u["username"]: u for u in admin.admin.users()}
    for name, roles in DEFAULT_USERS.items():
        assert name in users
        assert maya_test.client(name).auth.me()["username"] == name
    assert maya_test.client("dana") is maya_test.client("dana")  # cached per user
    assert "test" in {n["name"] for n in admin.namespaces.list()}

    dana, mick = maya_test.client("dana"), maya_test.client("mick")
    dana.features.create("test", "roles_px", infer_definition(PX))  # a designer designs
    dana.features.ingest("test/roles_px", PX, fmt="csv")
    dana.features.transition("test/roles_px", 1, "submit")
    with pytest.raises(PermissionDenied):  # ...but never approves
        dana.features.transition("test/roles_px", 1, "approve")
    with pytest.raises(PermissionDenied):  # nor administers
        dana.admin.create_user("mallory", password="Mallory-pass-12", roles=["admin"])
    assert mick.features.transition("test/roles_px", 1, "approve")["state"] == "approved"


def test_helpers_yield_approved_objects_visible_through_the_sdk(maya_test):
    frame = pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-02", "2026-01-05", "2026-01-05"],
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "x": [1.0, 2.0, 3.0, 4.0],
            "y": [2.5, 4.5, 6.5, 8.5],
        }
    )
    ref = maya_test.approved_feature("xy", frame)  # a DataFrame, definition inferred
    dana = maya_test.client("dana")
    feature = dana.features.get(ref)
    assert feature["versions"][0]["state"] == "approved"
    assert feature["versions"][0]["definition"]["index"] == ["date", "symbol"]

    plain = maya_test.approved_featureset("xy_set", {"x": ref, "y": (ref, "y")})
    assert plain == "maya://featureset/test/xy_set@v1"
    pin = maya_test.approved_featureset("x_pinned", {"x": ref}, pin=("eom", "2026-01-31"))
    assert pin == "maya://featureset/test/x_pinned#eom/2026-01-31"
    fs = maya_test.client("devi").featuresets.get("test/x_pinned")
    assert fs["versions"][0]["state"] == "approved" and fs["pins"][0]["state"] == "sealed"
    assert maya_test.client("devi").featuresets.preview(pin)["total_rows"] == 4

    model = maya_test.approved_model("line", "yhat = a*x + b", {"a": "parameter", "b": "parameter"})
    assert model == "test/line@v1"
    assert maya_test.client("mona").models.get("test/line")["versions"][0]["state"] == "approved"
    warrant = maya_test.training_warrant("fit", model, plain, {"target": "y"})
    assert warrant["contract_report"]["ok"]
    # ingested today about January: known long after the event, and the certificate says so
    assert warrant["leakage_certificate"]["status"] == "refused"


def test_factory_settings_cleanup_and_untouched_process_state(maya_factory, monkeypatch, tmp_path):
    monkeypatch.setenv("MAYA_HOME", str(tmp_path / "somebody-elses-home"))
    argv, environ = list(sys.argv), dict(os.environ)
    maya = maya_factory(
        users={"solo": ["feature_designer"]},
        namespace="lab",
        settings={"workflow.allow_self_approval": "true"},
    )
    assert sys.argv == argv and dict(os.environ) == environ
    home = maya.home
    assert home.is_dir() and maya.platform.settings.storage_root == home
    assert not (tmp_path / "somebody-elses-home").exists()  # MAYA_HOME is not used
    assert maya.platform.settings.bool("workflow.allow_self_approval") is True
    assert maya.platform.settings.dialect == "sqlite" and maya.platform.settings.is_dev
    assert maya.client("solo").auth.me()["roles"] == ["feature_designer"]
    with pytest.raises(MayaError):
        maya.client("dana")  # not seeded here

    maya.close()
    maya.close()  # idempotent
    assert not home.exists()
    assert sys.argv == argv and dict(os.environ) == environ
    with pytest.raises(MayaError, match="closed"):
        maya.client("solo")


def test_keep_leaves_the_directory_for_a_post_mortem():
    with Maya.start(users={}, namespace="", keep=True) as maya:
        home = maya.home
    try:
        assert (home / "maya.db").is_file()
    finally:
        import shutil

        shutil.rmtree(home, ignore_errors=True)


def test_the_admin_client_survives_a_changed_bootstrap_password(maya_factory):
    """The quick start tells a new user to change the published admin password, and every
    case study signs in as admin: the kit opens an operator session instead, and says so
    in the audit chain, without learning or resetting the new password."""
    m = maya_factory()
    m.client("admin").auth.change_password("maya-dev-admin", "Changed-by-user-2026")
    fresh = Maya.__new__(Maya)  # a later process: same platform, no cached clients
    fresh.__dict__.update({**m.__dict__, "_clients": {}})
    admin = fresh.client("admin")
    assert admin.auth.me()["username"] == "admin"
    with m.platform.uow() as uow:
        assert uow.repo("audit_events").find_one(action="auth.operator_session")
    again = Maya.__new__(Maya)
    again.__dict__.update({**m.__dict__, "_clients": {}})
    with pytest.raises(MayaError):
        again.client("admin", password="maya-dev-admin")  # an explicit password is not bypassed
