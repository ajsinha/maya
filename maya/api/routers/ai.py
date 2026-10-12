"""
The AI gateway: model profiles, the default, and the providers on offer (§21.6).

Reading the status needs only a signed-in user; everything that changes something is for an
administrator, and every change is audited.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas_governance as s
from maya.api.deps import Me, Plat, ok
from maya.core.errors import ValidationFailed
from maya.security.authz import Principal

router = APIRouter(tags=["ai"])


@router.get("/ai/status")
def ai_status(me: Principal = Me, plat: Any = Plat) -> Response:
    """Every model profile -- where it came from, where it points, whether it looks usable --
    which one is the default and who chose it, and every provider on offer. Nothing is called."""
    return ok(plat.ai.status(me))


@router.get("/ai/policy")
def ai_policy(me: Principal = Me, plat: Any = Plat) -> Response:
    """Who may use each AI feature, the rate limits, the daily budgets and today's use, and
    what is masked from prompts."""
    return ok(plat.ai.policy())


@router.get("/ai/usage")
def ai_usage(days: int = 7, me: Principal = Me, plat: Any = Plat) -> Response:
    """AI use over the last days, by feature, person and profile, and how many calls the
    policy refused (administrators)."""
    return ok(plat.ai.usage(me, days))


@router.post("/ai/ask")
def ai_ask(body: dict[str, Any], me: Principal = Me, plat: Any = Plat) -> Response:
    """A question in words, answered with rows and the structured query that found them, run
    with the asker's own permissions. Common phrasings are read without a model."""
    return ok(plat.ai_features.ask(me, str(body.get("question") or "")))


@router.get("/ai/vocabulary")
def ai_vocabulary(me: Principal = Me, plat: Any = Plat) -> Response:
    """What a query may name: kinds, fields, operators, states and namespaces."""
    return ok(plat.ai_features.vocabulary(me))


@router.post("/ai/query")
def ai_query(body: dict[str, Any], me: Principal = Me, plat: Any = Plat) -> Response:
    """Run a structured query (the shape /ai/ask returns) as the caller, with no model."""
    return ok({"rows": plat.ai_features.run(me, body)})


@router.post("/ai/explain")
def ai_explain(body: dict[str, Any], me: Principal = Me, plat: Any = Plat) -> Response:
    """An object's record in plain words: kind (feature, model, training_warrant,
    execution_warrant) and key (namespace/name, or the warrant's id). Any figure in the answer
    that is not in the record is named."""
    return ok(plat.ai_features.explain(me, str(body.get("kind")), str(body.get("key"))))


@router.post("/ai/narrate/diff")
def ai_narrate_diff(body: dict[str, Any], me: Principal = Me, plat: Any = Plat) -> Response:
    """What changed between two versions of a model, in words, from the semantic diff."""
    try:
        a, b = int(body["a"]), int(body["b"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationFailed("Name the two versions to compare, as a and b") from exc
    return ok(plat.ai_features.narrate_diff(me, str(body.get("ref") or ""), a, b))


@router.post("/ai/draft/formula")
def ai_draft_formula(body: dict[str, Any], me: Principal = Me, plat: Any = Plat) -> Response:
    """LaTeX and each symbol's role from a description, checked by MAYA's parser. A draft:
    nothing is registered."""
    return ok(plat.ai_features.draft_formula(me, str(body.get("description") or "")))


@router.post("/ai/register-self")
def ai_register_self(body: dict[str, Any], me: Principal = Me, plat: Any = Plat) -> Response:
    """Register MAYA's own AI features as LLM applications in a namespace, with their real
    prompts and starter evaluation sets, so MAYA's assistant is approved on evidence."""
    return ok(plat.ai_features.register_self(me, str(body.get("namespace") or "")))


@router.post("/ai/default")
def ai_set_default(body: s.AiDefaultIn, me: Principal = Me, plat: Any = Plat) -> Response:
    """Make a profile the default, at once and for every process; null returns the choice to
    the configuration."""
    return ok(plat.ai.set_default(me, body.profile))


@router.post("/ai/profiles/{name}/test")
def ai_test_profile(name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """Ask the profile's model one short question: the reply, the time, the tokens, or why not."""
    return ok(plat.ai.test(me, name))


@router.put("/ai/profiles/{name}")
def ai_save_profile(
    name: str, body: dict[str, Any], me: Principal = Me, plat: Any = Plat
) -> Response:
    """Create or replace a profile: provider, model, max_tokens, temperature, options,
    description. Options name a key's environment variable; they never hold a key."""
    return ok(plat.ai.save_profile(me, name, body))


@router.delete("/ai/profiles/{name}")
def ai_delete_profile(name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """Remove a profile saved from the UI; one from the profiles file is edited there."""
    return ok(plat.ai.delete_profile(me, name))
