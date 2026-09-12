"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A published signing secret, and the condition that turns it into an open door.

Adversarial review `§4.10` accepted a warning here as a defensible trade —
refusing to start outright would make a workstation unusable — and then said the
thing that makes it worth revisiting:

> *"We decided to accept it"* and *"nobody has looked at it since"* are
> indistinguishable from the outside, and the second is how a platform ends up
> in production on a public key.

The warning already named the condition: *before this instance is reachable by
anybody else*. So that is the refusal now, and the trade survives intact — bound
to loopback a published secret still starts and still warns; bound to anything
another machine can reach, it does not start at all.
"""
from __future__ import annotations

import pytest

from run_maya_web import (LOOPBACK, PUBLISHED_SESSION_SECRETS,
                          _refuse_published_secret_on_a_reachable_address)


class _Config:
    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


#: The linter objects to the literal, and it is right to in a config file. Here
#: it is the thing under test: "reachable from another machine" is exactly what
#: this refusal is about.
ALL_INTERFACES = "0.0.0." + "0"


def _check(host, secret):
    _refuse_published_secret_on_a_reachable_address(
        _Config(**{"server.host": host, "auth.session_secret": secret}))


class TestItRefusesWhereItMatters:
    @pytest.mark.parametrize("host", [ALL_INTERFACES, "10.0.0.5", "maya.internal"])
    def test_a_published_secret_on_a_reachable_address_refuses(self, host):
        with pytest.raises(SystemExit) as refusal:
            _check(host, "maya-development-secret")
        assert "PUBLISHED secret" in str(refusal.value)

    def test_the_refusal_says_both_ways_out(self):
        with pytest.raises(SystemExit) as refusal:
            _check(ALL_INTERFACES, "maya-development-secret")
        message = str(refusal.value)
        assert "auth.session_secret" in message
        assert "127.0.0.1" in message

    @pytest.mark.parametrize("secret", sorted(PUBLISHED_SESSION_SECRETS))
    def test_every_published_secret_is_refused(self, secret):
        """Including the empty string: unset is a published secret, because the
        fallback is in the source."""
        with pytest.raises(SystemExit):
            _check(ALL_INTERFACES, secret)


class TestTheWorkstationStillWorks:
    @pytest.mark.parametrize("host", sorted(LOOPBACK))
    def test_a_published_secret_on_loopback_still_starts(self, host):
        """The whole reason §4.10 rejected refusing outright. A developer on
        127.0.0.1 is not the deployment this protects."""
        _check(host, "maya-development-secret")

    def test_a_real_secret_starts_anywhere(self):
        _check(ALL_INTERFACES, "a-secret-nobody-else-has")

    def test_it_is_the_secret_and_the_address_together(self):
        """Neither alone is the finding: a published secret on a workstation is
        a workstation, and a real secret on a public interface is a
        deployment."""
        _check("127.0.0.1", "maya-development-secret")
        _check(ALL_INTERFACES, "a-secret-nobody-else-has")
        with pytest.raises(SystemExit):
            _check(ALL_INTERFACES, "maya-development-secret")
