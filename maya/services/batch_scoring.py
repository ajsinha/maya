"""
Attested batch scoring: a pinned feature set scored under a live execution warrant.

MAYA still does not serve models. What it does here is narrow, and the same thing it already
does for blind scoring: a model with a formula is evaluated from its IR with the warrant's
approved parameters, and a declared black box runs its validated artifact in the sandbox. It
does so only while the execution warrant is live in the environment asked for, as a job, on a
*pin* -- data frozen by content -- so a batch is reproducible to the byte.

Every batch is attested three ways at once. The output table is sealed by its content hash
and stored; the run is reported on the warrant exactly as an external caller would report
it, so its covenants are evaluated and a breach suspends the warrant; and the warrant's
custody chain records which pin went in and which hash came out. The person who asked may
download the output; nothing about it is asserted by anyone.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import io
import math
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from maya.core import canonical
from maya.core.errors import NotFound, PermissionDenied, ValidationFailed
from maya.formula import ir as irmod
from maya.security.authz import Principal
from maya.services import refs

JOB = "execution.batch_score"
MAX_ROWS = 5_000_000


def _stats(values: np.ndarray, edges: builtins.list[float] | None = None) -> dict[str, Any]:
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return {}
    finite = arr[~np.isnan(arr)]
    out: dict[str, Any] = {"null_rate": float(1 - len(finite) / len(arr)) if len(arr) else 0.0}
    if len(finite):
        out.update(mean=float(finite.mean()), min=float(finite.min()), max=float(finite.max()))
        if edges:
            counts, _ = np.histogram(np.clip(finite, edges[0], edges[-1]), bins=edges)
            out["histogram"] = [int(c) for c in counts]
    return {k: v for k, v in out.items() if not (isinstance(v, float) and math.isnan(v))}


class BatchScoring:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def submit(self, p: Principal, ew_id: str, *, pin: str, environment: str) -> dict[str, Any]:
        """Queue a batch: checked now, so a refusal comes back at once rather than as a job."""
        if not refs.parse(pin, "featureset").is_pin:
            raise ValidationFailed("Batch scoring reads a pin: maya://featureset/ns/name#pin/date")
        with self.p.uow(p.username) as uow:
            ew, ns = self.p.execution._load(uow, ew_id)
            self.p.access.require(uow, p, "read", "execution_warrant", ew)
            self.p.execution.check(ew, environment)
            job = self.p.jobs.submit(
                uow,
                JOB,
                {"ew_id": ew_id, "pin": pin, "environment": environment, "user_id": p.user_id},
                owner=p.username,
            )
            uow.audit(
                "warrant.batch_requested",
                object_type="execution_warrant",
                object_ref=self.p.execution.uri(ew, ns),
                detail={"pin": pin, "environment": environment, "job": job["id"]},
            )
            return job

    def run_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        with self.p.uow() as uow:
            p = self.p.auth.build_principal(uow, params["user_id"])
            ew, ns = self.p.execution._load(uow, params["ew_id"])
            self.p.execution.check(ew, params["environment"])
            mv = uow.repo("model_versions").require(ew["model_version_id"])
            values = (
                uow.repo("parameter_sets").require(ew["parameter_set_id"])["values"]
                if ew.get("parameter_set_id")
                else {}
            )
            tw = (
                uow.repo("training_warrants").get(ew["training_warrant_id"])
                if ew.get("training_warrant_id")
                else None
            )
        bindings = (tw or {}).get("spec", {}).get("bindings", {})
        ctx.progress(10, "resolving the pin")
        res = self.p.featuresets.resolve_ref(p, params["pin"])
        frame = res.df.reset_index(drop=True)
        if len(frame) > MAX_ROWS:
            raise ValidationFailed(
                f"A batch is at most {MAX_ROWS:,} rows; this pin has {len(frame):,}"
            )
        wanted = [c["name"] for c in mv["input_contract"] or []]
        missing = [n for n in wanted if bindings.get(n, n) not in frame.columns]
        if missing:
            raise ValidationFailed(f"The pin does not carry the model's inputs {missing}")
        ctx.progress(40, "scoring")
        if irmod.is_opaque(mv["formula_ir"] or {}):
            pred, provenance = self.p.warrants._predict_blind(
                mv, frame, bindings, values, target=None
            )
        else:
            pred, provenance = self.p.warrants.predict(mv, frame, bindings, values), {}
        output = (mv["formula_ir"].get("outputs") or [{"name": "prediction"}])[0]["name"]
        index = [c for c in res.meta.get("index", []) if c in frame.columns]
        table = pa.table(
            {**{c: frame[c].tolist() for c in index}, output: np.asarray(pred, dtype=float)}
        )
        content_hash = canonical.table_content_hash(table)
        buf = io.BytesIO()
        pq.write_table(table, buf)
        blob = self.p.blobs.put(buf.getvalue())
        edges = {
            c["attr"]: c["bin_edges"]
            for c in ew["spec"].get("covenants", [])
            if c.get("kind") == "input_psi" and c.get("bin_edges")
        }
        ctx.progress(80, "reporting the run")
        report = self.p.execution.report(
            p,
            params["ew_id"],
            environment=params["environment"],
            rows=len(frame),
            input_stats={
                n: _stats(frame[bindings.get(n, n)].to_numpy(), edges.get(n)) for n in wanted
            },
            output_stats={output: _stats(np.asarray(pred))},
        )
        with self.p.uow(p.username) as uow:
            self.p.warrants._custody(
                uow,
                params["ew_id"],
                "batch_scored",
                p.username,
                detail={"pin": params["pin"], "output_hash": content_hash, "rows": len(frame)},
                warrant_type="exec",
            )
        return {
            "rows": len(frame),
            "output": output,
            "output_blob": blob,
            "output_hash": content_hash,
            "status_after": report["status"],
            "breaches": report["breaches"],
            **provenance,
        }

    def list(self, p: Principal, ew_id: str) -> builtins.list[dict[str, Any]]:
        with self.p.uow() as uow:
            ew, _ = self.p.execution._load(uow, ew_id)
            self.p.access.require(uow, p, "read", "execution_warrant", ew)
            jobs = uow.repo("jobs").list(job_type=JOB, order_by=["-created_at"], limit=200)
        return [
            {
                k: j[k]
                for k in ("id", "state", "created_at", "created_by", "result", "error", "params")
            }
            for j in jobs
            if (j.get("params") or {}).get("ew_id") == ew_id
        ]

    def output(self, p: Principal, ew_id: str, job_id: str) -> dict[str, Any]:
        batch = next((b for b in self.list(p, ew_id) if b["id"] == job_id), None)
        if batch is None or batch["state"] != "succeeded":
            raise NotFound("No finished batch with that id on this warrant")
        if batch["created_by"] not in (p.username, None) and not p.is_admin:
            raise PermissionDenied("A batch's output is downloaded by whoever ran it")
        return {
            "data": self.p.blobs.get(batch["result"]["output_blob"]),
            "filename": f"batch-{job_id[:8]}.parquet",
            "content_hash": batch["result"]["output_hash"],
        }
