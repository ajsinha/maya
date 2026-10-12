"""
Plain-English pages: ask the estate, explain an object, narrate a change, draft a formula.

Every one is a client of the SDK like every other page, so the gateway's policy, masking and
audit apply, and a refusal is shown in the words the gateway gave.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from maya.core.errors import MayaError
from maya.web.routes.common import action, client, form, page, render

router = APIRouter()

EXAMPLES = (
    "approved models in credit, newest first",
    "black box models",
    "suspended execution warrants",
    "features in eq owned by dana",
    "feature sets in review",
)


@router.get("/ask")
@page
async def ask_page(request: Request) -> Any:
    """Ask MAYA in plain words; the answer is rows and the query that found them."""
    question = (request.query_params.get("q") or "").strip()
    answer, error = None, None
    async with client(request) as sdk:
        vocabulary = await sdk.ai.vocabulary()
        if question:
            try:
                answer = await sdk.ai.ask(question)
            except MayaError as exc:
                error = exc
    return await render(
        request,
        "ai/ask.html",
        {
            "q": question,
            "answer": answer,
            "error": error,
            "examples": EXAMPLES,
            "vocabulary": vocabulary,
        },
    )


@router.post("/ask/query")
@action
async def ask_query(request: Request) -> Any:
    """Run an edited query -- the one MAYA showed, changed by hand -- with no model."""
    import json

    data = await form(request)
    text = data.get("query", "")
    answer, error = None, None
    async with client(request) as sdk:
        vocabulary = await sdk.ai.vocabulary()
        try:
            query = json.loads(text)
            out = await sdk.ai.query(query)
            answer = {
                "how": "edited",
                "query": query,
                "rows": out["rows"],
                "summary": f"{len(out['rows'])} row(s) match",
                "model_attempts": 0,
                "read_as": None,
            }
        except (ValueError, MayaError) as exc:
            error = exc if isinstance(exc, MayaError) else MayaError(f"Not JSON: {exc}")
    return await render(
        request,
        "ai/ask.html",
        {"q": "", "answer": answer, "error": error, "examples": EXAMPLES, "vocabulary": vocabulary},
    )


@router.post("/ai/explain")
@action
async def explain(request: Request) -> Any:
    """An object's record in plain words, with any figure the model added named."""
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.ai.explain(data.get("kind", ""), data.get("key", ""))
    return await render(
        request,
        "ai/explain.html",
        {"out": out, "back": data.get("back") or "/", "title": data.get("title") or "Explanation"},
    )


@router.post("/models/{namespace}/{name}/narrate")
@action
async def narrate_diff(request: Request, namespace: str, name: str) -> Any:
    """What changed between two versions of a model, in words."""
    data = await form(request)
    a, b = int(data.get("a") or 1), int(data.get("b") or 2)
    async with client(request) as sdk:
        out = await sdk.ai.narrate_diff(f"{namespace}/{name}", a, b)
    return await render(
        request,
        "ai/explain.html",
        {
            "out": out,
            "back": f"/models/{namespace}/{name}/diff?a={a}&b={b}",
            "title": f"What changed from v{a} to v{b}",
        },
    )


@router.post("/models/kernel/draft")
@action
async def kernel_draft(request: Request) -> Any:
    """A formula drafted from words, checked by the parser, opened in the kernel designer."""
    from maya.web.kernel_templates import GROUPS, for_ui

    data = await form(request)
    description = data.get("description", "")
    draft, error = None, None
    async with client(request) as sdk:
        try:
            draft = await sdk.ai.draft_formula(description)
        except MayaError as exc:
            error = exc
    if draft:
        draft["roles_text"] = "\n".join(f"{k}: {v}" for k, v in draft["roles"].items())
    return await render(
        request,
        "models/kernel.html",
        {
            "templates": for_ui(),
            "groups": GROUPS,
            "draft": draft,
            "draft_error": error,
            "description": description,
        },
    )
