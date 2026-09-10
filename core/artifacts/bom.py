"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Everything a version is made of, in a form somebody else's tool can read.

AI Act Art. 11 asks for technical documentation, and the two standards a bank's
supply-chain team already runs — SPDX 3.0's AI and Dataset profiles, and
CycloneDX's ML-BOM — are how that arrives in a form their scanners understand.

**The bill of materials is derived, never authored.** Every component in it is
something the register already holds: the artifact and its digest, the featureset
version and the features it binds, the snapshot the parameters were fitted from,
the parameter set and its digest, the runtime the warrant grammar admits. An
authored BOM is a document that was true once, and the whole reason a supply-chain
team wants one is to diff it against the last.

**What it will not do is invent the parts MAYA never saw.** A model artifact
built elsewhere has a dependency tree, and this register does not have it — it
has a digest. So the BOM emits what it holds and names what it does not, rather
than emitting a plausible-looking tree with the interesting half missing. A BOM
whose gaps are invisible is worse than a short one, because a scanner reports it
as clean.

**Both formats, from one derivation.** SPDX and CycloneDX disagree about names
and nest differently, and a firm's tooling has usually standardised on one. Two
serialisers over one component list cannot drift; two independently-assembled
documents would, and the one that drifted would be the one nobody was reading.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

SPDX, CYCLONEDX = "spdx", "cyclonedx"
FORMATS = (SPDX, CYCLONEDX)

#: What a component of a model version can be, and which standard field it maps
#: to. Named as data because both serialisers read it, which is what stops them
#: disagreeing about what a version is made of.
COMPONENT_KINDS: Dict[str, Dict[str, str]] = {
    "model": {"spdx": "SOFTWARE_PACKAGE", "cyclonedx": "machine-learning-model",
              "is": "the version itself"},
    "artifact": {"spdx": "FILE", "cyclonedx": "file",
                 "is": "the bytes that execute, by digest"},
    "dataset": {"spdx": "DATASET", "cyclonedx": "data",
                "is": "the snapshot the parameters were fitted from"},
    "featureset": {"spdx": "SOFTWARE_PACKAGE", "cyclonedx": "library",
                   "is": "the schema that shaped the inputs"},
    "feature": {"spdx": "SOFTWARE_PACKAGE", "cyclonedx": "data",
                "is": "one input the model reads"},
    "parameters": {"spdx": "FILE", "cyclonedx": "data",
                   "is": "the point in P this version runs at"},
    "runtime": {"spdx": "SOFTWARE_PACKAGE", "cyclonedx": "framework",
                "is": "what the warrant grammar admits as an executor"},
}

#: The parts a register cannot know about a model it did not build. Named in
#: every document, because a BOM whose gaps are invisible is worse than a short
#: one — a scanner reports it as clean.
NOT_KNOWN: Dict[str, str] = {
    "transitive_dependencies": (
        "the library tree inside the artifact. MAYA has the artifact's digest "
        "and not its contents, and emitting a plausible tree with the "
        "interesting half missing would be worse than emitting none"),
    "build_environment": (
        "the toolchain that produced the artifact. It is the fitter's to state "
        "and is asked for in the reproducibility bundle"),
    "training_code": (
        "the procedure. It does not live in this register, and its revision is "
        "somebody else's fact"),
}


class BillOfMaterials:
    """Derives what a version is made of, and serialises it two ways."""

    def __init__(self, registry, features=None, parameters=None):
        self.registry = registry
        self.features, self.parameters = features, parameters

    # ------------------------------------------------------------ components
    def components(self, urn: str, semver: str) -> Dict[str, Any]:
        """Everything the register knows this version is made of."""
        model = self.registry.require(urn)
        version = self.registry.version_service.require(urn, semver)
        rows: List[Dict[str, Any]] = [{
            "kind": "model", "name": model.get("name") or urn,
            "identifier": f"{urn}@{semver}",
            "digest": version.get("manifest_digest"),
            "note": (f"trainability class {version.get('trainability_class')}, "
                     f"derived from how P is inhabited and never declared"),
        }]
        if version.get("artifact_digest"):
            rows.append({
                "kind": "artifact", "name": version.get("artifact_uri")
                or "artifact", "identifier": version.get("artifact_uri") or "",
                "digest": version["artifact_digest"],
                "note": "verified by digest at resolution",
            })
        rows += self._runtime(version)
        rows += self._from_parameters(model, version)
        return {
            "urn": urn, "semver": semver, "components": rows,
            "count": len(rows),
            "not_known": [{"part": k, "why": v} for k, v in NOT_KNOWN.items()],
            "detail": (
                f"{len(rows)} component(s) derived from what the register "
                f"holds. {len(NOT_KNOWN)} part(s) are named as NOT known "
                f"rather than emitted as an empty list — a bill of materials "
                f"whose gaps are invisible is worse than a short one, because "
                f"a scanner reports it as clean"),
        }

    @staticmethod
    def _runtime(version: Dict[str, Any]) -> List[Dict[str, Any]]:
        manifest = version.get("manifest") or {}
        runtime = (manifest.get("runtime") if isinstance(manifest, dict)
                   else None)
        if not runtime:
            return []
        return [{"kind": "runtime", "name": str(runtime),
                 "identifier": str(runtime), "digest": None,
                 "note": "one of the vocabulary the warrant grammar admits"}]

    def _from_parameters(self, model: Dict[str, Any],
                         version: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The dataset, featureset and features, reached through the fit.

        Reached through the parameter set rather than declared on the version,
        because a version says which fields it reads and a *fit* says which
        rows and which schema actually produced the numbers.
        """
        if self.parameters is None:
            return []
        rows: List[Dict[str, Any]] = []
        seen = set()
        for parameters in self.parameters.parameters.many(
                model_version_id=version["id"]):
            key = ("parameters", parameters.get("digest"))
            if key not in seen:
                seen.add(key)
                rows.append({
                    "kind": "parameters",
                    "name": parameters.get("name") or "parameters",
                    "identifier": parameters["id"],
                    "digest": parameters.get("digest"),
                    "note": f"provenance {parameters.get('provenance')}",
                })
            if parameters.get("snapshot_id") and (
                    "dataset", parameters["snapshot_id"]) not in seen:
                seen.add(("dataset", parameters["snapshot_id"]))
                rows.append({
                    "kind": "dataset", "name": "training snapshot",
                    "identifier": parameters["snapshot_id"], "digest": None,
                    "note": ("the rows the fit actually read, pinned — which "
                             "is what makes a re-run answer the same question"),
                })
            rows += self._featureset(parameters.get("featureset_version_id"),
                                     seen)
        return rows

    def _featureset(self, featureset_version_id: Optional[str],
                    seen: set) -> List[Dict[str, Any]]:
        if not featureset_version_id or self.features is None:
            return []
        if ("featureset", featureset_version_id) in seen:
            return []
        seen.add(("featureset", featureset_version_id))
        row = self.features.sets.versions.one(id=featureset_version_id)
        if not row:
            return []
        out = [{"kind": "featureset", "name": "featureset version",
                "identifier": featureset_version_id,
                "digest": row.get("digest"),
                "note": "the schema that shaped the inputs"}]
        for binding in (row.get("bindings") or {}).values():
            name = (binding.get("feature") if isinstance(binding, dict)
                    else binding)
            if not name or ("feature", name) in seen:
                continue
            seen.add(("feature", name))
            out.append({"kind": "feature", "name": name, "identifier": name,
                        "digest": None, "note": "one input the model reads"})
        return out

    # ----------------------------------------------------------- serialising
    def render(self, urn: str, semver: str, fmt: str = SPDX,
               now: Optional[float] = None) -> Dict[str, Any]:
        """The same derivation, in whichever dialect the firm's tooling reads.

        Two serialisers over one component list cannot drift. Two
        independently-assembled documents would, and the one that drifted would
        be the one nobody was reading.
        """
        from core.artifacts.common import ArtifactError

        if fmt not in FORMATS:
            raise ArtifactError(
                "unknown_bom_format",
                f"'{fmt}' is not a bill-of-materials format",
                "one of " + ", ".join(FORMATS))
        derived = self.components(urn, semver)
        moment = now if now is not None else time.time()
        document = (self._spdx(derived, moment) if fmt == SPDX
                    else self._cyclonedx(derived, moment))
        return {**derived, "format": fmt, "document": document}

    @staticmethod
    def _spdx(derived: Dict[str, Any], moment: float) -> Dict[str, Any]:
        return {
            "spdxVersion": "SPDX-3.0",
            "dataLicense": "CC0-1.0",
            "name": f"{derived['urn']}@{derived['semver']}",
            "created": moment,
            "packages": [{
                "SPDXID": f"SPDXRef-{i}",
                "name": c["name"],
                "primaryPackagePurpose": COMPONENT_KINDS[c["kind"]]["spdx"],
                "checksums": ([{"algorithm": "SHA256", "checksumValue": c["digest"]}]
                              if c.get("digest") else []),
                "comment": c["note"],
            } for i, c in enumerate(derived["components"])],
            # The gaps, inside the document rather than beside it: a consumer
            # reading only the file must see them, because that consumer is a
            # scanner and it will otherwise report this as complete.
            "annotations": [{
                "annotationType": "OTHER",
                "comment": f"NOT INCLUDED — {gap['part']}: {gap['why']}",
            } for gap in derived["not_known"]],
        }

    @staticmethod
    def _cyclonedx(derived: Dict[str, Any], moment: float) -> Dict[str, Any]:
        return {
            "bomFormat": "CycloneDX", "specVersion": "1.6",
            "metadata": {
                "timestamp": moment,
                "component": {"type": "machine-learning-model",
                              "name": f"{derived['urn']}@{derived['semver']}"},
                "properties": [{
                    "name": f"maya:not-included:{gap['part']}",
                    "value": gap["why"],
                } for gap in derived["not_known"]],
            },
            "components": [{
                "type": COMPONENT_KINDS[c["kind"]]["cyclonedx"],
                "name": c["name"], "bom-ref": c["identifier"],
                "hashes": ([{"alg": "SHA-256", "content": c["digest"]}]
                           if c.get("digest") else []),
                "description": c["note"],
            } for c in derived["components"]],
        }
