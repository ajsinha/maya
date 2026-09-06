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
from typing import Any, Dict, Optional

from core.artifacts.common import EXECUTES_ON_LOAD
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
              governance: Optional[Dict[str, Any]] = None,
              parameter_set: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            "parameters": self._parameters(version, kernel, verb,
                                           parameter_set),
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
    def _parameters(version: Dict[str, Any], kernel: Dict[str, Any],
                    verb: str = "score",
                    parameter_set: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        kind = version.get("parameter_kind", "none")
        return {"kind": kind,
                "source": _parameter_source(kind, verb, version, parameter_set),
                "digest": version.get("artifact_digest"),
                # Parameters are immutable for every verb except fit, and a fit
                # writes a NEW parameter object rather than editing this one.
                "mutable": False}

    @staticmethod
    def _realisation(version: Dict[str, Any], kernel: Dict[str, Any]) -> Dict[str, Any]:
        """Everything an engine needs to locate and load the thing that runs.

        The artifact block says WHAT the bytes are as well as where: the format
        decides how they are loaded, the size tells a caller what it is about to
        fetch, and `executes_on_load` says whether loading them runs code the
        platform did not write -- which is the difference between a graph and a
        pickle, and is not something an engine should be inferring from a file
        extension.

        `held_by_maya` is the one that matters operationally. An artifact stored
        here is addressed by its digest, so an engine can fetch it from the
        platform that authorised it; an artifact merely NAMED is somewhere else,
        and the warrant should say which of the two this is rather than leaving
        an engine to discover it from a URI scheme.
        """
        runtime = kernel.get("runtime") or DESCRIPTOR_ONLY
        entry = kernel.get("entry") or {}
        digest = version.get("artifact_digest")
        fmt = kernel.get("artifact_format")
        artifact: Dict[str, Any] = {
            "uri": version.get("artifact_uri"),
            "digest": digest,
            "format": fmt,
            "size": version.get("artifact_size"),
            "executes_on_load": fmt in EXECUTES_ON_LOAD,
            "held_by_maya": bool(digest) and str(
                version.get("artifact_uri") or "").startswith("maya://artifact/"),
        }
        if artifact["held_by_maya"]:
            # Where to GET it, so an engine holding a warrant needs nothing else.
            artifact["fetch"] = f"/api/v1/artifacts/{digest}"
        return {"runtime": runtime, "entry": entry, "artifact": artifact,
                "environment": kernel.get("environment") or {}}

    @staticmethod
    def _data(verb: str) -> Dict[str, Any]:
        """The default binding: the caller supplies inputs, the response carries
        outputs. Anything richer is passed in by whoever knows the contract."""
        return {"inputs": [{"name": "features", "binding": "request"}],
                "outputs": [{"name": "prediction", "sink": "response"}]}


def _parameter_source(kind: str, verb: str, version: Dict[str, Any],
                      parameter_set: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Which point in the parameter object this run is at.

    A fit does not read a parameter object, it writes one — so declaring that its
    parameters come from the artifact would describe the wrong direction. Where a
    registered parameter set is supplied it is named and digested, because that
    is what makes the run attributable to numbers somebody approved.
    """
    if kind == "none":
        return {}                      # T0: nothing to bind, and nothing to name
    if kind == "opaque":
        return {"binding": "vendor_internal"}
    if verb == "fit":
        return {"binding": "to_be_fitted"}
    if parameter_set:
        source = {"binding": "parameter_set",
                  "parameter_set": parameter_set["id"],
                  "name": parameter_set.get("name"),
                  "version": parameter_set.get("version"),
                  "digest": parameter_set["digest"]}
        # When the parameters are a calibration, the moment they were solved for
        # is part of what they mean: two runs naming this set on different
        # mornings are not the same run. L-W11 requires it to be statable; the
        # age is carried alongside so a reader does not have to subtract two
        # epochs to find out they are running last quarter's fit.
        if (as_of := parameter_set.get("as_of")) is not None:
            source["as_of"] = as_of
            source["age_seconds"] = max(0.0, time.time() - float(as_of))
        return source
    if not version.get("artifact_digest") and not version.get("artifact_uri"):
        # There is no approved set and no artifact either, so an artifact
        # binding here would be a fabrication: the warrant would tell an engine
        # to run at a point of P that does not exist anywhere. Refusing names
        # what is missing; L-W12 would otherwise catch it one step later and
        # report it as a malformed document rather than as an absent approval.
        raise WarrantError(
            "no_approved_parameters",
            f"this version's parameter object is '{kind}' and nothing inhabits "
            f"it: no approved parameter set, and no artifact to carry one",
            "record a parameter set and have somebody other than its author "
            "approve it, or register the version against an artifact")
    return {"binding": "artifact", "uri": version.get("artifact_uri")}
