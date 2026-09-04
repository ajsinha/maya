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
