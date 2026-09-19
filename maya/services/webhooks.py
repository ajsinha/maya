"""
Webhooks and the event stream (§18.1): the hook a monitoring or scheduling
system needs, without MAYA growing one.

Delivery is at-least-once. Each POST carries the event as JSON with
``X-Maya-Event``, ``X-Maya-Delivery`` (an idempotency key for the receiver),
``X-Maya-Timestamp`` and ``X-Maya-Signature: sha256=<hmac>`` over
``"<timestamp>.<body>"`` with the webhook's secret, which is shown once at
creation and sealed at rest. A failure retries with exponential backoff and
jitter; after the attempt cap the delivery is dead-lettered with the failure
kept. A webhook URL must be HTTPS, and outside dev must not resolve to a
private, loopback or link-local address — a governance platform that can be
told to POST into its own network is a pivot, not a feature.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import random
import secrets
import socket
import threading
from typing import Any
from urllib.parse import urlparse

import httpx

from maya.core.errors import ConflictError, NotFound, PermissionDenied, ValidationFailed
from maya.observability.metrics import METRICS
from maya.core.clock import utcnow
from maya.security.authz import Principal


def signature(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


class WebhookService:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        s = platform.settings
        self.max_attempts = s.int("observability.webhooks.max_attempts", 8)
        self.timeout = float(s.get("observability.webhooks.timeout_seconds", "5") or 5)
        self.allow_private = s.bool("observability.webhooks.allow_private", False) and s.is_dev
        self.transport: Any = None                 # tests inject a receiver
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        platform.db.on_event = self._wake.set

    # -- administration ---------------------------------------------------------------
    @staticmethod
    def _admin(p: Principal) -> None:
        if not (p.is_admin or "techops" in p.roles):
            raise PermissionDenied("Webhooks and the event stream are for administrators and "
                                   "techops")

    def check_url(self, url: str) -> str:
        parsed = urlparse(url)
        local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if parsed.scheme != "https" and not (local and self.allow_private):
            raise ValidationFailed("A webhook URL must be https://")
        if not parsed.hostname:
            raise ValidationFailed("A webhook URL needs a host")
        if self.allow_private:
            return url
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, None)}
        except socket.gaierror as exc:
            raise ValidationFailed(f"Cannot resolve '{parsed.hostname}'") from exc
        for addr in addresses:
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValidationFailed(f"'{parsed.hostname}' resolves to {addr}, a private or "
                                       "local address; webhooks may not target it")
        return url

    def create(self, p: Principal, *, name: str, url: str, event_types: list[str] | None = None,
               description: str = "") -> dict[str, Any]:
        self._admin(p)
        self.check_url(url)
        secret = "whsec_" + secrets.token_urlsafe(32)
        with self.p.uow(p.username) as uow:
            if uow.repo("webhooks").find_one(name=name):
                raise ConflictError(f"Webhook '{name}' already exists")
            row = uow.repo("webhooks").add({
                "name": name, "url": url, "secret_sealed": self._box().seal(secret),
                "event_types": event_types or [], "description": description})
            uow.audit("webhook.created", object_ref=f"webhook:{name}",
                      detail={"url": url, "event_types": event_types or ["*"]})
        return {**_public(row), "secret": secret, "shown_once": True}

    def list(self, p: Principal) -> list[dict[str, Any]]:
        self._admin(p)
        with self.p.uow() as uow:
            rows = uow.repo("webhooks").list(order_by=["name"])
            for r in rows:
                r["pending"] = uow.repo("webhook_deliveries").count(webhook_id=r["id"],
                                                                    state="pending")
                r["dead"] = uow.repo("webhook_deliveries").count(webhook_id=r["id"], state="dead")
        return [_public(r) for r in rows]

    def delete(self, p: Principal, webhook_id: str) -> None:
        self._admin(p)
        with self.p.uow(p.username) as uow:
            row = uow.repo("webhooks").require(webhook_id)
            uow.repo("webhooks").update(webhook_id, {"active": False})
            uow.repo("webhook_deliveries").delete_where(webhook_id=webhook_id, state="pending")
            uow.audit("webhook.deactivated", object_ref=f"webhook:{row['name']}")

    def deliveries(self, p: Principal, webhook_id: str) -> list[dict[str, Any]]:
        self._admin(p)
        with self.p.uow() as uow:
            uow.repo("webhooks").require(webhook_id)
            return uow.repo("webhook_deliveries").list(webhook_id=webhook_id,
                                                       order_by=["-created_at"], limit=500)

    def ping(self, p: Principal, webhook_id: str) -> dict[str, Any]:
        """Queue a ``maya.ping`` event to one webhook and deliver it now."""
        self._admin(p)
        with self.p.uow(p.username) as uow:
            hook = uow.repo("webhooks").require(webhook_id)
            event = uow.repo("events").add({"at": utcnow(), "type": "maya.ping",
                                            "actor": p.username, "payload": {"ping": True}})
            delivery = uow.repo("webhook_deliveries").add({
                "webhook_id": hook["id"], "event_seq": event["seq"], "state": "pending",
                "next_attempt_at": utcnow()})
        self.deliver_due()
        with self.p.uow() as uow:
            return uow.repo("webhook_deliveries").require(delivery["id"])

    # -- the event stream ---------------------------------------------------------------
    def events(self, p: Principal, *, after: int = 0, limit: int = 500,
               type_prefix: str | None = None) -> list[dict[str, Any]]:
        self._admin(p)
        with self.p.uow() as uow:
            filters: dict[str, Any] = {"seq__gt": after}
            if type_prefix:
                filters["type__prefix"] = type_prefix
            return uow.repo("events").list(order_by=["seq"], limit=min(limit, 5000), **filters)

    def events_page(self, p: Principal, *, type_prefix: str | None = None,
                    page_size: int | None = None, cursor: str | None = None,
                   sort: str | None = None, total: bool = False) -> dict[str, Any]:
        from maya.services.paging import Listing, run_page
        self._admin(p)
        filters = {"type__prefix": type_prefix} if type_prefix else {}
        return run_page(self.p, lambda uow: Listing(
            "events", {"seq": "seq", "-seq": "-seq"}, "seq", filters),
            page_size=page_size, cursor=cursor, sort=sort, total=total)

    # -- delivery -----------------------------------------------------------------------
    def deliver_due(self, limit: int = 100) -> int:
        """Attempt every due delivery once. Returns how many were attempted."""
        with self.p.uow() as uow:
            due = uow.repo("webhook_deliveries").list(state="pending",
                                                      next_attempt_at__le=utcnow(),
                                                      order_by=["next_attempt_at"], limit=limit)
            hooks = {h["id"]: h for h in uow.repo("webhooks").list()}
            events = {e["seq"]: e for e in uow.repo("events").list(
                seq__in=[d["event_seq"] for d in due])} if due else {}
        for d in due:
            self._attempt(d, hooks.get(d["webhook_id"]), events.get(d["event_seq"]))
        return len(due)

    def _attempt(self, d: dict[str, Any], hook: dict[str, Any] | None,
                 event: dict[str, Any] | None) -> None:
        if hook is None or event is None or not hook["active"]:
            self._settle(d, "dead", None, "webhook or event no longer exists")
            return
        body = json.dumps({"id": event["seq"], "type": event["type"],
                           "at": event["at"].isoformat(), "object_type": event["object_type"],
                           "object_ref": event["object_ref"], "actor": event["actor"],
                           "trace_id": event["trace_id"], "payload": event["payload"]},
                          sort_keys=True, default=str).encode()
        stamp = str(int(utcnow().timestamp()))
        headers = {"Content-Type": "application/json", "User-Agent": "MAYA-Webhooks/1",
                   "X-Maya-Event": event["type"], "X-Maya-Delivery": d["id"],
                   "X-Maya-Timestamp": stamp,
                   "X-Maya-Signature": signature(self._box().open(hook["secret_sealed"]), stamp,
                                                 body)}
        try:
            self.check_url(hook["url"])       # DNS may have changed since creation
            with httpx.Client(transport=self.transport, timeout=self.timeout,
                              follow_redirects=False) as client:
                r = client.post(hook["url"], content=body, headers=headers)
            ok, status, error = 200 <= r.status_code < 300, r.status_code, \
                None if 200 <= r.status_code < 300 else f"HTTP {r.status_code}"
        except (httpx.HTTPError, ValidationFailed) as exc:
            ok, status, error = False, None, str(getattr(exc, "message", exc))[:500]
        if ok:
            self._settle(d, "delivered", status, None)
        elif d["attempts"] + 1 >= self.max_attempts:
            self._settle(d, "dead", status, error)
        else:
            delay = min(3600.0, 2 ** (d["attempts"] + 1)) * (0.5 + random.random())
            self._settle(d, "pending", status, error, retry_in=delay)

    def _settle(self, d: dict[str, Any], state: str, status: int | None, error: str | None,
                retry_in: float | None = None) -> None:
        METRICS.inc("maya_webhook_deliveries_total", {"outcome": state})
        with self.p.uow("system") as uow:
            changes: dict[str, Any] = {"state": state, "attempts": d["attempts"] + 1,
                                       "last_status": status, "last_error": error}
            if state == "delivered":
                changes["delivered_at"] = utcnow()
            if retry_in is not None:
                changes["next_attempt_at"] = utcnow() + dt.timedelta(seconds=retry_in)
            uow.repo("webhook_deliveries").update(d["id"], changes)

    def _box(self) -> Any:
        from maya.core.crypto import SecretBox
        return SecretBox(self.p.root / "keys")

    # -- dispatcher thread ----------------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="maya-webhooks", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.deliver_due():
                    self._wake.wait(5.0)
                    self._wake.clear()
            except Exception:  # noqa: BLE001 - the dispatcher never dies on one bad delivery
                self._stop.wait(5.0)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(5)


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != "secret_sealed"}


def deliveries_backlog(uow: Any) -> dict[str, int]:
    return {s: uow.repo("webhook_deliveries").count(state=s) for s in ("pending", "dead")}


__all__ = ["WebhookService", "signature", "NotFound"]
