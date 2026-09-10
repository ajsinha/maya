"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A query somebody wants to keep, and an extract somebody wants to send.

**A saved view stores the query and never the rows.** That is the whole design,
and the reason is a disclosure that would otherwise be invisible: an author
whose scope reaches four legal entities saves a view, shares it, and a reader
scoped to one opens it — and if the rows had been stored, that reader now holds
three entities' worth of models because somebody clicked *share*. Storing the
query means the view re-executes under whoever opened it. Two people running the
same view legitimately see different numbers, which is correct, and the answer
says how many rows each reader's scope removed so neither of them attributes the
difference to a bug.

**An export is a disclosure event and is recorded as one.** Not because a
governance platform should be difficult, but because "who took a copy of the
model inventory, and when" is a question that gets asked after something has
gone wrong, and by then the answer has to already exist.

**Three formats, and a fourth refused by name.** CSV for the thing somebody will
open in a spreadsheet, Parquet for the thing a data platform will read, JSON for
the thing a script will parse. Not `.xlsx`: a binary workbook cannot be diffed,
carries formulas and formatting that are not in the register, and invites the
edit-then-circulate cycle that turns an extract into an unversioned second
source of truth. CSV opens in Excel. The refusal names the reason rather than
letting the format quietly be absent, because an unexplained absence reads as an
oversight and gets raised as one every quarter.
"""
from __future__ import annotations

import csv
import io
import json
import time
from typing import Any, Dict, Optional, Sequence

from core.log import get_logger
from core.reporting.semantics import MAX_ROWS, QueryError

logger = get_logger(__name__)

CSV, PARQUET, JSON = "csv", "parquet", "json"
FORMATS = (CSV, PARQUET, JSON)
MEDIA: Dict[str, str] = {
    CSV: "text/csv",
    PARQUET: "application/vnd.apache.parquet",
    JSON: "application/json",
}
EXTENSIONS: Dict[str, str] = {CSV: ".csv", PARQUET: ".parquet", JSON: ".json"}

#: Formats asked for often enough to be worth refusing by name rather than
#: leaving out. An absence reads as an oversight; a refusal reads as a decision.
REFUSED: Dict[str, str] = {
    "xlsx": ("a binary workbook cannot be diffed, carries formatting and "
             "formulas that are not in the register, and invites the "
             "edit-then-circulate cycle that turns an extract into a second "
             "source of truth nobody versions. CSV opens in Excel"),
    "xls": ("the same objection as xlsx, and a format Microsoft itself has "
            "deprecated"),
    "pdf": ("an extract is data somebody will compute with, and a PDF is data "
            "somebody will retype. The document compiler produces PDFs where a "
            "document is what is wanted"),
}


class SavedViews:
    """Named queries, re-run under whoever opens them, and exported as files."""

    def __init__(self, views, semantics, evidence=None):
        self.views, self.semantics, self.evidence = views, semantics, evidence

    # ------------------------------------------------------------------- save
    def save(self, name: str, entity: str, query: Dict[str, Any],
             owner: str, description: str = "", shared: bool = False,
             now: Optional[float] = None) -> Dict[str, Any]:
        """Keep a query. Validated now, so a broken view is refused at the
        moment its author can still fix it rather than when a committee opens it."""
        if not (name or "").strip():
            raise QueryError("name_required",
                             "a saved view needs a name somebody will recognise",
                             "give it one")
        # Run it once. A view that refuses is refused here, where its author is
        # present, rather than six months later in front of the people it was
        # saved for.
        self.semantics.query(entity, **_runnable(query), limit=1)
        if self.views.one(owner=owner, name=name):
            raise QueryError(
                "view_already_saved",
                f"you already have a view called '{name}'",
                "rename it, or delete the one you have — a second view with "
                "the same name is how two different numbers end up with one "
                "label")
        row = {"name": name.strip(), "entity": entity,
               "description": description.strip(), "query": dict(query),
               "owner": owner, "shared": bool(shared),
               "created_at": now if now is not None else time.time(),
               "last_run_at": None}
        self.views.add(row)
        logger.info("saved view '%s' over %s by %s (shared=%s)", name, entity,
                    owner, shared)
        return self.views.one(id=row["id"])

    def delete(self, view_id: str, actor: str) -> Dict[str, Any]:
        view = self.require(view_id)
        if view["owner"] != actor:
            raise QueryError(
                "not_your_view",
                f"'{view['name']}' belongs to {view['owner']}",
                "ask them to delete it; a shared view somebody else can remove "
                "is one whose disappearance nobody can explain")
        self.views.remove(id=view_id)
        logger.info("deleted view '%s' for %s", view["name"], actor)
        return {"deleted": view_id, "name": view["name"]}

    # -------------------------------------------------------------------- run
    def run(self, view_id: str, reader: str, scope=None,
            limit: Optional[int] = None,
            now: Optional[float] = None) -> Dict[str, Any]:
        """Execute a saved view **under the reader's scope, not the author's**."""
        view = self.require(view_id)
        if view["owner"] != reader and not view["shared"]:
            raise QueryError(
                "view_not_shared",
                f"'{view['name']}' is {view['owner']}'s and is not shared",
                "ask them to share it")
        query = _runnable(view["query"])
        if limit is not None:
            query["limit"] = limit
        moment = now if now is not None else time.time()
        out = self.semantics.query(view["entity"], scope=scope, now=moment,
                                   **query)
        self.views.set({"last_run_at": moment}, id=view_id)
        return {**out, "view": {k: view[k] for k in
                                ("id", "name", "description", "owner", "shared")},
                "run_as": reader,
                "detail": (out["detail"] + ". This ran under your scope rather "
                           "than its author's, which is why a shared view can "
                           "show two readers different numbers")}

    def list(self, reader: str) -> Dict[str, Any]:
        """This reader's own views, plus everything shared with them."""
        mine = self.views.many(owner=reader)
        shared = [v for v in self.views.many(shared=True)
                  if v["owner"] != reader]
        return {"mine": mine, "shared": shared,
                "count": len(mine) + len(shared),
                "detail": (f"{len(mine)} of your own and {len(shared)} shared "
                           f"with you. A shared view carries its query and "
                           f"never its rows, so opening one discloses nothing "
                           f"your scope does not already reach")}

    def require(self, view_id: str) -> Dict[str, Any]:
        view = self.views.one(id=view_id)
        if not view:
            raise QueryError("unknown_view", f"no saved view '{view_id}'",
                             "list your views")
        return view

    # ----------------------------------------------------------------- export
    def export(self, entity: str, fmt: str, query: Dict[str, Any],
               reader: str, scope=None, filename: str = "",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Serialise a query's rows, and record that somebody took a copy."""
        chosen = (fmt or "").strip().lower()
        if chosen in REFUSED:
            raise QueryError(
                "format_refused",
                f"MAYA does not export {chosen}: {REFUSED[chosen]}",
                f"use one of {', '.join(FORMATS)}")
        if chosen not in FORMATS:
            raise QueryError("unknown_format",
                             f"'{fmt}' is not an export format",
                             f"use one of {', '.join(FORMATS)}")
        runnable = _runnable(query)
        runnable.setdefault("limit", MAX_ROWS)
        result = self.semantics.query(entity, scope=scope, now=now, **runnable)
        payload = _serialise(chosen, result["fields"], result["rows"])
        name = (filename or f"{entity}{EXTENSIONS[chosen]}")

        if self.evidence is not None:
            # An export is a disclosure. "Who took a copy of the model
            # inventory, and when" is asked after something has gone wrong, and
            # the answer has to already exist by then.
            self.evidence.append(
                "extract_taken", "estate", entity,
                {"entity": entity, "format": chosen,
                 "rows": result["returned"], "outside_scope": result["outside_scope"],
                 "fields": result["fields"]}, actor=reader)
        logger.info("%s exported %d row(s) of %s as %s", reader,
                    result["returned"], entity, chosen)
        return {"entity": entity, "format": chosen, "filename": name,
                "media_type": MEDIA[chosen], "bytes": payload,
                "rows": result["returned"], "truncated": result["truncated"],
                "outside_scope": result["outside_scope"],
                "detail": result["detail"]}

    @staticmethod
    def formats() -> Dict[str, Any]:
        """What is offered, and what is refused with the reason."""
        return {
            "formats": [{"format": f, "media_type": MEDIA[f],
                         "extension": EXTENSIONS[f]} for f in FORMATS],
            "refused": [{"format": f, "why": why}
                        for f, why in REFUSED.items()],
            "detail": ("three formats, and the ones people ask for that are "
                       "refused are named with the reason rather than left "
                       "out — an unexplained absence reads as an oversight and "
                       "gets raised as one every quarter"),
        }


def _runnable(query: Dict[str, Any]) -> Dict[str, Any]:
    """The subset of a stored query the semantic layer accepts.

    Filtered rather than passed through: a stored dictionary that grew a key the
    layer does not take would fail at run time with a TypeError, which is a
    stack trace where a refusal belongs.
    """
    out: Dict[str, Any] = {}
    for key in ("select", "where", "order_by", "descending", "limit"):
        if key in (query or {}):
            out[key] = query[key]
    return out


def _serialise(fmt: str, fields: Sequence[str],
               rows: Sequence[Dict[str, Any]]) -> bytes:
    if fmt == JSON:
        return json.dumps({"fields": list(fields), "rows": list(rows)},
                          indent=2, sort_keys=False).encode("utf-8")
    if fmt == CSV:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(fields),
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _flat(row.get(k)) for k in fields})
        return buffer.getvalue().encode("utf-8")
    return _parquet(fields, rows)


def _parquet(fields: Sequence[str], rows: Sequence[Dict[str, Any]]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq
    columns = {name: [row.get(name) for row in rows] for name in fields}
    buffer = io.BytesIO()
    # No schema is imposed. Arrow infers from the column, and a column that is
    # entirely null infers as null rather than as a guessed type — which is the
    # honest outcome: MAYA does not know what type a field nobody has ever
    # populated would have been.
    pq.write_table(pa.table(columns), buffer)
    return buffer.getvalue()


def _flat(value: Any) -> Any:
    """CSV holds text. A dict or list is written as JSON rather than as its
    Python repr, which is a format nothing else can read back."""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value)
    if value is None:
        return ""
    return value
