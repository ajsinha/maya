"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Where a notification goes.

Three channels, and none of them is a dependency. The log channel is always
available and is the honest default for an instance with nowhere to send; the
webhook channel uses the standard library; the email channel uses ``smtplib``,
which is also standard. Adding a notification path should never be the reason a
deployment needs another package.

**A channel that cannot deliver says so.** It does not raise into the caller and
it does not fail silently: it returns a failure the service records, because
silence about a failed send is how somebody concludes they were never told.
"""
from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any, Dict, Optional, Tuple

from core.log import get_logger, swallowed
from core.notify.common import EMAIL, LOG, WEBHOOK

logger = get_logger(__name__)

TIMEOUT_SECONDS = 10.0


class LogChannel:
    """Writes the digest to the platform log. Always available."""

    key = LOG

    def available(self) -> Optional[str]:
        return None

    def send(self, to: str, subject: str,
             body: Dict[str, Any]) -> Tuple[bool, str]:
        logger.info("notification for %s — %s: %s items (%s)",
                    to, subject, body.get("count", 0),
                    ", ".join(body.get("headlines") or []) or "no detail")
        return True, "written to the platform log"


class WebhookChannel:
    """Posts the digest as JSON to a configured URL."""

    key = WEBHOOK

    def __init__(self, url: Optional[str] = None, timeout: float = TIMEOUT_SECONDS):
        self.url, self.timeout = url, timeout

    def available(self) -> Optional[str]:
        if not self.url:
            return ("no webhook url is configured; set "
                    "notifications.webhook.url")
        return None

    def send(self, to: str, subject: str,
             body: Dict[str, Any]) -> Tuple[bool, str]:
        if (why := self.available()):
            return False, why
        payload = json.dumps({"to": to, "subject": subject, **body}).encode()
        request = urllib.request.Request(
            self.url, data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return True, f"posted, {response.status}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # Recorded rather than raised: one unreachable webhook must not stop
            # everybody else being told, and a delivery nobody knows failed is
            # worse than one that visibly did.
            swallowed(logger, exc, f"posted a notification to {self.url}",
                      "recorded as a failed delivery", level=30)
            return False, f"the webhook did not accept it: {exc}"


class EmailChannel:
    """Sends the digest through a configured SMTP relay."""

    key = EMAIL

    def __init__(self, host: Optional[str] = None, port: int = 25,
                 sender: str = "maya@localhost",
                 username: Optional[str] = None, password: Optional[str] = None,
                 use_tls: bool = False, timeout: float = TIMEOUT_SECONDS):
        self.host, self.port, self.sender = host, port, sender
        self.username, self.password = username, password
        self.use_tls, self.timeout = use_tls, timeout

    def available(self) -> Optional[str]:
        if not self.host:
            return "no smtp host is configured; set notifications.email.host"
        return None

    def send(self, to: str, subject: str,
             body: Dict[str, Any]) -> Tuple[bool, str]:
        if (why := self.available()):
            return False, why
        if "@" not in (to or ""):
            return False, (f"'{to}' is not an address; a principal with no email "
                           f"cannot be reached this way")
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.sender, to, subject
        message.set_content(_plain(body))
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password or "")
                smtp.send_message(message)
            return True, "sent"
        except (smtplib.SMTPException, OSError) as exc:
            swallowed(logger, exc, f"sent a notification to {to}",
                      "recorded as a failed delivery", level=30)
            return False, f"the relay did not accept it: {exc}"


def _plain(body: Dict[str, Any]) -> str:
    """The digest as text somebody can read without a client that renders HTML."""
    lines = [body.get("summary", ""), ""]
    for item in body.get("items") or []:
        marker = {"overdue": "OVERDUE", "due": "due"}.get(item.get("urgency"), "")
        lines.append(f"  [{marker or 'open'}] {item.get('model')} — "
                     f"{item.get('title')}")
        if item.get("detail"):
            lines.append(f"           {item['detail']}")
    if body.get("escalated"):
        lines += ["", "Escalated to you because it has been overdue and unactioned:"]
        for item in body["escalated"]:
            lines.append(f"  {item.get('model')} — {item.get('title')}")
    lines += ["", body.get("footer", "")]
    return "\n".join(lines)


def build(config) -> Dict[str, Any]:
    """The channels this instance offers, from configuration.

    The log channel is always present. Nothing else is enabled by default,
    because an instance that quietly needed an SMTP relay to work would fail in
    a way nobody could diagnose from the outside.
    """
    channels: Dict[str, Any] = {LOG: LogChannel()}
    if config is None:
        return channels
    channels[WEBHOOK] = WebhookChannel(config.get("notifications.webhook.url"))
    channels[EMAIL] = EmailChannel(
        config.get("notifications.email.host"),
        config.get_int("notifications.email.port", 25),
        config.get("notifications.email.sender", "maya@localhost"),
        config.get("notifications.email.username"),
        config.get("notifications.email.password"),
        config.get_bool("notifications.email.use_tls", False))
    return channels
