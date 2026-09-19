"""
Model use cases (§8): formula, code artifact, parameters' schema, spec
document, composites, maturity, diff and conformance.

Nobody authors the formula IR by hand (§28.6): it is parsed from a formula
text (Python-ish or LaTeX-lite), lifted from a Python function, or uploaded
as JSON. A version's IR, artifact hash and input contract determine its
definition hash; the spec document versions with it and is re-marked for
review whenever the IR changes under it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from maya.core import djson
from maya.core.errors import ConflictError, NotApproved, NotFound, ValidationFailed
from maya.core.typeset import detect as typeset_detect
from maya.core.typeset import render_pdf
from maya.formula import composite as comp
from maya.formula import ir as irmod
from maya.formula.codegen import to_python
from maya.formula.conformance import conformance_test, sample_inputs
from maya.formula.diff import semantic_diff
from maya.formula.latex import to_latex
from maya.formula.parse import parse_model
from maya.formula.pylift import lift_python
from maya.formula.specdoc import default_document, expand_macros, section_completeness
from maya.persistence.types import utcnow
from maya.security.authz import Principal
from maya.services import catalog, refs
from maya.workflow.engine import Subject

EDITABLE = ("draft", "changes_requested")
KINDS = ("formula", "black_box", "composite", "vendor")
MATURITIES = ("experimental", "candidate", "approved", "restricted", "deprecated", "retired")


class ModelService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- read ---------------------------------------------------------------------
    def list(self, p: Principal, *, namespace: str | None = None, q: str | None = None
             ) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            filters: dict[str, Any] = {}
            if namespace:
                filters["namespace_id"] = self.p.access.namespace(uow, namespace)["id"]
            rows = uow.repo("models").list(order_by=["name"],
                                           search=(["name", "description"], q or ""), **filters)
            names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
            out = []
            for m in rows:
                if not self.p.access.allowed(uow, p, "read", "model", m):
                    continue
                latest = catalog.latest_version(uow, "model_versions", "model_id", m["id"])
                out.append({**m, "namespace": names.get(m["namespace_id"]),
                            "latest_version": latest["version_no"] if latest else None,
                            "latest_state": latest["state"] if latest else None,
                            "maturity": latest["maturity"] if latest else None,
                            "opaque": latest["opaque"] if latest else None,
                            "ref": refs.object_ref("model", names.get(m["namespace_id"], ""),
                                                   m["name"])})
            return out

    def get(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            versions = uow.repo("model_versions").list(model_id=model["id"],
                                                       order_by=["-version_no"])
            for v in versions:
                v["transitions"] = self.p.workflow.available(uow, self.subject(uow, model, ns, v))
                v["latex"] = self._latex(v["formula_ir"])
                v["completeness"] = section_completeness(v["spec_latex"] or "")
                v["parameter_sets"] = uow.repo("parameter_sets").list(
                    model_version_id=v["id"], order_by=["-created_at"])
            return {**model, "namespace": ns["name"], "versions": versions,
                    "ref": refs.object_ref("model", ns["name"], model["name"]),
                    "typeset": typeset_detect(),
                    "can_edit": self.p.access.allowed(uow, p, "update", "model", model)}

    @staticmethod
    def _latex(ir: dict[str, Any]) -> str:
        if not ir or "body" not in ir:
            return ""
        try:
            return to_latex(ir)
        except Exception:  # noqa: BLE001 - rendering is informational
            return ""

    # -- create and edit ------------------------------------------------------------
    def create(self, p: Principal, *, namespace: str, name: str, kind: str = "formula",
               description: str = "", formula: str | None = None,
               roles: dict[str, str] | None = None, ir: dict[str, Any] | None = None,
               python_source: str | None = None, vendor: dict[str, Any] | None = None
               ) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValidationFailed(f"kind must be one of {', '.join(KINDS)}")
        ir = self._build_ir(formula=formula, roles=roles, ir=ir, python_source=python_source)
        with self.p.uow(p.username) as uow:
            ns = self.p.access.namespace(uow, namespace)
            self.p.access.require(uow, p, "create", "model",
                                  {"id": "new", "namespace_id": ns["id"], "name": name})
            if uow.repo("models").find_one(namespace_id=ns["id"], name=name):
                raise ConflictError(f"Model '{namespace}/{name}' already exists")
            model = uow.repo("models").add({"namespace_id": ns["id"], "name": name,
                                            "owner_id": p.user_id, "kind": kind,
                                            "description": description, "vendor": vendor or {}})
            version = self._version_fields(ir or {}, name, p.username)
            uow.repo("model_versions").add({"model_id": model["id"], "version_no": 1,
                                            "state": "draft", **version})
            uow.audit("model.created", object_type="model",
                      object_ref=refs.object_ref("model", namespace, name), detail={"kind": kind})
            return model

    def _build_ir(self, *, formula: str | None = None, roles: dict[str, str] | None = None,
                  ir: dict[str, Any] | None = None, python_source: str | None = None
                  ) -> dict[str, Any] | None:
        if formula:
            return parse_model(formula, roles=roles or {})
        if python_source:
            return lift_python(python_source)
        return ir

    # -- spreadsheets (§29.9) ------------------------------------------------------------
    @staticmethod
    def lift_workbook(data: bytes, *, output: str | None = None,
                      roles: dict[str, str] | None = None,
                      filename: str = "workbook.xlsx") -> dict[str, Any]:
        """Preview: the IR a workbook lifts to, with its report. Nothing is stored."""
        from maya.formula.xlsx import lift_workbook
        return lift_workbook(data, output=output, roles=roles, filename=filename)

    def import_workbook(self, p: Principal, ref: str, data: bytes, *, output: str | None = None,
                        roles: dict[str, str] | None = None, filename: str = "workbook.xlsx",
                        expected_version: int | None = None) -> dict[str, Any]:
        """Lift a workbook into the model's editable draft and keep the workbook itself.

        The file is stored by hash (the IR records it), so the business keeps the workbook it
        recognises while MAYA governs the structured version."""
        ir = self.lift_workbook(data, output=output, roles=roles, filename=filename)
        ir["lifted_from"]["workbook"]["blob"] = self.p.blobs.put(data)
        row = self.update_draft(p, ref, ir=ir, expected_version=expected_version)
        with self.p.uow(p.username) as uow:
            uow.audit("model.workbook_imported", object_type="model", object_ref=ref,
                      detail={"filename": filename, "sha256": ir["lifted_from"]["workbook"]["sha256"],
                              "output": ir["lifted_from"]["workbook"]["output"],
                              "check": ir["lifted_from"]["workbook"]["check"]["status"]})
        return {**row, "workbook": ir["lifted_from"]["workbook"]}

    def workbook(self, p: Principal, ref: str, version_no: int) -> dict[str, Any]:
        """The original workbook a version was lifted from."""
        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        wb = ((v["formula_ir"] or {}).get("lifted_from") or {}).get("workbook")
        if not wb or not wb.get("blob"):
            raise NotFound(f"{ref} v{version_no} was not lifted from a workbook")
        return {"data": self.p.blobs.get(wb["blob"]), "filename": wb["filename"],
                "content_type": "application/vnd.openxmlformats-officedocument."
                                "spreadsheetml.sheet"}

    def _version_fields(self, ir: dict[str, Any], name: str, author: str,
                        spec: str | None = None) -> dict[str, Any]:
        contract = irmod.input_contract(ir) if ir and "body" in ir else []
        return {"formula_ir": ir, "input_contract": contract,
                "ir_hash": irmod.ir_hash(ir) if ir else None,
                "opaque": bool(ir) and irmod.is_opaque(ir),
                "spec_latex": spec if spec is not None else default_document(name, ir or {}, author),
                "spec_state": {"bound_ir_hash": irmod.ir_hash(ir) if ir else None}}

    def update_draft(self, p: Principal, ref: str, *, formula: str | None = None,
                     roles: dict[str, str] | None = None, ir: dict[str, Any] | None = None,
                     python_source: str | None = None, spec_latex: str | None = None,
                     maturity: str | None = None, expected_version: int | None = None
                     ) -> dict[str, Any]:
        new_ir = self._build_ir(formula=formula, roles=roles, ir=ir, python_source=python_source)
        with self.p.uow(p.username) as uow:
            model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "update", "model", model)
            draft = catalog.latest_version(uow, "model_versions", "model_id", model["id"])
            if draft["state"] not in EDITABLE:
                raise NotApproved("There is no editable draft; start a new draft first")
            changes: dict[str, Any] = {}
            if new_ir is not None:
                errors = irmod.validate_ir(new_ir) if "composite" not in new_ir else \
                    comp.validate_composite(new_ir["composite"])
                if errors:
                    raise ValidationFailed("The formula IR is not valid: " + "; ".join(errors),
                                           errors=errors)
                changes.update(formula_ir=new_ir, ir_hash=irmod.ir_hash(new_ir),
                               opaque=irmod.is_opaque(new_ir),
                               input_contract=self._contract(uow, new_ir))
                bound = (draft["spec_state"] or {}).get("bound_ir_hash")
                if bound and bound != changes["ir_hash"]:
                    changes["spec_state"] = {**(draft["spec_state"] or {}), "needs_review": True,
                                             "review_reason": "the formula IR changed under the "
                                                              "document"}
            if spec_latex is not None:
                state = dict(changes.get("spec_state") or draft["spec_state"] or {})
                state.update(bound_ir_hash=changes.get("ir_hash", draft["ir_hash"]),
                             needs_review=False, pdf_blob=None)
                changes.update(spec_latex=spec_latex, spec_state=state)
            if maturity is not None:
                changes["maturity"] = self._check_maturity(uow, draft, maturity, new_ir)
            row = uow.repo("model_versions").update(draft["id"], changes,
                                                    expected_version=expected_version)
            uow.audit("model.draft_updated", object_type="model", object_ref=ref,
                      detail={"fields": sorted(changes)})
            return row

    def _contract(self, uow: Any, ir: dict[str, Any]) -> list[dict[str, Any]]:
        if "composite" not in ir:
            return irmod.input_contract(ir) if "body" in ir else []
        members = self._member_irs(uow, ir)
        return comp.union_contract(members)

    def _member_irs(self, uow: Any, ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
        out = {}
        for m in ir["composite"]["members"]:
            r = refs.parse(m["ref"], "model")
            model, _ = catalog.find_object(uow, "models", "model", r)
            v = catalog.version_of(uow, "model_versions", "model_id", model, r.version)
            out[m["alias"]] = v["formula_ir"]
        return out

    def _member_maturities(self, uow: Any, ir: dict[str, Any]) -> dict[str, str]:
        out = {}
        for m in ir["composite"]["members"]:
            r = refs.parse(m["ref"], "model")
            model, _ = catalog.find_object(uow, "models", "model", r)
            out[m["alias"]] = catalog.version_of(uow, "model_versions", "model_id", model,
                                                 r.version)["maturity"]
        return out

    def _check_maturity(self, uow: Any, draft: dict[str, Any], maturity: str,
                        new_ir: dict[str, Any] | None) -> str:
        if maturity not in MATURITIES:
            raise ValidationFailed(f"maturity must be one of {', '.join(MATURITIES)}")
        ir = new_ir or draft["formula_ir"]
        if ir and "composite" in ir:
            cap = comp.capped_maturity(self._member_maturities(uow, ir))
            order = comp.MATURITY_ORDER
            if order.index(maturity) > order.index(cap):
                raise ValidationFailed(f"A composite's maturity is capped at its lowest member's "
                                       f"('{cap}'); cannot set '{maturity}'", cap=cap)
        return maturity

    def new_draft(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "update", "model", model)
            latest = catalog.latest_version(uow, "model_versions", "model_id", model["id"])
            if latest["state"] in EDITABLE:
                return latest
            keep = {k: latest[k] for k in ("formula_ir", "input_contract", "ir_hash",
                                           "artifact_hash", "artifact_report", "spec_latex",
                                           "spec_state", "opaque", "maturity")}
            return uow.repo("model_versions").add({"model_id": model["id"],
                                                   "version_no": latest["version_no"] + 1,
                                                   "state": "draft", **keep})

    # -- code artifact ------------------------------------------------------------------
    def upload_artifact(self, p: Principal, ref: str, source: str, *,
                        sample: dict[str, list[Any]] | None = None,
                        params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Store the artifact by hash and run the six-rung ladder as a job (§17.2)."""
        digest = self.p.blobs.put(source.encode("utf-8"))
        with self.p.uow(p.username) as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "update", "model", model, cap_type="artifact")
            draft = catalog.latest_version(uow, "model_versions", "model_id", model["id"])
            if draft["state"] not in EDITABLE:
                raise NotApproved("Artifacts attach to an editable draft")
            uow.repo("model_versions").update(draft["id"], {
                "artifact_hash": digest, "artifact_report": {"status": "validating"}})
            job = self.p.jobs.submit(uow, "model.validate_artifact",
                                     {"version_id": draft["id"], "blob": digest,
                                      "sample": sample or self._sample(draft),
                                      "params": params or self._default_params(draft)},
                                     owner=p.username)
            uow.audit("model.artifact_uploaded", object_type="model", object_ref=ref,
                      detail={"artifact_hash": digest})
            return {"artifact_hash": digest, "job": job}

    @staticmethod
    def _sample(version: dict[str, Any]) -> dict[str, list[Any]]:
        rng = np.random.default_rng(0)
        return {c["name"]: [float(x) for x in rng.uniform(0.5, 1.5, 8)]
                for c in version["input_contract"] or [{"name": "x"}]}

    @staticmethod
    def _default_params(version: dict[str, Any]) -> dict[str, Any]:
        """Values for everything a parameter set supplies: a constant's declared value, else
        the midpoint of the declared bounds (conformance only needs both sides to agree)."""
        out = {}
        for inp in irmod.supplied_inputs(version["formula_ir"] or {}) \
                if version["formula_ir"] and "body" in version["formula_ir"] else []:
            if "value" in inp:
                out[inp["name"]] = float(inp["value"])
                continue
            lo, hi = (inp.get("bounds") or [0.0, 1.0])[:2]
            out[inp["name"]] = (float(lo) + float(hi)) / 2
        return out

    def run_validation_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        from maya.formula.artifact import validate_artifact
        source = self.p.blobs.get(params["blob"]).decode("utf-8")
        ctx.progress(20, "running the validation ladder")
        report = validate_artifact(source, params["sample"], params["params"])
        with self.p.uow(ctx.actor) as uow:
            v = uow.repo("model_versions").require(params["version_id"])
            if v["artifact_hash"] == params["blob"]:
                uow.repo("model_versions").update(v["id"], {"artifact_report": report})
            uow.audit("model.artifact_validated", object_type="model_version",
                      object_ref=v["id"], detail={"passed": report["passed"],
                                                  "tier": report["tier"]})
        return {"passed": report["passed"], "tier": report["tier"]}

    # -- spec document -----------------------------------------------------------------
    def render_spec(self, p: Principal, ref: str, version_no: int) -> dict[str, Any]:
        with self.p.uow() as uow:
            model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        latex = expand_macros(v["spec_latex"] or "", v["formula_ir"] or {},
                              resolver=lambda uri: uri)
        pdf, meta = render_pdf(latex)
        digest = self.p.blobs.put(pdf)
        with self.p.uow(p.username) as uow:
            state = {**(v["spec_state"] or {}), "pdf_blob": digest,
                     "draft_render": meta["draft_render"], "backend": meta["backend"],
                     "rendered_at": utcnow().isoformat()}
            uow.repo("model_versions").update(v["id"], {"spec_state": state})
            uow.audit("model.spec_rendered", object_type="model", object_ref=ref,
                      detail={"draft_render": meta["draft_render"], "pdf": digest})
        return {"pdf_blob": digest, **meta}

    def spec_pdf(self, p: Principal, ref: str, version_no: int) -> bytes:
        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        digest = (v["spec_state"] or {}).get("pdf_blob")
        if not digest:
            digest = self.render_spec(p, ref, version_no)["pdf_blob"]
        return self.p.blobs.get(digest)

    # -- workflow ------------------------------------------------------------------------
    def subject(self, uow: Any, model: dict[str, Any], ns: dict[str, Any],
                v: dict[str, Any]) -> Subject:
        owner = uow.repo("users").get(model["owner_id"])
        return Subject("model_version", "model_versions", v["id"],
                       refs.version_ref("model", ns["name"], model["name"], v["version_no"]),
                       "model", v, ns, model["owner_id"], owner["username"] if owner else None,
                       uow.repo("grants").list(object_type="model", object_id=model["id"]),
                       {"model": model, "service": self})

    def transition(self, p: Principal, ref: str, version_no: int, name: str, *,
                   rationale: str | None = None, force: bool = False,
                   successor: str | None = None) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
            if name == "submit" and v["state"] in EDITABLE:
                self._freeze(uow, model, v)
                v = uow.repo("model_versions").require(v["id"])
            if name == "deprecate":
                if not (successor or rationale):
                    raise ValidationFailed("Deprecation names a successor or states that none "
                                           "exists (§8.6)")
                uow.repo("model_versions").update(v["id"], {"successor_ref": successor})
            out = self.p.workflow.transition(uow, p, self.subject(uow, model, ns, v), name,
                                             rationale=rationale, force=force)
            if out.moved:
                self._after_move(uow, model, ns, v, out.state)
            return out.__dict__

    def _after_move(self, uow: Any, model: dict[str, Any], ns: dict[str, Any],
                    v: dict[str, Any], state: str) -> None:
        uow.repo("models").update(model["id"], {"status": state})
        if state == "approved" and v["maturity"] == "experimental":
            uow.repo("model_versions").update(v["id"], {"maturity": "candidate"})
        me = refs.version_ref("model", ns["name"], model["name"], v["version_no"])
        if state == "approved" and v["formula_ir"] and "composite" in v["formula_ir"]:
            for m in v["formula_ir"]["composite"]["members"]:
                uow.repo("lineage_edges").link(m["ref"], me, "composite_member", m["alias"])
        if state == "deprecated":
            self._warn_dependents(uow, v["id"], me)

    def _warn_dependents(self, uow: Any, version_id: str, me: str) -> None:
        """Deprecation warns every owner of a warrant that depends on the version (§8.6)."""
        owners = {w["owner_id"] for tbl in ("training_warrants", "execution_warrants")
                  for w in uow.repo(tbl).list(model_version_id=version_id)}
        for owner in owners:
            uow.repo("notifications").add({"user_id": owner, "kind": "deprecation",
                                           "message": f"{me} was deprecated; a warrant you own "
                                                      "depends on it", "object_ref": me})

    def _freeze(self, uow: Any, model: dict[str, Any], v: dict[str, Any]) -> None:
        body = {"ir": irmod.ir_hash(v["formula_ir"]) if v["formula_ir"] else None,
                "artifact": v["artifact_hash"], "contract": v["input_contract"]}
        uow.repo("model_versions").update(v["id"], {"definition_hash": djson.canonical_hash(body)})

    # -- workflow checks ----------------------------------------------------------------
    def check_formula(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        ir = ctx["row"]["formula_ir"] or {}
        if not ir:
            return False, "the model has no formula IR (declare a black box if it has none)"
        if "composite" in ir:
            errors = comp.validate_composite(ir["composite"])
        else:
            errors = irmod.validate_ir(ir)
        check = ((ir.get("lifted_from") or {}).get("workbook") or {}).get("check") or {}
        if check.get("status") == "disagreed":
            errors.append("the lifted formula disagrees with the workbook's own results: "
                          + check["statement"])
        return (not errors, "; ".join(errors) or "IR validates and typechecks")

    def check_spec(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        rows = section_completeness(ctx["row"]["spec_latex"] or "")
        empty = [r["section"] for r in rows if not r["present"] or r["empty"]]
        if (ctx["row"]["spec_state"] or {}).get("needs_review"):
            empty.append("(document marked for re-review after an IR change — save it)")
        return (not empty, "required sections empty: " + ", ".join(empty) if empty
                else "all required sections present")

    def check_artifact(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        row = ctx["row"]
        if not row["artifact_hash"]:
            return True, "no code artifact attached (formula-only model)"
        report = row["artifact_report"] or {}
        if report.get("status") == "validating":
            return False, "artifact validation is still running"
        return (bool(report.get("passed")),
                f"validated under sandbox tier '{report.get('tier')}'" if report.get("passed")
                else "artifact failed validation: " + "; ".join(
                    r["detail"] for r in report.get("rungs", []) if r["passed"] is False))

    def check_true_build(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        require = self.p.settings.bool("typeset.require_true_build", False) \
            or self.p.settings.environment != "dev"
        state = ctx["row"]["spec_state"] or {}
        if not state.get("pdf_blob"):
            return (not require, "no PDF rendered yet" + ("" if require else
                                                          " (not required in dev)"))
        if state.get("draft_render"):
            return (not require, "the PDF is a DRAFT render (no Tectonic)" +
                    ("; a model cannot be approved on a draft render" if require
                     else " — accepted in dev only because typeset.require_true_build is false"))
        return True, "PDF is a true LaTeX build"

    def check_members(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        ir = ctx["row"]["formula_ir"] or {}
        if "composite" not in ir:
            return True, "not a composite"
        maturities = self._member_maturities(uow, ir)
        blocking = comp.blocking_members(maturities, "approved")
        low = [a for a, m in maturities.items() if m == "experimental"]
        return (not low, "members still experimental: " + ", ".join(low) if low
                else f"member maturities {maturities}; blocking: {blocking or 'none'}")

    # -- analysis -------------------------------------------------------------------------
    def diff(self, p: Principal, ref: str, v1: int, v2: int) -> dict[str, Any]:
        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            a = catalog.version_of(uow, "model_versions", "model_id", model, v1)
            b = catalog.version_of(uow, "model_versions", "model_id", model, v2)
        return {"statements": semantic_diff(a["formula_ir"] or {}, b["formula_ir"] or {}),
                "old_latex": self._latex(a["formula_ir"]), "new_latex": self._latex(b["formula_ir"]),
                "artifact_changed": a["artifact_hash"] != b["artifact_hash"],
                "spec_changed": a["spec_latex"] != b["spec_latex"]}

    def reference_code(self, p: Principal, ref: str, version_no: int) -> str:
        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        return to_python(v["formula_ir"])

    def conformance(self, p: Principal, ref: str, version_no: int, *, n: int = 2000,
                    params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Differential test of the uploaded Python against the documented IR (§29.7)."""
        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        if not v["artifact_hash"]:
            raise ValidationFailed("No code artifact to test against the specification")
        if irmod.is_opaque(v["formula_ir"] or {}):
            return {"skipped": True, "statement": "declared black box: nothing to compare"}
        from maya.security.sandbox import run_sandboxed
        source = self.p.blobs.get(v["artifact_hash"]).decode("utf-8")
        params = params or self._default_params(v)
        rng = np.random.default_rng(7)
        cols = {c["name"]: rng.uniform(0.5, 1.5, 256) for c in v["input_contract"]}
        samples = sample_inputs(v["formula_ir"], cols, n=n, seed=7)

        def predict(x: dict[str, Any], prm: dict[str, Any]) -> Any:
            out = run_sandboxed(source, "Model", {"mode": "predict", "X": {k: np.asarray(val)
                                .tolist() for k, val in x.items()}, "params": prm, "seed": 0},
                                wall_seconds=60)
            if not out["ok"]:
                raise ValidationFailed(f"artifact failed in the sandbox: {out['error']}")
            return out["result"]
        return conformance_test(v["formula_ir"], predict, samples, params)
