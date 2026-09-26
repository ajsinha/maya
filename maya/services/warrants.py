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

import builtins
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
from maya.core.errors import (
    ContractMismatch,
    NotApproved,
    PermissionDenied,
    ValidationFailed,
    WarrantExpired,
)
from maya.formula import composite as comp
from maya.formula import ir as irmod
from maya.formula.evaluate import evaluate, evaluate_composite
from maya.core.clock import utcnow
from maya.resolution.resolver import KT
from maya.security.authz import Principal
from maya.services import catalog, refs
from maya.workflow.engine import Subject

NUMERIC = ("int32", "int64", "float32", "float64", "decimal", "bool")
SPLIT_COL = "_split"


table_checksum = canonical.table_content_hash


def assign_splits(
    df: pd.DataFrame, index: list[str], split: dict[str, float], seed: int
) -> pd.Series:
    """Deterministic split by hashing (seed, index key): reproducible anywhere."""
    fracs = [float(split.get(k, 0)) for k in ("train", "validation", "test")]
    if abs(sum(fracs) - 1.0) > 1e-9 or any(f < 0 for f in fracs):
        raise ValidationFailed("split fractions train/validation/test must be ≥0 and sum to 1")
    keys = df[index].astype(str).agg("|".join, axis=1)
    u = keys.map(
        lambda k: int.from_bytes(hashlib.sha256(f"{seed}|{k}".encode()).digest()[:8], "big") / 2**64
    )
    return pd.Series(
        np.where(u < fracs[0], "train", np.where(u < fracs[0] + fracs[1], "validation", "test")),
        index=df.index,
    )


class WarrantService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- lookups -------------------------------------------------------------------
    def _load(self, uow: Any, warrant_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        w = uow.repo("training_warrants").require(warrant_id)
        return w, uow.repo("namespaces").require(w["namespace_id"])

    def _model(
        self, uow: Any, model_ref: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        r = refs.parse(model_ref, "model")
        model, ns = catalog.find_object(uow, "models", "model", r)
        return model, ns, catalog.version_of(uow, "model_versions", "model_id", model, r.version)

    def uri(self, w: dict[str, Any], ns: dict[str, Any]) -> str:
        return f"maya://warrant/train/{ns['name']}/{w['name']}@v{w['version_no']}"

    def listing(self, uow: Any, p: Principal, *, q: str | None = None) -> Any:
        from maya.services.paging import Listing

        names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
        return Listing(
            "training_warrants",
            {"-created": "-created_at", "created": "created_at", "name": "name", "-name": "-name"},
            "-created",
            {},
            (["name"], q or ""),
            keep=self.p.access.reader(uow, p, "training_warrant"),
            enrich=lambda uow, w: {
                **w,
                "namespace": names.get(w["namespace_id"]),
                "status": self.status(w),
                "uri": f"maya://warrant/train/{names.get(w['namespace_id'])}/"
                f"{w['name']}@v{w['version_no']}",
            },
        )

    def list(self, p: Principal) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return self.listing(uow, p).collect(uow)

    def page(
        self,
        p: Principal,
        *,
        q: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        from maya.services.paging import run_page

        return run_page(
            self.p,
            lambda uow: self.listing(uow, p, q=q),
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            total=total,
        )

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
            return {
                **w,
                "namespace": ns["name"],
                "status": self.status(w),
                "uri": self.uri(w, ns),
                "model": {
                    "name": model["name"],
                    "version_no": mv["version_no"],
                    "ir_hash": mv["ir_hash"],
                    "artifact_hash": mv["artifact_hash"],
                    "opaque": bool(mv.get("opaque")),
                },
                "custody": uow.repo("custody_events").list(
                    warrant_type="train", warrant_id=warrant_id, order_by=["created_at"]
                ),
                "parameter_sets": uow.repo("parameter_sets").list(
                    training_warrant_id=warrant_id, order_by=["created_at"]
                ),
                "holdout_scores": uow.repo("holdout_scores").list(
                    training_warrant_id=warrant_id, order_by=["attempt_no"]
                ),
                "transitions": self.p.workflow.available(uow, self.subject(uow, w, ns)),
            }

    # -- creation --------------------------------------------------------------------
    def create(
        self,
        p: Principal,
        *,
        namespace: str,
        name: str,
        model: str,
        featureset: str,
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        spec = self._normalise_spec(spec)
        with self.p.uow() as uow:
            ns = self.p.access.namespace(uow, namespace)
            self.p.access.require(
                uow,
                p,
                "create",
                "training_warrant",
                {"id": "new", "namespace_id": ns["id"], "name": name},
            )
            mobj, mns, mv = self._model(uow, model)
            if mv["state"] not in catalog.APPROVED_STATES:
                raise NotApproved(
                    f"{model} is '{mv['state']}'; warrants are drawn on approved model versions"
                )
            model_uri = refs.version_ref("model", mns["name"], mobj["name"], mv["version_no"])
        given, featureset = featureset, self._fixed_ref(featureset)
        self.p.licences.derivation("featureset", [featureset], "training a model on it")
        res = self.p.featuresets.resolve_ref(p, featureset)
        report = self.validate_contract(mv, res.meta, spec)
        if not report["ok"]:
            raise ContractMismatch(
                "The feature set does not satisfy the model's input "
                "contract: " + "; ".join(report["problems"]),
                **report,
            )
        certificate = self.leakage_certificate(res, spec)
        with self.p.uow() as uow:
            ir = mv["formula_ir"] or {}
            if "composite" in ir:
                # each member is fitted separately, so each gets its own seed, derived from
                # the warrant's seed so the whole is still reproducible from one number
                aliases = sorted(self.p.models.member_irs(uow, ir))
                spec = {**spec, "member_seeds": comp.member_seeds(int(spec["seed"]), aliases)}
        fsp_id = self._fs_pin_id(featureset)
        with self.p.uow(p.username) as uow:
            prior = uow.repo("training_warrants").list(
                namespace_id=ns["id"], name=name, order_by=["-version_no"], limit=1
            )
            w = uow.repo("training_warrants").add(
                {
                    "namespace_id": ns["id"],
                    "name": name,
                    "version_no": prior[0]["version_no"] + 1 if prior else 1,
                    "state": "draft",
                    "owner_id": p.user_id,
                    "model_version_id": mv["id"],
                    "featureset_ref": featureset,
                    "feature_set_pin_id": fsp_id,
                    "spec": {**spec, "model_ref": model_uri},
                    "contract_report": report,
                    "leakage_certificate": certificate,
                    **self._escrowed_holdout(res, spec),
                    "backends": Backends.provenance(),
                    "expires_at": utcnow() + dt.timedelta(days=int(spec["expiry_days"])),
                }
            )
            self._custody(
                uow,
                w["id"],
                "created",
                p.username,
                detail={
                    "model": model_uri,
                    "featureset": featureset,
                    **({"featureset_as_given": given} if given != featureset else {}),
                },
            )
            me = self.uri(w, ns)
            uow.repo("lineage_edges").link(model_uri, me, "trained_on", "model")
            uow.repo("lineage_edges").link(featureset, me, "trained_on", "data")
            uow.audit(
                "warrant.created",
                object_type="training_warrant",
                object_ref=me,
                detail={"certificate": certificate["status"]},
            )
            return w

    def _normalise_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        out = {
            "split": {"train": 0.7, "validation": 0.15, "test": 0.15},
            "seed": 42,
            "shape": "tabular",
            "holdout": "escrowed",
            "expiry_days": 365,
            "leakage_lag_days": 1,
            "bindings": {},
            "target": None,
            "environment": {"python": "3.13"},
            "objective": "",
            "metrics": ["rmse"],
            "allow_non_causal": False,
            "non_causal_justification": "",
            "leakage_justification": "",
        }
        out.update({k: v for k, v in spec.items() if v is not None})
        if out["holdout"] not in ("escrowed", "none"):
            raise ValidationFailed("holdout must be 'escrowed' or 'none'")
        return out

    def _fixed_ref(self, featureset: str) -> str:
        """The reference a warrant keeps: what ``featureset`` means now, written so it
        cannot come to mean anything else — a bare name becomes the version it resolved
        to, a pin series without a date the date of the sealed pin it found. A warrant is
        drawn on data; "the latest" is not data."""
        r = refs.parse(featureset, "featureset")
        fs, ns, v, pin, _, _ = self.p.featuresets.load(featureset)
        if pin is not None:
            return str(
                refs.Ref(
                    "featureset", ns["name"], fs["name"], series=r.series, as_of=pin["as_of_date"]
                )
            )
        return refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"])

    def _fs_pin_id(self, featureset: str) -> str | None:
        r = refs.parse(featureset, "featureset")
        if not r.is_pin:
            return None
        _, _, _, pin, _, _ = self.p.featuresets.load(featureset)
        return pin["id"] if pin else None

    def validate_contract(
        self, mv: dict[str, Any], meta: dict[str, Any], spec: dict[str, Any]
    ) -> dict[str, Any]:
        """Check the model's input contract against the feature set, listing every miss."""
        attrs = {a["name"]: a.get("type", "") for a in meta["schema"]}
        problems, mapping = [], {}
        for inp in mv["input_contract"] or []:
            if inp.get("role", "feature") != "feature":
                continue
            src = spec["bindings"].get(inp["name"], inp["name"])
            if src not in attrs:
                problems.append(
                    f"input '{inp['name']}' needs attribute '{src}', which the "
                    "feature set does not expose"
                )
                continue
            if not str(attrs[src]).startswith(NUMERIC):
                problems.append(
                    f"input '{inp['name']}' is {inp.get('type', 'float64')} but "
                    f"'{src}' is {attrs[src]}"
                )
            mapping[inp["name"]] = src
        target = spec.get("target")
        if target and target not in attrs:
            problems.append(f"target '{target}' is not an attribute of the feature set")
        return {
            "ok": not problems,
            "problems": problems,
            "mapping": mapping,
            "checked_at": utcnow().isoformat(),
        }

    def leakage_certificate(self, res: Any, spec: dict[str, Any]) -> dict[str, Any]:
        """Prove no row uses a value MAYA could not have known by its event time (§29.1)."""
        df, index = res.df, res.meta["index"]
        lag = dt.timedelta(days=int(spec["leakage_lag_days"]))
        violations: list[dict[str, Any]] = []
        examined = len(df)
        if KT in df.columns and examined:
            event = (
                pd.to_datetime(df[index[0]]).dt.tz_localize("UTC")
                if pd.to_datetime(df[index[0]]).dt.tz is None
                else pd.to_datetime(df[index[0]])
            )
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
            exceptions.append(
                {
                    "rule": "non-causal fill",
                    "attributes": nc,
                    "justification": spec.get("non_causal_justification") or None,
                }
            )
        if n_bad:
            exceptions.append(
                {
                    "rule": f"knowledge time > event time + {lag.days}d",
                    "rows": n_bad,
                    "justification": spec.get("leakage_justification") or None,
                }
            )
        unjustified = [e for e in exceptions if not e["justification"]]
        if nc and not spec.get("allow_non_causal"):
            unjustified.append({"rule": "non-causal fill without allow_non_causal"})
        status = (
            "refused"
            if unjustified
            else ("certified_with_exceptions" if exceptions else "certified")
        )
        body = {
            "rule": f"every row's knowledge time ≤ its event date + {lag.days} day(s)",
            "rows_examined": examined,
            "violations": n_bad,
            "examples": violations,
            "exceptions": exceptions,
            "status": status,
            "issued_at": utcnow().isoformat(),
        }
        signer = self.p.signer_or_none()
        if signer is not None:
            body["signature"] = signer.signature_block(djson.canonical(body).encode())
        else:
            body["signature"] = None
            body["unsigned_reason"] = "crypto backend unavailable (Type C refusal)"
        return body

    # -- data, the checksum cycle -------------------------------------------------------
    def training_frame(
        self, w: dict[str, Any], *, include_test: bool, principal: Principal | None = None
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
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
        manifest = {
            "warrant": self.uri(w, ns),
            "rows": table.num_rows,
            "checksum": checksum,
            "escrowed_holdout": escrow,
            "split": w["spec"]["split"],
            "seed": w["spec"]["seed"],
            "index": meta["index"],
            "target": w["spec"].get("target"),
            "issued_at": utcnow().isoformat(),
            "issued_to": p.username,
        }
        with self.p.uow(p.username) as uow:
            self._custody(
                uow,
                warrant_id,
                "downloaded",
                p.username,
                checksum=checksum,
                detail={"rows": table.num_rows},
            )
            uow.audit(
                "warrant.data_downloaded",
                object_type="training_warrant",
                object_ref=self.uri(w, ns),
                detail={"checksum": checksum},
            )
        return {"data": buf.getvalue(), "manifest": manifest}

    def _live(self, w: dict[str, Any]) -> None:
        if w["revoked_at"]:
            raise NotApproved(f"Warrant revoked: {w['revoke_reason']}")
        if w["expires_at"] and w["expires_at"] < utcnow():
            raise WarrantExpired("The training warrant has expired; clone it to continue")

    # -- parameters ------------------------------------------------------------------
    def upload_parameters(
        self,
        p: Principal,
        warrant_id: str,
        *,
        values: dict[str, Any],
        metrics: dict[str, Any] | None = None,
        data_checksum: str | None = None,
        name: str | None = None,
        notes: str = "",
        member_alias: str | None = None,
    ) -> dict[str, Any]:
        with self.p.uow() as uow:
            w, ns = self._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
            self.p.access.require_capability(p, "parameter_set", "C")
            if w["sealed_at"]:
                raise NotApproved("The warrant is sealed; clone it to train again")
            self._live(w)
            mv = uow.repo("model_versions").require(w["model_version_id"])
            issued = {
                e["checksum"]
                for e in uow.repo("custody_events").list(
                    warrant_type="train", warrant_id=warrant_id, event="downloaded"
                )
            }
        problems = self.check_bounds(
            mv["formula_ir"] or {}, values, member_alias, self.declared_parameters(mv)
        )
        if problems:
            raise ValidationFailed(
                "Parameters out of bounds: " + "; ".join(problems), problems=problems
            )
        verified = bool(data_checksum) and data_checksum in issued
        with self.p.uow(p.username) as uow:
            ps = uow.repo("parameter_sets").add(
                {
                    "model_version_id": mv["id"],
                    "training_warrant_id": warrant_id,
                    "name": name or f"{w['name']}-params-{utcnow():%Y%m%d%H%M%S}",
                    "state": "draft",
                    "values": values,
                    "values_hash": djson.canonical_hash(values),
                    # The declaration, not the shape of the model: a declared black box
                    # names its parameters too, and a schema of [] made every later check
                    # on them vacuous.
                    "param_schema": irmod.parameter_inputs(mv["formula_ir"] or {}),
                    "metrics": metrics or {},
                    "data_checksum": data_checksum,
                    "verified_data": verified,
                    "member_alias": member_alias,
                    "notes": notes,
                }
            )
            self._custody(
                uow,
                warrant_id,
                "parameters_uploaded",
                p.username,
                checksum=data_checksum,
                detail={"parameter_set": ps["id"], "verified_data": verified},
            )
            uri = self.uri(w, ns)
            uow.repo("lineage_edges").link(uri, f"maya://parameters/{ps['id']}", "parameterized_by")
            uow.audit(
                "warrant.parameters_uploaded",
                object_type="training_warrant",
                object_ref=uri,
                detail={"verified_data": verified, "values_hash": ps["values_hash"]},
            )
            return {**ps, "flag": None if verified else "unverified_data"}

    def _escrowed_holdout(self, res: Any, spec: dict[str, Any]) -> dict[str, Any]:
        """The escrowed test partition, fixed at this moment: its content hash and row
        count. ``holdout: none`` escrows nothing, and neither does a warrant with no
        target to score against."""
        if spec.get("holdout") != "escrowed":
            return {}
        df = res.df.copy()
        df[SPLIT_COL] = assign_splits(df, res.meta["index"], spec["split"], spec["seed"])
        test = df[df[SPLIT_COL] == "test"].drop(columns=[SPLIT_COL]).reset_index(drop=True)
        table = pa.Table.from_pandas(test, preserve_index=False).replace_schema_metadata(None)
        return {"holdout_hash": table_checksum(table), "holdout_rows": table.num_rows}

    @staticmethod
    def declared_parameters(mv: dict[str, Any]) -> builtins.list[dict[str, Any]]:
        """The parameters a version declares, wherever they are written down.

        A formula's own are in its IR. A composite's are in its computed input contract: its
        stored IR carries ``inputs: []`` because the list is derived from its members and its
        combiner, so reading the IR alone finds nothing — which is how a composite came to seal
        with the numbers its combiner needs unapproved."""
        ir = mv.get("formula_ir") or {}
        if "composite" in ir:
            return [c for c in (mv.get("input_contract") or []) if c.get("role") == "parameter"]
        return irmod.parameter_inputs(ir)

    def outstanding_parameters(
        self, uow: Any, warrant_id: str, mv: dict[str, Any]
    ) -> builtins.list[str]:
        """What still has to be fitted and approved before this warrant can seal.

        A plain model needs one approved parameter set. A composite needs one **per
        trainable member**: its members are fitted separately, under their own aliases,
        and sealing on the first one approved would license the rest untrained. The names
        returned are what a reviewer sees.
        """
        ir = mv["formula_ir"] or {}
        sets = uow.repo("parameter_sets").list(
            training_warrant_id=warrant_id, state__in=builtins.list(catalog.APPROVED_STATES)
        )
        if "composite" in ir:
            members = self.p.models.member_irs(uow, ir)
            outstanding = []
            for alias, member_ir in sorted(members.items()):
                wanted = {i["name"] for i in irmod.parameter_inputs(member_ir or {})}
                if not wanted:
                    continue
                # a member is covered by a set fitted under its alias, or by a combined
                # set that carries every one of its parameters as `alias.name`
                if any(
                    ps["member_alias"] == alias
                    or wanted
                    <= {k.split(".", 1)[1] for k in ps["values"] if k.startswith(alias + ".")}
                    for ps in sets
                ):
                    continue
                outstanding.append(alias)
            # And the combiner's own. A composite can be more than a product of its members:
            # the weight in a blend, the threshold in a router, the horizon multiple in an
            # impairment model. Those are numbers somebody has to decide, they belong to no
            # member, and a composite that sealed without them would license an allowance whose
            # most argued-over figures nobody had approved.
            own = {i["name"] for i in self.declared_parameters(mv)}
            if own and not any(
                ps["member_alias"] is None and own <= set(ps["values"]) for ps in sets
            ):
                outstanding.append("the combiner's own parameters")
            return outstanding
        return ["this model's parameters"] if irmod.parameter_inputs(ir) and not sets else []

    @staticmethod
    def check_bounds(
        ir: dict[str, Any],
        values: dict[str, Any],
        alias: str | None = None,
        declared: builtins.list[dict[str, Any]] | None = None,
    ) -> builtins.list[str]:
        """Every parameter the model version declares is present and within its bounds (§8.4).

        This used to return immediately for any IR with no ``body``, which is every declared
        black box — so the gate that reads it passed a parameter set with a whole weight
        matrix missing. A black box's *mathematics* is unavailable; its declaration of what
        parameters it takes is not, and it is the only thing left to check them against."""
        if not (ir.get("body") or "composite" in ir or irmod.is_opaque(ir)):
            return []
        problems = []
        wanted = irmod.parameter_inputs(ir) if declared is None else declared
        if alias is not None and "composite" in ir:
            # A set uploaded under a member alias answers for that member, not for the
            # combiner's own parameters, which belong to no alias.
            wanted = []
        for inp in wanted:
            key = f"{alias}.{inp['name']}" if alias else inp["name"]
            if key not in values and inp["name"] not in values:
                problems.append(f"missing parameter '{key}'")
                continue
            v = values.get(key, values.get(inp["name"]))
            lo, hi = (inp.get("bounds") or [None, None])[:2]
            numeric = isinstance(v, (int, float)) and not isinstance(v, bool)
            if (lo is not None or hi is not None) and not numeric:
                # A declared scalar bound on a value that is not a scalar means one of the two
                # is wrong, and saying nothing let {"beta0": [9.0, -9.0]} pass a bound of
                # [0, 0.25]. A black box's weight matrix is legitimately an array — it simply
                # declares no bounds, and then nothing here applies to it.
                problems.append(
                    f"'{key}' declares bounds [{lo}, {hi}] but its value is "
                    f"{type(v).__name__}, so no bound could be applied"
                )
            elif numeric and ((lo is not None and v < lo) or (hi is not None and v > hi)):
                problems.append(f"'{key}'={v} outside [{lo}, {hi}]")
        for inp in irmod.constant_inputs(ir):
            key = f"{alias}.{inp['name']}" if alias else inp["name"]
            if "value" not in inp and key not in values and inp["name"] not in values:
                problems.append(f"missing constant '{key}' (the model declares no value for it)")
        return problems + WarrantService.check_constraints(ir, values, alias)

    @staticmethod
    def check_constraints(
        ir: dict[str, Any], values: dict[str, Any], alias: str | None = None
    ) -> builtins.list[str]:
        """The model's joint parameter constraints, evaluated on the values offered (§8.4).

        Bounds are per parameter and some conditions are not: a GARCH model is stationary only
        if ``alpha + beta < 1``, and each of the two can sit anywhere in [0, 1] while the pair
        forecast an infinite variance. A per-parameter check cannot see that, so a set which is
        individually plausible and jointly impossible used to be approved."""
        from maya.formula.evaluate import eval_node

        constraints = irmod.constraints_of(ir)
        if not constraints:
            return []
        supplied = {
            (k.split(".", 1)[1] if alias and k.startswith(alias + ".") else k): v
            for k, v in values.items()
        }
        for inp in irmod.parameter_inputs(ir):
            if inp["name"] not in supplied and "value" in inp:
                supplied[inp["name"]] = inp["value"]
        problems = []
        for c in constraints:
            wanted = irmod.params_of(c["expr"])
            if not wanted <= set(supplied):
                continue  # a missing parameter is already reported by the bounds check
            try:
                got = float(np.asarray(eval_node(c["expr"], {}, supplied)).reshape(-1)[0])
            except Exception as exc:  # noqa: BLE001 - an unevaluable constraint is a finding
                problems.append(f"constraint could not be evaluated: {type(exc).__name__}: {exc}")
                continue
            rhs, op = float(c["rhs"]), c["op"]
            ok = {
                "lt": got < rhs,
                "le": got <= rhs,
                "gt": got > rhs,
                "ge": got >= rhs,
            }[op]
            if not ok:
                terms = " + ".join(f"{n}={supplied[n]:g}" for n in sorted(wanted))
                problems.append(
                    f"constraint {irmod.CONSTRAINT_OPS[op]} {rhs:g} is violated: "
                    f"{terms} gives {got:g} — {c['why']}"
                )
        return problems

    def parameter_subject(self, uow: Any, ps: dict[str, Any]) -> Subject:
        w, ns = self._load(uow, ps["training_warrant_id"])
        owner = uow.repo("users").get(w["owner_id"])
        return Subject(
            "parameter_set",
            "parameter_sets",
            ps["id"],
            f"maya://parameters/{ps['id']}",
            "parameter_set",
            ps,
            ns,
            w["owner_id"],
            owner["username"] if owner else None,
            [],
            {"warrant": w},
        )

    def parameter_transition(
        self,
        p: Principal,
        ps_id: str,
        name: str,
        *,
        rationale: str | None = None,
        force: bool = False,
        justification: str | None = None,
    ) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            ps = uow.repo("parameter_sets").require(ps_id)
            if justification:
                ps = uow.repo("parameter_sets").update(
                    ps_id, {"unverified_justification": justification}
                )
            out = self.p.workflow.transition(
                uow, p, self.parameter_subject(uow, ps), name, rationale=rationale, force=force
            )
            return out.__dict__

    def score_holdout(
        self,
        p: Principal,
        warrant_id: str,
        *,
        parameter_set_id: str | None = None,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Blind scoring against the escrowed partition: metrics out, rows never (§29.4)."""
        _, metrics, attempt = self.holdout_errors(
            p, warrant_id, parameter_set_id=parameter_set_id, values=values
        )
        return {
            "metrics": metrics,
            "attempt": attempt,
            "note": "Every attempt is counted and shown on the warrant.",
        }

    def holdout(
        self,
        p: Principal,
        warrant_id: str,
        *,
        parameter_set_id: str | None = None,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """The escrowed holdout, checked against its seal, and a predictor over it.

        For MAYA's own use -- scoring, comparisons, evidence -- never returned to a caller:
        ``test`` holds the rows. ``predict(frame)`` returns ``(predictions, provenance)``,
        running a black box's artifact in the sandbox and anything else from its IR."""
        with self.p.uow() as uow:
            w, _ = self._load(uow, warrant_id)
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
        if w["holdout_hash"]:
            fresh = pa.Table.from_pandas(
                test.drop(columns=["_split"]).reset_index(drop=True), preserve_index=False
            ).replace_schema_metadata(None)
            if table_checksum(fresh) != w["holdout_hash"]:
                raise ValidationFailed(
                    "The escrowed holdout is not the one this warrant was drawn on: it now "
                    f"has {fresh.num_rows} rows hashing differently (escrowed: "
                    f"{w['holdout_rows']} rows). Scoring against data that moved would make "
                    "every earlier score incomparable; draw a new warrant.",
                    escrowed_rows=w["holdout_rows"],
                    found_rows=fresh.num_rows,
                )
        bindings = w["spec"].get("bindings", {})
        prm = values or {}

        def predict(frame: pd.DataFrame) -> tuple[np.ndarray, dict[str, Any]]:
            if irmod.is_opaque(mv["formula_ir"] or {}):
                return self._predict_blind(mv, frame, bindings, prm, target)
            return self.predict(mv, frame, bindings, prm), {}

        return {
            "warrant": w,
            "model_version": mv,
            "test": test.reset_index(drop=True),
            "target": target,
            "y": test[target].astype(float).to_numpy(),
            "bindings": bindings,
            "predict": predict,
        }

    def record_attempt(
        self,
        p: Principal,
        warrant_id: str,
        metrics: dict[str, Any],
        *,
        parameter_set_id: str | None = None,
        purpose: str | None = None,
    ) -> int:
        """Count one use of the holdout, on the warrant and in its custody chain."""
        with self.p.uow(p.username) as uow:
            w = uow.repo("training_warrants").require(warrant_id)
            w = uow.repo("training_warrants").update(
                warrant_id, {"holdout_attempts": w["holdout_attempts"] + 1}
            )
            uow.repo("holdout_scores").add(
                {
                    "training_warrant_id": warrant_id,
                    "parameter_set_id": parameter_set_id,
                    "attempt_no": w["holdout_attempts"],
                    "metrics": metrics,
                }
            )
            self._custody(
                uow,
                warrant_id,
                "holdout_scored",
                p.username,
                detail={
                    "attempt": w["holdout_attempts"],
                    **metrics,
                    **({"purpose": purpose} if purpose else {}),
                },
            )
            return int(w["holdout_attempts"])

    def holdout_errors(
        self,
        p: Principal,
        warrant_id: str,
        *,
        parameter_set_id: str | None = None,
        values: dict[str, Any] | None = None,
        purpose: str | None = None,
    ) -> tuple[np.ndarray, dict[str, Any], int]:
        """Score once and record the attempt; returns the per-row errors, in the escrowed
        holdout's row order, for comparisons MAYA makes itself (champion and challenger).
        The errors never leave the platform: callers outside it get metrics only."""
        h = self.holdout(p, warrant_id, parameter_set_id=parameter_set_id, values=values)
        pred, sandboxed = h["predict"](h["test"])
        err = pred - h["y"]
        metrics = {
            "rmse": float(np.sqrt(np.nanmean(err**2))),
            "mae": float(np.nanmean(np.abs(err))),
            "rows": int(len(h["test"])),
            **sandboxed,
        }
        attempt = self.record_attempt(
            p, warrant_id, metrics, parameter_set_id=parameter_set_id, purpose=purpose
        )
        return err, metrics, attempt

    def _predict_blind(
        self,
        mv: dict[str, Any],
        df: pd.DataFrame,
        bindings: dict[str, str],
        values: dict[str, Any],
        target: str,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Score a black box by running its validated artifact in the sandbox (§29.4).

        MAYA cannot evaluate a model it cannot read, but it can run one it has validated,
        and that is enough to keep the holdout blind: the artifact is given the input
        columns of the escrowed rows and nothing else -- never the target -- inside the
        sandbox, with no network and no view of storage. Its predictions come back to MAYA,
        which computes the metrics; the person who asked sees the metrics and never a row.
        What was run is recorded with the score: the artifact's hash and the sandbox tier."""
        from maya.security.sandbox import run_sandboxed

        report = mv.get("artifact_report") or {}
        if not mv.get("artifact_hash") or not report.get("passed"):
            raise ValidationFailed(
                "A black box is scored by running its code artifact in the sandbox, and this "
                "version has no artifact that passed the validation ladder. Upload one to the "
                "model and let it validate, then score.",
                artifact=report.get("status")
                or ("none" if not mv.get("artifact_hash") else "failed"),
            )
        wanted = [c["name"] for c in mv["input_contract"] or []]
        missing = [n for n in wanted if bindings.get(n, n) not in df.columns]
        if not wanted or missing:
            raise ValidationFailed(
                "The black box's input contract cannot be met from the holdout: "
                + (f"missing {missing}" if missing else "the version declares no inputs"),
                missing=missing,
            )
        if target in {bindings.get(n, n) for n in wanted}:
            raise ValidationFailed(
                f"The black box reads the target '{target}' as an input; scoring it would hand "
                "it the answer"
            )
        X = {n: df[bindings.get(n, n)].astype(float).tolist() for n in wanted}
        source = self.p.blobs.get(mv["artifact_hash"]).decode("utf-8")
        out = run_sandboxed(
            source,
            "Model",
            {"mode": "predict", "X": X, "params": values, "seed": 0},
            cpu_seconds=60,
            memory_mb=2048,
            wall_seconds=120,
            output_limit_bytes=max(2_000_000, 64 * len(df)),
        )
        if not out["ok"]:
            raise ValidationFailed(f"The black box failed in the sandbox: {out['error']}")
        result = out["result"]
        if isinstance(result, dict):
            result = next(iter(result.values()), None)
        pred = np.asarray(result, dtype=float).reshape(-1)
        if pred.shape[0] != len(df):
            raise ValidationFailed(
                f"The black box returned {pred.shape[0]} predictions for {len(df)} holdout rows"
            )
        return pred, {
            "scored_in": "sandbox",
            "sandbox_tier": out["tier"],
            "artifact_hash": mv["artifact_hash"],
        }

    def predict(
        self, mv: dict[str, Any], df: pd.DataFrame, bindings: dict[str, str], values: dict[str, Any]
    ) -> np.ndarray:
        ir = mv["formula_ir"] or {}
        if irmod.is_opaque(ir):
            raise ValidationFailed("A declared black box cannot be scored by MAYA")
        if "composite" in ir:
            with self.p.uow() as uow:
                members = self.p.models._member_irs(uow, ir)
            # The composite's own contract, not the union of its members': a combiner reads
            # features no member mentions (§8.7), and the version's contract already says so.
            # Building the inputs from the members alone left the combiner without them and
            # failed at evaluation for something the contract check had already passed.
            wanted = [c["name"] for c in mv["input_contract"] or []] or [
                c["name"] for m in members.values() for c in irmod.input_contract(m)
            ]
            inputs = {
                name: df[bindings.get(name, name)].astype(float).to_numpy()
                for name in dict.fromkeys(wanted)
                if bindings.get(name, name) in df.columns
            }
            out = evaluate_composite(ir, members, inputs, values)
        else:
            inputs = {
                c["name"]: df[bindings.get(c["name"], c["name"])].astype(float).to_numpy()
                for c in irmod.input_contract(ir)
            }
            out = evaluate(ir, inputs, values)
        return np.asarray(next(iter(out.values())), dtype=float)

    # -- workflow, sealing, custody -------------------------------------------------------
    def subject(self, uow: Any, w: dict[str, Any], ns: dict[str, Any]) -> Subject:
        owner = uow.repo("users").get(w["owner_id"])
        return Subject(
            "training_warrant",
            "training_warrants",
            w["id"],
            self.uri(w, ns),
            "training_warrant",
            w,
            ns,
            w["owner_id"],
            owner["username"] if owner else None,
            uow.repo("grants").list(object_type="training_warrant", object_id=w["id"]),
            {"warrant": w},
        )

    def transition(
        self,
        p: Principal,
        warrant_id: str,
        name: str,
        *,
        rationale: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            w, ns = self._load(uow, warrant_id)
            out = self.p.workflow.transition(
                uow, p, self.subject(uow, w, ns), name, rationale=rationale, force=force
            )
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
            outstanding = self.outstanding_parameters(uow, warrant_id, mv)
            if outstanding:
                raise NotApproved(
                    "A trainable model's warrant seals only with an approved parameter set; "
                    "still to fit: " + ", ".join(outstanding),
                    outstanding=outstanding,
                )
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
            row = uow.repo("training_warrants").update(
                warrant_id, {"revoked_at": utcnow(), "revoke_reason": reason}
            )
            for ew in uow.repo("execution_warrants").list(
                training_warrant_id=warrant_id, revoked_at__isnull=True
            ):
                uow.repo("execution_warrants").update(
                    ew["id"],
                    {
                        "revoked_at": utcnow(),
                        "revoke_reason": f"training warrant revoked: {reason}",
                    },
                )
                uow.repo("notifications").add(
                    {
                        "user_id": ew["owner_id"],
                        "kind": "revocation",
                        "message": f"Execution warrant {ew['name']} revoked: {reason}",
                        "object_ref": ew["id"],
                    }
                )
            self._custody(uow, warrant_id, "revoked", p.username, detail={"reason": reason})
            uow.audit(
                "warrant.revoked",
                object_type="training_warrant",
                object_ref=self.uri(w, ns),
                detail={"reason": reason},
            )
        # A composite that merely contains this model is a different instrument with its own
        # owner: it is told, not revoked. Told here rather than by the hourly sweep, because
        # "your model was withdrawn" an hour late is an hour of using it unknowingly.
        self.p.tracking.flag_composites_of(warrant_id, f"member warrant revoked: {reason}")
        return row

    def clone(
        self, p: Principal, warrant_id: str, changes: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """A new draft in the same family, linked to its origin (§9.3)."""
        with self.p.uow() as uow:
            w, ns = self._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
        spec = {**w["spec"], **(changes or {})}
        model_ref = spec.pop("model_ref")
        new = self.create(
            p,
            namespace=ns["name"],
            name=w["name"],
            model=model_ref,
            featureset=(changes or {}).get("featureset", w["featureset_ref"]),
            spec=spec,
        )
        with self.p.uow(p.username) as uow:
            return uow.repo("training_warrants").update(new["id"], {"clone_of": warrant_id})

    def _custody(
        self,
        uow: Any,
        warrant_id: str,
        event: str,
        actor: str,
        *,
        checksum: str | None = None,
        detail: dict[str, Any] | None = None,
        warrant_type: str = "train",
    ) -> None:
        uow.repo("custody_events").add(
            {
                "warrant_type": warrant_type,
                "warrant_id": warrant_id,
                "event": event,
                "actor": actor,
                "checksum": checksum,
                "detail": djson.loads(djson.dumps(detail or {})),
            }
        )

    # -- checks ---------------------------------------------------------------------------
    def check_contract(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        report = ctx["row"]["contract_report"] or {}
        return (
            bool(report.get("ok")),
            "contract satisfied"
            if report.get("ok")
            else "; ".join(report.get("problems", [])) or "not validated",
        )

    def check_leakage(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        cert = ctx["row"]["leakage_certificate"] or {}
        status = cert.get("status", "missing")
        return (
            status in ("certified", "certified_with_exceptions"),
            f"leakage certificate: {status}; {cert.get('violations', 0)} violating row(s)",
        )

    def check_bounds_ok(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        ps = ctx["row"]
        mv = uow.repo("model_versions").require(ps["model_version_id"])
        problems = self.check_bounds(
            mv["formula_ir"] or {}, ps["values"], ps["member_alias"], self.declared_parameters(mv)
        )
        return (not problems, "; ".join(problems) or "all parameters within declared bounds")

    def check_data_verified(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        ps = ctx["row"]
        if ps["verified_data"]:
            return True, "trained on data MAYA issued (checksum matched)"
        if ps["unverified_justification"]:
            return True, f"unverified_data overridden: {ps['unverified_justification']}"
        return False, (
            "unverified_data: the checksum does not match any download MAYA issued; "
            "approve only with an explicit justification"
        )
