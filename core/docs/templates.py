"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Which lenses make which document.

A template is an ordered list of lenses and which of them are required. That is
all it is: there is no prose in a template, because prose in a template is prose
that cannot be checked against the model.

The `required` flag is what makes coverage meaningful. A model card is allowed to
omit the monitoring section; a model development document is not, and an Annex IV
pack that omits it is not an Annex IV pack.
"""
from __future__ import annotations

from typing import Dict, Tuple

from core.docs import lenses as L
from core.docs.common import ANNEX_IV, MODEL_CARD, MODEL_DEVELOPMENT, VALIDATION_REPORT
from core.docs.lenses import Lens


def _lens(key, heading, fn, required=True, note="") -> Lens:
    return Lens(key, heading, fn, required, note)


IDENTITY = _lens("identity", "Identity and ownership", L.identity)
CLASSIFICATION = _lens("classification", "Classification", L.classification)
RISK = _lens("risk_tier", "Risk tier and required controls", L.risk_tier)
METHOD = _lens("methodology", "Methodology and interfaces", L.methodology)
ASSUMPTIONS = _lens("assumptions", "Assumptions and limitations", L.assumptions)
DATA = _lens("data_and_features", "Data and features", L.data_and_features)
VALIDATION = _lens("validation", "Validation", L.validation)
FINDINGS = _lens("findings", "Open findings", L.findings)
MONITORING = _lens("monitoring", "Ongoing monitoring", L.monitoring)
LIFECYCLE = _lens("lifecycle", "Approval and attestation", L.lifecycle)
EXECUTION = _lens("execution", "Use and entitlement", L.execution)
PROVENANCE = _lens("provenance", "Provenance", L.provenance)


def optional(lens: Lens) -> Lens:
    return Lens(lens.key, lens.heading, lens.render, False, lens.note)


TEMPLATES: Dict[str, Tuple[Lens, ...]] = {
    MODEL_DEVELOPMENT: (
        IDENTITY, CLASSIFICATION, RISK, METHOD, ASSUMPTIONS, DATA,
        VALIDATION, FINDINGS, MONITORING, LIFECYCLE, EXECUTION, PROVENANCE),

    VALIDATION_REPORT: (
        IDENTITY, CLASSIFICATION, optional(RISK), VALIDATION, FINDINGS,
        optional(DATA), optional(MONITORING), LIFECYCLE, PROVENANCE),

    # Deliberately short. A model card that nobody reads because it is forty
    # pages is not serving the purpose a model card exists for.
    MODEL_CARD: (
        IDENTITY, CLASSIFICATION, ASSUMPTIONS, optional(VALIDATION),
        optional(FINDINGS), optional(MONITORING)),

    ANNEX_IV: (
        IDENTITY, CLASSIFICATION, RISK, METHOD, ASSUMPTIONS, DATA,
        VALIDATION, FINDINGS, MONITORING, LIFECYCLE, EXECUTION, PROVENANCE),
}
