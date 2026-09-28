"""
Reproducibility bundles (§18.4, §28.7): the artifact handed to a regulator.

A bundle is a zip holding the warrant, the model version and its formula IR,
the generated reference implementation, the parameter set, the feature set
pin's data and manifest, the leakage certificate, the environment and backend
set, and ``verify.py``. The verifier needs Python, ``pyarrow`` and ``numpy``
and nothing from MAYA: it recomputes every file hash, recomputes the data's
content hash with MAYA's canonical encoder (shipped inside the bundle, since
it *is* the definition of the hash), and re-executes the model to compare its
output hash with the one recorded at export. Where re-execution is
impossible — a declared black box — the bundle says so instead of implying a
verification it cannot perform.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from maya.core import canonical, chunker, djson
from maya.core import archives
from maya.core.errors import MayaError, ValidationFailed
from maya.core.version import VERSION
from maya.formula import ir as irmod
from maya.formula.codegen import to_python, to_python_composite
from maya.core.clock import utcnow
from maya.security.authz import Principal

VERIFY_PY = r'''"""Offline verifier for a MAYA reproducibility bundle. Needs pyarrow + numpy only."""
import hashlib, json, sys, zipfile, importlib.util, io, pathlib, tempfile

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def output_hash(values):
    import numpy as np
    arr = np.round(np.asarray(values, dtype="float64"), 10)
    return hashlib.sha256(arr.astype(">f8").tobytes()).hexdigest()

def main(bundle):
    import pyarrow.parquet as pq
    report = {"bundle": str(bundle), "checks": []}
    ok = True
    with zipfile.ZipFile(bundle) as z, tempfile.TemporaryDirectory() as tmp:
        infos = z.infolist()
        expanded = sum(i.file_size for i in infos)
        compressed = sum(i.compress_size for i in infos) or 1
        if len(infos) > 5000 or expanded > 2 * 1024**3 or expanded // compressed > 200:
            print(json.dumps({"verified": False, "error": "this bundle expands far past "
                              "what a MAYA bundle holds; refusing to read it"}))
            return
        if any(n.startswith("/") or ".." in n.split("/") for n in z.namelist()):
            print(json.dumps({"verified": False, "error": "this bundle holds an entry that "
                              "would be written outside it; refusing to read it"}))
            return
        z.extractall(tmp)
        root = pathlib.Path(tmp)
        manifest = json.loads((root / "manifest.json").read_text())
        for name, digest in manifest["files"].items():
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
            good = actual == digest; ok &= good
            report["checks"].append({"check": f"file hash {name}", "ok": good})
        sig = manifest.get("signature")
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            import base64
            pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(sig["public_key"]))
            body = json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode()
            pub.verify(base64.b64decode(sig["signature"]), body)
            report["checks"].append({"check": "Ed25519 signature over the file list", "ok": True})
        except ImportError:
            report["checks"].append({"check": "signature", "ok": None,
                                     "detail": "not checked: install 'cryptography'"})
        except Exception as exc:
            ok = False
            report["checks"].append({"check": "signature", "ok": False, "detail": str(exc)})
        canon = _load("canonical", root / "lib" / "canonical.py")
        table = pq.read_table(root / "data" / "training.parquet")
        content = canon.table_content_hash(table)
        good = content == manifest["data_content_hash"]; ok &= good
        report["checks"].append({"check": "data content hash (canonical, value-based)",
                                 "ok": good, "detail": content})
        if manifest.get("reexecutable"):
            ref = _load("reference_model", root / "model" / "reference_model.py")
            params = json.loads((root / "model" / "parameters.json").read_text())
            bindings = manifest.get("bindings", {})
            X = {name: table.column(bindings.get(name, name)).to_numpy(zero_copy_only=False)
                 .astype("float64") for name in manifest["model_inputs"]}
            out = ref.predict(X, params)
            values = list(out.values())[0] if isinstance(out, dict) else out
            h = output_hash(values)
            good = h == manifest["output_hash"]; ok &= good
            report["checks"].append({"check": "re-execution output hash", "ok": good,
                                     "detail": h})
        else:
            report["checks"].append({"check": "re-execution", "ok": None,
                                     "detail": manifest.get("not_reexecutable_reason")})
    report["verified"] = bool(ok)
    print(json.dumps(report, indent=2))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "bundle.zip"))
'''


def output_hash(values: Any) -> str:
    arr = np.round(np.asarray(values, dtype="float64"), 10)
    return hashlib.sha256(arr.astype(">f8").tobytes()).hexdigest()


def bounded(data: bytes, settings: Any = None) -> Any:
    """The bundle as a bounded zip (§21.1). Anything that is not one is refused by name, in
    the words a caller who offered a bundle expects."""
    try:
        return archives.opened(data, settings=settings, what="bundle")
    except ValidationFailed as exc:
        if "not a readable zip" in exc.message:
            raise ValidationFailed(f"Not a MAYA bundle: {exc.message}") from exc
        raise


def run_verifier(data: bytes, script: str) -> dict[str, Any]:
    """Run a verifier script over a bundle in a clean interpreter; its JSON report."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bundle.zip"
        path.write_bytes(data)
        (Path(tmp) / "verify.py").write_text(script, encoding="utf-8")
        # ``-I`` so the verifier runs as it would on a machine with no MAYA: no working
        # directory, no PYTHONPATH, no user site. It still needs pyarrow and numpy, so it is
        # told where this interpreter's libraries live -- plain directories, no .pth files,
        # so an editable install of MAYA is not among them.
        from maya.security.sandbox import _library_paths, _python

        boot = (
            "import runpy, sys; sys.path.extend(%r); "
            "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"
            % (_library_paths(),)
        )
        proc = subprocess.run(
            [_python(), "-I", "-c", boot, str(Path(tmp) / "verify.py"), str(path)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    try:
        return dict(json.loads(proc.stdout))
    except json.JSONDecodeError:
        # A verifier that could not run is a failed check, named, never a missing report.
        error = (proc.stderr or proc.stdout or "no output")[-2000:]
        return {
            "verified": False,
            "error": error,
            "checks": [
                {"check": "the verifier ran", "ok": False, "detail": error.strip().splitlines()[-1]}
            ],
        }


class BundleService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def export(self, p: Principal, warrant_id: str) -> dict[str, Any]:
        """Build a signed bundle for a training warrant and store it as a blob."""
        w = self.p.warrants.get(p, warrant_id)
        self.p.licences.export(p, "featureset", w["featureset_ref"], "external")
        with self.p.uow() as uow:
            mv = uow.repo("model_versions").require(w["model_version_id"])
            params = next(
                (ps for ps in w["parameter_sets"] if ps["state"] in ("approved", "published")), None
            ) or (w["parameter_sets"][-1] if w["parameter_sets"] else None)
        df, _ = self.p.warrants.training_frame(self._row(warrant_id), include_test=True)
        table = pa.Table.from_pandas(df, preserve_index=False).replace_schema_metadata(None)
        buf = io.BytesIO()
        pq.write_table(table, buf)
        table = pq.read_table(io.BytesIO(buf.getvalue()))
        files: dict[str, bytes] = {"data/training.parquet": buf.getvalue()}
        ir = mv["formula_ir"] or {}
        members: dict[str, Any] = {}
        if "composite" in ir:
            with self.p.uow() as uow:
                members = self.p.models._member_irs(uow, ir)
            files["model/member_irs.json"] = djson.dumps(members, indent=2).encode()
        reexec, why = self._reexecutable(ir, params, members)
        values = params["values"] if params else {}
        bindings = w["spec"].get("bindings", {})
        out_hash = None
        inputs: list[str] = []
        if reexec:
            pred = self.p.warrants.predict(mv, df, bindings, values)
            out_hash = output_hash(pred)
            if members:
                files["model/reference_model.py"] = to_python_composite(ir, members).encode()
                inputs = sorted(
                    {
                        c["name"]
                        for m in members.values()
                        for c in irmod.input_contract(m)
                        if bindings.get(c["name"], c["name"]) in df.columns
                    }
                )
            else:
                files["model/reference_model.py"] = to_python(ir).encode()
                inputs = [c["name"] for c in irmod.input_contract(ir)]
        files.update(self._documents(w, mv, params, values))
        files.update(self._inputs_and_artifact(w, mv))
        files["lib/canonical.py"] = Path(canonical.__file__).read_bytes()
        files["lib/chunker.py"] = Path(chunker.__file__).read_bytes()
        files["verify.py"] = VERIFY_PY.encode()
        manifest = {
            "maya_version": VERSION,
            "warrant": w["uri"],
            "exported_at": utcnow().isoformat(),
            "exported_by": p.username,
            "files": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())},
            "data_content_hash": self._content(table),
            "reexecutable": reexec,
            "not_reexecutable_reason": why,
            "output_hash": out_hash,
            "model_inputs": inputs,
            "bindings": w["spec"].get("bindings", {}),
            "sealed_featureset_pin": w["featureset_ref"],
        }
        manifest["signature"] = self.p.signer.signature_block(
            json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode()
        )
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in sorted(files.items()):
                z.writestr(name, data)
            z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        digest = self.p.blobs.put(zbuf.getvalue())
        with self.p.uow(p.username) as uow:
            self.p.warrants._custody(
                uow, warrant_id, "bundle_exported", p.username, checksum=digest
            )
            uow.audit(
                "bundle.exported",
                object_type="training_warrant",
                object_ref=w["uri"],
                detail={"blob": digest, "reexecutable": reexec},
            )
        return {"blob": digest, "size": len(zbuf.getvalue()), "manifest": manifest}

    def _row(self, warrant_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            return uow.repo("training_warrants").require(warrant_id)

    @staticmethod
    def _content(table: pa.Table) -> str:
        return canonical.table_content_hash(table)

    @staticmethod
    def _reexecutable(
        ir: dict[str, Any], params: dict[str, Any] | None, members: dict[str, Any] | None = None
    ) -> tuple[bool, str | None]:
        if not ir or irmod.is_opaque(ir):
            return False, (
                "declared black box: MAYA holds no executable specification, so "
                "this bundle verifies inputs only and says so"
            )
        if "composite" in ir:
            opaque = sorted(a for a, m in (members or {}).items() if "body" not in m)
            if opaque:
                return False, (
                    "composite with members that are not closed-form ("
                    + ", ".join(opaque)
                    + "): nested composites and black boxes "
                    "cannot be re-executed, so this bundle verifies inputs only"
                )
            needs_params = bool(irmod.parameter_inputs(ir)) or any(
                irmod.parameter_inputs(m) for m in (members or {}).values()
            )
            return (
                (False, "no parameter set has been uploaded against this warrant")
                if needs_params and not params
                else (True, None)
            )
        if irmod.parameter_inputs(ir) and not params:
            return False, "no parameter set has been uploaded against this warrant"
        return True, None

    def _inputs_and_artifact(self, w: dict[str, Any], mv: dict[str, Any]) -> dict[str, bytes]:
        """The three things §18.4 asks for and the bundle did not carry: the code artifact
        that was uploaded and validated, the feature-set definition the warrant was drawn
        on, and the member pins behind that feature set.

        Member *data* is not copied: the training frame in the bundle already is that data,
        resolved and pinned, and copying every member pin again would multiply a bundle's
        size for no new fact. What is copied is each member pin's identity and manifest, so
        a reader can say exactly which bytes the frame came from and check them against a
        MAYA that still holds them.
        """
        out: dict[str, bytes] = {}
        if mv.get("artifact_hash"):
            try:
                out["model/artifact.py"] = self.p.blobs.get(mv["artifact_hash"])
            except Exception as exc:  # noqa: BLE001 - a missing blob must not lose the bundle
                out["model/artifact.missing.txt"] = (
                    f"the uploaded artifact {mv['artifact_hash'][:16]} is no longer in the "
                    f"blob store: {exc}"
                ).encode()
            out["model/artifact_report.json"] = djson.dumps(
                mv.get("artifact_report") or {}, indent=2
            ).encode()
        try:
            fs, ns, version, pin, eff, inherited = self.p.featuresets.load(w["featureset_ref"])
        except MayaError as exc:
            out["featureset/missing.txt"] = (
                f"{w['featureset_ref']} could not be read at export: {exc.message}"
            ).encode()
            return out
        out["featureset/definition.json"] = djson.dumps(
            {
                "ref": w["featureset_ref"],
                "namespace": ns["name"],
                "name": fs["name"],
                "version_no": version["version_no"],
                "written": version["definition"],
                "effective": eff,
                "inherited_policies": inherited,
            },
            indent=2,
        ).encode()
        if pin is not None:
            # member_pin_ids maps each member reference to the pin row that fixed it
            with self.p.uow() as uow:
                members = [
                    {"member": ref, **(uow.repo("feature_pins").get(pin_id) or {"missing": True})}
                    for ref, pin_id in sorted((pin.get("member_pin_ids") or {}).items())
                ]
            out["featureset/pin.json"] = djson.dumps(
                {
                    "pin_name": pin["pin_name"],
                    "as_of_date": pin["as_of_date"],
                    "as_of_known": pin["as_of_known"],
                    "content_hash": pin["content_hash"],
                    "row_count": pin["row_count"],
                    "manifest": pin.get("manifest") or {},
                },
                indent=2,
            ).encode()
            out["featureset/member_pins.json"] = djson.dumps(
                [
                    {
                        k: m.get(k)
                        for k in (
                            "member",
                            "id",
                            "feature_id",
                            "pin_name",
                            "as_of_date",
                            "as_of_known",
                            "content_hash",
                            "row_count",
                            "fragments",
                            "missing",
                        )
                    }
                    for m in members
                ],
                indent=2,
            ).encode()
        return out

    def _documents(
        self,
        w: dict[str, Any],
        mv: dict[str, Any],
        params: dict[str, Any] | None,
        values: dict[str, Any],
    ) -> dict[str, bytes]:
        def dump(obj: Any) -> bytes:
            return djson.dumps(obj, indent=2).encode()

        return {
            "warrant.json": dump(
                {
                    k: w[k]
                    for k in (
                        "uri",
                        "name",
                        "version_no",
                        "spec",
                        "featureset_ref",
                        "contract_report",
                        "backends",
                        "custody",
                    )
                }
            ),
            "certificate.json": dump(w["leakage_certificate"]),
            "model/model_version.json": dump(
                {
                    k: mv[k]
                    for k in (
                        "version_no",
                        "maturity",
                        "ir_hash",
                        "artifact_hash",
                        "input_contract",
                        "definition_hash",
                    )
                }
            ),
            "model/formula_ir.json": dump(mv["formula_ir"]),
            "model/spec.tex": (mv["spec_latex"] or "").encode(),
            "model/parameters.json": dump(values),
            "model/parameter_set.json": dump(params or {}),
            "environment.json": dump(
                {
                    "python": sys.version.split()[0],
                    "declared": w["spec"].get("environment"),
                    "backends": w["backends"],
                }
            ),
        }

    def verify(self, data: bytes) -> dict[str, Any]:
        """Verify a bundle on the server, as ``verify.py`` does offline.

        Verification executes code the bundle carries (the canonical hasher and the
        reference model), so the server runs it only for a bundle this MAYA signed and
        whose every file still matches its signed hash — and then with MAYA's own
        ``verify.py``, never the uploaded one. Anything else is reported, not executed:
        verifying a stranger's bundle is for ``python verify.py`` on your own machine.
        """
        bounded(data, self.p.settings)  # bounded before anything reads or runs it
        refusal = self._untrusted(data)
        if refusal is not None:
            return {"verified": False, "checks": [refusal], "executed": False}
        return {**run_verifier(data, VERIFY_PY), "executed": True}

    @staticmethod
    def verify_offline(data: bytes) -> dict[str, Any]:
        """``maya export verify`` on your own machine: the bundle's own ``verify.py``, run
        by you on a bundle you chose — exactly what ``python verify.py`` would do."""
        z = bounded(data)
        try:
            script = archives.read(z, "verify.py", what="bundle").decode("utf-8")
        except KeyError as exc:
            raise ValidationFailed(f"Not a MAYA bundle: {exc}") from exc
        return run_verifier(data, script)

    def _untrusted(self, data: bytes) -> dict[str, Any] | None:
        """Why the server will not execute this bundle's code, or None when it may."""
        from maya.core.crypto import verify as verify_signature

        try:
            z = bounded(data, self.p.settings)
            manifest = json.loads(archives.read(z, "manifest.json", what="bundle"))
            files, sig = manifest["files"], manifest.get("signature") or {}
        except (KeyError, ValueError, TypeError) as exc:
            raise ValidationFailed(f"Not a MAYA bundle: {exc}") from exc
        why = "not executed on the server"
        signer = self.p.signer_or_none()
        body = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        if signer is None or sig.get("public_key") != signer.public_key_b64:
            return {
                "check": "signed by this MAYA",
                "ok": False,
                "detail": f"{why}: the bundle is not signed by this instance's key; "
                "verify it offline with 'python verify.py bundle.zip'",
            }
        try:
            signed = verify_signature(sig["public_key"], body, str(sig.get("signature", "")))
        except ValueError:
            signed = False
        if not signed:
            return {
                "check": "Ed25519 signature over the file list",
                "ok": False,
                "detail": f"{why}: the signature does not verify",
            }
        names = set(z.namelist())
        for name, digest in files.items():
            if name not in names or hashlib.sha256(z.read(name)).hexdigest() != digest:
                return {
                    "check": f"file hash {name}",
                    "ok": False,
                    "detail": f"{why}: {name} is missing or altered",
                }
        if names - set(files) - {"manifest.json"}:
            return {
                "check": "file list",
                "ok": False,
                "detail": f"{why}: files outside the signed list: "
                + ", ".join(sorted(names - set(files) - {"manifest.json"})),
            }
        return None
