"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Getting bytes to the platform and back.

**Standard library only.** Every asset in this repository is vendored for one
reason: a governance system that cannot be deployed air-gapped is one somebody
works around. An SDK that pulls a dependency tree is the same problem moved to
the client, and it is the client that lives inside somebody else's build
pipeline and somebody else's approval process for third-party packages.

**HTTP Basic, never a session cookie.** A cookie is *ambient* — the browser
sends it whether or not the page that triggered the request came from us — which
is exactly why a mutating call under one needs a CSRF token. A credential a
caller has to present is not ambient, so this needs no token, and that is a
property of the design rather than an exemption from it.

The transport is a seam. The default speaks HTTP; a test speaks to the
application in-process through the same interface, which is what makes the SDK
testable against the real routes rather than against a mock of them.
"""
from __future__ import annotations

import base64
import json as jsonlib
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from maya_sdk.errors import Unreachable

REQUEST_HEADER = "X-Request-ID"

#: Retried, because repeating them cannot change anything. `POST` is absent on
#: purpose: a create that timed out may well have succeeded, and retrying it
#: registers the model twice or records two parameter sets. An SDK that quietly
#: duplicates a governance act is worse than one that fails loudly.
IDEMPOTENT = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})

RETRIES = 3
BACKOFF_SECONDS = 0.25
TIMEOUT_SECONDS = 30.0


@dataclass
class Response:
    """What a transport returns. Deliberately the shape `httpx` already has, so
    a test client can be passed straight in without an adapter."""

    status_code: int
    content: bytes = b""
    headers: Dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return jsonlib.loads(self.content or b"null")

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")


class HttpTransport:
    """urllib, with credentials, a timeout and a bounded retry.

    Two ways in, and a service should prefer the second. **Basic** names a
    person and carries every permission they hold. An **API key** names a
    credential: it expires, it can be narrowed to a subset of what its principal
    holds, and it can be revoked without touching the account — which is what
    makes rotating one an ordinary Tuesday rather than an outage.
    """

    def __init__(self, base_url: str, username: str = "", password: str = "",
                 timeout: float = TIMEOUT_SECONDS, retries: int = RETRIES,
                 verify_tls: bool = True, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.verify_tls = verify_tls
        if api_key:
            # `Bearer`, because that is what an HTTP client library defaults to
            # and what an intermediary expects to see; MAYA accepts `X-API-Key`
            # as well, for the curl line somebody typed.
            self._authorization = f"Bearer {api_key}"
        elif username or password:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._authorization = f"Basic {token}"
        else:
            raise ValueError(
                "a MAYA client needs a way in: a username and password, or an "
                "api_key. Constructing one with neither would fail on the "
                "first call with a 401 that names nothing")

    def request(self, method: str, path: str, *, json: Any = None,
                content: Optional[bytes] = None,
                params: Optional[Dict[str, Any]] = None,
                headers: Optional[Dict[str, str]] = None) -> Response:
        url = self.base_url + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)

        body = content
        sending = dict(headers or {})
        sending["Authorization"] = self._authorization
        if json is not None:
            body = jsonlib.dumps(json).encode()
            sending.setdefault("Content-Type", "application/json")
        elif content is not None:
            sending.setdefault("Content-Type", "application/octet-stream")

        attempts = self.retries if method.upper() in IDEMPOTENT else 1
        last: Optional[BaseException] = None
        for attempt in range(attempts):
            try:
                return self._once(method, url, body, sending)
            except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
                # Never swallowed: the caller is told what could not be reached
                # and how many times it was tried, because "it did not work" and
                # "it did not work three times over four seconds" are different
                # facts to an operator.
                last = exc
                if attempt + 1 < attempts:
                    time.sleep(BACKOFF_SECONDS * (2 ** attempt))
        raise Unreachable(
            f"{method} {url} did not answer after {attempts} attempt(s): {last}"
        ) from last

    def _once(self, method: str, url: str, body: Optional[bytes],
              headers: Dict[str, str]) -> Response:
        request = urllib.request.Request(url, data=body, method=method.upper())
        for key, value in headers.items():
            request.add_header(key, value)
        context = None
        if not self.verify_tls:
            import ssl
            # Offered for a self-signed internal certificate and nothing else.
            # It is a named argument rather than a default so that turning
            # verification off is a decision somebody wrote down.
            context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout,
                                        context=context) as answer:
                return Response(answer.status, answer.read(),
                                {k.lower(): v for k, v in answer.headers.items()})
        except urllib.error.HTTPError as exc:
            # A refusal is a real answer, not a transport failure. urllib raises
            # for any 4xx or 5xx, so this is where the two are told apart — the
            # body carries the code, the detail and the remediation, and losing
            # it here would leave the caller with a status number.
            return Response(exc.code, exc.read(),
                            {k.lower(): v for k, v in (exc.headers or {}).items()})


def new_request_id() -> str:
    """A correlation id for one call.

    Minted here rather than left to the server so the identifier exists before
    the request does — which is what lets a client log "I am about to do X as
    id Y" and still have the id if the call never arrives.
    """
    return secrets.token_hex(8)
