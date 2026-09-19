"""
Feature data: ingest, resolution (live and derived) and pin materialization.

Resolution order for one feature version, stated in every plan:

1. source rows — the bitemporal ingest log (or, for ``derived``, the algebra
   replayed over resolved operands or their pins);
2. knowledge-time cut at ``as_of_known`` and latest row per key (§29.1);
3. grid and resolution rules, with the fill report (§5.3);
4. the transformation pipeline (§5.4);
5. the quality contract (§5.5) — which blocks a pin, never warns.

Pinning is a saga (§15.3): write fragments → re-read and verify the hash →
commit metadata. Nothing is usable until the metadata commit succeeds; a
failure leaves the pin ``failed`` and its unreferenced fragments reclaimable.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from maya.core.backends import Backends
from maya.core.errors import QualityCheckFailed, ValidationFailed
from maya.core.version import VERSION
from maya.core.clock import utcnow
from maya.resolution import algebra, quality, shapes
from maya.resolution.resolver import KT, resolve_feature
from maya.resolution.transforms import apply_pipeline
from maya.resolution.types import cast_frame
from maya.services import catalog, refs


@dataclass
class Resolved:
    """A resolved frame with everything needed to explain and reproduce it."""

    df: pd.DataFrame
    meta: dict[str, Any]
    fill_report: dict[str, Any]
    inputs: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)

    @property
    def full_schema(self) -> list[dict[str, Any]]:
        idx = [{"name": c, "type": self.meta["index_types"].get(c, "string")}
               for c in self.meta["index"]]
        return idx + self.meta["schema"] + [{"name": KT, "type": "timestamp"}]


def full_schema(eff: dict[str, Any]) -> list[dict[str, Any]]:
    idx = [{"name": c, "type": eff["index_types"][c], "nullable": False} for c in eff["index"]]
    return idx + list(eff["schema"])


def schema_generation(eff: dict[str, Any]) -> str:
    """Raw ingest tables are keyed by schema so an additive change starts a fresh log."""
    from maya.core import djson
    cols = eff.get("data_schema") or [[a["name"], a["type"]] for a in full_schema(eff)]
    return djson.canonical_hash([list(c) for c in cols])[:12]


class FeatureData:
    """Data-plane operations for features. Holds no state beyond the platform."""

    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- ingest -------------------------------------------------------------------
    def parse_upload(self, data: bytes, fmt: str, options: dict[str, Any] | None = None
                     ) -> pd.DataFrame:
        options = options or {}
        buf = io.BytesIO(data)
        if fmt == "csv":
            return pd.read_csv(buf, sep=options.get("delimiter", ","),
                               header=0 if options.get("header", True) else None)
        if fmt == "parquet":
            return pq.read_table(buf).to_pandas()
        if fmt == "json":
            if options.get("lines", False) or data.lstrip()[:1] != b"[":
                return pd.read_json(buf, lines=True)
            return pd.json_normalize(pd.read_json(buf).to_dict("records"),
                                     record_path=options.get("record_path"))
        raise ValidationFailed(f"Unsupported upload format '{fmt}' (csv, parquet, json)")

    def prepare_ingest(self, eff: dict[str, Any], frame: pd.DataFrame,
                       knowledge_time: dt.datetime) -> pa.Table:
        """Validate and type an upload against the definition; stamp knowledge time."""
        cols = [a["name"] for a in full_schema(eff)]
        missing = [c for c in cols if c not in frame.columns]
        if missing:
            raise ValidationFailed(f"The upload is missing column(s): {', '.join(missing)}",
                                   missing=missing, found=list(frame.columns))
        kcol = (eff.get("source") or {}).get("knowledge_time_column")
        out = cast_frame(frame[cols].copy(), full_schema(eff))
        if kcol and kcol in frame.columns:
            out[KT] = pd.to_datetime(frame[kcol], utc=True)
            if out[KT].isna().any():
                raise ValidationFailed(f"Column '{kcol}' has missing knowledge times")
        else:
            out[KT] = pd.Timestamp(knowledge_time).tz_convert("UTC") \
                if pd.Timestamp(knowledge_time).tzinfo else pd.Timestamp(knowledge_time, tz="UTC")
        schema = full_schema(eff) + [{"name": KT, "type": "timestamp"}]
        return shapes.parquet_safe(shapes.to_arrow(out, schema))

    def raw_frame(self, ns: str, name: str, eff: dict[str, Any]) -> pd.DataFrame | None:
        src = (eff.get("source") or {})
        if src.get("type") == "delta":
            table = self.p.lake.delta.read(src["path"])
            df = table.to_pandas()
            df[KT] = pd.Timestamp(utcnow())
            return df
        table = self.p.lake.read_raw(ns, f"{name}/{schema_generation(eff)}")
        return None if table is None else table.to_pandas()

    # -- resolution ---------------------------------------------------------------
    def resolve_ref(self, ref: str | refs.Ref, *, as_of_known: Any = None,
                    start: dt.date | None = None, end: dt.date | None = None,
                    depth: int = 0) -> Resolved:
        """Resolve a feature reference: a pin is read exactly; a version is resolved."""
        r = refs.parse(str(ref), "feature") if isinstance(ref, str) else ref
        if depth > catalog.MAX_DERIVATION_DEPTH:
            raise ValidationFailed("Derivation depth cap exceeded", cap=catalog.MAX_DERIVATION_DEPTH)
        with self.p.uow() as uow:
            feature, ns = catalog.find_object(uow, "features", "feature", r)
            if r.is_pin:
                pin = self.find_pin(uow, feature, r)
                version = uow.repo("feature_versions").require(pin["feature_version_id"])
            else:
                pin = None
                version = catalog.overlaid("feature", feature["id"], catalog.version_of(
                    uow, "feature_versions", "feature_id", feature, r.version), r.version)
            eff = catalog.effective_feature_definition(uow, version["definition"])
        if pin is not None:
            return self.read_pin(ns["name"], feature["name"], eff, pin)
        return self.resolve_definition(ns["name"], feature["name"], eff,
                                       as_of_known=as_of_known, start=start, end=end,
                                       depth=depth, label=refs.version_ref(
                                           "feature", ns["name"], feature["name"],
                                           version["version_no"]))

    def find_pin(self, uow: Any, feature: dict[str, Any], r: refs.Ref) -> dict[str, Any]:
        filters: dict[str, Any] = {"feature_id": feature["id"], "pin_name": r.series,
                                   "state": "sealed"}
        if r.as_of:
            filters["as_of_date"] = r.as_of
        rows = uow.repo("feature_pins").list(**filters, order_by=["-as_of_date"], limit=1)
        if not rows:
            from maya.core.errors import NotFound
            raise NotFound(f"No sealed pin {r}", ref=str(r))
        return rows[0]

    def resolve_definition(self, ns: str, name: str, eff: dict[str, Any], *,
                           as_of_known: Any = None, start: dt.date | None = None,
                           end: dt.date | None = None, depth: int = 0,
                           label: str = "") -> Resolved:
        src = eff.get("source") or {}
        attrs = [a["name"] for a in eff["schema"]]
        plan: list[str] = []
        inputs: list[str] = []
        inherited_nc = False
        if src.get("type") == "derived":
            raw, meta_in, inputs, plan = self._derive(src.get("derivation") or {},
                                                      as_of_known, start, end, depth)
            index = meta_in["index"]
            inherited_nc = bool(meta_in.get("non_causal"))
            eff = {**eff, "index": index, "index_types": meta_in.get("index_types", {})}
            plan.append(f"{label}: algebra '{src['derivation']['operator']}' over "
                        f"{len(inputs)} operand(s)")
        else:
            src_ns, src_name = (eff["data_from"].split("/", 1) if eff.get("data_from")
                                else (ns, name))
            raw = self.raw_frame(src_ns, src_name, eff)
            index = eff["index"]
            if raw is None:
                raw = pd.DataFrame({c: [] for c in index + attrs + [KT]})
            plan.append(f"{label}: read ingest log ({len(raw)} source rows)")
        known = None if src.get("type") == "derived" else as_of_known
        df, report = resolve_feature(raw, index=index, attributes=attrs,
                                     policy=eff.get("resolution") or {}, as_of_known=known,
                                     start=start, end=end)
        plan.append(f"knowledge-time cut at {as_of_known or 'now'}; grid "
                    f"{report['grid']}; rules per attribute")
        if eff.get("transform"):
            df = apply_pipeline(df, eff["transform"], index)
            plan.append(f"transform pipeline: {len(eff['transform'])} step(s)")
        non_causal = bool(report["non_causal"]) or inherited_nc
        meta = {"index": index, "index_types": eff.get("index_types", {}),
                "schema": eff["schema"], "non_causal": non_causal,
                "policy": eff.get("resolution") or {}}
        return Resolved(df, meta, report, inputs, plan)

    def _derive(self, derivation: dict[str, Any], as_of_known: Any, start: Any, end: Any,
                depth: int) -> tuple[pd.DataFrame, dict[str, Any], list[str], list[str]]:
        operands = [self.resolve_ref(o, as_of_known=as_of_known, start=start, end=end,
                                     depth=depth + 1) for o in derivation.get("operands") or []]
        metas = [o.meta for o in operands]
        frames = [o.df for o in operands]
        out_meta = algebra.typecheck(derivation["operator"], derivation.get("options"), metas)
        df = algebra.execute(derivation["operator"], derivation.get("options"), frames, metas)
        out_meta.setdefault("index_types", operands[0].meta.get("index_types", {}))
        plan = [line for o in operands for line in o.plan]
        return df, out_meta, list(derivation.get("operands") or []), plan

    def operand_metas(self, derivation: dict[str, Any]) -> list[dict[str, Any]]:
        """Definition-time metas of a derivation's operands (no data read)."""
        out = []
        with self.p.uow() as uow:
            for o in derivation.get("operands") or []:
                r = refs.parse(o, "feature")
                feature, _ = catalog.find_object(uow, "features", "feature", r)
                if r.is_pin:
                    pin = self.find_pin(uow, feature, r)
                    version = uow.repo("feature_versions").require(pin["feature_version_id"])
                else:
                    version = catalog.version_of(uow, "feature_versions", "feature_id",
                                                 feature, r.version)
                eff = catalog.effective_feature_definition(uow, version["definition"])
                out.append({"index": eff["index"], "index_types": eff.get("index_types", {}),
                            "schema": eff["schema"], "non_causal": version["non_causal"]})
        return out

    # -- pins -----------------------------------------------------------------------
    def read_pin(self, ns: str, name: str, eff: dict[str, Any], pin: dict[str, Any]) -> Resolved:
        table = self.p.lake.read_pin("pins", ns, name, pin["fragments"])
        df = table.to_pandas()
        meta = {"index": eff["index"], "index_types": eff.get("index_types", {}),
                "schema": eff["schema"], "non_causal": bool(pin["fill_report"].get("non_causal")),
                "policy": eff.get("resolution") or {}}
        ref = refs.pin_ref("feature", ns, name, pin["pin_name"], pin["as_of_date"])
        return Resolved(df, meta, pin["fill_report"], [], [f"{ref}: read sealed pin "
                                                           f"({len(pin['fragments'])} fragments)"])

    def materialize(self, pin_id: str, actor: str) -> dict[str, Any]:
        """The pin saga for one feature pin row (runs inside a job)."""
        with self.p.uow(actor) as uow:
            pin = uow.repo("feature_pins").require(pin_id)
            feature = uow.repo("features").require(pin["feature_id"])
            ns = uow.repo("namespaces").require(feature["namespace_id"])
            version = uow.repo("feature_versions").require(pin["feature_version_id"])
            eff = catalog.effective_feature_definition(uow, version["definition"])
            uow.lock(f"feature:{feature['id']}")
        label = refs.version_ref("feature", ns["name"], feature["name"], version["version_no"])
        res = self.resolve_definition(ns["name"], feature["name"], eff,
                                      as_of_known=pin["as_of_known"], end=pin["as_of_date"],
                                      label=label)
        checks = quality.run_checks(res.df, eff.get("quality") or [], res.meta["index"],
                                    as_of=pin["as_of_date"])
        failed = [c for c in checks if not c["passed"]]
        if failed:
            self._fail_pin(pin_id, actor, checks, "quality check(s) failed: " +
                           "; ".join(f"{c['check']}({c.get('attr') or ''}): {c['detail']}"
                                     for c in failed))
            raise QualityCheckFailed("Pin blocked by the quality contract", checks=checks)
        if res.df.empty:
            self._fail_pin(pin_id, actor, checks, "resolution produced no rows")
            raise ValidationFailed("Nothing to pin: resolution produced no rows (no data "
                                   "ingested, or none known at as_of_known)")
        table = self.to_table(res)
        write, lake_table = self._write_fragments(ns["name"], feature["name"], table)
        verify = self.p.lake.verify_pin("pins", ns["name"], feature["name"], write.fragments,
                                        write.content_hash)
        if not verify["ok"]:
            self._fail_pin(pin_id, actor, checks, "hash verification after write failed")
            raise ValidationFailed("Pin hash verification failed after write", **verify)
        return self._seal(pin_id, actor, write, lake_table, res, checks, version, label)

    def to_table(self, res: Resolved) -> pa.Table:
        df = res.df.sort_values(res.meta["index"], kind="mergesort").reset_index(drop=True)
        return shapes.parquet_safe(shapes.to_arrow(df, res.full_schema)).replace_schema_metadata(None)

    def _write_fragments(self, ns: str, name: str, table: pa.Table, kind: str = "pins"
                         ) -> tuple[Any, str]:
        lake_table = self.p.lake.rel(self.p.lake.table_path(kind, ns, name))
        with self.p.uow() as uow:
            known = {f["hash"] for f in uow.repo("fragments").list(lake_table=lake_table)}
        write = self.p.lake.write_pin(kind, ns, name, table, known)
        with self.p.uow() as uow:
            for digest, rows, size in write.new_fragments:
                if uow.repo("fragments").find_one(hash=digest, lake_table=lake_table) is None:
                    uow.repo("fragments").add({"hash": digest, "lake_table": lake_table,
                                               "rows": rows, "bytes": size,
                                               "created_at": utcnow()})
        return write, lake_table

    def _seal(self, pin_id: str, actor: str, write: Any, lake_table: str, res: Resolved,
              checks: list[dict[str, Any]], version: dict[str, Any], label: str
              ) -> dict[str, Any]:
        provenance = self.provenance(version["definition_hash"], res, write, actor)
        with self.p.uow(actor) as uow:
            pin = uow.repo("feature_pins").update(pin_id, {
                "state": "sealed", "content_hash": write.content_hash,
                "schema_digest": write.schema_digest, "fragments": write.fragments,
                "lake_table": lake_table, "row_count": write.rows,
                "bytes_total": write.bytes_total, "bytes_new": write.bytes_new,
                "fill_report": res.fill_report, "quality": checks, "provenance": provenance,
                "sealed_at": utcnow()})
            feature = uow.repo("features").require(pin["feature_id"])
            ns = uow.repo("namespaces").require(feature["namespace_id"])
            pin_uri = refs.pin_ref("feature", ns["name"], feature["name"], pin["pin_name"],
                                   pin["as_of_date"])
            uow.repo("lineage_edges").link(label, pin_uri, "pinned_as")
            from maya.observability.metrics import METRICS
            METRICS.inc("maya_pins_sealed_total", {"kind": "feature"})
            METRICS.inc("maya_pin_new_bytes_total", value=float(write.bytes_new))
            uow.audit("pin.sealed", object_type="feature_pin", object_ref=pin_uri,
                      detail={"content_hash": write.content_hash, "rows": write.rows,
                              "fragments": len(write.fragments),
                              "new_fragments": len(write.new_fragments)})
            return pin

    def provenance(self, definition_hash: str | None, res: Resolved, write: Any,
                   actor: str) -> dict[str, Any]:
        import sys
        import pyarrow
        return {"definition_hash": definition_hash, "engine_version": VERSION,
                "python": sys.version.split()[0], "pyarrow": pyarrow.__version__,
                "pandas": pd.__version__, "backends": Backends.provenance(),
                "lake_backend": self.p.lake.backend_name,
                "chunk_params": self.p.lake.chunk.as_dict(), "actor": actor,
                "wall_clock": utcnow().isoformat(), "plan": res.plan,
                "inputs": res.inputs, "content_hash": write.content_hash}

    def fail_if_unfinished(self, pin_id: str, actor: str, exc: BaseException) -> None:
        with self.p.uow() as uow:
            state = uow.repo("feature_pins").require(pin_id)["state"]
        if state == "materializing":
            self._fail_pin(pin_id, actor, [], f"{type(exc).__name__}: {exc}"[:2000])

    def _fail_pin(self, pin_id: str, actor: str, checks: list[dict[str, Any]], why: str) -> None:
        with self.p.uow(actor) as uow:
            uow.repo("feature_pins").update(pin_id, {"state": "failed", "quality": checks,
                                                     "failure": why})
            uow.audit("pin.failed", object_type="feature_pin", object_ref=pin_id,
                      detail={"reason": why})
