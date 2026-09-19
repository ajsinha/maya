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
