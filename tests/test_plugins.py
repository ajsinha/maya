"""
§25: "every axis of variation is a registered plugin implementing a declared protocol,
discovered by entry point, configured by name". MAYA had the variation and no registry, so
nothing was discoverable and a third party could not add anything without editing MAYA.

These tests hold the registry to two promises: what it lists is what exists, and an
installed plugin is not loaded merely because it is installed.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import pytest

from maya import notifiers
from maya.core.errors import CapabilityRefused, PermissionDenied
from maya.plugins import POINTS, Registry, built_ins


class _Settings:
    """Just enough of the settings object for a channel."""

    def __init__(self, **values: object) -> None:
        self.values = values

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    def int(self, key: str, default: int) -> int:
        return int(self.values.get(key, default))  # type: ignore[arg-type]

    def bool(self, key: str, default: bool) -> bool:
        return bool(self.values.get(key, default))


def test_every_point_the_specification_names_is_registered(world):
    report = world.p.plugins.report()
    assert {p["point"] for p in report["points"]} == set(POINTS)
    registered = {p["point"]: p["registered"] for p in report["points"]}
    # what is listed is what exists: the source drivers MAYA resolves, the rules it applies,
    # the calendars it ships, the checks the workflow engine actually registered
    assert {"csv", "parquet", "delta", "python", "derived", "sql", "json"} <= set(
        registered["source_driver"]
    )
    assert "forward_fill" in registered["resolution_rule"]
    assert {"NYSE", "LSE", "TARGET"} <= set(registered["calendar"])
    assert registered["workflow_check"], "the engine's checks are listed, not a static list"
    assert registered["search_index"] == ["inverted_index"]
    assert set(registered["notifier"]) == {"inbox", "webhook", "email", "slack", "teams"}


def test_an_unknown_point_is_refused_when_something_tries_to_register_at_it():
    registry = Registry()
    with pytest.raises(ValueError, match="unknown extension point"):
        registry.register("telepathy", "mind_reader")


def test_an_installed_plugin_is_refused_unless_it_is_named(monkeypatch):
    """A plugin runs in MAYA's own process with MAYA's privileges, so being installed is not
    consent. The refusal is recorded with the reason, not swallowed."""

    class _Entry:
        def __init__(self, name: str) -> None:
            self.name = name
            self.dist = type("D", (), {"name": "some-package"})()

        def load(self):  # pragma: no cover - never reached when refused
            raise AssertionError("a refused plugin must not be loaded")

    def entry_points(*, group: str):
        return [_Entry("mystery_source")] if group == "maya.source_driver" else []

    monkeypatch.setattr("importlib.metadata.entry_points", entry_points)
    refused = Registry()
    refused.discover(_Settings())
    row = next(r for r in refused.rows() if r["name"] == "mystery_source")
    assert row["status"] == "refused" and "plugins.allow" in row["detail"]
    assert refused.get("source_driver", "mystery_source") is None

    class _Good(_Entry):
        maya_plugin = {"version": "2.1", "capabilities": ["reads csv"]}

        def load(self):
            loaded = type("Driver", (), {"maya_plugin": self.maya_plugin})
            return loaded

    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda *, group: [_Good("mystery_source")] if group == "maya.source_driver" else [],
    )
    allowed = Registry()
    allowed.discover(_Settings(**{"plugins.allow": "mystery_source, another"}))
    got = allowed.get("source_driver", "mystery_source")
    assert got is not None and got.origin == "some-package" and got.version == "2.1"


def test_a_plugin_that_fails_to_load_is_reported_and_does_not_stop_maya(monkeypatch):
    class _Broken:
        name = "broken"
        dist = None

        def load(self):
            raise RuntimeError("no module named dependency")

    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda *, group: [_Broken()] if group == "maya.notifier" else [],
    )
    registry = Registry()
    registry.discover(_Settings(**{"plugins.allow": "broken"}))
    row = next(r for r in registry.rows() if r["name"] == "broken")
    assert row["status"] == "failed" and "no module named dependency" in row["detail"]


def test_a_channel_with_no_configuration_says_so_rather_than_dropping_the_notice():
    for name in ("email", "slack", "teams"):
        ready, why = notifiers.CHANNELS[name](_Settings()).configured()
        assert not ready and name in why or "notify." in why
        with pytest.raises(CapabilityRefused, match="not configured"):
            notifiers.send(_Settings(), name, "subject", "body", ["someone@example.com"])
    ready, why = notifiers.CHANNELS["inbox"](_Settings()).configured()
    assert ready and "always on" in why


def test_slack_and_teams_shape_their_own_payloads_and_refuse_plain_http():
    settings = _Settings(**{"notify.slack.webhook_url": "http://hooks.example.com/x"})
    ready, why = notifiers.CHANNELS["slack"](settings).configured()
    assert not ready and "https" in why
    slack = notifiers.Slack(_Settings(**{"notify.slack.webhook_url": "https://x/y"}))
    teams = notifiers.Teams(_Settings(**{"notify.teams.webhook_url": "https://x/y"}))
    assert slack.payload("s", "b")["text"].startswith("*s*")
    assert teams.payload("s", "b")["@type"] == "MessageCard"
    with pytest.raises(CapabilityRefused, match="Unknown channel"):
        notifiers.send(_Settings(), "carrier_pigeon", "s", "b", [])


def test_the_email_channel_sends_through_smtp_when_it_is_configured(monkeypatch):
    sent: list[tuple[str, str]] = []

    class _SMTP:
        def __init__(self, host, port, timeout=None):
            sent.append(("connect", f"{host}:{port}"))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def starttls(self):
            sent.append(("starttls", ""))

        def login(self, user, password):
            sent.append(("login", user))

        def send_message(self, message):
            sent.append(("send", message["To"]))

    monkeypatch.setattr("smtplib.SMTP", _SMTP)
    settings = _Settings(
        **{
            "notify.email.host": "smtp.example.com",
            "notify.email.from": "maya@example.com",
            "notify.email.username": "maya",
            "notify.email.password": "secret",
        }
    )
    out = notifiers.send(settings, "email", "A pin failed", "See MAYA.", ["a@x.com", "b@x.com"])
    assert out["sent"] == 2 and not out["failed"]
    assert ("send", "a@x.com") in sent and ("starttls", "") in sent
    assert ("login", "maya") in sent


def test_the_extension_report_is_for_administrators_and_names_the_channels(world):
    w = world
    report = w.p.ops.extensions(w.admin)
    assert {c["channel"] for c in report["channels"]} == set(notifiers.CHANNELS)
    assert any("privileges" in report["note"] for _ in [0])
    with pytest.raises(PermissionDenied, match="administrators and techops"):
        w.p.ops.extensions(w.dana)


def test_the_built_in_registry_needs_no_platform_to_be_listed():
    """A screen can list the points before a platform exists — the built-ins are static."""
    registry = built_ins(Registry())
    assert registry.at("exporter") and registry.at("calendar")
    assert registry.at("workflow_check") == [], "checks come from a platform, and it says so"
