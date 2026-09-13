"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a scenario is given, and the two ways it can lie.

`expect_refused` and `expect_accepted` exist so that a case cannot pass by
accident. Two failures this run has already produced make the point:

- A screen returning **200 with the sign-in form** counted as a page that
  rendered, and eighty-four screens passed without being opened.
- A mutating call returning **403 `csrf_token_invalid`** counted as a
  considered answer, and 238 operations were recorded as exercised without
  being reached.

Both were `status < 500` checks. So a refusal here is asserted **by code**,
never by status class, and an acceptance asserts that no error body came back.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"

Result = Tuple[str, str]


@dataclass
class Ctx:
    """Everything a scenario may reach."""
    ui: Any                      #: browser-shaped: session cookie + CSRF
    api: Any                     #: API-shaped: HTTP Basic, no session
    observer: Any                #: authenticated, almost no permissions
    people: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    made: Dict[str, Any] = field(default_factory=dict)

    def unique(self, stem: str) -> str:
        return f"{stem}-{uuid.uuid4().hex[:8]}"


def code_of(response) -> str:
    """The refusal code, or "" if the body is not a refusal."""
    try:
        body = response.json()
    except Exception:
        return ""
    if isinstance(body, dict):
        if isinstance(body.get("error"), str):
            return body["error"]
        detail = body.get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("error"), str):
            return detail["error"]
        if isinstance(detail, list):
            return "validation_error"
    return ""


def expect_refused(response, *codes: str, status: Optional[int] = None) -> Result:
    """Refused, with one of these codes. The CODE is the assertion."""
    got = code_of(response)
    if not got:
        return FAIL, (f"expected a refusal ({'/'.join(codes)}) and the answer "
                      f"carried no error code: {response.status_code} "
                      f"{response.text[:160]}")
    if codes and got not in codes:
        return FAIL, (f"expected {'/'.join(codes)}, got '{got}' "
                      f"({response.status_code}): {response.text[:160]}")
    if status is not None and response.status_code != status:
        return FAIL, (f"refused '{got}' as expected but with status "
                      f"{response.status_code}, not {status}")
    return PASS, f"refused '{got}' ({response.status_code})"


def expect_accepted(response, *, status: Optional[int] = None) -> Result:
    """Accepted — and carrying no refusal body."""
    if response.status_code >= 400 or code_of(response):
        return FAIL, (f"expected acceptance, got {response.status_code} "
                      f"{response.text[:160]}")
    if status is not None and response.status_code != status:
        return FAIL, (f"accepted but with status {response.status_code}, "
                      f"not {status}")
    return PASS, f"accepted ({response.status_code})"


def expect_absent(response, needle: str) -> Result:
    if needle.lower() in response.text.lower():
        return FAIL, f"the answer still contains {needle!r}"
    return PASS, f"{needle!r} is absent"


#: id -> (title, callable). Populated by the section modules.
REGISTRY: Dict[str, Tuple[str, Callable[[Ctx], Result]]] = {}


def case(case_id: str, title: str):
    def register(fn):
        REGISTRY[case_id] = (title, fn)
        return fn
    return register


def sections() -> List[str]:
    return sorted({cid.rsplit("-", 1)[0] for cid in REGISTRY})
