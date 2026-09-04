"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Descriptor construction.

The descriptor is the entire contract between MAYA and an execution engine, so
its shape is the platform's most public commitment — everything an engine needs
to run a model correctly, and nothing it needs to ask a second question about.
It carries a version, and a governance snapshot taken at the moment of
resolution, so that what an engine acted on can be reconstructed later even if
the model has moved on since.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from core.execution.signing import DescriptorSigner
from db.database import new_id

DESCRIPTOR_VERSION = "1.0"


class DescriptorFactory:
    """Builds and signs the descriptor an execution engine acts on."""

    def __init__(self, signer: DescriptorSigner):
        self.signer = signer

    def build(self, urn: str, model: Dict[str, Any], version: Dict[str, Any],
              grant: Dict[str, Any], principal: str, declared_use: str,
              environment: str, epoch: int) -> Dict[str, Any]:
        ttl, now = self.signer.jittered(grant["ttl_seconds"]), time.time()
        descriptor = {
            "maya_descriptor_version": DESCRIPTOR_VERSION, "descriptor_id": new_id(),
            "urn": urn,
            "resolved": {"model_urn": model["urn"], "version": version["semver"],
                         "version_id": version["id"],
                         "manifest_digest": version["manifest_digest"],
                         "binding_kind": grant["binding_kind"],
                         "trainability_class": version["trainability_class"]},
            "authorization": {"principal": principal, "declared_use": declared_use,
                              "environment": environment, "granted_at": now,
                              "expires_at": now + ttl,
                              "grace_seconds": grant["grace_seconds"]},
            "execution": {"flavour": grant["flavour"],
                          "artifact_digest": version["artifact_digest"],
                          "deterministic": version["deterministic"]},
            "io_contract": {"input_schema": version["input_schema"],
                            "output_schema": version["output_schema"]},
            "constraints": version["contract"],
            "governance_snapshot": {"tier": model.get("tier"),
                                    "model_status": model["status"],
                                    "version_status": version["status"]},
            "revocation": {"epoch": epoch},
        }
        descriptor["signature"] = self.signer.sign(descriptor)
        return descriptor
