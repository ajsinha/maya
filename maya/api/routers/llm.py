"""
LLM applications: versions sealed by definition hash, evaluation sets, evaluation runs
(recorded or live), and approval on evidence.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas_governance as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["llm"])


@router.get("/llm/apps")
def apps(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.llm.list_apps(me))


@router.post("/llm/apps", status_code=201)
def create_app(body: s.LlmAppIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.llm.create_app(me, **body.model_dump()), 201)


@router.get("/llm/apps/{namespace}/{name}")
def app(namespace: str, name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """The application with its versions, evaluation sets and runs."""
    return ok(plat.llm.get_app(me, f"{namespace}/{name}"))


@router.put("/llm/apps/{namespace}/{name}/draft")
def save_version(
    namespace: str, name: str, body: s.LlmVersionIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    """Edit the draft version, or open a new one when the latest is no longer a draft."""
    return ok(plat.llm.save_version(me, f"{namespace}/{name}", **body.model_dump()))


@router.put("/llm/apps/{namespace}/{name}/eval-sets")
def save_eval_set(
    namespace: str, name: str, body: s.LlmEvalSetIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.llm.save_eval_set(me, f"{namespace}/{name}", **body.model_dump()))


@router.post("/llm/apps/{namespace}/{name}/versions/{version_no}/runs", status_code=201)
def run_eval(
    namespace: str,
    name: str,
    version_no: int,
    body: s.LlmRunIn,
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    """Score a version: ``responses`` for a recorded run, none for a live one."""
    return ok(
        plat.llm.run_eval(
            me, f"{namespace}/{name}", version_no, body.eval_set, responses=body.responses
        ),
        201,
    )


@router.post("/llm/apps/{namespace}/{name}/versions/{version_no}/submit")
def submit(
    namespace: str, name: str, version_no: int, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.llm.submit(me, f"{namespace}/{name}", version_no))


@router.post("/llm/apps/{namespace}/{name}/versions/{version_no}/decision")
def decide(
    namespace: str,
    name: str,
    version_no: int,
    body: s.LlmDecisionIn,
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    return ok(plat.llm.decide(me, f"{namespace}/{name}", version_no, body.decision, body.note))
