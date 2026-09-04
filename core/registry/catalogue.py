"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The model catalogue: what exists, who owns it, what tier it carries.

Registration is the cheapest governance act in the platform and the one most
often skipped, so it asks for the minimum that makes a model findable and
accountable — owner, legal entity, purpose — and defers everything else to the
version that follows.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.ports import LifecycleGate
from core.registry.common import RegistryError
from db import ModelRepository


class ModelCatalogue:
    """Model identity and status. Emits evidence for everything it changes."""

    # Fields a model owner may revise while the record is open. Identity,
    # status and tier are not here: the URN is permanent, status moves only
    # through the lifecycle, and the tier comes from an assessment.
    EDITABLE = ("name", "description", "owner", "legal_entity", "purpose",
                "model_class", "domain", "origin", "attributes")

    def __init__(self, models: ModelRepository, evidence: EvidenceEngine,
                 gate: Optional[LifecycleGate] = None):
        self.models, self.evidence = models, evidence
        self.gate = gate
        self.policy = None

    def register(self, urn: str, name: str, model_class: str, domain: str, owner: str,
                 legal_entity: str, purpose: str, description: str = "",
                 origin: str = "internal", actor: str = "system",
                 attributes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.models.one(urn=urn):
            raise RegistryError(f"a model is already registered with urn {urn}")
        row = {"urn": urn, "name": name, "description": description,
               "model_class": model_class, "domain": domain, "owner": owner,
               "legal_entity": legal_entity, "purpose": purpose, "origin": origin,
               "status": "draft", "tier": None, "attributes": attributes or {},
               "created_at": time.time(), "created_by": actor}
        self.models.add(row)
        self.evidence.append("model_registered", "model", row["id"],
                             {"urn": urn, "owner": owner}, actor=actor)
        return row

    def by_id(self, model_id: str) -> Optional[Dict[str, Any]]:
        """A model from its id. Rows elsewhere carry the id, not the urn."""
        return self.models.one(id=model_id)

    def get(self, urn: str) -> Optional[Dict[str, Any]]:
        return self.models.one(urn=urn)

    def require(self, urn: str) -> Dict[str, Any]:
        row = self.get(urn)
        if not row:
            raise RegistryError(f"no model registered with urn {urn}")
        return row

    def list(self, domain: Optional[str] = None,
             tier: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.models.many(domain=domain, tier=tier)

    def update(self, urn: str, fields: Dict[str, Any],
               actor: str = "system") -> Dict[str, Any]:
        """Revise an open record. Refused once it is attested."""
        model = self.require(urn)
        if self.gate is not None:
            allowed, why = self.gate.may_mutate(model["id"])
            if not allowed:
                raise RegistryError(f"cannot change {urn}: {why}")
        if self.policy is not None:
            self.policy.check("model:mutate", {
                "tier": model.get("tier"),
                "lifecycle_state": model.get("status"),
                "attested": model.get("status") == "attested",
                "amending": model.get("status") == "amending"}, urn)
        unknown = set(fields) - set(self.EDITABLE)
        if unknown:
            raise RegistryError(
                f"these fields are not editable: {', '.join(sorted(unknown))}; "
                f"editable fields are {', '.join(self.EDITABLE)}")
        if not fields:
            return model
        self.models.set(dict(fields), id=model["id"])
        self.evidence.append("model_updated", "model", model["id"],
                             {"changed": sorted(fields),
                              "from": {k: model.get(k) for k in fields}}, actor=actor)
        return self.models.one(id=model["id"])

    def set_tier(self, model_id: str, tier: int) -> None:
        self.models.set({"tier": tier}, id=model_id)

    def set_status(self, model_id: str, status: str, actor: str = "system") -> None:
        self.models.set({"status": status}, id=model_id)
        self.evidence.append("status_changed", "model", model_id,
                             {"status": status}, actor=actor)
