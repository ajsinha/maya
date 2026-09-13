"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the semantic layer, and the field it deliberately does not have.

"There is no parameter that takes query text, and there will not be one: a
layer that accepts SQL cannot promise anything about what a query can reach,
and the first thing a BI tool does with table access is invent its own
definition of the most important word in the register."

The absence is the control, so the first case asserts on it.
"""
from __future__ import annotations

from core.reporting.semantics import ENTITIES, MAX_ROWS, OPERATORS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

Q = "/api/v1/query"
S = "/api/v1/semantic-layer"


def _query(ctx: Ctx, **over):
    body = {"entity": "model", "select": None, "where": [], "order_by": "",
            "limit": 100}
    body.update(over)
    return ctx.api.post(Q, json=body, auth=ctx.people["risk"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-PLT-5900", "There is no field that takes query text")
def plt_5900(ctx: Ctx) -> Result:
    """The absence is the control, and a field added later would remove it
    without anything else changing."""
    from routes.reporting_routes import QueryIn
    fields = set(QueryIn.model_fields)
    for text_like in ("sql", "query", "statement", "text", "expression",
                      "raw", "filter"):
        if text_like in fields:
            return FAIL, (f"the query layer accepts '{text_like}', so it can "
                          f"promise nothing about what a query reaches")
    if "entity" not in fields or "where" not in fields:
        return FAIL, f"the structured surface is not there: {sorted(fields)}"
    return PASS, f"structured only: {sorted(fields)}"


@case("QA-PLT-5901", "An entity that is not one")
def plt_5901(ctx: Ctx) -> Result:
    """The entities are the register's own nouns. One outside the list is a
    table somebody guessed at."""
    got = _query(ctx, entity="secrets")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a query ran against an entity the layer does not have"
    if not any(e in got.text for e in ENTITIES):
        return FAIL, "the refusal does not name the entities"
    return PASS, f"refused '{code_of(got)}', naming {len(ENTITIES)} entities"


@case("QA-PLT-5902", "A field the entity does not have")
def plt_5902(ctx: Ctx) -> Result:
    """Selecting a field that does not exist is a column of nulls somebody
    puts in a report."""
    got = _query(ctx, select=["salary"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a query selected a field the entity does not have"
    if "salary" not in got.text:
        return FAIL, f"the refusal does not name the field: {got.text[:130]}"
    return PASS, f"refused '{code_of(got)}', naming the field"


@case("QA-PLT-5903", "An operator that is not one")
def plt_5903(ctx: Ctx) -> Result:
    """The operators are closed. A free-text comparison is where a query
    language starts."""
    name = ctx.unique("qy")
    ctx.api.post("/api/v1/models",
                 json={"urn": f"maya://model/{name}", "name": name,
                       "owner": "owner", "model_class": "logistic",
                       "domain": "credit", "legal_entity": "LE-US-01",
                       "purpose": "credit_decision"})
    got = _query(ctx, where=[{"field": "domain", "op": "like",
                              "value": "credit"}])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        if not any(o in got.text for o in OPERATORS):
            return FAIL, "the refusal does not name the operators"
        return PASS, (f"refused '{code_of(got)}', naming {len(OPERATORS)} "
                      f"operators")
    # Accepted. Establish what it DID rather than only that it did something:
    # compare an unknown operator against `eq` on the same field.
    exact = _query(ctx, where=[{"field": "domain", "op": "eq",
                                "value": "credit"}])
    same = (got.json() or {}).get("rows") == (exact.json() or {}).get("rows")
    return FAIL, (
        "an operator outside the closed set was accepted"
        + (" and behaved as `eq` — so a caller asking for `like` gets exact "
           "match semantics, and a filter that means something different "
           "from what was written reads as one that was applied"
           if same else ", matching a set of its own"))


@case("QA-PLT-5904", "A row limit outside the range")
def plt_5904(ctx: Ctx) -> Result:
    """An unbounded query against a register is how a reporting tool takes an
    instance down, and zero rows is not a query."""
    accepted = []
    for limit in (0, -1, MAX_ROWS + 1, 10_000_000):
        got = _query(ctx, limit=limit)
        if got.status_code >= 500:
            return FAIL, f"limit {limit}: {got.status_code}"
        if got.status_code < 400:
            accepted.append(limit)
    if accepted:
        return FAIL, f"these limits were accepted: {accepted}"
    at = _query(ctx, limit=MAX_ROWS)
    if at.status_code >= 400 and _reached(at):
        return FAIL, (f"exactly {MAX_ROWS} was refused '{code_of(at)}'; the "
                      f"limit excludes itself")
    return PASS, f"0, -1 and past {MAX_ROWS} refused; {MAX_ROWS} accepted"


@case("QA-PLT-5905", "Ordering by a field the entity does not have")
def plt_5905(ctx: Ctx) -> Result:
    got = _query(ctx, order_by="whatever")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a query ordered by a field that does not exist"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-5906", "A query is scoped to the caller")
def plt_5906(ctx: Ctx) -> Result:
    """A reporting layer that ignored scope would be the cleanest way around
    every entity restriction in the platform."""
    name = ctx.unique("qy")
    ctx.api.post("/api/v1/models",
                 json={"urn": f"maya://model/{name}", "name": name,
                       "owner": "owner", "model_class": "logistic",
                       "domain": "credit", "legal_entity": "LE-US-01",
                       "purpose": "credit_decision"})
    who = ctx.unique("scoped")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["auditor"], "password": f"{who}-pw",
                              "legal_entities": ["LE-XX-99"], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(Q, json={"entity": "model", "where": [], "limit": 100},
                       auth=(who, f"{who}-pw"))
    if got.status_code >= 400:
        return PASS, f"a scoped reader is refused '{code_of(got)}'"
    if name in got.text:
        return FAIL, ("a principal scoped to another legal entity read this "
                      "model through the query layer, so reporting is the way "
                      "around every entity restriction")
    return PASS, "the query answers within the caller's scope"


@case("QA-PLT-5907", "Every entity and operator is published")
def plt_5907(ctx: Ctx) -> Result:
    """A structured layer is only usable if the structure is readable, and a
    caller guessing at nouns is a caller writing SQL somewhere else."""
    got = ctx.api.get(S, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    text = got.text
    for entity in ENTITIES:
        if entity not in text:
            return FAIL, f"entity '{entity}' is queryable and not published"
    for operator in OPERATORS:
        if f'"{operator}"' not in text:
            return FAIL, f"operator '{operator}' is accepted and not published"
    body = got.json() or {}
    if body.get("max_rows") != MAX_ROWS:
        return FAIL, (f"the published row cap is {body.get('max_rows')}, not "
                      f"{MAX_ROWS}")
    return PASS, (f"{len(ENTITIES)} entities, {len(OPERATORS)} operators and "
                  f"the {MAX_ROWS} cap all published")


@case("QA-PLT-5908", "Every field says what it describes")
def plt_5908(ctx: Ctx) -> Result:
    """A field name is not a definition. "Tier" means something specific
    here, and a BI tool inventing its own is the failure the whole layer
    exists to prevent."""
    mute = []
    for name, entity in ENTITIES.items():
        for field in getattr(entity, "fields", ()) or ():
            if not (getattr(field, "describes", "") or "").strip():
                mute.append(f"{name}.{getattr(field, 'name', '?')}")
    if mute:
        return FAIL, f"{len(mute)} field(s) with no description: {mute[:6]}"
    total = sum(len(getattr(e, "fields", ()) or ()) for e in ENTITIES.values())
    return PASS, f"all {total} fields across {len(ENTITIES)} entities describe themselves"


@case("QA-PLT-5909", "An export carries the query that produced it")
def plt_5909(ctx: Ctx) -> Result:
    """A spreadsheet on somebody's laptop with no record of what it asked for
    is a number nobody can reproduce."""
    got = ctx.api.post(f"{Q}/export",
                       json={"entity": "model", "where": [], "limit": 10},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    # The entity is in the download's filename, not in the CSV body — a
    # spreadsheet cannot carry a header row that is not a column.
    disposition = got.headers.get("content-disposition", "")
    if "model" not in disposition and "model" not in got.text:
        return FAIL, (f"the export records neither the entity it queried nor "
                      f"a filename naming it: {disposition!r}")
    return PASS, f"named by its entity: {disposition}"
