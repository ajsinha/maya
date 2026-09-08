"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The two hand-written schema files have to agree, and nothing checked that they did.

There are no migrations here on purpose: `db/schema/sqlite.sql` and
`db/schema/postgres.sql` are the schema, and a row written by one dialect must
read correctly under the other. That is a strong claim and it was resting on
whoever edited one file remembering to edit the other.

It had already failed. Fourteen columns were declared `BOOLEAN` on the Postgres
side while `db/repositories.py` coerced every boolean to `int` on the way in --
and PostgreSQL does not implicitly cast integer to boolean, so every insert
touching one of those tables would have failed and the entire dialect was
unusable. Nothing raised, because nothing ran against Postgres.

So the rule is now absolute and tested: **no BOOLEAN columns anywhere**, in
either dialect or in Delta. Truth values are integer 0 and 1 everywhere, and the
service layer converts to a real bool at its boundary so no consumer has to know
how one is persisted.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SQLITE = ROOT / "db" / "schema" / "sqlite.sql"
POSTGRES = ROOT / "db" / "schema" / "postgres.sql"

# The one substitution PostgreSQL requires. Anything else diverging is a defect.
EQUIVALENT = {frozenset({"REAL", "DOUBLE PRECISION"})}

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


def test_no_schema_declares_a_boolean_column():
    """Integer 0/1, in both dialects. See this module's docstring for what a
    BOOLEAN did to the Postgres dialect the last time one was declared."""
    offenders = []
    for path in (SQLITE, POSTGRES):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            if re.search(r"\bBOOL(EAN)?\b", stripped, re.I):
                offenders.append(f"{path.name}:{number}  {stripped}")
    assert not offenders, (
        "truth values are stored as integer 0 and 1 in every dialect, and these "
        "declare a boolean type:\n    " + "\n    ".join(offenders)
        + "\nUse `INTEGER NOT NULL DEFAULT 0` / `integer NOT NULL DEFAULT 0`.")


def test_both_dialects_declare_the_same_columns():
    sqlite, postgres = _columns(SQLITE), _columns(POSTGRES)
    only_sqlite = sorted(set(sqlite) - set(postgres))
    only_postgres = sorted(set(postgres) - set(sqlite))
    assert not only_sqlite and not only_postgres, (
        "the two schema files describe different tables. A row written by one "
        "dialect would not read under the other.\n"
        f"  only in sqlite.sql:   {only_sqlite}\n"
        f"  only in postgres.sql: {only_postgres}")


def test_every_shared_column_has_an_equivalent_type():
    sqlite, postgres = _columns(SQLITE), _columns(POSTGRES)
    divergent = []
    for key in sorted(set(sqlite) & set(postgres)):
        left, right = sqlite[key], postgres[key]
        if left != right and frozenset({left, right}) not in EQUIVALENT:
            divergent.append(f"{key[0]}.{key[1]}: sqlite {left} vs postgres {right}")
    assert not divergent, (
        "these columns are declared with types that are not equivalent across "
        "the dialects:\n    " + "\n    ".join(divergent))


def test_no_python_bool_can_reach_a_driver():
    """The write path coerces EVERY bool, not a named list of columns.

    There are no BOOLEAN columns in either dialect, so a Python `bool` is never
    the right thing to hand a driver. Naming the columns made the rule depend
    on a hand-maintained list, and a truth column added to the schema and left
    off it would take a real bool — which SQLite silently stores as 0/1 and
    psycopg sends to PostgreSQL as a boolean, where an integer column refuses
    it. Same shape as the defect the no-BOOLEAN rule exists for: it works on
    the dialect the tests run against and fails on the one they do not.
    """
    from db.repositories import Repository

    repo = Repository.__new__(Repository)
    repo.JSON = ()
    encoded = repo._encode({
        "revoked": True,                      # on the list
        "some_column_nobody_listed": False,   # not on it, and the point
        "count": 3, "name": "x", "when": 1.5, "nothing": None})
    for field, value in encoded.items():
        assert not isinstance(value, bool), f"{field} is still a bool"
    assert encoded["revoked"] == 1
    assert encoded["some_column_nobody_listed"] == 0
    assert encoded["count"] == 3 and encoded["name"] == "x"
    assert encoded["when"] == 1.5 and encoded["nothing"] is None


def test_every_truth_column_is_read_back_as_a_bool():
    """The read path still needs the list, and this says why it is the read
    path that does: which integers mean a truth value is a fact about the
    column, not about the value — 0 and 1 are also perfectly good counts."""
    from db.repositories import Repository, _BOOL_COLUMNS

    repo = Repository.__new__(Repository)
    repo.TABLE, repo.JSON = "t", ()
    decoded = repo._decode({"revoked": 1, "blocking": 0, "row_count": 1})
    assert decoded["revoked"] is True and decoded["blocking"] is False
    assert decoded["row_count"] == 1, "a count is not a truth value"
    assert "row_count" not in _BOOL_COLUMNS


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
    """Nineteen tables carry a `model_id`; the index read twelve.

    The dependency screen's own docstring calls a blank result "the most
    dangerous wrong answer this screen can give", and for seven tables that is
    what it gave. Two were reachable with no version at all, which is exactly
    the state in which a model CAN be deleted:

    `risk_assessment` holds the tier, which decides every control requirement
    and every quorum size on the model. `compliance_debt` is raised per gap by
    a baseline import and `DebtRegister.reconcile` is per-model, so debt
    orphaned by a deleted model can never close — the programme's burn-down
    stays below 100% forever, pointing at a model nobody can look up.

    Driven from the schema rather than from a list, so a twentieth table cannot
    be added without a decision about it.
    """
    index = (ROOT / "core" / "references" / "index.py").read_text(encoding="utf-8")
    carrying = set()
    for match in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);",
                             SQLITE.read_text(encoding="utf-8"), re.S):
        if re.search(r"^\s+model_id\s+\w", match.group(2), re.M):
            carrying.add(match.group(1))

    unread = sorted(t for t in carrying if f'"{t}"' not in index)
    assert not unread, (
        f"these tables carry a model_id and the reference index never reads "
        f"them, so deleting a model orphans their rows while the dependency "
        f"screen reports that nothing refers to it: {unread}")
    assert len(carrying) >= 19, \
        "the scan found fewer tables than expected; check the pattern"
