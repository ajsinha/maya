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
from maya.core.errors import ValidationFailed
from maya.core.version import VERSION
from maya.formula import ir as irmod
from maya.formula.codegen import to_python
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


def run_verifier(data: bytes, script: str) -> dict[str, Any]:
    """Run a verifier script over a bundle in a clean interpreter; its JSON report."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bundle.zip"
        path.write_bytes(data)
        (Path(tmp) / "verify.py").write_text(script, encoding="utf-8")
        proc = subprocess.run([sys.executable, "-I", str(Path(tmp) / "verify.py"), str(path)],
                              capture_output=True, text=True, timeout=300, check=False)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"verified": False, "error": proc.stderr[-2000:]}


class BundleService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def export(self, p: Principal, warrant_id: str) -> dict[str, Any]:
        """Build a signed bundle for a training warrant and store it as a blob."""
        w = self.p.warrants.get(p, warrant_id)
        self.p.licences.export(p, "featureset", w["featureset_ref"], "external")
        with self.p.uow() as uow:
            mv = uow.repo("model_versions").require(w["model_version_id"])
            params = next((ps for ps in w["parameter_sets"]
                           if ps["state"] in ("approved", "published")), None) or \
                (w["parameter_sets"][-1] if w["parameter_sets"] else None)
        df, _ = self.p.warrants.training_frame(self._row(warrant_id), include_test=True)
        table = pa.Table.from_pandas(df, preserve_index=False).replace_schema_metadata(None)
        buf = io.BytesIO()
        pq.write_table(table, buf)
        table = pq.read_table(io.BytesIO(buf.getvalue()))
        files: dict[str, bytes] = {"data/training.parquet": buf.getvalue()}
        ir = mv["formula_ir"] or {}
        reexec, why = self._reexecutable(ir, params)
        values = params["values"] if params else {}
        out_hash = None
        if reexec:
            pred = self.p.warrants.predict(mv, df, w["spec"].get("bindings", {}), values)
            out_hash = output_hash(pred)
            files["model/reference_model.py"] = to_python(ir).encode()
        files.update(self._documents(w, mv, params, values))
        files["lib/canonical.py"] = Path(canonical.__file__).read_bytes()
        files["lib/chunker.py"] = Path(chunker.__file__).read_bytes()
        files["verify.py"] = VERIFY_PY.encode()
        manifest = {
            "maya_version": VERSION, "warrant": w["uri"], "exported_at": utcnow().isoformat(),
            "exported_by": p.username,
            "files": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())},
            "data_content_hash": self._content(table), "reexecutable": reexec,
            "not_reexecutable_reason": why, "output_hash": out_hash,
            "model_inputs": [c["name"] for c in irmod.input_contract(ir)] if reexec else [],
            "bindings": w["spec"].get("bindings", {}),
            "sealed_featureset_pin": w["featureset_ref"],
        }
        manifest["signature"] = self.p.signer.signature_block(
            json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode())
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in sorted(files.items()):
                z.writestr(name, data)
            z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        digest = self.p.blobs.put(zbuf.getvalue())
        with self.p.uow(p.username) as uow:
            self.p.warrants._custody(uow, warrant_id, "bundle_exported", p.username,
                                     checksum=digest)
            uow.audit("bundle.exported", object_type="training_warrant", object_ref=w["uri"],
                      detail={"blob": digest, "reexecutable": reexec})
        return {"blob": digest, "size": len(zbuf.getvalue()), "manifest": manifest}

    def _row(self, warrant_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            return uow.repo("training_warrants").require(warrant_id)

    @staticmethod
    def _content(table: pa.Table) -> str:
        return canonical.table_content_hash(table)

    @staticmethod
    def _reexecutable(ir: dict[str, Any], params: dict[str, Any] | None) -> tuple[bool, str | None]:
        if not ir or irmod.is_opaque(ir):
            return False, ("declared black box: MAYA holds no executable specification, so "
                           "this bundle verifies inputs only and says so")
        if "composite" in ir:
            return False, "composite re-execution in verify.py is not shipped in this build"
        if irmod.parameter_inputs(ir) and not params:
            return False, "no parameter set has been uploaded against this warrant"
        return True, None

    def _documents(self, w: dict[str, Any], mv: dict[str, Any], params: dict[str, Any] | None,
                   values: dict[str, Any]) -> dict[str, bytes]:
        def dump(obj: Any) -> bytes:
            return djson.dumps(obj, indent=2).encode()
        return {
            "warrant.json": dump({k: w[k] for k in ("uri", "name", "version_no", "spec",
                                                    "featureset_ref", "contract_report",
                                                    "backends", "custody")}),
            "certificate.json": dump(w["leakage_certificate"]),
            "model/model_version.json": dump({k: mv[k] for k in (
                "version_no", "maturity", "ir_hash", "artifact_hash", "input_contract",
                "definition_hash")}),
            "model/formula_ir.json": dump(mv["formula_ir"]),
            "model/spec.tex": (mv["spec_latex"] or "").encode(),
            "model/parameters.json": dump(values),
            "model/parameter_set.json": dump(params or {}),
            "environment.json": dump({"python": sys.version.split()[0],
                                      "declared": w["spec"].get("environment"),
                                      "backends": w["backends"]}),
        }

    def verify(self, data: bytes) -> dict[str, Any]:
        """Verify a bundle on the server, as ``verify.py`` does offline.

        Verification executes code the bundle carries (the canonical hasher and the
        reference model), so the server runs it only for a bundle this MAYA signed and
        whose every file still matches its signed hash — and then with MAYA's own
        ``verify.py``, never the uploaded one. Anything else is reported, not executed:
        verifying a stranger's bundle is for ``python verify.py`` on your own machine.
        """
        refusal = self._untrusted(data)
        if refusal is not None:
            return {"verified": False, "checks": [refusal], "executed": False}
        return {**run_verifier(data, VERIFY_PY), "executed": True}

    @staticmethod
    def verify_offline(data: bytes) -> dict[str, Any]:
        """``maya export verify`` on your own machine: the bundle's own ``verify.py``, run
        by you on a bundle you chose — exactly what ``python verify.py`` would do."""
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                script = z.read("verify.py").decode("utf-8")
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValidationFailed(f"Not a MAYA bundle: {exc}") from exc
        return run_verifier(data, script)

    def _untrusted(self, data: bytes) -> dict[str, Any] | None:
        """Why the server will not execute this bundle's code, or None when it may."""
        from maya.core.crypto import verify as verify_signature
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            manifest = json.loads(z.read("manifest.json"))
            files, sig = manifest["files"], manifest.get("signature") or {}
        except (zipfile.BadZipFile, KeyError, ValueError, TypeError) as exc:
            raise ValidationFailed(f"Not a MAYA bundle: {exc}") from exc
        why = "not executed on the server"
        signer = self.p.signer_or_none()
        body = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        if signer is None or sig.get("public_key") != signer.public_key_b64:
            return {"check": "signed by this MAYA", "ok": False,
                    "detail": f"{why}: the bundle is not signed by this instance's key; "
                              "verify it offline with 'python verify.py bundle.zip'"}
        try:
            signed = verify_signature(sig["public_key"], body, str(sig.get("signature", "")))
        except ValueError:
            signed = False
        if not signed:
            return {"check": "Ed25519 signature over the file list", "ok": False,
                    "detail": f"{why}: the signature does not verify"}
        names = set(z.namelist())
        for name, digest in files.items():
            if name not in names or hashlib.sha256(z.read(name)).hexdigest() != digest:
                return {"check": f"file hash {name}", "ok": False,
                        "detail": f"{why}: {name} is missing or altered"}
        if names - set(files) - {"manifest.json"}:
            return {"check": "file list", "ok": False,
                    "detail": f"{why}: files outside the signed list: "
                              + ", ".join(sorted(names - set(files) - {"manifest.json"}))}
        return None
