"""
The short principal cache (auth.session.principal_cache_seconds).

One page makes several internal API calls for the same session, so a signed-in
session's principal is reused for a couple of seconds. What must still hold: a
sign-out, a revocation and an access change made in this process apply at once;
merely using a session (its last-seen touch) does not throw the cache away; a
session still owing a second factor is never reused; and 0 turns reuse off.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.core.errors import NotAuthenticated
from tests.conftest import PASSWORD


def _token(w, username: str) -> str:
    return w.p.auth.login(username, PASSWORD)["token"]


def test_a_session_is_resolved_once_then_reused(world):
    w = world
    token = _token(w, "dana")
    first = w.p.auth.principal(token)
    assert w.p.auth.principal(token) is first, "reused within the window"


def test_sign_out_and_revocation_apply_at_once_in_this_process(world):
    w = world
    token = _token(w, "dana")
    w.p.auth.principal(token)
    w.p.auth.logout(token)
    with pytest.raises(NotAuthenticated):
        w.p.auth.principal(token)
    other = _token(w, "dana")
    w.p.auth.principal(other)
    with w.p.uow() as uow:  # an administrator ends every session
        for s in uow.repo("sessions").list(revoked_at__isnull=True):
            uow.repo("sessions").update(s["id"], {"revoked_at": s["created_at"]})
    with pytest.raises(NotAuthenticated):
        w.p.auth.principal(other)


def test_a_role_change_applies_at_once_in_this_process(world):
    w = world
    token = _token(w, "mona")
    before = w.p.auth.principal(token)
    with w.p.uow() as uow:
        user = uow.repo("users").find_one(username="mona")
        role = uow.repo("roles").find_one(name="feature_designer")
        uow.repo("user_roles").add({"user_id": user["id"], "role_id": role["id"]})
    after = w.p.auth.principal(token)
    assert after is not before and "feature_designer" in after.roles


def test_using_a_session_does_not_empty_the_cache(world):
    w = world
    token = _token(w, "dana")
    cached = w.p.auth.principal(token)
    with w.p.uow() as uow:  # the 30-second last-seen touch
        s = uow.repo("sessions").find_one(token_hash=w.p.auth.token_hash(token))
        uow.repo("sessions").update(s["id"], {"last_seen_at": s["created_at"]})
    assert w.p.auth.principal(token) is cached


def test_zero_turns_reuse_off(world, monkeypatch):
    w = world
    monkeypatch.setattr(w.p.auth, "principal_ttl", 0.0)
    w.p.auth.forget_principals()
    token = _token(w, "dana")
    assert w.p.auth.principal(token) is not w.p.auth.principal(token)
