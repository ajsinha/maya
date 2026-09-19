"""
Training warrants and parameter sets (§9.1, §9.3–§9.5, §29.1, §29.4).

The checksum cycle is what turns a warrant from paperwork into a control:
every download records the content hash MAYA issued; a parameter upload
names the checksum it trained on, and a set whose checksum MAYA never issued
is flagged ``unverified_data`` and cannot be approved without a written,
justified override. The checksum is a *content* hash over canonical values,
so the SDK recomputes it from the table it received, whatever the format.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from maya.core import canonical, djson
from maya.core.backends import Backends
from maya.core.errors import (ContractMismatch, NotApproved, PermissionDenied,
                              ValidationFailed, WarrantExpired)
from maya.formula import ir as irmod
from maya.formula.evaluate import evaluate, evaluate_composite
from maya.persistence.types import utcnow
from maya.resolution.resolver import KT
from maya.security.authz import Principal
from maya.services import catalog, refs
from maya.workflow.engine import Subject

NUMERIC = ("int32", "int64", "float32", "float64", "decimal", "bool")
SPLIT_COL = "_split"


table_checksum = canonical.table_content_hash


def assign_splits(df: pd.DataFrame, index: list[str], split: dict[str, float],
                  seed: int) -> pd.Series:
    """Deterministic split by hashing (seed, index key): reproducible anywhere."""
    fracs = [float(split.get(k, 0)) for k in ("train", "validation", "test")]
    if abs(sum(fracs) - 1.0) > 1e-9 or any(f < 0 for f in fracs):
        raise ValidationFailed("split fractions train/validation/test must be ≥0 and sum to 1")
    keys = df[index].astype(str).agg("|".join, axis=1)
    u = keys.map(lambda k: int.from_bytes(hashlib.sha256(f"{seed}|{k}".encode()).digest()[:8],
                                          "big") / 2 ** 64)
    return pd.Series(np.where(u < fracs[0], "train",
                              np.where(u < fracs[0] + fracs[1], "validation", "test")),
                     index=df.index)


class WarrantService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- lookups -------------------------------------------------------------------
    def _load(self, uow: Any, warrant_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        w = uow.repo("training_warrants").require(warrant_id)
        return w, uow.repo("namespaces").require(w["namespace_id"])

    def _model(self, uow: Any, model_ref: str) -> tuple[dict[str, Any], dict[str, Any],
                                                        dict[str, Any]]:
        r = refs.parse(model_ref, "model")
        model, ns = catalog.find_object(uow, "models", "model", r)
        return model, ns, catalog.version_of(uow, "model_versions", "model_id", model, r.version)

    def uri(self, w: dict[str, Any], ns: dict[str, Any]) -> str:
        return f"maya://warrant/train/{ns['name']}/{w['name']}@v{w['version_no']}"

    def listing(self, uow: Any, p: Principal, *, q: str | None = None) -> Any:
        from maya.services.paging import Listing
        names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
        return Listing(
            "training_warrants", {"-created": "-created_at", "created": "created_at",
                                  "name": "name", "-name": "-name"},
            "-created", {}, (["name"], q or ""),
            keep=lambda uow, w: self.p.access.allowed(uow, p, "read", "training_warrant", w),
            enrich=lambda uow, w: {**w, "namespace": names.get(w["namespace_id"]),
                                   "status": self.status(w),
                                   "uri": f"maya://warrant/train/{names.get(w['namespace_id'])}/"
                                          f"{w['name']}@v{w['version_no']}"})

    def list(self, p: Principal) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return self.listing(uow, p).collect(uow)

    def page(self, p: Principal, *, q: str | None = None, page_size: int | None = None,
             cursor: str | None = None, sort: str | None = None, total: bool = False) -> dict[str, Any]:
        from maya.services.paging import run_page
        return run_page(self.p, lambda uow: self.listing(uow, p, q=q), page_size=page_size,
                        cursor=cursor, sort=sort, total=total)

    @staticmethod
    def status(w: dict[str, Any]) -> str:
        if w.get("revoked_at"):
            return "revoked"
        if w.get("expires_at") and w["expires_at"] < utcnow():
            return "expired"
        if w.get("sealed_at"):
            return "sealed"
        return w["state"]

    def get(self, p: Principal, warrant_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            w, ns = self._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
            mv = uow.repo("model_versions").require(w["model_version_id"])
            model = uow.repo("models").require(mv["model_id"])
            return {**w, "namespace": ns["name"], "status": self.status(w), "uri": self.uri(w, ns),
                    "model": {"name": model["name"], "version_no": mv["version_no"],
                              "ir_hash": mv["ir_hash"], "artifact_hash": mv["artifact_hash"]},
                    "custody": uow.repo("custody_events").list(warrant_type="train",
                                                               warrant_id=warrant_id,
                                                               order_by=["created_at"]),
                    "parameter_sets": uow.repo("parameter_sets").list(
                        training_warrant_id=warrant_id, order_by=["created_at"]),
                    "holdout_scores": uow.repo("holdout_scores").list(
                        training_warrant_id=warrant_id, order_by=["attempt_no"]),
                    "transitions": self.p.workflow.available(uow, self.subject(uow, w, ns))}

    # -- creation --------------------------------------------------------------------
    def create(self, p: Principal, *, namespace: str, name: str, model: str, featureset: str,
               spec: dict[str, Any]) -> dict[str, Any]:
        spec = self._normalise_spec(spec)
        with self.p.uow() as uow:
            ns = self.p.access.namespace(uow, namespace)
            self.p.access.require(uow, p, "create", "training_warrant",
                                  {"id": "new", "namespace_id": ns["id"], "name": name})
            mobj, mns, mv = self._model(uow, model)
            if mv["state"] not in catalog.APPROVED_STATES:
                raise NotApproved(f"{model} is '{mv['state']}'; warrants are drawn on approved "
                                  "model versions")
            model_uri = refs.version_ref("model", mns["name"], mobj["name"], mv["version_no"])
        self.p.licences.derivation("featureset", [featureset], "training a model on it")
        res = self.p.featuresets.resolve_ref(p, featureset)
        report = self.validate_contract(mv, res.meta, spec)
        if not report["ok"]:
            raise ContractMismatch("The feature set does not satisfy the model's input "
                                   "contract: " + "; ".join(report["problems"]), **report)
        certificate = self.leakage_certificate(res, spec)
        fsp_id = self._fs_pin_id(featureset)
        with self.p.uow(p.username) as uow:
            prior = uow.repo("training_warrants").list(namespace_id=ns["id"], name=name,
                                                       order_by=["-version_no"], limit=1)
            w = uow.repo("training_warrants").add({
                "namespace_id": ns["id"], "name": name,
                "version_no": prior[0]["version_no"] + 1 if prior else 1, "state": "draft",
                "owner_id": p.user_id, "model_version_id": mv["id"], "featureset_ref": featureset,
                "feature_set_pin_id": fsp_id, "spec": {**spec, "model_ref": model_uri},
                "contract_report": report, "leakage_certificate": certificate,
                "backends": Backends.provenance(),
                "expires_at": utcnow() + dt.timedelta(days=int(spec["expiry_days"]))})
            self._custody(uow, w["id"], "created", p.username,
                          detail={"model": model_uri, "featureset": featureset})
            me = self.uri(w, ns)
            uow.repo("lineage_edges").link(model_uri, me, "trained_on", "model")
            uow.repo("lineage_edges").link(featureset, me, "trained_on", "data")
            uow.audit("warrant.created", object_type="training_warrant", object_ref=me,
                      detail={"certificate": certificate["status"]})
            return w

    def _normalise_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        out = {"split": {"train": 0.7, "validation": 0.15, "test": 0.15}, "seed": 42,
               "shape": "tabular", "holdout": "escrowed", "expiry_days": 365,
               "leakage_lag_days": 1, "bindings": {}, "target": None,
               "environment": {"python": "3.13"}, "objective": "", "metrics": ["rmse"],
               "allow_non_causal": False, "non_causal_justification": "",
               "leakage_justification": ""}
        out.update({k: v for k, v in spec.items() if v is not None})
        if out["holdout"] not in ("escrowed", "none"):
            raise ValidationFailed("holdout must be 'escrowed' or 'none'")
        return out

    def _fs_pin_id(self, featureset: str) -> str | None:
        r = refs.parse(featureset, "featureset")
        if not r.is_pin:
            return None
        _, _, _, pin, _, _ = self.p.featuresets.load(featureset)
        return pin["id"] if pin else None

    def validate_contract(self, mv: dict[str, Any], meta: dict[str, Any],
                          spec: dict[str, Any]) -> dict[str, Any]:
        """Check the model's input contract against the feature set, listing every miss."""
        attrs = {a["name"]: a.get("type", "") for a in meta["schema"]}
        problems, mapping = [], {}
        for inp in mv["input_contract"] or []:
            if inp.get("role", "feature") != "feature":
                continue
            src = spec["bindings"].get(inp["name"], inp["name"])
            if src not in attrs:
                problems.append(f"input '{inp['name']}' needs attribute '{src}', which the "
                                "feature set does not expose")
                continue
            if not str(attrs[src]).startswith(NUMERIC):
                problems.append(f"input '{inp['name']}' is {inp.get('type', 'float64')} but "
                                f"'{src}' is {attrs[src]}")
            mapping[inp["name"]] = src
        target = spec.get("target")
        if target and target not in attrs:
            problems.append(f"target '{target}' is not an attribute of the feature set")
        return {"ok": not problems, "problems": problems, "mapping": mapping,
                "checked_at": utcnow().isoformat()}

    def leakage_certificate(self, res: Any, spec: dict[str, Any]) -> dict[str, Any]:
        """Prove no row uses a value MAYA could not have known by its event time (§29.1)."""
        df, index = res.df, res.meta["index"]
        lag = dt.timedelta(days=int(spec["leakage_lag_days"]))
        violations: list[dict[str, Any]] = []
        examined = len(df)
        if KT in df.columns and examined:
            event = pd.to_datetime(df[index[0]]).dt.tz_localize("UTC") \
                if pd.to_datetime(df[index[0]]).dt.tz is None else pd.to_datetime(df[index[0]])
            kt = pd.to_datetime(df[KT], utc=True)
            bad = kt.notna() & (kt > event + lag + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
            for _, row in df[bad].head(20).iterrows():
                violations.append({c: str(row[c]) for c in index + [KT]})
            n_bad = int(bad.sum())
        else:
            n_bad = 0
        exceptions = []
        nc = res.fill_report.get("non_causal") or []
        if nc:
            exceptions.append({"rule": "non-causal fill", "attributes": nc,
                               "justification": spec.get("non_causal_justification") or None})
        if n_bad:
            exceptions.append({"rule": f"knowledge time > event time + {lag.days}d",
                               "rows": n_bad,
                               "justification": spec.get("leakage_justification") or None})
        unjustified = [e for e in exceptions if not e["justification"]]
        if nc and not spec.get("allow_non_causal"):
            unjustified.append({"rule": "non-causal fill without allow_non_causal"})
        status = "refused" if unjustified else ("certified_with_exceptions" if exceptions
                                                else "certified")
        body = {"rule": f"every row's knowledge time ≤ its event date + {lag.days} day(s)",
                "rows_examined": examined, "violations": n_bad, "examples": violations,
                "exceptions": exceptions, "status": status, "issued_at": utcnow().isoformat()}
        signer = self.p.signer_or_none()
        if signer is not None:
            body["signature"] = signer.signature_block(djson.canonical(body).encode())
        else:
            body["signature"] = None
            body["unsigned_reason"] = "crypto backend unavailable (Type C refusal)"
        return body

    # -- data, the checksum cycle -------------------------------------------------------
    def training_frame(self, w: dict[str, Any], *, include_test: bool,
                       principal: Principal | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
        """The warrant's data. With a principal, that person's §11.4 conditions apply:
        a download never shows what a direct read would have withheld."""
        res = self.p.featuresets.resolve_ref(principal, w["featureset_ref"])
        df = res.df.copy()
        df[SPLIT_COL] = assign_splits(df, res.meta["index"], w["spec"]["split"], w["spec"]["seed"])
        if not include_test:
            df = df[df[SPLIT_COL] != "test"]
        return df.reset_index(drop=True), res.meta

    def data(self, p: Principal, warrant_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            w, ns = self._load(uow, warrant_id)
            self.p.access.require(uow, p, "download", "training_warrant", w)
        self._live(w)
        self.p.licences.export(p, "featureset", w["featureset_ref"], "internal")
        escrow = w["spec"].get("holdout") == "escrowed"
        df, meta = self.training_frame(w, include_test=not escrow, principal=p)
        table = pa.Table.from_pandas(df, preserve_index=False).replace_schema_metadata(None)
        checksum = table_checksum(table)
        buf = io.BytesIO()
        pq.write_table(table, buf)
        manifest = {"warrant": self.uri(w, ns), "rows": table.num_rows, "checksum": checksum,
                    "escrowed_holdout": escrow, "split": w["spec"]["split"],
                    "seed": w["spec"]["seed"], "index": meta["index"],
                    "target": w["spec"].get("target"), "issued_at": utcnow().isoformat(),
                    "issued_to": p.username}
        with self.p.uow(p.username) as uow:
            self._custody(uow, warrant_id, "downloaded", p.username, checksum=checksum,
                          detail={"rows": table.num_rows})
            uow.audit("warrant.data_downloaded", object_type="training_warrant",
                      object_ref=self.uri(w, ns), detail={"checksum": checksum})
        return {"data": buf.getvalue(), "manifest": manifest}

    def _live(self, w: dict[str, Any]) -> None:
        if w["revoked_at"]:
            raise NotApproved(f"Warrant revoked: {w['revoke_reason']}")
        if w["expires_at"] and w["expires_at"] < utcnow():
            raise WarrantExpired("The training warrant has expired; clone it to continue")

    # -- parameters ------------------------------------------------------------------
    def upload_parameters(self, p: Principal, warrant_id: str, *, values: dict[str, Any],
                          metrics: dict[str, Any] | None = None, data_checksum: str | None = None,
                          name: str | None = None, notes: str = "",
                          member_alias: str | None = None) -> dict[str, Any]:
        with self.p.uow() as uow:
            w, ns = self._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
            self.p.access.require_capability(p, "parameter_set", "C")
            if w["sealed_at"]:
                raise NotApproved("The warrant is sealed; clone it to train again")
            self._live(w)
            mv = uow.repo("model_versions").require(w["model_version_id"])
            issued = {e["checksum"] for e in uow.repo("custody_events").list(
                warrant_type="train", warrant_id=warrant_id, event="downloaded")}
        problems = self.check_bounds(mv["formula_ir"] or {}, values, member_alias)
        if problems:
            raise ValidationFailed("Parameters out of bounds: " + "; ".join(problems),
                                   problems=problems)
        verified = bool(data_checksum) and data_checksum in issued
        with self.p.uow(p.username) as uow:
            ps = uow.repo("parameter_sets").add({
                "model_version_id": mv["id"], "training_warrant_id": warrant_id,
                "name": name or f"{w['name']}-params-{utcnow():%Y%m%d%H%M%S}", "state": "draft",
                "values": values, "values_hash": djson.canonical_hash(values),
                "param_schema": irmod.parameter_inputs(mv["formula_ir"])
                if (mv["formula_ir"] or {}).get("body") else [],
                "metrics": metrics or {}, "data_checksum": data_checksum,
                "verified_data": verified, "member_alias": member_alias, "notes": notes})
            self._custody(uow, warrant_id, "parameters_uploaded", p.username,
                          checksum=data_checksum,
                          detail={"parameter_set": ps["id"], "verified_data": verified})
            uri = self.uri(w, ns)
            uow.repo("lineage_edges").link(uri, f"maya://parameters/{ps['id']}", "parameterized_by")
            uow.audit("warrant.parameters_uploaded", object_type="training_warrant", object_ref=uri,
                      detail={"verified_data": verified, "values_hash": ps["values_hash"]})
            return {**ps, "flag": None if verified else "unverified_data"}

    @staticmethod
    def check_bounds(ir: dict[str, Any], values: dict[str, Any],
                     alias: str | None = None) -> list[str]:
        if not ir.get("body"):
            return []
        problems = []
        for inp in irmod.parameter_inputs(ir):
            key = f"{alias}.{inp['name']}" if alias else inp["name"]
            if key not in values and inp["name"] not in values:
                problems.append(f"missing parameter '{key}'")
                continue
            v = values.get(key, values.get(inp["name"]))
            lo, hi = (inp.get("bounds") or [None, None])[:2]
            if isinstance(v, (int, float)) and ((lo is not None and v < lo) or
                                                (hi is not None and v > hi)):
                problems.append(f"'{key}'={v} outside [{lo}, {hi}]")
        for inp in irmod.constant_inputs(ir):
            key = f"{alias}.{inp['name']}" if alias else inp["name"]
            if "value" not in inp and key not in values and inp["name"] not in values:
                problems.append(f"missing constant '{key}' (the model declares no value for it)")
        return problems

    def parameter_subject(self, uow: Any, ps: dict[str, Any]) -> Subject:
        w, ns = self._load(uow, ps["training_warrant_id"])
        owner = uow.repo("users").get(w["owner_id"])
        return Subject("parameter_set", "parameter_sets", ps["id"], f"maya://parameters/{ps['id']}",
                       "parameter_set", ps, ns, w["owner_id"], owner["username"] if owner else None,
                       [], {"warrant": w})

    def parameter_transition(self, p: Principal, ps_id: str, name: str, *,
                             rationale: str | None = None, force: bool = False,
                             justification: str | None = None) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            ps = uow.repo("parameter_sets").require(ps_id)
            if justification:
                ps = uow.repo("parameter_sets").update(ps_id, {
                    "unverified_justification": justification})
            out = self.p.workflow.transition(uow, p, self.parameter_subject(uow, ps), name,
                                             rationale=rationale, force=force)
            return out.__dict__

    def score_holdout(self, p: Principal, warrant_id: str, *, parameter_set_id: str | None = None,
                      values: dict[str, Any] | None = None) -> dict[str, Any]:
        """Blind scoring against the escrowed partition: metrics out, rows never (§29.4)."""
        with self.p.uow() as uow:
            w, ns = self._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
            mv = uow.repo("model_versions").require(w["model_version_id"])
            if parameter_set_id:
                values = uow.repo("parameter_sets").require(parameter_set_id)["values"]
        target = w["spec"].get("target")
        if not target:
            raise ValidationFailed("The warrant declares no target attribute to score against")
        df, _ = self.training_frame(w, include_test=True)
        test = df[df["_split"] == "test"]
        if test.empty:
            raise ValidationFailed("The holdout partition is empty")
        pred = self.predict(mv, test, w["spec"].get("bindings", {}), values or {})
        y = test[target].astype(float).to_numpy()
        err = pred - y
        metrics = {"rmse": float(np.sqrt(np.nanmean(err ** 2))),
                   "mae": float(np.nanmean(np.abs(err))), "rows": int(len(test))}
        with self.p.uow(p.username) as uow:
            w = uow.repo("training_warrants").update(warrant_id, {
                "holdout_attempts": w["holdout_attempts"] + 1})
            uow.repo("holdout_scores").add({"training_warrant_id": warrant_id,
                                            "parameter_set_id": parameter_set_id,
                                            "attempt_no": w["holdout_attempts"],
                                            "metrics": metrics})
            self._custody(uow, warrant_id, "holdout_scored", p.username,
                          detail={"attempt": w["holdout_attempts"], **metrics})
        return {"metrics": metrics, "attempt": w["holdout_attempts"],
                "note": "Every attempt is counted and shown on the warrant."}

    def predict(self, mv: dict[str, Any], df: pd.DataFrame, bindings: dict[str, str],
                values: dict[str, Any]) -> np.ndarray:
        ir = mv["formula_ir"] or {}
        if irmod.is_opaque(ir):
            raise ValidationFailed("A declared black box cannot be scored by MAYA")
        if "composite" in ir:
            with self.p.uow() as uow:
                members = self.p.models._member_irs(uow, ir)
            inputs = {c["name"]: df[bindings.get(c["name"], c["name"])].astype(float).to_numpy()
                      for m in members.values() for c in irmod.input_contract(m)
                      if bindings.get(c["name"], c["name"]) in df.columns}
            out = evaluate_composite(ir, members, inputs, values)
        else:
            inputs = {c["name"]: df[bindings.get(c["name"], c["name"])].astype(float).to_numpy()
                      for c in irmod.input_contract(ir)}
            out = evaluate(ir, inputs, values)
        return np.asarray(next(iter(out.values())), dtype=float)

    # -- workflow, sealing, custody -------------------------------------------------------
    def subject(self, uow: Any, w: dict[str, Any], ns: dict[str, Any]) -> Subject:
        owner = uow.repo("users").get(w["owner_id"])
        return Subject("training_warrant", "training_warrants", w["id"], self.uri(w, ns),
                       "training_warrant", w, ns, w["owner_id"],
                       owner["username"] if owner else None,
                       uow.repo("grants").list(object_type="training_warrant", object_id=w["id"]),
                       {"warrant": w})

    def transition(self, p: Principal, warrant_id: str, name: str, *,
                   rationale: str | None = None, force: bool = False) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            w, ns = self._load(uow, warrant_id)
            out = self.p.workflow.transition(uow, p, self.subject(uow, w, ns), name,
                                             rationale=rationale, force=force)
            if out.moved:
                self._custody(uow, warrant_id, name, p.username, detail={"to": out.state})
            return out.__dict__

    def seal(self, p: Principal, warrant_id: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            w, ns = self._load(uow, warrant_id)
            self.p.access.require(uow, p, "seal", "training_warrant", w)
            if w["state"] not in catalog.APPROVED_STATES:
                raise NotApproved("Only an approved warrant can be sealed")
            if w["sealed_at"]:
                raise NotApproved("Already sealed")
            mv = uow.repo("model_versions").require(w["model_version_id"])
            trainable = bool(irmod.parameter_inputs(mv["formula_ir"])) \
                if (mv["formula_ir"] or {}).get("body") else False
            accepted = uow.repo("parameter_sets").count(training_warrant_id=warrant_id,
                                                        state__in=catalog.APPROVED_STATES)
            if trainable and not accepted:
                raise NotApproved("A trainable model's warrant seals only with an approved "
                                  "parameter set")
            row = uow.repo("training_warrants").update(warrant_id, {"sealed_at": utcnow()})
            self._custody(uow, warrant_id, "sealed", p.username)
            uow.audit("warrant.sealed", object_type="training_warrant", object_ref=self.uri(w, ns))
            return row

    def revoke(self, p: Principal, warrant_id: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise ValidationFailed("Revocation requires a reason")
        with self.p.uow(p.username) as uow:
            w, ns = self._load(uow, warrant_id)
            if not (p.is_admin or self.p.access.allowed(uow, p, "revoke", "training_warrant", w)):
                raise PermissionDenied("Only the model owner or an administrator revokes")
            row = uow.repo("training_warrants").update(warrant_id, {
                "revoked_at": utcnow(), "revoke_reason": reason})
            for ew in uow.repo("execution_warrants").list(training_warrant_id=warrant_id,
                                                          revoked_at__isnull=True):
                uow.repo("execution_warrants").update(ew["id"], {
                    "revoked_at": utcnow(), "revoke_reason": f"training warrant revoked: {reason}"})
                uow.repo("notifications").add({"user_id": ew["owner_id"], "kind": "revocation",
                                               "message": f"Execution warrant {ew['name']} revoked: "
                                                          f"{reason}", "object_ref": ew["id"]})
            self._custody(uow, warrant_id, "revoked", p.username, detail={"reason": reason})
            uow.audit("warrant.revoked", object_type="training_warrant",
                      object_ref=self.uri(w, ns), detail={"reason": reason})
            return row

    def clone(self, p: Principal, warrant_id: str, changes: dict[str, Any] | None = None
              ) -> dict[str, Any]:
        """A new draft in the same family, linked to its origin (§9.3)."""
        with self.p.uow() as uow:
            w, ns = self._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
        spec = {**w["spec"], **(changes or {})}
        model_ref = spec.pop("model_ref")
        new = self.create(p, namespace=ns["name"], name=w["name"], model=model_ref,
                          featureset=(changes or {}).get("featureset", w["featureset_ref"]),
                          spec=spec)
        with self.p.uow(p.username) as uow:
            return uow.repo("training_warrants").update(new["id"], {"clone_of": warrant_id})

    def _custody(self, uow: Any, warrant_id: str, event: str, actor: str, *,
                 checksum: str | None = None, detail: dict[str, Any] | None = None,
                 warrant_type: str = "train") -> None:
        uow.repo("custody_events").add({"warrant_type": warrant_type, "warrant_id": warrant_id,
                                        "event": event, "actor": actor, "checksum": checksum,
                                        "detail": djson.loads(djson.dumps(detail or {}))})

    # -- checks ---------------------------------------------------------------------------
    def check_contract(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        report = ctx["row"]["contract_report"] or {}
        return (bool(report.get("ok")), "contract satisfied" if report.get("ok")
                else "; ".join(report.get("problems", [])) or "not validated")

    def check_leakage(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        cert = ctx["row"]["leakage_certificate"] or {}
        status = cert.get("status", "missing")
        return (status in ("certified", "certified_with_exceptions"),
                f"leakage certificate: {status}; {cert.get('violations', 0)} violating row(s)")

    def check_bounds_ok(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        ps = ctx["row"]
        mv = uow.repo("model_versions").require(ps["model_version_id"])
        problems = self.check_bounds(mv["formula_ir"] or {}, ps["values"], ps["member_alias"])
        return (not problems, "; ".join(problems) or "all parameters within declared bounds")

    def check_data_verified(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        ps = ctx["row"]
        if ps["verified_data"]:
            return True, "trained on data MAYA issued (checksum matched)"
        if ps["unverified_justification"]:
            return True, f"unverified_data overridden: {ps['unverified_justification']}"
        return False, ("unverified_data: the checksum does not match any download MAYA issued; "
                       "approve only with an explicit justification")
