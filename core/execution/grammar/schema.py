"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

JSON Schema for the warrant grammar, generated from the vocabulary.

Generated rather than hand-written, because a schema that is maintained
separately from the vocabulary it describes will disagree with it, and the
disagreement will be discovered by whoever trusted the schema.

This is published at ``/api/v1/grammar/schema`` so an execution engine in any
language can validate a warrant before acting on it — which is the point of
having a grammar rather than a convention.
"""
from __future__ import annotations

from typing import Any, Dict

from core.execution.grammar.rules import NON_FITTABLE, admissible_verbs
from core.execution.grammar.vocabulary import (BINDINGS, RUNTIME_ENTRY, RUNTIMES,
                                               SECTIONS, SINKS, VERB_MEANING, VERBS,
                                               WARRANT_VERSION)


def _entry_conditionals() -> list:
    """One if/then per runtime, so the required entry keys are in the schema."""
    out = []
    for runtime, keys in RUNTIME_ENTRY.items():
        if not keys:
            continue
        out.append({
            "if": {"properties": {"runtime": {"const": runtime}}},
            "then": {"properties": {"entry": {"required": list(keys)}}},
        })
    return out


def json_schema() -> Dict[str, Any]:
    """The full JSON Schema for a MAYA warrant document."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://maya.dev/schema/warrant/{WARRANT_VERSION}",
        "title": "MAYA execution warrant",
        "description": (
            "A signed, expiring, entitlement-bound instruction an execution "
            "engine acts on. The grammar is the product of four independent "
            "vocabularies: how the parameter object is inhabited, how the kernel "
            "is realised, what operation is asked of it, and where its data "
            "comes from."),
        "type": "object",
        "required": ["maya_warrant", "warrant_id", "issued_at", *SECTIONS],
        # Underscore-prefixed keys are annotations: a note to a reader, never
        # something an engine acts on. Allowed everywhere so a warrant can be
        # commented without failing its own schema.
        "patternProperties": {"^_": {}},
        "additionalProperties": False,
        "properties": {
            "maya_warrant": {"const": WARRANT_VERSION},
            "warrant_id": {"type": "string"},
            "issued_at": {"type": "number"},

            "subject": {
                "type": "object", "description": SECTIONS["subject"],
                "required": ["urn", "model_urn", "version", "manifest_digest",
                             "trainability_class"],
                "properties": {
                    "urn": {"type": "string", "pattern": "^maya://model/"},
                    "model_urn": {"type": "string"},
                    "version": {"type": "string"},
                    "version_id": {"type": "string"},
                    "manifest_digest": {"type": "string"},
                    "binding_kind": {"enum": ["alias", "pinned_version"]},
                    "trainability_class": {
                        "type": "string", "pattern": "^T[0-8]$",
                        "description": "derived from how the parameter object is "
                                       "inhabited; determines which verbs are admissible"},
                },
            },

            "operation": {
                "type": "object", "description": SECTIONS["operation"],
                "required": ["verb"],
                "properties": {
                    "verb": {"enum": list(VERBS),
                             "description": "; ".join(f"{v}: {VERB_MEANING[v]}"
                                                      for v in VERBS)},
                    "determinism": {"enum": ["deterministic", "stochastic"]},
                    "seed": {"type": ["integer", "null"]},
                    "mode": {"enum": ["single", "batch", "streaming"]},
                },
            },

            "parameters": {
                "type": "object", "description": SECTIONS["parameters"],
                "required": ["kind"],
                "properties": {
                    "kind": {"enum": ["none", "calibration_set",
                                      "estimated_coefficients", "learned_weights",
                                      "llm_configuration", "rule_set",
                                      "elicited_weights", "opaque"]},
                    "source": {"type": "object"},
                    "digest": {"type": ["string", "null"]},
                    "mutable": {"type": "boolean"},
                },
            },

            "realisation": {
                "type": "object", "description": SECTIONS["realisation"],
                "required": ["runtime", "entry"],
                "properties": {
                    "runtime": {"enum": list(RUNTIMES)},
                    "entry": {"type": "object"},
                    "artifact": {
                        "type": "object",
                        "properties": {"uri": {"type": ["string", "null"]},
                                       "digest": {"type": ["string", "null"]},
                                       "format": {"type": ["string", "null"]}},
                    },
                    "environment": {"type": "object"},
                },
                "allOf": _entry_conditionals(),
            },

            "data": {
                "type": "object", "description": SECTIONS["data"],
                "properties": {
                    "inputs": {"type": "array", "items": {
                        "type": "object", "required": ["name", "binding"],
                        "properties": {"name": {"type": "string"},
                                       "binding": {"enum": list(BINDINGS)}},
                    }},
                    "outputs": {"type": "array", "items": {
                        "type": "object", "required": ["name", "sink"],
                        "properties": {"name": {"type": "string"},
                                       "sink": {"enum": list(SINKS)}},
                    }},
                },
            },

            "io_contract": {
                "type": "object", "description": SECTIONS["io_contract"],
                "properties": {"input_schema": {"type": "array"},
                               "output_schema": {"type": "array"}},
            },

            "constraints": {
                "type": "object", "description": SECTIONS["constraints"],
                "properties": {
                    "operating_boundary": {"type": "object"},
                    "on_boundary_violation": {"enum": ["reject", "flag", "clamp"]},
                    "resources": {"type": "object"},
                },
            },

            "authority": {
                "type": "object", "description": SECTIONS["authority"],
                "required": ["principal", "declared_use", "environment",
                             "granted_at", "expires_at"],
                "properties": {
                    "principal": {"type": "string"},
                    "declared_use": {"type": "string"},
                    "environment": {"type": "string"},
                    "granted_at": {"type": "number"},
                    "expires_at": {"type": "number"},
                    "grace_seconds": {"type": "number"},
                    "revocation": {"type": "object"},
                },
            },

            "governance": {"type": "object", "description": SECTIONS["governance"]},

            "signature": {
                "type": "object", "description": SECTIONS["signature"],
                "required": ["alg", "value"],
                "properties": {"alg": {"type": "string"},
                               "key_id": {"type": "string"},
                               "value": {"type": "string"}},
            },
        },
    }


def vocabulary() -> Dict[str, Any]:
    """The four axes, published so a client can build a warrant without guessing."""
    return {
        "warrant_version": WARRANT_VERSION,
        "sections": SECTIONS,
        "operations": [{"verb": v, "means": VERB_MEANING[v]} for v in VERBS],
        "runtimes": [{"runtime": r, "entry_keys": list(keys)}
                     for r, keys in RUNTIME_ENTRY.items()],
        "bindings": list(BINDINGS),
        "sinks": list(SINKS),
        "admissibility": {
            "non_fittable_classes": sorted(NON_FITTABLE),
            "by_trainability_class": {
                klass: admissible_verbs(klass)
                for klass in [f"T{i}" for i in range(9)]},
        },
    }
