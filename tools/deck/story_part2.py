"""
The deck, as data. Part 2, the lifecycle end to end; Part 3, the MAYA platform.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

LIFECYCLE: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "2",
        "title": "The lifecycle, end to end",
        "sub": "One chain, from a delivered file to a model running under a live licence and "
        "reporting back. Each link is a governed object, and each refuses something on purpose.",
        "points": [
            "Writing the mathematics",
            "Fitting under a warrant",
            "The holdout",
            "Running under a licence",
            "Evidence that travels",
        ],
    },
    {
        "kind": "shot",
        "title": "Write the mathematics; read back what MAYA made of it",
        "image": "compute-kernel.png",
        "caption": "The compute-kernel designer: LaTeX in, the typed tree and one Python function out",
        "items": [
            ("Write it as you would.", "LaTeX or plain text; say which symbols are the dials."),
            (
                "Read it back.",
                "The tree, each input with its role, the intermediates in order — "
                "or a refusal naming the position.",
            ),
            ("Take the function.", "One self-contained kernel, or the full reference module."),
            (
                "Nothing is created.",
                "It is a place to get the formula right before a version exists to attach it to.",
            ),
            (
                "106 templates",
                "to start from, in ten groups: credit, rates, options, insurance and more.",
            ),
        ],
    },
    {
        "kind": "numbered",
        "title": "The checksum cycle that turns paperwork into a control",
        "items": [
            (
                "Draw",
                "An approved model against a pinned feature set; the input contract is "
                "checked and every miss named.",
            ),
            (
                "Certify",
                "A signed leakage certificate is issued with the warrant, or the warrant "
                "is refused.",
            ),
            (
                "Download",
                "Train and validation rows only; who, when and the content hash are recorded.",
            ),
            (
                "Upload",
                "Parameters checked against that hash, their bounds and any joint constraint.",
            ),
            ("Seal", "Approved by policy; every object it references becomes undeletable."),
        ],
        "head_w": 0.16,
        "insight": "Parameters fitted on data matching no checksum MAYA issued are flagged and "
        "cannot be approved without a written justification — so a judgement is recorded "
        "honestly instead of being disguised as a fit.",
    },
    {
        "kind": "split",
        "title": "The leakage certificate, and the holdout nobody sees",
        "left": {
            "head": "Leakage certificate",
            "items": [
                (
                    "The rule",
                    "Every row's knowledge time is at or before its event date plus the "
                    "declared lag.",
                ),
                ("Three verdicts", "Certified; certified with justified exceptions; refused."),
                (
                    "Specific",
                    "Rows examined, violations with example rows, every exception's "
                    "reason — signed.",
                ),
            ],
        },
        "right": {
            "head": "Escrowed holdout",
            "items": [
                (
                    "Fixed at drawing",
                    "The test rows are hashed and counted when the warrant is drawn.",
                ),
                ("Scored by MAYA", "The developer never receives them; MAYA returns metrics only."),
                ("Every attempt numbered", "“Scored forty times, best reported” becomes visible."),
            ],
        },
    },
    {
        "kind": "shot",
        "title": "An execution warrant is a live licence",
        "image": "execution-warrant.png",
        "caption": "An execution warrant: what may run, where, until when, and how it has run",
        "items": [
            ("Environments", "dev, uat, prod — each permitted explicitly."),
            (
                "Covenants",
                "Null rate, input range, population stability, output range, rows per "
                "day, staleness. A breach suspends the warrant at once.",
            ),
            ("Drift", "Population stability against a baseline fixed when the warrant was drawn."),
            (
                "Restated data",
                "Corrections under its training pin, and how far they move the model.",
            ),
            (
                "Fails closed",
                "A revoked, expired or suspended warrant refuses every call and says "
                "whom to contact.",
            ),
        ],
    },
    {
        "kind": "split",
        "title": "A bundle that proves itself on a machine with no MAYA",
        "left": {
            "head": "In the archive",
            "items": [
                (
                    "The subject",
                    "Warrant, model, mathematics, specification, code, parameters, "
                    "leakage certificate, training frame and pins.",
                ),
                (
                    "The definition of the hash",
                    "MAYA's canonical encoder ships inside, so the "
                    "hash is recomputed, not described.",
                ),
                ("A signed manifest", "Every file's digest and the expected output hash."),
            ],
        },
        "right": {
            "head": "What the verifier does",
            "items": [
                ("Needs only Python, pyarrow, numpy", "No MAYA, no network."),
                ("Bounds the archive first", "Size, entry count, compression ratio, paths."),
                ("Recomputes, then re-executes", "Digests, signature, content hash, outputs."),
                ("Refuses on one changed byte", "Before anything is read."),
            ],
        },
    },
]

PLATFORM: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "3",
        "title": "The MAYA platform",
        "sub": "One platform reached four ways, governed by roles, deployable on a laptop or a "
        "team server, and measured rather than promised.",
        "points": [
            "Overview",
            "The web UI",
            "Two teams, one contract",
            "Access and security",
            "Deployment",
            "Measured",
        ],
    },
    {
        "kind": "numbered",
        "title": "MAYA 1.0.0 — overview",
        "items": [
            (
                "Production-grade Python",
                "FastAPI on Python 3.13; one process by default, "
                "several web processes and job workers on PostgreSQL.",
            ),
            (
                "Four surfaces, one contract",
                "Web UI, REST API with 268 endpoints, Python SDK, "
                "command line — every endpoint has an SDK method.",
            ),
            (
                "The whole lifecycle",
                "Features, pins, models, warrants, findings, tiers, reviews, "
                "monitoring, challengers, inventory.",
            ),
            (
                "Every kind of model",
                "Formulas, spreadsheets, composites, black boxes, imports from "
                "MLflow and SageMaker, LLM applications.",
            ),
            (
                "Held by gates",
                "17 static gates plus test, fallback, security and benchmark stages, "
                "on every commit.",
            ),
        ],
        "head_w": 0.27,
    },
    {
        "kind": "cards",
        "title": "Why MAYA — what makes it different",
        "cols": 3,
        "card_h": 2.35,
        "cards": [
            (
                "DEFINITIONS ARE CODE",
                "Data is a consequence",
                "MAYA stores how a number is produced and materialises values only when asked.",
            ),
            (
                "A CLOSED ALGEBRA",
                "Derived objects are ordinary",
                "union, intersect, compose, "
                "coalesce, extend, project, aggregate — each yields a definition.",
            ),
            (
                "MATHEMATICS AS DATA",
                "A typed expression tree",
                "Type-checked, rendered, diffed by "
                "meaning, and the yardstick code is tested against.",
            ),
            (
                "TWO CLOCKS",
                "From the first table",
                "A restatement is a new row, so a backtest "
                "cannot silently consume restated values.",
            ),
            (
                "EVIDENCE TRAVELS",
                "Hashes over canonical values",
                "Two pins of the same data hash the same across engine versions.",
            ),
            (
                "LICENCES, NOT MEMOS",
                "Warrants that act",
                "They expire, revoke, suspend on a breach and verify offline.",
            ),
        ],
    },
    {
        "kind": "shot",
        "title": "The web UI — your home page",
        "image": "dashboard.png",
        "caption": "Signed in: quick actions, the tiles, recent changes, your queue and your jobs",
        "items": [
            ("Your queue", "Reviews only you, or your role, can act on."),
            ("Jobs", "Slow work — pins, validations, documents — runs in the background."),
            ("About this page", "Every screen ends with what it is for and a link to Help."),
            ("Search anywhere", "Ctrl-K; only what you may read is found."),
            ("On a phone", "Every page fits a 390-pixel screen."),
        ],
    },
    {
        "kind": "table",
        "title": "The web UI — where the work happens",
        "rows": [
            ["Area", "What you do there"],
            ["Catalog", "Find features and feature sets; versions, pins, data, lineage, history"],
            [
                "Workbench",
                "Define a feature, upload data, build a feature set, try a change in a workspace",
            ],
            [
                "Models",
                "The kernel designer, definitions, code, specification, parameters, documents",
            ],
            ["Warrants", "Draw a training warrant, fetch data, upload parameters, seal and verify"],
            ["Workflow", "Your queue, policies, delegations, campaigns, access requests"],
            ["Governance", "Findings, tiers, periodic reviews, challengers, the inventory"],
            ["Monitoring", "Every live model graded ok, watch or breach"],
            ["Admin", "Users, namespaces, sources, AI models, jobs, health, audit, custody"],
        ],
        "col_w": [2.2, 9.4],
        "size": 14,
    },
    {
        "kind": "lanes",
        "title": "Two teams, one contract",
        "top": {
            "name": "Model developers",
            "steps": [
                ("Design", "Write the mathematics"),
                ("Fit", "On the warrant's rows"),
                ("Upload", "Parameters, by checksum"),
                ("Iterate", "A new version, a new warrant"),
            ],
        },
        "middle": "MAYA — the warrant is the contract: data, mathematics, holdout, approval",
        "bottom": {
            "name": "Model risk",
            "steps": [
                ("Review", "Specification and code"),
                ("Score blind", "On the escrowed holdout"),
                ("Approve", "Never their own work"),
                ("Monitor", "Findings, reviews, drift"),
            ],
        },
        "items": [
            "Two teams, two release cycles, no hand-offs by e-mail: each works against the same "
            "warrant, and neither can change what the other relies on.",
            "The developer never sees the holdout; the validator never edits the model; the "
            "approver is never the author.",
        ],
    },
    {
        "kind": "table",
        "title": "Roles — who may do what",
        "rows": [
            ["Role", "Responsible for"],
            ["admin", "Users, roles, SSO, system settings, storage, workflow policy"],
            ["feature_designer", "Feature definitions, schemas, resolution rules, sources"],
            ["feature_manager", "Approval of features and feature sets, pin authorisation"],
            ["model_designer", "Model definitions, formula, Python artifact, LaTeX specification"],
            ["model_developer", "Training warrants, parameter upload, experiment iteration"],
            ["model_manager", "Approval of models, warrants and parameter sets"],
            ["model_owner", "Access policy for a model and its lineage; accountable for its use"],
            [
                "model_validator",
                "Independent validation: findings and periodic reviews; approves nothing",
            ],
            ["techops", "Runtime health, job queues, retries, storage compaction, backups"],
        ],
        "col_w": [2.6, 9.0],
        "size": 13,
        "note": "Roles grant capabilities; access to one object is also decided by its grants, "
        "with row filters, column masks and time bounds.",
    },
    {
        "kind": "table",
        "title": "Security in layers",
        "rows": [
            ["Layer", "Mechanism", "Protects against"],
            [
                "Sign-in",
                "Passwords with lockout; OIDC and SAML 2.0 single sign-on; TOTP and security keys",
                "Unauthorised access",
            ],
            [
                "API keys",
                "Narrowed to roles, namespaces, actions and networks; expiring",
                "Over-broad automation",
            ],
            [
                "Authorisation",
                "One function: the role ceiling, then grants, row filters and masks",
                "Privilege escalation",
            ],
            [
                "Uploaded code",
                "Six-rung validation, then a sandbox with no network or storage",
                "Hostile artifacts",
            ],
            [
                "Webhooks",
                "Signed; sent only to the address that was vetted",
                "DNS rebinding, leaks",
            ],
            ["Audit", "Hash-chained, anchored outside the database", "Rewritten history"],
        ],
        "col_w": [1.9, 6.6, 3.1],
        "size": 13,
        "note": "Every request is authenticated, authorised and audited — denials included, even "
        "though they roll back.",
    },
    {
        "kind": "columns",
        "title": "Deploy where the data is allowed to be",
        "col_h": 2.55,
        "cols": [
            {
                "head": "A laptop or one server",
                "items": [
                    "SQLite, one process",
                    "Python 3.13, no services to install",
                    "Data, lake and blobs on local disk",
                ],
                "foot": "Evaluation, a small team",
            },
            {
                "head": "A team server",
                "items": [
                    "PostgreSQL 16, 17 or 18",
                    "Several web processes and job workers",
                    "Behind your TLS proxy; your SSO",
                ],
                "foot": "Production",
            },
            {
                "head": "Air-gapped",
                "items": [
                    "No outbound calls required",
                    "LLM providers optional, self-hosted allowed",
                    "Evidence verifies offline",
                ],
                "foot": "Regulated, sovereign",
            },
        ],
        "items": [
            "Data never leaves your infrastructure unless a connector you configure sends it.",
            "One database at a time, never mixed; a database from another schema is refused at "
            "start-up, and the upgrade is export, recreate, import.",
        ],
    },
    {
        "kind": "context",
        "title": "A team deployment",
        "nodes": [
            {
                "id": "users",
                "x": 0.0,
                "y": 0.0,
                "w": 0.2,
                "h": 0.28,
                "head": "People and programs",
                "body": "Browser, SDK, CLI.",
            },
            {
                "id": "proxy",
                "x": 0.4,
                "y": 0.0,
                "w": 0.2,
                "h": 0.28,
                "head": "TLS proxy",
                "body": "Your certificate.",
            },
            {
                "id": "idp",
                "x": 0.8,
                "y": 0.0,
                "w": 0.2,
                "h": 0.28,
                "head": "Identity provider",
                "body": "OIDC or SAML.",
            },
            {
                "id": "maya",
                "x": 0.12,
                "y": 0.38,
                "w": 0.76,
                "h": 0.24,
                "head": "MAYA",
                "body": "Web processes and job workers, one configuration.",
            },
            {
                "id": "pg",
                "x": 0.0,
                "y": 0.74,
                "w": 0.22,
                "h": 0.26,
                "head": "PostgreSQL",
                "body": "Objects and audit.",
            },
            {
                "id": "lake",
                "x": 0.26,
                "y": 0.74,
                "w": 0.22,
                "h": 0.26,
                "head": "maya_delta lake",
                "body": "Rows and sealed pins.",
            },
            {
                "id": "anchor",
                "x": 0.52,
                "y": 0.74,
                "w": 0.22,
                "h": 0.26,
                "head": "Write-once storage",
                "body": "Audit anchors.",
            },
            {
                "id": "prom",
                "x": 0.78,
                "y": 0.74,
                "w": 0.22,
                "h": 0.26,
                "head": "Prometheus",
                "body": "/metrics, /healthz.",
            },
        ],
        "edges": [
            ["users", "proxy", ""],
            ["proxy", "maya", "HTTPS"],
            ["idp", "maya", "sign-in"],
            ["maya", "pg", ""],
            ["maya", "lake", ""],
            ["maya", "anchor", ""],
            ["maya", "prom", ""],
        ],
    },
    {
        "kind": "stats",
        "title": "Measured, not promised",
        "stats": [
            ("0.16 s", "catalog search p95 over 100,000 objects"),
            ("0.15 s", "worst metadata page p95 (target 0.3 s)"),
            ("59.7 MB/s", "pin write throughput, one worker"),
            ("1.26 s", "cold start to serving"),
        ],
        "items": [
            "A 50-column, ten-year daily feature set — 1.26 million rows — resolves in under a "
            "second warm, 6.1 s with forward fill on every column (target 15 s).",
            "20,000 feature sets, 10,000 models and 100,000 pins without degradation; 134,962 "
            "small jobs an hour on one worker.",
            "The one target not met reliably: 200 concurrent users on one node, p95 0.22–0.43 s "
            "against 0.3 s. Every figure is in docs/quality/BENCHMARKS.md with its result file.",
        ],
    },
]

SLIDES = LIFECYCLE + PLATFORM
