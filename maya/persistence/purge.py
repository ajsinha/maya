"""
Removing a namespace and everything in it, in one transaction.

MAYA does not delete governed objects: an audit chain, a custody log and a lineage graph
all rest on the objects they name still existing. This is the one exception, and the
service that calls it refuses outside a development environment -- it is how a
demonstration or a test estate recovers from a run that stopped half way, not something a
production register does.

The rows of a namespace are found three ways, because the schema links them three ways:
by foreign key (versions, pins, parameter sets, findings); by an object id with no foreign
key (approvals, comments, grants, workflow history, custody, reports, scores); and by
reference string (lineage edges, notifications, subscriptions). Children go before parents
and the namespace row goes last. The audit log and the event stream are history and are
left as they are; the service records the purge in the audit log itself.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

CHUNK = 500
REF_KINDS = ("feature", "featureset", "model", "warrant/train", "warrant/exec")
BY_OBJECT_ID = (
    "approvals",
    "comments",
    "grants",
    "workflow_events",
    "challenge_memos",
    "search_terms",
    "access_requests",
    "workspace_changes",
)
BY_REFERENCE = (
    ("lineage_edges", ("src_ref", "dst_ref")),
    ("notifications", ("object_ref",)),
    ("subscriptions", ("object_ref",)),
)


def _chunks(values: Iterable[Any]) -> Iterable[list[Any]]:
    items = list(values)
    for i in range(0, len(items), CHUNK):
        yield items[i : i + CHUNK]


class _Purge:
    """One namespace's rows, found and then removed, counting as it goes."""

    def __init__(self, conn: Any, namespace_id: str, name: str) -> None:
        from maya.persistence.models import Base

        self.conn, self.name = conn, name
        self.t = Base.metadata.tables
        self.removed: dict[str, int] = {}
        self.ns = {namespace_id}

    def ids(self, table: str, column: str, values: Iterable[Any]) -> set[str]:
        from sqlalchemy import select

        col, found = self.t[table].c[column], set()
        for part in _chunks(values):
            found |= {
                r[0] for r in self.conn.execute(select(self.t[table].c.id).where(col.in_(part)))
            }
        return found

    def drop(self, table: str, column: str, values: Iterable[Any]) -> None:
        from sqlalchemy import delete

        n = sum(
            self.conn.execute(
                delete(self.t[table]).where(self.t[table].c[column].in_(part))
            ).rowcount
            for part in _chunks(values)
        )
        if n:
            self.removed[table] = self.removed.get(table, 0) + n

    def collect(self) -> dict[str, set[str]]:
        c: dict[str, set[str]] = {"ns": self.ns}
        c["features"] = self.ids("features", "namespace_id", self.ns)
        c["f_versions"] = self.ids("feature_versions", "feature_id", c["features"])
        c["f_pins"] = self.ids("feature_pins", "feature_id", c["features"])
        c["f_ingests"] = self.ids("feature_ingests", "feature_id", c["features"])
        c["sets"] = self.ids("feature_sets", "namespace_id", self.ns)
        c["s_versions"] = self.ids("feature_set_versions", "feature_set_id", c["sets"])
        c["s_pins"] = self.ids("feature_set_pins", "feature_set_id", c["sets"])
        c["models"] = self.ids("models", "namespace_id", self.ns)
        c["m_versions"] = self.ids("model_versions", "model_id", c["models"])
        c["apps"] = self.ids("llm_apps", "namespace_id", self.ns)
        c["a_versions"] = self.ids("llm_app_versions", "app_id", c["apps"])
        c["eval_sets"] = self.ids("llm_eval_sets", "app_id", c["apps"])
        c["trains"] = self.ids("training_warrants", "namespace_id", self.ns)
        c["execs"] = self.ids("execution_warrants", "namespace_id", self.ns)
        c["params"] = self.ids("parameter_sets", "model_version_id", c["m_versions"]) | self.ids(
            "parameter_sets", "training_warrant_id", c["trains"]
        )
        return c

    def soft_references(self, c: dict[str, set[str]]) -> None:
        everything = set().union(*c.values())
        for table in BY_OBJECT_ID:
            self.drop(table, "object_id", everything)
        warrants = c["trains"] | c["execs"]
        self.drop("custody_events", "warrant_id", warrants)
        self.drop("execution_reports", "execution_warrant_id", c["execs"])
        for table in ("holdout_scores", "warrant_evidence"):
            self.drop(table, "training_warrant_id", c["trains"])
        for column in ("champion_warrant_id", "challenger_warrant_id"):
            self.drop("challenges", column, c["trains"])
        self.drop("derivations", "target_version_id", c["f_versions"] | c["s_versions"])
        versions = c["f_versions"] | c["s_versions"] | c["m_versions"]
        self.drop("inheritance_links", "child_version_id", versions)
        self.drop("workflow_policies", "scope", [self.name])

    def references(self, c: dict[str, set[str]]) -> None:
        from sqlalchemy import delete, or_

        prefixes = [f"maya://{kind}/{self.name}/" for kind in REF_KINDS]
        prefixes += [f"maya://parameters/{pid}" for pid in c["params"]]
        exact = [f"maya://namespace/{self.name}"]
        for table, columns in BY_REFERENCE:
            col = self.t[table].c
            for part in _chunks(prefixes):
                tests = [col[n].startswith(x, autoescape=True) for n in columns for x in part]
                tests += [col[n].in_(exact) for n in columns]
                n = self.conn.execute(delete(self.t[table]).where(or_(*tests))).rowcount
                if n:
                    self.removed[table] = self.removed.get(table, 0) + n

    def fragments(self) -> None:
        from sqlalchemy import select

        rows = self.conn.execute(select(self.t["fragments"].c.lake_table).distinct())
        mine = [r[0] for r in rows if r[0].split("/")[1:2] == [self.name]]
        self.drop("fragments", "lake_table", mine)

    def objects(self, c: dict[str, set[str]]) -> None:
        """The governed objects themselves, children before parents, the namespace last.
        Warrants first: each names its model version by foreign key."""
        self.drop("training_warrants", "id", c["trains"])
        self.drop("execution_warrants", "id", c["execs"])
        self.drop("llm_eval_runs", "version_id", c["a_versions"])
        self.drop("llm_eval_runs", "eval_set_id", c["eval_sets"])
        self.drop("llm_eval_sets", "app_id", c["apps"])
        self.drop("llm_app_versions", "app_id", c["apps"])
        self.drop("llm_apps", "id", c["apps"])
        self.drop("parameter_sets", "id", c["params"])
        self.drop("composite_members", "composite_version_id", c["m_versions"])
        for table in ("findings", "model_governance", "model_reviews", "model_documents"):
            self.drop(table, "model_id", c["models"])
        self.drop("model_versions", "id", c["m_versions"])
        self.drop("models", "id", c["models"])
        self.drop("feature_set_members", "feature_set_version_id", c["s_versions"])
        self.drop("feature_set_pins", "id", c["s_pins"])
        self.drop("feature_set_versions", "id", c["s_versions"])
        self.drop("feature_sets", "id", c["sets"])
        self.drop("feature_pins", "id", c["f_pins"])
        self.drop("feature_ingests", "id", c["f_ingests"])
        self.drop("feature_versions", "id", c["f_versions"])
        self.drop("features", "id", c["features"])
        self.drop("namespaces", "id", self.ns)


def purge_namespace(db: Any, namespace_id: str, name: str) -> dict[str, int]:
    """Delete the namespace ``namespace_id`` and every row that belongs to it.

    Returns the number of rows removed per table (tables with none are left out)."""
    lock = db.write_mutex if db.is_sqlite else None
    if lock is not None:
        lock.acquire()
    try:
        with db.engine.begin() as conn:
            purge = _Purge(conn, namespace_id, name)
            found = purge.collect()
            purge.soft_references(found)
            purge.references(found)
            purge.fragments()
            purge.objects(found)
            return purge.removed
    finally:
        if lock is not None:
            lock.release()
