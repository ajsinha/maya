"""
The help catalog: the single source of truth for the Help pages.

Help is organised by **subject**: one page per thing a person wants to understand. A
subject page opens with the short, worked explanation (its *parts*, in
``templates/help/parts/<slug>.html``) and continues with the complete reference (its
*guide*, Markdown in ``maya/web/guides/<slug>.md``), so the overview and the detail of one
subject are never two cards that half repeat each other.

Tutorials and the two catalogue-style references (the REST API and configuration) are
pages of their own in the library at ``/help/guides``. Every older address -- a topic
page, or a reference that is now part of a subject -- redirects to where its content
went (``LEGACY``), so no link breaks.

``tests/test_web.py`` fails when a part is declared without a template, a template is
not declared, or a subject names a guide that does not exist.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

# slug -> the subject: its card, the parts that open it (slug, heading) and its reference.
SUBJECTS: dict[str, dict[str, Any]] = {
    "getting-started": {
        "title": "Getting started",
        "icon": "flag",
        "badge": "Start here",
        "summary": "Install, run and sign in; take one CSV to an approved, pinned feature; "
        "and find your way around the screens.",
        "parts": [
            ("getting-started", "Your first governed feature"),
            ("tour", "A tour of the screens"),
        ],
        "guide": None,
    },
    "glossary": {
        "title": "Glossary",
        "icon": "journal-bookmark",
        "summary": "Definition, version, pin, knowledge time, warrant, covenant — every term "
        "in one place.",
        "parts": [("glossary", "")],
        "guide": None,
    },
    "features": {
        "title": "Features",
        "icon": "pencil-square",
        "summary": "Defining a feature, getting data into it from files, SQL or Python, and "
        "every key of a definition.",
        "parts": [
            ("features", "Features and the designer"),
            ("ingest", "Ingesting data"),
            ("sources", "SQL and Python sources"),
        ],
        "guide": "features-reference",
    },
    "algebra": {
        "title": "Derived features",
        "icon": "diagram-3",
        "summary": "Build a feature from others with the algebra: every operator, its typing "
        "rules and what it does to causality.",
        "parts": [("algebra", "")],
        "guide": "algebra-reference",
    },
    "data": {
        "title": "Time, pins and the lake",
        "icon": "hdd-stack",
        "summary": "Two clocks and as-of reads, pins frozen by content, and how the lake "
        "stores, compacts and verifies them.",
        "parts": [
            ("bitemporal", "Bitemporality and as-of"),
            ("pins", "Pins and content addressing"),
        ],
        "guide": "data-and-lake-guide",
    },
    "featuresets": {
        "title": "Feature sets",
        "icon": "grid-3x3-gap",
        "summary": "Members, alignment, policy inheritance, cascade pins, shapes and downloads.",
        "parts": [("featuresets", "")],
        "guide": "featuresets-reference",
    },
    "models": {
        "title": "Models and specifications",
        "icon": "calculator",
        "summary": "Formulas and the IR, black boxes and composites, the specification "
        "document, artifacts and conformance.",
        "parts": [
            ("models", "Models and the formula IR"),
            ("conformance", "Specifications and conformance"),
        ],
        "guide": "models-reference",
    },
    "designers": {
        "title": "What each designer expects",
        "icon": "lightbulb",
        "summary": "The rules behind every authoring screen: a model's Python function and "
        "artifact, features, feature sets, and both warrants.",
        "parts": [],
        "guide": "authoring-reference",
    },
    "warrants": {
        "title": "Warrants and bundles",
        "icon": "file-earmark-lock",
        "summary": "Training warrants and parameters, execution warrants and covenants, and "
        "the signed bundle anyone can verify without MAYA.",
        "parts": [
            ("training-warrants", "Training warrants"),
            ("execution-warrants", "Execution warrants and covenants"),
            ("bundles", "Reproducibility bundles"),
        ],
        "guide": "warrants-reference",
    },
    "model-risk": {
        "title": "Model risk governance",
        "icon": "clipboard2-pulse",
        "summary": "Tiering and the inventory, periodic review, findings, monitoring, "
        "challengers, batch scoring and restatement alerts.",
        "parts": [],
        "guide": "model-risk-reference",
    },
    "documents": {
        "title": "Model documents and the AI gateway",
        "icon": "file-earmark-richtext",
        "summary": "Model cards, validation reports and documentation from templates; model "
        "profiles and providers; the assistant's challenger.",
        "parts": [],
        "guide": "documents-and-ai-reference",
    },
    "llm-apps": {
        "title": "LLM applications",
        "icon": "chat-square-text",
        "summary": "Govern an application built on a language model: versions, evaluation "
        "sets, recorded and live runs, approval.",
        "parts": [],
        "guide": "llm-apps-reference",
    },
    "workflow": {
        "title": "Workflow, delegation and policies",
        "icon": "diagram-2",
        "summary": "States and transitions, the policy for each namespace, separation of "
        "duties, break-glass, delegation and escalation.",
        "parts": [
            ("workflow", "Workflow and policies"),
            ("delegation", "Delegation and escalation"),
        ],
        "guide": "workflow-reference",
    },
    "access": {
        "title": "Access and licences",
        "icon": "key",
        "summary": "Roles and capabilities, grants and conditions, API keys, and the data "
        "licences that travel with every read and export.",
        "parts": [
            ("access", "Access, grants and conditions"),
            ("licences", "Data licences"),
        ],
        "guide": "access-reference",
    },
    "workspaces": {
        "title": "Workspaces and shadow replay",
        "icon": "bezier2",
        "summary": "Stage a change, replay what it would have done, and merge it on approval.",
        "parts": [("workspaces", "")],
        "guide": None,
    },
    "security": {
        "title": "Security, audit and custody",
        "icon": "shield-lock",
        "summary": "Sign-in and SSO, two-factor and security keys, sessions, the sandbox, "
        "the hash-chained audit log and chain of custody.",
        "parts": [
            ("security", "Sign-in and security"),
            ("audit", "Audit and custody"),
        ],
        "guide": "security-guide",
    },
    "sdk": {
        "title": "Python SDK and CLI",
        "icon": "code-square",
        "summary": "Every SDK resource and method, errors, client modes, record and replay, "
        "offline bundles, and every CLI command.",
        "parts": [("sdk", "")],
        "guide": "sdk-cli-reference",
    },
    "integrations": {
        "title": "Events and integrations",
        "icon": "plug",
        "summary": "The event stream and signed webhooks, and MAYA's integrations with "
        "other platforms.",
        "parts": [("events", "Events and webhooks")],
        "guide": "integrations-reference",
    },
    "operations": {
        "title": "Operations and monitoring",
        "icon": "tools",
        "summary": "Install and run, databases, backups, the estate, the lake, metrics, "
        "alerts, dashboards, tracing and logs.",
        "parts": [
            ("operations", "Configuration and databases"),
            ("observability", "Metrics and tracing"),
        ],
        "guide": "operations-guide",
    },
}

CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "start",
        "name": "Start here",
        "icon": "flag",
        "blurb": "Install MAYA, govern your first feature, and learn the words.",
        "subjects": ["getting-started", "glossary"],
    },
    {
        "id": "data",
        "name": "Features and data",
        "icon": "boxes",
        "blurb": "How a number is defined, ingested, derived, resolved and frozen.",
        "subjects": ["features", "algebra", "data", "featuresets"],
    },
    {
        "id": "models",
        "name": "Models and warrants",
        "icon": "calculator",
        "blurb": "Models and their specifications, the warrants that license them, the "
        "documents about them, and LLM applications.",
        "subjects": ["models", "designers", "warrants", "documents", "llm-apps"],
    },
    {
        "id": "governance",
        "name": "Governance",
        "icon": "shield-check",
        "blurb": "Who may do what, who must approve it, what is watched after, and the "
        "record of all of it.",
        "subjects": ["model-risk", "workflow", "access", "workspaces", "security"],
    },
    {
        "id": "integrate",
        "name": "Integrate and operate",
        "icon": "plug",
        "blurb": "Reach MAYA from code and other systems, and run it.",
        "subjects": ["sdk", "integrations", "operations"],
    },
]

# -- the library: tutorials, and the catalogue-style references -------------------------
GUIDES: list[dict[str, Any]] = [
    {
        "slug": "tutorial-01-first-feature",
        "kind": "tutorial",
        "icon": "flag",
        "title": "Tutorial 1 — Your first governed feature",
        "summary": "From one CSV to an approved, pinned, downloadable feature, with every "
        "command and screen.",
    },
    {
        "slug": "tutorial-02-featureset-and-model",
        "kind": "tutorial",
        "icon": "grid-3x3-gap",
        "title": "Tutorial 2 — A feature set and a model",
        "summary": "Map features into a panel, write a model in LaTeX, complete its "
        "specification and take it through review.",
    },
    {
        "slug": "tutorial-03-warrants-and-bundles",
        "kind": "tutorial",
        "icon": "mortarboard",
        "title": "Tutorial 3 — Warrants, parameters and a bundle",
        "summary": "Train under a warrant, upload parameters, issue an execution warrant, "
        "export a bundle and verify it offline.",
    },
    {
        "slug": "tutorial-04-governed-change",
        "kind": "tutorial",
        "icon": "bezier2",
        "title": "Tutorial 4 — A governed change",
        "summary": "Stage a change in a workspace, replay its impact, answer the challenger "
        "and merge on approval.",
    },
    {
        "slug": "api-guide",
        "kind": "reference",
        "icon": "braces",
        "title": "REST API guide",
        "summary": "Authentication, conventions, errors, paging, idempotency and every "
        "endpoint by area.",
    },
    {
        "slug": "configuration-reference",
        "kind": "reference",
        "icon": "sliders",
        "title": "Configuration reference",
        "summary": "Every key in application.yaml: its default, what it controls, and how to "
        "override it.",
    },
]

# subject -> the page of docs/architecture (or docs/developer) that explains how it is built
INSIDE: dict[str, str] = {
    "getting-started": "architecture",
    "features": "architecture/resolution",
    "algebra": "architecture/resolution",
    "data": "architecture/lake-and-storage",
    "featuresets": "architecture/resolution",
    "models": "architecture/formula",
    "designers": "developer/model-artifacts",
    "warrants": "architecture/warrants-and-custody",
    "model-risk": "architecture/governance",
    "documents": "architecture/ai-and-documents",
    "llm-apps": "architecture/ai-and-documents",
    "workflow": "architecture/workflow",
    "access": "architecture/security",
    "workspaces": "architecture/resolution",
    "security": "architecture/security",
    "sdk": "architecture/sdk",
    "integrations": "architecture/integrations",
    "operations": "architecture/observability",
}

# every address help has ever had -> where that content lives now
LEGACY: dict[str, str] = {
    "tour": "/help/getting-started#tour",
    "ingest": "/help/features#ingest",
    "sources": "/help/features#sources",
    "bitemporal": "/help/data#bitemporal",
    "pins": "/help/data#pins",
    "conformance": "/help/models#conformance",
    "training-warrants": "/help/warrants#training-warrants",
    "execution-warrants": "/help/warrants#execution-warrants",
    "bundles": "/help/warrants#bundles",
    "delegation": "/help/workflow#delegation",
    "licences": "/help/access#licences",
    "audit": "/help/security#audit",
    "events": "/help/integrations#events",
    "observability": "/help/operations#observability",
}
GUIDE_HOME: dict[str, str] = {s["guide"]: slug for slug, s in SUBJECTS.items() if s["guide"]}


def subject(slug: str) -> dict[str, Any] | None:
    """A subject with its category, neighbours and parts, ready for its page."""
    s = SUBJECTS.get(slug)
    if s is None:
        return None
    order = [x for c in CATEGORIES for x in c["subjects"]]
    cat = next(c for c in CATEGORIES if slug in c["subjects"])
    i = order.index(slug)

    def card(x: str) -> dict[str, Any]:
        return {"slug": x, **SUBJECTS[x]}

    return {
        "slug": slug,
        **s,
        "parts": [{"slug": p, "title": t} for p, t in s["parts"]],
        "category": cat["name"],
        "category_id": cat["id"],
        "siblings": [card(x) for x in cat["subjects"] if x != slug],
        "prev": card(order[i - 1]) if i else None,
        "next": card(order[i + 1]) if i + 1 < len(order) else None,
    }


def all_parts() -> list[str]:
    return [p for s in SUBJECTS.values() for p, _ in s["parts"]]


def all_subjects() -> list[dict[str, Any]]:
    return [
        {"slug": x, **SUBJECTS[x], "category": c["name"], "category_id": c["id"]}
        for c in CATEGORIES
        for x in c["subjects"]
    ]


def redirect_for(slug: str) -> str | None:
    """Where an old help address now lives, or None."""
    if slug in LEGACY:
        return LEGACY[slug]
    return None


def guide_redirect(slug: str) -> str | None:
    """A reference that became part of a subject page opens there."""
    home = GUIDE_HOME.get(slug)
    # no fragment of our own: the browser keeps the one the old link carried
    return f"/help/{home}" if home else None


def find_guide(slug: str) -> dict[str, Any] | None:
    for i, g in enumerate(GUIDES):
        if g["slug"] == slug:
            return {
                **g,
                "prev": GUIDES[i - 1] if i else None,
                "next": GUIDES[i + 1] if i + 1 < len(GUIDES) else None,
            }
    return None
