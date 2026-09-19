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
VERSION = "0.3.0"
BUILD_DATE = "2026-09-19"
API_VERSION = "v1"

# Per-release highlights, newest first. Rendered on the About page.
HIGHLIGHTS = {
    "0.3.0": [
        "Single sign-on tested against a real identity provider, Keycloak 26.4: OIDC and "
        "SAML sign-in, single logout in both directions",
        "Feature-set pin materialization per namespace: always, on_demand or never, "
        "every mode sealed by the same hash",
        "A signed-in session's principal reused for two seconds; access changes apply "
        "at once in the same process",
        "OIDC logout both ways: sign-out at the IdP, and back-channel logout tokens",
        "Custody timestamps: the TSA's signature verified against its CA inside MAYA",
        "The specification's PDF and DOCX rebuilt from the Markdown by a script",
    ],
    "0.2.0": [
        "Top navigation with mega-menus; a card-based help centre with four tutorials and "
        "thirteen full-reference guides",
        "Spreadsheet import: an Excel formula graph lifted into the IR, checked cell by cell "
        "against the workbook's own results and against LibreOffice Calc",
        "The python source driver: a reviewed producer function run in the sandbox on each pull",
        "SAML 2.0 sign-in with signed requests and single logout; WebAuthn security keys",
        "Catalog search on an inverted index: ranked, prefix-matched, permission-filtered",
        "True LaTeX builds with Tectonic; SDK record/replay (sync and async) and "
        "maya.offline(bundle)",
        "Server-side cursor paging; the assistant as a recorded challenger on every review",
        "maya_delta compaction and vacuum on both backends, run daily over every lake table",
        "Composite models re-executed in evidence bundles; offline execution labelled unattested",
        "Several web processes on one node over PostgreSQL, spread evenly by SO_REUSEPORT",
        "Measured: SC-4, SC-5 and 100k-object search pass; SC-3 close (docs/BENCHMARKS.md)",
    ],
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
    ],
}
