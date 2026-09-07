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
from contextvars import ContextVar
from typing import Any, ClassVar, Dict, List, Optional, Set

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import Engine

from core.log import get_logger, swallowed

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


class Database:
    """Owns the engine and applies the schema for the configured dialect."""

    #: How long a SQLite connection waits for a lock before giving up. Thirty
    #: seconds rather than the driver's five: every write here is short, so a
    #: wait this long means real contention, and the right answer to real
    #: contention is to queue rather than to lose the write.
    BUSY_TIMEOUT_MS = 30_000

    def __init__(self, url: str = "sqlite:///data/sqlite/maya.db", echo: bool = False):
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
        path = self.schema_file()
        with self.engine.begin() as conn:
            for stmt in self._statements(path.read_text()):
                conn.execute(text(stmt))
        logger.info("schema applied from %s (%s)", path.name, self.dialect)
        self.check_drift()

    # --------------------------------------------------------------- drift
    def columns_of(self, table: str) -> List[str]:
        """The columns a table actually has, from the database itself."""
        try:
            return [c["name"] for c in inspect(self.engine).get_columns(table)]
        except Exception as exc:                          # pragma: no cover
            swallowed(logger, exc, f"inspected columns of '{table}'",
                      detail="treated as absent")
            return []

    def declared_schema(self) -> Dict[str, Set[str]]:
        """Table to columns, parsed out of the shipped DDL.

        Deliberately a small parser rather than a dependency: the DDL is
        hand-written, has no foreign keys, no CHECK and no triggers, and the
        only thing needed here is which columns each CREATE TABLE declares.
        """
        declared: Dict[str, Set[str]] = {}
        for stmt in self._statements(self.schema_file().read_text()):
            match = _CREATE_TABLE.match(_without_trailing_comments(stmt))
            if not match:
                continue
            table, body = match.group(1), match.group(2)
            columns = set()
            depth = 0
            current = ""
            for ch in body:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if ch == "," and depth == 0:
                    columns.add(current.strip().split()[0] if current.strip() else "")
                    current = ""
                else:
                    current += ch
            if current.strip():
                columns.add(current.strip().split()[0])
            declared[table] = {c for c in columns
                               if c and c.upper() not in _NOT_A_COLUMN}
        return declared

    def declared_indexes(self) -> Dict[str, Set[str]]:
        """Table to the index names the shipped DDL creates."""
        declared: Dict[str, Set[str]] = {}
        for stmt in self._statements(self.schema_file().read_text()):
            match = _CREATE_INDEX.match(_without_trailing_comments(stmt))
            if match:
                declared.setdefault(match.group(2), set()).add(match.group(1))
        return declared

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
        """
        gaps: Dict[str, List[str]] = {}
        for table, columns in self.declared_schema().items():
            live = set(self.columns_of(table))
            if not live:
                gaps[table] = ["the table is absent"]
                continue
            if missing := sorted(columns - live):
                gaps[table] = [f"missing column '{c}'" for c in missing]
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
        if gaps:
            detail = "; ".join(f"{t}: {', '.join(why)}" for t, why in sorted(gaps.items()))
            logger.error(
                "SCHEMA DRIFT — the database does not match the shipped DDL: %s. "
                "The schema is applied with CREATE TABLE IF NOT EXISTS, so an "
                "existing table is skipped and a new column is never added. "
                "Apply the difference by hand before serving traffic; queries "
                "touching these columns will fail at the point of use, not here.",
                detail)
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
