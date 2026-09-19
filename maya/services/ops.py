"""
Operations: health and readiness (§20), jobs (§15.2), integrity verification
(§7.3), lineage (§19), catalog search, and the estate export/import that is
MAYA's only schema-upgrade path (§14.3).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import platform as pyplatform
import sys
from typing import Any

from maya.core.backends import Backends
from maya.core.compress import procstat
from maya.core.errors import PermissionDenied, ValidationFailed
from maya.core.typeset import detect as typeset_detect
from maya.core.version import BUILD_DATE, VERSION
from maya.persistence import estate
from maya.security.authz import Principal
from maya.security.sandbox import sandbox_tier

class OpsService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- health ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        """The system health page (§20): every dependency, in plain language."""
        db_ok, db_detail = self._db_ok()
        with self.p.uow() as uow:
            queued = uow.repo("jobs").count(state="queued")
            running = uow.repo("jobs").count(state="running")
            dead = uow.repo("jobs").count(state="dead_letter")
        s = self.p.settings
        degraded = [f"{c['seam']}: {c['selected']} instead of {c['preferred']} — {c['cost']}"
                    for c in Backends.report() if c["selected"] != c["preferred"]]
        if self.p.db.is_sqlite:
            degraded.append("database: SQLite — single writer, suited to a laptop or small "
                            "team; PostgreSQL is the production backend")
        return {
            "version": VERSION, "build_date": BUILD_DATE, "environment": s.environment,
            "python": sys.version.split()[0], "platform": pyplatform.platform(),
            "database": {"dialect": self.p.db.dialect, "ok": db_ok, "detail": db_detail,
                         "schema_hash": self.p.db.schema_hash(),
                         "schema_file": f"maya/persistence/schema/{self.p.db.dialect}.sql"},
            "lake": {"backend": self.p.lake.backend_name, "detail": self.p.lake.delta.info.reason,
                     "root": str(self.p.lake.root)},
            "sandbox": sandbox_tier(), "typeset": typeset_detect(),
            "jobs": {"queued": queued, "running": running, "dead_letter": dead,
                     "workers": self.p.jobs.n_workers},
            "seams": Backends.report(), "degraded": degraded, "process": procstat(),
            "default_admin_password": self.p.auth.default_admin_password_active(),
            "tracing": _tracing_status(),
            "webhooks": _webhook_backlog(self.p),
            "audit_chain": self.p.access.verify_audit(),
        }

    def _db_ok(self) -> tuple[bool, str]:
        try:
            self.p.db.verify_schema()
            return True, "schema identity verified"
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            return False, str(exc)

    def ready(self) -> dict[str, Any]:
        db_ok, detail = self._db_ok()
        lake_ok = self.p.lake.root.exists()
        return {"ready": db_ok and lake_ok, "database": detail,
                "lake": self.p.lake.backend_name, "seams": Backends.provenance()}

    # -- jobs ---------------------------------------------------------------------
    def jobs(self, p: Principal, *, all_users: bool = False) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            if all_users and (p.is_admin or "techops" in p.roles):
                return uow.repo("jobs").list(order_by=["-created_at"], limit=1000)
            return uow.repo("jobs").list(owner=p.username, order_by=["-created_at"], limit=500)

    def jobs_page(self, p: Principal, *, all_users: bool = False, q: str | None = None,
                  page_size: int | None = None, cursor: str | None = None,
                   sort: str | None = None, total: bool = False) -> dict[str, Any]:
        from maya.services.paging import Listing, run_page
        everyone = all_users and (p.is_admin or "techops" in p.roles)
        filters = {} if everyone else {"owner": p.username}
        return run_page(self.p, lambda uow: Listing(
            "jobs", {"-created": "-created_at", "created": "created_at"}, "-created", filters,
            (["job_type", "state", "owner"], q or "")),
            page_size=page_size, cursor=cursor, sort=sort, total=total)

    def job(self, p: Principal, job_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            job = uow.repo("jobs").require(job_id)
        if job["owner"] != p.username and not (p.is_admin or "techops" in p.roles):
            raise PermissionDenied("You can see only your own jobs")
        return job

    def cancel_job(self, p: Principal, job_id: str) -> dict[str, Any]:
        self.job(p, job_id)
        with self.p.uow(p.username) as uow:
            row = self.p.jobs.cancel(uow, job_id)
            uow.audit("job.cancel_requested", object_type="job", object_ref=job_id)
            return row

    def retry_job(self, p: Principal, job_id: str) -> dict[str, Any]:
        if not (p.is_admin or "techops" in p.roles):
            raise PermissionDenied("Retrying a dead-lettered job is a techops action")
        with self.p.uow(p.username) as uow:
            job = uow.repo("jobs").require(job_id)
            if job["state"] not in ("dead_letter", "failed"):
                raise ValidationFailed("Only failed or dead-lettered jobs are retried")
            row = uow.repo("jobs").update(job_id, {"state": "queued", "attempts": 0,
                                                   "error": None, "run_after": None})
            uow.audit("job.retried", object_type="job", object_ref=job_id)
            uow.after_commit(self.p.jobs._wake.set)
            return row

    # -- integrity (§7.3) ------------------------------------------------------------
    def verify_integrity(self, p: Principal) -> dict[str, Any]:
        """Re-read every sealed pin and recompute its content hash. Drift is an incident."""
        if not (p.is_admin or "techops" in p.roles):
            raise PermissionDenied("Integrity verification is for administrators and techops")
        results = []
        with self.p.uow() as uow:
            pins = [("pins", "feature_pins", "features", "feature_id", x)
                    for x in uow.repo("feature_pins").list(state="sealed")]
            pins += [("fspins", "feature_set_pins", "feature_sets", "feature_set_id", x)
                     for x in uow.repo("feature_set_pins").list(state="sealed")]
            names = {}
            for _, _, table, fk, pin in pins:
                obj = uow.repo(table).require(pin[fk])
                ns = uow.repo("namespaces").require(obj["namespace_id"])
                names[pin["id"]] = (ns["name"], obj["name"])
        for kind, _, _, _, pin in pins:
            ns, name = names[pin["id"]]
            try:
                r = self.p.lake.verify_pin(kind, ns, name, pin["fragments"], pin["content_hash"])
            except Exception as exc:  # noqa: BLE001 - reported per pin
                r = {"ok": False, "error": str(exc)}
            results.append({"pin": f"{ns}/{name}#{pin['pin_name']}/{pin['as_of_date']}", **r})
        drift = [r for r in results if not r["ok"]]
        with self.p.uow(p.username) as uow:
            uow.audit("integrity.verified", detail={"pins": len(results), "drift": len(drift)})
            if drift:
                for admin in self._admins(uow):
                    uow.repo("notifications").add({"user_id": admin, "kind": "integrity_drift",
                                                   "message": f"{len(drift)} pin(s) failed "
                                                              "integrity verification",
                                                   "object_ref": None})
        return {"checked": len(results), "drift": drift, "results": results,
                "audit_chain": self.p.access.verify_audit()}

    @staticmethod
    def _admins(uow: Any) -> set[str]:
        role = uow.repo("roles").find_one(name="admin")
        return {r["user_id"] for r in uow.repo("user_roles").list(role_id=role["id"])}

    def storage_report(self) -> dict[str, Any]:
        """Fragment sharing across pins: what content addressing saved (SC-12)."""
        with self.p.uow() as uow:
            frags = uow.repo("fragments").list()
            pins = uow.repo("feature_pins").list(state="sealed") + \
                uow.repo("feature_set_pins").list(state="sealed")
        logical = sum(p["bytes_total"] for p in pins)
        stored = sum(f["bytes"] for f in frags)
        referenced = {h for p in pins for h in p["fragments"]}
        orphans = [f for f in frags if f["hash"] not in referenced]
        return {"pins": len(pins), "fragments": len(frags), "logical_bytes": logical,
                "stored_bytes": stored,
                "saved_ratio": (1 - stored / logical) if logical else 0.0,
                "orphan_fragments": len(orphans),
                "orphan_bytes": sum(f["bytes"] for f in orphans),
                "gc_note": "Orphans are fragments no sealed pin references (left by failed "
                           "pins). They are reported, never deleted automatically."}

    def read_blob(self, p: Principal, digest: str) -> bytes:
        """Only an administrator, the uploader, or whoever exported it may read a blob."""
        with self.p.uow(p.username) as uow:
            blob = uow.repo("blobs").find_one(hash=digest)
            exported = uow.repo("custody_events").find_one(checksum=digest, actor=p.username)
            if not (p.is_admin or exported or (blob and blob["created_by"] == p.username)):
                raise PermissionDenied("You may read only blobs you uploaded or exported")
            uow.audit("blob.downloaded", object_ref=f"blob:{digest[:16]}")
        return self.p.blobs.get(digest)

    # -- lineage and search ------------------------------------------------------------
    def lineage(self, root: str, *, direction: str = "both", depth: int = 3) -> dict[str, Any]:
        with self.p.uow() as uow:
            edges = uow.repo("lineage_edges").walk(root, direction=direction, depth=depth)
        nodes = {root} | {e["src_ref"] for e in edges} | {e["dst_ref"] for e in edges}
        return {"root": root, "nodes": [{"id": n, "kind": _kind(n)} for n in sorted(nodes)],
                "edges": [{"source": e["src_ref"], "target": e["dst_ref"],
                           "type": e["edge_type"], "label": e["label"]} for e in edges]}

    SEARCH_KINDS = {"feature": "feature", "featureset": "featureset", "model": "model",
                    "warrant/train": "training_warrant", "warrant/exec": "execution_warrant"}

    def search(self, p: Principal, q: str, limit: int = 50) -> list[dict[str, Any]]:
        """Ranked catalog hits the caller may read; nothing else is so much as named."""
        if not q or len(q.strip()) < 2:
            return []
        out = []
        with self.p.uow() as uow:
            names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
            for h in uow.repo("search").search(q, limit=max(1, min(limit, 200)) * 3):
                kind = self.SEARCH_KINDS.get(h["kind"])
                if kind is not None:
                    table = {"feature": "features", "featureset": "feature_sets",
                             "model": "models", "training_warrant": "training_warrants",
                             "execution_warrant": "execution_warrants"}[kind]
                    if not self.p.access.allowed(uow, p, "read", kind,
                                                 uow.repo(table).require(h["id"])):
                        continue
                h["namespace"] = names.get(h.get("namespace_id"))
                out.append(h)
                if len(out) >= limit:
                    break
        return out

    def reindex_search(self, p: Principal) -> dict[str, Any]:
        """Recreate the derived search index from the catalog (admin; recovery only)."""
        if not p.is_admin:
            raise PermissionDenied("Rebuilding the search index is for administrators")
        with self.p.uow(p.username) as uow:
            n = uow.repo("search").rebuild()
            uow.audit("search.reindexed", detail={"objects": n})
        return {"objects": n}

    # -- lake maintenance ------------------------------------------------------------------
    def lake_maintenance(self, p: Principal | None = None) -> dict[str, Any]:
        """Compact every lake table and vacuum files past retention (admin, or the scheduler)."""
        if p is not None and not (p.is_admin or "techops" in p.roles):
            raise PermissionDenied("Lake maintenance is for administrators and techops")
        s = self.p.settings
        tables = self.p.lake.maintain(
            target_size=s.int("lake.maintenance.target_size_mb", 128) * 1024 * 1024,
            retention_hours=float(s.get("lake.maintenance.vacuum_retention_hours", "168")
                                  or 168))
        totals = {k: sum(t[k] for t in tables) for k in ("filesRemoved", "filesAdded",
                                                         "vacuumed")}
        with self.p.uow(p.username if p else "system") as uow:
            uow.audit("lake.maintained", principal_type="user" if p else "system",
                      channel="api" if p else "scheduler",
                      detail={"tables": len(tables), **totals})
        return {"tables": tables, **totals}

    # -- estate (§14.3) -------------------------------------------------------------------
    def export_estate(self) -> bytes:
        """Dialect-neutral dump of every table, hashed per table, in dependency order."""
        return estate.export(self.p.db, self.p.uow, VERSION)

    def import_estate(self, data: bytes) -> dict[str, Any]:
        """Load an estate into an empty, freshly created schema, verifying every hash."""
        counts = estate.load(self.p.db, data)
        with self.p.uow() as uow:
            chain = uow.repo("audit_events").verify_chain()
        if not chain["ok"]:
            raise ValidationFailed("The imported audit chain does not verify", **chain)
        return {"tables": counts, "audit_chain": chain}


def _tracing_status() -> dict[str, Any]:
    from maya.observability import tracing
    return tracing.status()


def _webhook_backlog(platform: Any) -> dict[str, int]:
    from maya.services.webhooks import deliveries_backlog
    with platform.uow() as uow:
        return deliveries_backlog(uow)


def _kind(ref: str) -> str:
    if ref.startswith("maya://"):
        return ref[7:].split("/")[0]
    return "other"


__all__ = ["OpsService"]
