"""
MAYA version — the single authority.

Every banner, template, API document and bundle reads these constants at
runtime. A version string written anywhere else is a copy that will rot, and
``tools/ci/version_single_source.py`` fails the build when one appears.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

APP_NAME = "MAYA"
APP_TAGLINE = "Model & AI Lifecycle Assurance"
APP_SLOGAN = "Evidence, not assertion."
VERSION = "0.1.0"
BUILD_DATE = "2026-09-19"
API_VERSION = "v1"

# Per-release highlights, newest first. Rendered on the About page.
HIGHLIGHTS = {
    "0.1.0": [
        "First end-to-end build from specification revision 2.1",
        "Bitemporal features with content-addressed, fragment-shared pins",
        "maya_delta with native (delta-rs) and pure-Python backends",
        "Feature sets with cascade pin, policy precedence, tabular and wide downloads",
        "Formula IR, spec documents, parameter sets, training and execution warrants",
        "Configurable workflow with segregation of duties and break-glass",
        "SQLite and PostgreSQL from two generated schema files, no migrations",
        "OIDC single sign-on, TOTP two-factor codes, and a verified strong sandbox on Linux",
        "Grant conditions: row filters, column masks and time bounds",
        "Workspaces with shadow replay; read-only SQL sources into the bitemporal log",
        "Prometheus metrics, W3C tracing, a durable event stream and signed webhooks",
        "Delegation and SLA escalation, run by a maintenance scheduler",
        "Licence algebra and tamper-evident custody anchoring of the audit chain",
        "Top navigation with mega-menus, and a card-based help system with worked examples",
        "Spreadsheet import: an Excel formula graph lifted into the IR, checked cell by cell "
        "against the workbook's own results",
    ],
}
