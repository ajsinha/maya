"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the edges of the persistence conventions.

Four middlewares wrap every request, and the ORDER they were registered in is
a design decision that shows up in the answers. Outermost to innermost:
`request_context`, `idempotent_replay`, `entity_tags`, `narrow_and_age`. So a
replay short-circuits before anything can tag it, and a projection is narrowed
before the tag is computed over it. Both are consequences somebody has to have
meant; this section is where they are read back.

The idempotency key is the other half. **Only a success is kept** — a recorded
refusal makes a client's retry replay that refusal forever, and the key becomes
a tombstone for an act that never happened. What follows from that is the
subject of most of these cases: a 500, a stale claim, a retention window, and
what a caller can do with a key they never finish using.
"""
from __future__ import annotations

import time

from core.concurrency.idempotency import (HEADER, REPLAYED, RETENTION_HOURS,
                                          STALE_MINUTES)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _spec(ctx: Ctx, **over) -> dict:
    name = ctx.unique("pe")
    body = {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **SHAPE}
    body.update(over)
    return body


def _store(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("idempotency")


def _registered(ctx: Ctx) -> str:
    body = _spec(ctx)
    ctx.api.post(M, json=body, auth=ctx.people["owner"])
    return body["urn"]


# ------------------------------------------------------------ idempotency keys
@case("QA-PLT-046", "A key whose first attempt 500'd, retried")
def plt_046(ctx: Ctx) -> Result:
    """The retry runs. A platform that cannot distinguish *partly done* from
    *not done* must re-run, because every act has its own refusals in front
    of it — and a key that recorded the crash would turn one failure into a
    permanent inability to retry the very act that crashed."""
    store = _store(ctx)
    if store is None:
        return BLOCKED, "no idempotency store is wired"
    body = _spec(ctx)
    key = ctx.unique("key")
    registry = ctx.ui.app.state.ctx["registry"]
    real = type(registry).register

    def explode(self, *a, **k):
        raise RuntimeError("the disk filled up half way through")

    type(registry).register = explode
    try:
        crashed = ctx.api.post(M, json=body, headers={HEADER: key},
                               auth=ctx.people["owner"])
    finally:
        type(registry).register = real
    if crashed.status_code < 500:
        return BLOCKED, (f"the forced failure answered {crashed.status_code} "
                         f"rather than a 500")
    held = store.repo.one(idempotency_key=key)
    if held is not None:
        return FAIL, (f"the key survives the crash in state "
                      f"'{held['state']}', so the retry of the act that "
                      f"crashed is refused forever")
    retried = ctx.api.post(M, json=body, headers={HEADER: key},
                           auth=ctx.people["owner"])
    if retried.status_code >= 400:
        return FAIL, (f"the retry was refused '{code_of(retried) or ''}' "
                      f"{retried.status_code}: {retried.text[:140]}")
    if retried.headers.get(REPLAYED):
        return FAIL, "the retry replayed the crash rather than running"
    if (retried.json() or {}).get("urn") != body["urn"]:
        return FAIL, "the retry answered something else"
    return PASS, ("the key is released on the way out of a 500 and the retry "
                  "really runs")


@case("QA-PLT-050", "A key replayed after the retention window")
def plt_050(ctx: Ctx) -> Result:
    """Stated in advance rather than discovered: the sweep drops records
    older than the window, so a key replayed after it is a real re-run. A key
    that silently stops being a key is worse than one that never was, because
    by then the client has stopped checking."""
    store = _store(ctx)
    if store is None:
        return BLOCKED, "no idempotency store is wired"
    body = _spec(ctx)
    key = ctx.unique("key")
    first = ctx.api.post(M, json=body, headers={HEADER: key},
                         auth=ctx.people["owner"])
    if first.status_code >= 400:
        return BLOCKED, f"the first attempt failed: {first.text[:150]}"
    row = store.repo.one(idempotency_key=key)
    if row is None:
        return BLOCKED, "the key was not kept"
    replayed = ctx.api.post(M, json=body, headers={HEADER: key},
                            auth=ctx.people["owner"])
    if not replayed.headers.get(REPLAYED):
        return BLOCKED, "the key is not replaying before the window is aged"
    aged = time.time() - (RETENTION_HOURS + 1) * 3600.0
    store.repo.set({"started_at": aged}, id=row["id"])
    swept = store.sweep()
    if not swept.get("dropped"):
        return FAIL, (f"a record {RETENTION_HOURS + 1:.0f} hours old survived "
                      f"the sweep: {swept.get('detail')}")
    after = ctx.api.post(M, json=body, headers={HEADER: key},
                         auth=ctx.people["owner"])
    if after.headers.get(REPLAYED):
        return FAIL, "a swept key still replayed"
    if after.status_code < 400:
        return FAIL, (f"the re-run registered {body['urn']} a second time, so "
                      f"the register now holds two models the client believes "
                      f"is one")
    if code_of(after) != "registry_refused":
        return FAIL, (f"the re-run was refused '{code_of(after)}' rather than "
                      f"by the act's own guard")
    return PASS, (f"past {RETENTION_HOURS:.0f} hours the key is gone and the "
                  f"act runs again — refused here by the register's own "
                  f"duplicate-URN guard, which is the point: every act has its "
                  f"own refusals in front of it")


@case("QA-PLT-086", "Two anonymous callers choosing the same idempotency key")
def plt_086(ctx: Ctx) -> Result:
    """The scope is a digest of what the caller PRESENTED, because the
    middleware runs before authentication. Two callers presenting nothing
    present the same thing — so the question is whether an unauthenticated
    request can leave a key behind that a different anonymous caller then
    collides with, or worse is handed the answer to."""
    store = _store(ctx)
    if store is None:
        return BLOCKED, "no idempotency store is wired"
    from fastapi.testclient import TestClient
    anon = TestClient(ctx.ui.app, raise_server_exceptions=False)
    key = ctx.unique("key")
    first = anon.post(M, json=_spec(ctx), headers={HEADER: key})
    if first.status_code != 401:
        return BLOCKED, (f"an unauthenticated POST answered "
                         f"{first.status_code} rather than 401")
    held = store.repo.one(idempotency_key=key)
    if held is not None:
        return FAIL, (f"a refused unauthenticated request left the key in "
                      f"state '{held['state']}', so one anonymous caller can "
                      f"poison a key for every other")
    second = anon.post(M, json=_spec(ctx), headers={HEADER: key})
    if second.headers.get(REPLAYED):
        return FAIL, ("a second anonymous caller was handed the first's "
                      "answer under a shared scope")
    if second.status_code != 401:
        return FAIL, (f"the second anonymous request answered "
                      f"{second.status_code}: {second.text[:140]}")
    return PASS, ("both refused at the door and the key is released each "
                  "time, so the shared anonymous scope carries nothing")


@case("QA-PLT-087", "An in-flight key held past the stale window")
def plt_087(ctx: Ctx) -> Result:
    """The work re-runs, which is right — a process killed mid-request must
    not poison a key forever. The question the case is really asking is what
    that costs: the stale release RESETS `started_at`, and the retention
    sweep reads the same column."""
    store = _store(ctx)
    if store is None:
        return BLOCKED, "no idempotency store is wired"
    key, scope = ctx.unique("key"), "qa-scope"
    claimed = store.claim(key, scope, "POST", "/api/v1/models", b'{"a":1}')
    if claimed is not None:
        return BLOCKED, "the fresh key did not claim"
    row = store.repo.one(idempotency_key=key, principal=scope)
    store.repo.set({"started_at": time.time() - (STALE_MINUTES + 1) * 60.0},
                   id=row["id"])
    again = store.claim(key, scope, "POST", "/api/v1/models", b'{"a":1}')
    if again is not None:
        return FAIL, "a stale claim replayed rather than re-running"
    refreshed = store.repo.one(idempotency_key=key, principal=scope)
    if refreshed["started_at"] <= row["started_at"]:
        return FAIL, "the stale release did not re-claim the key"
    # Ten abandonments, each past the stale window, then the 24-hour sweep.
    for _ in range(10):
        current = store.repo.one(idempotency_key=key, principal=scope)
        store.repo.set(
            {"started_at": time.time() - (STALE_MINUTES + 1) * 60.0},
            id=current["id"])
        store.claim(key, scope, "POST", "/api/v1/models", b'{"a":1}')
    swept = store.sweep()
    still = store.repo.one(idempotency_key=key, principal=scope)
    if still is None:
        return PASS, (f"the work re-runs after {STALE_MINUTES:.0f} minutes and "
                      f"the {RETENTION_HOURS:.0f}-hour sweep still reaches the "
                      f"key: {swept.get('detail')}")
    age_hours = (time.time() - still["started_at"]) / 3600.0
    return FAIL, (
        f"a caller who abandons a request every {STALE_MINUTES:.0f} minutes "
        f"keeps the key alive indefinitely: eleven abandonments later it is "
        f"{age_hours:.2f} hours old by `started_at` and the "
        f"{RETENTION_HOURS:.0f}-hour sweep does not reach it. The stale "
        f"release writes `started_at = now`, and the sweep reads `started_at` "
        f"— so the column that means *when this attempt began* is also the "
        f"column that means *how long we have kept this record*, and "
        f"refreshing the first silently extends the second. An unauthenticated "
        f"caller shares one scope, so the row is reachable without an account")


# ---------------------------------------------------------------- ETags, again
@case("QA-PLT-088", "A replayed response and its ETag")
def plt_088(ctx: Ctx) -> Result:
    """`idempotent_replay` is registered AFTER `entity_tags`, which puts it
    outside: a replay returns from the store and never passes through the
    tagging middleware. A client that reads a tag on the original and none on
    the retry cannot use conditional requests across a retry, which is
    exactly when it most wants to."""
    key = ctx.unique("key")
    body = _spec(ctx)
    first = ctx.api.post(M, json=body, headers={HEADER: key},
                         auth=ctx.people["owner"])
    if first.status_code >= 400:
        return BLOCKED, f"the first attempt failed: {first.text[:150]}"
    second = ctx.api.post(M, json=body, headers={HEADER: key},
                          auth=ctx.people["owner"])
    if not second.headers.get(REPLAYED):
        return BLOCKED, "the second attempt did not replay"
    if first.headers.get("etag") is None:
        return PASS, ("neither the original nor the replay carries a tag on "
                      "this path, so the two agree")
    if second.headers.get("etag") == first.headers.get("etag"):
        return PASS, "the replay carries the tag the original did"
    return FAIL, (
        f"the original carries etag {first.headers['etag']} and the replay "
        f"carries {second.headers.get('etag')!r}. `idempotent_replay` is "
        f"registered after `entity_tags` and is therefore outside it, so a "
        f"replayed body is returned from the store without ever reaching the "
        f"tagging middleware — a retry, which is when a client most wants a "
        f"conditional request, is the one response it cannot make one from")


PROJECTABLE = ("/api/v1/models", "/api/v1/features", "/api/v1/featuresets",
               "/api/v1/warrants", "/api/v1/principals", "/api/v1/roles",
               "/api/v1/open-findings", "/api/v1/legal-holds",
               "/api/v1/campaigns", "/api/v1/api-keys",
               "/api/v1/subscriptions", "/api/v1/finding-roots")


@case("QA-PLT-089", "The same path with and without `?fields=`")
def plt_089(ctx: Ctx) -> Result:
    """Two tags for one resource, and the second describes a body the caller
    cannot have wanted. `project()` narrows the `rows` of a paged answer and
    narrows a bare list; every other shape falls through to narrowing the
    TOP-LEVEL dict — whose keys are `models`, `count`, `detail`, never a
    field name. So the rows are discarded, `detail` survives because it is in
    ALWAYS_KEPT, and the surviving sentence describes a listing that was
    never sent."""
    from core.http.conventions import ALWAYS_KEPT
    _registered(ctx)
    emptied, kept = [], []
    misleading = ""
    for path in PROJECTABLE:
        whole = ctx.api.get(path, auth=ctx.people["risk"])
        thin = ctx.api.get(f"{path}?fields=urn,name", auth=ctx.people["risk"])
        if whole.status_code >= 400 or thin.status_code >= 400:
            continue
        try:
            full, narrow = whole.json(), thin.json()
        except ValueError:
            continue
        if not isinstance(full, dict) or not isinstance(narrow, dict):
            continue
        rows = [k for k, v in full.items() if isinstance(v, list)]
        if not rows:
            continue
        if any(narrow.get(k) for k in rows):
            kept.append(path)
            continue
        emptied.append(path)
        if not misleading and narrow.get("detail"):
            misleading = f"{path} → {narrow['detail'][:70]}"
    if not emptied:
        return PASS, (f"{len(kept)} listing(s) keep their rows under "
                      f"`?fields=`")
    whole = ctx.api.get(M, auth=ctx.people["risk"])
    thin = ctx.api.get(f"{M}?fields=urn,tier", auth=ctx.people["risk"])
    tags = (whole.headers.get("etag"), thin.headers.get("etag"))
    return FAIL, (
        f"`?fields=` discards the rows of {len(emptied)} of "
        f"{len(emptied) + len(kept)} listings sampled, and keeps none: "
        f"{emptied[:6]}{' …' if len(emptied) > 6 else ''}. `project()` "
        f"narrows `payload['rows']` or a bare list; exactly ONE route in the "
        f"API answers `rows` (`conventions.page` has a single caller), so "
        f"every other listing falls through to `_narrow` on the top-level "
        f"dict and loses everything except the {len(ALWAYS_KEPT)} keys in "
        f"ALWAYS_KEPT. `detail` is one of them, so the answer is a 200 "
        f"carrying a sentence about rows it did not send — {misleading!r}. "
        f"The two ETags ({tags[0]} against {tags[1]}) are the symptom: the "
        f"second tags an almost-empty object")


@case("QA-PLT-090", "The precondition check re-dispatches a synthetic GET")
def plt_090(ctx: Ctx) -> Result:
    """`If-Match` is evaluated by asking the same path for its current
    representation, which means dispatching a GET. A write that silently
    performs a read of itself doubles the cost of every guarded write, and
    the second request is invisible unless somebody counts."""
    urn = _registered(ctx)
    path = f"{M}/{urn}"
    read = ctx.api.get(path, auth=ctx.people["risk"])
    if read.status_code >= 400 or not read.headers.get("etag"):
        return BLOCKED, f"no tag to precondition on: {read.status_code}"
    seen = {"n": 0}
    app = ctx.ui.app
    real = app.router.__class__.__call__

    async def counting(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("method") == "GET" \
                and scope.get("path") == path:
            seen["n"] += 1
        return await real(self, scope, receive, send)

    app.router.__class__.__call__ = counting
    try:
        ctx.api.put(path, json={"description": "changed under a precondition"},
                    headers={"If-Match": read.headers["etag"]},
                    auth=ctx.people["owner"])
    finally:
        app.router.__class__.__call__ = real
    if seen["n"] == 0:
        return PASS, ("the precondition is evaluated without dispatching a "
                      "second request through the router")
    return FAIL, (
        f"one guarded write dispatched {seen['n']} GET(s) to its own path "
        f"through the router. The precondition is real and this is what it "
        f"costs: every `If-Match` write is two trips through routing, "
        f"authorisation and the service layer, and only one of them is in the "
        f"caller's request")


@case("QA-PLT-091", "A JSON response that will not parse gets no ETag")
def plt_091(ctx: Ctx) -> Result:
    """Served without a tag rather than with a wrong one — a tag over bytes
    nobody can compare semantically would be a claim the middleware does not
    check. And a warning, because a route declaring JSON and emitting
    something else is a defect somewhere else that must not be silent."""
    import logging
    from starlette.responses import Response as Raw
    app = ctx.ui.app
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    path = f"/api/v1/qa-unparseable-{int(time.time() * 1000)}"

    @app.get(path)
    def unparseable():
        return Raw(content=b"{not json at all", media_type="application/json")

    handler = Catch()
    root = logging.getLogger()
    root.addHandler(handler)
    was = root.level
    root.setLevel(logging.WARNING)
    try:
        got = ctx.api.get(path, auth=ctx.people["risk"])
    finally:
        root.removeHandler(handler)
        root.setLevel(was)
    if got.status_code != 200:
        return BLOCKED, f"the probe route answered {got.status_code}"
    if got.headers.get("etag"):
        return FAIL, (f"an unparseable body was tagged {got.headers['etag']} — "
                      f"a digest over bytes, offered as a semantic comparison")
    if got.content != b"{not json at all":
        return FAIL, "the body was altered on the way out"
    said = [m for m in records if "does not parse" in m]
    if not said:
        return FAIL, ("no ETag and no warning: a route declaring JSON and "
                      "emitting something else is a defect that leaves no "
                      "trace, and the client's conditional requests silently "
                      "stop working")
    return PASS, f"no tag, and a warning: {said[0][:120]}"


# ------------------------------------------------- triggers, scope, deletion
@case("QA-PLT-067", "A database role that cannot create triggers")
def plt_067(ctx: Ctx) -> Result:
    """The instance still starts, and says what it lost. A deployment whose
    role cannot create a trigger has the convention and not the constraint,
    and needs to be told at start-up rather than the day somebody rewrites a
    version."""
    import logging
    db = ctx.ui.app.state.ctx.get("db")
    if db is None:
        return BLOCKED, "no database is wired"
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    class Refusing:
        """An engine whose role holds no CREATE TRIGGER."""

        def __init__(self, wrapped):
            self._wrapped = wrapped

        def begin(self):
            raise RuntimeError("permission denied for CREATE TRIGGER")

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

    handler, root = Catch(), logging.getLogger()
    root.addHandler(handler)
    was, real = root.level, db.engine
    root.setLevel(logging.WARNING)
    try:
        db.engine = Refusing(real)
        applied = db._apply_enforcement()
    finally:
        db.engine = real
        root.removeHandler(handler)
        root.setLevel(was)
    if applied:
        return BLOCKED, (f"{applied} trigger(s) applied anyway, so the "
                         f"refusing role was not in force")
    warned = [m for m in records if "convention" in m and "constraint" in m]
    if not warned:
        return FAIL, ("every trigger failed to apply and nothing warned: the "
                      "deployment has the convention rather than the "
                      "constraint, and no way to find out")
    if db._apply_enforcement() <= 0:
        return FAIL, "the real engine no longer applies the triggers either"
    return PASS, (f"{len(warned)} warning(s) and the instance still starts: "
                  f"{warned[0][:130]}")


def _scoped_reader(ctx: Ctx) -> tuple:
    who = ctx.unique("scoped")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_risk_manager"],
                              "password": f"{who}-pw",
                              "legal_entities": ["LE-XX-99"], "domains": []})
    return (who, f"{who}-pw") if made.status_code < 400 else ("", "")


@case("QA-PLT-072",
      "A directly-addressable page under a scope that should not see it")
def plt_072(ctx: Ctx) -> Result:
    """The same defect already happened once here: listings filtered and
    directly-addressable pages did not, so a model was invisible on the
    dashboard and readable by URL. A page reached by typing its address is
    the one nobody tests and the one an auditor tries."""
    from fastapi.testclient import TestClient
    urn = _registered(ctx)
    who, password = _scoped_reader(ctx)
    if not who:
        return BLOCKED, "the scoped reader could not be created"
    with TestClient(ctx.ui.app, raise_server_exceptions=False) as browser:
        browser.post("/login", data={"username": who, "password": password},
                     follow_redirects=False)
        landing = browser.get("/dashboard")
        if "sign in" in landing.text[:4000].lower():
            return BLOCKED, "the scoped reader could not sign in"
        page = browser.get(f"/model/{urn}")
        listing = browser.get("/models")
    if page.status_code == 200 and "forbidden" not in page.text.lower():
        hidden = urn not in listing.text
        return FAIL, (
            f"a validator scoped to LE-XX-99 opened /model/{urn} directly and "
            f"was served it (200), while the listing "
            f"{'hides it' if hidden else 'shows it too'}. A page filtered out "
            f"of every list and served by URL is the worse of the two: "
            f"nobody looks for it")
    if page.status_code != 403:
        return FAIL, (f"the page answered {page.status_code} rather than 403; "
                      f"an out-of-scope read must be refused, not empty")
    return PASS, "refused 403 on the directly-addressable page"


@case("QA-PLT-074", "A table not in `SCOPED_TABLES` reached through one that is")
def plt_074(ctx: Ctx) -> Result:
    """Rows that do not CARRY an entity are outside the database backstop by
    construction — a version's entity is its model's, and expressing that as
    a policy is a subquery per row on every read. The application is what
    stops it, and the posture has to say so rather than implying the backstop
    is wider than it is."""
    from core.security.rls import SCOPED_TABLES
    from db.schema.tables import METADATA
    policed = {t for t, _ in SCOPED_TABLES}
    carrying = {n for n, tab in METADATA.tables.items()
                if "model_id" in tab.c and n not in policed}
    if not carrying:
        return BLOCKED, "every model-bearing table is policed"
    rls = getattr(ctx.ui.app.state, "rls", None)
    if rls is None:
        return BLOCKED, "no row-level-security reporter is wired"
    reach = rls.posture().get("does_not_reach") or ""
    if "do not CARRY an entity" not in reach:
        return FAIL, (f"{len(carrying)} table(s) carry a model_id and no "
                      f"policy, and the posture does not say so: {reach[:140]}")
    urn = _registered(ctx)
    auth = _scoped_reader(ctx)
    if not auth[0]:
        return BLOCKED, "the scoped reader could not be created"
    reads = {
        "versions": ctx.api.get(f"/api/v1/models/{urn}/versions", auth=auth),
        "findings": ctx.api.get(f"/api/v1/findings?urn={urn}", auth=auth),
        # `model=`, not `urn=`. An unknown query parameter is ignored, so a
        # probe that misnames it reads the estate-wide listing, sees a 200 and
        # reports a leak that is its own spelling mistake.
        "warrants": ctx.api.get(f"/api/v1/warrants?model={urn}", auth=auth),
    }
    served = [name for name, got in reads.items()
              if got.status_code < 400 and urn in got.text]
    if served:
        return FAIL, (f"{len(carrying)} unpoliced table(s) carry a model_id, "
                      f"and the application served {served} for a model the "
                      f"caller is scoped away from — so neither layer stops it")
    return PASS, (f"{len(carrying)} table(s) carry a model_id outside "
                  f"SCOPED_TABLES; the posture names the gap and the "
                  f"application refuses all three reads")


@case("QA-PLT-075", "A hard delete and what still names the model",
      isolated=True)
def plt_075(ctx: Ctx) -> Result:
    """The case was written when a hard delete left orphan versions,
    warrants, findings and monitors and the database said nothing. The
    cascade closed that; this is what keeps the closure honest. Every table
    carrying a `model_id` must be DISPOSED of by name — destroyed, kept
    deliberately, or blocking — because a disposition list that misses a
    table does not fail, it leaves an orphan nothing counts."""
    from core.retention.cascade import CASCADE
    from db.schema.tables import METADATA
    declared = {d.table for d in CASCADE}
    carrying = {n for n, tab in METADATA.tables.items() if "model_id" in tab.c}
    missing = carrying - declared
    if missing:
        return FAIL, (f"{len(missing)} table(s) carry a model_id and appear in "
                      f"no disposition: {sorted(missing)} — a deletion leaves "
                      f"their rows pointing at an identifier that no longer "
                      f"resolves, and nothing counts them")
    urn = _registered(ctx)
    db = ctx.ui.app.state.ctx["db"]
    model_id = ctx.ui.app.state.ctx["registry"].require(urn)["id"]
    got = ctx.api.delete(f"/api/v1/models/{urn}?reason=qa%20deletion")
    if got.status_code >= 400:
        return BLOCKED, f"the deletion was refused: {got.text[:170]}"
    body = got.json() or {}
    left = {}
    for table in sorted(carrying):
        rows = db.query(f"SELECT COUNT(*) AS n FROM {table} "
                        f"WHERE model_id = :m", {"m": model_id})
        if rows and rows[0]["n"]:
            left[table] = rows[0]["n"]
    kept = {d.table for d in CASCADE if d.kind == "stays"}
    orphans = {t: n for t, n in left.items() if t not in kept}
    if orphans:
        return FAIL, (f"after the deletion these rows still name a model that "
                      f"no longer resolves, and none of them is a declared "
                      f"'stays': {orphans}")
    if not body.get("tombstone"):
        return FAIL, "the deletion recorded no tombstone"
    return PASS, (f"{len(carrying)} model-bearing tables, every one disposed; "
                  f"destroyed {body.get('destroyed')}, kept "
                  f"{sorted(left) or 'nothing'}, tombstone "
                  f"{str(body['tombstone'])[:12]}")


@case("QA-PLT-076", "A deletion refused because something still refers to it")
def plt_076(ctx: Ctx) -> Result:
    """There are no foreign keys on purpose, so the reference index is the
    whole control — and a refusal that does not NAME what refers to it sends
    somebody looking, which is how a deletion gets forced through another
    way."""
    # EPHEMERAL deliberately. A durable feature is refused earlier and for a
    # different reason — it is retired rather than destroyed — and that
    # refusal is a property of the thing, so a case using one would never
    # reach the reference index it is written about.
    feature = ctx.unique("feat")
    made = ctx.api.post("/api/v1/features",
                        json={"name": feature, "entity": "obligor",
                              "dtype": "float", "owner": "person/owner",
                              "ephemeral": True, "ttl_days": 7,
                              "description": "qa"},
                        auth=ctx.people["owner"])
    if made.status_code >= 400:
        return BLOCKED, f"the feature could not be defined: {made.text[:150]}"
    fset = ctx.unique("fs")
    built = ctx.api.post("/api/v1/featuresets",
                         json={"name": fset, "entity": "obligor",
                               "slots": {feature: {"dtype": "float"}},
                               "description": "qa"}, auth=ctx.people["owner"])
    if built.status_code >= 400:
        return BLOCKED, f"the featureset could not be built: {built.text[:150]}"
    got = ctx.api.delete(f"/api/v1/features/{feature}")
    if got.status_code < 400:
        return FAIL, (f"a feature the featureset {fset} declares a slot for "
                      f"was deleted, leaving the set pointing at nothing")
    if code_of(got) != "still_referenced":
        return FAIL, (f"refused '{code_of(got)}' rather than "
                      f"'still_referenced': {got.text[:200]}")
    said = got.text
    if fset not in said:
        return FAIL, (f"the refusal does not name what refers to it, so the "
                      f"caller has to go looking: {said[:180]}")
    if "retire" not in said:
        return FAIL, "the refusal offers no alternative to deleting"
    return PASS, f"refused 'still_referenced', naming {fset}"


@case("QA-PLT-077", "A deletion under legal hold", isolated=True)
def plt_077(ctx: Ctx) -> Result:
    """A hold that a delete path does not consult is a hold that exists in a
    status table. Both directions matter: refused while it stands, and
    permitted once it is lifted — a hold nobody can lift is a different
    failure with the same symptom."""
    urn = _registered(ctx)
    placed = ctx.api.post("/api/v1/legal-holds",
                          json={"matter": "QA-2026-114",
                                "owner": "person/legal-counsel",
                                "scope_kind": "model", "scope_id": urn,
                                "classes": []}, auth=ctx.people["risk"])
    if placed.status_code >= 400:
        return BLOCKED, f"the hold could not be placed: {placed.text[:150]}"
    body = placed.json() or {}
    reference = (body.get("hold") or body).get("reference", "")
    held = ctx.api.delete(f"/api/v1/models/{urn}?reason=qa%20deletion")
    if held.status_code < 400:
        return FAIL, ("a model under legal hold was deleted; the hold is a "
                      "row in a status table that no delete path reads")
    if code_of(held) != "under_legal_hold":
        return FAIL, (f"refused '{code_of(held)}' rather than "
                      f"'under_legal_hold': {held.text[:150]}")
    if not reference:
        return FAIL, "the hold carries no reference, so nothing can lift it"
    if "QA-2026-114" not in held.text and reference not in held.text:
        return FAIL, (f"the refusal names neither the matter nor the hold, so "
                      f"nobody knows who to ask: {held.text[:170]}")
    if "QA-2026-114" not in held.text:
        # The reference is named rather than the matter. Acceptable only if
        # the reference resolves to the matter without another permission.
        listed = ctx.api.get("/api/v1/legal-holds", auth=ctx.people["risk"])
        if "QA-2026-114" not in listed.text:
            return FAIL, (f"the refusal names {reference} and nothing readable "
                          f"maps it to a matter, so the caller is told a hold "
                          f"exists and cannot find out whose it is")
    lifted = ctx.api.post(f"/api/v1/legal-holds/{reference}/lift",
                          json={"reason": "the matter closed"},
                          auth=ctx.people["risk"])
    if lifted.status_code >= 400:
        return FAIL, (f"the hold cannot be lifted ({lifted.status_code}), so "
                      f"it is permanent rather than a hold: {lifted.text[:140]}")
    after = ctx.api.delete(f"/api/v1/models/{urn}?reason=qa%20deletion")
    if after.status_code >= 400:
        return FAIL, (f"the deletion is still refused after the hold was "
                      f"lifted: '{code_of(after)}' {after.text[:150]}")
    return PASS, ("refused 'under_legal_hold' naming the matter, and "
                  "permitted once it was lifted")
