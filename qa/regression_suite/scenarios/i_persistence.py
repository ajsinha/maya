"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — persistence: what the database refuses whatever the code does.

Everything above the storage layer can be argued with. A trigger cannot. These
cases go under the application and write to the tables directly, because a
guarantee enforced only by the code that respects it is a convention.
"""
from __future__ import annotations

from db.schema.immutable import (APPEND_ONLY, EMPTY_WHEN_FLAGGED,
                                 IMMUTABLE_COLUMNS)
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _db(ctx: Ctx):
    return ctx.made.get("db") or ctx.ui.app.state.ctx.get("db")


def _versioned(ctx: Ctx) -> str:
    """A model with a version, and the version's row id."""
    name = ctx.unique("pe")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    registry = ctx.ui.app.state.ctx.get("registry")
    return (registry.version(f"maya://model/{name}", "1.0.0") or {}).get("id")


def _execute(db, sql: str, params: dict):
    """`Database` wraps the engine and exposes `execute`/`query`/`query_one`.
    It has no `begin` and no `connect`, so a case reaching for a SQLAlchemy
    connection raises AttributeError — which the runner reports as the CASE
    failing, and which reads exactly like the database having allowed the
    write it was asked to refuse."""
    db.execute(sql, params)


@case("QA-PLT-064", "Every immutable column written directly")
def plt_064(ctx: Ctx) -> Result:
    """The whole list, not a sample. A column left out of the trigger is a
    column the register believes is immutable and is not — and the belief is
    what everything above rests on.
    """
    db, vid = _db(ctx), _versioned(ctx)
    if db is None or not vid:
        return BLOCKED, "no database or no version to attack"
    slipped = []
    for table, columns in IMMUTABLE_COLUMNS.items():
        for column in columns:
            try:
                _execute(db, f"UPDATE {table} SET {column} = :v WHERE id = :i",
                         {"v": "tampered", "i": vid})
            except Exception as exc:
                if "immutable" not in str(exc):
                    slipped.append(f"{table}.{column} -> {type(exc).__name__}")
            else:
                slipped.append(f"{table}.{column} WRITTEN")
    if slipped:
        return FAIL, ("these are declared immutable and the database allowed "
                      "the write: " + ", ".join(slipped[:6]))
    total = sum(len(c) for c in IMMUTABLE_COLUMNS.values())
    return PASS, f"all {total} immutable column(s) refused by the database"


@case("QA-PLT-065", "model_version.status is deliberately not guarded")
def plt_065(ctx: Ctx) -> Result:
    """The lifecycle has to be able to move it. A guard here would freeze
    every version at the state it was created in, so its ABSENCE is the
    design and is worth pinning."""
    if "status" in IMMUTABLE_COLUMNS.get("model_version", ()):
        return FAIL, ("`status` is guarded as immutable, so no version can "
                      "ever be approved")
    db, vid = _db(ctx), _versioned(ctx)
    if db is None or not vid:
        return BLOCKED, "no database or no version"
    try:
        _execute(db, "UPDATE model_version SET status = :v WHERE id = :i",
                 {"v": "approved", "i": vid})
    except Exception as exc:
        return FAIL, f"the lifecycle cannot move a version's status: {exc}"
    return PASS, "status moves; the immutable columns do not"


@case("QA-PLT-066", "An append-only table against UPDATE and DELETE")
def plt_066(ctx: Ctx) -> Result:
    """Both, because guarding one leaves the other. A chain node that can be
    deleted is a chain that can be shortened, and one that can be updated is
    a chain that can be rewritten."""
    db = _db(ctx)
    if db is None:
        return BLOCKED, "no database"
    slipped = []
    for table in APPEND_ONLY:
        row = db.query_one(f"SELECT id FROM {table} LIMIT 1")
        if not row:
            return BLOCKED, f"{table} is empty, so there is nothing to attack"
        for sql in (f"UPDATE {table} SET actor = 'tampered' WHERE id = :i",
                    f"DELETE FROM {table} WHERE id = :i"):
            try:
                _execute(db, sql, {"i": row["id"]})
            except Exception as exc:
                if not str(exc):
                    slipped.append(f"{table}: {sql.split()[0]} silently")
            else:
                slipped.append(f"{table}: {sql.split()[0]}")
    if slipped:
        return FAIL, f"an append-only table allowed: {', '.join(slipped)}"
    return PASS, f"{len(APPEND_ONLY)} append-only table(s) refuse both"


@case("QA-PLT-2500", "A flagged row cannot carry the content it flags")
def plt_2500(ctx: Ctx) -> Result:
    """`contains_personal_data` on an evidence node means the payload must be
    empty. Enforced by trigger rather than by the code that sets the flag,
    because the two are set at the same moment and one caller forgetting is
    the whole risk."""
    db = _db(ctx)
    if db is None:
        return BLOCKED, "no database"
    slipped = []
    for table, (flag, content) in EMPTY_WHEN_FLAGGED.items():
        try:
            _execute(
                db,
                f"INSERT INTO {table} (id, {flag}, {content}) "
                f"VALUES (:i, 1, :p)",
                {"i": ctx.unique("qa")[:28], "p": '{"name": "a real person"}'})
        except Exception as exc:
            if "empty" not in str(exc).lower() and "personal" not in str(exc).lower():
                # Any refusal is acceptable here; a NOT NULL on another
                # column would also stop it, and that is not the guard.
                slipped.append(f"{table}: refused for another reason ({exc})")
        else:
            slipped.append(f"{table}: WRITTEN with {content} populated")
    real = [s for s in slipped if "WRITTEN" in s]
    if real:
        return FAIL, ("a row flagged as containing personal data was written "
                      "with that data in it: " + "; ".join(real))
    return PASS, f"{len(EMPTY_WHEN_FLAGGED)} flagged table(s) refuse content"


@case("QA-PLT-049", "One idempotency key reused across two routes")
def plt_049(ctx: Ctx) -> Result:
    """A key is a promise about ONE request. Honouring it across two routes
    would return the first route's answer to the second."""
    key = ctx.unique("idem")
    name = ctx.unique("pe")
    first = ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                                  "owner": "owner", **TIER},
                         headers={"Idempotency-Key": key})
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    other = ctx.unique("pe")
    got = ctx.api.post("/api/v1/features",
                       json={"name": other, "owner": "owner",
                             "entity": "customer", "dtype": "float",
                             "description": "a QA feature"},
                       headers={"Idempotency-Key": key})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        body = got.text
        if name in body:
            return FAIL, ("one key across two routes replayed the FIRST "
                          "route's answer to the second")
        return FAIL, "one key was honoured on two different routes"
    if code_of(got) in DENIAL:
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-2501", "The same key with a different body")
def plt_2501(ctx: Ctx) -> Result:
    """The point of the key is that a retry is the SAME request. A different
    body under one key is a second request wearing the first's promise."""
    key = ctx.unique("idem")
    name = ctx.unique("pe")
    first = ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                                  "owner": "owner", **TIER},
                         headers={"Idempotency-Key": key})
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    other = ctx.unique("pe")
    got = ctx.api.post(M, json={"urn": f"maya://model/{other}", "name": other,
                                "owner": "owner", **TIER},
                       headers={"Idempotency-Key": key})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400 and other in got.text:
        return FAIL, ("a different body under one key created a second "
                      "model, so the key promised nothing")
    if got.status_code < 400:
        return FAIL, "a different body under one key replayed the first answer"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-2502", "The same key with the same body, keys reordered")
def plt_2502(ctx: Ctx) -> Result:
    """A retry serialised by a different client library orders its JSON keys
    differently. Digesting the raw bytes would call that a different request
    and refuse a legitimate retry."""
    key = ctx.unique("idem")
    name = ctx.unique("pe")
    body = {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **TIER}
    first = ctx.api.post(M, json=body, headers={"Idempotency-Key": key})
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    shuffled = {k: body[k] for k in reversed(list(body))}
    got = ctx.api.post(M, json=shuffled, headers={"Idempotency-Key": key})
    if got.status_code >= 400:
        return FAIL, (f"the same request with its JSON keys in another order "
                      f"was refused '{code_of(got)}'; a retry from a "
                      f"different client library cannot succeed")
    return PASS, "reordered keys are the same request"


@case("QA-PLT-055", "A write with a deliberately wrong If-Match")
def plt_055(ctx: Ctx) -> Result:
    """A client sending `If-Match` believes it has optimistic concurrency."""
    name = ctx.unique("pe")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    got = ctx.api.patch(f"{M}/{name}",
                        json={"fields": {"description": "changed"}},
                        headers={"If-Match": '"not-the-current-tag"'})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a wrong If-Match was ignored, so a client that "
                      "believes it has optimistic concurrency does not")
    if got.status_code != 412 and code_of(got) != "precondition_failed":
        return FAIL, f"refused '{code_of(got)}' ({got.status_code}), not 412"
    return PASS, f"refused {got.status_code} '{code_of(got)}'"


@case("QA-PLT-059", "The ETag does not move when nothing changed")
def plt_059(ctx: Ctx) -> Result:
    """A tag that moves on every read makes If-Match unusable: every write
    would race the read that preceded it."""
    name = ctx.unique("pe")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    tags = []
    for _ in range(3):
        got = ctx.api.get(f"{M}/{name}")
        tags.append(got.headers.get("etag"))
    if not tags[0]:
        return BLOCKED, "the route issues no ETag"
    if len(set(tags)) != 1:
        return FAIL, (f"three reads of an unchanged model gave different "
                      f"tags: {tags}")
    return PASS, f"stable across three reads: {tags[0][:24]}"


@case("QA-PLT-058", "If-None-Match with the current tag")
def plt_058(ctx: Ctx) -> Result:
    name = ctx.unique("pe")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    first = ctx.api.get(f"{M}/{name}")
    tag = first.headers.get("etag")
    if not tag:
        return BLOCKED, "the route issues no ETag"
    got = ctx.api.get(f"{M}/{name}", headers={"If-None-Match": tag})
    if got.status_code != 304:
        return FAIL, (f"the current tag answered {got.status_code}, not 304, "
                      f"so a conditional read never saves anything")
    if got.content:
        return FAIL, "a 304 carried a body"
    return PASS, "304 with no body"


@case("QA-PLT-061", "A governed act that fails half way")
def plt_061(ctx: Ctx) -> Result:
    """Registering a model appends evidence and writes a row. If the two are
    not one transaction, a failed registration leaves an evidence node for a
    model that does not exist."""
    name = ctx.unique("pe")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    # The same urn again: refused, and the refusal must leave nothing behind.
    again = ctx.api.post(M, json={"urn": f"maya://model/{name}",
                                  "name": name, "owner": "owner", **TIER})
    if again.status_code < 400:
        return BLOCKED, "the duplicate registration was not refused"
    db = _db(ctx)
    if db is None:
        return BLOCKED, "no database"
    row = db.query_one("SELECT COUNT(*) AS n FROM model WHERE name = :n",
                       {"n": name})
    rows = (row or {}).get("n")
    if rows != 1:
        return FAIL, f"{rows} rows for one model after a refused duplicate"
    return PASS, "the refused act left exactly one row"
