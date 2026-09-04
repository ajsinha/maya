"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Baseline import and compliance debt.

Adversarial review, finding C-5: a platform that shows 1,200 imported models as
1,200 breaches on day one is one the model risk office stops believing within a
month. The answer is not to lower the gates but to be honest about what the
register does not know — explicit, dated, self-closing debt, kept apart from
breach on every view.
"""
from core.baseline import gaps
from core.baseline.common import DEFAULT_EXPIRY_MONTHS, BaselineError
from core.baseline.debt import DebtRegister
from core.baseline.importer import BASELINED, BaselineImporter

__all__ = ["BaselineImporter", "DebtRegister", "BaselineError", "gaps",
           "BASELINED", "DEFAULT_EXPIRY_MONTHS"]
