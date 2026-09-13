"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the second dialect, and the backstop that only exists on it.

**A rule enforced on one dialect and not the other is a rule the deployment
does not have.** The immutability triggers are generated per dialect from
`db/schema/immutable.py`, and 1,780 tests once passed against a PostgreSQL
schema nobody had ever executed — fourteen BOOLEAN columns against a
repository layer that coerces every boolean to `int`, which PostgreSQL will
not implicitly cast.

Row-level security is the other half. It is **not** the control —
`core/authz/scope.py` is, and it produces a refusal somebody can act on where
RLS produces no rows. The backstop is for the endpoint somebody wrote last week
and forgot to filter, and three facts decide whether it is real: `available`
(false on SQLite, and nothing can be done about that),
`connecting_role_is_exempt` (a superuser bypasses all of it, FORCE or not), and
`forced` rather than `enabled`.

The PostgreSQL cases run only against a live database. Set
`MAYA_QA_POSTGRES` to a SQLAlchemy URL — a skip is honest, but an untested
backstop is an assumed one, so a run without it says so per case rather than
reporting a pass.
"""
from __future__ import annotations

import os

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

URL = os.environ.get("MAYA_QA_POSTGRES", "")
NO_PG = ("set MAYA_QA_POSTGRES to a live PostgreSQL to run this; an untested "
         "backstop is an assumed one")


def _pg():
    """A schema-applied PostgreSQL database, as the owner."""
    from db.database import Database
    db = Database(URL)
    db.apply_schema()
    return db


def _seeded(db):
    """A chain with something in it.

    An empty append-only table refuses nothing: a row-level trigger does not
    fire on an UPDATE that matches no rows, and a DELETE over nothing
    succeeds. A case that attacked an empty chain would report the guard
    working while never reaching it.
    """
    from core.evidence.engine import EvidenceEngine
    from db.repositories import EvidenceRepository
    engine = EvidenceEngine(EvidenceRepository(db))
    with engine.recording():
        engine.append("qa_probe", "model", "pg-probe",
                      {"why": "an append-only guard needs a row to guard"},
                      actor="qa")
    return engine


# ------------------------------------------------------- what SQLite can answer
@case("QA-PLT-121", "Row-level security asked for on SQLite")
def plt_121(ctx: Ctx) -> Result:
    """`available: false`, with the reason — never a silent success. A
    deployment that read `applied` off a SQLite instance would believe it had
    a database backstop it cannot have."""
    got = ctx.api.get("/api/v1/row-level-security")
    if got.status_code >= 400:
        return BLOCKED, f"the report was refused: {got.text[:150]}"
    body = got.json() or {}
    if body.get("available") is not False:
        return BLOCKED, f"this instance is not on SQLite: {body.get('available')}"
    if body.get("forced") or body.get("enabled") or body.get("tables"):
        return FAIL, (f"an unavailable backstop reports coverage: "
                      f"forced={body.get('forced')} enabled={body.get('enabled')} "
                      f"tables={len(body.get('tables') or [])}")
    detail = body.get("detail") or ""
    if "PostgreSQL" not in detail:
        return FAIL, f"the report does not say why: {detail[:150]}"
    if "scope" not in detail:
        return FAIL, (f"the report does not say what carries the weight "
                      f"instead: {detail[:150]}")
    return PASS, f"available false, and the reason: {detail[:120]}"


@case("QA-PLT-122", "A dimension outside `POLICED`")
def plt_122(ctx: Ctx) -> Result:
    """Scope has more dimensions than the policies cover, and the ones it
    does not cover must be stated rather than assumed. A backstop narrower
    than the control is ordinary; one that LOOKED as wide would be the
    problem."""
    from core.security.rls import POLICED, UNPOLICED
    rls = getattr(ctx.ui.app.state, "rls", None)
    if rls is None:
        return BLOCKED, "no row-level-security reporter is wired"
    posture = rls.posture()
    if not UNPOLICED:
        return BLOCKED, "every scope dimension is policed"
    named = posture.get("unpoliced_dimensions") or []
    if sorted(named) != sorted(UNPOLICED):
        return FAIL, (f"the posture names {named} as unpoliced against "
                      f"{list(UNPOLICED)}")
    if sorted(posture.get("policed_dimensions") or []) != sorted(POLICED):
        return FAIL, "the policed dimensions disagree with the module"
    reach = posture.get("does_not_reach") or ""
    for dimension in UNPOLICED:
        if dimension not in reach:
            return FAIL, (f"'{dimension}' is unpoliced and `does_not_reach` "
                          f"does not say so: {reach[:150]}")
    if "do not CARRY an entity" not in reach:
        return FAIL, ("the report names the dimensions and not the rows — a "
                      "version's entity is its model's, and no policy here "
                      "expresses that")
    if posture.get("is_the_control") is not False:
        return FAIL, "the backstop reports itself as the control"
    if not (posture.get("why_not_the_control") or ""):
        return FAIL, "and says nothing about why it is not"
    return PASS, (f"policed {list(POLICED)}, unpoliced {named}, both named "
                  f"in `does_not_reach`")


# ------------------------------------------------------------ the second dialect
@case("QA-PLT-068", "The same immutability attacks against PostgreSQL")
def plt_068(ctx: Ctx) -> Result:
    """The triggers are generated per dialect from `db/schema/immutable.py`.
    A rule that holds on the dialect the tests run against and not on the one
    a bank deploys is a rule the bank does not have."""
    if not URL:
        return BLOCKED, NO_PG
    import sqlalchemy as sa

    from db.schema.immutable import APPEND_ONLY, IMMUTABLE_COLUMNS
    db = _pg()
    triggers = db.query(
        "SELECT c.relname AS table_name, t.tgname AS name FROM pg_trigger t "
        "JOIN pg_class c ON c.oid = t.tgrelid WHERE NOT t.tgisinternal")
    guarded = {row["table_name"] for row in triggers}
    wanted = set(IMMUTABLE_COLUMNS) | set(APPEND_ONLY)
    missing = wanted - guarded
    if missing:
        return FAIL, (f"{len(missing)} guarded table(s) have no trigger on "
                      f"PostgreSQL: {sorted(missing)} — the rule holds on "
                      f"SQLite and not on the dialect a bank deploys")
    _seeded(db)
    engine = sa.create_engine(URL)
    refused, allowed = [], []
    for statement, what in (
            ("UPDATE evidence_node SET payload = '{}'", "an UPDATE"),
            ("DELETE FROM evidence_node", "a DELETE")):
        try:
            with engine.begin() as conn:
                conn.execute(sa.text(statement))
            allowed.append(what)
        except Exception as exc:
            refused.append(f"{what}: {str(exc).splitlines()[0][:80]}")
    if allowed:
        return FAIL, (f"the append-only chain accepted {', '.join(allowed)} "
                      f"on PostgreSQL")
    return PASS, (f"{len(guarded)} guarded table(s) carry triggers; "
                  f"evidence_node refuses both — {'; '.join(refused)}")


@case("QA-PLT-117", "A raw `UPDATE` on `evidence_node` against PostgreSQL")
def plt_117(ctx: Ctx) -> Result:
    """The trigger raises, which is the answer the case wants — and it is
    also why the dialect test that proves the CHAIN detects tampering can no
    longer run. That test writes the tamper through `db.execute`, the very
    statement the trigger now refuses, so the assertion after it is
    unreachable."""
    if not URL:
        return BLOCKED, NO_PG
    import sqlalchemy as sa
    db = _pg()
    _seeded(db)
    engine = sa.create_engine(URL)
    seq = db.query("SELECT seq FROM evidence_node ORDER BY seq LIMIT 1")
    if not seq:
        return BLOCKED, "the chain is empty on this database"
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE evidence_node SET payload = '{}' "
                                 "WHERE seq = :s"), {"s": seq[0]["seq"]})
    except Exception as exc:
        said = str(exc)
        if "append" not in said.lower() and "immutab" not in said.lower():
            return FAIL, f"refused, but not by the append-only guard: {said[:150]}"
        import inspect

        from tests import test_postgres_dialect as dialect
        source = inspect.getsource(
            dialect.test_a_tampered_payload_breaks_the_chain_on_postgres_too)
        if "db\"].execute(" in source and "verify_chain" in source:
            return FAIL, (
                "the trigger refuses the raw UPDATE, which is correct — and "
                "`tests/test_postgres_dialect.py::"
                "test_a_tampered_payload_breaks_the_chain_on_postgres_too` "
                "performs exactly that UPDATE through `db.execute` before "
                "asserting `verify_chain()['valid'] is False`. The trigger now "
                "raises there, so the test ERRORS and the only assertion that "
                "the chain DETECTS tampering on PostgreSQL never runs. The "
                "guard that was added made the test that proves the deeper "
                "guard unreachable, and nothing noticed because "
                "MAYA_TEST_POSTGRES is unset in the gate")
        return PASS, f"refused by the append-only trigger: {said[:110]}"
    return FAIL, ("a raw UPDATE on evidence_node succeeded on PostgreSQL: the "
                  "append-only trigger is not in force on the dialect a bank "
                  "deploys")


@case("QA-PLT-069", "A cross-entity read with row-level security in force")
def plt_069(ctx: Ctx) -> Result:
    """Zero rows, not a refusal — and the isolation tests that prove it have
    never run. `tests/test_row_level_security.py` hands `MAYA_TEST_POSTGRES`
    straight to `psycopg.connect`, which needs a libpq URL, while
    `tests/test_postgres_dialect.py` documents the SQLAlchemy form of the
    same variable."""
    if not URL:
        return BLOCKED, NO_PG
    import inspect

    import psycopg

    from tests import test_row_level_security as rls
    source = inspect.getsource(rls)
    if "psycopg.connect(PG_URL" not in source:
        return BLOCKED, "the isolation tests no longer connect that way"
    try:
        psycopg.connect(URL)
    except psycopg.ProgrammingError as exc:
        # Redacted: the URL carries a password, and a QA result is a file in
        # the repository.
        said = str(exc).replace(URL, "<MAYA_QA_POSTGRES>")
        if "missing" not in said:
            return FAIL, f"refused for another reason: {said}"
        return FAIL, (
            f"the URL that runs `tests/test_postgres_dialect.py` cannot be "
            f"parsed by `psycopg.connect`, which "
            f"`tests/test_row_level_security.py` calls with it directly: "
            f"{said[:110]}. The dialect file's own docstring documents the "
            f"`postgresql+psycopg://` form, so following the documented "
            f"instruction ERRORS all six isolation tests at setup, and the "
            f"plain `postgresql://` form errors all six dialect tests instead. "
            f"There is no value of MAYA_TEST_POSTGRES that runs both, and the "
            f"tests that prove the cross-entity read returns zero rows are the "
            f"half that silently never ran. Worse than the parse: the "
            f"`estate` fixture opens with `DROP TABLE IF EXISTS model CASCADE` "
            f"and rebuilds a two-column stub it never restores, so even a URL "
            f"both files could parse would leave the dialect tests running "
            f"against a `model` table with no `urn`. The two suites cannot "
            f"share a database, and nothing says so")
    except Exception as exc:
        return BLOCKED, f"could not reach the database: {str(exc)[:120]}"
    return PASS, ("the same URL drives both PostgreSQL test files, so the "
                  "isolation tests run with the dialect tests")


@case("QA-PLT-085", "A truth-valued column written as a Python `bool`")
def plt_085(ctx: Ctx) -> Result:
    """The hand-kept coercion list is what makes fourteen BOOLEAN columns
    survive a repository layer that stores ints. Both dialects have to store
    and read a truth value identically, or a governance flag means one thing
    in the test estate and another in the deployed one."""
    if not URL:
        return BLOCKED, NO_PG
    from db.repositories import FindingRepository, ModelRepository
    import time as _t
    db = _pg()
    models, findings = ModelRepository(db), FindingRepository(db)
    urn = f"maya://model/pg-bool-{int(_t.time() * 1000)}"
    model = models.add({"urn": urn, "name": "pg bool", "owner": "owner",
                        "model_class": "logistic", "domain": "credit",
                        "legal_entity": "LE-US-01",
                        "purpose": "credit_decision", "tier": 3,
                        "status": "registered", "created_at": _t.time(),
                        "created_by": "qa"})
    out = []
    for value in (True, False):
        row = findings.add({"model_id": model["id"], "source": "validation",
                            "severity": "High", "category": "general",
                            "title": "pg bool", "description": "",
                            "blocking": value, "owner": "person/owner",
                            "raised_at": _t.time(),
                            "due_at": _t.time() + 86400,
                            "status": "open", "closure_evidence": {}})
        back = findings.one(id=row["id"])
        out.append((value, back["blocking"]))
        if bool(back["blocking"]) is not value:
            return FAIL, (f"a truth column written as Python {value} reads "
                          f"back as {back['blocking']!r} on PostgreSQL")
    counted = findings.many(model_id=model["id"], blocking=True)
    if len(counted) != 1:
        return FAIL, (f"an equality filter on a truth column matched "
                      f"{len(counted)} of the two rows, so a Python bool and "
                      f"the stored value are not the same thing in a WHERE "
                      f"clause")
    return PASS, f"True and False round-trip and filter: {out}"


@case("QA-PLT-115", "Sixteen concurrent version creations against PostgreSQL")
def plt_115(ctx: Ctx) -> Result:
    """The measured symptom on SQLite was five versions and eleven 500s, from
    a serialise lock taken too late. Sixteen versions, contiguous evidence
    seqs and zero 500s is the answer; anything else is a governance record
    with holes in it that nothing reports."""
    if not URL:
        return BLOCKED, NO_PG
    return BLOCKED, ("the scenario harness serves one app over a TestClient "
                     "and cannot drive sixteen simultaneous requests against "
                     "a second dialect; run the concurrency suite with "
                     "MAYA_TEST_POSTGRES set")
