"""
Operations: health and readiness (§20), jobs (§15.2), integrity verification
(§7.3), lineage (§19), catalog search, and the estate export/import that is
MAYA's only schema-upgrade path (§14.3).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import io
import json
import platform as pyplatform
import sys
import zipfile
from typing import Any

from maya.core.backends import Backends
from maya.core.compress import procstat
from maya.core.errors import PermissionDenied, ValidationFailed
from maya.core.typeset import detect as typeset_detect
from maya.core.version import BUILD_DATE, VERSION
from maya.persistence import schema
from maya.persistence.models import Base, MODELS
from maya.persistence.types import utcnow
from maya.security.authz import Principal
from maya.security.sandbox import sandbox_tier

ESTATE_FORMAT = "maya-estate-v1"


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
                         "schema_hash": schema.stored_hash(self.p.db.engine),
                         "schema_file": f"maya/persistence/schema/{self.p.db.dialect}.sql"},
            "lake": {"backend": self.p.lake.backend_name, "detail": self.p.lake.delta.info.reason,
                     "root": str(self.p.lake.root)},
            "sandbox": sandbox_tier(), "typeset": typeset_detect(),
            "jobs": {"queued": queued, "running": running, "dead_letter": dead,
                     "workers": self.p.jobs.n_workers},
            "seams": Backends.report(), "degraded": degraded, "process": procstat(),
            "default_admin_password": self.p.auth.default_admin_password_active(),
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

    def search(self, p: Principal, q: str) -> list[dict[str, Any]]:
        if not q or len(q) < 2:
            return []
        with self.p.uow() as uow:
            names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
            hits = uow.repo("search").search(q)
        for h in hits:
            h["namespace"] = names.get(h.get("namespace_id"))
        return hits

    # -- estate (§14.3) -------------------------------------------------------------------
    def export_estate(self) -> bytes:
        """Dialect-neutral dump of every table, hashed per table, in dependency order."""
        tables = [t.name for t in Base.metadata.sorted_tables]
        out = io.BytesIO()
        manifest: dict[str, Any] = {"format": ESTATE_FORMAT, "maya_version": VERSION,
                                    "exported_at": utcnow().isoformat(),
                                    "source_dialect": self.p.db.dialect, "tables": {}}
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z, self.p.uow() as uow:
            for name in tables:
                rows = uow.repo(name).list() if name not in ("audit_events",) else \
                    uow.repo(name).list(order_by=["seq"])
                body = "\n".join(json.dumps(r, default=_enc, sort_keys=True) for r in rows)
                z.writestr(f"tables/{name}.jsonl", body)
                manifest["tables"][name] = {"rows": len(rows),
                                            "sha256": hashlib.sha256(body.encode()).hexdigest()}
            z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        return out.getvalue()

    def import_estate(self, data: bytes) -> dict[str, Any]:
        """Load an estate into an empty, freshly created schema, verifying every hash."""
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            manifest = json.loads(z.read("manifest.json"))
            if manifest.get("format") != ESTATE_FORMAT:
                raise ValidationFailed("Not a MAYA estate bundle")
            counts = {}
            with self.p.db.engine.begin() as conn:
                for t in Base.metadata.sorted_tables:
                    if t.name not in manifest["tables"]:
                        continue
                    body = z.read(f"tables/{t.name}.jsonl").decode()
                    if hashlib.sha256(body.encode()).hexdigest() != \
                            manifest["tables"][t.name]["sha256"]:
                        raise ValidationFailed(f"Table {t.name} failed its hash check")
                    if t.name == "schema_meta":
                        continue
                    rows = [_decode(t, json.loads(line)) for line in body.splitlines() if line]
                    if rows:
                        conn.execute(t.insert(), rows)
                    counts[t.name] = len(rows)
                if self.p.db.dialect == "postgresql":
                    # explicit seq values leave the BIGSERIAL sequence behind; advance it
                    conn.exec_driver_sql(
                        "SELECT setval(pg_get_serial_sequence('audit_events', 'seq'), "
                        "COALESCE((SELECT MAX(seq) FROM audit_events), 1))")
        with self.p.uow() as uow:
            chain = uow.repo("audit_events").verify_chain()
        if not chain["ok"]:
            raise ValidationFailed("The imported audit chain does not verify", **chain)
        return {"tables": counts, "audit_chain": chain}


def _kind(ref: str) -> str:
    if ref.startswith("maya://"):
        return ref[7:].split("/")[0]
    return "other"


def _enc(v: Any) -> Any:
    if isinstance(v, (dt.datetime, dt.date)):
        return {"$dt": v.isoformat()}
    if isinstance(v, decimal.Decimal):
        return {"$dec": str(v)}
    raise TypeError(type(v).__name__)


def _decode(table: Any, row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if isinstance(v, dict) and set(v) == {"$dt"}:
            text = v["$dt"]
            out[k] = dt.datetime.fromisoformat(text) if "T" in text else dt.date.fromisoformat(text)
        elif isinstance(v, dict) and set(v) == {"$dec"}:
            out[k] = decimal.Decimal(v["$dec"])
        else:
            out[k] = v
    return out


__all__ = ["OpsService", "MODELS"]
