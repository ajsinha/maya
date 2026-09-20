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

import builtins
from typing import Any

import numpy as np

from maya.core import djson
from maya.core.errors import ConflictError, NotApproved, NotFound, ValidationFailed
from maya.core.typeset import detect as typeset_detect
from maya.formula import composite as comp
from maya.formula import ir as irmod
from maya.formula.codegen import to_python
from maya.formula.conformance import conformance_test, sample_inputs
from maya.formula.diff import semantic_diff
from maya.formula.latex import to_latex
from maya.formula.parse import parse_model
from maya.formula.pylift import lift_python
from maya.formula.specdoc import default_document, expand_macros, section_completeness
from maya.core.clock import utcnow
from maya.security.authz import Principal
from maya.services import catalog, refs, typesetting
from maya.workflow.engine import Subject

EDITABLE = ("draft", "changes_requested")
KINDS = ("formula", "black_box", "composite", "vendor")
MATURITIES = ("experimental", "candidate", "approved", "restricted", "deprecated", "retired")


class ModelService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- read ---------------------------------------------------------------------
    def listing(
        self, uow: Any, p: Principal, *, namespace: str | None = None, q: str | None = None
    ) -> Any:
        from maya.services.paging import Listing

        filters: dict[str, Any] = {}
        if namespace:
            filters["namespace_id"] = self.p.access.namespace(uow, namespace)["id"]
        names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}

        def enrich_many(uow: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            latest = uow.repo("model_versions").latest_per("model_id", [m["id"] for m in rows])
            out = []
            for m in rows:
                v = latest.get(m["id"])
                out.append(
                    {
                        **m,
                        "namespace": names.get(m["namespace_id"]),
                        "latest_version": v["version_no"] if v else None,
                        "latest_state": v["state"] if v else None,
                        "maturity": v["maturity"] if v else None,
                        "opaque": v["opaque"] if v else None,
                        "ref": refs.object_ref(
                            "model", names.get(m["namespace_id"], ""), m["name"]
                        ),
                    }
                )
            return out

        return Listing(
            "models",
            {
                "name": "name",
                "-name": "-name",
                "updated": "updated_at",
                "-updated": "-updated_at",
                "created": "created_at",
                "-created": "-created_at",
            },
            "name",
            filters,
            (["name", "description"], q or ""),
            keep=self.p.access.reader(uow, p, "model"),
            enrich_many=enrich_many,
        )

    def list(
        self, p: Principal, *, namespace: str | None = None, q: str | None = None
    ) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return self.listing(uow, p, namespace=namespace, q=q).collect(uow)

    def page(
        self,
        p: Principal,
        *,
        namespace: str | None = None,
        q: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        from maya.services.paging import run_page

        return run_page(
            self.p,
            lambda uow: self.listing(uow, p, namespace=namespace, q=q),
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            total=total,
        )

    def get(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            versions = uow.repo("model_versions").list(
                model_id=model["id"], order_by=["-version_no"]
            )
            for v in versions:
                v["transitions"] = self.p.workflow.available(uow, self.subject(uow, model, ns, v))
                v["latex"] = self._latex(v["formula_ir"])
                v["completeness"] = section_completeness(v["spec_latex"] or "")
                v["parameter_sets"] = uow.repo("parameter_sets").list(
                    model_version_id=v["id"], order_by=["-created_at"]
                )
            return {
                **model,
                "namespace": ns["name"],
                "versions": versions,
                "ref": refs.object_ref("model", ns["name"], model["name"]),
                "typeset": typeset_detect(),
                "can_edit": self.p.access.allowed(uow, p, "update", "model", model),
            }

    @staticmethod
    def _latex(ir: dict[str, Any]) -> str:
        if not ir or "body" not in ir:
            return ""
        try:
            return to_latex(ir)
        except Exception:  # noqa: BLE001 - rendering is informational
            return ""

    # -- create and edit ------------------------------------------------------------
    def create(
        self,
        p: Principal,
        *,
        namespace: str,
        name: str,
        kind: str = "formula",
        description: str = "",
        formula: str | None = None,
        roles: dict[str, str] | None = None,
        ir: dict[str, Any] | None = None,
        python_source: str | None = None,
        vendor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValidationFailed(f"kind must be one of {', '.join(KINDS)}")
        ir = self._build_ir(formula=formula, roles=roles, ir=ir, python_source=python_source)
        with self.p.uow(p.username) as uow:
            ns = self.p.access.namespace(uow, namespace)
            self.p.access.require(
                uow, p, "create", "model", {"id": "new", "namespace_id": ns["id"], "name": name}
            )
            if uow.repo("models").find_one(namespace_id=ns["id"], name=name):
                raise ConflictError(f"Model '{namespace}/{name}' already exists")
            model = uow.repo("models").add(
                {
                    "namespace_id": ns["id"],
                    "name": name,
                    "owner_id": p.user_id,
                    "kind": kind,
                    "description": description,
                    "vendor": vendor or {},
                }
            )
            version = self._version_fields(ir or {}, name, p.username)
            uow.repo("model_versions").add(
                {"model_id": model["id"], "version_no": 1, "state": "draft", **version}
            )
            uow.audit(
                "model.created",
                object_type="model",
                object_ref=refs.object_ref("model", namespace, name),
                detail={"kind": kind},
            )
            return model

    def _build_ir(
        self,
        *,
        formula: str | None = None,
        roles: dict[str, str] | None = None,
        ir: dict[str, Any] | None = None,
        python_source: str | None = None,
    ) -> dict[str, Any] | None:
        if formula:
            return parse_model(formula, roles=roles or {})
        if python_source:
            return lift_python(python_source)
        return ir

    # -- spreadsheets (§29.9) ------------------------------------------------------------
    @staticmethod
    def lift_workbook(
        data: bytes,
        *,
        output: str | None = None,
        roles: dict[str, str] | None = None,
        filename: str = "workbook.xlsx",
    ) -> dict[str, Any]:
        """Preview: the IR a workbook lifts to, with its report. Nothing is stored."""
        from maya.formula.xlsx import lift_workbook

        return lift_workbook(data, output=output, roles=roles, filename=filename)

    def import_workbook(
        self,
        p: Principal,
        ref: str,
        data: bytes,
        *,
        output: str | None = None,
        roles: dict[str, str] | None = None,
        filename: str = "workbook.xlsx",
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """Lift a workbook into the model's editable draft and keep the workbook itself.

        The file is stored by hash (the IR records it), so the business keeps the workbook it
        recognises while MAYA governs the structured version."""
        ir = self.lift_workbook(data, output=output, roles=roles, filename=filename)
        ir["lifted_from"]["workbook"]["blob"] = self.p.blobs.put(data)
        row = self.update_draft(p, ref, ir=ir, expected_version=expected_version)
        with self.p.uow(p.username) as uow:
            uow.audit(
                "model.workbook_imported",
                object_type="model",
                object_ref=ref,
                detail={
                    "filename": filename,
                    "sha256": ir["lifted_from"]["workbook"]["sha256"],
                    "output": ir["lifted_from"]["workbook"]["output"],
                    "check": ir["lifted_from"]["workbook"]["check"]["status"],
                },
            )
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
        return {
            "data": self.p.blobs.get(wb["blob"]),
            "filename": wb["filename"],
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

    def _version_fields(
        self, ir: dict[str, Any], name: str, author: str, spec: str | None = None
    ) -> dict[str, Any]:
        # a declared black box (a vendor model, §29.10) still declares its inputs
        contract = irmod.input_contract(ir) if ir and ("body" in ir or irmod.is_opaque(ir)) else []
        return {
            "formula_ir": ir,
            "input_contract": contract,
            "ir_hash": irmod.ir_hash(ir) if ir else None,
            "opaque": bool(ir) and irmod.is_opaque(ir),
            "spec_latex": spec if spec is not None else default_document(name, ir or {}, author),
            "spec_state": {"bound_ir_hash": irmod.ir_hash(ir) if ir else None},
        }

    def update_draft(
        self,
        p: Principal,
        ref: str,
        *,
        formula: str | None = None,
        roles: dict[str, str] | None = None,
        ir: dict[str, Any] | None = None,
        python_source: str | None = None,
        spec_latex: str | None = None,
        maturity: str | None = None,
        shadow_materiality: float | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        new_ir = self._build_ir(formula=formula, roles=roles, ir=ir, python_source=python_source)
        with self.p.uow(p.username) as uow:
            model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "update", "model", model)
            draft = catalog.require_latest(uow, "model_versions", "model_id", model["id"])
            if draft["state"] not in EDITABLE:
                raise NotApproved("There is no editable draft; start a new draft first")
            changes: dict[str, Any] = {}
            if new_ir is not None:
                errors = (
                    irmod.validate_ir(new_ir)
                    if "composite" not in new_ir
                    else comp.validate_composite(new_ir["composite"])
                )
                if errors:
                    raise ValidationFailed(
                        "The formula IR is not valid: " + "; ".join(errors), errors=errors
                    )
                if "composite" in new_ir:
                    # cycles and over-deep nesting, refused while it is still a draft, and
                    # read access to every member: a composite makes its members' shape and
                    # behaviour visible to whoever holds it (§8.7)
                    root = f"{ns['name']}/{model['name']}"
                    comp.check_structure(self.member_graph(uow, new_ir, root), root)
                    self._require_member_reads(uow, p, new_ir)
                changes.update(
                    formula_ir=new_ir,
                    ir_hash=irmod.ir_hash(new_ir),
                    opaque=irmod.is_opaque(new_ir),
                    input_contract=self._contract(uow, new_ir),
                )
                bound = (draft["spec_state"] or {}).get("bound_ir_hash")
                if bound and bound != changes["ir_hash"]:
                    changes["spec_state"] = {
                        **(draft["spec_state"] or {}),
                        "needs_review": True,
                        "review_reason": "the formula IR changed under the document",
                    }
            if spec_latex is not None:
                state = dict(changes.get("spec_state") or draft["spec_state"] or {})
                state.update(
                    bound_ir_hash=changes.get("ir_hash", draft["ir_hash"]),
                    needs_review=False,
                    pdf_blob=None,
                )
                changes.update(spec_latex=spec_latex, spec_state=state)
            if maturity is not None:
                changes["maturity"] = self._check_maturity(uow, draft, maturity, new_ir)
            if shadow_materiality is not None:
                # §29.2: the shift in this model's output that its owner calls material. Only
                # the model knows its units, so it is declared with the version rather than
                # taken from the namespace; a change to it needs a draft like any other claim
                # the version makes.
                if float(shadow_materiality) <= 0:
                    raise ValidationFailed(
                        "shadow_materiality is the shift in this model's output that counts "
                        "as material; it is above zero"
                    )
                changes["shadow_materiality"] = float(shadow_materiality)
            row = uow.repo("model_versions").update(
                draft["id"], changes, expected_version=expected_version
            )
            uow.audit(
                "model.draft_updated",
                object_type="model",
                object_ref=ref,
                detail={"fields": sorted(changes)},
            )
            return row

    def _contract(self, uow: Any, ir: dict[str, Any]) -> builtins.list[dict[str, Any]]:
        if "composite" not in ir:
            return irmod.input_contract(ir) if "body" in ir or irmod.is_opaque(ir) else []
        members = self._member_irs(uow, ir)
        return comp.union_contract(members, combine=ir["composite"].get("combine"))

    def _require_member_reads(self, uow: Any, p: Principal, ir: dict[str, Any]) -> None:
        """A composite exposes its members: whoever writes one must be able to read each.
        Without this, a composite is a way to use — and, through its contract and its
        diagnostics, to learn about — a model you were never granted (§8.7, §11)."""
        for m in ir["composite"]["members"]:
            r = refs.parse(m["ref"], "model")
            member, _ = catalog.find_object(uow, "models", "model", r)
            self.p.access.require(uow, p, "read", "model", member)

    def member_irs(self, uow: Any, ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Each composite member's IR by alias (public: warrants ask what must be fitted)."""
        return self._member_irs(uow, ir)

    def member_graph(
        self, uow: Any, ir: dict[str, Any], root: str = ""
    ) -> dict[str, builtins.list[str]]:
        """``{node: [children]}`` over a composite and the composites inside it, so cycles
        and nesting depth can be seen (§8.7). A node is a model — ``namespace/name``, not a
        reference — so a composite that names an older version of itself is still a cycle.
        """
        graph: dict[str, builtins.list[str]] = {}

        def node_of(ref: str) -> tuple[str, dict[str, Any] | None]:
            r = refs.parse(ref, "model")
            model, ns = catalog.find_object(uow, "models", "model", r)
            version = catalog.version_of(uow, "model_versions", "model_id", model, r.version)
            return f"{ns['name']}/{model['name']}", version["formula_ir"]

        def walk(name: str, node_ir: dict[str, Any] | None) -> None:
            if name in graph:
                return
            if not node_ir or "composite" not in node_ir:
                graph[name] = []
                return
            children = []
            for member in node_ir["composite"]["members"]:
                child, child_ir = node_of(member["ref"])
                children.append(child)
                graph[name] = children  # recorded before recursing, so a loop is visible
                walk(child, child_ir)
            graph[name] = children

        walk(root or "(this model)", ir)
        return graph

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
            out[m["alias"]] = catalog.version_of(
                uow, "model_versions", "model_id", model, r.version
            )["maturity"]
        return out

    def _check_maturity(
        self, uow: Any, draft: dict[str, Any], maturity: str, new_ir: dict[str, Any] | None
    ) -> str:
        if maturity not in MATURITIES:
            raise ValidationFailed(f"maturity must be one of {', '.join(MATURITIES)}")
        ir = new_ir or draft["formula_ir"]
        if ir and "composite" in ir:
            cap = comp.capped_maturity(self._member_maturities(uow, ir))
            order = comp.MATURITY_ORDER
            if order.index(maturity) > order.index(cap):
                raise ValidationFailed(
                    f"A composite's maturity is capped at its lowest member's "
                    f"('{cap}'); cannot set '{maturity}'",
                    cap=cap,
                )
        return maturity

    def new_draft(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "update", "model", model)
            latest = catalog.require_latest(uow, "model_versions", "model_id", model["id"])
            if latest["state"] in EDITABLE:
                return latest
            keep = {
                k: latest[k]
                for k in (
                    "formula_ir",
                    "input_contract",
                    "ir_hash",
                    "artifact_hash",
                    "artifact_report",
                    "spec_latex",
                    "spec_state",
                    "opaque",
                    "maturity",
                    "shadow_materiality",
                )
            }
            return uow.repo("model_versions").add(
                {
                    "model_id": model["id"],
                    "version_no": latest["version_no"] + 1,
                    "state": "draft",
                    **keep,
                }
            )

    # -- code artifact ------------------------------------------------------------------
    def upload_artifact(
        self,
        p: Principal,
        ref: str,
        source: str,
        *,
        sample: dict[str, builtins.list[Any]] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store the artifact by hash and run the six-rung ladder as a job (§17.2)."""
        digest = self.p.blobs.put(source.encode("utf-8"))
        with self.p.uow(p.username) as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "update", "model", model, cap_type="artifact")
            draft = catalog.require_latest(uow, "model_versions", "model_id", model["id"])
            if draft["state"] not in EDITABLE:
                raise NotApproved("Artifacts attach to an editable draft")
            uow.repo("model_versions").update(
                draft["id"], {"artifact_hash": digest, "artifact_report": {"status": "validating"}}
            )
            job = self.p.jobs.submit(
                uow,
                "model.validate_artifact",
                {
                    "version_id": draft["id"],
                    "blob": digest,
                    "sample": sample or self._sample(draft),
                    "params": params or self._default_params(draft),
                },
                owner=p.username,
            )
            uow.audit(
                "model.artifact_uploaded",
                object_type="model",
                object_ref=ref,
                detail={"artifact_hash": digest},
            )
            return {"artifact_hash": digest, "job": job}

    @staticmethod
    def _sample(version: dict[str, Any]) -> dict[str, builtins.list[Any]]:
        rng = np.random.default_rng(0)
        return {
            c["name"]: [float(x) for x in rng.uniform(0.5, 1.5, 8)]
            for c in version["input_contract"] or [{"name": "x"}]
        }

    @staticmethod
    def _default_params(version: dict[str, Any]) -> dict[str, Any]:
        """Values for everything a parameter set supplies: a constant's declared value, else
        the midpoint of the declared bounds (conformance only needs both sides to agree)."""
        out = {}
        for inp in (
            irmod.supplied_inputs(version["formula_ir"] or {})
            if version["formula_ir"] and "body" in version["formula_ir"]
            else []
        ):
            if "value" in inp:
                out[inp["name"]] = float(inp["value"])
                continue
            lo, hi = (inp.get("bounds") or [0.0, 1.0])[:2]
            out[inp["name"]] = (float(lo) + float(hi)) / 2
        return out

    def run_validation_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        """The ladder, and then the differential test against the documented mathematics.

        The two belong together. The ladder asks whether the artifact parses, imports
        nothing forbidden and runs; the differential test asks whether it *computes the
        model*, which is a different question and the one the commonest implementation bugs
        fail. Leaving the second to be asked by hand made it a button rather than a check,
        so it runs here, on upload, and its result is recorded against the artifact hash it
        tested (§29.7)."""
        from maya.formula.artifact import validate_artifact

        source = self.p.blobs.get(params["blob"]).decode("utf-8")
        ctx.progress(20, "running the validation ladder")
        report = validate_artifact(source, params["sample"], params["params"])
        with self.p.uow(ctx.actor) as uow:
            v = uow.repo("model_versions").require(params["version_id"])
            if report["passed"] and not irmod.is_opaque(v["formula_ir"] or {}):
                ctx.progress(70, "comparing the code with the documented mathematics")
                report["conformance"] = self._differential(v, source, params["params"], ctx.actor)
            if v["artifact_hash"] == params["blob"]:
                uow.repo("model_versions").update(v["id"], {"artifact_report": report})
            uow.audit(
                "model.artifact_validated",
                object_type="model_version",
                object_ref=v["id"],
                detail={"passed": report["passed"], "tier": report["tier"]},
            )
        return {"passed": report["passed"], "tier": report["tier"]}

    def _differential(
        self, v: dict[str, Any], source: str, params: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        """Compare the artifact with the IR at upload time, over the default domain.

        A failure to run is recorded as a failure to agree, not as silence: if MAYA could
        not compare the two it must not imply that it did. Re-running it against a real
        feature set is ``conformance()``, and that result replaces this one."""
        cols, domain = self._conformance_domain(None, v, None)
        try:
            result = self._compare(v, source, params, n=2000, cols=cols, domain=domain)
        except Exception as exc:  # noqa: BLE001 - an unrunnable comparison is a finding
            result = {
                "agreed": 0,
                "total": 0,
                "counterexamples": [],
                "domain": "not compared",
                "statement": f"the comparison could not be run: {type(exc).__name__}: {exc}",
            }
        return self._conformance_record(v, result, actor)

    # -- spec document -----------------------------------------------------------------
    def render_spec(self, p: Principal, ref: str, version_no: int) -> dict[str, Any]:
        with self.p.uow() as uow:
            model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        latex = expand_macros(
            v["spec_latex"] or "", v["formula_ir"] or {}, resolver=lambda uri: uri
        )
        pdf, meta = typesetting.render(self.p.settings, latex)
        digest = self.p.blobs.put(pdf)
        with self.p.uow(p.username) as uow:
            state = {
                **(v["spec_state"] or {}),
                "pdf_blob": digest,
                "draft_render": meta["draft_render"],
                "backend": meta["backend"],
                # What the build was allowed to do (§17.1). A reviewer reading a sealed
                # version a year from now can see the caps and the network mode this PDF
                # was produced under, rather than today's configuration.
                "caps": meta.get("caps"),
                "rendered_at": utcnow().isoformat(),
            }
            uow.repo("model_versions").update(v["id"], {"spec_state": state})
            uow.audit(
                "model.spec_rendered",
                object_type="model",
                object_ref=ref,
                detail={"draft_render": meta["draft_render"], "pdf": digest},
            )
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
    def subject(
        self, uow: Any, model: dict[str, Any], ns: dict[str, Any], v: dict[str, Any]
    ) -> Subject:
        owner = uow.repo("users").get(model["owner_id"])
        return Subject(
            "model_version",
            "model_versions",
            v["id"],
            refs.version_ref("model", ns["name"], model["name"], v["version_no"]),
            "model",
            v,
            ns,
            model["owner_id"],
            owner["username"] if owner else None,
            uow.repo("grants").list(object_type="model", object_id=model["id"]),
            {"model": model, "service": self},
        )

    def transition(
        self,
        p: Principal,
        ref: str,
        version_no: int,
        name: str,
        *,
        rationale: str | None = None,
        force: bool = False,
        successor: str | None = None,
    ) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
            if name == "submit" and v["state"] in EDITABLE:
                self._freeze(uow, model, v)
                v = uow.repo("model_versions").require(v["id"])
            if name == "deprecate":
                if not (successor or rationale):
                    raise ValidationFailed(
                        "Deprecation names a successor or states that none exists (§8.6)"
                    )
                uow.repo("model_versions").update(v["id"], {"successor_ref": successor})
            out = self.p.workflow.transition(
                uow, p, self.subject(uow, model, ns, v), name, rationale=rationale, force=force
            )
            if out.moved:
                self._after_move(uow, model, ns, v, out.state)
            return out.__dict__

    def _after_move(
        self, uow: Any, model: dict[str, Any], ns: dict[str, Any], v: dict[str, Any], state: str
    ) -> None:
        uow.repo("models").update(model["id"], {"status": state})
        if state == "approved" and v["maturity"] == "experimental":
            uow.repo("model_versions").update(v["id"], {"maturity": "candidate"})
        elif state in ("deprecated", "retired") and v["maturity"] != state:
            # §8.6's ladder ends in these two rungs and nothing else could reach them:
            # ``maturity`` is only settable through ``update_draft``, which needs an
            # editable draft, so an approved version could never be moved down it. A
            # deprecated version therefore went on advertising itself as a 'candidate',
            # and — because §8.7's cap reads a member's *maturity* and not its state — a
            # composite went on treating a deprecated member as a usable one.
            uow.repo("model_versions").update(v["id"], {"maturity": state})
        me = refs.version_ref("model", ns["name"], model["name"], v["version_no"])
        if state == "approved" and v["formula_ir"] and "composite" in v["formula_ir"]:
            for m in v["formula_ir"]["composite"]["members"]:
                uow.repo("lineage_edges").link(m["ref"], me, "composite_member", m["alias"])
        if state in ("deprecated", "retired"):
            self._warn_dependents(uow, v["id"], me, state)

    def _warn_dependents(self, uow: Any, version_id: str, me: str, state: str) -> None:
        """Deprecation and retirement both warn every owner of a dependent warrant (§8.6).

        Retirement used to warn nobody, which left the owner of a sealed training warrant to
        discover by accident that the version it was drawn on had reached the end of its life.
        The warrant stays valid and stays reproducible — that is what sealing is for — but its
        owner should hear about it from MAYA rather than from somebody else's audit."""
        owners = {
            w["owner_id"]
            for tbl in ("training_warrants", "execution_warrants")
            for w in uow.repo(tbl).list(model_version_id=version_id)
        }
        for owner in owners:
            uow.repo("notifications").add(
                {
                    "user_id": owner,
                    "kind": "deprecation" if state == "deprecated" else "retirement",
                    "message": (
                        f"{me} was {state}; a warrant you own depends on it. A sealed warrant "
                        "stays valid and reproducible."
                    ),
                    "object_ref": me,
                }
            )

    def _freeze(self, uow: Any, model: dict[str, Any], v: dict[str, Any]) -> None:
        body = {
            "ir": irmod.ir_hash(v["formula_ir"]) if v["formula_ir"] else None,
            "artifact": v["artifact_hash"],
            "contract": v["input_contract"],
        }
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
            errors.append(
                "the lifted formula disagrees with the workbook's own results: "
                + check["statement"]
            )
        return (not errors, "; ".join(errors) or "IR validates and typechecks")

    def check_spec(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        rows = section_completeness(ctx["row"]["spec_latex"] or "")
        empty = [r["section"] for r in rows if not r["present"] or r["empty"]]
        if (ctx["row"]["spec_state"] or {}).get("needs_review"):
            empty.append("(document marked for re-review after an IR change — save it)")
        return (
            not empty,
            "required sections empty: " + ", ".join(empty)
            if empty
            else "all required sections present",
        )

    def check_artifact(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        row = ctx["row"]
        if not row["artifact_hash"]:
            return True, "no code artifact attached (formula-only model)"
        report = row["artifact_report"] or {}
        if report.get("status") == "validating":
            return False, "artifact validation is still running"
        return (
            bool(report.get("passed")),
            f"validated under sandbox tier '{report.get('tier')}'"
            if report.get("passed")
            else "artifact failed validation: "
            + "; ".join(r["detail"] for r in report.get("rungs", []) if r["passed"] is False),
        )

    def check_conformance(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        """The code must agree with the mathematics the document states (§29.7).

        The ladder in ``check_artifact`` asks whether the artifact parses, imports nothing
        forbidden and runs. That is a different question from whether it computes the model:
        the commonest implementation bugs are perfectly valid Python. So a closed-form
        version that carries code cannot be moved on until somebody has run the differential
        test against *this* artifact and it agreed everywhere it looked.

        What the check does **not** establish, stated because a gate whose reach is misread is
        worse than none: whether the domain the comparison explored was worth exploring. MAYA
        cannot know whether a named feature set is representative, and it cannot insist on one
        at all — a model version is approved before any warrant binds it to data, which is
        deliberate (§8.2 checks the contract at warrant time, not at model time). So the
        domain is reported here, in the detail a reviewer reads, and sending a version back
        for a comparison over something wider is a judgement a person makes. Agreement over
        numbers near 1 is not evidence about a mortgage or an option, and the report says which
        domain it used precisely so that nobody has to take it for more than it is."""
        row = ctx["row"]
        if not row["artifact_hash"]:
            return True, "no code artifact attached (nothing to compare)"
        ir = row["formula_ir"] or {}
        if irmod.is_opaque(ir):
            return True, "declared black box: there is no closed form to compare against"
        got = (row["artifact_report"] or {}).get("conformance") or {}
        if got.get("artifact_hash") != row["artifact_hash"]:
            return False, (
                "the code has not been tested against the specification since it changed: "
                "run conformance on this version"
            )
        if got["agreed"] != got["total"]:
            examples = got.get("counterexamples") or []
            where = ""
            if examples:
                first = examples[0]
                where = (
                    "; e.g. "
                    + ", ".join(f"{k}={v:g}" for k, v in first.items() if not k.startswith("_"))
                    + f" → specification {first['_expected']:g}, code {first['_actual']:g}"
                )
            return False, (
                f"the code disagrees with the specification on "
                f"{got['total'] - got['agreed']} of {got['total']} sampled inputs{where}"
            )
        return True, (
            f"agreed with the specification on all {got['total']} sampled inputs, "
            f"{got.get('domain', 'domain not recorded')}"
        )

    def check_no_live_warrant(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        """A version still serving production cannot be retired (§8.6, §9.4).

        Retirement is an administrative end of life, not an outage. Left unguarded it was
        neither: a version could be retired while a sealed execution warrant went on serving
        it, so production ran a retired model and nothing said so. Taking a model out of
        service *now* is revocation, which is a different and deliberate act, and this check
        makes the operator do the two in the right order.

        A *training* warrant does not block. It is a record rather than a service, and its
        seal exists to keep the fit reproducible — withdrawing that because the version was
        retired would destroy the thing the seal is for. Its owner is warned instead."""
        live = []
        for ew in uow.repo("execution_warrants").list(model_version_id=ctx["row"]["id"]):
            if self.p.execution.status(ew) in ("live", "suspended"):
                ns = uow.repo("namespaces").get(ew["namespace_id"])
                live.append(f"{(ns or {}).get('name', '?')}/{ew['name']}")
        if not live:
            return True, "no execution warrant is serving this version"
        return False, (
            "an execution warrant is still serving this version: "
            + ", ".join(sorted(live))
            + ". Retirement is not an outage — revoke the warrant first (§9.4)"
        )

    def check_true_build(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        require = (
            self.p.settings.bool("typeset.require_true_build", False)
            or self.p.settings.environment != "dev"
        )
        state = ctx["row"]["spec_state"] or {}
        if not state.get("pdf_blob"):
            return (
                not require,
                "no PDF rendered yet" + ("" if require else " (not required in dev)"),
            )
        if state.get("draft_render"):
            return (
                not require,
                "the PDF is a DRAFT render (no Tectonic)"
                + (
                    "; a model cannot be approved on a draft render"
                    if require
                    else " — accepted in dev only because typeset.require_true_build is false"
                ),
            )
        return True, "PDF is a true LaTeX build"

    def check_members(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        ir = ctx["row"]["formula_ir"] or {}
        if "composite" not in ir:
            return True, "not a composite"
        maturities = self._member_maturities(uow, ir)
        blocking = comp.blocking_members(maturities, "approved")
        low = [a for a, m in maturities.items() if m == "experimental"]
        return (
            not low,
            "members still experimental: " + ", ".join(low)
            if low
            else f"member maturities {maturities}; blocking: {blocking or 'none'}",
        )

    # -- analysis -------------------------------------------------------------------------
    def diff(self, p: Principal, ref: str, v1: int, v2: int) -> dict[str, Any]:
        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            a = catalog.version_of(uow, "model_versions", "model_id", model, v1)
            b = catalog.version_of(uow, "model_versions", "model_id", model, v2)
        return {
            "statements": semantic_diff(a["formula_ir"] or {}, b["formula_ir"] or {}),
            "old_latex": self._latex(a["formula_ir"]),
            "new_latex": self._latex(b["formula_ir"]),
            "artifact_changed": a["artifact_hash"] != b["artifact_hash"],
            "spec_changed": a["spec_latex"] != b["spec_latex"],
        }

    def reference_code(self, p: Principal, ref: str, version_no: int) -> str:
        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        return to_python(v["formula_ir"])

    def conformance(
        self,
        p: Principal,
        ref: str,
        version_no: int,
        *,
        n: int = 2000,
        params: dict[str, Any] | None = None,
        featureset: str | None = None,
    ) -> dict[str, Any]:
        """Differential test of the uploaded Python against the documented IR (§29.7).

        With a ``featureset`` the inputs are resampled from that set's own values, which is
        the domain the model will actually be asked about. Without one they are drawn from
        the unit interval, and the report says so: a disagreement that only appears on a
        seasoned mortgage or a deep-out-of-the-money option will not be found by numbers
        near 1, so an agreement over an invented domain is worth less than it looks."""
        with self.p.uow() as uow:
            model, _ = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
            self.p.access.require(uow, p, "read", "model", model)
            v = catalog.version_of(uow, "model_versions", "model_id", model, version_no)
        if not v["artifact_hash"]:
            raise ValidationFailed("No code artifact to test against the specification")
        if irmod.is_opaque(v["formula_ir"] or {}):
            return {"skipped": True, "statement": "declared black box: nothing to compare"}
        source = self.p.blobs.get(v["artifact_hash"]).decode("utf-8")
        params = params or self._default_params(v)
        cols, domain = self._conformance_domain(p, v, featureset)
        result = self._compare(v, source, params, n=n, cols=cols, domain=domain)
        with self.p.uow(p.username) as uow:
            self._record_conformance(uow, v, result, p.username)
        # The caller needs to be able to tie the answer to the code it was about without
        # reading the version back: an agreement with no artifact hash beside it is a claim
        # about nothing in particular.
        return {**result, "artifact_hash": v["artifact_hash"]}

    def _compare(
        self,
        v: dict[str, Any],
        source: str,
        params: dict[str, Any],
        *,
        n: int,
        cols: dict[str, Any],
        domain: str,
    ) -> dict[str, Any]:
        """Run the artifact in the sandbox over ``n`` sampled rows and compare with the IR."""
        from maya.security.sandbox import run_sandboxed

        samples = sample_inputs(v["formula_ir"], cols, n=n, seed=7)

        def predict(x: dict[str, Any], prm: dict[str, Any]) -> Any:
            out = run_sandboxed(
                source,
                "Model",
                {
                    "mode": "predict",
                    "X": {k: np.asarray(val).tolist() for k, val in x.items()},
                    "params": prm,
                    "seed": 0,
                },
                wall_seconds=60,
            )
            if not out["ok"]:
                raise ValidationFailed(f"artifact failed in the sandbox: {out['error']}")
            return out["result"]

        return {**conformance_test(v["formula_ir"], predict, samples, params), "domain": domain}

    def _conformance_record(
        self, v: dict[str, Any], result: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        """What is kept on the version: the outcome, and the artifact hash it was about."""
        return {
            "artifact_hash": v["artifact_hash"],
            "agreed": result["agreed"],
            "total": result["total"],
            "counterexamples": result["counterexamples"][:3],
            "domain": result["domain"],
            "statement": result["statement"],
            "run_by": actor,
            "run_at": utcnow().isoformat(),
        }

    def _record_conformance(
        self, uow: Any, v: dict[str, Any], result: dict[str, Any], actor: str
    ) -> None:
        # Recorded against the artifact hash it tested, so attaching different code
        # invalidates it rather than inheriting somebody else's clean run.
        report = dict(uow.repo("model_versions").require(v["id"])["artifact_report"] or {})
        report["conformance"] = self._conformance_record(v, result, actor)
        uow.repo("model_versions").update(v["id"], {"artifact_report": report})

    def _conformance_domain(
        self, p: Principal | None, v: dict[str, Any], featureset: str | None
    ) -> tuple[dict[str, Any], str]:
        """The values to draw the differential test's inputs from, and where they came from."""
        names = [c["name"] for c in v["input_contract"] or []]
        if featureset and p is not None:
            res = self.p.featuresets.resolve_ref(p, featureset)
            missing = [name for name in names if name not in res.df.columns]
            if missing:
                raise ValidationFailed(
                    f"{featureset} does not expose {', '.join(missing)}, which the model's "
                    "input contract names, so it cannot supply the test's domain",
                    missing=missing,
                )
            return (
                {name: res.df[name].astype(float).to_numpy() for name in names},
                f"resampled from {featureset} ({len(res.df):,} rows)",
            )
        rng = np.random.default_rng(7)
        return (
            {name: rng.uniform(0.5, 1.5, 256) for name in names},
            "drawn from the unit interval: no feature set was named, so agreement here says "
            "nothing about the values the model will really be given",
        )
