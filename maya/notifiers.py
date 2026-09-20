"""
Notification channels (§25's `Notifier.send(event, recipients)`).

Two channels always existed and were not called channels: the in-app **inbox**, which every
notice already lands in, and signed **webhooks**. §25 also lists email, Slack and Teams, and
those were missing — so a covenant breach or an overdue review reached a person only if they
came and looked.

Each channel here is a plugin at the `notifier` point, and each is **off until it is
configured**: no host, no channel. That is deliberate and not laziness — a platform that
mails people by default mails the wrong people the first time it is started, and MAYA is
started on laptops. A channel that cannot send says so rather than dropping the notice: the
inbox copy is written first, always, so the record survives a channel that is misconfigured
or down.

Slack and Teams both take an incoming-webhook URL, which is a secret, so it lives in the
environment or the local overlay — never in the tracked configuration file, which a gate
checks.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import json
from typing import Any

from maya.core.errors import CapabilityRefused

TIMEOUT = 10.0


class Channel:
    """What a notifier is: a name, whether it is configured, and how it sends one notice."""

    name = "channel"
    maya_plugin: dict[str, Any] = {}

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def configured(self) -> tuple[bool, str]:
        raise NotImplementedError

    def send(self, subject: str, body: str, recipients: list[str]) -> dict[str, Any]:
        raise NotImplementedError


class Inbox(Channel):
    """The in-app inbox: MAYA's own, and the one channel that cannot be misconfigured.

    Every notice is written here by the service that raised it, so this channel reports
    rather than sends — it exists in the registry because §25 lists it, and because an
    operator looking at the channel list should see the one that always works.
    """

    name = "inbox"
    maya_plugin = {
        "capabilities": ["always available", "no configuration"],
        "config_schema": {},
    }

    def configured(self) -> tuple[bool, str]:
        return True, "always on: every notice is written to the recipient's inbox"

    def send(self, subject: str, body: str, recipients: list[str]) -> dict[str, Any]:
        return {
            "channel": self.name,
            "sent": len(recipients),
            "detail": "written by the service that raised the notice",
        }


class Webhook(Channel):
    """Signed webhooks, which MAYA already delivers with retries and a dead letter."""

    name = "webhook"
    maya_plugin = {
        "capabilities": ["signed", "retried", "dead-lettered"],
        "config_schema": {"registered per subscriber": "on the Webhooks admin page"},
    }

    def configured(self) -> tuple[bool, str]:
        return True, "subscribers are registered on the Webhooks page; each delivery is signed"

    def send(self, subject: str, body: str, recipients: list[str]) -> dict[str, Any]:
        return {
            "channel": self.name,
            "sent": 0,
            "detail": "webhook delivery is driven by the event stream, not by this call",
        }


class Email(Channel):
    """SMTP, with no host configured meaning no email — and saying so."""

    name = "email"
    maya_plugin = {
        "capabilities": ["plain text", "one message per recipient"],
        "config_schema": {
            "notify.email.host": "SMTP host; empty turns the channel off",
            "notify.email.port": "587 by default",
            "notify.email.from": "the envelope sender",
            "notify.email.username": "optional; MAYA_SMTP_USERNAME",
            "notify.email.password": "optional; MAYA_SMTP_PASSWORD, never in the tracked file",
            "notify.email.starttls": "true by default",
        },
    }

    def configured(self) -> tuple[bool, str]:
        host = (self.settings.get("notify.email.host", "") or "").strip()
        if not host:
            return False, "no notify.email.host is set, so MAYA sends no email"
        if not (self.settings.get("notify.email.from", "") or "").strip():
            return False, "notify.email.host is set but notify.email.from is not"
        return True, f"SMTP to {host}"

    def send(self, subject: str, body: str, recipients: list[str]) -> dict[str, Any]:
        ready, why = self.configured()
        if not ready:
            raise CapabilityRefused(f"The email channel is not configured: {why}")
        import smtplib
        from email.message import EmailMessage

        host = str(self.settings.get("notify.email.host"))
        port = self.settings.int("notify.email.port", 587)
        sender = str(self.settings.get("notify.email.from"))
        username = self.settings.get("notify.email.username") or ""
        password = self.settings.get("notify.email.password") or ""
        starttls = self.settings.bool("notify.email.starttls", True)
        sent, failed = 0, []
        with smtplib.SMTP(host, port, timeout=TIMEOUT) as smtp:
            if starttls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            for address in recipients:
                message = EmailMessage()
                message["Subject"] = subject
                message["From"] = sender
                message["To"] = address
                message.set_content(body)
                try:
                    smtp.send_message(message)
                    sent += 1
                except Exception as exc:  # noqa: BLE001 - one bad address is not a failed run
                    failed.append(f"{address}: {exc}")
        return {"channel": self.name, "sent": sent, "failed": failed, "detail": f"SMTP {host}"}


class _IncomingWebhook(Channel):
    """Slack and Teams differ only in the shape of the body they accept."""

    setting = ""

    def configured(self) -> tuple[bool, str]:
        url = (self.settings.get(self.setting, "") or "").strip()
        if not url:
            return False, f"no {self.setting} is set, so MAYA posts nothing to {self.name}"
        if not url.startswith("https://"):
            return False, f"{self.setting} must be an https URL"
        return True, "an incoming webhook is configured"

    def payload(self, subject: str, body: str) -> dict[str, Any]:
        raise NotImplementedError

    def send(self, subject: str, body: str, recipients: list[str]) -> dict[str, Any]:
        ready, why = self.configured()
        if not ready:
            raise CapabilityRefused(f"The {self.name} channel is not configured: {why}")
        import httpx

        url = str(self.settings.get(self.setting))
        response = httpx.post(
            url,
            content=json.dumps(self.payload(subject, body)).encode(),
            headers={"content-type": "application/json"},
            timeout=TIMEOUT,
        )
        return {
            "channel": self.name,
            "sent": 1 if response.status_code < 300 else 0,
            "status": response.status_code,
            "detail": "one post to the configured incoming webhook; recipients are whoever "
            "reads that channel, which is why MAYA does not name them",
            "recipients_named": False,
        }


class Slack(_IncomingWebhook):
    name = "slack"
    setting = "notify.slack.webhook_url"
    maya_plugin = {
        "capabilities": ["one channel per URL", "no per-person addressing"],
        "config_schema": {
            "notify.slack.webhook_url": "incoming webhook URL; a secret, so set it in the "
            "environment (MAYA_SLACK_WEBHOOK_URL) or the local overlay"
        },
    }

    def payload(self, subject: str, body: str) -> dict[str, Any]:
        return {"text": f"*{subject}*\n{body}"}


class Teams(_IncomingWebhook):
    name = "teams"
    setting = "notify.teams.webhook_url"
    maya_plugin = {
        "capabilities": ["one channel per URL", "no per-person addressing"],
        "config_schema": {
            "notify.teams.webhook_url": "incoming webhook URL; a secret, so set it in the "
            "environment (MAYA_TEAMS_WEBHOOK_URL) or the local overlay"
        },
    }

    def payload(self, subject: str, body: str) -> dict[str, Any]:
        return {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": subject,
            "title": subject,
            "text": body,
        }


CHANNELS: dict[str, type[Channel]] = {c.name: c for c in (Inbox, Webhook, Email, Slack, Teams)}


def status(settings: Any) -> list[dict[str, Any]]:
    """Each channel and whether it can send, for the admin page and the health report."""
    out = []
    for name, channel in CHANNELS.items():
        ready, why = channel(settings).configured()
        out.append({"channel": name, "configured": ready, "detail": why})
    return out


def send(
    settings: Any, channel: str, subject: str, body: str, recipients: list[str]
) -> dict[str, Any]:
    """Send one notice through one channel, refusing by name when it is not configured."""
    if channel not in CHANNELS:
        raise CapabilityRefused(
            f"Unknown channel '{channel}'; MAYA ships {', '.join(sorted(CHANNELS))}"
        )
    return CHANNELS[channel](settings).send(subject, body, recipients)


__all__ = ["CHANNELS", "Channel", "Email", "Inbox", "Slack", "Teams", "Webhook", "send", "status"]
