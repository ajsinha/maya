"""
MAYA — where a feature view's values come from, when they are not uploaded.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A source is **pulled, never read through**.

That distinction is the whole design. MAYA fetches from the SQL query, the file
or the object store, and writes what it got into its own Delta table as a new
feature view version — with the same two clocks, the same quality measurement
and the same immutability as an upload. It does not, and will not, serve a
model straight off somebody's warehouse table.

Reading through would give away every guarantee this platform exists to make:

  * **Point-in-time.** The whole register rests on `event_ts` and `ingest_ts`
    and on `min(label_ts, as_of)`. A warehouse table that has been overwritten
    since March cannot answer what was knowable in March. It will answer
    something, which is worse.
  * **Reproducibility.** A training set built from a live query is not a
    training set; it is a description of one. Re-running it next week gives
    different rows and the same digest is impossible to produce.
  * **Provenance.** "Where did this number come from" has to have an answer
    that survives the source being dropped, renamed or truncated. A pulled
    version has one; a passthrough has a connection string.

So: declare a source, pull it, and what you get is an ordinary version of an
ordinary view — auditable, pinnable, exportable, and MAYA's.

**No secret is stored here.** A source names a `credential_ref`; resolving that
name is the deployment's job, through configuration or the environment. A
register holding a warehouse password is a register nobody can export, and this
platform's whole point is that the register can be handed to an auditor.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.features.common import ENTITY, INGEST_TIME, VALID_TIME, FeatureError
from core.log import get_logger, swallowed

logger = get_logger(__name__)

#: What MAYA will talk to. Each is a way of GETTING a table, and nothing here
#: is a way of writing one back.
SQL, FILE, S3, GCS = "sql", "file", "s3", "gcs"
KINDS: Tuple[str, ...] = (SQL, FILE, S3, GCS)

#: The file formats a source may be in. CSV and JSONL first because that is
#: what somebody actually has; Parquet and Arrow because that is what a job
#: produces. MAYA stores what it pulls in **Delta**, whatever it arrived as.
CSV, JSONL, PARQUET, ARROW = "csv", "jsonl", "parquet", "arrow"
FORMATS: Tuple[str, ...] = (CSV, JSONL, PARQUET, ARROW)

#: Suffixes that identify a format when the locator carries one, so a person
#: giving a path does not also have to say what it is.
BY_SUFFIX: Dict[str, str] = {
    ".csv": CSV, ".tsv": CSV, ".jsonl": JSONL, ".ndjson": JSONL,
    ".parquet": PARQUET, ".arrow": ARROW,
}

#: A statement that is not a read. Checked with a word-boundary match on the
#: FIRST keyword rather than by searching anywhere, because "SELECT ... FROM
#: updates" is a perfectly good query and refusing it would be a control that
#: refuses correct work — which people then route around.
_WRITE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|"
    r"MERGE|REPLACE|ATTACH|COPY|CALL|EXEC)\b", re.I)

#: More than one statement. A source is one query; a semicolon in the middle is
#: either a mistake or somebody appending a second statement to a read.
_TERMINATOR = re.compile(r";\s*\S")


def _as_epoch(value: Any) -> Any:
    """A date or datetime as epoch seconds; everything else untouched.

    Parquet and Arrow carry real timestamp types and MAYA's two clocks are
    epoch seconds, so a `event_ts` column arriving as a `datetime` would be
    stored as a string and every point-in-time comparison after it would be a
    string comparison — which sorts "2026-1-9" after "2026-10-1" and answers
    the question wrongly rather than refusing.

    A naive datetime is read as UTC. Guessing a local zone for data that came
    from somebody else's warehouse would be inventing an offset, and an hour is
    exactly the size of error nobody notices.
    """
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value.timestamp()
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day,
                                 tzinfo=datetime.timezone.utc).timestamp()
    return value


class SourceError(FeatureError):
    """A source could not be declared, reached, or read."""


def _digest(rows: List[Dict[str, Any]]) -> str:
    """A stable digest of what was pulled.

    Over the ROWS rather than over the bytes, because the same table read twice
    through two drivers is the same data and should say so — and because a
    CSV's whitespace is not a fact about the feature.
    """
    canonical = json.dumps(rows, sort_keys=True, default=str,
                           separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


class SourceRegistry:
    """Declare, inspect and pull the sources that fill feature views."""

    def __init__(self, repo, views, evidence, credentials=None):
        self.repo = repo
        self.views = views
        self.evidence = evidence
        # A callable that turns a credential NAME into whatever the connector
        # needs. Injected so the register never has to know what a secret looks
        # like, and so a test can supply one without a warehouse.
        self.credentials = credentials or (lambda name: None)

    # ------------------------------------------------------------- declaring
    def declare(self, view_name: str, kind: str, locator: str, *,
                statement: str = "", fmt: str = "", options: Optional[Dict] = None,
                credential_ref: Optional[str] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Record where a view's values come from. Does not pull.

        Declaring and pulling are separate acts on purpose: one says where the
        data lives and is a governance decision somebody signs for, the other
        moves bytes and happens on a schedule.
        """
        view = self.views.require(view_name)
        kind = (kind or "").strip().lower()
        if kind not in KINDS:
            raise SourceError(
                f"'{kind}' is not a kind of source; MAYA reads {', '.join(KINDS)}",
                remediation="use one of those, or upload the values instead")
        if not (locator or "").strip():
            raise SourceError("a source needs a locator — a connection URL, a "
                              "path, or an s3:// URI",
                              remediation="say where the data is")

        fmt = self._format_for(kind, locator, fmt)
        if kind == SQL:
            self._check_statement(statement)
        existing = self.repo.one(view_name=view_name)
        if existing and not existing.get("retired_at"):
            raise SourceError(
                f"'{view_name}' already reads from a {existing['kind']} source",
                remediation="amend that one, retire it, or declare a second "
                            "view — a view filled from two places at once has "
                            "a provenance nobody can state")

        row = {
            "view_name": view_name, "kind": kind, "locator": locator.strip(),
            "statement": (statement or "").strip(), "format": fmt,
            "options": json.dumps(options or {}), "credential_ref": credential_ref,
            "enabled": True, "created_by": actor, "created_at": time.time(),
        }
        with self.evidence.recording():
            self.repo.add(row)
            self.evidence.append(
                "feature_source_declared", "feature_view", view["id"],
                {"view": view_name, "kind": kind, "locator": locator,
                 "format": fmt, "credential_ref": credential_ref,
                 # The STATEMENT is recorded and the credential is not. What
                 # was read is a governance fact; how we authenticated is not.
                 "statement": row["statement"]},
                actor=actor)
        logger.info("declared a %s source for feature view %s", kind, view_name)
        return self.repo.one(view_name=view_name)

    def _format_for(self, kind: str, locator: str, fmt: str) -> str:
        if kind == SQL:
            return ""
        fmt = (fmt or "").strip().lower()
        if not fmt:
            for suffix, guess in BY_SUFFIX.items():
                if locator.lower().endswith(suffix):
                    fmt = guess
                    break
        if fmt not in FORMATS:
            raise SourceError(
                f"a {kind} source needs a format; '{fmt or locator}' does not "
                f"say which of {', '.join(FORMATS)} it is",
                remediation="name the format, or give a path whose suffix does")
        return fmt

    @staticmethod
    def _check_statement(statement: str) -> None:
        """A source reads. Anything else is refused before it is stored.

        Checked at DECLARATION rather than at pull, because a statement nobody
        may run is a statement nobody should be able to save — and the moment
        it is saved, somebody will schedule it.
        """
        text = (statement or "").strip()
        if not text:
            raise SourceError(
                "a SQL source needs a statement to read",
                remediation="give the SELECT that produces the rows")
        if _WRITE.match(text):
            raise SourceError(
                f"a source may only read, and this starts with "
                f"'{text.split()[0].upper()}'",
                remediation="give a SELECT; a source that can write is not a "
                            "source, and this is refused before it is stored "
                            "rather than before it is run")
        if _TERMINATOR.search(text):
            raise SourceError(
                "a source is one statement, and this is more than one",
                remediation="remove everything after the first `;` — a second "
                            "statement appended to a read is how a read stops "
                            "being one")

    def amend(self, view_name: str, fields: Dict[str, Any],
              actor: str = "system") -> Dict[str, Any]:
        """Change where it reads from. The same checks the declaration made."""
        row = self.require(view_name)
        allowed = {"locator", "statement", "format", "options",
                   "credential_ref", "enabled"}
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise SourceError(
                f"a source has no {', '.join(unknown)} to change",
                remediation=f"the fields that may be amended are "
                            f"{', '.join(sorted(allowed))}")
        merged = {**row, **fields}
        if merged["kind"] == SQL and "statement" in fields:
            self._check_statement(merged["statement"])
        if merged["kind"] != SQL and ("locator" in fields or "format" in fields):
            merged["format"] = self._format_for(
                merged["kind"], merged["locator"], merged.get("format", ""))
            fields = {**fields, "format": merged["format"]}
        if isinstance(fields.get("options"), dict):
            fields = {**fields, "options": json.dumps(fields["options"])}
        with self.evidence.recording():
            self.repo.set(fields, view_name=view_name)
            self.evidence.append(
                "feature_source_amended", "feature_view",
                self.views.require(view_name)["id"],
                {"view": view_name, "changed": sorted(fields)}, actor=actor)
        return self.require(view_name)

    def retire(self, view_name: str, reason: str,
               actor: str = "system") -> Dict[str, Any]:
        """Stop reading from it. The versions it already produced stand."""
        self.require(view_name)
        with self.evidence.recording():
            self.repo.set({"retired_at": time.time(), "retired_by": actor,
                           "retire_reason": reason, "enabled": False},
                          view_name=view_name)
            self.evidence.append(
                "feature_source_retired", "feature_view",
                self.views.require(view_name)["id"],
                {"view": view_name, "reason": reason}, actor=actor)
        return self.repo.one(view_name=view_name)

    # -------------------------------------------------------------- reading
    def get(self, view_name: str) -> Optional[Dict[str, Any]]:
        row = self.repo.one(view_name=view_name)
        return self._decode(row) if row else None

    def require(self, view_name: str) -> Dict[str, Any]:
        row = self.get(view_name)
        if row is None or row.get("retired_at"):
            raise SourceError(
                f"feature view '{view_name}' has no source to read from",
                remediation="declare one, or upload the values")
        return row

    def all(self) -> List[Dict[str, Any]]:
        return [self._decode(r) for r in self.repo.many()]

    @staticmethod
    def _decode(row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        if isinstance(out.get("options"), str):
            try:
                out["options"] = json.loads(out["options"] or "{}")
            except ValueError as exc:
                swallowed(logger, exc, f"read the options of {out.get('view_name')}",
                          detail="left as text; the pull will refuse rather "
                                 "than guess what was meant")
                out["options"] = {}
        return out

    # ---------------------------------------------------------- the pulling
    def preview(self, view_name: str, limit: int = 20) -> Dict[str, Any]:
        """Read a few rows and say what came back. Writes nothing.

        The thing somebody does before committing a source to a schedule, and
        the only way to find out that a column is named `asof` rather than
        `event_ts` without producing a version that says so.
        """
        source = self.require(view_name)
        rows = list(self._read(source, limit=limit))
        columns = sorted({key for row in rows for key in row})
        missing = [c for c in (ENTITY, VALID_TIME, INGEST_TIME) if c not in columns]
        return {
            "view": view_name, "kind": source["kind"], "rows": rows[:limit],
            "row_count": len(rows), "columns": columns,
            "missing_required": missing,
            "usable": not missing,
            "detail": (
                "every required column is there; a pull would produce a version"
                if not missing else
                f"the source does not supply {', '.join(missing)}. Map them in "
                f"the source's options, or fix the query — a row without both "
                f"clocks is refused at load, and it is refused here so that it "
                f"is refused before a version exists rather than after"),
        }

    def pull(self, view_name: str, actor: str = "system",
             feature_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fetch everything the source has and write it as a NEW version.

        A version, not an update. The previous version keeps serving exactly
        what it served, because it is a different Delta path — so a warrant
        pinned to it does not change meaning because somebody refreshed the
        source. That is the entire reason MAYA pulls rather than reads through.
        """
        source = self.require(view_name)
        if not source.get("enabled"):
            raise SourceError(
                f"the source for '{view_name}' is switched off",
                remediation="enable it, or upload the values instead")
        began = time.time()
        rows = list(self._read(source))
        if not rows:
            raise SourceError(
                f"the source for '{view_name}' returned no rows",
                remediation="a version of nothing is not a version; check the "
                            "query or the path. Nothing has been written")
        digest = _digest(rows)
        unchanged = digest == source.get("last_pull_digest")

        version = self.views.materialise(view_name, rows,
                                         feature_names=feature_names,
                                         actor=actor)
        took = time.time() - began
        detail = (f"{len(rows):,} row(s) from {source['kind']} in {took:.1f}s"
                  + (" — the same bytes as the last pull" if unchanged else ""))
        # One transaction. The row that says "pulled, this many rows, this
        # digest" and the evidence node that attests it are the same fact
        # written twice; a failure between them would leave a pull that
        # happened and a chain that does not say so — which is the one shape of
        # inconsistency a governance register cannot have.
        with self.evidence.recording():
            self.repo.set({"last_pulled_at": time.time(),
                           "last_pull_rows": len(rows),
                           "last_pull_digest": digest,
                           "last_pull_detail": detail,
                           "last_pull_version": version.get("version")},
                          view_name=view_name)
            self.evidence.append(
                "feature_source_pulled", "feature_view",
                self.views.require(view_name)["id"],
                {"view": view_name, "kind": source["kind"],
                 "locator": source["locator"], "rows": len(rows),
                 "digest": digest, "version": version.get("version"),
                 # Said explicitly, because "we refreshed and nothing changed"
                 # is a fact a reviewer wants and a silent no-op is not.
                 "unchanged": unchanged},
                actor=actor)
        logger.info("pulled %s rows into %s v%s from a %s source",
                    len(rows), view_name, version.get("version"), source["kind"])
        return {"view": view_name, "version": version.get("version"),
                "rows": len(rows), "digest": digest, "unchanged": unchanged,
                "detail": detail}

    # -------------------------------------------------------- the connectors
    def _read(self, source: Dict[str, Any],
              limit: Optional[int] = None) -> Iterable[Dict[str, Any]]:
        kind = source["kind"]
        if kind == SQL:
            rows = self._read_sql(source, limit)
        else:
            rows = self._read_object(source, limit)
        mapping = (source.get("options") or {}).get("columns") or {}
        for row in rows:
            yield self._apply_mapping(row, mapping)

    @staticmethod
    def _apply_mapping(row: Dict[str, Any],
                       mapping: Dict[str, str]) -> Dict[str, Any]:
        """Rename the source's columns to MAYA's.

        A warehouse calls the entity `customer_number` and the clock `asof`.
        Renaming here rather than making somebody rewrite their query is the
        difference between a source people declare and a source people export
        a CSV to avoid.
        """
        if not mapping:
            return dict(row)
        out = dict(row)
        for theirs, ours in mapping.items():
            if theirs in out:
                out[ours] = out.pop(theirs)
        return out

    def _read_sql(self, source: Dict[str, Any],
                  limit: Optional[int]) -> List[Dict[str, Any]]:
        import sqlalchemy as sa

        url = source["locator"]
        credential = self.credentials(source.get("credential_ref"))
        try:
            engine = sa.create_engine(url, **(credential or {}))
        except Exception as exc:
            logger.warning("could not open a %s source at %s: %s",
                           source["kind"], url, exc)
            raise SourceError(
                f"could not open the connection: {exc}",
                remediation="check the URL, and that the driver it names is "
                            "installed in this deployment") from exc
        statement = source["statement"]
        self._check_statement(statement)
        try:
            with engine.connect() as connection:
                result = connection.execute(sa.text(statement))
                if limit:
                    # `fetchmany` and stop. Reading the whole result and then
                    # slicing is what this did, which means a PREVIEW of a
                    # warehouse table drags the warehouse table across the wire
                    # — and preview is the thing somebody does before they are
                    # sure the query is right. Driver-agnostic, because
                    # wrapping the statement in a LIMIT would mean this module
                    # knowing every dialect's spelling of one.
                    rows = [dict(r) for r in result.mappings().fetchmany(limit)]
                    result.close()
                else:
                    rows = [dict(r) for r in result.mappings()]
        except Exception as exc:
            logger.warning("a source refused the read for %s: %s",
                           source["view_name"], exc)
            raise SourceError(
                f"the source refused the read: {exc}",
                remediation="run the statement against that database yourself; "
                            "the message above is the database's own") from exc
        finally:
            engine.dispose()
        return rows

    def _read_object(self, source: Dict[str, Any],
                     limit: Optional[int]) -> List[Dict[str, Any]]:
        """A file, or an object in a store. Read with pyarrow, which brings its
        own S3, GCS and local filesystems — so an object store is not a new
        dependency, it is the same reader with a different prefix."""
        table = self._arrow_table(source)
        if limit:
            table = table.slice(0, limit)
        # `to_pylist` gives plain dicts, which is what `materialise` takes.
        return [{key: _as_epoch(value) for key, value in row.items()}
                for row in table.to_pylist()]

    def _arrow_table(self, source: Dict[str, Any]):
        import pyarrow as pa
        import pyarrow.csv
        import pyarrow.fs
        import pyarrow.json
        import pyarrow.parquet

        kind, locator, fmt = source["kind"], source["locator"], source["format"]
        options = source.get("options") or {}
        try:
            if kind == FILE:
                filesystem: Any = pyarrow.fs.LocalFileSystem()
                path = locator
            else:
                stripped = re.sub(r"^[a-z0-9]+://", "", locator)
                if kind == S3:
                    filesystem = pyarrow.fs.S3FileSystem(
                        **{k: v for k, v in {
                            "region": options.get("region"),
                            "endpoint_override": options.get("endpoint"),
                            **(self.credentials(source.get("credential_ref")) or {}),
                        }.items() if v is not None})
                else:
                    filesystem = pyarrow.fs.GcsFileSystem(
                        **(self.credentials(source.get("credential_ref")) or {}))
                path = stripped
            with filesystem.open_input_file(path) as handle:
                if fmt == CSV:
                    return pyarrow.csv.read_csv(
                        handle,
                        parse_options=pyarrow.csv.ParseOptions(
                            delimiter=options.get("delimiter", ",")))
                if fmt == JSONL:
                    return pyarrow.json.read_json(handle)
                if fmt == PARQUET:
                    return pyarrow.parquet.read_table(handle)
                if fmt == ARROW:
                    return pa.ipc.open_stream(handle).read_all()
        except SourceError:
            # Already a refusal with its own sentence; re-raised untouched, and
            # `guard()` logs it as the refusal it is.
            logger.info("re-raising a source refusal for %s", source["view_name"])
            raise
        except FileNotFoundError as exc:
            logger.warning("no object at %s for %s", locator, source["view_name"])
            raise SourceError(
                f"nothing at {locator}",
                remediation="check the path; MAYA reads it as the user this "
                            "process runs as") from exc
        except Exception as exc:
            logger.warning("could not read %s for %s: %s",
                           locator, source["view_name"], exc)
            raise SourceError(
                f"could not read {locator}: {exc}",
                remediation="check the location, the format, and — for an "
                            "object store — that the credential named by this "
                            "source is configured in this deployment") from exc
        raise SourceError(f"'{fmt}' is not a format MAYA reads",
                          remediation=f"one of {', '.join(FORMATS)}")


__all__ = [
    "ARROW",
    "CSV",
    "FILE",
    "FORMATS",
    "GCS",
    "JSONL",
    "KINDS",
    "PARQUET",
    "S3",
    "SQL",
    "SourceError",
    "SourceRegistry",
]
