"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The documentation graph, and the two things a list could not do.

Documentation about a model is not a list. It is a graph, and the edges are the
pins that already exist in the register:

    model
     ├── attached: methodology paper, literature, vendor note
     ├── compiled: model development document, model card, Annex IV
     └── version 1.0.0
          ├── attached: kernel specification
          ├── compiled: validation report
          ├── parameter set ps-8817        (fitted 2026-03-31)
          │    ├── compiled: TRAINING RECORD
          │    └── attached: convergence study
          └── fitted from  featureset sb_core @ v1
               ├── attached: data dictionary, source agreement
               └── feature dscr
                    └── attached: business definition

Two properties make it worth walking rather than listing.

**It follows the pins, not the names.** A training record links `sb_core@v1`,
not `sb_core`. A document that referenced the *set* would describe something that
has since moved — finding C-2 in documentation's clothing — so the walk goes
through the featureset **version** the parameters were actually fitted from, and
a reader who asks *what was this trained on* gets the schema that was in force
rather than the one that is.

**Gaps are named.** A featureset with no data dictionary is a gap in the
dossier, not an absence a reader has to notice. Same discipline as the compiled
documents and the export pack, for the same reason: a page that silently omits
what it could not find reads as complete.

The dossier is **computed, never stored**. Its inputs are all versioned or
immutable, so there is nothing to keep in step — and a stored dossier would be a
second account of the model's documentation, able to disagree with the first.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.docs.subjects import (FEATURESET_VERSION, FEATURE, MODEL,
                                MODEL_VERSION, PARAMETER_SET, VALIDATION)
from core.log import get_logger

logger = get_logger(__name__)

# There was a `MAX_DEPTH = 8` here, with a comment saying the dossier "says so
# rather than running forever". Nothing read it. The walk is not recursive — it
# is five named methods calling each other in one direction, model → version →
# {parameter set, featureset version} → feature, and `_feature` returns a leaf
# with no children. So the bound is structural and a constant could only ever
# have been decorative.
#
# It is removed rather than wired up, because a limit nobody reaches is a limit
# nobody tests, and a declared-but-unread constant reads to the next person as a
# control that exists.


class Dossier:
    """Everything documented about a model, following the pins."""

    def __init__(self, registry, attachments=None, documents=None,
                 parameters=None, featuresets=None, features=None,
                 validation=None):
        self.registry = registry
        self.attachments = attachments
        self.documents = documents
        self.parameters = parameters
        # Wired as the FeatureRegistry, whose featureset half is `.sets`.
        # Resolved once here rather than at each call site: doing it in one
        # method and not the next is how the pin came to resolve and then fail
        # one step further down.
        self.featuresets = getattr(featuresets, "sets", featuresets)
        self.features = features
        self.validation = validation

    # ------------------------------------------------------------------ walk
    def of(self, urn: str) -> Dict[str, Any]:
        """The graph, rooted at one model."""
        model = self.registry.require(urn)
        gaps: List[Dict[str, str]] = []

        node = self._node(MODEL, model["id"], model.get("name", urn), gaps,
                          expect="the methodology, and the literature the "
                                 "approach comes from")
        node["urn"] = model["urn"]
        node["children"] = [self._version(model, v, gaps)
                            for v in self.registry.versions(urn)]

        counts = _count(node)
        return {"urn": model["urn"], "model": model["name"], "root": node,
                "gaps": gaps, "counts": counts,
                "detail": (f"{counts['documents']} document(s) across "
                           f"{counts['nodes']} node(s)"
                           + (f"; {len(gaps)} gap(s)" if gaps
                              else "; nothing missing"))}

    # ----------------------------------------------------------------- parts
    def _version(self, model: Dict[str, Any], version: Dict[str, Any],
                 gaps: List[Dict[str, str]]) -> Dict[str, Any]:
        node = self._node(MODEL_VERSION, version["id"],
                          f"version {version['semver']}", gaps,
                          expect="the specification of this kernel")
        node["semver"] = version["semver"]
        node["status"] = version.get("status")
        children = []

        for parameter_set in self._parameter_sets(version):
            children.append(self._parameters(parameter_set, gaps))
        for episode in self._validations(model, version):
            children.append(self._node(
                VALIDATION, episode["id"],
                f"validation {episode.get('scope', '')}".strip(), gaps,
                expect="the independent recode, and the reviewer's working"))
        node["children"] = children
        return node

    def _parameters(self, parameter_set: Dict[str, Any],
                    gaps: List[Dict[str, str]]) -> Dict[str, Any]:
        node = self._node(
            PARAMETER_SET, parameter_set["id"],
            f"parameters {parameter_set.get('name', '')}".strip(), gaps,
            expect="the training record, and any note explaining this fit")
        node["provenance"] = parameter_set.get("provenance")
        node["status"] = parameter_set.get("status")
        node["as_of"] = parameter_set.get("as_of")

        # The pin. A parameter set names the featureset VERSION it was fitted
        # from, and the dossier follows that rather than the set — which is the
        # difference between "what was this trained on" and "what does that
        # featureset look like today".
        #
        # The row holds `featureset_version_id`; it has no `featureset` or
        # `featureset_version` column and never had. So this read two keys that
        # are always absent, the pin was never followed for **any** fitted set,
        # and every export pack carried the gap below — "a fitted set that does
        # not name the featureset version it came from" — about sets that plainly
        # do name one.
        #
        # A false gap is worse than a missing feature. `gaps.md` is the property
        # that lets a reader tell a thin model from a thin export, and a gap that
        # is always there teaches them to skip the file.
        name, number = self._pin(parameter_set)
        if name and number is not None:
            node["children"] = [self._featureset_version(name, number, gaps)]
        elif parameter_set.get("provenance") == "fitted":
            gaps.append({
                "what": f"parameters {parameter_set.get('name')}",
                "why": "a fitted set that does not name the featureset version "
                       "it came from — 'what data produced these numbers' has "
                       "no answer from here"})
        return node

    def _pin(self, parameter_set: Dict[str, Any]):
        """The featureset version a fitted set came from, as name and number.

        Resolved from `featureset_version_id`, which is what the row carries. An
        id is not something a reviewer can read, and the dossier is read by
        people rather than by joins.
        """
        version_id = parameter_set.get("featureset_version_id")
        if not version_id or self.featuresets is None:
            return None, None
        for row in self.featuresets.list():
            for version in self.featuresets.versions_of(row["name"]):
                if version["id"] == version_id:
                    return row["name"], version["version"]
        # A pin that does not resolve is a real gap, and a different one from
        # having no pin at all: the set named a featureset version that the
        # register can no longer find.
        logger.warning("parameter set %s pins featureset version %s, which the "
                       "register cannot resolve",
                       parameter_set.get("name"), version_id)
        return None, None

    def _featureset_version(self, name: str, number: int,
                            gaps: List[Dict[str, str]]) -> Dict[str, Any]:
        node = self._node(FEATURESET_VERSION, f"{name}@{number}",
                          f"{name} @ v{number}", gaps,
                          expect="the data dictionary, and the source-system "
                                 "agreement")
        node["featureset"] = name
        node["version"] = number
        node["children"] = [self._feature(slot, gaps)
                            for slot in self._slots(name, number)]
        return node

    def _feature(self, name: str, gaps: List[Dict[str, str]]) -> Dict[str, Any]:
        node = self._node(FEATURE, name, name, gaps,
                          expect="the business definition")
        node["children"] = []
        return node

    def _node(self, subject_type: str, subject_id: str, label: str,
              gaps: List[Dict[str, str]], expect: str = "") -> Dict[str, Any]:
        attached = self._attached(subject_type, subject_id)
        compiled = self._compiled(subject_type, subject_id)
        if not attached and not compiled and expect:
            # Named rather than left blank. A reader cannot tell a thin model
            # from a thin page unless the page says which it is.
            gaps.append({"what": f"{subject_type} {label}",
                         "why": f"nothing is filed here; expected {expect}"})
        return {"subject_type": subject_type, "subject_id": subject_id,
                "label": label, "attached": attached, "compiled": compiled,
                "expected": expect, "children": []}

    # ------------------------------------------------------------- the reads
    def _attached(self, subject_type: str, subject_id: str) -> List[Dict[str, Any]]:
        if self.attachments is None:
            return []
        try:
            return [{k: row.get(k) for k in
                     ("id", "kind", "title", "filename", "digest", "state",
                      "reviewed_by", "attached_by", "attached_at")}
                    for row in self.attachments.about(subject_type, subject_id)]
        except Exception as exc:
            logger.warning("could not read attachments for %s %s: %s",
                           subject_type, subject_id, exc)
            return []

    def _compiled(self, subject_type: str, subject_id: str) -> List[Dict[str, Any]]:
        if self.documents is None:
            return []
        try:
            rows = self.documents.about(subject_type, subject_id)
        except Exception as exc:
            logger.warning("could not read documents for %s %s: %s",
                           subject_type, subject_id, exc)
            return []
        return [{k: row.get(k) for k in
                 ("id", "kind", "title", "digest", "status", "compiled_at",
                  "compiled_by")}
                for row in rows]

    def _parameter_sets(self, version: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.parameters is None:
            return []
        try:
            return self.parameters.for_version(version["id"])
        except Exception as exc:
            logger.warning("could not read parameter sets for %s: %s",
                           version.get("semver"), exc)
            return []

    def _validations(self, model: Dict[str, Any],
                     version: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.validation is None:
            return []
        try:
            episodes = self.validation.for_model(model["urn"])
        except Exception as exc:
            logger.warning("could not read validations for %s: %s",
                           model.get("urn"), exc)
            return []
        return [e for e in episodes
                if e.get("model_version_id") in (None, version["id"])]

    def _slots(self, name: str, number: int) -> List[str]:
        if self.featuresets is None:
            return []
        try:
            version = self.featuresets.version(name, number)
        except Exception as exc:
            logger.warning("could not read featureset %s@%s: %s", name, number, exc)
            return []
        return sorted((version or {}).get("bindings") or {})


def _count(node: Dict[str, Any]) -> Dict[str, int]:
    nodes = documents = 0
    stack = [node]
    while stack:
        current = stack.pop()
        nodes += 1
        documents += len(current.get("attached") or []) + \
            len(current.get("compiled") or [])
        stack.extend(current.get("children") or [])
    return {"nodes": nodes, "documents": documents}
