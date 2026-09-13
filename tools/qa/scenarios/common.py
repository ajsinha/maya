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

#: Cases that must not share a database with anything else.
#:
#: A tamper case leaves the chain broken, and every case after it then sees an
#: already-invalid chain and "detects" its own tampering without doing
#: anything. QA-PLT-006 reported that truncation was caught — a better result
#: than the case expected — and it was reading damage a previous case had
#: done. The same shape as section B's malformed posts making twenty-six of
#: section C's cases look broken.
ISOLATED: set = set()


def case(case_id: str, title: str, *, isolated: bool = False):
    def register(fn):
        REGISTRY[case_id] = (title, fn)
        if isolated:
            ISOLATED.add(case_id)
        return fn
    return register


def sections() -> List[str]:
    return sorted({cid.rsplit("-", 1)[0] for cid in REGISTRY})


# --------------------------------------------------------------- sequences
#
# Most hand-written cases are the same shape: perform a short sequence of
# requests and assert what the LAST one does. Writing each as its own function
# means several hundred near-identical functions, and the differences — which
# is the case — get lost in the boilerplate.
#
# So a sequence is data. `{model}` in a path is substituted with the name of
# the model the case registered, so a step can refer to its own subject
# without the table needing to know the generated name.

def _substitute(value, bindings: Dict[str, str]):
    if isinstance(value, str):
        for key, replacement in bindings.items():
            value = value.replace("{" + key + "}", replacement)
        return value
    if isinstance(value, dict):
        return {k: _substitute(v, bindings) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, bindings) for v in value]
    return value


def sequence(case_id: str, title: str, steps: List[tuple],
             expect: tuple, *, setup: Optional[Callable[[Ctx], Dict]] = None,
             client: str = "api"):
    """Register a case that runs `steps` and asserts on the last answer.

    `expect` is `("refused", code, ...)`, `("accepted",)` or
    `("explore",)` — the last for a case whose author could not state the
    expectation in advance and said so. An exploratory case never fails; it
    records what happened, which is the only honest verdict for a question
    nobody has answered yet.
    """
    def run(ctx: Ctx) -> Result:
        bindings = setup(ctx) if setup else {}
        caller = getattr(ctx, client)
        response = None
        for index, step in enumerate(steps):
            method, path = step[0], _substitute(step[1], bindings)
            body = _substitute(step[2], bindings) if len(step) > 2 else None
            params = _substitute(step[3], bindings) if len(step) > 3 else None
            kwargs: Dict[str, Any] = {}
            if body is not None and method in ("POST", "PUT", "PATCH"):
                kwargs["json"] = body
            if params:
                kwargs["params"] = params
            response = caller.request(method, path, **kwargs)
            # Every step but the last is setup. A setup step that fails means
            # the case never reached what it was asking about, and reporting
            # that as a failure of the LAST step would be a lie about which
            # control was exercised.
            if index < len(steps) - 1 and response.status_code >= 500:
                return BLOCKED, (f"setup step {index + 1} ({method} {path}) "
                                 f"answered {response.status_code}")
        if response is None:
            return BLOCKED, "no steps"
        kind = expect[0]
        if kind == "refused":
            return expect_refused(response, *expect[1:])
        if kind == "accepted":
            return expect_accepted(response)
        return PASS, (f"EXPLORATORY — {response.status_code} "
                      f"{response.text[:150]}")

    REGISTRY[case_id] = (title, run)
    return run
