"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a refusal looks like on this side of the wire.

**A refusal is raised, never returned.** The alternative — a result object a
caller checks — puts the decision in the caller's hands, and a caller who forgets
to check has continued past a governance decision while their code reads as
though it succeeded. Raising means the only way past a refusal is to handle it
deliberately.

The API already answers refusals in one shape: a code that says what was refused,
a detail that says why, and a remediation that says what to do about it. All
three survive the crossing, because the remediation is the half that makes a
refusal usable and it is the half a naive client throws away.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class MayaError(Exception):
    """Base for everything this package raises."""


class Unreachable(MayaError):
    """The platform could not be reached, or did not answer in time.

    Deliberately distinct from `Refused`. "MAYA said no" and "MAYA did not
    answer" call for opposite responses — the first is a decision to act on, the
    second is an operational fault to retry or escalate — and a client that
    collapses them will eventually treat an outage as a governance verdict.
    """


class Refused(MayaError):
    """MAYA refused, and said why and what to do about it."""

    def __init__(self, status: int, code: str, detail: str,
                 remediation: str = "", request_id: str = "",
                 body: Optional[Dict[str, Any]] = None):
        self.status = status
        self.code = code
        self.detail = detail
        self.remediation = remediation
        # Carried so a traceback quotes the identifier the server logged against
        # this call. Without it, "it failed" and "which of the four thousand
        # lines was mine" are separate investigations.
        self.request_id = request_id
        self.body = body or {}
        super().__init__(self._message())

    def _message(self) -> str:
        parts = [f"{self.code}: {self.detail}"]
        if self.remediation:
            parts.append(f"→ {self.remediation}")
        if self.request_id:
            parts.append(f"[request {self.request_id}]")
        return "  ".join(parts)


class NotAuthenticated(Refused):
    """No credentials, or they did not verify."""


class NotPermitted(Refused):
    """Authenticated, and not allowed to do this.

    Its own class because it is the refusal a caller most often wants to catch
    on purpose — a first-line tool that offers an action it turns out the user
    may not take wants to hide the button, not crash.
    """


class NotFound(Refused):
    """No such model, version, warrant, featureset or artifact."""


class Blocked(Refused):
    """The platform understood, and a governance condition stands in the way.

    An open blocking finding, an unapproved version, a sealed record, a quorum
    that has not signed. These are the refusals the platform exists to produce,
    and they are separated from the rest so a caller can report them as
    *governance* rather than as errors — the distinction a model developer needs
    and a generic HTTP client cannot make.
    """


#: HTTP status → the class raised for it. A status this does not name raises
#: `Refused` itself, which is the honest answer: the refusal is real and the
#: SDK has no more specific thing to say about it.
BY_STATUS = {
    401: NotAuthenticated,
    403: NotPermitted,
    404: NotFound,
    409: Blocked,
    410: Blocked,
    423: Blocked,
}


def refusal(status: int, body: Any, request_id: str = "") -> Refused:
    """Build the exception for a refusal response.

    A body that is not the platform's problem shape still produces a usable
    exception rather than a `KeyError`: a proxy, a load balancer or a crash can
    all answer with something else, and the SDK failing to parse an error is a
    worse failure than the error.
    """
    if isinstance(body, dict):
        problem = body.get("detail") if isinstance(body.get("detail"), dict) else body
        code = str(problem.get("error") or f"http_{status}")
        detail = str(problem.get("detail") or problem.get("message") or body)
        remediation = str(problem.get("remediation") or "")
    else:
        code, detail, remediation = f"http_{status}", str(body), ""
    return BY_STATUS.get(status, Refused)(
        status, code, detail, remediation, request_id,
        body if isinstance(body, dict) else {"body": body})
