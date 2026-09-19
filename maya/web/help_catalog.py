"""
The help catalog: the single source of truth for the Help pages.

The index renders searchable, collapsible category tiles straight from here, and
every topic page takes its title, icon, summary and "more in this category"
links from here, so a topic is declared exactly once. A topic's body lives in
``templates/help/topics/<slug>.html``; ``tests/test_web.py`` fails when a
declared topic has no template or a template has no declaration.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

CATEGORIES: list[dict[str, Any]] = [
    {"id": "start", "name": "Getting started", "icon": "flag",
     "blurb": "Install MAYA, sign in, and govern your first feature in minutes.",
     "topics": [
         {"slug": "getting-started", "title": "Getting started", "icon": "flag",
          "summary": "Install, run, sign in, and take one CSV all the way to an approved, "
                     "pinned feature.", "badge": "Start here"},
         {"slug": "tour", "title": "A tour of the screens", "icon": "compass",
          "summary": "What lives under each menu, the five-tab object page, and the table "
                     "every list uses."},
         {"slug": "glossary", "title": "Glossary", "icon": "journal-bookmark",
          "summary": "Definition, version, pin, knowledge time, warrant, covenant — every "
                     "term in one place."},
     ]},
    {"id": "features", "name": "Features and data", "icon": "boxes",
     "blurb": "How a number is defined, ingested, resolved and frozen.",
     "topics": [
         {"slug": "features", "title": "Features and the designer", "icon": "pencil-square",
          "summary": "Index, schema, source, resolution rules and quality contracts — and "
                     "what submitting does."},
         {"slug": "ingest", "title": "Ingesting data", "icon": "cloud-upload",
          "summary": "CSV, Parquet, JSON, SQL and Delta sources; restatements append, they "
                     "never overwrite."},
         {"slug": "bitemporal", "title": "Bitemporality and as-of", "icon": "clock-history",
          "summary": "Event time versus knowledge time, and how to ask what you knew on a "
                     "given day."},
         {"slug": "pins", "title": "Pins and content addressing", "icon": "pin-angle",
          "summary": "Materialize a version into sealed, hashed, fragment-shared data you "
                     "can cite for years."},
         {"slug": "algebra", "title": "Derived features: the algebra", "icon": "diagram-3",
          "summary": "Union, compose, coalesce, project, transform and more over other "
                     "features, type-checked at submit."},
         {"slug": "featuresets", "title": "Feature sets", "icon": "grid-3x3-gap",
          "summary": "Map feature attributes to model inputs, pin them together, and "
                     "download them tabular or wide."},
     ]},
    {"id": "models", "name": "Models and warrants", "icon": "calculator",
     "blurb": "A model's mathematics, its code, and the instruments that license it.",
     "topics": [
         {"slug": "models", "title": "Models and the formula IR", "icon": "calculator",
          "summary": "Author a model in LaTeX or Python, or lift it from an Excel "
                     "workbook; MAYA derives the typed expression tree everything uses."},
         {"slug": "conformance", "title": "Specifications and conformance", "icon": "file-earmark-check",
          "summary": "The spec document, the uploaded artifact, and the differential test "
                     "that holds them to each other."},
         {"slug": "training-warrants", "title": "Training warrants", "icon": "mortarboard",
          "summary": "Freeze a model against a feature-set pin, with a signed leakage "
                     "certificate and checksummed downloads."},
         {"slug": "execution-warrants", "title": "Execution warrants and covenants", "icon": "play-circle",
          "summary": "A live licence to run: short-lived tokens, covenants that suspend on "
                     "breach, revocation that fails closed."},
         {"slug": "bundles", "title": "Reproducibility bundles", "icon": "box-seam",
          "summary": "A signed archive that verifies offline and re-executes the model "
                     "where it can."},
     ]},
    {"id": "governance", "name": "Governance", "icon": "shield-check",
     "blurb": "Who may change what, who must agree, and the evidence that they did.",
     "topics": [
         {"slug": "workflow", "title": "Workflow and policies", "icon": "diagram-2",
          "summary": "One state machine, policies as data, checks that block by name, and "
                     "separation of duties."},
         {"slug": "delegation", "title": "Delegation and escalation", "icon": "person-badge",
          "summary": "Hand your approvals to a stand-in for a window; overdue reviews "
                     "escalate on their own."},
         {"slug": "access", "title": "Access, grants and conditions", "icon": "key",
          "summary": "Roles set the ceiling, grants open objects, and conditions filter "
                     "rows, mask columns or expire."},
         {"slug": "licences", "title": "Data licences", "icon": "file-earmark-lock",
          "summary": "Vendor terms that follow the data through the algebra, enforced at "
                     "every exit.", "badge": "New"},
         {"slug": "workspaces", "title": "Workspaces and shadow replay", "icon": "bezier2",
          "summary": "Stage a change, replay its numeric impact on everything downstream, "
                     "then merge on approval."},
         {"slug": "audit", "title": "Audit and custody", "icon": "journal-text",
          "summary": "A hash-chained log, and anchors outside the database that catch a "
                     "rewritten history.", "badge": "New"},
     ]},
    {"id": "platform", "name": "Platform and integration", "icon": "hdd-stack",
     "blurb": "Scripting MAYA, wiring it to your systems, and running it in production.",
     "topics": [
         {"slug": "sdk", "title": "The Python SDK and REST API", "icon": "code-square",
          "summary": "Everything the UI does, a script can do: sessions, API keys, and "
                     "worked examples."},
         {"slug": "sources", "title": "SQL and Python sources", "icon": "server",
          "summary": "Reviewed read-only queries and sandboxed producer functions, pulled "
                     "into the bitemporal log on demand."},
         {"slug": "events", "title": "Events and webhooks", "icon": "broadcast-pin",
          "summary": "A durable ordered event stream, server-sent events, and HMAC-signed "
                     "webhooks with retries."},
         {"slug": "observability", "title": "Metrics and tracing", "icon": "activity",
          "summary": "Prometheus metrics, W3C trace context end to end, and optional "
                     "OpenTelemetry export."},
         {"slug": "security", "title": "Sign-in and security", "icon": "shield-lock",
          "summary": "Passwords, OIDC single sign-on, two-factor codes, API keys, and the "
                     "code sandbox."},
         {"slug": "operations", "title": "Configuration and databases", "icon": "sliders",
          "summary": "application.yaml, switching SQLite and PostgreSQL, estate export and "
                     "import, and the gates."},
     ]},
]


def all_topics() -> list[dict[str, Any]]:
    return [dict(t, category=c["name"], category_id=c["id"])
            for c in CATEGORIES for t in c["topics"]]


def find(slug: str) -> dict[str, Any] | None:
    for c in CATEGORIES:
        for i, t in enumerate(c["topics"]):
            if t["slug"] == slug:
                siblings = [s for s in c["topics"] if s["slug"] != slug]
                ordered = all_topics()
                pos = next(n for n, o in enumerate(ordered) if o["slug"] == slug)
                return {**t, "category": c["name"], "category_id": c["id"],
                        "category_icon": c["icon"], "siblings": siblings,
                        "prev": ordered[pos - 1] if pos > 0 else None,
                        "next": ordered[pos + 1] if pos + 1 < len(ordered) else None}
    return None


# -- full references and tutorials (Markdown in maya/web/guides/<slug>.md) --------------
# Topic pages explain and show; a guide is the complete reference or a step-by-step
# tutorial, rendered from Markdown when opened. A topic names its companion guide, and
# its footer links to it as "Full reference".
GUIDES: list[dict[str, Any]] = [
    {"slug": "tutorial-01-first-feature", "kind": "tutorial", "icon": "flag",
     "title": "Tutorial 1 — Your first governed feature",
     "summary": "From one CSV to an approved, pinned, downloadable feature, with every "
                "command and screen."},
    {"slug": "tutorial-02-featureset-and-model", "kind": "tutorial", "icon": "grid-3x3-gap",
     "title": "Tutorial 2 — A feature set and a model",
     "summary": "Map features into a panel, write a model in LaTeX, complete its "
                "specification and take it through review."},
    {"slug": "tutorial-03-warrants-and-bundles", "kind": "tutorial", "icon": "mortarboard",
     "title": "Tutorial 3 — Warrants, parameters and a bundle",
     "summary": "Train under a warrant, upload parameters, issue an execution warrant, "
                "export a bundle and verify it offline."},
    {"slug": "tutorial-04-governed-change", "kind": "tutorial", "icon": "bezier2",
     "title": "Tutorial 4 — A governed change",
     "summary": "Stage a change in a workspace, replay its impact, answer the challenger "
                "and merge on approval."},
    {"slug": "features-reference", "kind": "reference", "icon": "pencil-square",
     "title": "Feature definition reference",
     "summary": "Every key of a feature definition: index, types, sources, resolution "
                "rules, calendars, transforms, quality checks, licences, extends."},
    {"slug": "algebra-reference", "kind": "reference", "icon": "diagram-3",
     "title": "Feature algebra reference",
     "summary": "Every operator with its typing rules, options, examples and what it "
                "does to causality."},
    {"slug": "featuresets-reference", "kind": "reference", "icon": "grid-3x3-gap",
     "title": "Feature set reference",
     "summary": "Members, alignment, policy inheritance, cascade pins, shapes and "
                "downloads."},
    {"slug": "data-and-lake-guide", "kind": "reference", "icon": "hdd-stack",
     "title": "Data, pins and the lake",
     "summary": "The bitemporal ingest log, content hashing, fragments, the two Delta "
                "backends, compaction and vacuum."},
    {"slug": "models-reference", "kind": "reference", "icon": "calculator",
     "title": "Models and the formula IR reference",
     "summary": "Formula syntax, IR nodes and operations, roles, black boxes, composites, "
                "specification documents, artifacts, conformance, spreadsheet lifting."},
    {"slug": "warrants-reference", "kind": "reference", "icon": "file-earmark-lock",
     "title": "Warrants and bundles reference",
     "summary": "Training and execution warrant specifications, leakage certificates, "
                "parameter sets, covenants, limits, tokens, bundles and offline use."},
    {"slug": "workflow-reference", "kind": "reference", "icon": "diagram-2",
     "title": "Workflow and policy reference",
     "summary": "States, transitions, the policy schema, every check, separation of "
                "duties, break-glass, delegation, escalation and the challenger."},
    {"slug": "access-reference", "kind": "reference", "icon": "key",
     "title": "Roles, access and licences reference",
     "summary": "Roles and capabilities, presets, grants and conditions, API keys, and "
                "how licence terms combine."},
    {"slug": "sdk-cli-reference", "kind": "reference", "icon": "code-square",
     "title": "Python SDK and CLI reference",
     "summary": "Every SDK resource and method, errors, client modes, record/replay, "
                "offline bundles, and every CLI command."},
    {"slug": "api-guide", "kind": "reference", "icon": "braces",
     "title": "REST API guide",
     "summary": "Authentication, conventions, errors, paging, idempotency and the "
                "endpoints by area."},
    {"slug": "configuration-reference", "kind": "reference", "icon": "sliders",
     "title": "Configuration reference",
     "summary": "Every key in application.yaml: its default, what it controls, and how to "
                "override it."},
    {"slug": "operations-guide", "kind": "reference", "icon": "tools",
     "title": "Operations and administration guide",
     "summary": "Install, run, switch databases, back up, export and import the estate, "
                "maintain the lake, anchor custody, monitor."},
    {"slug": "security-guide", "kind": "reference", "icon": "shield-lock",
     "title": "Security guide",
     "summary": "Sign-in modes, OIDC and SAML, two-factor codes and security keys, "
                "sessions, the sandbox, secrets and the audit trail."},
]

# topic slug -> the guide that is its full reference
COMPANIONS: dict[str, str] = {
    "getting-started": "tutorial-01-first-feature", "features": "features-reference",
    "ingest": "features-reference", "bitemporal": "data-and-lake-guide",
    "pins": "data-and-lake-guide", "algebra": "algebra-reference",
    "featuresets": "featuresets-reference", "models": "models-reference",
    "conformance": "models-reference", "training-warrants": "warrants-reference",
    "execution-warrants": "warrants-reference", "bundles": "warrants-reference",
    "workflow": "workflow-reference", "delegation": "workflow-reference",
    "access": "access-reference", "licences": "access-reference",
    "workspaces": "tutorial-04-governed-change", "audit": "operations-guide",
    "sdk": "sdk-cli-reference", "sources": "features-reference",
    "events": "operations-guide", "observability": "operations-guide",
    "security": "security-guide", "operations": "operations-guide",
    "tour": "tutorial-01-first-feature", "glossary": "features-reference",
}


def find_guide(slug: str) -> dict[str, Any] | None:
    for i, g in enumerate(GUIDES):
        if g["slug"] == slug:
            same = [x for x in GUIDES if x["kind"] == g["kind"]]
            pos = same.index(g)
            return {**g, "prev": same[pos - 1] if pos > 0 else None,
                    "next": same[pos + 1] if pos + 1 < len(same) else None,
                    "topics": [t for t in all_topics() if COMPANIONS.get(t["slug"]) == slug]}
    return None


def companion(topic_slug: str) -> dict[str, Any] | None:
    slug = COMPANIONS.get(topic_slug)
    return next((g for g in GUIDES if g["slug"] == slug), None) if slug else None
