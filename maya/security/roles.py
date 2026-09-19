"""
The eight shipped roles and their capability matrix (§3), as data.

C create · R read · U update · A approve · P pin/seal · G grant · Q request a pin.
Roles are stored in the database and seeded from this table; an administrator
can define custom roles as further named capability sets.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

OBJECT_TYPES = (
    "feature",
    "feature_pin",
    "featureset",
    "model",
    "artifact",
    "specdoc",
    "training_warrant",
    "parameter_set",
    "execution_warrant",
    "users",
    "jobs",
    "namespace",
    "workflow_policy",
)

_R = "R"
MATRIX: dict[str, dict[str, str]] = {
    "admin": {
        "feature": "CRUG",
        "feature_pin": "P",
        "featureset": "CRUG",
        "model": "CRUG",
        "artifact": "CRU",
        "specdoc": "CRU",
        "training_warrant": "CRUG",
        "parameter_set": "CRU",
        "execution_warrant": "CRUG",
        "users": "CRUG",
        "jobs": "CRU",
        "namespace": "CRUG",
        "workflow_policy": "CRUAG",
    },
    "feature_designer": {
        "feature": "CRU",
        "feature_pin": "Q",
        "featureset": "CRU",
        "model": _R,
        "artifact": "",
        "specdoc": "",
        "jobs": "R",
    },
    "feature_manager": {
        "feature": "RA",
        "feature_pin": "AP",
        "featureset": "RAP",
        "model": _R,
        "artifact": _R,
        "specdoc": _R,
        "training_warrant": _R,
        "jobs": "R",
    },
    "model_designer": {
        "feature": _R,
        "featureset": _R,
        "model": "CRU",
        "artifact": "CRU",
        "specdoc": "CRU",
        "training_warrant": _R,
        "parameter_set": _R,
        "execution_warrant": _R,
        "jobs": "R",
    },
    "model_developer": {
        "feature": _R,
        "feature_pin": "Q",
        "featureset": "CRU",
        "model": _R,
        "artifact": "RU",
        "specdoc": "RU",
        "training_warrant": "CRU",
        "parameter_set": "CRU",
        "execution_warrant": _R,
        "jobs": "R",
    },
    "model_manager": {
        "feature": _R,
        "featureset": _R,
        "model": "RA",
        "artifact": "RA",
        "specdoc": "RA",
        "training_warrant": "RAP",
        "parameter_set": "RA",
        "execution_warrant": "CRUAP",
        "jobs": "R",
    },
    # The owner is accountable for a model's use, and both §10.2's example policy and the
    # shipped execution-warrant policy ask the owner to approve in a production namespace.
    # Without 'A' here that approval could never be given, so a production namespace could
    # not approve an execution warrant at all. 'A' on the model and on its execution
    # warrant, not on training or parameters, which stay the manager's.
    "model_owner": {
        "feature": _R,
        "featureset": _R,
        "model": "RAG",
        "artifact": _R,
        "specdoc": _R,
        "training_warrant": "RG",
        "parameter_set": _R,
        "execution_warrant": "RAG",
        "jobs": "R",
    },
    "techops": {
        "feature": _R,
        "feature_pin": _R,
        "featureset": _R,
        "model": _R,
        "artifact": _R,
        "specdoc": _R,
        "training_warrant": _R,
        "parameter_set": _R,
        "execution_warrant": _R,
        "users": _R,
        "jobs": "CRU",
    },
}

DESCRIPTIONS = {
    "admin": "Users, roles, SSO, system settings, storage, workflow policy",
    "feature_designer": "Feature definitions, schemas, resolution rules, sources",
    "feature_manager": "Approval of features and feature sets, pin authorization",
    "model_designer": "Model definitions, formula, Python artifact, LaTeX specification",
    "model_developer": "Training warrants, parameter upload, experiment iteration",
    "model_manager": "Approval of models, warrants and parameter sets",
    "model_owner": "Access policy for a model and its lineage; accountable for its use",
    "techops": "Runtime health, job queues, retries, storage compaction, backups",
}

# Namespace presets (§28.9): which roles a namespace expects, and its SoD level.
PRESETS = {
    # Even a small team needs someone who can approve a feature and a model, so the
    # preset staffs both managers; its SoD is "none", so one person may hold several roles.
    "small_team": {
        "roles": ["admin", "feature_designer", "feature_manager", "model_manager"],
        "sod": "none",
    },
    # A standard namespace staffs the whole review chain — including the model owner, whom
    # the shipped execution-warrant policy asks to sign off in production — and techops,
    # who run it. The list is also what `namespace_read` means: these are its people (§11.1).
    "standard": {
        "roles": [
            "admin",
            "feature_designer",
            "feature_manager",
            "model_designer",
            "model_developer",
            "model_manager",
            "model_owner",
            "techops",
        ],
        "sod": "two_person",
    },
    "regulated": {"roles": list(MATRIX), "sod": "strict"},
}
