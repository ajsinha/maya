"""
The executive briefing: what MAYA is, what 0.3.0 delivers, what has been
measured, and what it does not do — for a reader deciding whether to use it.

Every figure is taken from the code, the README's "What's shipped" and
docs/BENCHMARKS.md. Nothing here is a projection: where something is not
measured or not built, the slide says so.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from maya.core.version import VERSION

CHAPTER = "MAYA · Executive Briefing"
TITLE = "MAYA — Executive Briefing"
SUBJECT = "What MAYA is, what version 0.3.0 delivers, and what it does not"

SLIDES = [
    {"kind": "title", "kicker": "MODEL RISK  ·  REPRODUCIBILITY  ·  EXECUTIVE BRIEFING",
     "title": ["Any number a model produced,", "rebuilt exactly, years later"],
     "sub": "MAYA — Model & AI Lifecycle Assurance.  Evidence, not assertion.",
     "agenda": ["What MAYA is, and the four failures it removes",
                "The warrant: a licence to train or run a model",
                "What version 0.3.0 delivers, with its tests",
                "What has been measured, and what fell short",
                "What it does not do, by decision and not yet"]},

    {"kind": "bullets", "kicker": "What MAYA is", "title": "A system of record for the whole chain behind a model's number",
     "intro": "MAYA holds the features, feature sets, models and warrants of a quantitative "
              "shop in one place: definition, data, documentation, approval and evidence.",
     "items": [("Definitions are code; data is a consequence",
                "MAYA stores how a number is produced. A version freezes how; a pin freezes what — "
                "the same bytes forever, verified by a content hash."),
               ("Models are mathematics, code, parameters and a specification together",
                "A model's formula is a typed expression tree, from which MAYA renders the "
                "specification document and diffs two versions mathematically."),
               ("A warrant binds model, data and parameters into one object",
                "Who was allowed to run what, on which data, with whose approval, becomes a query."),
               ("It does not train models and does not serve predictions",
                "Training runs on the user's own compute; MAYA issues the licence and keeps the evidence.")],
     "note": "Specification §1–§2. The specification, revision 2.3, is the authority; this deck describes version 0.3.0 of the code built from it."},

    {"kind": "cards", "kicker": "The problem", "title": "Four failures found in almost every quantitative shop",
     "cols": 2,
     "cards": [("1", "Feature logic lives in notebooks and SQL snippets",
                "Two teams compute “adjusted close” differently and neither is wrong. MAYA holds one "
                "versioned, approved definition, and an algebra for building on it."),
               ("2", "Training data is a file on a share drive",
                "When results are challenged nobody can produce the exact rows used. A MAYA pin is "
                "immutable and content-addressed; a warrant records the checksum that was downloaded."),
               ("3", "Mathematics, code and parameters drift apart",
                "A PDF, a repository and a spreadsheet. MAYA versions the formula, the code artifact, "
                "the parameter sets and the LaTeX specification against one another."),
               ("4", "Nothing binds model, data and parameters",
                "The warrant does: one auditable, transferable object, sealed, and revocable when "
                "the model is found to be wrong.")],
     "note": "Specification §1. Each of the four is a reproducibility failure waiting to be found by someone who is not on your side."},

    {"kind": "flow", "kicker": "The distinguishing primitive", "title": "The warrant: a licence to compute, not a document about one",
     "steps": [("Training warrant", "Freezes a model version against a pinned feature set; the contract and a leakage certificate are checked first."),
               ("Offline training", "The developer downloads the data with a checksum and trains on their own compute."),
               ("Parameter set", "Uploaded against that checksum; changed data is flagged and cannot be approved silently."),
               ("Execution warrant", "Model, parameters and input contract as a live licence: it expires, is revoked, and suspends on a covenant breach."),
               ("Bundle", "A signed archive that verifies offline, re-executes the model and fails on one changed byte.")],
     "box_h": 2.2,
     "items": ["A revoked, expired or suspended warrant fails every consuming SDK call closed, naming the person to contact.",
               "An escrowed holdout is scored by MAYA; the developer never receives it, and every scoring attempt is counted on the warrant.",
               "Proved by tests/test_warrants.py (the checksum cycle, the leakage certificate) and tests/test_security_regressions.py (each covenant)."]},

    {"kind": "table", "kicker": "Why not buy it", "title": "What each adjacent category does well, and where it stops",
     "rows": [["Category", "Good at", "Where it stops"],
              ["Feature stores", "Point-in-time joins, online serving, streaming, scale", "No approval workflow, no model side, no immutable snapshot for an auditor"],
              ["Lakehouse versioning", "Branch, tag and time travel over data", "Versions bytes, not meaning: no owner, no approval, no model linkage"],
              ["ML registries", "Run tracking, artifact lineage, metrics", "A run is a record of what happened, not a licence for what may happen"],
              ["Catalogs and lineage", "Discovery, ownership, column lineage", "Observe pipelines rather than gate them; hold no data"],
              ["Model-risk tools", "Inventory, validation workflow, regulator reporting", "Store a document saying a model was validated, not what lets you re-run it"]],
     "col_w": [2.3, 4.2, 5.2],
     "note": "Specification §27. MAYA's position is the seam between them: pinned, hash-verified data, an algebra over definitions, model mathematics as data, and a transferable licence to compute."},

    {"kind": "stats", "kicker": "Status", "title": "Version 0.3.0, built from specification revision 2.3",
     "stats": [(VERSION, "released 19 September 2026"),
               ("1,200+", "tests, on SQLite and PostgreSQL, run on Linux"),
               ("1 : 1", "REST endpoints to SDK methods, both ways, checked by a CI gate"),
               ("90%", "line-coverage floor enforced by gates.py --tests")],
     "items": ["The whole spine runs through the web UI, the REST API, the Python SDK and the CLI: source → feature → feature set → pin → model → training warrant → parameter set → execution warrant → reproducibility bundle.",
               "The suite includes real-browser tests in headless Chrome, a multi-process server, LibreOffice Calc as a judge of spreadsheet lifts, and a real openssl timestamp authority.",
               "Single sign-on is tested against a real identity provider, Keycloak 26.4, by opt-in tests that are skipped by default."]},

    {"kind": "table", "kicker": "What's shipped", "title": "Delivered by milestone, each with the tests that prove it",
     "rows": [["Milestone", "Delivered", "Proved by"],
              ["M0–M1", "Gate ladder; canonical bytes and content-defined fragments; two generated schema files; hash-chained audit; one authorization function; SSO, TOTP and WebAuthn", "test_foundation.py, test_api_and_gates.py, test_workflow_and_estate.py, test_authz_matrix.py, test_sso_mfa.py"],
              ["M2–M3", "maya_delta on two backends; byte-identical re-resolution (SC-1); point-in-time after restatement (SC-11); the feature algebra; sources", "test_maya_delta.py, test_features.py, test_resolution_*.py, test_properties.py"],
              ["M4–M5", "Feature sets, cascade pin, materialization policies, grant conditions; workflow as data, SoD, workspaces and shadow replay", "test_materialization.py, test_conditions.py, test_workflow_matrix.py, test_workspaces.py"],
              ["M6–M7", "Formula IR, sandboxed artifacts, Tectonic specifications, spreadsheets as models; warrants, covenants, signed bundles", "test_formula.py, test_sandbox_linux.py, test_spreadsheet.py, test_warrants.py, test_sdk_modes.py"],
              ["M8 and §29", "SDK record/replay, paging, several web processes, observability; licence algebra, custody anchors, the assistant as a recorded challenger", "test_paging.py, test_web_processes.py, test_custody.py, test_assistant.py"]],
     "col_w": [1.4, 5.6, 4.7],
     "note": "The README's “What's shipped” lists every capability with its module and tests. A capability without a test that exercises it is not listed."},

    {"kind": "stats", "kicker": "Measured", "title": "Three targets met on a shared workstation, one not met reliably",
     "stats": [("0.98 s", "SC-5 warm p95, 50 columns × 10 years × 500 symbols (target 15 s)"),
               ("0.16 s", "catalog search p95 over 100,000 objects (target 0.5 s)"),
               ("0.18 s", "SC-4 worst metadata page p95, PostgreSQL, 8 processes (target 0.3 s)"),
               ("0.34 s", "SC-3 median p95, 200 users (target 0.3 s): not met reliably")],
     "rows": [["Criterion", "Result", "Verdict"],
              ["SC-5 resolution", "No rules: warm p95 0.98 s, cold 1.0 s. forward_fill(limit=3) on every attribute: warm p95 6.1 s, cold 6.3 s", "pass"],
              ["Search, 100k objects", "p95 0.16 s (p50 0.08 s), 800,010 index rows", "pass"],
              ["SC-4 page latency", "Worst page p95 0.15 s on SQLite, one process; 0.18 s on PostgreSQL, 8 processes", "pass"],
              ["SC-3, 200 users", "Three runs: p95 0.34 s, 0.22 s, 0.43 s; 93–97 requests/s; no errors", "not met reliably"]],
     "col_w": [2.2, 7.4, 2.1],
     "note": "docs/BENCHMARKS.md, from the unedited result files in docs/benchmarks/. One developer workstation, not a benchmark host."},

    {"kind": "table", "kicker": "What fell short", "title": "SC-3: one run of three meets the target, and the median does not",
     "intro": "200 users, each with their own session, browsing random screens with 1–3 s think time for 60 s, on PostgreSQL with 8 web processes and the two-second principal cache.",
     "rows": [["Run", "Throughput", "p50", "p95", "Max", "Errors"],
              ["1", "95.3 req/s", "0.056 s", "0.345 s", "1.73 s", "0"],
              ["2", "96.6 req/s", "0.033 s", "0.215 s", "0.80 s", "0"],
              ["3", "93.4 req/s", "0.054 s", "0.425 s", "3.37 s", "0"]],
     "col_w": [1.0, 2.0, 1.6, 1.6, 1.6, 1.4],
     "note": "The configuration was identical across runs, so the spread is most likely the machine. That is an inference: only a quiet, dedicated host could make it a measurement, and a dedicated host is out of scope by decision. SC-3 therefore stands as not met reliably."},

    {"kind": "bullets", "kicker": "Out of scope by decision", "title": "Three things that will not be done, and what each costs",
     "items": [("The assistant is not tested against the live Claude API",
                "With the Claude provider the request is verified against a stub of the client only. Whether the live service answers as the stub does is unproven. The default deterministic provider is unaffected."),
               ("Windows and macOS are not exercised; only Linux is",
                "SC-14 — the full suite green on all three platforms — is therefore not met, and the code paths only those platforms use have never run. There is no hosted CI; the gate ladder runs locally and in the pre-commit hook."),
               ("There is no dedicated benchmark host",
                "Every figure comes from one shared workstation, so a verdict close to its target — SC-3 above all — is a verdict about this machine.")],
     "note": "README, “Out of scope by decision”. Stated as decisions, not as work in progress."},

    {"kind": "bullets", "kicker": "Not yet", "title": "Stated so nobody has to discover it",
     "items": ["PostgreSQL 14 and 15 have not been run; the suite has passed on PostgreSQL 16, 17 and 18 and on SQLite.",
               "Single sign-on is proven against one real identity provider, Keycloak 26.4, over http on loopback. No commercial IdP has been tried; SAML back-channel (SOAP) logout is not supported.",
               "The strong sandbox tier is Linux-only. True specification PDFs need Tectonic on each server; without it they are watermarked drafts.",
               "Most of the §24.3 capacity targets have not been measured, and SC-5 and search only on SQLite.",
               "Spreadsheet import is v1 scope: checked against LibreOffice Calc, not against workbooks saved by Microsoft Excel.",
               "Custody anchors are only as external as the file they are written to.",
               "SC-9, a new designer publishing a first model in under an hour, has not been timed with a real person. No external security review has been done, and the restore drill has not been performed on a real deployment."],
     "note": "README, “Not yet”, and the implementation plan's milestone status notes."},

    {"kind": "split", "kicker": "Deliberate non-goals", "title": "Where MAYA chooses to lose",
     "left": {"head": "Beaten on, by design",
              "items": ["Online serving latency", "Streaming freshness", "Raw scale",
                        "Connector breadth", "Out-of-the-box regulatory report templates",
                        "Where sub-10 ms serving is needed: MAYA governs the definition, and a serving layer consumes a sealed execution warrant."]},
     "right": {"head": "Accepted risks, mitigated not removed",
               "items": [("Two-store consistency on pin", "A saga and a reaper make a half-pin invisible, not impossible."),
                         ("Python's concurrency ceiling", "Several web processes on PostgreSQL; still the SC-3 shortfall."),
                         ("Execution outside MAYA", "Some lineage escapes; the SDK narrows it, nothing closes it."),
                         ("An empty catalog", "Someone must seed the first two namespaces.")]},
     "note": "Specification §2, §27.4 and §28.11."},

    {"kind": "cards", "kicker": "Security posture", "title": "Specified before it was built",
     "cols": 3,
     "cards": [("", "No silent defaults", "Where a setting changes behaviour materially there is no default outside dev; MAYA fails at startup naming it."),
               ("", "No secret in a tracked file", "config/application.yaml carries none; a CI gate checks it."),
               ("", "The admin password is a speed bump", "MAYA refuses to start with the default outside dev unless explicitly allowed."),
               ("", "User Python is hostile", "Static validation, an import allowlist and a sandboxed subprocess with no network; the tier is declared and recorded on every artifact."),
               ("", "One authorization function", "Every route is tested as anonymous, as no-role and as administrator; the role ceiling is never exceeded."),
               ("", "An audit log nobody can edit", "Append-only and hash-chained, with the chain head anchored outside the database.")],
     "note": "README, “Security posture”; tests/test_foundation.py, tests/test_api_contract.py, tests/test_sandbox_linux.py, tests/test_custody.py."},

    {"kind": "table", "kicker": "Model risk alignment", "title": "MAYA holds the evidence; the firm's policy decides what is enough",
     "rows": [["Expectation", "What MAYA holds"],
              ["Inventory", "A queryable register of models, versions, owners, maturity and dependencies"],
              ["Documentation", "A LaTeX specification per model version; submission is blocked while a required section is empty"],
              ["Independent review", "Segregation of duties enforced by workflow; review comments and decisions on the record"],
              ["Reproducibility", "Pins and warrants; a signed bundle that verifies and re-executes offline"],
              ["Change control", "Every version change classified breaking, behavioral or additive, with its impact shown to the approver"],
              ["Effective challenge", "The assistant's memo on every review: it never approves or blocks, and the reviewer records whether they agreed"]],
     "col_w": [2.6, 9.1],
     "note": "Specification §21.3, mapped to SR 26-2. This is an engineering description, not legal or regulatory advice (NOTICE §4)."},

    {"kind": "bullets", "kicker": "What adoption takes", "title": "Two questions the software cannot answer",
     "items": [("Which separation-of-duties preset the first namespaces get",
                "Small team, Standard or Regulated. All three ship; strictness is a namespace setting, stated on every review screen."),
               ("Who seeds the first two namespaces",
                "The platform cannot create its own critical mass of curated features. This is a sponsorship question, not an engineering one."),
               ("And the first five minutes",
                "A personal scratch namespace with no ceremony: `maya feature quick prices.csv` makes a typed, resolvable feature in one command. Ceremony scales with consequence.")],
     "note": "Specification §26.3 and §28.1."},

    {"kind": "bullets", "kicker": "In one slide", "title": "Evidence, not assertion",
     "items": ["One place that answers what the firm runs, who approved it, what it was fitted on — and lets that answer be checked rather than asserted.",
               "A warrant is a live licence: it expires, it is revoked, and it suspends itself when a covenant is breached.",
               "Version 0.3.0 runs the whole spine end to end, with more than 1,200 tests on Linux over SQLite and PostgreSQL.",
               "Three performance targets pass on one workstation; SC-3 does not pass reliably, and the deck says so.",
               "What is out of scope, and what is not yet done, is written down before anyone has to discover it."],
     "note": "Specification: docs/MAYA_Requirements_and_Design.md · Plan: docs/IMPLEMENTATION_PLAN.md · Measurements: docs/BENCHMARKS.md"},
]
