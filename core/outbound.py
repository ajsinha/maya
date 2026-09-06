"""
MAYA — what the platform is permitted to fetch.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

MAYA makes very few outbound requests: an identity provider's discovery
document and the endpoints it names, and a notification webhook. Each is a URL
the server fetches, and two of them are read out of a document fetched from
somewhere else — `token_endpoint` and `jwks_uri` come from the issuer's own
discovery response.

That is the shape of a server-side request forgery. A misconfigured or
compromised issuer returns `"jwks_uri": "file:///etc/shadow"` and the platform
opens it, because `urllib.request.urlopen` handles `file:` as readily as
`https:`. Nothing here validated the scheme; the fetch was written as though the
URL had come from configuration, and half of it had not.

One function decides, in one place, and it fails closed.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse
from typing import Tuple

from core.log import get_logger, swallowed

logger = get_logger(__name__)

#: The only schemes MAYA will fetch. `http` is admitted for loopback alone, so
#: a developer can run against an identity provider on their own machine
#: without the platform being willing to talk to the network in clear.
PERMITTED_SCHEMES: Tuple[str, ...] = ("https", "http")


class OutboundError(ValueError):
    """A URL the platform will not fetch, and why.

    Named `…Error` rather than `…Refused` because every refusal in this codebase
    is, and `tests/test_refusal_discipline.py` walks for that suffix to check
    each coded refusal is mapped to a status. A refusal the discipline test
    cannot see is one that reaches a caller as a bare 400.
    """

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> dict:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


def _is_loopback(host: str) -> bool:
    """Whether every address this name resolves to is loopback.

    Every address, not the first: a name resolving to both `127.0.0.1` and a
    routable address is not loopback, and treating it as one would admit exactly
    the redirection this exists to refuse. Resolution failure is not loopback
    either — an unresolvable host is not a reason to relax.
    """
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError, ValueError) as exc:
        swallowed(logger, exc, f"resolved '{host}' to decide whether it is loopback",
                  detail="unresolvable, so treated as NOT loopback — failing "
                         "open here would make every typo a permitted "
                         "plain-http fetch")
        return False
    if not addresses:
        return False
    try:
        return all(ipaddress.ip_address(a).is_loopback for a in addresses)
    except ValueError as exc:                             # pragma: no cover
        swallowed(logger, exc, f"parsed the addresses of '{host}'",
                  detail="treated as NOT loopback")
        return False


def permit(url: str, *, what: str = "this URL") -> str:
    """Return the URL, or refuse it.

    Refuses rather than sanitising, for the reason the redirect guard gives: a
    URL somebody had to repair is one nobody understands.
    """
    if not url or not isinstance(url, str):
        raise OutboundError(
            "outbound_url_missing", f"{what} is empty",
            "configure it, or leave the feature off")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in PERMITTED_SCHEMES:
        raise OutboundError(
            "outbound_scheme_refused",
            f"{what} is '{parsed.scheme or 'no'}' and MAYA fetches only "
            f"{' or '.join(PERMITTED_SCHEMES)}",
            "a 'file:' or 'ftp:' URL here would make the platform read its own "
            "host on behalf of whoever supplied the address; use https")
    if not parsed.hostname:
        raise OutboundError(
            "outbound_host_missing", f"{what} names no host",
            "an address without a host is not something that can be fetched")
    if parsed.scheme == "http" and not _is_loopback(parsed.hostname):
        raise OutboundError(
            "outbound_not_encrypted",
            f"{what} is plain http to '{parsed.hostname}', which is not loopback",
            "use https; http is admitted only against the local machine, so a "
            "developer can run an identity provider on their own laptop without "
            "the platform being willing to talk to a network in clear")
    return url
