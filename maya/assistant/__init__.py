"""
The assistant as a recorded challenger (§29.8).

It never approves, never blocks and never writes to the object it reviews. It
reads a *dossier* of the version under review and returns a memo of findings;
the memo is stored beside the review, attributed to the provider and model that
wrote it, and the human approver records whether they agreed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

SEVERITIES = ("high", "medium", "low", "info")
CATEGORIES = (
    "look_ahead",
    "unbounded_fill",
    "schema_drift",
    "missing_limitations",
    "doc_ir_inconsistency",
    "data_quality",
    "licence",
    "other",
)
