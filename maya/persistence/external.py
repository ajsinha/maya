"""
Reading from external SQL sources (§5.2, §21.1) — SQLAlchemy stays in this package.

Every query MAYA runs against someone else's database is:

* a single ``SELECT`` or ``WITH`` statement — anything else is refused before a
  connection is opened;
* parameterised: values are bound, never interpolated into the text;
* executed over a connection opened read-only at the driver level (SQLite
  ``mode=ro``; PostgreSQL ``default_transaction_read_only``), so a statement that
  slipped past the text check still cannot write;
* authenticated with a password taken from the environment at the moment of
  use, never stored in MAYA's database or configuration.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from maya.core.errors import ValidationFailed

_LEADING = re.compile(r"^\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*", re.S)
_FORBIDDEN = re.compile(r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|"
                        r"revoke|copy|call|execute|attach|detach|pragma|vacuum|replace)\b", re.I)


def check_query(query: str) -> str:
    """The query, if it is one read-only statement. Refuses anything else, naming why."""
    body = _LEADING.sub("", query or "").strip().rstrip(";").strip()
    if not body:
        raise ValidationFailed("The SQL source has no query")
    if ";" in _strip_strings(body):
        raise ValidationFailed("One statement only: a ';' inside the query is refused")
    if not re.match(r"(?is)^(select|with)\b", body):
        raise ValidationFailed("Only SELECT (or WITH … SELECT) queries are allowed")
    hit = _FORBIDDEN.search(_strip_strings(body))
    if hit:
        raise ValidationFailed(f"'{hit.group(1)}' is not allowed in a source query")
    return body


def _strip_strings(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_url(url: str) -> str:
    """A connection URL may name a user but never carry a password."""
    try:
        parsed = make_url(url)
    except Exception as exc:  # noqa: BLE001 - any parse failure is the user's to fix
        raise ValidationFailed(f"Not a database URL: {exc}") from exc
    if parsed.password:
        raise ValidationFailed("Put the password in an environment variable and name it in "
                               "password_env; MAYA never stores database passwords")
    if parsed.get_backend_name() not in ("sqlite", "postgresql"):
        raise ValidationFailed("Supported source databases: sqlite, postgresql")
    return url


def _read_only_engine(url: str, password_env: str | None) -> Any:
    parsed = make_url(url)
    if password_env:
        secret = os.environ.get(password_env)
        if secret is None:
            raise ValidationFailed(f"Environment variable '{password_env}' holding the "
                                   "connection's password is not set on this server")
        parsed = parsed.set(password=secret)
    if parsed.get_backend_name() == "sqlite":
        path = parsed.database or ""
        return create_engine(f"sqlite:///file:{path}?mode=ro&uri=true")
    return create_engine(parsed, connect_args={
        "options": "-c default_transaction_read_only=on -c statement_timeout=300000"})


def read_query(url: str, password_env: str | None, query: str,
               params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Run one validated, parameterised, read-only query and return its rows."""
    body = check_query(query)
    engine = _read_only_engine(url, password_env)
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(body), conn, params=params or {})
    finally:
        engine.dispose()


def test_connection(url: str, password_env: str | None) -> dict[str, Any]:
    engine = _read_only_engine(check_url(url), password_env)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True, "dialect": engine.dialect.name}
    except Exception as exc:  # noqa: BLE001 - reported to the administrator
        return {"ok": False, "error": str(exc).splitlines()[0][:300]}
    finally:
        engine.dispose()
