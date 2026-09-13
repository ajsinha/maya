"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The schema is declared once, and these hold what that declaration must satisfy.

It used to be declared twice. `db/schema/sqlite.sql` and `postgres.sql` were
hand-maintained in parallel, had to say the same thing about fifty tables, and
this file existed to compare them — a good test of a bad arrangement, because
comparing two files can only ever report a divergence somebody has already
shipped. It had already failed once: fourteen columns were declared `BOOLEAN`
on the PostgreSQL side while `db/repositories.py` coerced every Python bool to
`int` on the way in, and PostgreSQL does not implicitly cast integer to
boolean — so every insert touching one of those tables would have failed, and
the entire dialect was unusable. Nothing raised, because nothing ran against
PostgreSQL.

The response then was a rule: **no BOOLEAN columns anywhere**, truth as integer
0/1, with the service layer converting at its boundary. That fixed the symptom.
The cause was that a column's type was written in two places and known to
neither the driver nor the code writing to it.

`db/schema/tables.py` removes the cause. One typed declaration per column,
compiled to each dialect's DDL; `Boolean` becomes `BOOLEAN` in both, and the
value that reaches the driver is decided by the column rather than by a list of
column names somebody maintains. So BOOLEAN is now allowed — and what these
tests hold is the property the old rule was reaching for: **a row written under
one dialect reads correctly under the other**, plus the things a single
declaration still cannot guarantee on its own.
"""
from __future__ import annotations

import pathlib
import re

import sqlalchemy as sa

from db.schema.tables import METADATA

ROOT = pathlib.Path(__file__).resolve().parents[1]
SQLITE = ROOT / "db" / "schema" / "sqlite.sql"
POSTGRES = ROOT / "db" / "schema" / "postgres.sql"

CONSTRAINTS = ("PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CHECK", "CONSTRAINT")


def _columns(path: pathlib.Path) -> dict:
    """{(table, column): type} for every table in a schema file."""
    out = {}
    for match in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);",
                             path.read_text(encoding="utf-8"), re.S):
        table, body = match.group(1), match.group(2)
        for line in body.splitlines():
            # Strip a trailing comment BEFORE the comma, or a commented column
            # keeps its comma and reads as a different type from its twin.
            line = line.split("--")[0].strip().rstrip(",")
            if not line or line.startswith("--") or line.upper().startswith(CONSTRAINTS):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            # `DOUBLE PRECISION` is two tokens, and the files mix casing.
            rest = [p.upper() for p in parts[1:3]]
            declared = "DOUBLE PRECISION" if rest[:2] == ["DOUBLE", "PRECISION"] \
                else parts[1].upper()
            out[(table, parts[0])] = declared
    return out


def test_boolean_is_a_real_boolean_in_both_dialects():
    """The type that broke this codebase, now declared once and compiled twice.

    `Boolean` must reach BOTH dialects as `BOOLEAN`, and it must not drag a
    CHECK constraint along with it: SQLAlchemy can emit `CHECK (col IN (0, 1))`
    for backends without a native type, MAYA has no CHECK constraints anywhere
    by design, and one appearing here would be a constraint nobody declared.
    """
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    truth = [(t, c) for t in METADATA.tables.values() for c in t.columns
             if isinstance(c.type, sa.Boolean)]
    assert truth, "the truth columns exist"
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        for table, column in truth:
            ddl = str(CreateTable(table).compile(dialect=dialect))
            line = next(ln.strip() for ln in ddl.splitlines()
                        if ln.strip().startswith(column.name + " "))
            assert "BOOLEAN" in line.upper(), f"{table.name}.{column.name}: {line}"
        for table, _ in truth:
            # `CHECK (`, not the word: `model_edge.type_checked` contains it.
            assert "CHECK (" not in str(
                CreateTable(table).compile(dialect=dialect)).upper(), table.name


def test_a_truth_columns_default_is_a_truth_value_in_both_dialects():
    """The same bug as the original one, arriving through the DEFAULT.

    Every truth column was declared `server_default=text('0')` — a raw SQL
    literal, emitted verbatim to both dialects. The type was right and the
    default was an integer, and PostgreSQL does not implicitly cast integer to
    boolean *in a default expression* any more than it does in an insert:

        column "type_checked" is of type boolean but default expression is of
        type integer

    which is a CREATE TABLE that fails, so the whole dialect was uncreatable
    again. SQLite accepted it, exactly as it accepted the original.

    `false()`/`true()` are compiled by the dialect rather than passed through:
    SQLite still gets `0`/`1`, so a deployed SQLite database sees no change,
    and PostgreSQL gets `false`/`true`.
    """
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    truth = [(t, c) for t in METADATA.tables.values() for c in t.columns
             if isinstance(c.type, sa.Boolean)]
    assert truth, "the truth columns exist"
    allowed = {"sqlite": {"0", "1"}, "postgresql": {"FALSE", "TRUE"}}
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        for table, column in truth:
            ddl = str(CreateTable(table).compile(dialect=dialect))
            line = next(ln.strip() for ln in ddl.splitlines()
                        if ln.strip().startswith(column.name + " "))
            if "DEFAULT" not in line.upper():
                continue
            rendered = line.upper().split("DEFAULT", 1)[1].split()[0].rstrip(",")
            assert rendered in allowed[dialect.name], (
                f"{table.name}.{column.name} defaults to {rendered} under "
                f"{dialect.name}; a BOOLEAN column takes a boolean default, "
                f"and PostgreSQL refuses the CREATE TABLE otherwise")


def test_a_count_is_not_a_truth_value():
    """The distinction the old hand-maintained list kept getting wrong.

    `use_count`, `epoch`, `row_count`, `size_bytes` and `definition_version`
    all default to 0 or 1 and are integers. Declaring one Boolean would round
    every value above one down to `True`.
    """
    counts = {"use_count", "epoch", "row_count", "size_bytes", "item_count",
              "definition_version", "delta_version", "sample_size", "renewals",
              "consecutive", "specificity", "cardinality", "version",
              "grace_seconds", "outcome_window_days", "models", "debt_items",
              "evidence_head"}
    wrong = [f"{t.name}.{c.name}" for t in METADATA.tables.values()
             for c in t.columns
             if c.name in counts and isinstance(c.type, sa.Boolean)]
    assert not wrong, f"these are counts declared as truth values: {wrong}"


def test_the_generated_ddl_still_matches_the_declaration():
    """`db/schema/*.sql` are generated reference and must not become fiction.

    They are what a DBA reads and what a change-control process is handed. A
    file that says one thing while the application creates another is worse
    than no file, because it is believed.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "ci" / "render_schema.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, (
        result.stdout + result.stderr
        + "\nrun: python tools/ci/render_schema.py")


def test_one_declaration_produces_the_same_shape_in_both_dialects():
    """The property the two-file comparison was reaching for, asserted at the
    source instead: the same tables, the same columns, in the same order.

    Quoting is stripped before comparing, because the dialects disagree about
    which identifiers need it — SQLite quotes `plan`, PostgreSQL does not — and
    getting that right in two hand-written files was one more thing that had to
    be remembered. It is now one more thing the compiler does."""
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    def shape(dialect):
        out = {}
        for name, table in METADATA.tables.items():
            ddl = str(CreateTable(table).compile(dialect=dialect))
            out[name] = [ln.strip().split()[0].strip('"') for ln in ddl.splitlines()
                         if ln.startswith(("\t", "    ")) and ln.strip()
                         and ln.strip().split()[0].upper() not in CONSTRAINTS_FIRST]
        return out

    assert shape(sqlite.dialect()) == shape(postgresql.dialect())


CONSTRAINTS_FIRST = {"PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"}


def test_a_truth_column_gets_a_bool_and_nothing_else_does():
    """Both directions, because PostgreSQL refuses both mistakes.

    An integer in a BOOLEAN column and a boolean in an INTEGER column are each
    an error there, and each is silently accepted by SQLite — which is exactly
    why SQLite cannot be the thing that tells you which one you wrote.
    """
    from db.repositories import Repository

    repo = Repository.__new__(Repository)
    repo.TABLE, repo.JSON = "warrant", ()
    encoded = repo._encode({
        "revoked": 0,                # a truth column, given an int
        "epoch": 3,                  # a count, and must stay one
        "principal": "svc/x", "expires_at": 1.5, "revoke_reason": None,
        "declared_use": True})       # not a truth column, given a bool
    assert encoded["revoked"] is False, "a truth column is handed a real bool"
    assert encoded["epoch"] == 3 and not isinstance(encoded["epoch"], bool)
    assert encoded["declared_use"] == 1, "a bool elsewhere is made an integer"
    assert encoded["revoke_reason"] is None, "and None stays None"


def test_the_truth_columns_are_read_off_the_schema():
    """The list used to be maintained by hand, and the list was the defect: it
    named fourteen of the twenty columns that existed. The six it missed were
    correct only because every call site happened to write an integer."""
    from db.repositories import _TRUTH

    declared = {(t.name, c.name) for t in METADATA.tables.values()
                for c in t.columns if isinstance(c.type, sa.Boolean)}
    derived = {(table, col) for table, cols in _TRUTH.items() for col in cols}
    assert derived == declared
    assert ("role", "built_in") in derived, "one of the six the list missed"
    assert ("api_key", "use_count") not in derived, "a count is not a truth value"


def test_a_truth_column_round_trips_as_a_bool(tmp_path):
    """Written as a bool, read back as a bool, through a real database."""
    from db.database import Database
    from db.repositories import Repository

    db = Database(f"sqlite:///{tmp_path}/x.db")

    class Roles(Repository):
        TABLE, JSON = "role", ("permissions",)

    roles = Roles(db)
    roles.add({"name": "r", "description": "d", "permissions": [],
               "built_in": True, "created_at": 1.0, "created_by": "me"})
    row = roles.one(name="r")
    assert row["built_in"] is True
    roles.set({"built_in": False}, name="r")
    assert roles.one(name="r")["built_in"] is False


def test_no_relational_table_holds_bulk_values():
    """Feature and featureset DATA lives in Delta. The database holds pointers.

    The relational store is the control plane: models, versions, findings,
    evidence — things a person reads one at a time. Feature values are the data
    plane and can run to hundreds of millions of rows per view, so they live in
    Delta and the register keeps a `delta_table` and a `delta_version` that
    together name exactly which bytes a read gets.

    This is already true and this test is here so it stays true. The failure it
    guards against is somebody adding a `rows` or `values` column "just for a
    preview" — at which point the register grows without bound, backups stop
    fitting, and a governance database becomes a data lake nobody chose.
    """
    import re

    bulk = {"rows", "values", "data", "records", "sample", "observations",
            "payload_rows", "frame", "dataset"}
    offenders = []
    for path in (SQLITE, POSTGRES):
        text = path.read_text(encoding="utf-8")
        for table, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);",
                                      text, re.S):
            for line in body.splitlines():
                column = line.strip().split("--")[0].strip().rstrip(",")
                if not column or column.upper().startswith(CONSTRAINTS):
                    continue
                if column.split()[0] in bulk:
                    offenders.append(f"{path.name}: {table}.{column.split()[0]}")
    assert not offenders, (
        "these columns look like they hold bulk data rather than a pointer to "
        "it:\n    " + "\n    ".join(offenders)
        + "\nFeature values belong in Delta; the register keeps delta_table and "
          "delta_version, which name exactly which bytes a read gets.")


def test_the_data_plane_is_addressed_by_pointer():
    """The positive half: the tables that own bulk data say where it is."""
    import re

    text = SQLITE.read_text(encoding="utf-8")
    tables = dict(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);",
                             text, re.S))
    for table, needs in (("feature_view", "delta_table"),
                         ("feature_view_version", "delta_version"),
                         ("dataset_snapshot", "delta_table"),
                         ("telemetry_batch", "delta_table")):
        assert needs in tables[table], f"{table} must name its Delta location"


def test_postgres_never_uses_real_where_sqlite_does():
    """`REAL` in PostgreSQL is float4, and an epoch second does not fit in it.

    `postgres.sql` says at the top that the ONE substitution it makes is
    `DOUBLE PRECISION` where SQLite uses `REAL`. A `serving_attestation`
    column shipped as `REAL` anyway, and float4 carries about six significant
    decimal digits against the ten an epoch timestamp needs — so `attested_at`
    quantised to roughly 33 seconds, on the evidence trail whose entire purpose
    is saying what was served and when.

    The dialect comparison could not see it: it checks that the two files agree
    on which tables and columns exist, and both files said `REAL`. Agreement is
    not correctness when the agreed value is wrong for one of them.
    """
    postgres = (ROOT / "db" / "schema" / "postgres.sql").read_text()
    offending = [line.strip() for line in postgres.splitlines()
                 if re.search(r"\bREAL\b", line)
                 and not line.lstrip().startswith("--")]
    assert not offending, (
        "these PostgreSQL columns are REAL (float4, ~6 significant digits) "
        "where the file's own header says DOUBLE PRECISION:\n    "
        + "\n    ".join(offending))


def test_every_timestamp_column_survives_an_epoch_second():
    """The property behind the rule, asserted rather than assumed.

    Stated as a property so a future column called `..._at` cannot be added as
    something too narrow to hold the value it is named for.
    """
    import numpy

    moment = 1788710367.229
    assert float(numpy.float32(moment)) != moment, (
        "float4 is assumed too narrow for an epoch second; if that has stopped "
        "being true this test is asserting nothing")
    assert float(numpy.float64(moment)) == moment

    for dialect, kind in (("sqlite", "REAL"), ("postgres", "DOUBLE PRECISION")):
        sql = (ROOT / "db" / "schema" / f"{dialect}.sql").read_text()
        for line in sql.splitlines():
            match = re.match(
                r"\s+(\w*(?:_at|_ts|_due))\s+(DOUBLE PRECISION|REAL|TEXT|INTEGER)\b",
                line)
            if match and match.group(2) not in ("TEXT", "INTEGER"):
                assert match.group(2) == kind, (
                    f"{dialect}.sql: {match.group(1)} is {match.group(2)}, "
                    f"and a timestamp column here must be {kind}")


def _unique_clauses(path: pathlib.Path) -> list:
    """(table, clause) for every UNIQUE written inside a CREATE TABLE body."""
    out = []
    for match in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);",
                             path.read_text(encoding="utf-8"), re.S):
        table, body = match.group(1), match.group(2)
        for line in body.splitlines():
            line = line.split("--")[0].strip().rstrip(",")
            if line.upper().startswith("UNIQUE ("):
                out.append((table, line))
    return out


def test_uniqueness_is_declared_as_an_index_and_never_inside_a_table():
    """A UNIQUE clause in a CREATE TABLE body never reaches a database that
    already exists — and unlike a missing column, it fails nothing at the point
    of use. It silently permits the write it existed to refuse.

    Two quorum constraints shipped that way. The commit message said a quorum
    was now a number of people, the suite proved it on a fresh database, and on
    every database that already existed one dual-hatted principal was still a
    quorum of one. `CREATE UNIQUE INDEX IF NOT EXISTS` applies to a table that
    already exists, in both dialects, with no migration step — so uniqueness is
    written that way and this holds the line.

    PRIMARY KEY is exempt: it is part of creating the table at all, and there is
    no version of this platform whose tables lack one.
    """
    for path in (SQLITE, POSTGRES):
        clauses = _unique_clauses(path)
        assert not clauses, (
            f"{path.name} declares uniqueness inside a CREATE TABLE body, where "
            f"it will never reach an existing database: {clauses}. Write it as "
            f"CREATE UNIQUE INDEX IF NOT EXISTS instead.")


def test_both_dialects_declare_the_same_indexes():
    """The indexes are as much of the schema as the columns, and now that
    uniqueness lives in them, a dialect missing one is a dialect missing a
    control rather than missing a bit of speed."""
    def names(path):
        return {(m.group(2), m.group(1), "UNIQUE" in m.group(0).upper())
                for m in re.finditer(
                    r"CREATE\s+(?:UNIQUE\s+)?INDEX IF NOT EXISTS (\w+)\s+ON (\w+)",
                    path.read_text(encoding="utf-8"), re.I)}

    only_sqlite = names(SQLITE) - names(POSTGRES)
    only_postgres = names(POSTGRES) - names(SQLITE)
    assert not only_sqlite and not only_postgres, \
        f"only in sqlite: {sorted(only_sqlite)}; only in postgres: {sorted(only_postgres)}"


def test_the_reference_index_reads_every_table_that_carries_a_model_id():
    """Every table with a `model_id` is either QUERIED or has a disposition.

    This test used to assert that the table's name appeared *somewhere in
    `index.py`*, and it passed while four tables went unread: `validation`,
    `version_approval`, `model_assumption` and `model_limitation`. All four
    names are in the file — in prose, in a `why` clause, as a `Reference`
    kind — so the substring match found them and reported the control present.

    What that cost: a model with an unfinished validation, or a version
    approval still being collected, reported `deletable: true` with zero
    references, and deleting it went through. The failure mode of a reference
    check is not an error. It is approval.

    So the assertion is now about **reaching** the table, and there are two
    ways to reach one — a real `FROM`, or a declared disposition in
    `core/retention/cascade.py`. A name in a sentence is not a third way.
    """
    from core.retention.cascade import CASCADE

    index = (ROOT / "core" / "references" / "index.py").read_text(encoding="utf-8")
    carrying = set()
    for match in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);",
                             SQLITE.read_text(encoding="utf-8"), re.S):
        if re.search(r"^\s+model_id\s+\w", match.group(2), re.M):
            carrying.add(match.group(1))

    # A literal FROM, or the f-string loop's `FROM {table}` with the name
    # leading one of its tuples. Both are real queries; prose is not.
    queried = set(re.findall(r"FROM ([a-z_]+)", index))
    queried |= {t for t in carrying
                if re.search(rf'\(\s*"{t}", "[^"]*",', index)}
    declared = {d.table for d in CASCADE}

    unreached = sorted(carrying - queried - declared)
    assert not unreached, (
        f"these tables carry a model_id and nothing reaches them — not a "
        f"query in the reference index, not a disposition in the cascade — so "
        f"deleting a model orphans their rows while the dependency screen "
        f"reports that nothing refers to it: {unreached}")
    assert len(carrying) >= 38, \
        "the scan found fewer tables than expected; check the pattern"
