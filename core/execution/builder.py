"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Building a warrant that conforms to the grammar.

The warrant is the entire contract between MAYA and an execution engine, so its
shape is the platform's most public commitment: everything an engine needs to
act correctly, and nothing it needs to ask a second question about.

The four axes are filled in from four different places, which is why they stay
independent:

  * **parameters** comes from the version's kernel specification — how P is
    inhabited, which is what the trainability class is derived from.
  * **realisation** comes from the version's artifact and its declared runtime.
  * **operation** comes from the *request*: the same version can be scored
    today and fitted tomorrow, and those are different warrants.
  * **data** comes from the feature contract and the request together.

Every warrant is validated against the grammar before it is signed. A malformed
or inadmissible warrant is never handed out, so an engine that trusts the
signature can also trust the shape.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.execution.errors import WarrantError
from core.execution.grammar import GrammarValidator, WARRANT_VERSION
from core.execution.signing import WarrantSigner
from db.database import new_id

# When a version declares its runtime and entry, the warrant carries them and an
# engine can locate the artifact unaided. When it does not, the honest answer is
# `descriptor_only`: MAYA holds the governance, the schemas and the operating
# boundary, and the engine supplies the model.
#
# Guessing would be worse than saying so. A warrant asserting `python.callable`
# with an entry nobody filled in is a warrant that fails at the artifact, which
# is the most expensive place to discover a registration was incomplete.
DESCRIPTOR_ONLY = "descriptor_only"


class WarrantBuilder:
    """Builds, validates and signs the document an execution engine acts on."""

    def __init__(self, signer: WarrantSigner,
                 validator: Optional[GrammarValidator] = None):
        self.signer = signer
        self.validator = validator or GrammarValidator()

    # ----------------------------------------------------------------- build
    def build(self, urn: str, model: Dict[str, Any], version: Dict[str, Any],
              grant: Dict[str, Any], principal: str, declared_use: str,
              environment: str, epoch: int, *, verb: str = "score",
              realisation: Optional[Dict[str, Any]] = None,
              data: Optional[Dict[str, Any]] = None,
              governance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = time.time()
        ttl = self.signer.jittered(grant["ttl_seconds"])
        manifest = version.get("manifest") or {}
        kernel = manifest.get("kernel") or {}

        doc: Dict[str, Any] = {
            "maya_warrant": WARRANT_VERSION,
            "warrant_id": new_id(),
            "issued_at": now,

            "subject": {
                "urn": urn, "model_urn": model["urn"], "version": version["semver"],
                "version_id": version["id"],
                "manifest_digest": version["manifest_digest"],
                "binding_kind": grant["binding_kind"],
                "trainability_class": version["trainability_class"],
            },

            "operation": self._operation(verb, version, kernel),
            "parameters": self._parameters(version, kernel),
            "realisation": realisation or self._realisation(version, kernel),
            "data": data or self._data(verb),

            "io_contract": {"input_schema": version["input_schema"],
                            "output_schema": version["output_schema"]},

            "constraints": {
                "operating_boundary": version["contract"],
                "on_boundary_violation": (version["contract"] or {}).get(
                    "on_boundary_violation", "reject"),
                "resources": {"max_seconds": grant.get("max_seconds", 30)},
            },

            "authority": {
                "principal": principal, "declared_use": declared_use,
                "environment": environment, "granted_at": now,
                "expires_at": now + ttl,
                "grace_seconds": grant["grace_seconds"],
                "revocation": {"epoch": epoch, "check": "required"},
            },

            "governance": governance or {
                "tier": model.get("tier"), "model_status": model["status"],
                "version_status": version["status"],
            },
        }
        return self._seal(doc)

    def _seal(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Validate, then sign. Never the other way round.

        A signature over a document that does not conform would be an assurance
        that the document is authentic and not that it is usable, and engines
        would reasonably read it as both.
        """
        doc["signature"] = {"alg": self.signer.ALGORITHM,
                            "key_id": self.signer.key_id, "value": ""}
        report = self.validator.validate(doc)
        if not report.valid:
            raise WarrantError(
                "grammar_violation",
                f"the warrant does not conform to the grammar: {report.as_dict()['detail']}",
                "this is a defect in the model's registration, not in the request; "
                "the problems name the exact paths")
        doc["signature"]["value"] = self.signer.sign(doc)
        return doc

    # --------------------------------------------------------------- the axes
    @staticmethod
    def _operation(verb: str, version: Dict[str, Any],
                   kernel: Dict[str, Any]) -> Dict[str, Any]:
        deterministic = bool(version.get("deterministic", True))
        return {"verb": verb,
                "determinism": "deterministic" if deterministic else "stochastic",
                "seed": kernel.get("seed"),
                "mode": "batch"}

    @staticmethod
    def _parameters(version: Dict[str, Any], kernel: Dict[str, Any]) -> Dict[str, Any]:
        kind = version.get("parameter_kind", "none")
        return {"kind": kind,
                "source": ({"binding": "artifact", "uri": version.get("artifact_uri")}
                           if kind != "none" else {}),
                "digest": version.get("artifact_digest"),
                # Parameters are immutable for every verb except fit, and a fit
                # writes a NEW parameter object rather than editing this one.
                "mutable": False}

    @staticmethod
    def _realisation(version: Dict[str, Any], kernel: Dict[str, Any]) -> Dict[str, Any]:
        runtime = kernel.get("runtime") or DESCRIPTOR_ONLY
        entry = kernel.get("entry") or {}
        return {"runtime": runtime, "entry": entry,
                "artifact": {"uri": version.get("artifact_uri"),
                             "digest": version.get("artifact_digest"),
                             "format": kernel.get("artifact_format")},
                "environment": kernel.get("environment") or {}}

    @staticmethod
    def _data(verb: str) -> Dict[str, Any]:
        """The default binding: the caller supplies inputs, the response carries
        outputs. Anything richer is passed in by whoever knows the contract."""
        return {"inputs": [{"name": "features", "binding": "request"}],
                "outputs": [{"name": "prediction", "sink": "response"}]}
