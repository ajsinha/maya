"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a document can be *about*.

Documentation does not arrive all at once about one thing. It arrives at
different moments, about different objects, and until now everything was filed
against a model or a version — so two of the five cases had nowhere to go.

| When | About | Example |
|---|---|---|
| before anything runs | the **model** | the methodology paper, the literature the approach comes from |
| a version is created | the **version** | the specification of that kernel |
| a fit warrant executes | the **parameter set** | the convergence study, the training note |
| a featureset is filled | the **featureset version** | the data dictionary, the source-system agreement |
| validation concludes | the **validation** | the independent recode, the challenger comparison |

The third and fourth are the ones that were unfilable, and they are the two that
matter most in practice. A calibrated model produces a parameter set every
morning; the note explaining the one morning it went wrong had nowhere to live.
And a featureset's documentation is read by every model fitted from it, so
filing it against one of them makes it invisible to the rest.

**A subject is always pinned.** `featureset_version`, not `featureset`. A
document filed against the *set* would describe something that has since moved,
which is finding C-2 wearing documentation's clothes — and it is the failure
this vocabulary exists to prevent rather than a detail of how it is stored.
"""
from __future__ import annotations

from typing import Dict, Tuple

MODEL = "model"
MODEL_VERSION = "model_version"
PARAMETER_SET = "parameter_set"
FEATURESET_VERSION = "featureset_version"
FEATURE = "feature"
VALIDATION = "validation"

SUBJECTS: Tuple[str, ...] = (MODEL, MODEL_VERSION, PARAMETER_SET,
                             FEATURESET_VERSION, FEATURE, VALIDATION)

SUBJECT_MEANING: Dict[str, str] = {
    MODEL: "the model itself — methodology, literature, board papers; things "
           "true of every version",
    MODEL_VERSION: "one immutable kernel — its specification, its validation "
                   "report",
    PARAMETER_SET: "one point of P — the convergence study, the note explaining "
                   "the morning a calibration went wrong",
    FEATURESET_VERSION: "one filled schema — the data dictionary, the "
                        "source-system agreement. Pinned to the version, never "
                        "to the set, because a document about the set describes "
                        "something that has since moved",
    FEATURE: "one governed signal — its business definition, the argument for "
             "how it is computed",
    VALIDATION: "one episode — the independent recode, the challenger "
                "comparison, the reviewer's working",
}

#: Subjects that are **pinned by construction**: naming one names a fixed thing
#: whose contents cannot change underneath the document. The others are pinned
#: because the platform makes them immutable once they are in force.
IMMUTABLE: Tuple[str, ...] = (MODEL_VERSION, PARAMETER_SET, FEATURESET_VERSION)


def known(subject_type: str) -> bool:
    return subject_type in SUBJECTS


def describe() -> Dict[str, object]:
    """Published rather than documented, so a client need not carry a copy."""
    return {"subjects": [{"subject": s, "means": SUBJECT_MEANING[s],
                          "pinned": s in IMMUTABLE} for s in SUBJECTS],
            "detail": "a document is filed against what it is ABOUT; a subject "
                      "that is pinned cannot move underneath the document that "
                      "describes it"}
