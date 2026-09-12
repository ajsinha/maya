"""
MAYA — database connection and schema application.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from pathlib import Path
from contextlib import contextmanager
import logging
from contextvars import ContextVar
from typing import (Any, ClassVar, Dict, List, Optional, Sequence,
                    Set)

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.schema import CreateTable
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import Engine

from core.log import get_logger, swallowed
from db.schema.tables import METADATA

logger = get_logger(__name__)

# Enough to read a hand-written CREATE TABLE. Not a SQL parser, and not trying
# to be: the shipped DDL has no foreign keys, no CHECK and no triggers.
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*)\)\s*$",
    re.S | re.I)

_CREATE_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+"
    r"ON\s+(\w+)\s*\(", re.S | re.I)

# Words that begin a table constraint rather than a column.
_NOT_A_COLUMN = {"PRIMARY", "UNIQUE", "CONSTRAINT", "FOREIGN", "CHECK", "INDEX"}


def _without_trailing_comments(sql: str) -> str:
    """Drop `-- …` from the end of each line.

    `_statements` removes lines that BEGIN with a comment, which is all it
    needed to do for splitting on semicolons. A column list also carries
    comments after the column, and reading those as columns produced a drift
    report naming `--` as a missing column on six tables — a check whose first
    output is nonsense is a check nobody reads twice.

    Quote-aware, because a `--` inside a string default would not be a comment.
    """
    out = []
    for line in sql.splitlines():
        quoted, cut = False, len(line)
        for i, ch in enumerate(line):
            if ch == "'":
                quoted = not quoted
            elif ch == "-" and not quoted and line[i:i + 2] == "--":
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)

# The connection a transaction() is running on, if any. A ContextVar
# rather than a thread local so it is correct under async as well.
_CONNECTION: ContextVar = ContextVar("maya_db_connection", default=None)

# Which named write locks the transaction on `_CONNECTION` currently holds.
# Kept because re-entrancy made `serialise=` silently optional: a nested call
# joined the running transaction and skipped the lock on the grounds that "the
# lock, if any, was taken when it opened" -- which was an ASSUMPTION about the
# caller, not a fact, and it was false at every site that mattered.
_LOCKS_HELD: ContextVar = ContextVar("maya_db_locks", default=frozenset())
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def new_id() -> str:
    """Sortable, non-guessable identifier: millisecond prefix plus randomness."""
    return f"{int(time.time() * 1000):012x}{secrets.token_hex(8)}"


def digest(payload: Any) -> str:
    """Stable SHA-256 over a canonical JSON encoding."""
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class DeltaPaths:
    """Where the Delta tables live. Held here so that no service above the
    persistence package needs to know a filesystem path."""

    AREAS = ("features", "snapshots", "telemetry", "monitoring")

    def __init__(self, root: Path, retention_days: int = 400, **areas: Path):
        self.root, self.retention_days = Path(root), retention_days
        for area in self.AREAS:
            setattr(self, area, Path(areas.get(area) or self.root / area))

    @classmethod
    def from_config(cls, cfg) -> "DeltaPaths":
        root = Path(cfg.get("data.delta.dir", "./data/delta"))
        return cls(root, cfg.get_int("data.delta.retention_days", 400),
                   **{a: cfg.get(f"data.delta.{a}") for a in cls.AREAS})

    def ensure(self) -> "DeltaPaths":
        for p in (self.root, *(getattr(self, a) for a in self.AREAS)):
            p.mkdir(parents=True, exist_ok=True)
        return self


def _family(sa_type: Any) -> str:
    """The kind of thing a column holds, as both dialects would see it.

    Compared by FAMILY rather than by class or by spelling, because the same
    column is legitimately `DOUBLE` here and `DOUBLE PRECISION` there, and
    SQLAlchemy reflects a SQLite `REAL` back as `REAL` and a declared `DOUBLE`
    as `FLOAT`. What matters is whether a value written under one description
    reads correctly under the other, and there are four answers to that.
    """
    name = type(sa_type).__name__.upper()
    text = str(sa_type).upper()
    if "BOOL" in name or "BOOL" in text:
        return "boolean"
    if "INT" in name or "INT" in text:
        return "integer"
    if any(k in name or k in text for k in ("FLOAT", "DOUBLE", "REAL", "NUMERIC",
                                            "DECIMAL")):
        return "number"
    return "text"


class Database:
    """Owns the engine and applies the schema for the configured dialect."""

    #: How long a SQLite connection waits for a lock before giving up. Thirty
    #: seconds rather than the driver's five: every write here is short, so a
    #: wait this long means real contention, and the right answer to real
    #: contention is to queue rather than to lose the write.
    BUSY_TIMEOUT_MS = 30_000

    def __init__(self, url: str = "sqlite:///data/sqlite/maya.db", echo: bool = False):
        # The estate-fold index, or None when there is no fold open. See
        # `folding()`: it exists so that nine per-model sources can keep their
        # exact logic while a cut of the whole register stops being half a
        # million round trips.
        self._fold: Optional[Dict[str, Dict[Any, Dict[Any, List[Dict[str, Any]]]]]] = None
        self.url = url
        options: Dict[str, Any] = {}
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        if ":memory:" in url:
            # An in-memory SQLite database belongs to its CONNECTION, so the
            # default pool hands every caller a different, empty database. That
            # is not a smaller version of production -- it is a topology in
            # which two callers can never contend for anything, and it is why a
            # read-then-write race in the evidence chain survived a suite of
            # eighteen hundred tests.
            #
            # StaticPool keeps one connection, so `:memory:` means ONE database
            # the way a file or a Postgres server does. Tests that need genuine
            # parallel connections use a file-backed URL; see
            # tests/test_concurrency.py.
            options = {"poolclass": StaticPool,
                       "connect_args": {"check_same_thread": False}}
        self.engine: Engine = create_engine(url, echo=echo, future=True, **options)
        self.dialect = self.engine.dialect.name
        if self.dialect == "sqlite":
            self._tune_sqlite(":memory:" not in url)
        self.apply_schema()

    def _tune_sqlite(self, on_disk: bool) -> None:
        """Two pragmas, set on every connection, for the same reason.

        SQLite's default journal makes a writer block every reader for the
        duration of its transaction, and Python's driver gives up after five
        seconds with `database is locked`. Under a scheduler pass, several web
        requests and a monitoring sweep at once, that is not a hypothetical: the
        evidence chain is read-then-write and it is the busiest table here.

        `WAL` lets readers proceed while a write is in flight, which removes
        most of the contention rather than waiting it out. `busy_timeout` waits
        out the rest — a lock held for a moment is normal, and failing the
        request instead of waiting turns a millisecond of contention into a
        governance act that did not happen.

        WAL is a property of the file and does not apply in memory, so it is
        set only on disk. The timeout is per connection either way.
        """
        timeout_ms = self.BUSY_TIMEOUT_MS

        @event.listens_for(self.engine, "connect")
        def _pragmas(connection, _record):        # pragma: no cover - driver hook
            cursor = connection.cursor()
            try:
                if on_disk:
                    cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute(f"PRAGMA busy_timeout={timeout_ms}")
            finally:
                cursor.close()

    def schema_file(self) -> Path:
        """PostgreSQL and SQLite have hand-written schemas; no migrations exist."""
        return SCHEMA_DIR / ("postgres.sql" if self.dialect.startswith("postgres")
                             else "sqlite.sql")

    @staticmethod
    def _statements(sql: str) -> List[str]:
        """Strip comments BEFORE splitting on ';' -- prose in a comment may
        contain a semicolon, and a naive split then produces invalid SQL."""
        body = "\n".join(line for line in sql.splitlines()
                         if not line.lstrip().startswith("--"))
        return [s.strip() for s in body.split(";") if s.strip()]

    def apply_schema(self) -> None:
        """Create what is missing, from the typed metadata.

        `create_all(checkfirst=True)` is CREATE TABLE IF NOT EXISTS by another
        name, so starting against an existing database is still a no-op — and
        an existing table is still SKIPPED rather than altered, which is why
        `drift()` and `repair()` exist below.

        The DDL is generated for this dialect from one declaration rather than
        read from one of two files that had to be kept saying the same thing.
        """
        METADATA.create_all(self.engine, checkfirst=True)
        added = self._create_missing_indexes()
        self._apply_enforcement()
        logger.info("schema applied from db/schema/tables.py — %d tables%s (%s)",
                    len(METADATA.tables),
                    f", {added} index(es) added" if added else "", self.dialect)
        self.check_drift()

    def _apply_enforcement(self) -> int:
        """The triggers that make immutability a constraint rather than a comment.

        Applied HERE and not only rendered into the `.sql` files, because
        `create_all` builds from the typed metadata and never reads those
        files — so a trigger that existed only in the rendered schema would be
        exactly the defect it was written to close: a constraint where a reader
        expects one, enforced by nothing. `db/schema/immutable.py` explains
        what they guard.

        Idempotent by construction — `IF NOT EXISTS` on SQLite, `CREATE OR
        REPLACE` plus `DROP TRIGGER IF EXISTS` on PostgreSQL — so applying to a
        database that already has them is a no-op, like everything else here.
        """
        from db.schema.immutable import (postgres_statements,
                                         sqlite_statements)
        statements = (postgres_statements() if self.dialect == "postgresql"
                      else sqlite_statements())
        applied = 0
        for statement in statements:
            try:
                with self.engine.begin() as conn:
                    conn.execute(text(statement))
                applied += 1
            except Exception as exc:            # pragma: no cover - defensive
                # Reported rather than swallowed. A deployment whose database
                # user cannot create a trigger has the convention and not the
                # constraint, and it needs to know that rather than discover it
                # the day somebody rewrites a version.
                logger.warning(
                    "could not apply an integrity trigger, so that protection "
                    "is a convention on this database rather than a "
                    "constraint: %s", exc)
        logger.info("%d integrity trigger(s) applied (%s)", applied,
                    self.dialect)
        return applied

    def _create_missing_indexes(self) -> int:
        """Create declared indexes that an EXISTING table does not have.

        `create_all` skips a table that exists, and skipping the table skips
        its indexes — so on a deployed database a newly declared uniqueness
        rule would never arrive. That is not a hypothetical: the wave that
        moved every UNIQUE clause out of the table bodies and into
        `CREATE UNIQUE INDEX IF NOT EXISTS` did so precisely because an index
        statement applies to a table that already exists and a table statement
        does not, and the quorum constraint reached deployed instances by that
        route.

        An index is additive and cannot lose a row. It CAN fail, on a table
        whose existing rows already violate the uniqueness it declares — which
        is a real finding about the data and is reported rather than hidden,
        because a constraint that could not be applied is one the deployment
        believes it has.
        """
        added = 0
        for table in METADATA.tables.values():
            if not self.table_exists(table.name):
                continue                    # create_all just made it, indexes and all
            present = set(self.indexes_of(table.name))
            for index in table.indexes:
                if index.name in present:
                    continue
                try:
                    index.create(self.engine, checkfirst=True)
                    added += 1
                    logger.info("created missing index %s on %s",
                                index.name, table.name)
                except Exception as exc:
                    swallowed(logger, exc, f"created index {index.name} "
                                           f"on {table.name}",
                              detail="the drift report will still name it; a "
                                     "unique index refuses where existing rows "
                                     "already violate it, which is a finding "
                                     "about the data",
                              level=logging.ERROR)
        return added

    def table_exists(self, table: str) -> bool:
        try:
            return inspect(self.engine).has_table(table)
        except Exception as exc:                          # pragma: no cover
            swallowed(logger, exc, f"asked whether '{table}' exists",
                      detail="treated as absent")
            return False

    # --------------------------------------------------------------- drift
    def _live_columns(self, table: str) -> Dict[str, Any]:
        """{column: its type}, as the DATABASE describes it rather than as the
        schema declares it. The difference is the whole point of `drift`."""
        try:
            return {c["name"]: c["type"]
                    for c in inspect(self.engine).get_columns(table)}
        except Exception as exc:                          # pragma: no cover
            swallowed(logger, exc, f"inspected columns of '{table}'",
                      detail="treated as absent")
            return {}

    def columns_of(self, table: str) -> List[str]:
        """The columns a table actually has, from the database itself."""
        try:
            return [c["name"] for c in inspect(self.engine).get_columns(table)]
        except Exception as exc:                          # pragma: no cover
            swallowed(logger, exc, f"inspected columns of '{table}'",
                      detail="treated as absent")
            return []

    def declared_schema(self) -> Dict[str, Set[str]]:
        """Table to its column names, from the typed metadata."""
        return {name: {c.name for c in table.columns}
                for name, table in METADATA.tables.items()}

    def declared_indexes(self) -> Dict[str, Set[str]]:
        """Table to the index names the metadata creates.

        A column-level `unique=True` becomes a UNIQUE CONSTRAINT rather than a
        named index, and `indexes_of` reads both — so only real Index objects
        are named here, or drift would report an index nobody declared.
        """
        return {name: {ix.name for ix in table.indexes if ix.name}
                for name, table in METADATA.tables.items()}

    def indexes_of(self, table: str) -> List[str]:
        """The index names a table actually has, from the database itself."""
        try:
            found = {i["name"] for i in inspect(self.engine).get_indexes(table)}
            # A UNIQUE clause inside a CREATE TABLE surfaces as a constraint
            # rather than an index on both dialects, so both are read.
            found |= {c["name"] for c in
                      inspect(self.engine).get_unique_constraints(table)}
            return sorted(n for n in found if n)
        except Exception as exc:                          # pragma: no cover
            swallowed(logger, exc, f"inspected indexes of '{table}'",
                      detail="treated as absent")
            return []

    def declared_columns(self) -> Dict[str, Dict[str, str]]:
        """Table to {column: the DDL fragment this dialect wants for it}.

        `declared_schema` returns names, which is all a drift CHECK needs.
        Repairing one needs the declaration — the type, the default and the
        NOT NULL — because that is what an ALTER has to reproduce, and it must
        be reproduced in the dialect actually in front of us: the same column
        is `DOUBLE` here and `DOUBLE PRECISION` there.

        Compiled by SQLAlchemy rather than assembled by hand, so a repair
        cannot spell a type differently from the CREATE that would have made
        it.
        """
        dialect = self.engine.dialect
        declared: Dict[str, Dict[str, str]] = {}
        for name, table in METADATA.tables.items():
            # The compiler wants the statement it is compiling, so it is given
            # the CREATE that would have made this very table — which is the
            # point: an ALTER must spell a column the way its CREATE would.
            compiler = dialect.ddl_compiler(dialect, CreateTable(table))
            declared[name] = {c.name: compiler.get_column_specification(c)
                              for c in table.columns}
        return declared

    def repair(self, dry_run: bool = True) -> Dict[str, Any]:
        """Add the columns the shipped DDL declares and this database lacks.

        `drift()` reports precisely what is missing and then says "apply the
        difference by hand", which is a real chore and the reason a stale
        development database gets deleted rather than fixed. This closes that
        loop without becoming a migration tool: there is no version history, no
        ordering and no down-step. The consolidated schema is still the only
        description of the shape, and this asks it what is missing and adds
        exactly that.

        `ALTER TABLE ... ADD COLUMN` is non-destructive in both dialects and
        cannot lose a row. What it cannot do is add a NOT NULL column with no
        default to a table that already has rows — there is no value to put in
        the existing ones — so those are REPORTED rather than attempted, with
        the declaration, so somebody can decide what the existing rows should
        say. Guessing on their behalf is how a governance register acquires a
        column full of zeros that nobody chose.
        """
        declared = self.declared_columns()
        planned: List[Dict[str, str]] = []
        refused: List[Dict[str, str]] = []
        # Differences that are REAL and need no action on this dialect. Kept
        # apart from `refused`, because "somebody must decide what the existing
        # rows should say" and "the declaration is stale and nothing behaves
        # differently" are not the same report, and merging them would make an
        # operator go looking for a decision that does not exist.
        noted: List[Dict[str, str]] = []
        for table, columns in sorted(declared.items()):
            live = set(self.columns_of(table))
            if not live:
                continue                    # the table itself is absent
            rows = 0
            missing = [c for c in columns if c not in live]
            if missing:
                found = self.query_one(f"SELECT COUNT(*) AS n FROM {table}")
                rows = int((found or {}).get("n") or 0)
            for name in missing:
                declaration = columns[name]
                upper = declaration.upper()
                if "NOT NULL" in upper and "DEFAULT" not in upper and rows:
                    refused.append({
                        "table": table, "column": name,
                        "declaration": declaration,
                        "why": f"NOT NULL with no default, and {table} already "
                               f"holds {rows} row(s) — there is no value to put "
                               f"in them that somebody has chosen"})
                    continue
                planned.append({"table": table, "column": name,
                                "sql": f"ALTER TABLE {table} ADD COLUMN {declaration}"})

        # TYPES, which `drift()` now reports and a repair had better be able to
        # close — a check that names a problem nothing can fix is a check
        # people learn to scroll past.
        #
        # The two dialects differ in what is possible and in what is NEEDED,
        # and both halves matter.
        #
        # PostgreSQL can change a column's type in place, and here it must:
        # an INTEGER column where the schema says BOOLEAN refuses every write
        # the current code makes. `USING` gives the conversion explicitly
        # rather than hoping for a cast, and the statement rewrites the column
        # without touching any other.
        #
        # SQLite cannot change a column's type at all, short of rebuilding the
        # table — and does not need to. Its affinities mean an `INTEGER` column
        # and a `BOOLEAN` one store a Python bool identically as 0/1 and return
        # it identically, so the declaration is out of date and the BEHAVIOUR
        # is correct. Rebuilding fifty tables of a governance register to
        # change a word in a declaration would be the larger risk by far, so it
        # is reported as needing no action rather than attempted.
        types: List[Dict[str, str]] = []
        postgres = self.dialect.startswith("postgres")
        for name, declared_table in sorted(METADATA.tables.items()):
            live_types = self._live_columns(name)
            for column in declared_table.columns:
                if column.name not in live_types:
                    continue
                want = _family(column.type)
                have = _family(live_types[column.name])
                if want == have:
                    continue
                spelled = column.type.compile(self.engine.dialect)
                step = {"table": name, "column": column.name,
                        "from": have, "to": want}
                if postgres:
                    using = (f"({column.name} <> 0)" if want == "boolean"
                             else f"({column.name}::{spelled})")
                    step["sql"] = (f"ALTER TABLE {name} ALTER COLUMN "
                                   f"{column.name} TYPE {spelled} USING {using}")
                    types.append(step)
                else:
                    noted.append({
                        **step, "declaration": spelled,
                        "why": f"SQLite cannot change a column's type in place, "
                               f"and does not need to: an {have} column stores "
                               f"and returns a {want} identically here. The "
                               f"declaration is stale; the behaviour is not. "
                               f"PostgreSQL is where this matters, and there it "
                               f"is repaired."})

        # Indexes as well as columns, because uniqueness now LIVES in an index
        # and a repair that closed half the drift it reported would leave a
        # deployment believing it held a constraint it does not.
        missing_indexes: List[Dict[str, Any]] = []
        for name, declared_table in sorted(METADATA.tables.items()):
            if not self.table_exists(name):
                continue
            present = set(self.indexes_of(name))
            for index in declared_table.indexes:
                if index.name and index.name not in present:
                    missing_indexes.append({"table": name, "index": index.name,
                                            "unique": bool(index.unique)})

        applied = []
        if not dry_run:
            for step in planned:
                try:
                    self.execute(step["sql"])
                    applied.append(step)
                except Exception as exc:
                    swallowed(logger, exc, f"added {step['table']}.{step['column']}",
                              detail="left for the operator; the drift report "
                                     "will still name it")
                    refused.append({**step, "why": str(exc)})
            for step in types:
                try:
                    self.execute(step["sql"])
                    applied.append(step)
                except Exception as exc:
                    swallowed(logger, exc,
                              f"retyped {step['table']}.{step['column']}",
                              detail="left for the operator; the drift report "
                                     "will still name it")
                    refused.append({**step, "why": str(exc)})
            # After the columns: an index may be ON one of them.
            added_indexes = self._create_missing_indexes()
            logger.warning("schema repaired: %d column(s) added by ALTER TABLE "
                           "and %d index(es) created. This adds what the shipped "
                           "schema declares and nothing else.",
                           len(applied), added_indexes)
        return {
            "indexes": missing_indexes,
            "types": types,
            "noted": noted,
            "planned": planned, "applied": applied, "refused": refused,
            "detail": (
                ", ".join(filter(None, [
                    f"{len(planned)} column(s) can be added" if planned else "",
                    f"{len(types)} column(s) can be retyped" if types else "",
                    f"{len(missing_indexes)} index(es) can be created"
                    if missing_indexes else "",
                    f"{len(refused)} need a decision" if refused else "",
                    f"{len(noted)} stale declaration(s) needing no action here"
                    if noted else ""]))
                or "nothing to repair"),
        }

    def drift(self) -> Dict[str, List[str]]:
        """Where the live database and the shipped DDL disagree.

        `CREATE TABLE IF NOT EXISTS` is how the schema is applied, which means a
        table that already exists is SKIPPED ENTIRELY. Add a column to the DDL,
        deploy onto a database that predates it, and the statement does nothing:
        the application starts cleanly on a schema that does not match its own
        code and fails weeks later, inside a workflow, on a query nobody
        associates with the deployment.

        There is no migration tool here and this is not one. It is the check
        that turns that silence into a sentence at start-up.

        Indexes are checked as well as columns, and the reason is the sharpest
        version of this whole problem. A UNIQUE clause written into a CREATE
        TABLE body is skipped on an existing table exactly as a column is -- but
        unlike a missing column, a missing uniqueness constraint fails NOTHING
        at the point of use. It silently permits the write it existed to refuse.
        Two quorum constraints shipped that way: the commit message said a
        quorum was now a number of people, the suite proved it on a fresh
        database, and on every database that already existed one dual-hatted
        principal remained a quorum of one. Nothing anywhere said so.

        Both are now `CREATE UNIQUE INDEX IF NOT EXISTS`, which DOES apply to an
        existing table in both dialects -- so they arrive on a deployed database
        with no migration step. This check is what catches the next one written
        the other way.

        TYPES are checked too, and that is newer. A column present under the
        right name and the wrong type is the quietest version of this problem:
        the same code writes a Python `bool` into a column declared `BOOLEAN`
        and into one declared `INTEGER`, SQLite stores 0/1 either way, and
        PostgreSQL refuses the second. So a database that predates a type
        change starts cleanly, works on the dialect somebody develops against,
        and fails on the one they deploy to — which is precisely the failure
        this codebase has already had once.
        """
        gaps: Dict[str, List[str]] = {}
        declared_types = {name: {c.name: c.type for c in table.columns}
                          for name, table in METADATA.tables.items()}
        for table, columns in self.declared_schema().items():
            live_columns = self._live_columns(table)
            live = set(live_columns)
            if not live:
                gaps[table] = ["the table is absent"]
                continue
            if missing := sorted(columns - live):
                gaps[table] = [f"missing column '{c}'" for c in missing]
            for name, declared in sorted(declared_types[table].items()):
                if name not in live_columns:
                    continue
                want, have = _family(declared), _family(live_columns[name])
                if want == have:
                    continue
                # Named accurately for the dialect in front of us. On
                # PostgreSQL an INTEGER column where the schema says BOOLEAN
                # refuses every write the current code makes; on SQLite the
                # affinities make the two store and return a truth value
                # identically, so the declaration is stale and nothing behaves
                # differently. Saying "queries will fail" in both cases would
                # be untrue in one of them, and a warning that overstates is
                # one people learn to scroll past.
                harmless = (not self.dialect.startswith("postgres")
                            and {want, have} <= {"boolean", "integer", "number"})
                gaps.setdefault(table, []).append(
                    f"column '{name}' is {have} where the schema says {want}"
                    + (" (stale declaration; no effect on SQLite)" if harmless
                       else ""))
        indexes = self.declared_indexes()
        for table, names in indexes.items():
            if table in gaps and gaps[table] == ["the table is absent"]:
                continue
            if missing := sorted(names - set(self.indexes_of(table))):
                gaps.setdefault(table, []).extend(
                    f"missing index '{i}'" for i in missing)
        return gaps

    def check_drift(self) -> Dict[str, List[str]]:
        """Report the drift, loudly. Reported rather than raised: refusing to
        start would take an instance out of service over a column that may not
        be on any path it serves, and an operator who cannot start the platform
        cannot read its logs either."""
        gaps = self.drift()
        if not gaps:
            return gaps
        detail = "; ".join(f"{t}: {', '.join(why)}"
                           for t, why in sorted(gaps.items()))
        # A stale declaration that changes no behaviour is not the same finding
        # as a column that is not there, and reporting both at ERROR with the
        # same sentence would teach a reader that this line means nothing.
        acting = any("no effect on SQLite" not in why
                     for whys in gaps.values() for why in whys)
        if acting:
            logger.error(
                "SCHEMA DRIFT — the database does not match the schema: %s. It "
                "is applied with CREATE TABLE IF NOT EXISTS, so an existing "
                "table is skipped and a new column is never added. Close it "
                "with `python run_maya_web.py --repair-schema`; until then, "
                "queries touching these will fail at the point of use, not "
                "here.", detail)
        else:
            logger.warning(
                "schema declarations have moved on from this database: %s. "
                "Nothing behaves differently here — `--check-schema` explains "
                "each one — and the same database under PostgreSQL would need "
                "`--repair-schema`.", detail)
        return gaps

    # ------------------------------------------------------------- transaction
    #: Distinct per contended sequence, so two different serialised writes do
    #: not queue behind each other on PostgreSQL. Only the evidence chain uses
    #: one today; the argument is named rather than numbered so a second caller
    #: cannot collide with it by picking the same integer.
    _ADVISORY_LOCKS: ClassVar[Dict[str, int]] = {"evidence_seq": 0x4D415941}

    @contextmanager
    def transaction(self, *, serialise: Optional[str] = None):
        """Run several statements on one connection, committed or rolled back
        together.

        `serialise` names a contended sequence and takes the write lock BEFORE
        the transaction reads anything, which is a stronger thing than atomicity
        and the evidence chain needs it. The chain is read-then-write — take the
        head, insert head+1 — and a plain transaction is deferred: under WAL two
        writers both read the same head, and the second INSERT dies on the UNIQUE
        over `seq`. A retry loop covered it, and under a loaded machine four
        writers exhausted twelve attempts and an append was lost. A lost append
        is not a slow request: segregation of duties is decided by reading the
        chain, so a missing `version_created` node means "you cannot approve what
        you created" has nothing to read.

        SQLite gets `BEGIN IMMEDIATE`, which takes the write lock at BEGIN
        rather than at the first write, so the second writer waits there and
        then reads a head that is actually current. PostgreSQL gets a
        transaction-scoped advisory lock, which releases on commit or rollback
        with no unlock to forget.

        Without this there was no way to make a read and a write atomic, because
        every statement opened its own connection: `execute` began a transaction
        and ended it, and `query` opened a second one that could not see inside
        the first. Anything shaped read-then-write was therefore a race, and the
        evidence chain is exactly that shape -- read the head, insert head+1.

        Re-entrant. A nested call joins the transaction already running rather
        than opening a second one and deadlocking against it, so a service can
        wrap a whole governance act without knowing what its collaborators do.
        """
        existing = _CONNECTION.get()
        if existing is not None:
            held = _LOCKS_HELD.get()
            if serialise is None or serialise in held:
                yield existing
                return
            # A nested call asking for a lock the outer transaction does not
            # hold. This used to yield anyway, on the reasoning that "the lock,
            # if any, was taken when it opened" — an assumption about the
            # caller that was false at every site that mattered.
            # `create_version`, `alias.move` and `approval.sign` each open a
            # plain transaction and call `evidence.append` inside it, so
            # `serialise="evidence_seq"` was dropped on the three most important
            # governance acts in the platform.
            #
            # SQLite hid it: the outer transaction's first statement is an
            # INSERT, which takes SQLite's single write lock before the chain
            # head is read. PostgreSQL has no such lock, so the read-then-write
            # on `evidence_node.seq` was a live race — and when the loser hit
            # the UNIQUE, the OUTER transaction was aborted, so all twelve
            # retries re-entered a poisoned connection and died on
            # InFailedSqlTransaction, which is not IntegrityError and so escaped
            # the retry handler entirely. Sixteen concurrent version creations
            # produced five versions and eleven 500s.
            #
            # Taken here instead. It is later than ideal — the outer
            # transaction may already have read — but the read this lock exists
            # to order is the one BELOW it, inside the nested block, and that
            # read has not happened yet. There is one named lock, so taking it
            # late cannot deadlock against a different ordering. Logged at
            # warning because the outer transaction should ask for it, and this
            # is how the next site that does not gets found.
            logger.warning(
                "'%s' was requested inside a transaction that does not hold "
                "it; taking it now. The outermost transaction should open with "
                "serialise=%r so the lock is held before anything is read.",
                serialise, serialise)
            self._take_write_lock(existing, serialise, nested=True)
            lock_token = _LOCKS_HELD.set(held | {serialise})
            try:
                yield existing
            finally:
                _LOCKS_HELD.reset(lock_token)
            return
        with self.engine.begin() as conn:
            if serialise is not None:
                self._take_write_lock(conn, serialise)
            token = _CONNECTION.set(conn)
            lock_token = _LOCKS_HELD.set(
                frozenset({serialise}) if serialise else frozenset())
            try:
                yield conn
            finally:
                _LOCKS_HELD.reset(lock_token)
                _CONNECTION.reset(token)

    def _take_write_lock(self, conn: Any, name: str,
                         nested: bool = False) -> None:
        """Escalate to a write lock now, before the transaction reads."""
        if self.dialect == "sqlite":
            if nested:
                # `BEGIN IMMEDIATE` inside a transaction is an error, and it is
                # also unnecessary: SQLite has ONE write lock per database, and
                # the enclosing transaction either already holds it or takes it
                # at its first write, which is before any append can commit.
                # This is why the dropped lock never showed on SQLite.
                return
            # pysqlite defers BEGIN to the first write statement, so nothing has
            # started a transaction yet and this is the BEGIN, not a second one.
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        elif self.dialect.startswith("postgres"):
            # Idempotent within a transaction and released at commit, so taking
            # it from a nested call is safe.
            conn.exec_driver_sql(
                f"SELECT pg_advisory_xact_lock({self._ADVISORY_LOCKS[name]})")

    # ------------------------------------------------------------------ access
    # ----------------------------------------------------------- folding
    #
    # An estate fold asks the same shape of question of every model, and the
    # register answers it one model at a time. `WorkList.for_model` consults
    # nine sources; `Portfolio.by` calls it per model; so a cut of fifty
    # thousand models is most of half a million round trips and takes 33
    # seconds. The shape is wrong rather than any one query being slow — the
    # per-model cost is flat at about 0.67 ms across sizes.
    #
    # The obvious fix is a batched twin of each source, and it is the wrong
    # one: a second implementation of *what a model owes* is a second
    # governance judgement, and the two eventually disagree. So the sources are
    # left exactly as they are and their READS are served from an index built
    # once per fold.
    #
    # Three rules make this safe enough to put under a control plane.
    #
    #   * It is **opt-in and scoped**. Nothing is cached outside the `with`,
    #     and the caller names the tables, so a fold cannot accidentally pull
    #     a telemetry table into memory.
    #   * It is **read-only**. A write inside a fold raises rather than
    #     invalidating quietly, because a fold that silently re-read half its
    #     answers would be worse than a slow one.
    #   * It serves only **single-column equality** reads. Anything else falls
    #     through to the database, so a query this cannot answer correctly is
    #     one it does not answer at all.
    @contextmanager
    def folding(self, tables: Sequence[str]):
        """Serve single-column equality reads on these tables from memory."""
        if self._fold is not None:
            # Nesting would make the inner scope's exit drop the outer scope's
            # index, and the bug that produces is a read that is correct on
            # Tuesday. One fold at a time.
            yield
            return
        self._fold = {t: {} for t in tables}
        try:
            yield
        finally:
            self._fold = None

    def folded(self, table: str, columns: Sequence[str],
               values: Sequence[Any]) -> Optional[List[Dict[str, Any]]]:
        """Rows matching `table.columns = values`, or None outside a fold.

        Indexed on the exact column SET the caller asked for. A single index
        per table would not do: the sources filter on one column and on two —
        `model_id` alone, and `model_id` with a status — and answering a
        two-column question from a one-column index would mean filtering in
        Python, which is the same work this exists to remove.

        Every key is an equality, so the index answers exactly what the SQL
        would have. Anything else never reaches here; see
        `Repository._from_fold`.
        """
        if self._fold is None or table not in self._fold:
            return None
        key = tuple(columns)
        index = self._fold[table].get(key)
        if index is None:
            index = {}
            for row in self.query(f"SELECT * FROM {table}"):
                index.setdefault(tuple(row.get(c) for c in key), []).append(row)
            self._fold[table][key] = index
        return list(index.get(tuple(values), ()))

    def _refuse_write_while_folding(self, table: str) -> None:
        if self._fold is not None and table in self._fold:
            raise RuntimeError(
                f"'{table}' was written during an estate fold. A fold serves "
                f"reads from an index built once; writing to a folded table "
                f"would make the rest of the fold answer from before the "
                f"write, and a governance read that is half-stale is worse "
                f"than a slow one")

    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        conn = _CONNECTION.get()
        if conn is not None:
            return conn.execute(text(sql), params or {}).rowcount
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {}).rowcount

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        conn = _CONNECTION.get()
        if conn is not None:
            return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]

    def query_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, table: str, row: Dict[str, Any]) -> Dict[str, Any]:
        cols = ", ".join(row)
        binds = ", ".join(f":{c}" for c in row)
        self.execute(f"INSERT INTO {table} ({cols}) VALUES ({binds})", row)
        return row

    def update(self, table: str, where: str, params: Dict[str, Any],
               values: Dict[str, Any]) -> int:
        sets = ", ".join(f"{k} = :set_{k}" for k in values)
        merged = {**params, **{f"set_{k}": v for k, v in values.items()}}
        return self.execute(f"UPDATE {table} SET {sets} WHERE {where}", merged)
