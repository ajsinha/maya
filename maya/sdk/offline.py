"""
``maya.offline(bundle=…)`` (§18.2.3, §18.4): the read API served from a
reproducibility bundle, on a machine with no route to any MAYA.

Opening a bundle checks it before anything is read: every file against the
manifest's hash, and the Ed25519 signature over the file list (when the
``cryptography`` package is present; otherwise the report says it was not
checked). A bundle that fails is refused, not partly served.

What a bundle holds is served with the same method names a live client uses —
``training.get``, ``training.data``, ``training_data``, ``models.get`` — plus
``predict``, which evaluates the signed formula IR with MAYA's own evaluator.
The bundle's ``reference_model.py`` is never imported: a bundle may come from
outside, and opening one must not run code it carries. Anything a bundle does
not hold (the catalog, workflow, other warrants) is refused by name.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from maya.core.errors import CapabilityRefused, MayaError, NotFound, ValidationFailed


class NotInBundle(MayaError):
    """The call needs a live MAYA; an offline bundle does not hold what it asks for."""

    code, status = "not_in_bundle", 0


class _Refuse:
    def __init__(self, area: str, holds: str) -> None:
        self._area, self._holds = area, holds

    def __getattr__(self, name: str) -> Any:
        def refuse(*_: Any, **__: Any) -> Any:
            raise NotInBundle(f"{self._area}.{name}() needs a live MAYA; this offline bundle "
                              f"holds {self._holds}")
        return refuse


class _Training:
    def __init__(self, off: "Offline") -> None:
        self._off = off

    def get(self, warrant_id: str | None = None) -> dict[str, Any]:
        return {**self._off._check_id(warrant_id), "offline": True}

    def data(self, warrant_id: str | None = None) -> dict[str, Any]:
        self._off._check_id(warrant_id)
        return {"data": self._off.files["data/training.parquet"],
                "manifest": {"checksum": self._off.checksum, "offline": True,
                             "partition": "every row, including the escrowed holdout",
                             "data_content_hash": self._off.manifest["data_content_hash"],
                             "warrant": self._off.manifest["warrant"]},
                "content_type": "application/vnd.apache.parquet"}

    def __getattr__(self, name: str) -> Any:
        return getattr(_Refuse("training", self._off.holds), name)


class _Models:
    def __init__(self, off: "Offline") -> None:
        self._off = off

    def get(self, ref: str | None = None) -> dict[str, Any]:
        return {"versions": [{**self._off.json("model/model_version.json"),
                              "formula_ir": self._off.json("model/formula_ir.json"),
                              "spec_latex": self._off.files["model/spec.tex"].decode()}],
                "offline": True}

    def __getattr__(self, name: str) -> Any:
        return getattr(_Refuse("models", self._off.holds), name)


class Offline:
    """A verified bundle, read with the SDK's own method names."""

    mode = "offline"

    def __init__(self, bundle: str | Path | bytes) -> None:
        raw = bundle if isinstance(bundle, bytes) else Path(bundle).read_bytes()
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                self.files = {n: z.read(n) for n in z.namelist()}
        except zipfile.BadZipFile as exc:
            raise ValidationFailed("Not a MAYA reproducibility bundle (not a zip)") from exc
        if "manifest.json" not in self.files:
            raise ValidationFailed("Not a MAYA reproducibility bundle (no manifest.json)")
        self.manifest = json.loads(self.files["manifest.json"])
        self.report = self._verify()
        bad = [c for c in self.report if c["ok"] is False]
        if bad:
            raise ValidationFailed("The bundle failed verification and is refused: "
                                   + "; ".join(c["check"] for c in bad), checks=self.report)
        self.warrant = self.json("warrant.json")
        self.holds = f"warrant {self.manifest['warrant']} (its model, parameters and data)"
        self.checksum = self._checksum()
        self.training = _Training(self)
        self.models = _Models(self)
        for area in ("features", "featuresets", "execution", "workflow", "jobs", "access", "assistant",
                     "admin", "auth", "namespaces", "workspaces", "sources", "events",
                     "custody"):
            setattr(self, area, _Refuse(area, self.holds))

    # -- verification --------------------------------------------------------------------
    def _verify(self) -> list[dict[str, Any]]:
        checks = []
        for name, digest in self.manifest.get("files", {}).items():
            actual = hashlib.sha256(self.files.get(name, b"")).hexdigest() \
                if name in self.files else None
            checks.append({"check": f"file hash {name}", "ok": actual == digest})
        sig = self.manifest.get("signature") or {}
        body = json.dumps(self.manifest.get("files", {}), sort_keys=True,
                          separators=(",", ":")).encode()
        try:
            from maya.core.crypto import verify
            try:
                good = bool(sig) and verify(sig["public_key"], body, sig["signature"])
            except (ValueError, KeyError):           # malformed key or signature
                good = False
            checks.append({"check": "Ed25519 signature over the file list", "ok": good,
                           "key_id": sig.get("key_id")})
        except (ImportError, CapabilityRefused):
            checks.append({"check": "signature", "ok": None,
                           "detail": "not checked: the 'cryptography' package is absent"})
        return checks

    def verify(self) -> dict[str, Any]:
        """The checks made on opening, plus the canonical data content hash."""
        from maya.core.canonical import table_content_hash
        table = self.table()
        content = table_content_hash(table)
        checks = self.report + [{"check": "data content hash (canonical, value-based)",
                                 "ok": content == self.manifest["data_content_hash"]}]
        return {"verified": all(c["ok"] is not False for c in checks), "checks": checks,
                "warrant": self.manifest["warrant"], "offline": True}

    # -- reading ------------------------------------------------------------------------------
    def json(self, name: str) -> Any:
        if name not in self.files:
            raise NotFound(f"The bundle has no {name}")
        return json.loads(self.files[name])

    def table(self) -> Any:
        import pyarrow.parquet as pq
        return pq.read_table(io.BytesIO(self.files["data/training.parquet"]))

    def _checksum(self) -> str:
        from maya.sdk.io import table_checksum
        return table_checksum(self.table())

    def _check_id(self, warrant_id: str | None) -> dict[str, Any]:
        if warrant_id not in (None, self.warrant.get("uri"), self.warrant.get("name"),
                              self.warrant.get("id")):
            raise NotInBundle(f"This bundle holds {self.manifest['warrant']}, not '{warrant_id}'")
        return self.warrant

    def training_data(self, warrant_id: str | None = None) -> tuple[Any, dict[str, Any]]:
        """As ``Client.training_data``: the table, verified against its checksum."""
        result = self.training.data(warrant_id)
        return self.table(), result["manifest"]

    def parameters(self) -> dict[str, Any]:
        return self.json("model/parameters.json")

    def certificate(self) -> dict[str, Any]:
        return self.json("certificate.json")

    def predict(self, X: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Evaluate the signed formula IR (never the bundle's Python) on ``X``; for a
        composite, the signed member IRs too."""
        from maya.formula.evaluate import evaluate, evaluate_composite
        ir = self.json("model/formula_ir.json")
        values = self.parameters() if params is None else params
        if ir and "composite" in ir and "model/member_irs.json" in self.files:
            members = self.json("model/member_irs.json")
            if all("body" in m for m in members.values()):
                return evaluate_composite(ir, members, X, values)
        if not ir or "body" not in ir:
            raise NotInBundle("This model has no closed form in the bundle (a black box, or a "
                              "composite with a member that is not closed-form): it cannot be "
                              "evaluated offline")
        return evaluate(ir, X, values)

    def close(self) -> None:
        self.files = {}

    def __enter__(self) -> "Offline":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def offline(bundle: str | Path | bytes) -> Offline:
    """Open a reproducibility bundle as a read-only, network-free MAYA."""
    return Offline(bundle)
