"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A read layer for the bank's own tools, and the one thing it must not be.

Every governance platform is eventually asked for "database access, so our BI
team can build their own dashboards". Granting it is the fastest way to lose
the register, and the mechanism is worth spelling out because it does not look
like a failure while it is happening.

A BI tool pointed at the physical schema has to decide for itself what *in
force* means. `status = 'approved'` is the obvious answer and it is wrong — a
model can be approved and have a blocking finding, an expired attestation, a
lapsed warrant. So a second definition of the most important word in the
register comes into existence, lives in a dashboard nobody governs, disagrees
with the platform, and is the one on the slide. **Handing out SQL is not a
semantic layer; it is a database credential with a nicer name.**

So this layer exposes **entities and fields, never tables and columns**, and
every derived field is computed by the same code the screens use. `in_force`
here is the platform's `in_force`. If it changes, it changes in one place, and
the BI tool's next refresh is right rather than differently wrong.

**No query text is accepted anywhere.** A query is a structured object — an
entity, a list of fields, comparisons drawn from a closed set of operators.
There is no parameter that takes SQL, and there will not be one: the moment
there is, the layer above stops being able to promise anything about what a
query can reach.

**Scope is applied to rows, not to endpoints.** A principal restricted to one
legal entity gets a shorter table rather than a refusal, and the answer says how
many rows their scope removed. A count silently short is worse than a refusal,
because it gets reconciled against somebody else's count and the difference is
attributed to a bug.

**The catalogue is checked against the data.** Every entity publishes its fields
and a test asserts that the rows carry exactly those and no others — a data
dictionary that drifts from the data is the artefact this layer exists to
replace.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger

logger = get_logger(__name__)

TEXT, NUMBER, TIMESTAMP, BOOLEAN = "text", "number", "timestamp", "boolean"
TYPES: Tuple[str, ...] = (TEXT, NUMBER, TIMESTAMP, BOOLEAN)

# The closed set. Every operator here is one a form can offer and a reader can
# reason about; none of them can reach a row the entity does not already yield.
OPERATORS: Dict[str, str] = {
    "eq": "equals", "ne": "does not equal",
    "lt": "is less than", "lte": "is at most",
    "gt": "is greater than", "gte": "is at least",
    "in": "is one of", "contains": "contains the text",
    "is_null": "has no value", "not_null": "has a value",
}
# Which operators make sense for which type. Offering `contains` on a timestamp
# is how a query builder produces a form nobody can fill in correctly.
ADMISSIBLE: Dict[str, Tuple[str, ...]] = {
    TEXT: ("eq", "ne", "in", "contains", "is_null", "not_null"),
    NUMBER: ("eq", "ne", "lt", "lte", "gt", "gte", "in", "is_null", "not_null"),
    TIMESTAMP: ("lt", "lte", "gt", "gte", "is_null", "not_null"),
    BOOLEAN: ("eq", "ne"),
}

MAX_ROWS = 10_000
DAY = 86400.0


class QueryError(RuntimeError):
    """A query was refused. The message always says which part of it."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    describes: str
    #: True where the value is computed rather than stored. Published, because
    #: "where does this number come from" is the first question anybody
    #: reconciling two reports asks.
    derived: bool = False


@dataclass(frozen=True)
class Entity:
    name: str
    grain: str
    describes: str
    fields: Tuple[Field, ...]
    #: The field carrying the model URN, used to apply the reader's scope. An
    #: entity with none is estate-wide and is marked as such.
    scoped_by: str = "urn"

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise QueryError(
            "unknown_field",
            f"'{self.name}' has no field '{name}'",
            f"it has {', '.join(f.name for f in self.fields)}")

    def as_dict(self) -> Dict[str, Any]:
        return {"entity": self.name, "grain": self.grain,
                "describes": self.describes, "scoped_by": self.scoped_by,
                "fields": [{"name": f.name, "type": f.type,
                            "describes": f.describes, "derived": f.derived,
                            "operators": list(ADMISSIBLE[f.type])}
                           for f in self.fields]}


def _f(name, type_, describes, derived=False) -> Field:
    return Field(name, type_, describes, derived)


ENTITIES: Dict[str, Entity] = {e.name: e for e in (
    Entity("model", "one row per registered model",
           "The register itself. `in_force` is the platform's definition and "
           "not `status = 'approved'` — a model can be approved and carry a "
           "blocking finding, which is exactly the case a hand-written "
           "dashboard gets wrong.",
           (_f("urn", TEXT, "the stable identity"),
            _f("name", TEXT, "what people call it"),
            _f("domain", TEXT, "the business area"),
            _f("legal_entity", TEXT, "which entity owns it"),
            _f("owner", TEXT, "the accountable principal"),
            _f("purpose", TEXT, "what it was registered to do"),
            _f("status", TEXT, "the lifecycle state"),
            _f("tier", NUMBER, "risk tier, 1 to 4"),
            _f("origin", TEXT, "built here, bought, or inherited"),
            _f("registered_at", TIMESTAMP, "when it entered the register"),
            _f("versions", NUMBER, "how many versions exist", True),
            _f("in_force", BOOLEAN,
               "approved, unblocked and currently servable", True),
            _f("open_findings", NUMBER, "findings not closed", True),
            _f("blocking_findings", NUMBER,
               "open findings that refuse resolution", True))),
    Entity("model_version", "one row per immutable version",
           "Versions never change, so every row here is a fact about a moment "
           "rather than a current state.",
           (_f("urn", TEXT, "the model"),
            _f("semver", TEXT, "the version"),
            _f("trainability_class", TEXT, "T0 to T8, derived at registration"),
            _f("status", TEXT, "draft, approved or superseded"),
            _f("artifact_digest", TEXT, "what resolves, by content"),
            _f("deterministic", BOOLEAN, "whether the same input must answer alike"),
            _f("created_at", TIMESTAMP, "when it was created"))),
    Entity("finding", "one row per finding",
           "Overdue is computed against the moment the query runs, not stored, "
           "so a report cut today cannot show yesterday's answer.",
           (_f("id", TEXT, "the finding"),
            _f("urn", TEXT, "the model it is against", True),
            _f("severity", TEXT, "Critical to Observation"),
            _f("category", TEXT, "what kind of failure"),
            _f("title", TEXT, "the one-line statement"),
            _f("status", TEXT, "open, acknowledged, planned or closed"),
            _f("blocking", BOOLEAN, "whether it refuses warrant resolution"),
            _f("owner", TEXT, "who has to fix it"),
            _f("raised_at", TIMESTAMP, "when it was raised"),
            _f("due_at", TIMESTAMP, "the remediation date"),
            _f("closed_at", TIMESTAMP, "when it was closed"),
            _f("overdue", BOOLEAN, "open and past its date", True),
            _f("days_open", NUMBER, "how long it has been open", True))),
    Entity("monitor", "one row per monitor",
           "A monitor that is not running looks exactly like one that is "
           "passing, so `stalled` is published as a field rather than left to "
           "whoever writes the query.",
           (_f("id", TEXT, "the monitor"),
            _f("urn", TEXT, "the model it watches", True),
            _f("name", TEXT, "what it is called"),
            _f("kind", TEXT, "drift, performance or calibration"),
            _f("test_key", TEXT, "the test that answers it"),
            _f("status", TEXT, "active, paused or retired"),
            _f("cadence_days", NUMBER, "how often it should run"),
            _f("last_evaluated_at", TIMESTAMP, "when it last ran"),
            _f("observations", NUMBER, "how many results it holds", True),
            _f("stalled", BOOLEAN,
               "active and past three times its own cadence", True))),
    Entity("observation", "one row per monitoring result",
           "`source` says whether MAYA computed the number or took delivery of "
           "it. A report that mixes the two without saying so is claiming "
           "assurance it does not have.",
           (_f("id", TEXT, "the observation"),
            _f("monitor_id", TEXT, "the monitor"),
            _f("urn", TEXT, "the model", True),
            _f("value", NUMBER, "what was measured"),
            _f("passed", BOOLEAN, "against this firm's threshold"),
            _f("sample_size", NUMBER, "how many rows it was computed over"),
            _f("window_start", TIMESTAMP, "the start of the population"),
            _f("window_end", TIMESTAMP, "the end of the population"),
            _f("source", TEXT, "maya, or a system that sent the number"),
            _f("computed_by", TEXT, "who computed it, where that is not MAYA"),
            _f("computed_at", TIMESTAMP, "when it was recorded"))),
    Entity("validation", "one row per validation episode",
           "An episode, not a document. `outcome` is what the second line "
           "concluded and is empty while it is still open.",
           (_f("id", TEXT, "the episode"),
            _f("urn", TEXT, "the model", True),
            _f("kind", TEXT, "initial, periodic or targeted"),
            _f("status", TEXT, "open or concluded"),
            _f("outcome", TEXT, "what it concluded"),
            _f("started_at", TIMESTAMP, "when it opened"),
            _f("completed_at", TIMESTAMP, "when it concluded"),
            _f("elapsed_days", NUMBER, "how long it took, or has taken", True))),
    Entity("overlay", "one row per post-model adjustment",
           "The register a risk committee asks for and almost never has: how "
           "much of the number is the model and how much is us.",
           (_f("id", TEXT, "the overlay"),
            _f("urn", TEXT, "the model", True),
            _f("name", TEXT, "what it is called"),
            _f("kind", TEXT, "add-on, haircut, exclusion or uplift"),
            _f("status", TEXT, "proposed, active or closed"),
            _f("owner", TEXT, "who proposed it"),
            _f("renewals", NUMBER, "how many times it has been continued"),
            _f("effective_from", TIMESTAMP, "when it started applying"),
            _f("expires_at", TIMESTAMP, "when it stops"),
            _f("expired", BOOLEAN, "past its window and still open", True))),
    Entity("warrant_grant", "one row per grant",
           "A grant is permission to resolve, not a call. Counting grants as "
           "usage is the commonest misreading of this table.",
           (_f("id", TEXT, "the grant"),
            _f("urn", TEXT, "the model", True),
            _f("environment", TEXT, "where it may be resolved"),
            _f("principal", TEXT, "who holds it"),
            _f("declared_use", TEXT, "what it was granted for"),
            _f("binding_kind", TEXT, "pinned to a version, or to an alias"),
            _f("revoked", BOOLEAN, "whether it has been withdrawn"),
            _f("created_at", TIMESTAMP, "when it was issued"))),
)}


class SemanticLayer:
    """Named entities over the register, queried structurally and never by text."""

    def __init__(self, db, registry, findings=None, monitoring=None,
                 lifecycle=None):
        self.db, self.registry = db, registry
        self.findings, self.monitoring = findings, monitoring
        self.lifecycle = lifecycle
        self._urn_cache: Dict[str, str] = {}

    # ------------------------------------------------------------- catalogue
    @staticmethod
    def describe() -> Dict[str, Any]:
        """Every entity, every field, and which operators each field admits."""
        return {
            "entities": [e.as_dict() for e in ENTITIES.values()],
            "operators": [{"operator": k, "means": v}
                          for k, v in OPERATORS.items()],
            "max_rows": MAX_ROWS,
            "detail": (
                f"{len(ENTITIES)} entities. There is no parameter that takes "
                f"query text, and there will not be one: a layer that accepts "
                f"SQL cannot promise anything about what a query can reach, "
                f"and the first thing a BI tool does with table access is "
                f"invent its own definition of 'in force'"),
        }

    # ------------------------------------------------------------------ query
    def query(self, entity: str, select: Optional[Sequence[str]] = None,
              where: Optional[Sequence[Dict[str, Any]]] = None,
              order_by: str = "", descending: bool = False,
              limit: int = 1000, scope=None,
              now: Optional[float] = None) -> Dict[str, Any]:
        """Run one structured query, under the reader's scope."""
        spec = self._entity(entity)
        moment = now if now is not None else time.time()
        fields = self._select(spec, select)
        clauses = [self._clause(spec, c) for c in (where or [])]
        if order_by:
            spec.field(order_by)
        if limit < 1 or limit > MAX_ROWS:
            raise QueryError(
                "limit_out_of_range",
                f"a limit of {limit} is outside 1..{MAX_ROWS}",
                f"ask for at most {MAX_ROWS} rows; a report that needs more "
                f"than that is an extract, and the export formats exist for it")

        rows = self._rows(spec, moment)
        in_scope, removed = self._apply_scope(spec, rows, scope)
        matched = [r for r in in_scope if all(c(r) for c in clauses)]
        if order_by:
            # Two passes rather than one key function. Nulls sort last in BOTH
            # directions, and a single key cannot do that: whichever sentinel
            # puts them at the end ascending puts them at the front descending.
            # A report ordered by due date that opens with everything having no
            # date is one nobody reads past the first screen.
            present = [r for r in matched if r.get(order_by) is not None]
            absent = [r for r in matched if r.get(order_by) is None]
            present.sort(key=lambda r: _sortable(r.get(order_by)),
                         reverse=descending)
            matched = present + absent
        page = matched[:limit]
        logger.info("semantic query on %s returned %d of %d rows (%d outside "
                    "scope)", entity, len(page), len(matched), removed)
        return {
            "entity": entity, "fields": fields,
            "rows": [{k: r.get(k) for k in fields} for r in page],
            "returned": len(page), "matched": len(matched),
            "truncated": len(matched) > len(page),
            "outside_scope": removed,
            "detail": self._detail(entity, len(page), len(matched), removed),
        }

    @staticmethod
    def _detail(entity: str, returned: int, matched: int, removed: int) -> str:
        out = f"{returned} row(s) of {entity}"
        if matched > returned:
            out += (f"; {matched} matched and the rest were cut by the limit, "
                    f"which is said here rather than left to be inferred from a "
                    f"round number")
        if removed:
            out += (f". {removed} further row(s) were outside your scope and "
                    f"are not in the count — a total that is silently short "
                    f"gets reconciled against somebody else's and the "
                    f"difference is blamed on a bug")
        return out

    @staticmethod
    def _entity(name: str) -> Entity:
        if name not in ENTITIES:
            raise QueryError(
                "unknown_entity", f"there is no entity called '{name}'",
                f"the layer publishes {', '.join(sorted(ENTITIES))}")
        return ENTITIES[name]

    @staticmethod
    def _select(spec: Entity, select: Optional[Sequence[str]]) -> List[str]:
        if not select:
            return [f.name for f in spec.fields]
        for name in select:
            spec.field(name)                       # refuses an unknown field
        return list(select)

    @staticmethod
    def _clause(spec: Entity, clause: Dict[str, Any]) -> Callable:
        field = spec.field(clause.get("field", ""))
        operator = clause.get("operator", "eq")
        if operator not in OPERATORS:
            raise QueryError(
                "unknown_operator", f"'{operator}' is not an operator",
                f"use one of {', '.join(sorted(OPERATORS))}")
        if operator not in ADMISSIBLE[field.type]:
            raise QueryError(
                "operator_not_admissible",
                f"'{operator}' cannot be applied to '{field.name}', which is "
                f"{field.type}",
                f"for {field.type} use one of "
                f"{', '.join(ADMISSIBLE[field.type])}")
        value = clause.get("value")
        if operator == "in" and not isinstance(value, (list, tuple)):
            raise QueryError(
                "value_not_a_list", "'in' compares against a list of values",
                "pass value as a list")
        return _predicate(field.name, operator, value)

    # ------------------------------------------------------------------ scope
    def _apply_scope(self, spec: Entity, rows: List[Dict[str, Any]],
                     scope) -> Tuple[List[Dict[str, Any]], int]:
        """Filter to what this reader may see, and count what was removed."""
        if scope is None or scope.unrestricted or not spec.scoped_by:
            return rows, 0
        permitted = {m["urn"] for m in self.registry.list() if scope.permits(m)}
        kept = [r for r in rows if r.get(spec.scoped_by) in permitted]
        return kept, len(rows) - len(kept)

    # ------------------------------------------------------------------- rows
    def _rows(self, spec: Entity, now: float) -> List[Dict[str, Any]]:
        return getattr(self, f"_rows_{spec.name}")(now)

    def _urn_of(self, model_id: Optional[str]) -> str:
        if not model_id:
            return ""
        if model_id not in self._urn_cache:
            model = self.registry.catalogue.by_id(model_id)
            self._urn_cache[model_id] = model["urn"] if model else ""
        return self._urn_cache[model_id]

    def _rows_model(self, now: float) -> List[Dict[str, Any]]:
        out = []
        for model in self.registry.list():
            versions = self.registry.versions(model["urn"])
            opened = (self.findings.open_for(model["id"])
                      if self.findings else [])
            out.append({
                "urn": model["urn"], "name": model.get("name") or "",
                "domain": model.get("domain") or "",
                "legal_entity": model.get("legal_entity") or "",
                "owner": model.get("owner") or "",
                "purpose": model.get("purpose") or "",
                "status": model.get("status") or "",
                "tier": model.get("tier"),
                "origin": model.get("origin") or "",
                "registered_at": model.get("created_at"),
                "versions": len(versions),
                # The platform's own definition, not `status = 'approved'`.
                "in_force": (any(v.get("status") == "approved" for v in versions)
                             and not any(f["blocking"] for f in opened)),
                "open_findings": len(opened),
                "blocking_findings": sum(1 for f in opened if f["blocking"]),
            })
        return out

    def _rows_model_version(self, now: float) -> List[Dict[str, Any]]:
        return [{"urn": model["urn"], "semver": v.get("semver") or "",
                 "trainability_class": v.get("trainability_class") or "",
                 "status": v.get("status") or "",
                 "artifact_digest": v.get("artifact_digest") or "",
                 "deterministic": bool(v.get("deterministic")),
                 "created_at": v.get("created_at")}
                for model in self.registry.list()
                for v in self.registry.versions(model["urn"])]

    def _rows_finding(self, now: float) -> List[Dict[str, Any]]:
        from db.repositories import FindingRepository
        out = []
        for row in FindingRepository(self.db).many():
            closed = row.get("status") == "closed"
            out.append({
                "id": row["id"], "urn": self._urn_of(row.get("model_id")),
                "severity": row.get("severity") or "",
                "category": row.get("category") or "",
                "title": row.get("title") or "",
                "status": row.get("status") or "",
                "blocking": bool(row.get("blocking")),
                "owner": row.get("owner") or "",
                "raised_at": row.get("raised_at"),
                "due_at": row.get("due_at"),
                "closed_at": row.get("closed_at"),
                "overdue": (not closed and (row.get("due_at") or 0) < now),
                "days_open": round(
                    ((row.get("closed_at") or now) - (row.get("raised_at") or now))
                    / DAY, 1),
            })
        return out

    def _rows_monitor(self, now: float) -> List[Dict[str, Any]]:
        from db.repositories import MonitorRepository, ObservationRepository
        observations = ObservationRepository(self.db)
        out = []
        for row in MonitorRepository(self.db).many():
            history = observations.many(monitor_id=row["id"])
            last = row.get("last_evaluated_at")
            cadence = float(row.get("cadence_days") or 1.0)
            out.append({
                "id": row["id"], "urn": self._urn_of(row.get("model_id")),
                "name": row.get("name") or "", "kind": row.get("kind") or "",
                "test_key": row.get("test_key") or "",
                "status": row.get("status") or "",
                "cadence_days": cadence, "last_evaluated_at": last,
                "observations": len(history),
                # Published rather than left to the query author. A monitor
                # that is not running looks exactly like one that is passing.
                "stalled": (row.get("status") == "active"
                            and (now - (last or 0)) > 3 * cadence * DAY),
            })
        return out

    def _rows_observation(self, now: float) -> List[Dict[str, Any]]:
        from db.repositories import MonitorRepository, ObservationRepository
        monitors = {m["id"]: m for m in MonitorRepository(self.db).many()}
        out = []
        for row in ObservationRepository(self.db).many():
            monitor = monitors.get(row.get("monitor_id")) or {}
            out.append({
                "id": row["id"], "monitor_id": row.get("monitor_id") or "",
                "urn": self._urn_of(monitor.get("model_id")),
                "value": row.get("value"), "passed": bool(row.get("passed")),
                "sample_size": row.get("sample_size"),
                "window_start": row.get("window_start"),
                "window_end": row.get("window_end"),
                "source": row.get("source") or "maya",
                "computed_by": row.get("computed_by") or "",
                "computed_at": row.get("computed_at")})
        return out

    def _rows_validation(self, now: float) -> List[Dict[str, Any]]:
        from db.repositories import ValidationRepository
        out = []
        for row in ValidationRepository(self.db).many():
            started = row.get("started_at") or now
            out.append({
                "id": row["id"], "urn": self._urn_of(row.get("model_id")),
                "kind": row.get("kind") or "", "status": row.get("status") or "",
                "outcome": row.get("outcome") or "",
                "started_at": row.get("started_at"),
                "completed_at": row.get("completed_at"),
                "elapsed_days": round(
                    ((row.get("completed_at") or now) - started) / DAY, 1)})
        return out

    def _rows_overlay(self, now: float) -> List[Dict[str, Any]]:
        from db.repositories import OverlayRepository
        out = []
        for row in OverlayRepository(self.db).many():
            expires = row.get("expires_at")
            out.append({
                "id": row["id"], "urn": self._urn_of(row.get("model_id")),
                "name": row.get("name") or "", "kind": row.get("kind") or "",
                "status": row.get("status") or "",
                "owner": row.get("owner") or "",
                "renewals": row.get("renewals") or 0,
                "effective_from": row.get("effective_from"),
                "expires_at": expires,
                "expired": bool(row.get("status") == "active" and expires
                                and expires < now)})
        return out

    def _rows_warrant_grant(self, now: float) -> List[Dict[str, Any]]:
        from db.repositories import WarrantRepository
        return [{"id": row["id"], "urn": self._urn_of(row.get("model_id")),
                 "environment": row.get("environment") or "",
                 "principal": row.get("principal") or "",
                 "declared_use": row.get("declared_use") or "",
                 "binding_kind": row.get("binding_kind") or "",
                 "revoked": bool(row.get("revoked")),
                 "created_at": row.get("created_at")}
                for row in WarrantRepository(self.db).many()]


def _sortable(value: Any):
    """A total order over a column that may hold mixed types.

    Nulls never reach this — they are ordered separately, so that they can be
    last in both directions. What is left is a column that may still mix a
    string and a number, which is a data problem rather than a crash: the type
    name orders first so the two never compare against each other.
    """
    return (type(value).__name__, value)


def _predicate(field: str, operator: str, value: Any) -> Callable:
    """One comparison, closed over the field and the value."""
    def run(row: Dict[str, Any]) -> bool:
        held = row.get(field)
        if operator == "is_null":
            return held is None or held == ""
        if operator == "not_null":
            return held is not None and held != ""
        if held is None:
            # A null satisfies no comparison. SQL agrees, and the alternative
            # is a filter that silently includes the rows it cannot judge.
            return False
        if operator == "eq":
            return held == value
        if operator == "ne":
            return held != value
        if operator == "in":
            return held in (value or [])
        if operator == "contains":
            return str(value).lower() in str(held).lower()
        try:
            if operator == "lt":
                return held < value
            if operator == "lte":
                return held <= value
            if operator == "gt":
                return held > value
            return held >= value
        except TypeError:
            # Comparing a string to a number. Refused per row rather than for
            # the query, because a mixed column is a data problem and this
            # reports it as no match rather than as a crash.
            logger.debug("%s %s %r could not be compared", field, operator, value)
            return False
    return run
