"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The risk lattices.

Materiality and complexity are separate orders, never collapsed into one
score: materiality joins a quantitative exposure band with a qualitative
purpose class; complexity is a meet over its declared components.
"""
RULESET_VERSION = "2026.09.1"

MATERIALITY = ["negligible", "low", "moderate", "material", "critical"]
COMPLEXITY = ["simple", "moderate", "complex", "advanced"]
CONTROLS = {
    1: ["independent_validation", "annual_review", "monthly_monitoring",
        "committee_approval", "full_documentation", "reproducibility_proof"],
    2: ["independent_validation", "biennial_review", "quarterly_monitoring",
        "delegated_approval", "full_documentation"],
    3: ["peer_review", "triennial_review", "semiannual_monitoring", "owner_approval"],
    4: ["identification", "condition_monitoring"],
}
# Complexity factors that raise the assessment for advanced techniques
_OPAQUE_CLASSES = {"T3", "T4", "T5", "T6"}
